"""Screenshot helper: grab the ChatGPT sidebar (and full screen) with DPI awareness.

DPI awareness matters: UI Automation reports physical pixels, and an unaware
Python process would grab a scaled bitmap, so the screenshot and the click
coordinates would disagree.
"""
from __future__ import annotations

import ctypes
import io
import sys
from pathlib import Path

import uiautomation as auto
from PIL import ImageGrab

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# PROCESS_PER_MONITOR_DPI_AWARE = 2
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    ctypes.windll.user32.SetProcessDPIAware()

HERE = Path(__file__).parent


def find_descendant(node, predicate, max_depth: int = 8):
    if max_depth < 0:
        return None
    try:
        children = node.GetChildren()
    except Exception:
        return None
    for child in children:
        try:
            if predicate(child):
                return child
        except Exception:
            continue
    for child in children:
        found = find_descendant(child, predicate, max_depth - 1)
        if found is not None:
            return found
    return None


def sidebar_rect():
    for window in auto.GetRootControl().GetChildren():
        try:
            if "Edge" not in (window.Name or ""):
                continue
        except Exception:
            continue
        pane = find_descendant(window, lambda n: n.ClassName == "SidePaneRootContainer")
        if pane is not None:
            r = pane.BoundingRectangle
            return (r.left, r.top, r.right, r.bottom), window
    return None, None


def main() -> int:
    rect, window = sidebar_rect()
    if rect is None:
        print("sidebar not found")
        return 1
    left, top, right, bottom = rect
    print(f"sidebar rect = {(left, top, right, bottom)}  size={right - left}x{bottom - top}")

    screen = ImageGrab.grab()
    print(f"virtual screen size = {screen.size}")

    pad = 6
    crop = (max(0, left - pad), max(0, top - pad), right + pad, bottom + pad)
    sidebar_img = screen.crop(crop)
    sidebar_path = HERE / "shot-sidebar.png"
    sidebar_img.save(sidebar_path)

    full_path = HERE / "shot-screen.png"
    screen.save(full_path)

    # The sidebar with its top strip, so the header is visible for orientation.
    print(f"saved {sidebar_path.name} ({sidebar_img.size[0]}x{sidebar_img.size[1]}) crop={crop}")
    print(f"saved {full_path.name} ({screen.size[0]}x{screen.size[1]})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
