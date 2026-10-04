# Guide — architecture, installation and command reference

The plugin's manual. For the *why* behind each design choice read
[LESSONS.md](LESSONS.md); for one complete run read [EXAMPLE.md](EXAMPLE.md).

---

## 1. What problem it solves

A DSH session can call models through adapters, but a model that lives *only* behind a browser UI —
ChatGPT with a subscription, on the surfaces that have no API — is out of reach. This bridge makes
that surface reachable by driving it as a human would, and by reading its answer out of the
accessibility tree, so any DSH model can hold a conversation with it.

It is deliberately narrow: **one** target surface (the ChatGPT sidebar docked in Edge), **one**
input path (`SendInput`), **one** reading path (UI Automation). Narrowness is what makes it reliable
enough to assert on.

## 2. Architecture

```
                ┌──────────────────────────────────────────────────────────┐
                │  core.py                                                 │
                │                                                          │
  aim    ──────►│  locate_sidebar()  ── UIA: Edge window → SidePaneRoot     │
                │                       Container → DocumentControl →      │
                │                       EditControl (the composer)          │
  act    ──────►│  Emitter           ── SendInput: absolute mouse, click,   │
                │                       Unicode keys, Ctrl/Shift combos    │
  time   ──────►│  build_motion()    ── humanised trajectory (or fallback)  │
                │  type_text_plan()  ── humanised key intervals             │
  read   ──────►│  transcript_text() ── UIA text nodes, chrome filtered     │
                │  extract_reply()   ── text after the last "ChatGPT said:" │
  verify ──────►│  focus_is_composer(), normalize_for_compare()             │
                └──────────────────────────────────────────────────────────┘
```

### Targeting

| Element | How it is found | Observed geometry |
|---|---|---|
| Edge window | top-level window whose title contains `Edge` | — |
| Sidebar pane | `ClassName == "SidePaneRootContainer"` | `[1533,79]-[1920,1029]`, 387×950 |
| Composer | `EditControl` under the pane, searched to depth 20 | `[1554,928,1896,972]` (empty) |
| Attachment chips | buttons named `Remove <file>` | 80×80 each, in a scrolling row |
| Add button | `ButtonControl` named `Add files and more` | 28×28 |
| File dialog | Win32 `FindWindowW("#32770")`, **not** the UIA tree | — |

Two facts worth keeping: Chromium builds the accessibility tree **lazily** (the first query returns
frame chrome only, so the lookup retries), and the composer is **~15 levels deep**, which is why
naive depth-12 searches find nothing.

### Input

`Emitter` assembles `INPUT` structures for `SendInput`:

- mouse: `MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK`, coordinates normalised
  to 0–65535 over the virtual screen;
- keyboard: `KEYEVENTF_UNICODE` scan codes for characters (any script), virtual-key codes for
  Enter/Backspace/Escape, and explicit Ctrl/Shift wrappers for combinations.

The process is declared **per-monitor DPI aware** so that UI Automation rectangles, screenshots and
click coordinates all agree.

### Timing

Trajectories and key intervals come from the sibling `humanized-input-lab` project when it is
importable (`hilab.motion`, `hilab.typing`); otherwise a built-in minimum-jerk path and log-normal
intervals are used. Deliberate typo injection is switched **off**: a corrupted prompt is not useful
realism here. Point `HILAB_ROOT` at the project to use the fitted model.

### Reading

The reply is the text after the **last** `ChatGPT said:` marker, with these removed: chat chrome
(`Do anything`, `New chat`, `No chats in progress`, `Thinking`, `Copy`, …), timestamps, and
Chromium's ARIA announcements (`Response complete: …`). Completion is judged by requiring a **new**
assistant block whose text has stopped changing for `--settle` seconds — "the text changed" alone is
satisfied by the placeholder state `Thinking`.

## 3. Installation

```powershell
pip install -e .            # from a clone; needs uiautomation + Pillow
$env:HILAB_ROOT = "C:\path\to\humanized-input-lab"   # optional: fitted timing model
```

Environment variables:

| Variable | Default | Purpose |
|---|---|---|
| `HILAB_ROOT` | `<source parent>/humanized-input-lab` | where the humanised timing model lives |
| `DSH_BRIDGE_STATE` | the package directory | where diagnostic screenshots are written |
| `PI_AI_DIST` | — | unused here; present in the sibling Codex bridge |

## 4. Command reference

| Command | Does | Writes |
|---|---|---|
| `find` | locate window, sidebar, document, composer | nothing |
| `dump [--depth N]` | print the sidebar's automation subtree | nothing |
| `read` | print the cleaned transcript | nothing |
| `ask [text] [--prompt-file F] [--reply-timeout S] [--settle S] [--max-seconds S] [--dry-run] [--seed N]` | aim, click, verify focus, type, verify text, Enter, read | nothing |
| `send --expect-file F` | press Enter on a message the composer already holds, after verifying it | nothing |
| `new-chat [--name N]` | click the sidebar's *New chat* control | nothing |
| `reset-composer` | remove every attachment, clear the text | nothing |
| `attach-files PATH... [--chunk-chars N] [--menu-item S]` | attach through the real UI | nothing |
| `attach [--wait S]` | paste the clipboard into the composer | nothing |
| `fill-dialog PATH...` | fill a file dialog that is already open | nothing |
| `click NAME` | click a named button in the sidebar | nothing |
| `type-keys [text] [--prompt-file F] [--enter]` | type into whatever has focus (native dialogs) | nothing |

Exit codes: `0` success, `1` precondition failed, `2` aborted safely (nothing was typed or sent).

## 5. Extending it to another surface

The reusable parts are `Emitter` (input), `collect`/`find_descendant` (tree walking),
`normalize_for_compare` (comparing a field against intent), and the `find_dialog` + `fill_file_dialog`
pair (native dialogs). A new surface needs, in order:

1. a locator for the window, the input control and the transcript container;
2. a completion signal specific to that surface;
3. a chrome filter for its transcript;
4. the two guards (focus before typing, content before committing), wired in.

## 6. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `sidebar found, but no composer EditControl appeared` | the accessibility tree is not built yet, or the pane is closed | open the ChatGPT sidebar; the lookup already retries — re-run |
| `ABORTED: could not focus the sidebar composer` | a click missed, or an overlay (image preview) is open | press Escape, re-run; the tool screenshots the pane on attachment paths |
| `ABORTED: composer does not contain the intended text` | newline splitting or list autoformatting | use `--prompt-file` with `视角——`-style labels, no `N. ` at line starts |
| attachment count < file count | the dialog's name field truncated | lower `--chunk-chars`, retry |
| reply reads `Thinking` | completion judged too early | raise `--settle` |
| the cursor is left somewhere odd | a run was interrupted | re-run; every run restores the cursor itself |
