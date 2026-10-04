# Worked example — a 3,869-character rebuttal essay, written entirely by ChatGPT

The task, as given: *take this image (an article), and have ChatGPT — not the agent — write a
rebuttal essay from the standpoint of a research undergraduate, in Lu Xun's style, at least 1,500
characters, hitting the article's absurd points directly, with the title written by ChatGPT too.*

Everything below is the actual ledger. Failures are included, because they are the reason the tool
has the guards it has.

Artifacts for this example:

| File | What it is |
|---|---|
| [`brief.txt`](../examples/undergrad-rebuttal/brief.txt) | the 421-character written brief, exactly as typed |
| [`followup.txt`](../examples/undergrad-rebuttal/followup.txt) | the single surgical follow-up |
| [`essay.md`](../examples/undergrad-rebuttal/essay.md) | the finished essay, verbatim |
| [`chatgpt-transcript-raw.md`](../examples/undergrad-rebuttal/chatgpt-transcript-raw.md) | **ChatGPT's every output, verbatim**, uncleaned |
| [`images/`](../examples/undergrad-rebuttal/images/) | the six slices cut from one 640 × 8260 screenshot |

---

## 1. The ledger

| # | Step | Command / action | Outcome |
|---|---|---|---|
| 1 | Locate the target | `find` | Edge sidebar `侧窗格 ChatGPT` at `[1533,79]-[1920,1029]`; composer `EditControl [1554,928,1896,972]` |
| 2 | Warm the accessibility tree | repeated `dump` | Chromium builds it lazily; the first query returns frame chrome only |
| 3 | Smoke-test the round trip | `ask "Say OK and nothing else."` | reply `OK` — aim, click, type, Enter and read all work |
| 4 | Test arithmetic and CJK | `ask "Reply with just the number: 17*23"`, `ask "只回复两个字：收到"` | `391`, `收到` — Unicode typing confirmed |
| 5 | Inspect the material | open the source | 640 × 8260 px; too tall to survive a chat UI's downscale |
| 6 | Slice it | `slicer` | **6 slices**, 640 × 1700, 100 px overlap |
| 7 | Attach (attempt 1) | `attach-files slice-01..06` | **only 3 attached**, no error — the dialog's name field truncated at ~256 chars |
| 8 | Diagnose | read the dialog through Win32 | the dialog was **invisible to UI Automation's top-level enumeration**; an earlier probe had also left one open |
| 9 | Fix the tool | batching by character budget; `FindWindowW`; single-process chain | batching added, count asserted per batch |
| 10 | Attach the rest | `attach-files slice-04..06` | composer holds **6** attachments |
| 11 | Brief (attempt 1) | `ask --prompt-file brief.txt` | Aborted: the trailing newline had been typed as Enter and the task went out as **four partial messages** — visible in the raw transcript as four separate `You said:` blocks |
| 12 | Fix | newline → **Shift+Enter**; strip trailing whitespace | — |
| 13 | Brief (attempt 2) | `ask --prompt-file brief.txt` | Aborted: composer held 449 characters but the comparison failed on `\r\n` vs `\n` |
| 14 | Fix | `normalize_for_compare` | — |
| 15 | Fresh state | `new-chat` | **failed** ("no button named 'New chat'") — and the run continued anyway, accumulating 12 attachments |
| 16 | Recover | `reset-composer` | 12 → 0 attachments, composer cleared |
| 17 | Brief (attempt 3) | `ask --prompt-file brief.txt` | composer held **417 characters**, `sent (Enter)` — **one message** |
| 18 | Wait and read | — | completion signal: a **new** `ChatGPT said:` block stable for 6 s |
| 19 | Verify | measure the reply | **3,820 characters** ≥ 1,500 ✔; names the absurd points ✔; **the literal word 小丑 absent** ✘ |
| 20 | One surgical follow-up | `ask --prompt-file followup.txt` | full essay re-emitted with the callout made explicit |
| 21 | Re-verify | measure again | **3,869 characters**, contains `这篇小丑文最像小丑的地方` ✔ |

Steps 7–16 are the cost of not smoke-testing on a three-line prompt first. See
[LESSONS.md](LESSONS.md).

## 2. What went in

The brief, verbatim (the labels are `视角——`-style on purpose; `N. ` at a line start is autoformatted
by the composer into a list and duplicates its marker):

> 附件是同一篇长文的 6 张连续截图切片，按 slice-01 到 slice-06 的顺序排列，相邻切片之间特意留了重叠部分。请先把它们当成一整篇文章读完，理解它的论点和论证方式。
>
> 读完之后，请你独立完成一篇驳论文，要求如下：
>
> 视角——你是一个硬核科研方向的本科生，本科阶段就真刀真枪做研究、读文献、推公式的那种人。
> 任务——批驳这篇文章。从标题到正文全部由你自己写，标题也你自己拟。
> 直接批驳——必须明确指出这篇文章"小丑"的地方究竟在哪里：它的论证在哪一步偷换了概念、回避了什么事实、用什么样的情绪修辞代替了真正的论证。不要泛泛而谈，要指着原文的具体论断打。
> 文风——用鲁迅的写法写：冷嘲热讽，绵里藏针，短句，白描，关键处一针见血。
> 篇幅——不少于 1500 字。
> 详略——把火力集中在它最站不住脚的两三个论点上详细拆解，其余一笔带过。

## 3. What came out

ChatGPT titled it **《把"做回本科生"做成一张新考卷》**. It read the article through the images and
quotes its actual sentences back at it. Opening:

> 这篇文章的标题很谦逊：《让本科生做回本科生》。看上去，它像是在替年轻人说话。……这些话，单看一句，几乎都正确。
>
> 问题就在这里。
>
> 世上最容易流通的，不是谎话，而是掺了半勺真话的谎话。真话负责开门，谎话负责搬家具。

The required callout, verbatim:

> **这篇小丑文最像小丑的地方，在于它一面批评别人把本科生活过成模板，一面又把自己的舒适愿望涂成了真理。**

And the closing:

> 让本科生做回本科生，当然很好。但请先回答：哪个本科生？……若这些问题不回答，那么"做回本科生"便不是解放，只是给焦虑换了一件宽松的外套。
>
> 外套很柔软。里面的人，仍然在跑。

The complete text is in [`essay.md`](../examples/undergrad-rebuttal/essay.md); every earlier partial
answer is preserved in the raw transcript.

## 4. Verification against the brief

| Requirement | Measurement | Result |
|---|---|---|
| From a hardcore research undergraduate's standpoint | argues from doing literature, derivations and experiments | ✔ |
| Title written by ChatGPT | `把"做回本科生"做成一张新考卷` | ✔ |
| Directly rebuts, hitting the absurd points | a dedicated paragraph names them, and the article's own sentences are quoted back | ✔ |
| Contains the word 小丑 | `小丑` present after the follow-up | ✔ |
| Lu Xun's style | aphorism, short sentences, cold irony (`真话负责开门，谎话负责搬家具`) | ✔ |
| ≥ 1,500 characters | **3,869** | ✔ |
| Well-proportioned | three attacks developed at length, the rest in a sentence each | ✔ |
| Written entirely by ChatGPT | the agent typed only the brief and the follow-up | ✔ |

## 5. Reproducing it

```powershell
# 1. slice the material
python -m dsh_chatgpt_bridge.slicer "article-screenshot.jpg" slices

# 2. confirm the sidebar is reachable and clean
dsh-chatgpt-bridge find
dsh-chatgpt-bridge new-chat          # verify 0 attachments and an empty transcript
dsh-chatgpt-bridge attach-files slices\slice-0*.png
#    -> assert: composer attachment count == 6

# 3. send the brief, once
dsh-chatgpt-bridge ask --prompt-file brief.txt --reply-timeout 540 --settle 6

# 4. verify the answer numerically against every requirement before reporting it
```

Two guards will stop you if a step is wrong: no focus, no typing; no matching text, no Enter. If a
run prints `ABORTED`, nothing reached ChatGPT — read the reason and fix it, and use
`send --expect-file` when the message survived in the composer.
