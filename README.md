# dsh-chatgpt-bridge

**Let any model inside [DSH](https://github.com/deepseek-ai/deepseek-harness) talk to the ChatGPT that is already open in your browser — by moving a real mouse and typing real keys.**

[中文说明](README.zh.md) · [Worked example](docs/EXAMPLE.md) · [Lessons learned](docs/LESSONS.md)

---

## What this is

A bridge, not an API client. It drives the **ChatGPT sidebar docked in Microsoft Edge** the way a
person does: it aims with UI Automation, clicks with `SendInput`, types with `SendInput`, and reads
the answer back out of the accessibility tree. No API key. No JavaScript injection. No DevTools
protocol. No browser extension.

That makes it usable exactly where an API is not: your own logged-in session, your own subscription,
the model picker and modes you already have — including ChatGPT's file and image attachments.

```
  DSH model  ──►  skills + CLI  ──►  SendInput (real mouse/keyboard)  ──►  Edge sidebar (ChatGPT)
                        ▲                                                        │
                        └────────────  UI Automation tree (reads the reply)  ◄────┘
```

## Why it is built this way

| Layer | Choice | Reason |
|---|---|---|
| **Aim** | UI Automation on the Edge window | The sidebar exposes a `DocumentControl` and an `EditControl`, so targets are exact rectangles rather than template matches. No computer vision needed. |
| **Act** | Windows `SendInput` with `MOUSEEVENTF_ABSOLUTE \| VIRTUALDESK` and `KEYEVENTF_UNICODE` | Events reach the application the same way hardware does, and any script — CJK included — arrives intact without a clipboard round trip. |
| **Time** | A humanised input model | Minimum-jerk trajectories with overshoot and correction, log-normal inter-key intervals, instead of teleport-and-dump. |
| **Read** | The accessibility tree, not OCR | Deterministic text with no screenshot parsing, no clipboard, and no OCR language packs. |
| **Verify** | Assertions before every committing action | Focus is confirmed before typing; content is confirmed before pressing Enter. |

Everything above is *observed behaviour*, not aspiration: each choice exists because the alternatives
failed in practice. See [docs/LESSONS.md](docs/LESSONS.md).

## Quick start

Requirements: Windows, Microsoft Edge with the **ChatGPT sidebar open**, Python 3.11+, and the
`uiautomation` + `Pillow` packages in the interpreter you run this with.

```powershell
git clone https://github.com/Jxbbbbbyan/dsh-chatgpt-bridge
cd dsh-chatgpt-bridge
pip install -e .

dsh-chatgpt-bridge find            # locate the sidebar, its document and its composer
dsh-chatgpt-bridge read            # the current transcript, UI chrome removed
dsh-chatgpt-bridge ask "Reply with just the word: OK"
```

`ask` moves the cursor, clicks the composer, **verifies the composer actually holds focus**, types
the prompt, **verifies the composer holds the intended text**, presses Enter, waits for a new
assistant message to stop changing, and prints it.

Refusing to type or to send is a feature. Two guards exist because both failure modes happened:
a missed click would otherwise spray a prompt into whatever window did have focus, and a mangled
prompt would otherwise be sent.

## Attaching files and long screenshots

```powershell
dsh-chatgpt-bridge attach-files slices\slice-0*.png     # real UI: + → Files and folders → Open dialog
dsh-chatgpt-bridge ask --prompt-file brief.txt          # prompts read from a UTF-8 file
```

A screenshot taller than about 2000 px is **downscaled by the chat UI until its text cannot be
read**. `dsh_chatgpt_bridge.slicer` cuts it into overlapping, still-legible slices:

```powershell
python -m dsh_chatgpt_bridge.slicer long-screenshot.jpg slices
```

Six 640×1700 slices from one 640×8260 screenshot, attached in length-bounded batches because the
file dialog's name field truncates silently near 256 characters. The full procedure, with the four
rules that make it reliable, is in [docs/LONG-SCREENSHOTS.md](docs/LONG-SCREENSHOTS.md).

## Safety model

Real input means the human cannot use their own machine while a run is in progress. So:

- **Escape is the panic key**, checked before every emitted event.
- Every run carries **wall-clock, event-count and cursor-distance caps**.
- The **cursor is restored** when a run finishes or aborts.
- The tool **aborts rather than guessing** — no focus, no typing; no matching text, no Enter.

This drives *your* session with *your* account. It is not a way to evade a service's controls, and it
should not be pointed at an account that is not yours.

## Worked example

A real, complete run is committed: a **640 × 8260 px** screenshot of an article, sliced into six
images, delivered to the sidebar with a written brief, and answered with a **3,869-character
Chinese rebuttal essay** — written entirely by ChatGPT.

- [docs/EXAMPLE.md](docs/EXAMPLE.md) — the step-by-step ledger and the verification of every requirement
- [examples/undergrad-rebuttal/](examples/undergrad-rebuttal/) — the brief, the follow-up, the
  finished essay, the six slices, and ChatGPT's **verbatim transcript**

## What this is not

- Not an API client, and not a wrapper around one.
- Not a general browser-automation framework. It targets one surface deliberately.
- Not stealth tooling. There is no fingerprint spoofing, no CAPTCHA handling, no proxy rotation.
- Not a substitute for the ChatGPT API when an API is available — it exists for the cases where the
  capability is in the browser and nowhere else.

## Repository layout

| Path | Contents |
|---|---|
| `src/dsh_chatgpt_bridge/core.py` | the engine and the CLI (aim, act, time, read, verify) |
| `src/dsh_chatgpt_bridge/browser.py` | generic Chromium driver (used for the GitHub console work) |
| `src/dsh_chatgpt_bridge/slicer.py` | long screenshot → readable, uploadable slices |
| `skills/` | three DSH skills: tool reference, gated delivery process, hard input rules |
| `docs/` | guide, long-screenshot pipeline, lessons, worked example |
| `examples/undergrad-rebuttal/` | the committed example, including ChatGPT's raw output |
| `tools/` | the diagnostic probes used to find and characterise the surface |

## License

MIT. See [LICENSE](LICENSE).
