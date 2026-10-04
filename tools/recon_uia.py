"""Recon: dump the Windows UIA tree so we can locate the ChatGPT sidebar in Edge.

Read-only. Prints top-level windows, then walks the interesting ones and reports
every node that looks like a text input, a document, or ChatGPT itself.
"""
from __future__ import annotations

import sys

import uiautomation as auto

auto.SetGlobalSearchTimeout(1.5)

MAX_DEPTH = int(sys.argv[1]) if len(sys.argv) > 1 else 5
MAX_LINES = int(sys.argv[2]) if len(sys.argv) > 2 else 400

INTERESTING = ("edit", "document", "text", "pane", "group", "button", "hyperlink", "list")


def rect(node) -> str:
    r = node.BoundingRectangle
    if r is None:
        return "rect=None"
    return f"[{r.left},{r.top},{r.right},{r.bottom}] {r.width()}x{r.height()}"


def walk(node, depth, out, budget):
    if budget[0] <= 0 or depth > MAX_DEPTH:
        return
    try:
        children = node.GetChildren()
    except Exception as exc:  # pragma: no cover - defensive
        out.append(f"{'  ' * depth}<children failed: {exc}>")
        return
    for child in children:
        if budget[0] <= 0:
            return
        budget[0] -= 1
        try:
            name = (child.Name or "").replace("\n", " ")[:90]
            ctype = child.ControlTypeName
            ctrl_type = child.ControlType
            cls = child.ClassName or ""
            out.append(f"{'  ' * depth}{ctype:<18} cls={cls[:28]:<28} {rect(child)}  name={name!r}")
        except Exception as exc:
            out.append(f"{'  ' * depth}<node failed: {exc}>")
            continue
        walk(child, depth + 1, out, budget)


def main() -> int:
    root = auto.GetRootControl()
    print("=== top-level windows ===")
    targets = []
    for window in root.GetChildren():
        try:
            name = window.Name or ""
            ctype = window.ControlTypeName
            print(f"  {ctype:<22} hwnd={window.NativeWindowHandle:<10} {rect(window)}  name={name[:80]!r}")
            if any(k in name for k in ("Edge", "ChatGPT", "Microsoft Edge")):
                targets.append(window)
        except Exception as exc:
            print(f"  <{exc}>")

    for window in targets:
        print(f"\n=== tree of {window.Name[:70]!r} (depth<={MAX_DEPTH}) ===")
        out: list[str] = []
        walk(window, 1, out, [MAX_LINES])
        print("\n".join(out))
        if len(out) >= MAX_LINES:
            print(f"... truncated at {MAX_LINES} nodes")

        print("\n--- nodes whose name mentions chatgpt/openai ---")
        hits = [line for line in out if any(k in line.lower() for k in ("chatgpt", "openai", "gpt-"))]
        print("\n".join(hits[:40]) if hits else "  (none)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
