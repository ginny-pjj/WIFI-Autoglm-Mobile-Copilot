"""ADB utilities for Android device interaction."""

from phone_agent.adb.connection import (
    ADBConnection,
    ConnectionType,
    DeviceInfo,
    list_devices,
    quick_connect,
)
from phone_agent.adb.device import (
    back,
    double_tap,
    get_current_app,
    home,
    launch_app,
    long_press,
    swipe,
    tap,
    ensure_meituan_home_tab,
)
from phone_agent.adb.input import (
    clear_text,
    detect_and_set_adb_keyboard,
    restore_keyboard,
    type_text,
)
from phone_agent.adb.screenshot import get_screenshot
from phone_agent.adb.ui_tree import get_ui_elements

__all__ = [
    # Screenshot
    "get_screenshot",
    "get_ui_elements",
    # Input
    "type_text",
    "clear_text",
    "detect_and_set_adb_keyboard",
    "restore_keyboard",
    # Device control
    "get_current_app",
    "tap",
    "swipe",
    "back",
    "home",
    "double_tap",
    "long_press",
    "launch_app",
    "ensure_meituan_home_tab",
    # Connection management
    "ADBConnection",
    "DeviceInfo",
    "ConnectionType",
    "quick_connect",
    "list_devices",
]
