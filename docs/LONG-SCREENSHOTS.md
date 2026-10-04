# One long screenshot → six readable images → attached to ChatGPT

This is the procedure for handing a chat UI a picture that is too tall to survive its own
downscaling, and for getting it in through the real user interface. Every rule below is the
resolution of an observed failure.

---

## Step 1 — Why slicing is mandatory

The material for the worked example was a WeChat article screenshot:

```
微信图片_20261005002555_572_4.jpg    640 × 8260 px    1,069,110 bytes
```

A chat UI resizes an image for its vision model by fitting it into a bounded box. A 8260 px tall
image is therefore scaled down by roughly **4×** in its long dimension, and 12 px body text becomes
unreadable. The model receives a picture, but not the article.

**Rule:** if the long side exceeds ~2000 px, slice before sending.

## Step 2 — Slicing with overlap

```powershell
python -m dsh_chatgpt_bridge.slicer "微信图片_20261005002555_572_4.jpg" slices
```

| Parameter | Value | Reason |
|---|---|---|
| slice height | 1700 px | survives downscaling with the text still legible |
| overlap | 100 px | a line of text or a sentence is never cut in half across two images |
| format | PNG | lossless; the source was already a lossy JPEG |

Result for this source — **one image becomes six**:

| Slice | Rows | Size |
|---|---|---|
| `slice-01.png` | 0 – 1700 | 640 × 1700 |
| `slice-02.png` | 1600 – 3300 | 640 × 1700 |
| `slice-03.png` | 3200 – 4900 | 640 × 1700 |
| `slice-04.png` | 4800 – 6500 | 640 × 1700 |
| `slice-05.png` | 6400 – 8100 | 640 × 1700 |
| `slice-06.png` | 8000 – 8260 | 640 × 260 |

**Verify legibility before uploading** by opening one slice — not by assuming the arithmetic worked.

## Step 3 — Telling the model what it is looking at

The slices are meaningless in isolation, so the brief says so explicitly:

> 附件是同一篇长文的 6 张连续截图切片，按 slice-01 到 slice-06 的顺序排列，相邻切片之间特意留了重叠部分。

Without that sentence the model treats them as six unrelated pictures. **Rule:** the brief must state
the slice count, the ordering, and the overlap.

## Step 4 — Attaching through the real user interface

```powershell
dsh-chatgpt-bridge attach-files slices\slice-0*.png
```

The tool performs, with real input:

1. click the composer's **add** button (`Add files and more`);
2. click **Files and folders** in the menu that appears;
3. wait for the native Windows **Open** dialog;
4. click its file-name field, type the quoted space-separated paths, press Enter;
5. wait for the attachment chips and report how many the composer holds.

### Four rules that make it reliable

**R-1 — Batch by character budget.** The dialog's file-name field **truncates near 256 characters and
reports no error**. Six paths of ~64 characters (384 total) produced exactly **three** attachments,
with the UI reporting success. `--chunk-chars` (default 200) splits the list, and the running count is
asserted after every batch. Six slices went in as three batches of two.

**R-2 — Find the dialog through Win32, not UI Automation.** An owned modal dialog can be absent from
`GetRootControl().GetChildren()` while plainly on screen. Enumerating it that way led to the
conclusion "the dialog closed by itself" — while it was in fact open and swallowing every click meant
for the sidebar. `FindWindowW("#32770")` finds it, and the handle is wrapped for UIA use.

**R-3 — Run the whole chain in one process.** Handing control back to the shell between steps loses
the modal. This is why `attach-files` is a single command rather than four.

**R-4 — A dialog left open owns the screen.** The command detects an already-open dialog and fills it
instead of clicking behind it; `fill-dialog` finishes one by hand.

## Step 5 — Confirming the attachments actually landed

```
batch 1/3: 2 file(s)  →  composer now holds 2 attachment(s)
batch 2/3: 2 file(s)  →  composer now holds 4 attachment(s)
batch 3/3: 2 file(s)  →  composer now holds 6 attachment(s)
```

The count is read from the accessibility tree as buttons named `Remove slice-0N.png`. **Rule:** never
treat "no error" as "accepted" — assert the count. A silent short batch is the failure mode to watch.

## Step 6 — Sending the brief, once

```powershell
dsh-chatgpt-bridge ask --prompt-file brief.txt --reply-timeout 540 --settle 6
```

Two traps live here, both of which the guards catch:

- **Enter sends.** A newline in the prompt is typed as **Shift+Enter**. When it was typed as Enter, a
  four-paragraph brief went out as four separate partial messages and ChatGPT answered each fragment.
- **The composer's value uses `\r\n`** while the prompt file uses `\n`, so a raw substring test fails
  on any multi-line prompt; comparison normalises line endings first.

`ask` refuses to press Enter unless the composer's (normalised) text matches the brief.

## Step 7 — Reading the answer

The reply is the text after the last `ChatGPT said:` marker, waiting for a **new** block that has been
stable for `--settle` seconds. For the worked example this returned a 3,869-character essay; the
uncleaned transcript is committed as
[`examples/undergrad-rebuttal/chatgpt-transcript-raw.md`](../examples/undergrad-rebuttal/chatgpt-transcript-raw.md)
so the chrome that had to be filtered is visible as evidence.

## Checklist

- [ ] Long side > 2000 px → slice at 1700 px with 100 px overlap
- [ ] Open one slice and confirm the text is legible
- [ ] State slice count, order and overlap in the brief
- [ ] `attach-files` with default batching; assert the attachment count equals the file count
- [ ] Brief written to a UTF-8 file, no `N. ` at line starts, no trailing newline
- [ ] `ask --prompt-file`; expect the focus line, the character count and `sent (Enter)`
- [ ] Read with a domain completion signal, then verify the answer against each requirement
