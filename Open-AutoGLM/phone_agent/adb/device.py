"""Device control utilities for Android automation."""

import os
import re
import subprocess
import time

from phone_agent.config.apps import APP_PACKAGES, resolve_app_name
from phone_agent.config.timing import TIMING_CONFIG


def _adb_cmd_timeout() -> int:
    return int(os.getenv("PHONE_AGENT_ADB_CMD_TIMEOUT", "45"))


def _run_adb(adb_prefix: list[str], args: list[str], timeout: int | None = None, **kwargs):
    return subprocess.run(
        adb_prefix + args,
        timeout=timeout or _adb_cmd_timeout(),
        **kwargs,
    )


def get_current_app(device_id: str | None = None) -> str:
    """
    Get the currently focused app name.

    Args:
        device_id: Optional ADB device ID for multi-device setups.

    Returns:
        The app name if recognized, otherwise "System Home".
    """
    adb_prefix = _get_adb_prefix(device_id)

    result = _run_adb(
        adb_prefix,
        ["shell", "dumpsys", "window"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    output = result.stdout
    if not output:
        return "System Home"

    for line in output.split("\n"):
        if "mCurrentFocus" in line or "mFocusedApp" in line:
            for app_name, package in APP_PACKAGES.items():
                if package in line:
                    return app_name

    return "System Home"


def tap(
    x: int, y: int, device_id: str | None = None, delay: float | None = None
) -> None:
    """
    Tap at the specified coordinates.

    Args:
        x: X coordinate.
        y: Y coordinate.
        device_id: Optional ADB device ID.
        delay: Delay in seconds after tap. If None, uses configured default.
    """
    if delay is None:
        delay = TIMING_CONFIG.device.default_tap_delay

    adb_prefix = _get_adb_prefix(device_id)

    _run_adb(
        adb_prefix,
        ["shell", "input", "tap", str(x), str(y)],
        capture_output=True,
    )
    time.sleep(delay)


def double_tap(
    x: int, y: int, device_id: str | None = None, delay: float | None = None
) -> None:
    """
    Double tap at the specified coordinates.

    Args:
        x: X coordinate.
        y: Y coordinate.
        device_id: Optional ADB device ID.
        delay: Delay in seconds after double tap. If None, uses configured default.
    """
    if delay is None:
        delay = TIMING_CONFIG.device.default_double_tap_delay

    adb_prefix = _get_adb_prefix(device_id)

    _run_adb(
        adb_prefix,
        ["shell", "input", "tap", str(x), str(y)],
        capture_output=True,
    )
    time.sleep(TIMING_CONFIG.device.double_tap_interval)
    _run_adb(
        adb_prefix,
        ["shell", "input", "tap", str(x), str(y)],
        capture_output=True,
    )
    time.sleep(delay)


def long_press(
    x: int,
    y: int,
    duration_ms: int = 3000,
    device_id: str | None = None,
    delay: float | None = None,
) -> None:
    """
    Long press at the specified coordinates.

    Args:
        x: X coordinate.
        y: Y coordinate.
        duration_ms: Duration of press in milliseconds.
        device_id: Optional ADB device ID.
        delay: Delay in seconds after long press. If None, uses configured default.
    """
    if delay is None:
        delay = TIMING_CONFIG.device.default_long_press_delay

    adb_prefix = _get_adb_prefix(device_id)

    _run_adb(
        adb_prefix,
        ["shell", "input", "swipe", str(x), str(y), str(x), str(y), str(duration_ms)],
        capture_output=True,
    )
    time.sleep(delay)


def swipe(
    start_x: int,
    start_y: int,
    end_x: int,
    end_y: int,
    duration_ms: int | None = None,
    device_id: str | None = None,
    delay: float | None = None,
) -> None:
    """
    Swipe from start to end coordinates.

    Args:
        start_x: Starting X coordinate.
        start_y: Starting Y coordinate.
        end_x: Ending X coordinate.
        end_y: Ending Y coordinate.
        duration_ms: Duration of swipe in milliseconds (auto-calculated if None).
        device_id: Optional ADB device ID.
        delay: Delay in seconds after swipe. If None, uses configured default.
    """
    if delay is None:
        delay = TIMING_CONFIG.device.default_swipe_delay

    adb_prefix = _get_adb_prefix(device_id)

    if duration_ms is None:
        dist_sq = (start_x - end_x) ** 2 + (start_y - end_y) ** 2
        duration_ms = int(dist_sq / 1000)
        duration_ms = max(1000, min(duration_ms, 2000))

    _run_adb(
        adb_prefix,
        [
            "shell",
            "input",
            "swipe",
            str(start_x),
            str(start_y),
            str(end_x),
            str(end_y),
            str(duration_ms),
        ],
        capture_output=True,
    )
    time.sleep(delay)


def back(device_id: str | None = None, delay: float | None = None) -> None:
    """
    Press the back button.

    Args:
        device_id: Optional ADB device ID.
        delay: Delay in seconds after pressing back. If None, uses configured default.
    """
    if delay is None:
        delay = TIMING_CONFIG.device.default_back_delay

    adb_prefix = _get_adb_prefix(device_id)

    _run_adb(
        adb_prefix,
        ["shell", "input", "keyevent", "4"],
        capture_output=True,
    )
    time.sleep(delay)


def home(device_id: str | None = None, delay: float | None = None) -> None:
    """
    Press the home button.

    Args:
        device_id: Optional ADB device ID.
        delay: Delay in seconds after pressing home. If None, uses configured default.
    """
    if delay is None:
        delay = TIMING_CONFIG.device.default_home_delay

    adb_prefix = _get_adb_prefix(device_id)

    _run_adb(
        adb_prefix,
        ["shell", "input", "keyevent", "KEYCODE_HOME"],
        capture_output=True,
    )
    time.sleep(delay)


def launch_app(
    app_name: str, device_id: str | None = None, delay: float | None = None
) -> bool:
    """
    Launch an app by name.

    Args:
        app_name: The app name (must be in APP_PACKAGES).
        device_id: Optional ADB device ID.
        delay: Delay in seconds after launching. If None, uses configured default.

    Returns:
        True if app was launched, False if app not found.
    """
    if delay is None:
        delay = TIMING_CONFIG.device.default_launch_delay

    canonical = resolve_app_name(app_name)
    if canonical is None:
        return False

    adb_prefix = _get_adb_prefix(device_id)
    package = APP_PACKAGES[canonical]

    _run_adb(
        adb_prefix,
        [
            "shell",
            "monkey",
            "-p",
            package,
            "-c",
            "android.intent.category.LAUNCHER",
            "1",
        ],
        capture_output=True,
    )
    time.sleep(delay)
    if package == "com.sankuai.meituan":
        ensure_meituan_home_tab(device_id)
    return True


def ensure_meituan_home_tab(device_id: str | None = None) -> None:
    """
    Meituan often resumes the last sub-tab (e.g. 闪购) after monkey Launch.
    Tap the bottom-left 推荐 tab to return to the main home feed.
    """
    width, height = _screen_size(device_id)
    home_x = int(width * 0.10)
    home_y = int(height * 0.965)
    tap(home_x, home_y, device_id, delay=1.2)
    time.sleep(0.8)
    tap(home_x, home_y, device_id, delay=1.0)


def _screen_size(device_id: str | None = None) -> tuple[int, int]:
    adb_prefix = _get_adb_prefix(device_id)
    try:
        result = _run_adb(
            adb_prefix,
            ["shell", "wm", "size"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        match = re.search(r"Physical size:\s*(\d+)x(\d+)", result.stdout + result.stderr)
        if match:
            return int(match.group(1)), int(match.group(2))
    except Exception:
        pass
    return 1080, 2412


def _get_adb_prefix(device_id: str | None) -> list:
    """Get ADB command prefix with optional device specifier."""
    if device_id:
        return ["adb", "-s", device_id]
    return ["adb"]
