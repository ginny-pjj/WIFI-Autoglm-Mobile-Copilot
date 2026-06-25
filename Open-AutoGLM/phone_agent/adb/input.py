"""Input utilities for Android device text input."""

import base64
import os
import subprocess

ADB_KEYBOARD_IME = "com.android.adbkeyboard/.AdbIME"


def _adb_cmd_timeout() -> int:
    return int(os.getenv("PHONE_AGENT_ADB_CMD_TIMEOUT", "45"))


def _keep_adb_keyboard() -> bool:
    return os.getenv("PHONE_AGENT_KEEP_ADB_KEYBOARD", "true").lower() in (
        "1",
        "true",
        "yes",
    )


def _run_adb(adb_prefix: list[str], args: list[str], timeout: int | None = None, **kwargs):
    return subprocess.run(
        adb_prefix + args,
        timeout=timeout or _adb_cmd_timeout(),
        **kwargs,
    )


def type_text(text: str, device_id: str | None = None) -> None:
    """
    Type text into the currently focused input field using ADB Keyboard.

    Args:
        text: The text to type.
        device_id: Optional ADB device ID for multi-device setups.

    Note:
        Requires ADB Keyboard to be installed on the device.
        See: https://github.com/nicnocquee/AdbKeyboard
    """
    adb_prefix = _get_adb_prefix(device_id)
    encoded_text = base64.b64encode(text.encode("utf-8")).decode("utf-8")

    result = _run_adb(
        adb_prefix,
        [
            "shell",
            "am",
            "broadcast",
            "-a",
            "ADB_INPUT_B64",
            "--es",
            "msg",
            encoded_text,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout or "ADB Keyboard input failed").strip())


def clear_text(device_id: str | None = None) -> None:
    """
    Clear text in the currently focused input field.

    Args:
        device_id: Optional ADB device ID for multi-device setups.
    """
    adb_prefix = _get_adb_prefix(device_id)

    _run_adb(
        adb_prefix,
        ["shell", "am", "broadcast", "-a", "ADB_CLEAR_TEXT"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def detect_and_set_adb_keyboard(device_id: str | None = None) -> str:
    """
    Detect current keyboard and switch to ADB Keyboard if needed.

    Args:
        device_id: Optional ADB device ID for multi-device setups.

    Returns:
        The original keyboard IME identifier for later restoration.
    """
    adb_prefix = _get_adb_prefix(device_id)

    result = _run_adb(
        adb_prefix,
        ["shell", "settings", "get", "secure", "default_input_method"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    current_ime = (result.stdout + result.stderr).strip()

    if ADB_KEYBOARD_IME not in current_ime:
        set_result = _run_adb(
            adb_prefix,
            ["shell", "ime", "set", ADB_KEYBOARD_IME],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        output = (set_result.stdout + set_result.stderr).strip()
        if set_result.returncode != 0 or "Error" in output or "Unknown" in output:
            raise RuntimeError(f"ADB Keyboard not enabled: {output}")

    return current_ime


def restore_keyboard(ime: str, device_id: str | None = None) -> None:
    """
    Restore the original keyboard IME.

    Args:
        ime: The IME identifier to restore.
        device_id: Optional ADB device ID for multi-device setups.
    """
    if _keep_adb_keyboard() or not ime or ime == "null" or ADB_KEYBOARD_IME in ime:
        return

    adb_prefix = _get_adb_prefix(device_id)

    _run_adb(
        adb_prefix,
        ["shell", "ime", "set", ime],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def _get_adb_prefix(device_id: str | None) -> list:
    """Get ADB command prefix with optional device specifier."""
    if device_id:
        return ["adb", "-s", device_id]
    return ["adb"]
