"""Screenshot utilities for capturing Android device screen."""

import base64
import json
import os
import subprocess
import tempfile
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from io import BytesIO
from pathlib import Path

from PIL import Image

# Remote ADB (Tailscale / wireless) needs more time than local USB.
DEFAULT_SCREENSHOT_TIMEOUT = 90
PULL_TIMEOUT = 20
DEFAULT_MAX_LONG_EDGE = 720

_debug_context: dict[str, str | int] = {"step": 0, "tag": "observe", "attempt": 1}


@dataclass
class Screenshot:
    """Represents a captured screenshot."""

    base64_data: str
    width: int
    height: int
    is_sensitive: bool = False
    capture_method: str = "unknown"
    failure_reason: str | None = None
    is_fallback: bool = False
    mean_luminance: float | None = None
    is_mostly_black: bool = False
    debug_saved_path: str | None = None
    debug_meta: dict[str, object] = field(default_factory=dict)


def _screenshot_timeout() -> int:
    return int(os.getenv("PHONE_AGENT_SCREENSHOT_TIMEOUT", DEFAULT_SCREENSHOT_TIMEOUT))


def _max_long_edge() -> int | None:
    raw = os.getenv("PHONE_AGENT_SCREENSHOT_MAX_LONG_EDGE", str(DEFAULT_MAX_LONG_EDGE)).strip()
    if not raw or raw.lower() in ("0", "none", "off", "false"):
        return None
    return max(320, int(raw))


def _screenshot_debug_enabled() -> bool:
    return os.getenv("PHONE_AGENT_SCREENSHOT_DEBUG", "").lower() in (
        "1",
        "true",
        "yes",
    ) or os.getenv("PHONE_AGENT_SAVE_SCREENSHOTS", "").lower() in ("1", "true", "yes")


def _screenshot_dump_dir() -> Path:
    raw = os.getenv("PHONE_AGENT_SCREENSHOT_DUMP_DIR", "").strip()
    if raw:
        return Path(raw)
    work_root = os.getenv("AUTOGLM_WORK_ROOT", "").strip()
    if work_root:
        return Path(work_root) / "screenshot_debug"
    return Path.cwd() / "screenshot_debug"


def set_screenshot_context(
    *,
    step: int,
    tag: str = "observe",
    task_id: str | None = None,
    attempt: int = 1,
) -> None:
    """Tag the next screenshot capture for debug dumps (step / retry / task)."""
    _debug_context["step"] = step
    _debug_context["tag"] = tag
    _debug_context["attempt"] = attempt
    if task_id:
        _debug_context["task_id"] = task_id


def _analyze_image(img: Image.Image) -> tuple[float, bool]:
    rgb = img.convert("RGB")
    pixels = list(rgb.getdata())
    if not pixels:
        return 0.0, True
    luminance_sum = sum((0.299 * r + 0.587 * g + 0.114 * b) for r, g, b in pixels)
    mean_luminance = luminance_sum / len(pixels)
    dark_pixels = sum(1 for r, g, b in pixels if r < 12 and g < 12 and b < 12)
    is_mostly_black = dark_pixels / len(pixels) >= 0.95
    return mean_luminance, is_mostly_black


def _dump_screenshot_debug(
    screenshot: "Screenshot",
    *,
    raw_img: Image.Image | None = None,
    model_img: Image.Image | None = None,
) -> None:
    if not _screenshot_debug_enabled():
        return

    step = int(_debug_context.get("step", 0) or 0)
    tag = str(_debug_context.get("tag", "observe"))
    attempt = int(_debug_context.get("attempt", 1) or 1)
    task_id = str(_debug_context.get("task_id") or os.getenv("PHONE_AGENT_SCREENSHOT_TASK_ID", "session"))

    dump_root = _screenshot_dump_dir() / task_id
    dump_root.mkdir(parents=True, exist_ok=True)

    filename = f"step{step:03d}_{tag}"
    if attempt > 1:
        filename += f"_try{attempt}"

    saved_paths: list[str] = []
    if raw_img is not None:
        raw_path = dump_root / f"{filename}_raw.png"
        raw_img.save(raw_path, format="PNG")
        saved_paths.append(str(raw_path))

    if model_img is not None:
        model_path = dump_root / f"{filename}_model.jpg"
        model_img.save(model_path, format="JPEG", quality=82)
        saved_paths.append(str(model_path))
    elif screenshot.is_fallback:
        fallback_path = dump_root / f"{filename}_fallback_black.png"
        Image.new("RGB", (screenshot.width, screenshot.height), color="black").save(
            fallback_path, format="PNG"
        )
        saved_paths.append(str(fallback_path))

    meta = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "step": step,
        "tag": tag,
        "attempt": attempt,
        "task_id": task_id,
        "capture_method": screenshot.capture_method,
        "failure_reason": screenshot.failure_reason,
        "is_fallback": screenshot.is_fallback,
        "is_sensitive": screenshot.is_sensitive,
        "width": screenshot.width,
        "height": screenshot.height,
        "mean_luminance": screenshot.mean_luminance,
        "is_mostly_black": screenshot.is_mostly_black,
        "saved_paths": saved_paths,
        "diagnosis": _build_diagnosis(screenshot),
    }
    meta_path = dump_root / f"{filename}_meta.json"
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    saved_paths.append(str(meta_path))

    screenshot.debug_saved_path = saved_paths[0] if saved_paths else None
    screenshot.debug_meta = meta
    print(_format_debug_line(screenshot, saved_paths))


def _build_diagnosis(screenshot: "Screenshot") -> str:
    if screenshot.failure_reason and "Status: -1" in screenshot.failure_reason:
        return "adb_screencap_blocked_sensitive_or_secure_screen"
    if screenshot.is_fallback and screenshot.is_sensitive:
        return "fallback_black_marked_sensitive"
    if screenshot.is_fallback and not screenshot.failure_reason:
        return "fallback_black_capture_failed"
    if screenshot.is_mostly_black and not screenshot.is_fallback:
        return "real_capture_but_mostly_black_image"
    if screenshot.capture_method in {"exec_out", "pull"} and not screenshot.is_fallback:
        return "capture_ok"
    return "unknown"


def _format_debug_line(screenshot: "Screenshot", saved_paths: list[str]) -> str:
    path_hint = saved_paths[0] if saved_paths else "-"
    return (
        "[ScreenshotDebug] "
        f"step={_debug_context.get('step')} "
        f"tag={_debug_context.get('tag')} "
        f"method={screenshot.capture_method} "
        f"sensitive={screenshot.is_sensitive} "
        f"fallback={screenshot.is_fallback} "
        f"black={screenshot.is_mostly_black} "
        f"reason={screenshot.failure_reason or '-'} "
        f"size={screenshot.width}x{screenshot.height} "
        f"luma={screenshot.mean_luminance if screenshot.mean_luminance is not None else '-'} "
        f"diagnosis={_build_diagnosis(screenshot)} "
        f"path={path_hint}"
    )


def log_screenshot_decision(
    screenshot: "Screenshot",
    *,
    current_app: str,
    ui_elements_count: int,
    effective_sensitive: bool,
    image_sent_to_model: bool,
) -> None:
    if not _screenshot_debug_enabled():
        return
    print(
        "[ScreenshotDebug] "
        f"step={_debug_context.get('step')} "
        f"app={current_app} "
        f"ui_elements={ui_elements_count} "
        f"raw_sensitive={screenshot.is_sensitive} "
        f"effective_sensitive={effective_sensitive} "
        f"image_sent_to_model={image_sent_to_model}"
    )


def get_screenshot(
    device_id: str | None = None, timeout: int | None = None
) -> Screenshot:
    """
    Capture a screenshot from the connected Android device.

    Args:
        device_id: Optional ADB device ID for multi-device setups.
        timeout: Timeout in seconds for screenshot operations.

    Returns:
        Screenshot object containing base64 data and dimensions.

    Note:
        If the screenshot fails (e.g., on sensitive screens like payment pages),
        a black fallback image is returned with is_sensitive=True.
    """
    adb_prefix = _get_adb_prefix(device_id)
    capture_timeout = timeout if timeout is not None else _screenshot_timeout()

    try:
        if os.getenv("PHONE_AGENT_SCREENSHOT_EXEC_OUT", "false").lower() in ("1", "true", "yes"):
            screenshot = _capture_via_exec_out(adb_prefix, capture_timeout)
            if screenshot is not None:
                return screenshot

        screenshot = _capture_via_pull(adb_prefix, capture_timeout)
        if screenshot is not None:
            return screenshot

        return _create_fallback_screenshot(
            is_sensitive=False,
            capture_method="fallback",
            failure_reason="exec_out_and_pull_both_failed",
        )

    except Exception as e:
        print(f"Screenshot error: {e}")
        return _create_fallback_screenshot(
            is_sensitive=False,
            capture_method="fallback",
            failure_reason=f"exception:{e}",
        )


def _capture_via_exec_out(adb_prefix: list[str], timeout: int) -> Screenshot | None:
    """Single round-trip capture; much faster over remote ADB than shell+pull."""
    result = subprocess.run(
        adb_prefix + ["exec-out", "screencap", "-p"],
        capture_output=True,
        timeout=timeout,
    )

    stderr = result.stderr.decode("utf-8", errors="replace")
    if "Status: -1" in stderr or "Failed" in stderr:
        return _create_fallback_screenshot(
            is_sensitive=True,
            capture_method="exec_out",
            failure_reason=stderr.strip() or "Status: -1",
        )

    data = result.stdout
    if result.returncode != 0 or not data or len(data) < 100:
        return None

    if not data.startswith(b"\x89PNG"):
        return None

    img = Image.open(BytesIO(data))
    return _encode_screenshot(img, capture_method="exec_out", raw_img=img)


def _capture_via_pull(adb_prefix: list[str], timeout: int) -> Screenshot | None:
    """Legacy screencap-to-sdcard + pull fallback."""
    temp_path = os.path.join(tempfile.gettempdir(), f"screenshot_{uuid.uuid4()}.png")

    try:
        remote_path = f"/data/local/tmp/autoglm_{uuid.uuid4().hex}.png"
        result = subprocess.run(
            adb_prefix + ["shell", "screencap", "-p", remote_path],
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        output = result.stdout + result.stderr
        if "Status: -1" in output or "Failed" in output:
            return _create_fallback_screenshot(
                is_sensitive=True,
                capture_method="pull",
                failure_reason=output.strip() or "Status: -1",
            )

        pull_result = subprocess.run(
            adb_prefix + ["pull", remote_path, temp_path],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        subprocess.run(
            adb_prefix + ["shell", "rm", "-f", remote_path],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if pull_result.returncode != 0:
            return None

        img = Image.open(temp_path)
        return _encode_screenshot(img, capture_method="pull", raw_img=img)
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def _encode_screenshot(
    img: Image.Image,
    *,
    capture_method: str,
    raw_img: Image.Image | None = None,
) -> Screenshot:
    orig_w, orig_h = img.size
    model_img = _resize_for_model(img)
    buffered = BytesIO()
    model_img.save(buffered, format="JPEG", quality=82, optimize=True)
    base64_data = base64.b64encode(buffered.getvalue()).decode("utf-8")
    mean_luminance, is_mostly_black = _analyze_image(model_img)
    screenshot = Screenshot(
        base64_data=base64_data,
        width=orig_w,
        height=orig_h,
        is_sensitive=False,
        capture_method=capture_method,
        mean_luminance=round(mean_luminance, 2),
        is_mostly_black=is_mostly_black,
    )
    _dump_screenshot_debug(screenshot, raw_img=raw_img or img, model_img=model_img)
    return screenshot


def _resize_for_model(img: Image.Image) -> Image.Image:
    max_edge = _max_long_edge()
    if not max_edge:
        return img.convert("RGB")

    orig_w, orig_h = img.size
    long_edge = max(orig_w, orig_h)
    if long_edge <= max_edge:
        return img.convert("RGB")

    scale = max_edge / long_edge
    new_w = max(1, int(orig_w * scale))
    new_h = max(1, int(orig_h * scale))
    return img.resize((new_w, new_h), Image.Resampling.LANCZOS).convert("RGB")


def _get_adb_prefix(device_id: str | None) -> list:
    """Get ADB command prefix with optional device specifier."""
    if device_id:
        return ["adb", "-s", device_id]
    return ["adb"]


def _create_fallback_screenshot(
    is_sensitive: bool,
    *,
    capture_method: str = "fallback",
    failure_reason: str | None = None,
) -> Screenshot:
    """Create a black fallback image when screenshot fails."""
    default_width, default_height = 1080, 2400

    black_img = Image.new("RGB", (default_width, default_height), color="black")
    buffered = BytesIO()
    black_img.save(buffered, format="PNG")
    base64_data = base64.b64encode(buffered.getvalue()).decode("utf-8")

    screenshot = Screenshot(
        base64_data=base64_data,
        width=default_width,
        height=default_height,
        is_sensitive=is_sensitive,
        capture_method=capture_method,
        failure_reason=failure_reason,
        is_fallback=True,
        mean_luminance=0.0,
        is_mostly_black=True,
    )
    _dump_screenshot_debug(screenshot)
    return screenshot
