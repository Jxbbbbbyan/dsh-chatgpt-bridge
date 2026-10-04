"""Why does the Edge page content not appear in the accessibility tree?

Prints the control-type histogram for a browser window and every Document/Edit node
it can reach, at increasing search depths.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import browse  # noqa: E402
from dsh_chatgpt_bridge import core as sb  # noqa: E402

title = sys.argv[1] if len(sys.argv) > 1 else "Edge"
window = browse.browser_window(title)
if window is None:
    print(f"no window matching {title!r}")
    browse.list_windows()
    raise SystemExit(1)

print(f"window: {window.Name[:70]!r} hwnd={window.NativeWindowHandle}")

for attempt in range(1, 4):
    histogram: dict[str, int] = {}
    found = []
    for depth, node in sb.collect(window, 14):
        try:
            kind = node.ControlTypeName
        except Exception:
            continue
        histogram[kind] = histogram.get(kind, 0) + 1
        if kind in ("DocumentControl", "EditControl"):
            try:
                r = node.BoundingRectangle
                found.append((depth, kind, (r.left, r.top, r.right, r.bottom), r.width(), r.height(), node.Name or ""))
            except Exception:
                pass
    print(f"\n[attempt {attempt}] types={histogram}")
    for depth, kind, rect, w, h, name in found:
        print(f"   {kind} depth={depth} rect={rect} {w}x{h} name={name[:50]!r}")
    if any(w > 200 for _d, _k, _r, w, _h, _n in found):
        break
    time.sleep(1.0)
