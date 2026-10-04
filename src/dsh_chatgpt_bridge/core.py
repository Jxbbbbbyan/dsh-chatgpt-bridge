"""Drive the ChatGPT sidebar docked in Edge with real OS-level mouse and keyboard input.

Design notes
------------
* **Real input, not injection.** Every event goes through the Windows ``SendInput``
  API, so it reaches the application the same way a physical mouse and keyboard do.
  Nothing here touches the page's JavaScript, the accessibility tree's invoke
  patterns, or the network.
* **Trajectory and keystroke timing come from the calibrated engine** in the sibling
  ``humanized-input-lab`` project (:mod:`hilab.motion`, :mod:`hilab.typing`) when it is
  importable; a built-in minimum-jerk / log-normal fallback keeps this tool usable
  without it. Deliberate typo injection is disabled: a corrupted prompt is not a
  useful kind of realism here.
* **Targeting comes from UI Automation**, which already exposes the sidebar's web
  content once the renderer has been asked for it.
* **Bounded and abortable.** Every run carries wall-clock, event-count, and cursor
  distance caps, checks the panic key (Escape) before every emission, and restores
  the cursor to where it started.

Usage
-----
    python sidebar_bridge.py find                 # locate the sidebar and its composer
    python sidebar_bridge.py dump                 # print the sidebar's UIA tree
    python sidebar_bridge.py read                 # print the current transcript text
    python sidebar_bridge.py ask "your question"  # click, type, send, and read the reply
    python sidebar_bridge.py ask --dry-run "..."  # plan only; emit nothing
"""
from __future__ import annotations

import argparse
import ctypes
import os
import io
import random
import re
import sys
import time
from ctypes import wintypes
from dataclasses import dataclass, field
from pathlib import Path

import uiautomation as auto

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# ------------------------------------------------------------------------------
# DPI awareness: UIA reports physical pixels; an unaware process would be scaled.
# ------------------------------------------------------------------------------
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:  # pragma: no cover - older Windows
    ctypes.windll.user32.SetProcessDPIAware()

auto.SetGlobalSearchTimeout(2.0)

HERE = Path(__file__).parent
WORKSPACE = HERE.parent
# Both are overridable so the shipped package works outside the source tree.
HILAB_ROOT = Path(os.environ.get("HILAB_ROOT", WORKSPACE / "humanized-input-lab"))
STATE_DIR = Path(os.environ.get("DSH_BRIDGE_STATE", str(HERE)))

# ------------------------------------------------------------------------------
# Humanized timing models (optional dependency on the sibling research harness)
# ------------------------------------------------------------------------------
try:
    if str(HILAB_ROOT) not in sys.path:
        sys.path.insert(0, str(HILAB_ROOT))
    from hilab.motion import MotionParams, plan_move  # type: ignore
    from hilab.typing import TypingParams, plan_typing  # type: ignore

    HUMANIZED_ENGINE = "hilab"
except Exception as exc:  # pragma: no cover - fallback path
    HUMANIZED_ENGINE = f"builtin (hilab unavailable: {type(exc).__name__})"
    MotionParams = None  # type: ignore
    TypingParams = None  # type: ignore
    plan_move = None  # type: ignore
    plan_typing = None  # type: ignore


# ==============================================================================
# SendInput plumbing
# ==============================================================================
ULONG_PTR = ctypes.c_uint64 if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_uint32

INPUT_MOUSE = 0
INPUT_KEYBOARD = 1
MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_WHEEL = 0x0800
MOUSEEVENTF_VIRTUALDESK = 0x4000
MOUSEEVENTF_ABSOLUTE = 0x8000
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004

SM_XVIRTUALSCREEN, SM_YVIRTUALSCREEN = 76, 77
SM_CXVIRTUALSCREEN, SM_CYVIRTUALSCREEN = 78, 79

VK_BACK, VK_RETURN, VK_ESCAPE = 0x08, 0x0D, 0x1B
VK_CONTROL, VK_A = 0x11, 0x41
VK_SHIFT = 0x10
VK_V = 0x56

user32 = ctypes.WinDLL("user32", use_last_error=True)


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD), ("wParamH", wintypes.WORD)]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUTUNION)]


user32.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
user32.SendInput.restype = wintypes.UINT


class InputAborted(RuntimeError):
    """Raised when the panic key, a cap, or the caller stops emission."""


@dataclass
class InputLimits:
    max_seconds: float = 180.0
    max_events: int = 4000
    max_distance_px: float = 60000.0


class Emitter:
    """Emits real mouse and keyboard events, guarded by a panic key and hard caps."""

    def __init__(self, limits: InputLimits | None = None, panic_vk: int = VK_ESCAPE):
        self.limits = limits or InputLimits()
        self.panic_vk = panic_vk
        self.events = 0
        self.distance = 0.0
        self.started = time.monotonic()
        self._last: tuple[float, float] | None = None

    # -- guards ---------------------------------------------------------------
    def _guard(self, *, will_move: float = 0.0) -> None:
        if user32.GetAsyncKeyState(self.panic_vk) & 0x8000:
            raise InputAborted("panic key is down")
        if time.monotonic() - self.started > self.limits.max_seconds:
            raise InputAborted(f"exceeded max_seconds={self.limits.max_seconds}")
        if self.events >= self.limits.max_events:
            raise InputAborted(f"exceeded max_events={self.limits.max_events}")
        if self.distance + will_move > self.limits.max_distance_px:
            raise InputAborted(f"exceeded max_distance_px={self.limits.max_distance_px}")

    def _send(self, payloads: list[INPUT]) -> None:
        array = (INPUT * len(payloads))(*payloads)
        sent = user32.SendInput(len(payloads), array, ctypes.sizeof(INPUT))
        if sent != len(payloads):
            raise ctypes.WinError(ctypes.get_last_error())
        self.events += len(payloads)

    # -- mouse ----------------------------------------------------------------
    @staticmethod
    def virtual_screen() -> tuple[int, int, int, int]:
        g = user32.GetSystemMetrics
        return (
            g(SM_XVIRTUALSCREEN),
            g(SM_YVIRTUALSCREEN),
            g(SM_CXVIRTUALSCREEN),
            g(SM_CYVIRTUALSCREEN),
        )

    @staticmethod
    def cursor_pos() -> tuple[int, int]:
        point = wintypes.POINT()
        user32.GetCursorPos(ctypes.byref(point))
        return point.x, point.y

    def move_to(self, x: float, y: float) -> None:
        vx, vy, vw, vh = self.virtual_screen()
        nx = int(round((x - vx) * 65535 / max(1, vw - 1)))
        ny = int(round((y - vy) * 65535 / max(1, vh - 1)))
        if self._last is not None:
            self.distance += ((x - self._last[0]) ** 2 + (y - self._last[1]) ** 2) ** 0.5
        self._last = (x, y)
        self._guard(will_move=0.0)
        self._send([
            INPUT(type=INPUT_MOUSE, mi=MOUSEINPUT(
                dx=nx, dy=ny, mouseData=0,
                dwFlags=MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK,
                time=0, dwExtraInfo=0)),
        ])

    def click(self, button: str = "left") -> None:
        """Press a real mouse button: 'left' (default) or 'right'."""
        down = MOUSEEVENTF_LEFTDOWN if button == "left" else MOUSEEVENTF_RIGHTDOWN
        up = MOUSEEVENTF_LEFTUP if button == "left" else MOUSEEVENTF_RIGHTUP
        self._guard()
        self._send([INPUT(type=INPUT_MOUSE, mi=MOUSEINPUT(0, 0, 0, down, 0, 0))])
        time.sleep(0.06)
        self._send([INPUT(type=INPUT_MOUSE, mi=MOUSEINPUT(0, 0, 0, up, 0, 0))])

    def right_click(self) -> None:
        self.click("right")

    def wheel(self, delta: int) -> None:
        """Scroll the wheel: +120 per notch down, -120 per notch up."""
        self._guard()
        self._send([INPUT(type=INPUT_MOUSE, mi=MOUSEINPUT(0, 0, delta, MOUSEEVENTF_WHEEL, 0, 0))])

    # -- keyboard -------------------------------------------------------------
    def key_vk(self, vk: int, *, hold_s: float = 0.03) -> None:
        self._guard()
        self._send([INPUT(type=INPUT_KEYBOARD, ki=KEYBDINPUT(vk, 0, 0, 0, 0))])
        time.sleep(hold_s)
        self._send([INPUT(type=INPUT_KEYBOARD, ki=KEYBDINPUT(vk, 0, KEYEVENTF_KEYUP, 0, 0))])

    def key_shifted(self, vk: int, *, hold_s: float = 0.03) -> None:
        """Hold Shift while pressing a key. Shift+Enter is 'newline', not 'send'."""
        self._guard()
        self._send([INPUT(type=INPUT_KEYBOARD, ki=KEYBDINPUT(VK_SHIFT, 0, 0, 0, 0))])
        self._send([INPUT(type=INPUT_KEYBOARD, ki=KEYBDINPUT(vk, 0, 0, 0, 0))])
        time.sleep(hold_s)
        self._send([INPUT(type=INPUT_KEYBOARD, ki=KEYBDINPUT(vk, 0, KEYEVENTF_KEYUP, 0, 0))])
        self._send([INPUT(type=INPUT_KEYBOARD, ki=KEYBDINPUT(VK_SHIFT, 0, KEYEVENTF_KEYUP, 0, 0))])

    def key_unicode(self, ch: str, *, hold_s: float = 0.02) -> None:
        """Send one character as a Unicode scan code, so any script arrives intact."""
        for unit in _utf16_units(ch):
            self._guard()
            self._send([INPUT(type=INPUT_KEYBOARD, ki=KEYBDINPUT(0, unit, KEYEVENTF_UNICODE, 0, 0))])
            time.sleep(hold_s)
            self._send([
                INPUT(type=INPUT_KEYBOARD, ki=KEYBDINPUT(0, unit, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP, 0, 0)),
            ])

    def press_esc(self) -> None:
        self.key_vk(VK_ESCAPE)

    def select_all(self) -> None:
        self._guard()
        self._send([INPUT(type=INPUT_KEYBOARD, ki=KEYBDINPUT(VK_CONTROL, 0, 0, 0, 0))])
        self._send([INPUT(type=INPUT_KEYBOARD, ki=KEYBDINPUT(VK_A, 0, 0, 0, 0))])
        self._send([INPUT(type=INPUT_KEYBOARD, ki=KEYBDINPUT(VK_A, 0, KEYEVENTF_KEYUP, 0, 0))])
        self._send([INPUT(type=INPUT_KEYBOARD, ki=KEYBDINPUT(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0, 0))])

    def paste(self) -> None:
        """Ctrl+V, so whatever the caller put on the clipboard lands in the focused field."""
        self._guard()
        self._send([INPUT(type=INPUT_KEYBOARD, ki=KEYBDINPUT(VK_CONTROL, 0, 0, 0, 0))])
        self._send([INPUT(type=INPUT_KEYBOARD, ki=KEYBDINPUT(VK_V, 0, 0, 0, 0))])
        self._send([INPUT(type=INPUT_KEYBOARD, ki=KEYBDINPUT(VK_V, 0, KEYEVENTF_KEYUP, 0, 0))])
        self._send([INPUT(type=INPUT_KEYBOARD, ki=KEYBDINPUT(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0, 0))])


def _utf16_units(ch: str) -> list[int]:
    encoded = ch.encode("utf-16-le")
    return [int.from_bytes(encoded[i:i + 2], "little") for i in range(0, len(encoded), 2)]


# ==============================================================================
# Motion and typing plans
# ==============================================================================
@dataclass
class Plan:
    moves: list[tuple[float, float, float]] = field(default_factory=list)  # (t, x, y)
    keys: list[tuple[str, float]] = field(default_factory=list)            # (char, t)
    source: str = "unknown"


def _eased_path(start: tuple[float, float], end: tuple[float, float], duration: float, rng: random.Random):
    """Minimum-jerk fallback, sampled at 60 Hz."""
    samples = []
    steps = max(2, int(duration * 60))
    for i in range(steps + 1):
        u = i / steps
        s = 10 * u**3 - 15 * u**4 + 6 * u**5
        x = start[0] + (end[0] - start[0]) * s + rng.gauss(0, 0.6)
        y = start[1] + (end[1] - start[1]) * s + rng.gauss(0, 0.6)
        samples.append((u * duration, x, y))
    return samples


def build_motion(start: tuple[float, float], end: tuple[float, float],
                 target_width: float, seed: int | None = None) -> Plan:
    """Plan only the pointing movement: cursor -> target."""
    rng = random.Random(seed if seed is not None else time.time_ns() & 0xFFFFFFFF)
    if plan_move is not None:
        movement = plan_move(start, end, max(8.0, target_width), MotionParams(), rng, cadence_hz=60.0)
        moves = [(t, x, y) for t, x, y in movement.samples]
    else:
        moves = _eased_path(start, end, 0.55, rng)
    return Plan(moves=moves, keys=[], source=HUMANIZED_ENGINE)


def build_plan(text: str, start: tuple[float, float], end: tuple[float, float],
               target_width: float, seed: int | None = None) -> Plan:
    """Plan a movement and a typing sequence. Kept for planning/preview only.

    Callers that actually drive the machine must emit these two phases separately
    and focus the target in between: replaying one merged timeline would type
    before anything had focus.
    """
    motion = build_motion(start, end, target_width, seed)
    rng = random.Random((seed if seed is not None else time.time_ns()) ^ 0x5EED)

    if plan_typing is not None:
        params = TypingParams()
        # No deliberate typos: a corrupted prompt is not useful realism here.
        if hasattr(params, "typo_rate"):
            params.typo_rate = 0.0
        typing_plan = plan_typing(text, params, rng)
        keys = [(step.key, step.t_down) for step in typing_plan.steps]
    else:
        keys, t = [], 0.0
        for i, ch in enumerate(text):
            t += rng.lognormvariate(-3.2, 0.35) + (0.35 if i and text[i - 1] == " " else 0.0)
            keys.append((ch, t))

    motion.keys = keys
    return motion


def run_plan(emitter: Emitter, plan: Plan, *, dry_run: bool = False,
             emit_click: bool = True, verbose: bool = True) -> None:
    """Replay a plan in real time, sleeping between events."""
    timeline: list[tuple[float, str, object]] = []
    for t, x, y in plan.moves:
        timeline.append((t, "move", (x, y)))
    for ch, t in plan.keys:
        timeline.append((t, "key", ch))
    timeline.sort(key=lambda item: item[0])

    t0 = time.monotonic()
    for t, kind, payload in timeline:
        wait = t - (time.monotonic() - t0)
        if wait > 0:
            time.sleep(wait)
        if dry_run:
            continue
        if kind == "move":
            x, y = payload  # type: ignore[misc]
            emitter.move_to(x, y)
        else:
            ch = payload  # type: ignore[assignment]
            if ch == "Backspace":
                emitter.key_vk(VK_BACK)
            elif ch in ("\n", "Enter", "\r"):
                emitter.key_vk(VK_RETURN)
            elif len(ch) == 1:
                emitter.key_unicode(ch)
            if verbose and len(plan.keys) <= 40:
                pass
    # A move plan ends exactly on the target; click there unless the caller
    # handles focusing itself (which is what click_composer() does).
    if not dry_run and emit_click:
        emitter.click()


# ==============================================================================
# UI Automation targeting and reading
# ==============================================================================
def find_descendant(node, predicate, max_depth: int = 12):
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


@dataclass
class Target:
    window: object
    sidebar: object
    document: object
    composer: object
    composer_rect: tuple[int, int, int, int]

    @property
    def center(self) -> tuple[float, float]:
        left, top, right, bottom = self.composer_rect
        return ((left + right) / 2, (top + bottom) / 2)

    @property
    def focus_point(self) -> tuple[float, float]:
        """A point on the composer's text line, not its geometric centre.

        Attachments grow the composer upward, so the centre can land on a
        thumbnail — clicking that opens the image preview and steals focus
        instead of placing the caret. The text line is always at the bottom.
        """
        left, top, right, bottom = self.composer_rect
        return ((left + right) / 2, bottom - 14)

    @property
    def width(self) -> float:
        left, top, right, bottom = self.composer_rect
        return float(right - left)


def locate_sidebar(edge_title_hint: str = "Edge", retries: int = 4) -> Target:
    """Find the Edge window, its ChatGPT sidebar pane, and the composer inside it."""
    window = None
    for candidate in auto.GetRootControl().GetChildren():
        try:
            if edge_title_hint.lower() in (candidate.Name or "").lower():
                window = candidate
                break
        except Exception:
            continue
    if window is None:
        raise LookupError(f"no top-level window matching {edge_title_hint!r}")

    sidebar = find_descendant(window, lambda n: n.ClassName == "SidePaneRootContainer")
    if sidebar is None:
        raise LookupError("Edge is running but no sidebar pane is open")

    # Chromium builds the accessibility tree lazily; the first query warms it.
    # The composer sits ~15 levels deep under the sidebar, so search generously.
    document = composer = None
    for attempt in range(retries):
        document = find_descendant(
            sidebar, lambda n: n.ControlTypeName == "DocumentControl", max_depth=20
        )
        composer = find_descendant(
            sidebar, lambda n: n.ControlTypeName == "EditControl", max_depth=20
        )
        if composer is not None:
            break
        time.sleep(0.6)
    if composer is None:
        seen = sorted({n.ControlTypeName for _d, n in collect(sidebar, 20)})
        raise LookupError(
            "sidebar found, but no composer EditControl appeared; control types present: "
            + ", ".join(seen)
        )
    if document is None:
        raise LookupError("sidebar found, but its DocumentControl did not appear")

    r = composer.BoundingRectangle
    return Target(window, sidebar, document,
                  composer, (r.left, r.top, r.right, r.bottom))


def composer_text(target: Target) -> str:
    """Read the composer's current contents."""
    try:
        return target.composer.GetValuePattern().Value or ""
    except Exception:
        pass
    try:
        return target.composer.Name or ""
    except Exception:
        return ""


#: Sidebar chrome that is not part of the conversation.
CHROME_LINES = {
    "Do anything",
    "New chat",
    "No chats in progress",
    "Thinking",
    "Copy",
    "Good response",
    "Bad response",
    "Regenerate",
    "Acknowledge request",
    "Send",
    "Stop",
    "Search",
}
TIMESTAMP_RE = re.compile(r"^\d{1,2}:\d{2}\s*(?:AM|PM)?$", re.IGNORECASE)
#: Chromium announces completion through an ARIA live region; the text lands in the
#: accessibility tree as its own node ("Response complete: DONE").
ANNOUNCEMENT_RE = re.compile(
    r"^(?:response (?:complete|finished)|message sent|stopped|chatgpt is typing|loading)\b[:：]?",
    re.IGNORECASE,
)
YOU_SAID = "You said:"
CHATGPT_SAID = "ChatGPT said:"


def is_chrome_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return True
    if stripped in CHROME_LINES:
        return True
    if TIMESTAMP_RE.match(stripped):
        return True
    if ANNOUNCEMENT_RE.match(stripped):
        return True
    return False


def transcript_text(target: Target, *, clean: bool = True) -> str:
    """Read the sidebar's visible text in tree order, dropping interface chrome."""
    nodes = collect(target.document, 16)
    lines: list[str] = []
    for _depth, node in nodes:
        try:
            if node.ControlTypeName not in ("TextControl", "EditControl"):
                continue
            name = (node.Name or "").strip()
            if not name:
                continue
            if clean:
                if is_chrome_line(name):
                    continue
            if lines and lines[-1] == name:
                continue
            lines.append(name)
        except Exception:
            continue
    return "\n".join(lines)


def reply_count(text: str) -> int:
    """How many assistant messages the transcript currently shows."""
    return text.count(CHATGPT_SAID)


def extract_reply(text: str) -> str:
    """The most recent assistant message, without the speaker label or trailing chrome."""
    if CHATGPT_SAID not in text:
        return ""
    tail = text.rsplit(CHATGPT_SAID, 1)[1]
    kept: list[str] = []
    for line in tail.split("\n"):
        stripped = line.strip()
        if is_chrome_line(stripped) or stripped in (YOU_SAID, CHATGPT_SAID):
            continue
        kept.append(stripped)
    return "\n".join(kept).strip()


def wait_for_reply(target: Target, *, timeout_s: float, settle_s: float = 3.0,
                   min_wait_s: float = 2.0, poll_s: float = 0.6) -> str:
    """Poll the sidebar until a new assistant message has finished streaming.

    Completion is judged on stability plus an assistant marker: the transcript must
    contain a *new* ``ChatGPT said:`` block whose text has stopped changing.
    """
    before = transcript_text(target)
    before_count = reply_count(before)

    started = time.monotonic()
    deadline = started + timeout_s
    last = before
    stable_since = started

    while time.monotonic() < deadline:
        time.sleep(poll_s)
        current = transcript_text(target)
        if current != last:
            last = current
            stable_since = time.monotonic()
            continue
        if time.monotonic() - started < min_wait_s:
            continue
        if reply_count(current) <= before_count:
            continue
        reply = extract_reply(current)
        if not reply:
            continue
        if time.monotonic() - stable_since >= settle_s:
            return reply

    reply = extract_reply(last)
    if reply and reply_count(last) > before_count:
        return reply + "\n[note: still streaming when the timeout expired]"
    return "<no assistant reply detected before the timeout>"


# ==============================================================================
# Commands
# ==============================================================================
def cmd_find(args: argparse.Namespace) -> int:
    target = locate_sidebar()
    print(f"edge window     : hwnd={target.window.NativeWindowHandle} {target.window.Name[:60]!r}")
    print(f"sidebar pane    : {target.sidebar.Name!r}")
    print(f"document        : {target.document.Name!r}")
    print(f"composer rect   : {target.composer_rect}  center={target.center} width={target.width}")
    print(f"composer value  : {composer_text(target)!r}")
    print(f"engine          : {HUMANIZED_ENGINE}")
    return 0


def cmd_dump(args: argparse.Namespace) -> int:
    target = locate_sidebar()
    for depth, node in collect(target.document, args.depth):
        try:
            r = node.BoundingRectangle
            print(
                "{indent}{ctype:<16} [{l},{t},{rr},{b}] {w}x{h}  {name!r}".format(
                    indent="  " * depth,
                    ctype=node.ControlTypeName,
                    l=r.left, t=r.top, rr=r.right, b=r.bottom,
                    w=r.width(), h=r.height(),
                    name=(node.Name or "").replace("\n", " ⏎ ")[:80],
                )
            )
        except Exception:
            continue
    return 0


def cmd_read(args: argparse.Namespace) -> int:
    target = locate_sidebar()
    print(transcript_text(target))
    return 0


def focus_is_composer(target: Target) -> bool:
    """True when the keyboard focus sits on the sidebar's composer.

    Checked after clicking and before typing: if the click missed, the keys would
    land in whatever window does have focus, which is never acceptable.
    """
    try:
        focused = auto.GetFocusedControl()
    except Exception:
        return False
    if focused is None:
        return False
    try:
        if focused.ControlTypeName == "EditControl":
            a, b = focused.BoundingRectangle, target.composer.BoundingRectangle
            if abs(a.left - b.left) <= 4 and abs(a.top - b.top) <= 4:
                return True
            # A child of the composer (Chromium nests a text area inside it).
            if (b.left - 4) <= a.left and (b.top - 4) <= a.top and a.right <= (b.right + 4):
                return True
        # Fall back to walking up: is the composer among its ancestors?
        node = focused
        for _ in range(8):
            node = node.GetParentControl()
            if node is None:
                break
            if node.ControlTypeName == "EditControl" and node.Name == target.composer.Name:
                return True
    except Exception:
        return False
    return False


def click_composer(target: Target, emitter: Emitter, *, attempts: int = 3) -> bool:
    """Move onto the composer and click until it actually holds focus."""
    for attempt in range(1, attempts + 1):
        emitter.move_to(*target.focus_point)
        time.sleep(0.12)
        emitter.click()
        for _ in range(8):
            time.sleep(0.15)
            if focus_is_composer(target):
                print(f"composer focused after click #{attempt}")
                return True
        print(f"click #{attempt} did not focus the composer; retrying")
    return False


def find_button(target: Target, name: str):
    """Find a button by its accessible name anywhere inside the sidebar."""
    return find_descendant(
        target.sidebar,
        lambda n: n.ControlTypeName == "ButtonControl" and (n.Name or "") == name,
        max_depth=20,
    )


def button_center(button) -> tuple[float, float]:
    r = button.BoundingRectangle
    return ((r.left + r.right) / 2, (r.top + r.bottom) / 2)


def click_at(emitter: Emitter, point: tuple[float, float], *, settle_s: float = 0.6) -> None:
    emitter.move_to(*point)
    time.sleep(0.1)
    emitter.click()
    time.sleep(settle_s)


def sidebar_node_names(target: Target) -> set[str]:
    return {(n.Name or "").strip() for _d, n in collect(target.sidebar, 20) if (n.Name or "").strip()}


def cmd_new_chat(args: argparse.Namespace) -> int:
    """Click the sidebar's 'New chat' control so a fresh thread gets the material."""
    target = locate_sidebar()
    start = Emitter.cursor_pos()
    emitter = Emitter()
    try:
        button = find_button(target, args.name)
        if button is None:
            print(f"no button named {args.name!r} in the sidebar; leaving the chat as it is")
            return 1
        center = button_center(button)
        print(f"clicking {args.name!r} at ({center[0]:.0f},{center[1]:.0f})")
        click_at(emitter, center, settle_s=1.5)
        print("new chat requested")
        return 0
    finally:
        try:
            emitter.move_to(*start)
        except Exception:
            pass


@dataclass
class AttachResult:
    accepted: bool
    new_names: list[str]
    screenshot: str | None


def attach_from_clipboard(target: Target, emitter: Emitter, *, wait_s: float = 90.0) -> AttachResult:
    """Paste the clipboard into the composer, then wait for attachment chips to appear."""
    before = sidebar_node_names(target)
    if not click_composer(target, emitter):
        raise InputAborted("could not focus the composer before pasting attachments")
    emitter.paste()
    print("pasted from clipboard; waiting for the attachments to register")

    deadline = time.monotonic() + wait_s
    added: list[str] = []
    while time.monotonic() < deadline:
        time.sleep(1.5)
        added = sorted(sidebar_node_names(target) - before)
        joined = " | ".join(added).lower()
        if any(k in joined for k in (".png", ".jpg", "image", "remove", "attachment", "upload")):
            break

    shot = None
    try:
        from PIL import ImageGrab

        r = target.sidebar.BoundingRectangle
        path = STATE_DIR / "sidebar-after-attach.png"
        ImageGrab.grab().crop((r.left, r.top, r.right, r.bottom)).save(path)
        shot = str(path)
    except Exception as exc:  # pragma: no cover - screenshot is diagnostic only
        print(f"screenshot failed: {exc}")

    return AttachResult(accepted=bool(added), new_names=added, screenshot=shot)


def cmd_attach(args: argparse.Namespace) -> int:
    target = locate_sidebar()
    start = Emitter.cursor_pos()
    emitter = Emitter(InputLimits(max_seconds=args.max_seconds))
    try:
        result = attach_from_clipboard(target, emitter, wait_s=args.wait)
        print(f"attachment evidence: {len(result.new_names)} new node name(s)")
        for name in result.new_names[:25]:
            print(f"  - {name}")
        if result.screenshot:
            print(f"screenshot: {result.screenshot}")
        if not result.accepted:
            print("WARNING: nothing attachment-shaped appeared; check the screenshot")
            return 1
        return 0
    except InputAborted as exc:
        print(f"ABORTED: {exc}")
        return 2
    finally:
        try:
            emitter.move_to(*start)
        except Exception:
            pass


def resolve_prompt(args: argparse.Namespace) -> str:
    """The prompt text, either inline or read from a UTF-8 file.

    A file is the safer channel for long non-ASCII prompts: it sidesteps shell
    quoting and any console code page between the caller and this process.
    """
    prompt_file = getattr(args, "prompt_file", None)
    if prompt_file:
        text = Path(prompt_file).read_text(encoding="utf-8")
        print(f"prompt loaded from {prompt_file}: {len(text)} chars")
        return text.rstrip()  # a trailing newline must never become a stray Enter
    return args.text or ""


def cmd_click(args: argparse.Namespace) -> int:
    """Click one named button inside the sidebar, whatever it is."""
    target = locate_sidebar()
    start = Emitter.cursor_pos()
    emitter = Emitter()
    try:
        button = find_button(target, args.name)
        if button is None:
            names = sorted({(n.Name or "") for d, n in collect(target.sidebar, 20)
                            if n.ControlTypeName == "ButtonControl" and (n.Name or "")})
            print(f"no button named {args.name!r}; buttons present: {names}")
            return 1
        center = button_center(button)
        print(f"clicking {args.name!r} at ({center[0]:.0f},{center[1]:.0f})")
        click_at(emitter, center, settle_s=args.settle)
        return 0
    finally:
        try:
            emitter.move_to(*start)
        except Exception:
            pass


def cmd_type_keys(args: argparse.Namespace) -> int:
    """Type into whatever currently has focus, optionally pressing Enter.

    Used for native dialogs (file pickers) that are not part of the sidebar's
    accessibility tree this tool targets.
    """
    text = resolve_prompt(args)
    emitter = Emitter(InputLimits(max_seconds=args.max_seconds))
    type_text_plan(emitter, text, seed=args.seed)
    if args.enter:
        time.sleep(0.2)
        emitter.key_vk(VK_RETURN)
    print(f"typed {len(text)} chars" + (" + Enter" if args.enter else ""))
    return 0


def find_top_window(*, class_name: str | None = None,
                    name_contains: tuple[str, ...] = ()):
    """Find a visible top-level window, optionally by class or a title fragment."""
    for candidate in auto.GetRootControl().GetChildren():
        try:
            if class_name is not None and (candidate.ClassName or "") != class_name:
                continue
            if name_contains and not any(
                k.lower() in (candidate.Name or "").lower() for k in name_contains
            ):
                continue
            if candidate.BoundingRectangle.width() <= 0:
                continue
            return candidate
        except Exception:
            continue
    return None


user32.FindWindowW.restype = wintypes.HWND
user32.FindWindowW.argtypes = (wintypes.LPCWSTR, wintypes.LPCWSTR)
user32.IsWindowVisible.argtypes = (wintypes.HWND,)


def find_dialog(control_type: str = "#32770"):
    """Find a native dialog by Win32 window class.

    UI Automation's top-level enumeration does not reliably surface an *owned
    modal* dialog — it can be missing from the tree while plainly on screen,
    which is exactly how a file dialog ends up invisible to this tool.
    ``FindWindowW`` asks Win32 instead, and the handle is wrapped for UIA use.
    """
    for title in ("打开", "Open", None):
        handle = user32.FindWindowW(control_type, title)
        if not handle or not user32.IsWindowVisible(handle):
            continue
        try:
            return auto.ControlFromHandle(handle)
        except Exception:
            continue
    return None


def dialog_file_field(dialog):
    """The file-name edit box of a standard file dialog (AutomationId 1148 = edt1)."""
    edits = [n for _d, n in collect(dialog, 8) if n.ControlTypeName == "EditControl"]
    for node in edits:
        try:
            if (node.AutomationId or "") == "1148":
                return node
        except Exception:
            continue
    return edits[0] if edits else None


def fill_file_dialog(dialog, paths: list[Path], emitter: Emitter) -> None:
    """Click the file-name box, type the quoted paths, and accept the dialog."""
    field = dialog_file_field(dialog)
    if field is None:
        raise InputAborted("the file dialog has no file-name field")
    print(f"file-name field at {button_center(field)}; typing {len(paths)} path(s)")
    click_at(emitter, button_center(field), settle_s=0.3)
    emitter.select_all()
    # Quoted, space-separated paths open every file in one go.
    type_text_plan(emitter, " ".join(f'"{p}"' for p in paths), humanize=False)
    time.sleep(0.5)
    emitter.key_vk(VK_RETURN)

    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if find_dialog() is None:
            print("dialog closed")
            return
        time.sleep(0.4)
    raise InputAborted("the file dialog did not close after Enter")


def cmd_fill_dialog(args: argparse.Namespace) -> int:
    """Fill an already-open file dialog. Useful when one is left over from an earlier run."""
    paths = [Path(p).expanduser().resolve() for p in args.paths]
    emitter = Emitter(InputLimits(max_seconds=args.max_seconds))
    dialog = find_dialog()
    if dialog is None:
        print("no file dialog is open")
        return 1
    print(f"filling dialog: {dialog.Name!r}")
    try:
        fill_file_dialog(dialog, paths, emitter)
        return 0
    except InputAborted as exc:
        print(f"ABORTED: {exc}")
        return 2


def wait_for_attachments(target: Target, before: set[str], *, wait_s: float,
                         expect: int | None = None) -> AttachResult:
    """Poll the sidebar until the expected number of attachments is present."""
    deadline = time.monotonic() + wait_s
    added: list[str] = []
    while time.monotonic() < deadline:
        time.sleep(1.0)
        added = sorted(sidebar_node_names(target) - before)
        if expect is not None and attached_count(target) >= expect:
            break
        joined = " | ".join(added).lower()
        if expect is None and any(
            k in joined for k in (".png", ".jpg", "image", "remove", "attachment", "upload")
        ):
            break
    shot = None
    try:
        from PIL import ImageGrab

        r = target.sidebar.BoundingRectangle
        path = STATE_DIR / "sidebar-after-attach.png"
        ImageGrab.grab().crop((r.left, r.top, r.right, r.bottom)).save(path)
        shot = str(path)
    except Exception as exc:  # pragma: no cover - diagnostic only
        print(f"screenshot failed: {exc}")
    return AttachResult(accepted=bool(added), new_names=added, screenshot=shot)


def report_attachment_result(result: AttachResult) -> int:
    print(f"attachment evidence: {len(result.new_names)} new node name(s)")
    for name in result.new_names[:25]:
        print(f"  - {name}")
    if result.screenshot:
        print(f"screenshot: {result.screenshot}")
    if not result.accepted:
        print("WARNING: no attachment-shaped node appeared; inspect the screenshot")
        return 1
    return 0


def chunk_paths(paths: list[Path], limit: int) -> list[list[Path]]:
    """Split paths into groups whose quoted, space-joined text fits the dialog.

    A standard Windows file dialog's file-name field truncates somewhere around
    256 characters, and it does so silently: six 64-character quoted paths were
    cut down to three valid files with no error shown. The group size is derived
    from the real path lengths instead of assumed.
    """
    chunks: list[list[Path]] = []
    current: list[Path] = []
    size = 0
    for path in paths:
        cost = len(str(path)) + 3  # two quotes plus the separating space
        if current and size + cost > limit:
            chunks.append(current)
            current, size = [], 0
        current.append(path)
        size += cost
    if current:
        chunks.append(current)
    return chunks


def attached_count(target: Target) -> int:
    """How many attachment thumbnails the composer currently shows."""
    return sum(
        1 for _d, n in collect(target.sidebar, 20) if (n.Name or "").startswith("Remove ")
    )


def cmd_attach_files(args: argparse.Namespace) -> int:
    """Attach real files through the UI: add button, menu item, native dialog, Enter.

    The whole chain runs in this one process on purpose: the file dialog is a modal
    owned by the browser and lives outside the accessibility tree this tool reads,
    so handing control back to the shell between steps loses it. Paths go up in
    size-bounded batches because the dialog's file-name field truncates long lists.
    """
    paths = [Path(p).expanduser().resolve() for p in args.paths]
    missing = [str(p) for p in paths if not p.is_file()]
    if missing:
        print("missing file(s):\n  " + "\n  ".join(missing))
        return 1
    if not paths:
        print("no files given")
        return 1

    target = locate_sidebar()
    start = Emitter.cursor_pos()
    before = sidebar_node_names(target)
    already = attached_count(target)
    emitter = Emitter(InputLimits(max_seconds=args.max_seconds, max_distance_px=400000))

    chunks = chunk_paths(paths, args.chunk_chars)
    print(f"{len(paths)} file(s) in {len(chunks)} batch(es); "
          f"composer already holds {already} attachment(s)")

    try:
        for index, chunk in enumerate(chunks, 1):
            print(f"--- batch {index}/{len(chunks)}: {len(chunk)} file(s)")

            # A dialog left open by an earlier run owns the screen and swallows
            # every click meant for the sidebar, so reuse it rather than clicking blind.
            dialog = find_dialog()
            if dialog is not None:
                print(f"a file dialog is already open ({dialog.Name!r}); filling it")
            else:
                item = find_button(target, args.menu_item)
                if item is None:
                    plus = find_button(target, "Add files and more")
                    if plus is None:
                        raise InputAborted("the sidebar has no 'Add files and more' button")
                    print(f"clicking the add button at {button_center(plus)}")
                    click_at(emitter, button_center(plus), settle_s=1.0)
                    for _ in range(32):
                        item = find_button(target, args.menu_item)
                        if item is not None:
                            break
                        time.sleep(0.25)
                if item is None:
                    raise InputAborted(f"menu item {args.menu_item!r} never appeared")
                print(f"clicking {args.menu_item!r} at {button_center(item)}")
                click_at(emitter, button_center(item), settle_s=1.5)

                dialog = None
                deadline = time.monotonic() + 20
                while time.monotonic() < deadline:
                    dialog = find_dialog()
                    if dialog is not None:
                        break
                    time.sleep(0.3)
                if dialog is None:
                    raise InputAborted("the file dialog never appeared")

            fill_file_dialog(dialog, chunk, emitter)
            time.sleep(1.0)
            print(f"    composer now holds {attached_count(target)} attachment(s)")

        result = wait_for_attachments(target, before, wait_s=args.wait,
                                      expect=len(paths) + already)
        return report_attachment_result(result)
    except InputAborted as exc:
        print(f"ABORTED: {exc}")
        return 2
    finally:
        try:
            emitter.move_to(*start)
        except Exception:
            pass


def normalize_for_compare(text: str) -> str:
    """Normalise a composer value and a prompt so they can be compared.

    Chromium's EditControl returns ``\\r\\n`` for the line breaks the typing model
    inserts as ``\\n``, so a raw substring test fails on any multi-line prompt even
    though the text is exactly right.
    """
    flat = text.replace("\r\n", "\n").replace("\r", "\n")
    return "\n".join(line.strip() for line in flat.split("\n") if line.strip())


def cmd_reset_composer(args: argparse.Namespace) -> int:
    """Return the composer to empty: drop every attachment, then clear the text.

    Recovery path for a composer left dirty by an interrupted or refused run.
    """
    start = Emitter.cursor_pos()
    emitter = Emitter(InputLimits(max_seconds=args.max_seconds))
    try:
        for _ in range(args.max_items):
            target = locate_sidebar()
            buttons = [
                n for _d, n in collect(target.sidebar, 22)
                if n.ControlTypeName == "ButtonControl"
                and (n.Name or "").startswith("Remove ")
            ]
            if not buttons:
                break
            button = buttons[0]
            print(f"removing {(button.Name or '')[:50]!r}")
            click_at(emitter, button_center(button), settle_s=0.6)

        target = locate_sidebar()
        click_at(emitter, target.focus_point, settle_s=0.4)
        emitter.select_all()
        emitter.key_vk(VK_BACK)
        time.sleep(0.6)

        target = locate_sidebar()
        print(f"attachments now: {attached_count(target)}")
        print(f"composer text now: {composer_text(target)[:60]!r}")
        return 0
    finally:
        try:
            emitter.move_to(*start)
        except Exception:
            pass


def clipboard_text() -> str:
    """Read the Windows clipboard as text.

    Done through PowerShell rather than a Python clipboard binding: the base
    interpreter has no win32clipboard, and one shell call is cheaper than adding a
    dependency for a two-way copy.
    """
    import subprocess

    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command", "Get-Clipboard -Raw"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if result.returncode != 0:
        raise RuntimeError(f"Get-Clipboard failed: {result.stderr.strip()}")
    return result.stdout


def cmd_paste(args: argparse.Namespace) -> int:
    """Paste the clipboard into the composer and verify what landed.

    Pasting rather than typing sidesteps the whole family of composer traps: no
    newline can be mistaken for Enter, and no line-start pattern can be autoformatted
    into a list. It is also the only sane way to deliver a few thousand characters.
    """
    target = locate_sidebar()
    start = Emitter.cursor_pos()
    emitter = Emitter(InputLimits(max_seconds=args.max_seconds))
    expected = None
    if args.expect_file:
        expected = Path(args.expect_file).read_text(encoding="utf-8").rstrip()
    try:
        if not click_composer(target, emitter):
            raise InputAborted("could not focus the composer before pasting")
        emitter.paste()
        time.sleep(args.settle)
        typed = composer_text(target)
        print(f"composer holds {len(typed)} chars and {attached_count(target)} attachment(s)")
        if expected is not None:
            if normalize_for_compare(expected) not in normalize_for_compare(typed):
                raise InputAborted("the pasted text does not match the expected content")
            print(f"pasted content verified against {args.expect_file} "
                  f"({len(expected)} chars expected)")
        if args.send:
            emitter.key_vk(VK_RETURN)
            print("sent (Enter)")
            reply = wait_for_reply(target, timeout_s=args.reply_timeout, settle_s=args.settle_reply)
            print("\n=== reply ===\n" + reply)
        return 0
    except InputAborted as exc:
        print(f"ABORTED: {exc}")
        return 2
    finally:
        try:
            emitter.move_to(*start)
        except Exception:
            pass


def top_level_handles() -> dict[int, str]:
    """Every visible top-level window, as {hwnd: class name}.

    Used to notice native popups, which are invisible to the page's accessibility tree.
    """
    found: dict[int, str] = {}
    for window in auto.GetRootControl().GetChildren():
        try:
            handle = window.NativeWindowHandle
            if handle:
                found[handle] = window.ClassName or ""
        except Exception:
            continue
    return found


def cmd_right_click(args: argparse.Namespace) -> int:
    """Right-click in the composer and report whether a context menu appeared.

    A real button-2 press, verified by the accessibility tree rather than by assuming
    the menu opened: the node-name set is compared before and after.
    """
    target = locate_sidebar()
    start = Emitter.cursor_pos()
    emitter = Emitter(InputLimits(max_seconds=args.max_seconds))
    try:
        before = top_level_handles()
        point = target.focus_point
        emitter.move_to(*point)
        time.sleep(0.15)
        emitter.right_click()
        time.sleep(1.2)
        after = top_level_handles()
        # The page tree is NOT the right place to look: a browser context menu is a
        # native popup window (class #32768) that never enters the document's tree.
        menu = user32.FindWindowW("#32768", None)
        fresh = sorted(set(after) - set(before))
        if args.dismiss:
            emitter.press_esc()
            time.sleep(0.5)
        print(f"right-clicked at ({point[0]:.0f},{point[1]:.0f})")
        print(f"native menu window (#32768): {'present' if menu else 'absent'}")
        print(f"new top-level windows: {len(fresh)}")
        for handle in fresh:
            print(f"  - hwnd={handle} cls={(after[handle] or '')[:30]!r}")
        return 0 if (menu or fresh) else 1
    finally:
        try:
            emitter.move_to(*start)
        except Exception:
            pass


def cmd_send(args: argparse.Namespace) -> int:
    """Send a message the composer already holds, re-verifying its text first.

    Exists because a guard that refuses to press Enter (correctly) leaves the
    message sitting in the composer; retyping it would be wasteful and could
    duplicate the text.
    """
    target = locate_sidebar()
    start = Emitter.cursor_pos()
    emitter = Emitter(InputLimits(max_seconds=args.max_seconds))
    try:
        typed = composer_text(target)
        print(f"composer holds {len(typed)} chars and {attached_count(target)} attachment(s)")
        if args.expect_file:
            expected = Path(args.expect_file).read_text(encoding="utf-8").rstrip()
            if normalize_for_compare(expected) not in normalize_for_compare(typed):
                raise InputAborted("the composer does not hold the expected text; not sending")
            print("composer text matches the expected prompt")
        if not click_composer(target, emitter):
            raise InputAborted("could not focus the composer before sending")
        emitter.key_vk(VK_RETURN)
        print("sent (Enter)")
        reply = wait_for_reply(target, timeout_s=args.reply_timeout, settle_s=args.settle)
        print("\n=== reply ===\n" + reply)
        return 0
    except InputAborted as exc:
        print(f"ABORTED: {exc}")
        return 2
    finally:
        try:
            emitter.move_to(*start)
        except Exception:
            pass


def cmd_ask(args: argparse.Namespace) -> int:
    text = resolve_prompt(args)
    if not text.strip():
        print("no prompt text given")
        return 1
    target = locate_sidebar()
    start = Emitter.cursor_pos()
    motion = build_motion(start, target.focus_point, target.width, seed=args.seed)

    print(f"engine={motion.source} move_samples={len(motion.moves)} "
          f"cursor={start} -> composer={target.focus_point}")

    if args.dry_run:
        preview = build_plan(text, start, target.focus_point, target.width, seed=args.seed)
        print(f"dry run: {len(preview.moves)} move samples, {len(preview.keys)} keystrokes planned; "
              "nothing emitted")
        return 0

    emitter = Emitter(InputLimits(max_seconds=args.max_seconds))
    try:
        # Phase 1: humanized approach to the composer.
        emitter.move_to(*start)
        time.sleep(0.1)
        run_plan(emitter, motion, emit_click=False)

        # Phase 2: click until the composer genuinely holds keyboard focus.
        if not click_composer(target, emitter):
            raise InputAborted(
                "could not focus the sidebar composer; refusing to type so keystrokes "
                "cannot land in another window"
            )

        # Phase 3: only now is typing safe.
        type_text_plan(emitter, text)

        time.sleep(0.3)
        typed = composer_text(target)
        print(f"after typing, composer holds {len(typed)} chars: {typed[:60]!r}")
        if normalize_for_compare(text) not in normalize_for_compare(typed):
            raise InputAborted(
                f"composer does not contain the intended text (holds {typed[:40]!r}); "
                "not pressing Enter"
            )

        # Phase 4: send and read.
        emitter.key_vk(VK_RETURN)
        print("sent (Enter)")

        reply = wait_for_reply(target, timeout_s=args.reply_timeout, settle_s=args.settle)
        print("\n=== reply ===\n" + reply)
        return 0
    except InputAborted as exc:
        print(f"ABORTED: {exc}")
        return 2
    finally:
        try:
            emitter.move_to(*start)
        except Exception:
            pass


def type_text_plan(emitter: Emitter, text: str, *, seed: int | None = None,
                   humanize: bool = True, newline_sends: bool = False) -> None:
    """Type ``text`` with timed key intervals.

    ``humanize=True`` uses the fitted typing model. Dialog fields (a file-name box)
    take ``humanize=False``: a path is not prose, and waiting 30 s to type one is
    time the user cannot use their own machine.

    ``newline_sends`` decides what a newline means. In a chat composer Enter sends
    the message, so a multi-paragraph prompt must type **Shift+Enter** instead —
    otherwise every line break fires off a separate partial message, which is
    exactly what a four-paragraph brief did before this parameter existed.
    """
    rng = random.Random(seed if seed is not None else time.time_ns() & 0xFFFFFFFF)
    if humanize and plan_typing is not None:
        params = TypingParams()
        if hasattr(params, "typo_rate"):
            params.typo_rate = 0.0
        steps = plan_typing(text, params, rng).steps
        waits = [(step.key, step.t_down) for step in steps]
    else:
        t = 0.0
        waits = []
        for i, ch in enumerate(text):
            t += 0.012 if not humanize else rng.lognormvariate(-3.2, 0.35)
            waits.append((ch, t))

    t0 = time.monotonic()
    for ch, when in waits:
        wait = when - (time.monotonic() - t0)
        if wait > 0:
            time.sleep(wait)
        if ch == "Backspace":
            emitter.key_vk(VK_BACK)
        elif ch in ("\n", "\r"):
            if newline_sends:
                emitter.key_vk(VK_RETURN)
            else:
                emitter.key_shifted(VK_RETURN)
        elif ch == "Enter":
            emitter.key_vk(VK_RETURN)
        elif len(ch) == 1:
            emitter.key_unicode(ch)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("find", help="locate the sidebar and its composer").set_defaults(func=cmd_find)

    p_dump = sub.add_parser("dump", help="print the sidebar's UIA subtree")
    p_dump.add_argument("--depth", type=int, default=6)
    p_dump.set_defaults(func=cmd_dump)

    sub.add_parser("read", help="print the current transcript text").set_defaults(func=cmd_read)

    p_ask = sub.add_parser("ask", help="click, type, send, and read the reply")
    p_ask.add_argument("text", nargs="?", default="")
    p_ask.add_argument("--prompt-file", default=None,
                       help="read the prompt from a UTF-8 file (safer for long non-ASCII text)")
    p_ask.add_argument("--dry-run", action="store_true")
    p_ask.add_argument("--seed", type=int, default=None)
    p_ask.add_argument("--max-seconds", type=float, default=180.0)
    p_ask.add_argument("--reply-timeout", type=float, default=180.0)
    p_ask.add_argument("--settle", type=float, default=3.0,
                       help="seconds of unchanged transcript before the reply counts as finished")
    p_ask.set_defaults(func=cmd_ask)

    p_new = sub.add_parser("new-chat", help="click the sidebar's New chat control")
    p_new.add_argument("--name", default="New chat")
    p_new.set_defaults(func=cmd_new_chat)

    p_reset = sub.add_parser("reset-composer", help="drop attachments and clear the composer text")
    p_reset.add_argument("--max-items", type=int, default=40)
    p_reset.add_argument("--max-seconds", type=float, default=180.0)
    p_reset.set_defaults(func=cmd_reset_composer)

    p_paste = sub.add_parser("paste", help="paste the clipboard into the composer (Ctrl+V)")
    p_paste.add_argument("--expect-file", default=None)
    p_paste.add_argument("--send", action="store_true")
    p_paste.add_argument("--settle", type=float, default=1.0)
    p_paste.add_argument("--reply-timeout", type=float, default=540.0)
    p_paste.add_argument("--settle-reply", type=float, default=5.0)
    p_paste.add_argument("--max-seconds", type=float, default=200.0)
    p_paste.set_defaults(func=cmd_paste)

    p_rclick = sub.add_parser("right-click", help="right-click in the composer and report the menu")
    p_rclick.add_argument("--dismiss", action="store_true", default=True)
    p_rclick.add_argument("--max-seconds", type=float, default=120.0)
    p_rclick.set_defaults(func=cmd_right_click)

    p_send = sub.add_parser("send", help="send what the composer already holds")
    p_send.add_argument("--expect-file", default=None,
                        help="verify the composer holds this prompt before pressing Enter")
    p_send.add_argument("--reply-timeout", type=float, default=540.0)
    p_send.add_argument("--settle", type=float, default=5.0)
    p_send.add_argument("--max-seconds", type=float, default=120.0)
    p_send.set_defaults(func=cmd_send)

    p_attach = sub.add_parser("attach", help="paste the clipboard (files/images) into the composer")
    p_attach.add_argument("--wait", type=float, default=90.0)
    p_attach.add_argument("--max-seconds", type=float, default=120.0)
    p_attach.set_defaults(func=cmd_attach)

    p_files = sub.add_parser(
        "attach-files",
        help="attach files through the real UI (add button, menu, file dialog)",
    )
    p_files.add_argument("paths", nargs="+")
    p_files.add_argument("--menu-item", default="Files and folders")
    p_files.add_argument("--chunk-chars", type=int, default=200,
                         help="max characters per dialog batch (the field truncates near 256)")
    p_files.add_argument("--wait", type=float, default=120.0)
    p_files.add_argument("--max-seconds", type=float, default=300.0)
    p_files.set_defaults(func=cmd_attach_files)

    p_fill = sub.add_parser("fill-dialog", help="fill an already-open native file dialog")
    p_fill.add_argument("paths", nargs="+")
    p_fill.add_argument("--max-seconds", type=float, default=300.0)
    p_fill.set_defaults(func=cmd_fill_dialog)

    p_click = sub.add_parser("click", help="click a named button inside the sidebar")
    p_click.add_argument("name")
    p_click.add_argument("--settle", type=float, default=0.8)
    p_click.set_defaults(func=cmd_click)

    p_keys = sub.add_parser("type-keys", help="type into the focused control (native dialogs)")
    p_keys.add_argument("text", nargs="?", default="")
    p_keys.add_argument("--prompt-file", default=None)
    p_keys.add_argument("--enter", action="store_true")
    p_keys.add_argument("--seed", type=int, default=None)
    p_keys.add_argument("--max-seconds", type=float, default=300.0)
    p_keys.set_defaults(func=cmd_type_keys)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
