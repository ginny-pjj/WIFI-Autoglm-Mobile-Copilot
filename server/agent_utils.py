import re
from typing import Literal

TraceKind = Literal["observe", "think", "act", "result", "system"]

PHASE_LABELS = {
    "observe": "OBSERVE",
    "think": "THINK",
    "act": "ACTION",
    "result": "RESULT",
}


def classify_log_line(message: str) -> TraceKind:
    raw = message

    if any(k in raw for k in ("思考过程", "💭", "Think:", "think:", "调用 Open-AutoGLM")):
        return "think"
    if any(k in raw for k in ("执行动作", "🎯", "Parsing action:", "Action:", "do(action=")):
        return "act"
    if any(k in raw for k in ("任务完成", "Result:", "finish(message=", "✅ 任务完成", "finished successfully")):
        return "result"
    if any(k in raw for k in ("截图", "screenshot", "Screen Info", "Observe", "获取当前手机", "准备设备")):
        return "observe"
    text = message.lower()
    if any(k in text for k in ("launch", "tap", "swipe", "type", "back", "home")):
        return "act"
    return "system"


def _strip_timestamp(line: str) -> str:
    return re.sub(r"^\[\d{2}:\d{2}:\d{2}\]\s*", "", line).strip()


def is_noise_line(message: str) -> bool:
    text = message.strip()
    if not text:
        return True
    if text in {"执行结果:", "执行结果"}:
        return True
    if re.fullmatch(r"'action': '[A-Za-z]+'", text):
        return True
    if re.fullmatch(r"Real task finished successfully", text, flags=re.I):
        return True
    if re.fullmatch(r"Mock task finished successfully", text, flags=re.I):
        return True
    if text.startswith("Failed: Open-AutoGLM exited with code"):
        return True
    return False


def simplify_message(message: str, kind: TraceKind) -> str:
    text = message.strip()

    finish_match = re.search(r"finish\(message=['\"](.+?)['\"]", text)
    if finish_match:
        return finish_match.group(1)

    if "Parsing action:" in text:
        action_match = re.search(r"do\(action='([^']+)'(?:,\s*([^)]+))?\)", text)
        if action_match:
            action = action_match.group(1)
            extras = action_match.group(2) or ""
            if action == "Launch":
                app_match = re.search(r"app='([^']+)'", extras)
                return f"打开应用：{app_match.group(1) if app_match else '目标 App'}"
            if action == "Tap":
                coord_match = re.search(r"element=\[(\d+),\s*(\d+)\]", extras)
                if coord_match:
                    return f"点击屏幕 ({coord_match.group(1)}, {coord_match.group(2)})"
                return "点击屏幕元素"
            if action == "Type":
                text_match = re.search(r"text='([^']*)'", extras)
                return f"输入文字：{text_match.group(1) if text_match else '...'}"
            if action == "Swipe":
                return "滑动屏幕"
            if action == "Back":
                return "返回上一页"
            if action == "Home":
                return "返回桌面"
            return f"执行动作：{action}"

    if "执行动作:" in text:
        return text.split("执行动作:", 1)[-1].strip() or text

    if kind == "think":
        for prefix in ("Think:", "思考过程:", "思考过程：", "💭"):
            if prefix in text:
                text = text.split(prefix, 1)[-1].strip()
        if len(text) > 160:
            return text[:160] + "..."
        return text

    if kind == "observe":
        replacements = {
            "Observe: 任务开始前准备设备环境": "观察手机屏幕，准备执行环境",
            "Observe: 模拟返回桌面": "观察设备状态（Mock）",
            "Observe: 获取当前手机屏幕状态": "截取当前屏幕画面",
            "Act: 唤醒屏幕并返回桌面": "唤醒设备并返回桌面",
            "Result: 设备已回到桌面，开始 Agent 任务": "设备就绪，开始 Agent 循环",
        }
        for old, new in replacements.items():
            if old in text:
                return new

    if kind == "result" and "✅" in text:
        return re.sub(r"^✅\s*", "", text)

    if text.startswith("Result:"):
        return text.split("Result:", 1)[-1].strip()

    return text


def _result_priority(message: str) -> int:
    if "finish(message=" in message or "任务完成" in message:
        return 3
    if len(message) > 40:
        return 2
    if "successfully" in message.lower():
        return 0
    return 1


def build_trace_from_logs(logs: list[str]) -> list[dict[str, str]]:
    """Raw per-line trace for debug mode."""
    trace: list[dict[str, str]] = []
    for line in logs:
        message = _strip_timestamp(line)
        if not message:
            continue
        trace.append({
            "kind": classify_log_line(message),
            "message": message,
        })
    return trace


def consolidate_trace_steps(logs: list[str]) -> list[dict[str, str | int]]:
    """Merge noisy Open-AutoGLM logs into clean step-based trace."""
    pending: dict[str, str] = {}
    steps: list[dict[str, str | int]] = []

    def flush() -> None:
        nonlocal pending
        if not pending:
            return
        step_id = len(steps) + 1
        kind = pending["kind"]
        steps.append({
            "step_id": step_id,
            "kind": kind,
            "title": f"Step {step_id} · {PHASE_LABELS.get(kind, kind.upper())}",
            "message": pending["message"],
        })
        pending = {}

    for line in logs:
        message = _strip_timestamp(line)
        if is_noise_line(message):
            continue

        kind = classify_log_line(message)
        if kind == "system":
            continue

        summary = simplify_message(message, kind)
        if not summary:
            continue

        if kind == "result":
            if pending.get("kind") == "result":
                if _result_priority(summary) >= _result_priority(pending["message"]):
                    pending["message"] = summary
                continue
            flush()
            pending = {"kind": kind, "message": summary}
            continue

        if pending.get("kind") == "result":
            flush()

        if pending.get("kind") == kind == "act":
            if "Parsing action" in message or "执行动作" in message or "do(action=" in message:
                pending["message"] = summary
            continue

        if pending.get("kind") == kind == "think":
            if len(summary) > len(pending["message"]):
                pending["message"] = summary
            continue

        flush()
        pending = {"kind": kind, "message": summary}

    flush()
    return steps


def pick_highlight_trace(trace: list[dict[str, str]]) -> list[dict[str, str]]:
    """Backward-compatible condensed trace."""
    kinds = {"think", "act", "result", "observe"}
    condensed: list[dict[str, str]] = []
    for item in trace:
        if item["kind"] in kinds:
            if condensed and condensed[-1]["message"] == item["message"]:
                continue
            condensed.append(item)
    return condensed[-30:]
