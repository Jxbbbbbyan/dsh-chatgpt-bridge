"""Locate the ChatGPT sidebar, capture it, and try to read its web content.

Two things are attempted here:
  1. a precise crop of the sidebar as it looks right now;
  2. a UI Automation read of the sidebar's renderer, retried, because Chromium
     only builds the accessibility tree for a renderer once a client asks.
"""
from __future__ import annotations

import ctypes
import io
import sys
import time
from pathlib import Path

import uiautomation as auto
from PIL import ImageGrab

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    ctypes.windll.user32.SetProcessDPIAware()

auto.SetGlobalSearchTimeout(2.0)
HERE = Path(__file__).parent


def find_descendant(node, predicate, max_depth: int = 9):
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


def all_descendants(node, max_depth: int, out: list, depth: int = 0) -> None:
    if depth > max_depth:
        return
    try:
        children = node.GetChildren()
    except Exception:
        return
    for child in children:
        out.append((depth, child))
        all_descendants(child, max_depth, out, depth + 1)


def main() -> int:
    edge = None
    for window in auto.GetRootControl().GetChildren():
        try:
            if "Edge" in (window.Name or ""):
                edge = window
                break
        except Exception:
            continue
    if edge is None:
        print("Edge not found")
        return 1

    sidebar = find_descendant(edge, lambda n: n.ClassName == "SidePaneRootContainer")
    if sidebar is None:
        print("sidebar not found")
        return 1
    r = sidebar.BoundingRectangle
    print(f"sidebar rect = ({r.left},{r.top},{r.right},{r.bottom}) {r.width()}x{r.height()}  name={sidebar.Name!r}")

    # fresh crop of just the sidebar
    screen = ImageGrab.grab()
    img = screen.crop((r.left, r.top, r.right, r.bottom))
    path = HERE / "sidebar-now.png"
    img.save(path)
    print(f"saved {path.name} {img.size}")
    print(f"sidebar-local coordinates: (0,0) top-left .. ({img.size[0]},{img.size[1]}) bottom-right")

    print("\n=== UIA read attempts ===")
    for attempt in range(1, 6):
        nodes: list = []
        all_descendants(sidebar, 14, nodes)
        interesting = [
            (d, n) for d, n in nodes
            if n.ControlTypeName in ("EditControl", "DocumentControl", "TextControl", "ButtonControl")
        ]
        print(f"[attempt {attempt}] descendants={len(nodes)} interesting={len(interesting)}")
        for d, n in interesting[:15]:
            try:
                b = n.BoundingRectangle
                print(f"    {'  ' * d}{n.ControlTypeName:<18} [{b.left},{b.top},{b.right},{b.bottom}] name={(n.Name or '')[:60]!r}")
            except Exception:
                pass
        if any(n.ControlTypeName == "EditControl" for _, n in interesting):
            print("    -> EditControl found; UIA is usable for reading")
            break
        time.sleep(1.0)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
