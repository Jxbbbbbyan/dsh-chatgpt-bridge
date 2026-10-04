"""Probe the ChatGPT sidebar's web content.

Chromium builds its accessibility tree lazily: the first UIA query on a renderer
returns frame chrome only, and the document appears a moment later. This walks
the sidebar's render widget repeatedly until the web content shows up.
"""
from __future__ import annotations

import io
import sys
import time
from pathlib import Path

import uiautomation as auto

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
auto.SetGlobalSearchTimeout(2.0)

ATTEMPTS = int(sys.argv[1]) if len(sys.argv) > 1 else 12
SLEEP = float(sys.argv[2]) if len(sys.argv) > 2 else 0.7
OUT = Path(__file__).with_name("sidebar-tree.txt")


def rect(node) -> str:
    r = node.BoundingRectangle
    if r is None:
        return "[-,-,-,-]"
    return f"[{r.left},{r.top},{r.right},{r.bottom}] {r.width()}x{r.height()}"


def walk(node, depth: int, out: list[str], budget: list[int], max_depth: int) -> None:
    if budget[0] <= 0 or depth > max_depth:
        return
    try:
        children = node.GetChildren()
    except Exception:
        return
    for child in children:
        if budget[0] <= 0:
            return
        budget[0] -= 1
        try:
            out.append(
                "{indent}{ctype:<20} cls={cls:<22} {rect:<26} name={name!r}".format(
                    indent="  " * depth,
                    ctype=child.ControlTypeName,
                    cls=(child.ClassName or "")[:22],
                    rect=rect(child),
                    name=(child.Name or "").replace("\n", " ⏎ ")[:110],
                )
            )
        except Exception:
            continue
        walk(child, depth + 1, out, budget, max_depth)


def find_descendant(node, predicate, max_depth: int = 8):
    """Depth-first search for the first descendant satisfying predicate."""
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


def main() -> int:
    edge = None
    for window in auto.GetRootControl().GetChildren():
        try:
            if "Microsoft\u200b Edge" in (window.Name or "") or "Edge" in (window.Name or ""):
                edge = window
                break
        except Exception:
            continue
    if edge is None:
        print("Edge window not found")
        return 1
    print(f"edge hwnd={edge.NativeWindowHandle}")

    sidebar = find_descendant(edge, lambda n: n.ClassName == "SidePaneRootContainer")
    if sidebar is None:
        print("sidebar pane not found")
        return 1
    print(f"sidebar: {rect(sidebar)} name={sidebar.Name!r}")

    widget = find_descendant(sidebar, lambda n: (n.ClassName or "").startswith("Chrome_RenderWidgetHost"))
    if widget is None:
        print("render widget not found inside sidebar")
        return 1
    print(f"render widget: {rect(widget)} cls={widget.ClassName}")

    best = ""
    for attempt in range(1, ATTEMPTS + 1):
        out: list[str] = []
        walk(widget, 1, out, [3000], 10)
        text = "\n".join(out)
        interesting = [
            line for line in out
            if any(t in line for t in ("EditControl", "DocumentControl", "TextControl", "ButtonControl"))
        ]
        print(f"\n[attempt {attempt}] nodes={len(out)} interesting={len(interesting)}")
        for line in interesting[:12]:
            print("   ", line.strip())
        if len(out) > len(best):
            best = text
        if any("EditControl" in line or "DocumentControl" in line for line in out):
            print("\n*** web content is in the tree ***")
            break
        time.sleep(SLEEP)

    OUT.write_text(best, encoding="utf-8")
    print(f"\nlargest tree saved -> {OUT} ({len(best.splitlines())} lines)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
