"""Inspect candidate windows: enumerate, classify, and crop each one for review."""
from __future__ import annotations

import ctypes
import io
import sys
from pathlib import Path

import uiautomation as auto
from PIL import ImageGrab

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    ctypes.windll.user32.SetProcessDPIAware()

auto.SetGlobalSearchTimeout(1.5)
HERE = Path(__file__).parent


def main() -> int:
    root = auto.GetRootControl()
    try:
        foreground = auto.GetForegroundControl()
        fg_hwnd = foreground.NativeWindowHandle
    except Exception:
        fg_hwnd = -1

    screen = ImageGrab.grab()
    print(f"screen={screen.size} foreground_hwnd={fg_hwnd}\n")

    saved = []
    for window in root.GetChildren():
        try:
            r = window.BoundingRectangle
            if r is None or r.width() <= 0 or r.height() <= 0:
                continue
            title = window.Name or ""
            hwnd = window.NativeWindowHandle
            cls = window.ClassName or ""
            mark = "  <== FOREGROUND" if hwnd == fg_hwnd else ""
            print(f"hwnd={hwnd:<10} cls={cls:<24} {r.width()}x{r.height()} at ({r.left},{r.top})  {title[:70]!r}{mark}")
            if any(k in title for k in ("ChatGPT", "Edge", "Chrome")):
                crop = (max(0, r.left), max(0, r.top), min(screen.size[0], r.right), min(screen.size[1], r.bottom))
                img = screen.crop(crop)
                path = HERE / f"win-{hwnd}.png"
                img.save(path)
                saved.append((hwnd, title, path, crop))
        except Exception as exc:
            print(f"  <{exc}>")

    print()
    for hwnd, title, path, crop in saved:
        print(f"saved {path.name}  hwnd={hwnd} crop={crop} title={title[:50]!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
