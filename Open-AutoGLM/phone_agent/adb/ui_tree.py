"""UI hierarchy utilities via uiautomator dump (hybrid grounding for remote ADB)."""

import os
import re
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from typing import Any

DEFAULT_UI_TREE_TIMEOUT = 30
MAX_UI_ELEMENTS = 40
_BOUNDS_RE = re.compile(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]")


def get_ui_elements(
    device_id: str | None = None,
    timeout: int | None = None,
    max_elements: int = MAX_UI_ELEMENTS,
) -> list[dict[str, Any]]:
    """
    Dump the accessibility tree and return salient interactive elements.

    Used as text grounding alongside VLM screenshots (helps locate search boxes).
    """
    if os.getenv("PHONE_AGENT_UI_TREE", "true").lower() not in ("1", "true", "yes"):
        return []

    adb_prefix = _get_adb_prefix(device_id)
    ui_timeout = timeout or int(os.getenv("PHONE_AGENT_UI_TREE_TIMEOUT", DEFAULT_UI_TREE_TIMEOUT))

    xml_text = _fetch_ui_xml(adb_prefix, ui_timeout)
    if not xml_text:
        return []

    return _parse_ui_xml(xml_text, max_elements=max_elements)


def _fetch_ui_xml(adb_prefix: list[str], timeout: int) -> str:
    dump_path = "/sdcard/window_dump.xml"
    try:
        dump_result = subprocess.run(
            adb_prefix + ["shell", "uiautomator", "dump", dump_path],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if dump_result.returncode != 0:
            return ""

        cat_result = subprocess.run(
            adb_prefix + ["exec-out", "cat", dump_path],
            capture_output=True,
            timeout=timeout,
        )
        if cat_result.returncode == 0 and cat_result.stdout:
            return cat_result.stdout.decode("utf-8", errors="replace")

        pull_path = os.path.join(tempfile.gettempdir(), f"window_dump_{os.getpid()}.xml")
        try:
            pull_result = subprocess.run(
                adb_prefix + ["pull", dump_path, pull_path],
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            if pull_result.returncode != 0:
                return ""
            with open(pull_path, encoding="utf-8", errors="replace") as handle:
                return handle.read()
        finally:
            if os.path.exists(pull_path):
                os.remove(pull_path)
    except Exception as exc:
        print(f"UI tree error: {exc}")
        return ""


def _parse_ui_xml(xml_text: str, max_elements: int) -> list[dict[str, Any]]:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []

    candidates: list[tuple[int, dict[str, Any]]] = []
    for node in root.iter("node"):
        text = (node.attrib.get("text") or "").strip()
        content_desc = (node.attrib.get("content-desc") or "").strip()
        resource_id = (node.attrib.get("resource-id") or "").strip()
        class_name = (node.attrib.get("class") or "").strip()
        clickable = node.attrib.get("clickable") == "true"
        focusable = node.attrib.get("focusable") == "true"
        bounds = _parse_bounds(node.attrib.get("bounds", ""))

        if not bounds:
            continue

        label = text or content_desc or resource_id
        if not label and not clickable and "EditText" not in class_name:
            continue

        element = {
            "text": text,
            "content_desc": content_desc,
            "resource_id": resource_id,
            "class": class_name,
            "clickable": clickable,
            "focusable": focusable,
            "bounds": list(bounds),
            "center": _center(bounds),
        }
        candidates.append((_score_element(element), element))

    candidates.sort(key=lambda item: item[0], reverse=True)
    return [item[1] for item in candidates[:max_elements]]


def _score_element(element: dict[str, Any]) -> int:
    score = 0
    label = f"{element['text']} {element['content_desc']} {element['resource_id']}".lower()
    if element["clickable"]:
        score += 2
    if element["focusable"]:
        score += 2
    if "edittext" in element["class"].lower():
        score += 5
    for keyword in ("搜索", "search", "query", "输入", "查找"):
        if keyword in label:
            score += 8
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
            score -= 6
    if element["text"]:
        score += 1
    return score


def _parse_bounds(raw: str) -> tuple[int, int, int, int] | None:
    match = _BOUNDS_RE.search(raw)
    if not match:
        return None
    x1, y1, x2, y2 = (int(match.group(i)) for i in range(1, 5))
    if x2 <= x1 or y2 <= y1:
        return None
    return x1, y1, x2, y2


def _center(bounds: tuple[int, int, int, int]) -> list[int]:
    x1, y1, x2, y2 = bounds
    return [(x1 + x2) // 2, (y1 + y2) // 2]


def _get_adb_prefix(device_id: str | None) -> list[str]:
    if device_id:
        return ["adb", "-s", device_id]
    return ["adb"]
