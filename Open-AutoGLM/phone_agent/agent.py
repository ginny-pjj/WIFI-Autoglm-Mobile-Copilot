"""Main PhoneAgent class for orchestrating phone automation."""

import json
import os
import time
import traceback
from dataclasses import dataclass
from typing import Any, Callable

from phone_agent.actions import ActionHandler
from phone_agent.actions.handler import do, finish, parse_action
from phone_agent.adb.device import ensure_meituan_home_tab
from phone_agent.adb.screenshot import log_screenshot_decision, set_screenshot_context
from phone_agent.config import get_messages, get_system_prompt
from phone_agent.device_factory import get_device_factory
from phone_agent.model import ModelClient, ModelConfig
from phone_agent.model.client import MessageBuilder


@dataclass
class AgentConfig:
    """Configuration for the PhoneAgent."""

    max_steps: int = 100
    device_id: str | None = None
    lang: str = "cn"
    system_prompt: str | None = None
    verbose: bool = True

    def __post_init__(self):
        if self.system_prompt is None:
            self.system_prompt = get_system_prompt(self.lang)


@dataclass
class StepResult:
    """Result of a single agent step."""

    success: bool
    finished: bool
    action: dict[str, Any] | None
    thinking: str
    message: str | None = None


def _ui_text_blob(ui_elements: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for element in ui_elements:
        for key in ("text", "content_desc", "resource_id", "class"):
            value = element.get(key)
            if value:
                parts.append(str(value))
    return " ".join(parts)


def _element_label(element: dict[str, Any]) -> str:
    parts: list[str] = []
    for key in ("text", "content_desc", "resource_id", "class"):
        value = element.get(key)
        if value:
            parts.append(str(value))
    return " ".join(parts)


def _pick_meituan_search_candidates(ui_elements: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates: list[tuple[int, dict[str, Any]]] = []
    for element in ui_elements:
        bounds = element.get("bounds") or []
        center = element.get("center") or []
        if len(bounds) != 4 or len(center) != 2:
            continue

        x1, y1, x2, y2 = bounds
        width = x2 - x1
        if width < 260:
            continue
        if center[1] > 900:
            continue

        label = _element_label(element).lower()
        score = 0
        if "edittext" in str(element.get("class", "")).lower():
            score += 8
        if element.get("clickable"):
            score += 3
        if element.get("focusable"):
            score += 3
        if width >= 420:
            score += 3

        for keyword in ("搜索", "search", "query", "输入", "查找"):
            if keyword in label:
                score += 12

        for keyword in (
            "问小团",
            "assistant",
            "chat",
            "address",
            "location",
            "地址",
            "定位",
            "收货",
            "闪购",
        ):
            if keyword in label:
                score -= 14

        if score > 0:
            item = dict(element)
            item["_search_score"] = score
            candidates.append((score, item))

    candidates.sort(key=lambda item: item[0], reverse=True)
    return [item[1] for item in candidates[:3]]


def _looks_like_meituan_off_track_page(current_app: str, ui_elements: list[dict[str, Any]]) -> bool:
    if current_app != "美团":
        return False
    blob = _ui_text_blob(ui_elements)
    address_markers = (
        "选择收货地址",
        "我的地址",
        "国内城市",
        "海外地区",
        "地图选点",
        "重新定位",
        "收货地址",
        "新增地址",
        "请输入收货地址",
        "附近地址",
    )
    if sum(1 for marker in address_markers if marker in blob) >= 2:
        return True
    # 闪购子频道：顶部标题「闪购」且没有首页常见外卖/团购入口时，视为偏离搜索任务
    if "闪购" in blob and "外卖" not in blob and "团购" not in blob:
        return True
    return False


def _has_safe_ui_tree(ui_elements: list[dict[str, Any]]) -> bool:
    if not ui_elements:
        return False
    blob = _ui_text_blob(ui_elements)
    unsafe_markers = ("支付", "密码", "验证码", "登录", "人脸", "指纹", "银行卡")
    if any(marker in blob for marker in unsafe_markers):
        return False
    return any(element.get("text") or element.get("content_desc") or element.get("resource_id") for element in ui_elements)


class PhoneAgent:
    """
    AI-powered agent for automating Android phone interactions.

    The agent uses a vision-language model to understand screen content
    and decide on actions to complete user tasks.

    Args:
        model_config: Configuration for the AI model.
        agent_config: Configuration for the agent behavior.
        confirmation_callback: Optional callback for sensitive action confirmation.
        takeover_callback: Optional callback for takeover requests.

    Example:
        >>> from phone_agent import PhoneAgent
        >>> from phone_agent.model import ModelConfig
        >>>
        >>> model_config = ModelConfig(base_url="http://localhost:8000/v1")
        >>> agent = PhoneAgent(model_config)
        >>> agent.run("Open WeChat and send a message to John")
    """

    def __init__(
        self,
        model_config: ModelConfig | None = None,
        agent_config: AgentConfig | None = None,
        confirmation_callback: Callable[[str], bool] | None = None,
        takeover_callback: Callable[[str], None] | None = None,
    ):
        self.model_config = model_config or ModelConfig()
        self.agent_config = agent_config or AgentConfig()

        self.model_client = ModelClient(self.model_config)
        self.action_handler = ActionHandler(
            device_id=self.agent_config.device_id,
            confirmation_callback=confirmation_callback,
            takeover_callback=takeover_callback,
        )

        self._context: list[dict[str, Any]] = []
        self._step_count = 0

    def run(self, task: str) -> str:
        """
        Run the agent to complete a task.

        Args:
            task: Natural language description of the task.

        Returns:
            Final message from the agent.
        """
        self._context = []
        self._step_count = 0

        # First step with user prompt
        result = self._execute_step(task, is_first=True)

        if result.finished:
            return result.message or "Task completed"

        # Continue until finished or max steps reached
        while self._step_count < self.agent_config.max_steps:
            result = self._execute_step(is_first=False)

            if result.finished:
                return result.message or "Task completed"

        return "Max steps reached"

    def step(self, task: str | None = None) -> StepResult:
        """
        Execute a single step of the agent.

        Useful for manual control or debugging.

        Args:
            task: Task description (only needed for first step).

        Returns:
            StepResult with step details.
        """
        is_first = len(self._context) == 0

        if is_first and not task:
            raise ValueError("Task is required for the first step")

        return self._execute_step(task, is_first)

    def reset(self) -> None:
        """Reset the agent state for a new task."""
        self._context = []
        self._step_count = 0

    def _execute_step(
        self, user_prompt: str | None = None, is_first: bool = False
    ) -> StepResult:
        """Execute a single step of the agent loop."""
        self._step_count += 1

        # Capture current screen state
        device_factory = get_device_factory()
        set_screenshot_context(
            step=self._step_count,
            tag="observe",
            task_id=os.getenv("PHONE_AGENT_SCREENSHOT_TASK_ID"),
        )
        screenshot = device_factory.get_screenshot(self.agent_config.device_id)
        current_app = device_factory.get_current_app(self.agent_config.device_id)
        ui_elements = self._get_ui_elements(device_factory)

        if self._maybe_recover_meituan_off_track_page(device_factory, current_app, ui_elements):
            set_screenshot_context(
                step=self._step_count,
                tag="observe_after_back",
                task_id=os.getenv("PHONE_AGENT_SCREENSHOT_TASK_ID"),
                attempt=2,
            )
            screenshot = device_factory.get_screenshot(self.agent_config.device_id)
            current_app = device_factory.get_current_app(self.agent_config.device_id)
            ui_elements = self._get_ui_elements(device_factory)

        is_sensitive = screenshot.is_sensitive
        if is_sensitive and _has_safe_ui_tree(ui_elements):
            print("Observe: screenshot marked sensitive, but UI tree is available; continue with UI tree grounding")
            is_sensitive = False

        screen_info = self._build_screen_info(current_app, is_sensitive, ui_elements)
        task_hint = self._build_task_hint(user_prompt, current_app, ui_elements)

        image_base64 = screenshot.base64_data
        if screenshot.is_sensitive and ui_elements:
            image_base64 = None

        log_screenshot_decision(
            screenshot,
            current_app=current_app,
            ui_elements_count=len(ui_elements),
            effective_sensitive=is_sensitive,
            image_sent_to_model=image_base64 is not None,
        )

        # Build messages
        if is_first:
            self._context.append(
                MessageBuilder.create_system_message(self.agent_config.system_prompt)
            )

            text_content = f"{user_prompt}\n\n{screen_info}\n\n{task_hint}"

            self._context.append(
                MessageBuilder.create_user_message(
                    text=text_content, image_base64=image_base64
                )
            )
        else:
            text_content = f"** Screen Info **\n\n{screen_info}\n\n{task_hint}"

            self._context.append(
                MessageBuilder.create_user_message(
                    text=text_content, image_base64=image_base64
                )
            )

        # Get model response
        try:
            msgs = get_messages(self.agent_config.lang)
            print("\n" + "=" * 50)
            print(f"💭 {msgs['thinking']}:")
            print("-" * 50)
            response = self.model_client.request(self._context)
        except Exception as e:
            if self.agent_config.verbose:
                traceback.print_exc()
            return StepResult(
                success=False,
                finished=True,
                action=None,
                thinking="",
                message=f"Model error: {e}",
            )

        # Parse action from response
        try:
            action = parse_action(response.action)
        except ValueError:
            if self.agent_config.verbose:
                traceback.print_exc()
            action = finish(message=response.action)

        if self.agent_config.verbose:
            # Print thinking process
            print("-" * 50)
            print(f"🎯 {msgs['action']}:")
            print(json.dumps(action, ensure_ascii=False, indent=2))
            print("=" * 50 + "\n")

        # Remove image from context to save space
        self._context[-1] = MessageBuilder.remove_images_from_message(self._context[-1])

        # Execute action
        try:
            result = self.action_handler.execute(
                action, screenshot.width, screenshot.height
            )
        except Exception as e:
            if self.agent_config.verbose:
                traceback.print_exc()
            result = self.action_handler.execute(
                finish(message=str(e)), screenshot.width, screenshot.height
            )

        # Add assistant response to context
        self._context.append(
            MessageBuilder.create_assistant_message(
                f"<think>{response.thinking}</think><answer>{response.action}</answer>"
            )
        )

        # Check if finished
        finished = action.get("_metadata") == "finish" or result.should_finish

        if not result.success and result.message:
            print(f"❌ Action failed: {result.message}")

        if finished and self.agent_config.verbose:
            msgs = get_messages(self.agent_config.lang)
            print("\n" + "🎉 " + "=" * 48)
            print(
                f"✅ {msgs['task_completed']}: {result.message or action.get('message', msgs['done'])}"
            )
            print("=" * 50 + "\n")

        return StepResult(
            success=result.success,
            finished=finished,
            action=action,
            thinking=response.thinking,
            message=result.message or action.get("message"),
        )

    @property
    def context(self) -> list[dict[str, Any]]:
        """Get the current conversation context."""
        return self._context.copy()

    @property
    def step_count(self) -> int:
        """Get the current step count."""
        return self._step_count

    def _get_ui_elements(self, device_factory) -> list[dict[str, Any]]:
        if os.getenv("PHONE_AGENT_UI_TREE", "true").lower() not in ("1", "true", "yes"):
            return []
        try:
            return device_factory.get_ui_elements(self.agent_config.device_id) or []
        except Exception as exc:
            print(f"UI tree error: {exc}")
            return []

    def _maybe_recover_meituan_off_track_page(
        self,
        device_factory,
        current_app: str,
        ui_elements: list[dict[str, Any]],
    ) -> bool:
        if not _looks_like_meituan_off_track_page(current_app, ui_elements):
            return False
        blob = _ui_text_blob(ui_elements)
        if "闪购" in blob and "外卖" not in blob and "团购" not in blob:
            print("Observe: detected Meituan 闪购 tab; tapping bottom 推荐 to return home")
            ensure_meituan_home_tab(self.agent_config.device_id)
            time.sleep(1.5)
            return True
        print("Observe: detected Meituan off-track page (address); pressing Back twice to return")
        device_factory.back(self.agent_config.device_id)
        time.sleep(1.2)
        device_factory.back(self.agent_config.device_id)
        time.sleep(1.5)
        return True

    def _build_task_hint(
        self,
        user_prompt: str | None,
        current_app: str,
        ui_elements: list[dict[str, Any]],
    ) -> str:
        blob = _ui_text_blob(ui_elements)
        hints: list[str] = []
        if current_app == "美团" and ("搜索" in blob or "search" in blob.lower()):
            search_candidates = _pick_meituan_search_candidates(ui_elements)
            hints.append(
                "Execution hint: 当前在美团，请优先根据 ui_elements 中包含 搜索/search/输入 的元素点击搜索框，随后执行 Type 输入用户要搜索的关键词。"
            )
            hints.append(
                "Execution hint: 禁止点击顶部定位/地址栏（如 牡丹江、师范学院、重新定位）；禁止进入 闪购/收货地址 页面；只点击首页中间带「搜索」按钮的搜索框。"
            )
            if search_candidates:
                lines = []
                for idx, candidate in enumerate(search_candidates, start=1):
                    lines.append(
                        f"candidate_{idx}: center={candidate.get('center')} bounds={candidate.get('bounds')} label={_element_label(candidate)[:120]}"
                    )
                hints.append(
                    "Execution hint: Prefer these Meituan search-box candidates from ui_elements; tap candidate_1 first unless it is clearly an address/location/assistant field.\n"
                    + "\n".join(lines)
                )
        if user_prompt and "美团" in user_prompt and ("搜索" in user_prompt or "搜" in user_prompt):
            hints.append(
                "Execution hint: 这是美团搜索任务；不要因为截图黑屏就 Take_over。若 ui_elements 可读且没有登录/支付/验证码/密码等安全元素，请继续用 ui_elements 完成搜索。"
            )
            hints.append(
                "Execution hint: 若当前不在美团首页，先连续 Back 回到首页，再点击搜索框；不要 Launch 已打开的美团。"
            )
        if not hints:
            return ""
        return "\n".join(hints)

    def _build_screen_info(
        self, current_app: str, is_sensitive: bool, ui_elements: list[dict[str, Any]]
    ) -> str:
        extra: dict[str, Any] = {"screen_is_sensitive": is_sensitive}
        if ui_elements:
            extra["ui_elements"] = ui_elements
        return MessageBuilder.build_screen_info(current_app, **extra)
