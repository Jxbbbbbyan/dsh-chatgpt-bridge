"""Dump any top-level window's UI Automation subtree, to drive native dialogs.

The sidebar bridge targets the Edge sidebar specifically; native dialogs (the Windows
file picker, for instance) are separate windows, so they need their own look-up.
"""
from __future__ import annotations

import io
import sys

import uiautomation as auto

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
auto.SetGlobalSearchTimeout(1.5)


def collect(node, max_depth: int, depth: int = 0, out: list | None = None) -> list:
    if out is None:
        out = []
    if depth > max_depth:
        return out
    try:
        children = node.GetChildren()
    except Exception:
        return out
    for child in children:
        out.append((depth, child))
        collect(child, max_depth, depth + 1, out)
    return out


def rect(node) -> str:
    try:
        r = node.BoundingRectangle
        return f"[{r.left},{r.top},{r.right},{r.bottom}] {r.width()}x{r.height()}"
    except Exception:
        return "[-,-,-,-]"


def main() -> int:
    fragment = sys.argv[1] if len(sys.argv) > 1 else ""
    max_depth = int(sys.argv[2]) if len(sys.argv) > 2 else 5

    window = None
    for candidate in auto.GetRootControl().GetChildren():
        try:
            if fragment.lower() in (candidate.Name or "").lower():
                window = candidate
                break
        except Exception:
            continue
    if window is None:
        print(f"no top-level window matching {fragment!r}")
        for candidate in auto.GetRootControl().GetChildren():
            try:
                if candidate.BoundingRectangle.width() > 0:
                    print(f"  {candidate.ControlTypeName:<16} {candidate.Name[:60]!r}")
            except Exception:
                continue
        return 1

    print(f"window {window.Name!r} cls={window.ClassName} hwnd={window.NativeWindowHandle}")
    for depth, node in collect(window, max_depth):
        try:
            print(f"{'  ' * depth}{node.ControlTypeName:<18} {rect(node):<28} "
                  f"cls={(node.ClassName or '')[:20]:<20} name={(node.Name or '')[:60]!r}")
        except Exception:
            continue
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
