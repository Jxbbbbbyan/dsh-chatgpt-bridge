"""Recon pass 2: find the ChatGPT sidebar's input box and transcript inside Edge.

Chromium builds its accessibility tree lazily, so the first enumeration often
returns only frame chrome. This touches the tree twice and then walks deep,
logging every node to a file and printing the ones that matter.
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

import uiautomation as auto

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

auto.SetGlobalSearchTimeout(2.0)

OUT = Path(__file__).with_name("uia-tree.txt")
MAX_DEPTH = int(sys.argv[1]) if len(sys.argv) > 1 else 9
MAX_NODES = int(sys.argv[2]) if len(sys.argv) > 2 else 4000

KEYWORDS = ("chatgpt", "openai", "gpt", "message", "prompt", "composer", "ask", "发送", "输入")

#: Chromium surfaces web content under these control types.
CONTENT_TYPES = {
    "DocumentControl",
    "EditControl",
    "TextControl",
    "HyperlinkControl",
    "ButtonControl",
    "ListControl",
    "ListItemControl",
    "GroupControl",
    "PaneControl",
    "CustomControl",
}


def rect(node) -> str:
    r = node.BoundingRectangle
    if r is None:
        return "[-,-,-,-]"
    return f"[{r.left},{r.top},{r.right},{r.bottom}] {r.width()}x{r.height()}"


def walk(node, depth: int, out: list[str], budget: list[int]) -> None:
    if budget[0] <= 0 or depth > MAX_DEPTH:
        return
    try:
        children = node.GetChildren()
    except Exception as exc:
        out.append(f"{'  ' * depth}<children failed: {exc}>")
        return
    for child in children:
        if budget[0] <= 0:
            return
        budget[0] -= 1
        try:
            out.append(
                "{indent}{ctype:<20} cls={cls:<26} {rect:<26} name={name!r}".format(
                    indent="  " * depth,
                    ctype=child.ControlTypeName,
                    cls=(child.ClassName or "")[:26],
                    rect=rect(child),
                    name=(child.Name or "").replace("\n", " ⏎ ")[:120],
                )
            )
        except Exception as exc:
            out.append(f"{'  ' * depth}<node failed: {exc}>")
            continue
        walk(child, depth + 1, out, budget)


def find_window(name_fragment: str):
    for window in auto.GetRootControl().GetChildren():
        try:
            if name_fragment.lower() in (window.Name or "").lower():
                return window
        except Exception:
            continue
    return None


def main() -> int:
    window = find_window("Microsoft\u200b Edge") or find_window("Edge")
    if window is None:
        print("Edge window not found")
        return 1
    print(f"target window: hwnd={window.NativeWindowHandle} name={window.Name[:80]!r}")

    # Touch the tree twice: the first walk is what makes Chromium build it.
    window.GetChildren()
    out: list[str] = []
    walk(window, 1, out, [MAX_NODES])
    OUT.write_text("\n".join(out), encoding="utf-8")
    print(f"walked {len(out)} nodes -> {OUT}")

    print("\n=== content-bearing nodes (Edit / Document / Text) ===")
    for line in out:
        if any(t in line for t in ("EditControl", "DocumentControl", "TextControl")):
            print(line)

    print("\n=== nodes matching keywords ===")
    for line in out:
        low = line.lower()
        if any(k in low for k in KEYWORDS):
            print(line)

    depths = {}
    for line in out:
        indent = (len(line) - len(line.lstrip(" "))) // 2
        depths[indent] = depths.get(indent, 0) + 1
    print(f"\ndepth histogram: {dict(sorted(depths.items()))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
