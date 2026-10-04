"""Drive a Chromium browser generically: activate a tab, navigate, read the page, shoot it.

The sidebar bridge targets one specific pane. This targets "whatever page the browser is
showing", which is what any web-console job needs (GitHub included). It reuses the same
SendInput emitter and the same accessibility-reading approach.

Usage:
    python browse.py --title Edge tab GitHub
    python browse.py --title Edge read
    python browse.py --title Edge goto https://github.com/
    python browse.py --title Edge shot gh-01
    python browse.py --title Edge click "Sign in"
"""
from __future__ import annotations

import argparse
import ctypes
import sys
import time
from pathlib import Path

import uiautomation as auto

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

# sidebar_bridge installs the UTF-8 stdout wrapper on import; wrapping the same
# buffer twice lets whichever wrapper is collected first close it for both.
from . import core as sidebar_bridge  # noqa: E402,F401
from .core import (  # noqa: E402
    INPUT,
    INPUT_KEYBOARD,
    KEYBDINPUT,
    KEYEVENTF_KEYUP,
    Emitter,
    InputLimits,
    VK_CONTROL,
    VK_RETURN,
    button_center,
    click_at,
    collect,
    normalize_for_compare,
    type_text_plan,
)

VK_L = 0x4C

auto.SetGlobalSearchTimeout(2.0)


def browser_window(title_hint: str):
    """The visible top-level window whose title contains the hint."""
    for window in auto.GetRootControl().GetChildren():
        try:
            name = window.Name or ""
            if not name or window.BoundingRectangle.width() <= 0:
                continue
            if title_hint.lower() in name.lower():
                return window
        except Exception:
            continue
    return None


def list_windows() -> None:
    print("visible top-level windows:")
    for window in auto.GetRootControl().GetChildren():
        try:
            r = window.BoundingRectangle
            if r.width() <= 0:
                continue
            print(f"  cls={(window.ClassName or '')[:24]:<24} hwnd={window.NativeWindowHandle:<10} "
                  f"{r.width()}x{r.height()}  {(window.Name or '')[:70]!r}")
        except Exception:
            continue


def foreground(window) -> None:
    """Bring a window to the front so keystrokes land in it."""
    user32 = ctypes.windll.user32
    hwnd = window.NativeWindowHandle
    user32.ShowWindow(hwnd, 9)  # SW_RESTORE
    user32.SetForegroundWindow(hwnd)
    time.sleep(0.6)


def ctrl_key(emitter: Emitter, vk: int) -> None:
    """Press Ctrl+<vk>: how a browser's address bar is focused."""
    emitter._send([INPUT(type=INPUT_KEYBOARD, ki=KEYBDINPUT(VK_CONTROL, 0, 0, 0, 0))])
    emitter._send([INPUT(type=INPUT_KEYBOARD, ki=KEYBDINPUT(vk, 0, 0, 0, 0))])
    emitter._send([INPUT(type=INPUT_KEYBOARD, ki=KEYBDINPUT(vk, 0, KEYEVENTF_KEYUP, 0, 0))])
    emitter._send([INPUT(type=INPUT_KEYBOARD, ki=KEYBDINPUT(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0, 0))])


def page_document(window):
    """The rendered document inside a browser window (Chromium builds it lazily)."""
    for _attempt in range(6):
        for _d, node in collect(window, 10):
            try:
                if node.ControlTypeName == "DocumentControl" and node.BoundingRectangle.width() > 200:
                    return node
            except Exception:
                continue
        time.sleep(0.7)
    return None


def resolve(args) -> object:
    window = browser_window(args.title)
    if window is None:
        print(f"no browser window matching {args.title!r}")
        list_windows()
    return window


def cmd_focus(args: argparse.Namespace) -> int:
    window = resolve(args)
    if window is None:
        return 1
    foreground(window)
    print(f"focused: {window.Name[:70]!r}")
    return 0


def cmd_tab(args: argparse.Namespace) -> int:
    """Click a browser tab by name, so the right page is in front."""
    window = resolve(args)
    if window is None:
        return 1
    target = None
    for _d, node in collect(window, 14):
        try:
            if node.ControlTypeName != "TabItemControl":
                continue
            if args.name.lower() in (node.Name or "").lower():
                target = node
                break
        except Exception:
            continue
    if target is None:
        print(f"no tab matching {args.name!r}")
        return 1
    start = Emitter.cursor_pos()
    emitter = Emitter()
    try:
        foreground(window)
        click_at(emitter, button_center(target), settle_s=args.settle)
        print(f"activated tab: {(target.Name or '')[:70]!r}")
        return 0
    finally:
        try:
            emitter.move_to(*start)
        except Exception:
            pass


def cmd_goto(args: argparse.Namespace) -> int:
    window = resolve(args)
    if window is None:
        return 1
    start = Emitter.cursor_pos()
    emitter = Emitter(InputLimits(max_seconds=180))
    try:
        foreground(window)
        ctrl_key(emitter, VK_L)
        time.sleep(0.4)
        emitter.select_all()
        type_text_plan(emitter, args.url, humanize=False)
        time.sleep(0.3)
        emitter.key_vk(VK_RETURN)
        print(f"navigating to {args.url}")
        time.sleep(args.wait)
        return 0
    finally:
        try:
            emitter.move_to(*start)
        except Exception:
            pass


def cmd_read(args: argparse.Namespace) -> int:
    window = resolve(args)
    if window is None:
        return 1
    document = page_document(window)
    if document is None:
        print("no rendered document found")
        return 1
    lines: list[str] = []
    seen: set[str] = set()
    for _d, node in collect(document, args.depth):
        try:
            if node.ControlTypeName not in (
                "TextControl", "EditControl", "HyperlinkControl", "ButtonControl", "TabItemControl"
            ):
                continue
            name = (node.Name or "").strip()
            if not name or name in seen:
                continue
            seen.add(name)
            lines.append(f"{node.ControlTypeName[:12]:<12} {name[:130]}")
        except Exception:
            continue
    print("\n".join(lines[: args.limit]))
    print(f"\n-- {len(lines)} named node(s), showing {min(len(lines), args.limit)}")
    return 0


def cmd_shot(args: argparse.Namespace) -> int:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        pass
    from PIL import ImageGrab

    window = resolve(args)
    if window is None:
        return 1
    foreground(window)
    image = ImageGrab.grab()
    path = HERE / f"{args.name or 'browser'}.png"
    image.save(path)
    print(f"saved {path} {image.size}")
    return 0


def cmd_click(args: argparse.Namespace) -> int:
    window = resolve(args)
    if window is None:
        return 1
    document = page_document(window) or window
    wanted = normalize_for_compare(args.name)
    target = None
    for _d, node in collect(document, 16):
        try:
            if node.ControlTypeName not in ("ButtonControl", "HyperlinkControl"):
                continue
            if normalize_for_compare(node.Name or "") == wanted:
                target = node
                break
        except Exception:
            continue
    if target is None:
        print(f"no button/link named {args.name!r}")
        return 1
    start = Emitter.cursor_pos()
    emitter = Emitter()
    try:
        foreground(window)
        click_at(emitter, button_center(target), settle_s=args.settle)
        print(f"clicked {args.name!r} at {button_center(target)}")
        return 0
    finally:
        try:
            emitter.move_to(*start)
        except Exception:
            pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--title", default="Chrome", help="top-level window title fragment")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("windows").set_defaults(func=lambda a: (list_windows(), 0)[1])
    sub.add_parser("focus").set_defaults(func=cmd_focus)

    p_tab = sub.add_parser("tab")
    p_tab.add_argument("name")
    p_tab.add_argument("--settle", type=float, default=1.5)
    p_tab.set_defaults(func=cmd_tab)

    p_goto = sub.add_parser("goto")
    p_goto.add_argument("url")
    p_goto.add_argument("--wait", type=float, default=4.0)
    p_goto.set_defaults(func=cmd_goto)

    p_read = sub.add_parser("read")
    p_read.add_argument("--depth", type=int, default=12)
    p_read.add_argument("--limit", type=int, default=120)
    p_read.set_defaults(func=cmd_read)

    p_shot = sub.add_parser("shot")
    p_shot.add_argument("name", nargs="?", default="browser")
    p_shot.set_defaults(func=cmd_shot)

    p_click = sub.add_parser("click")
    p_click.add_argument("name")
    p_click.add_argument("--settle", type=float, default=1.0)
    p_click.set_defaults(func=cmd_click)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
