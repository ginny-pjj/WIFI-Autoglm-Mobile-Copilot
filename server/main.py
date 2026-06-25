import base64
import json
import os
import re
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from agent_utils import build_trace_from_logs, consolidate_trace_steps, pick_highlight_trace

def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_env_file(Path(__file__).with_name(".env"))
load_env_file(Path(__file__).with_name(".env.cloud"))


def _default_work_root() -> Path:
    if value := os.getenv("AUTOGLM_WORK_ROOT"):
        return Path(value)
    return Path("D:/autoglm-mobile-work") if sys.platform == "win32" else Path("/app")


def _default_adb_path(work_root: Path) -> Path:
    if value := os.getenv("ADB_PATH"):
        return Path(value)
    if sys.platform == "win32":
        return work_root / "platform-tools" / "adb.exe"
    return Path("/usr/bin/adb")


def _default_python_path() -> Path:
    if value := os.getenv("PYTHON_PATH"):
        return Path(value)
    if sys.platform == "win32":
        return Path("D:/autoglm-mobile-work/.venv/Scripts/python.exe")
    return Path(sys.executable)


WORK_ROOT = _default_work_root()
ADB_PATH = _default_adb_path(WORK_ROOT)
AUTOGLM_DIR = Path(os.getenv("AUTOGLM_DIR", WORK_ROOT / "Open-AutoGLM"))
PYTHON_PATH = _default_python_path()
AUTOGLM_BASE_URL = os.getenv("AUTOGLM_BASE_URL", "https://open.bigmodel.cn/api/paas/v4")
AUTOGLM_MODEL = os.getenv("AUTOGLM_MODEL", "autoglm-phone")
BIGMODEL_API_KEY = os.getenv("BIGMODEL_API_KEY", "")
DEFAULT_TASK_TIMEOUT = int(os.getenv("TASK_TIMEOUT_SECONDS", "240"))
PREPARE_HOME_BEFORE_TASK = os.getenv("PREPARE_HOME_BEFORE_TASK", "true").lower() == "true"
ADB_CONNECT_ADDRESS = os.getenv("ADB_CONNECT_ADDRESS", "").strip()
PHONE_AGENT_DEVICE_ID = os.getenv("PHONE_AGENT_DEVICE_ID", ADB_CONNECT_ADDRESS).strip()
ADB_CONNECT_TIMEOUT = int(os.getenv("ADB_CONNECT_TIMEOUT", "45"))

if str(AUTOGLM_DIR) not in sys.path:
    sys.path.insert(0, str(AUTOGLM_DIR))

app = FastAPI(
    title="AutoGLM Mobile Copilot Server",
    description="Mobile control server for Open-AutoGLM Phone Agent demo.",
    version="0.4.1",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

TaskMode = Literal["mock", "real"]
TaskStatus = Literal["pending", "running", "success", "failed", "cancelled"]


class TaskCreateRequest(BaseModel):
    task: str = Field(..., min_length=1, max_length=500)
    mode: TaskMode = "mock"
    prepare_home: bool = True


class TraceStep(BaseModel):
    kind: str
    message: str


class StructuredTraceStep(BaseModel):
    step_id: int
    kind: str
    title: str
    message: str


class TaskRecord(BaseModel):
    task_id: str
    task: str
    mode: TaskMode
    status: TaskStatus
    created_at: str
    updated_at: str
    logs: list[str] = []
    trace: list[TraceStep] = []
    steps: list[StructuredTraceStep] = []
    return_code: int | None = None
    error: str = ""
    duration_ms: int | None = None


tasks: dict[str, TaskRecord] = {}
tasks_lock = threading.Lock()
task_runtimes: dict[str, dict[str, object]] = {}
task_runtimes_lock = threading.Lock()


def init_task_runtime(task_id: str) -> threading.Event:
    cancel_event = threading.Event()
    with task_runtimes_lock:
        task_runtimes[task_id] = {
            "cancel_event": cancel_event,
            "process": None,
            "started_at": time.time(),
        }
    return cancel_event


def get_cancel_event(task_id: str) -> threading.Event | None:
    with task_runtimes_lock:
        runtime = task_runtimes.get(task_id)
        if not runtime:
            return None
        return runtime["cancel_event"]  # type: ignore[return-value]


def set_task_process(task_id: str, process: subprocess.Popen[str]) -> None:
    with task_runtimes_lock:
        runtime = task_runtimes.get(task_id)
        if runtime is not None:
            runtime["process"] = process


def is_task_cancelled(task_id: str) -> bool:
    event = get_cancel_event(task_id)
    return bool(event and event.is_set())


def cleanup_task_runtime(task_id: str) -> None:
    with task_runtimes_lock:
        task_runtimes.pop(task_id, None)


def finish_cancelled_task(task_id: str, started_at: float) -> None:
    with tasks_lock:
        record = tasks.get(task_id)
        if not record or record.status not in {"pending", "running"}:
            return
    duration_ms = int((time.time() - started_at) * 1000)
    update_task(
        task_id,
        status="cancelled",
        duration_ms=duration_ms,
        error="Task cancelled by user",
    )
    append_log(task_id, "Result: 任务已由用户停止")
    refresh_trace(task_id)


def cancel_task(task_id: str) -> bool:
    with tasks_lock:
        record = tasks.get(task_id)
        if not record:
            return False
        if record.status not in {"pending", "running"}:
            return False

    event = get_cancel_event(task_id)
    if event:
        event.set()

    process: subprocess.Popen[str] | None = None
    with task_runtimes_lock:
        runtime = task_runtimes.get(task_id)
        if runtime:
            process = runtime.get("process")  # type: ignore[assignment]

    if process and process.poll() is None:
        try:
            process.terminate()
            process.wait(timeout=2)
        except Exception:
            try:
                process.kill()
            except Exception:
                pass

    kill_orphan_agent_processes()

    with tasks_lock:
        record = tasks.get(task_id)
        if record and record.status in {"pending", "running"}:
            started_at = time.time()
            with task_runtimes_lock:
                runtime = task_runtimes.get(task_id)
                if runtime and isinstance(runtime.get("started_at"), float):
                    started_at = runtime["started_at"]  # type: ignore[assignment]
            finish_cancelled_task(task_id, started_at)
            return True
    return False


def kill_orphan_agent_processes() -> None:
    patterns = [
        "python.*main.py.*--base-url",
        "/app/Open-AutoGLM/main.py",
    ]
    for pattern in patterns:
        try:
            subprocess.run(["pkill", "-TERM", "-f", pattern], capture_output=True, timeout=3)
        except Exception:
            pass
    time.sleep(0.5)
    for pattern in patterns:
        try:
            subprocess.run(["pkill", "-KILL", "-f", pattern], capture_output=True, timeout=3)
        except Exception:
            pass


def cancel_other_running_tasks(active_task_id: str) -> list[str]:
    cancelled_ids: list[str] = []
    with tasks_lock:
        running_ids = [
            task_id
            for task_id, record in tasks.items()
            if task_id != active_task_id and record.status in {"pending", "running"}
        ]
    for task_id in running_ids:
        if cancel_task(task_id):
            cancelled_ids.append(task_id)
    return cancelled_ids


def now_text() -> str:
    return datetime.now().isoformat(timespec="seconds")


def refresh_trace(task_id: str) -> None:
    with tasks_lock:
        record = tasks.get(task_id)
        if not record:
            return
        raw_steps = build_trace_from_logs(record.logs)
        consolidated = consolidate_trace_steps(record.logs)
        record.trace = [TraceStep(**step) for step in raw_steps]
        record.steps = [StructuredTraceStep(**step) for step in consolidated]


def append_log(task_id: str, message: str) -> None:
    with tasks_lock:
        record = tasks.get(task_id)
        if not record:
            return
        record.logs.append(f"[{datetime.now().strftime('%H:%M:%S')}] {message}")
        record.updated_at = now_text()
    refresh_trace(task_id)


def update_task(task_id: str, **kwargs) -> None:
    with tasks_lock:
        record = tasks.get(task_id)
        if not record:
            return
        for key, value in kwargs.items():
            setattr(record, key, value)
        record.updated_at = now_text()


def adb_prefix() -> list[str]:
    args = [str(ADB_PATH)]
    if PHONE_AGENT_DEVICE_ID:
        args.extend(["-s", PHONE_AGENT_DEVICE_ID])
    return args


def adb_device_alive(device_id: str) -> bool:
    try:
        result = run_command(
            [str(ADB_PATH), "-s", device_id, "shell", "echo", "ok"],
            timeout=min(12, ADB_CONNECT_TIMEOUT),
        )
        return result.returncode == 0 and "ok" in (result.stdout + result.stderr)
    except Exception:
        return False


def ensure_remote_adb(task_id: str) -> bool:
    if not ADB_CONNECT_ADDRESS:
        return True

    target = PHONE_AGENT_DEVICE_ID or ADB_CONNECT_ADDRESS
    append_log(task_id, "Observe: 准备 Open-AutoGLM PhoneAgent (截图→VLM→ADB 循环)")
    append_log(task_id, f"Observe: 检查远程 ADB 连接 {target}")

    try:
        devices_result = run_command([str(ADB_PATH), "devices"], timeout=10)
        devices_raw = devices_result.stdout + devices_result.stderr
        if f"{target}\toffline" in devices_raw or f"{target} offline" in devices_raw:
            append_log(task_id, f"Act: 设备 offline，先 adb disconnect {target}")
            run_command([str(ADB_PATH), "disconnect", target], timeout=10)
    except Exception:
        pass

    if adb_device_alive(target):
        append_log(task_id, f"Result: 远程 ADB 已就绪 ({target})")
        return True

    append_log(task_id, f"Act: adb connect {ADB_CONNECT_ADDRESS}")
    try:
        from phone_agent.adb.connection import ADBConnection

        conn = ADBConnection(str(ADB_PATH))
        ok, message = conn.connect(ADB_CONNECT_ADDRESS, timeout=ADB_CONNECT_TIMEOUT)
    except Exception as exc:
        ok, message = False, str(exc)

    if ok and adb_device_alive(target):
        append_log(task_id, f"Result: {message}")
        return True

    if not ok:
        detail = message
    else:
        detail = f"adb connect 成功但设备 {target} 无响应，请检查手机无线调试与 Tailscale"
    update_task(task_id, status="failed", error=detail)
    append_log(task_id, f"Failed: {detail}")
    return False


def build_env(task_id: str | None = None) -> dict[str, str]:
    env = os.environ.copy()
    env["PATH"] = f"{ADB_PATH.parent};{env.get('PATH', '')}"
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    if PHONE_AGENT_DEVICE_ID:
        env["PHONE_AGENT_DEVICE_ID"] = PHONE_AGENT_DEVICE_ID
    for key in (
        "AUTOGLM_SAFETY_CHECK",
        "AUTOGLM_SENSITIVE_FILTER",
        "PHONE_AGENT_FAIL_ON_TAKEOVER",
        "PHONE_AGENT_CONTINUE_ON_SCREENSHOT_TAKEOVER",
        "PHONE_AGENT_SCREENSHOT_TIMEOUT",
        "PHONE_AGENT_SCREENSHOT_EXEC_OUT",
        "PHONE_AGENT_SCREENSHOT_MAX_LONG_EDGE",
        "PHONE_AGENT_MAX_STEPS",
        "PHONE_AGENT_UI_TREE",
        "PHONE_AGENT_ADB_CMD_TIMEOUT",
        "ADB_CONNECT_ADDRESS",
    ):
        if key in os.environ:
            env[key] = os.environ[key]
    if task_id:
        env["PHONE_AGENT_SCREENSHOT_TASK_ID"] = task_id
        env.setdefault("PHONE_AGENT_SCREENSHOT_DEBUG", "true")
        env.setdefault(
            "PHONE_AGENT_SCREENSHOT_DUMP_DIR",
            str(WORK_ROOT / "screenshot_debug"),
        )
    return env


def run_command(args: list[str], timeout: int = 20, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=str(cwd) if cwd else None,
        env=build_env(),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )


def adb_shell(command: str) -> bool:
    if not ADB_PATH.exists():
        return False
    try:
        result = run_command([*adb_prefix(), "shell", command], timeout=30)
        return result.returncode == 0
    except Exception:
        return False


def adb_shell_result(command: str, timeout: int = 30) -> subprocess.CompletedProcess[str]:
    return run_command([*adb_prefix(), "shell", command], timeout=timeout)


def adb_keyevent(keycode: str) -> bool:
    return adb_shell(f"input keyevent {keycode}")


def adb_tap(x: int, y: int) -> bool:
    return adb_shell(f"input tap {x} {y}")


def adb_broadcast_b64_text(text: str) -> bool:
    encoded = base64.b64encode(text.encode("utf-8")).decode("utf-8")
    result = run_command(
        [
            *adb_prefix(),
            "shell",
            "am",
            "broadcast",
            "-a",
            "ADB_INPUT_B64",
            "--es",
            "msg",
            encoded,
        ],
        timeout=30,
    )
    return result.returncode == 0


def adb_set_adb_keyboard() -> bool:
    result = run_command(
        [*adb_prefix(), "shell", "ime", "set", "com.android.adbkeyboard/.AdbIME"],
        timeout=30,
    )
    return result.returncode == 0 and "Error" not in (result.stdout + result.stderr)


def adb_launch_package(package: str) -> bool:
    result = run_command(
        [
            *adb_prefix(),
            "shell",
            "monkey",
            "-p",
            package,
            "-c",
            "android.intent.category.LAUNCHER",
            "1",
        ],
        timeout=30,
    )
    if result.returncode == 0:
        return True

    fallback = run_command(
        [
            *adb_prefix(),
            "shell",
            "monkey",
            "-p",
            package,
            "1",
        ],
        timeout=30,
    )
    if fallback.returncode == 0:
        return True

    start_result = run_command(
        [
            *adb_prefix(),
            "shell",
            "cmd package resolve-activity --brief "
            f"{package} | tail -n 1 | xargs -r am start -n",
        ],
        timeout=30,
    )
    return start_result.returncode == 0 and "Error" not in (start_result.stdout + start_result.stderr)


def mark_task_accepted_success(task_id: str, started: float, message: str) -> None:
    duration_ms = int((time.time() - started) * 1000)
    update_task(task_id, status="success", return_code=0, duration_ms=duration_ms, error="")
    append_log(task_id, message)


def should_ack_mobile_app_early() -> bool:
    return os.getenv("AUTOGLM_ACK_MOBILE_APP_EARLY", "false").lower() in ("1", "true", "yes")


def fail_or_warn_task(task_id: str, error: str) -> None:
    with tasks_lock:
        record = tasks.get(task_id)
        already_success = bool(record and record.status == "success")
    if already_success and should_ack_mobile_app_early():
        append_log(task_id, f"Observe: 后台执行警告：{error}")
        return
    update_task(task_id, status="failed", error=error)


def mark_running_unless_already_success(task_id: str) -> None:
    with tasks_lock:
        record = tasks.get(task_id)
        already_success = bool(record and record.status == "success")
    if not already_success:
        update_task(task_id, status="running")


def adb_force_stop_package(package: str) -> bool:
    result = run_command([*adb_prefix(), "shell", "am", "force-stop", package], timeout=30)
    return result.returncode == 0


def adb_clear_text_field() -> None:
    adb_shell("am broadcast -a ADB_CLEAR_TEXT")
    time.sleep(0.3)


def adb_focused_ui_text() -> str:
    remote_path = "/data/local/tmp/autoglm_ui.xml"
    try:
        result = run_command([*adb_prefix(), "shell", "uiautomator", "dump", remote_path], timeout=20)
        if result.returncode != 0:
            return ""
        cat_result = run_command([*adb_prefix(), "shell", "cat", remote_path], timeout=20)
        run_command([*adb_prefix(), "shell", "rm", "-f", remote_path], timeout=5)
        return cat_result.stdout + cat_result.stderr
    except Exception:
        return ""


def adb_current_focus() -> str:
    try:
        result = adb_shell_result("dumpsys window | grep -E 'mCurrentFocus|mFocusedApp'", timeout=20)
        return result.stdout + result.stderr
    except Exception:
        return ""


def adb_current_focus_package() -> str:
    focus = adb_current_focus()
    patterns = [
        r"u0\s+([a-zA-Z0-9_.]+)/",
        r"Window\{[^}]+\s+([a-zA-Z0-9_.]+)/",
        r"ActivityRecord\{[^}]+\s+u0\s+([a-zA-Z0-9_.]+)/",
    ]
    for pattern in patterns:
        match = re.search(pattern, focus)
        if match:
            return match.group(1)
    return ""


def adb_is_meituan_foreground() -> bool:
    return "com.sankuai.meituan" in adb_current_focus()


def maybe_stop_control_app(task_id: str) -> None:
    package = adb_current_focus_package()
    if not package:
        append_log(task_id, "Observe: 未识别到当前控制端前台包名，改为按 Home 退到后台")
        adb_keyevent("KEYCODE_HOME")
        time.sleep(1)
        return
    protected_prefixes = (
        "com.sankuai.meituan",
        "com.android.",
        "android",
        "com.coloros.",
        "com.oplus.",
        "com.heytap.",
        "com.tailscale.",
    )
    if package.startswith(protected_prefixes):
        append_log(task_id, f"Observe: 当前前台包 {package} 不作为控制端清理")
        return
    append_log(task_id, f"Act: 任务已接收，将控制端 App 退到后台以防抢焦点：{package}")
    adb_keyevent("KEYCODE_HOME")
    time.sleep(1)


def ensure_meituan_foreground(task_id: str) -> bool:
    if adb_is_meituan_foreground():
        return True
    append_log(task_id, "Observe: 前台不是美团，重新拉起美团以避免输入到控制端 App")
    adb_launch_package("com.sankuai.meituan")
    time.sleep(3)
    if adb_is_meituan_foreground():
        return True
    append_log(task_id, "Observe: 远程 ADB 前台校验未稳定返回美团，继续尝试在当前输入框完成搜索，避免误判中断")
    return True


def adb_input_keyword_with_verify(keyword: str, task_id: str, retries: int = 2) -> bool:
    for attempt in range(1, retries + 1):
        if not ensure_meituan_foreground(task_id):
            append_log(task_id, f"Observe: 第 {attempt} 次输入前美团不在前台，停止输入")
            return False
        adb_clear_text_field()
        append_log(task_id, f"Act: 已清空搜索框旧内容（第 {attempt} 次）")
        if not adb_broadcast_b64_text(keyword):
            append_log(task_id, f"Observe: ADB Keyboard 广播输入失败（第 {attempt} 次）")
            time.sleep(0.8)
            continue
        time.sleep(1.2)
        if not adb_is_meituan_foreground():
            append_log(task_id, f"Observe: 输入后前台校验不是美团（第 {attempt} 次），可能是远程 ADB 误判；继续检查输入框内容")
        ui_text = adb_focused_ui_text()
        if keyword in ui_text:
            append_log(task_id, f"Result: 已确认美团搜索框包含关键词：{keyword}")
            return True
        append_log(task_id, f"Observe: 未在美团 UI 中确认关键词，准备重试输入：{keyword}")
        time.sleep(0.8)
    return False


def adb_screen_size() -> tuple[int, int]:
    try:
        result = adb_shell_result("wm size", timeout=20)
        match = re.search(r"Physical size:\s*(\d+)x(\d+)", result.stdout + result.stderr)
        if match:
            return int(match.group(1)), int(match.group(2))
    except Exception:
        pass
    return 1080, 2400


def adb_pick_meituan_search_box(task_id: str) -> tuple[int, int] | None:
    try:
        from phone_agent.adb.ui_tree import get_ui_elements
    except Exception as exc:
        append_log(task_id, f"Observe: 无法导入 UI 树模块：{exc}")
        return None

    try:
        ui_elements = get_ui_elements(PHONE_AGENT_DEVICE_ID or None, timeout=25, max_elements=80)
    except Exception as exc:
        append_log(task_id, f"Observe: 获取 UI 树失败：{exc}")
        return None

    candidates: list[tuple[int, tuple[int, int], str]] = []
    for element in ui_elements:
        bounds = element.get("bounds") or []
        center = element.get("center") or []
        if len(bounds) != 4 or len(center) != 2:
            continue

        x1, y1, x2, y2 = bounds
        width = x2 - x1
        if width < 260 or center[1] > 900:
            continue

        label = " ".join(
            str(element.get(key) or "")
            for key in ("text", "content_desc", "resource_id", "class")
        ).lower()

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
            candidates.append((score, (center[0], center[1]), label[:120]))

    if not candidates:
        append_log(task_id, "Observe: UI 树里没有找到可信的美团搜索框候选，将退回固定坐标")
        return None

    candidates.sort(key=lambda item: item[0], reverse=True)
    score, point, label = candidates[0]
    append_log(task_id, f"Observe: 选中 UI 树搜索框候选 score={score} point={point} label={label}")
    return point


def extract_meituan_keyword(task_text: str) -> str:
    text = task_text.strip()
    patterns = [
        r"搜索\s*([^，。,.\s]+)",
        r"搜\s*([^，。,.\s]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            keyword = match.group(1).strip()
            keyword = keyword.replace("并搜索", "").replace("然后搜索", "")
            if keyword and keyword not in {"美团", "一下"}:
                return keyword
    return "蜜雪冰城"


def should_use_meituan_fast_path(task_text: str) -> bool:
    return "美团" in task_text and ("搜索" in task_text or "搜" in task_text)


def should_use_open_app_fast_path(task_text: str) -> bool:
    text = task_text.strip()
    open_words = ("打开", "启动", "进入")
    search_words = ("搜索", "搜", "查找", "下单", "购买", "点", "点击", "输入")
    return "美团" in text and any(word in text for word in open_words) and not any(word in text for word in search_words)


def run_open_app_fast_path(task_id: str, task_text: str, prepare_home: bool) -> bool:
    started = time.time()
    mark_running_unless_already_success(task_id)
    append_log(task_id, "Think: 检测到打开美团任务，启用 ADB 快路径直接完成")

    if prepare_home and PREPARE_HOME_BEFORE_TASK:
        append_log(task_id, "Act: 唤醒屏幕并返回桌面")
        adb_shell("input keyevent KEYCODE_WAKEUP")
        time.sleep(0.4)
        adb_shell("input keyevent KEYCODE_MENU")
        time.sleep(0.2)
        adb_shell("input swipe 540 2100 540 900 350")
        time.sleep(0.5)
        adb_shell("input keyevent KEYCODE_HOME")
        time.sleep(0.8)
        if is_task_cancelled(task_id):
            return True

    append_log(task_id, "Act: 直接启动美团应用")
    if not adb_launch_package("com.sankuai.meituan"):
        fail_or_warn_task(task_id, "启动美团失败")
        append_log(task_id, "Failed: 启动美团失败")
        return True

    time.sleep(5)
    duration_ms = int((time.time() - started) * 1000)
    update_task(task_id, status="success", return_code=0, duration_ms=duration_ms)
    append_log(task_id, "Result: 美团已打开，任务完成")
    return True


def run_meituan_fast_path(task_id: str, task_text: str, prepare_home: bool) -> bool:
    started = time.time()
    keyword = extract_meituan_keyword(task_text)
    update_task(task_id, status="running")
    append_log(task_id, "Think: 检测到美团搜索任务，启用 ADB 快路径绕过敏感截图")

    if prepare_home and PREPARE_HOME_BEFORE_TASK:
        prepare_device_for_task(task_id, task_text)
        if is_task_cancelled(task_id):
            return True

    append_log(task_id, "Act: 直接启动美团应用")
    if not adb_launch_package("com.sankuai.meituan"):
        update_task(task_id, status="failed", error="启动美团失败")
        append_log(task_id, "Failed: 启动美团失败")
        return True

    time.sleep(6)
    if is_task_cancelled(task_id):
        return True

    candidate = adb_pick_meituan_search_box(task_id)
    if candidate is not None:
        search_x, search_y = candidate
        append_log(task_id, "Act: 根据 UI 树定位美团搜索框")
    else:
        width, height = adb_screen_size()
        search_x, search_y = width // 2, int(height * 0.075)
        append_log(task_id, "Act: 未拿到 UI 树候选，退回顶部搜索框固定坐标")
    adb_tap(search_x, search_y)
    time.sleep(1.2)

    append_log(task_id, "Act: 切换到 ADB Keyboard 并输入关键词")
    if not adb_set_adb_keyboard():
        update_task(task_id, status="failed", error="ADB Keyboard 未启用或切换失败")
        append_log(task_id, "Failed: ADB Keyboard 未启用或切换失败")
        return True

    if not adb_input_keyword_with_verify(keyword, task_id):
        update_task(task_id, status="failed", error=f"未能确认美团搜索框已输入关键词：{keyword}")
        append_log(task_id, f"Failed: 未能确认美团搜索框已输入关键词：{keyword}")
        return True

    time.sleep(0.8)
    append_log(task_id, f"Act: 输入关键词：{keyword}")

    adb_keyevent("KEYCODE_ENTER")
    time.sleep(2)
    adb_keyevent("KEYCODE_SEARCH")
    time.sleep(2)
    append_log(task_id, "Act: 发送搜索确认键")

    duration_ms = int((time.time() - started) * 1000)
    update_task(task_id, status="success", return_code=0, duration_ms=duration_ms)
    append_log(task_id, "Result: 美团搜索快路径执行完成")
    return True


def prepare_device_for_task(task_id: str, task_text: str = "") -> None:
    append_log(task_id, "Observe: 任务开始前准备设备环境")
    append_log(task_id, "Act: 唤醒屏幕、尝试上滑解锁并返回桌面")
    adb_shell("input keyevent KEYCODE_WAKEUP")
    time.sleep(0.4)
    adb_shell("input keyevent KEYCODE_MENU")
    time.sleep(0.2)
    # Generic unlock swipe (center-bottom -> center-top, 1080p-ish)
    adb_shell("input swipe 540 2100 540 900 350")
    time.sleep(0.5)
    adb_shell("input keyevent KEYCODE_HOME")
    time.sleep(0.8)
    if "美团" in task_text:
        append_log(task_id, "Act: 美团任务预启动——打开美团并等待首页加载")
        if adb_launch_package("com.sankuai.meituan"):
            time.sleep(4)
            try:
                from phone_agent.adb.device import ensure_meituan_home_tab

                ensure_meituan_home_tab()
                append_log(task_id, "Act: 已点击底部「推荐」回到美团首页（避免恢复闪购页）")
            except Exception as exc:
                append_log(task_id, f"Observe: 回美团首页失败，将由 Agent 处理：{exc}")
        else:
            append_log(task_id, "Observe: 预启动美团失败，将由 Agent 自行 Launch")
    append_log(task_id, "Result: 设备环境准备完成，开始 Agent 任务")


def parse_devices(raw: str) -> list[dict[str, str]]:
    device_rows = []
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("List of devices"):
            continue
        parts = line.split()
        if len(parts) >= 2:
            device_id = parts[0]
            status = parts[1]
            model = ""
            product = ""
            for part in parts[2:]:
                if part.startswith("model:"):
                    model = part.split(":", 1)[1]
                if part.startswith("product:"):
                    product = part.split(":", 1)[1]
            device_rows.append({
                "id": device_id,
                "serial": device_id,
                "status": status,
                "state": status,
                "model": model or product,
                "raw": line,
            })
    return device_rows


def get_skill_apps() -> list[str]:
    try:
        from phone_agent.config.apps import list_supported_apps
        apps = list_supported_apps()
        priority = ["美团", "小红书", "淘宝", "京东", "抖音", "Settings", "Chrome", "微信", "知乎", "高德地图"]
        ordered = [name for name in priority if name in apps]
        rest = sorted(name for name in apps if name not in ordered)
        return ordered + rest[:40]
    except Exception:
        return ["美团", "小红书", "淘宝", "Settings", "Chrome", "微信"]


def run_mock_task(task_id: str, task_text: str, prepare_home: bool) -> None:
    init_task_runtime(task_id)
    started = time.time()
    try:
        update_task(task_id, status="running")
        if is_task_cancelled(task_id):
            return
        append_log(task_id, "Mock Agent started")
        if prepare_home:
            append_log(task_id, "Observe: 模拟返回桌面")
            append_log(task_id, "Act: Home")
        mock_steps = [
            ("observe", "Observe: 获取当前手机屏幕状态"),
            ("think", f"Think: 分析用户任务：{task_text}"),
            ("act", "Act: 规划 Launch / Tap / Type / Swipe 动作"),
            ("act", "Act: 模拟执行 Open-AutoGLM PhoneAgent 循环"),
            ("result", "Result: 任务执行完成（mock 模式）"),
        ]
        cancel_event = get_cancel_event(task_id)
        for _, step in mock_steps:
            if cancel_event and cancel_event.wait(0.8):
                finish_cancelled_task(task_id, started)
                return
            if is_task_cancelled(task_id):
                return
            append_log(task_id, step)
        if is_task_cancelled(task_id):
            return
        duration_ms = int((time.time() - started) * 1000)
        update_task(task_id, status="success", return_code=0, duration_ms=duration_ms)
        append_log(task_id, "Mock task finished successfully")
    finally:
        cleanup_task_runtime(task_id)


def run_real_task(task_id: str, task_text: str, prepare_home: bool) -> None:
    init_task_runtime(task_id)
    started = time.time()
    process: subprocess.Popen[str] | None = None
    try:
        update_task(task_id, status="running")
        if is_task_cancelled(task_id):
            return
        append_log(task_id, "Real Agent started")

        if not BIGMODEL_API_KEY:
            update_task(task_id, status="failed", error="BIGMODEL_API_KEY is not configured")
            append_log(task_id, "Failed: BIGMODEL_API_KEY is not configured")
            return

        if not PYTHON_PATH.exists():
            update_task(task_id, status="failed", error=f"Python not found: {PYTHON_PATH}")
            append_log(task_id, f"Failed: Python not found: {PYTHON_PATH}")
            return

        if not AUTOGLM_DIR.exists():
            update_task(task_id, status="failed", error=f"Open-AutoGLM dir not found: {AUTOGLM_DIR}")
            append_log(task_id, f"Failed: Open-AutoGLM dir not found: {AUTOGLM_DIR}")
            return

        if is_task_cancelled(task_id):
            return

        if not ensure_remote_adb(task_id):
            return

        if should_use_meituan_fast_path(task_text):
            run_meituan_fast_path(task_id, task_text, prepare_home)
            return

        if should_use_open_app_fast_path(task_text):
            run_open_app_fast_path(task_id, task_text, prepare_home)
            return

        if prepare_home and PREPARE_HOME_BEFORE_TASK:
            prepare_device_for_task(task_id, task_text)
            if is_task_cancelled(task_id):
                return

        command = [
            str(PYTHON_PATH),
            "main.py",
            "--base-url",
            AUTOGLM_BASE_URL,
            "--model",
            AUTOGLM_MODEL,
            "--apikey",
            BIGMODEL_API_KEY,
        ]
        if PHONE_AGENT_DEVICE_ID:
            command.extend(["--device-id", PHONE_AGENT_DEVICE_ID])
        command.append(task_text)
        append_log(task_id, f"Think: 调用 Open-AutoGLM，任务：{task_text}")
        append_log(task_id, "Act: 启动 PhoneAgent 截图-决策-执行循环")

        try:
            process = subprocess.Popen(
                command,
                cwd=str(AUTOGLM_DIR),
                env=build_env(task_id),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            set_task_process(task_id, process)
            append_log(
                task_id,
                f"Screenshot debug enabled; dumps -> {WORK_ROOT / 'screenshot_debug' / task_id}",
            )
        except Exception as exc:
            update_task(task_id, status="failed", error=str(exc))
            append_log(task_id, f"Failed: {exc}")
            return

        loop_start = time.time()
        recent_output: list[str] = []
        assert process.stdout is not None
        for line in process.stdout:
            if is_task_cancelled(task_id):
                if process.poll() is None:
                    try:
                        process.kill()
                    except Exception:
                        pass
                finish_cancelled_task(task_id, started)
                return
            if time.time() - loop_start > DEFAULT_TASK_TIMEOUT:
                process.kill()
                update_task(task_id, status="failed", error="Task timed out")
                append_log(task_id, f"Failed: task timed out after {DEFAULT_TASK_TIMEOUT}s")
                return
            if line.strip():
                clean_line = line.strip()
                recent_output.append(clean_line)
                recent_output = recent_output[-12:]
                append_log(task_id, clean_line)

        if is_task_cancelled(task_id):
            return

        return_code = process.wait()
        duration_ms = int((time.time() - started) * 1000)
        if return_code == 0:
            update_task(task_id, status="success", return_code=return_code, duration_ms=duration_ms)
            append_log(task_id, "Result: Real task finished successfully")
        else:
            detail = "\n".join(recent_output[-8:]) or f"Open-AutoGLM exited with code {return_code}"
            update_task(
                task_id,
                status="failed",
                return_code=return_code,
                duration_ms=duration_ms,
                error=detail,
            )
            append_log(task_id, f"Failed: Open-AutoGLM exited with code {return_code}")
    finally:
        cleanup_task_runtime(task_id)


def start_task_runner(task_id: str, prepare_home: bool) -> None:
    with tasks_lock:
        record = tasks[task_id]
        mode = record.mode
        task_text = record.task

    target = run_mock_task if mode == "mock" else run_real_task
    thread = threading.Thread(
        target=target,
        args=(task_id, task_text, prepare_home),
        daemon=True,
    )
    thread.start()


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "autoglm-mobile-copilot-server",
        "version": "0.4.1",
        "time": now_text(),
        "work_root": str(WORK_ROOT),
        "adb_exists": ADB_PATH.exists(),
        "autoglm_dir_exists": AUTOGLM_DIR.exists(),
        "python_exists": PYTHON_PATH.exists(),
        "api_key_configured": bool(BIGMODEL_API_KEY),
        "prepare_home_before_task": PREPARE_HOME_BEFORE_TASK,
    }


@app.get("/devices")
def devices():
    if not ADB_PATH.exists():
        return {
            "success": False,
            "devices": [],
            "error": f"ADB not found: {ADB_PATH}",
        }

    try:
        result = run_command([str(ADB_PATH), "devices", "-l"])
    except Exception as exc:
        return {"success": False, "devices": [], "error": str(exc)}

    return {
        "success": result.returncode == 0,
        "devices": parse_devices(result.stdout),
        "raw": result.stdout,
        "error": result.stderr,
    }


def _screenshot_debug_root() -> Path:
    raw = os.getenv("PHONE_AGENT_SCREENSHOT_DUMP_DIR", "").strip()
    if raw:
        return Path(raw)
    return WORK_ROOT / "screenshot_debug"


def _safe_screenshot_name(filename: str) -> str:
    if not re.fullmatch(r"[\w.\-]+", filename):
        raise HTTPException(status_code=400, detail="Invalid filename")
    return filename


@app.get("/debug/screenshots")
def list_screenshot_tasks():
    root = _screenshot_debug_root()
    if not root.exists():
        return {"root": str(root), "tasks": []}

    task_rows = []
    for task_dir in sorted(root.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        if not task_dir.is_dir():
            continue
        files = sorted(path.name for path in task_dir.iterdir() if path.is_file())
        task_rows.append(
            {
                "task_id": task_dir.name,
                "folder": str(task_dir),
                "file_count": len(files),
                "files": files,
            }
        )
    return {"root": str(root), "tasks": task_rows}


@app.get("/debug/screenshots/{task_id}")
def get_screenshot_task(task_id: str):
    if not re.fullmatch(r"[\w\-]+", task_id):
        raise HTTPException(status_code=400, detail="Invalid task id")

    task_dir = _screenshot_debug_root() / task_id
    if not task_dir.exists() or not task_dir.is_dir():
        raise HTTPException(status_code=404, detail=f"No screenshots for task: {task_id}")

    files = []
    for path in sorted(task_dir.iterdir()):
        if not path.is_file():
            continue
        meta = {}
        if path.name.endswith("_meta.json"):
            try:
                meta = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                meta = {}
        files.append(
            {
                "name": path.name,
                "size_bytes": path.stat().st_size,
                "url": f"/debug/screenshots/{task_id}/{path.name}",
                "meta": meta,
            }
        )
    return {
        "task_id": task_id,
        "folder": str(task_dir),
        "files": files,
    }


@app.get("/debug/screenshots/{task_id}/{filename}")
def download_screenshot_file(task_id: str, filename: str):
    if not re.fullmatch(r"[\w\-]+", task_id):
        raise HTTPException(status_code=400, detail="Invalid task id")
    filename = _safe_screenshot_name(filename)

    file_path = _screenshot_debug_root() / task_id / filename
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="Screenshot file not found")

    media = "application/json" if filename.endswith(".json") else None
    if filename.endswith(".png"):
        media = "image/png"
    elif filename.endswith(".jpg") or filename.endswith(".jpeg"):
        media = "image/jpeg"
    return FileResponse(file_path, media_type=media, filename=filename)


@app.get("/skills")
def skills():
    apps = get_skill_apps()
    templates = [
        {"name": "查看 WLAN", "task": "打开设置查看WLAN", "category": "system"},
        {"name": "美团搜索", "task": "点击搜索框，搜索蜜雪冰城", "category": "life"},
        {"name": "浏览器搜索", "task": "打开浏览器搜索 Open-AutoGLM", "category": "search"},
        {"name": "小红书搜索", "task": "打开小红书搜索英语学习", "category": "social"},
        {"name": "淘宝搜索", "task": "打开淘宝搜索无线耳机", "category": "shopping"},
    ]
    return {
        "templates": templates,
        "supported_apps": apps,
        "total_apps": len(apps),
    }


@app.post("/tasks")
def create_task(request: TaskCreateRequest):
    task_id = uuid.uuid4().hex[:12]
    record = TaskRecord(
        task_id=task_id,
        task=request.task.strip(),
        mode=request.mode,
        status="pending",
        created_at=now_text(),
        updated_at=now_text(),
        logs=[f"[{datetime.now().strftime('%H:%M:%S')}] Task created"],
    )
    with tasks_lock:
        tasks[task_id] = record
    cancel_other_running_tasks(task_id)
    kill_orphan_agent_processes()
    append_log(task_id, "Observe: 已清理可能残留的旧 Agent 进程")
    start_task_runner(task_id, request.prepare_home)
    refresh_trace(task_id)
    return record


@app.post("/tasks/{task_id}/cancel")
def cancel_task_endpoint(task_id: str):
    with tasks_lock:
        record = tasks.get(task_id)
        if not record:
            raise HTTPException(status_code=404, detail="Task not found")
        if record.status not in {"pending", "running"}:
            raise HTTPException(status_code=409, detail=f"Task is not cancellable: {record.status}")

    if not cancel_task(task_id):
        with tasks_lock:
            record = tasks.get(task_id)
            if not record:
                raise HTTPException(status_code=404, detail="Task not found")
            return record
        raise HTTPException(status_code=409, detail="Task could not be cancelled")

    with tasks_lock:
        record = tasks.get(task_id)
        if not record:
            raise HTTPException(status_code=404, detail="Task not found")
        return record


@app.get("/tasks")
def list_tasks():
    with tasks_lock:
        return sorted(tasks.values(), key=lambda item: item.updated_at, reverse=True)


@app.get("/tasks/{task_id}")
def get_task(task_id: str):
    with tasks_lock:
        record = tasks.get(task_id)
        if not record:
            raise HTTPException(status_code=404, detail="Task not found")
        return record


@app.get("/tasks/{task_id}/logs")
def get_task_logs(task_id: str):
    with tasks_lock:
        record = tasks.get(task_id)
        if not record:
            raise HTTPException(status_code=404, detail="Task not found")
        return {
            "task_id": task_id,
            "status": record.status,
            "logs": record.logs,
        }


@app.get("/tasks/{task_id}/trace")
def get_task_trace(task_id: str):
    with tasks_lock:
        record = tasks.get(task_id)
        if not record:
            raise HTTPException(status_code=404, detail="Task not found")
        full_trace = [step.model_dump() for step in record.trace]
        structured = [step.model_dump() for step in record.steps]
        return {
            "task_id": task_id,
            "status": record.status,
            "duration_ms": record.duration_ms,
            "trace": full_trace,
            "steps": structured,
            "highlight": structured or pick_highlight_trace(full_trace),
        }
