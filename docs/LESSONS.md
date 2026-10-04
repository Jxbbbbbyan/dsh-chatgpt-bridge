# Lessons learned

Everything here comes from one recorded attempt to deliver a real task through the ChatGPT sidebar.
It is kept because the failures are more instructive than the final design: **not one of them was a
slip — each was a decision made at the wrong level of abstraction.**

The full incident log, with evidence, is in [POSTMORTEM.md](../POSTMORTEM.md). The enforceable rules
derived from it are the `gui-input-hard-rules` skill in [`skills/`](../skills/).

---

## The twelve mistakes

| # | Mistake | What it cost | The rule it produced |
|---|---|---|---|
| 1 | Edited 1250 lines of source by **line index from a shell**, using variables from an earlier shell invocation | corrupted the tool file; needed a restore | never edit source by line index; back up and assert invariants before any programmatic rewrite |
| 2 | A **trailing newline** in the prompt file was typed as Enter | the task was split into **four partial messages**; ChatGPT answered each fragment; three essays were generated | in a send-on-Enter field a newline is **Shift+Enter**, and prompt files are stripped |
| 3 | Compared a correct composer value against the prompt **without normalising line endings** | a correct message was refused; the composer held `\r\n`, the prompt `\n` | normalise before comparing; report the first differing index |
| 4 | Trusted "no error" from the file dialog | six paths silently became **three attachments** | batch by a measured character budget and assert the resulting count |
| 5 | Concluded "the dialog closed by itself" from **one** negative enumeration | a modal was in fact open and swallowed every click | cross-check window discovery (UIA + Win32); "not observed" ≠ "not present" |
| 6 | Split a modal interaction **across shell invocations** | the dialog was lost between steps | a modal chain is one atomic process |
| 7 | Clicked the composer's **geometric centre** | with attachments present it landed on a thumbnail, opened the image preview, and the input control vanished from the tree | aim at a semantic point (the text line), never a container's centre |
| 8 | Treated a failed "New chat" as a **warning** and continued | the composer accumulated **twelve** attachments instead of six | a failed precondition stops the run; assert the postcondition of every reset |
| 9 | Left a **modal open** from an exploratory probe | it blocked the next real attempt | probes clean up after themselves; start with a pre-flight |
| 10 | Judged the sidebar "blank" from a **region screenshot** | briefly blamed the accessibility layer; another window was covering it | when a region looks wrong, capture the whole screen and check the foreground window |
| 11 | Let a **624 KB API payload** into the transcript | wasted context | constrain output at the source; write large results to a file |
| 12 | Waited on **"the text changed"** as the completion signal | the first read returned only `Thinking` | use a domain-specific completion signal |

## What it cost

The same deliverable was generated about six times. The expensive repetitions were all downstream of
two decisions: **using the real 438-character brief to discover the newline bug**, and **continuing
after a failed reset**. A three-line throwaway prompt through the same pipeline would have exposed
mistakes 2, 3 and 12 for roughly 1 % of the cost.

**The rule that follows:** *prove the pipeline with a cheap smoke test before the expensive real task.*

## What actually worked

- **Two guards earned their keep.** "No focus, no typing" prevented ~440 characters from being typed
  into the wrong application — including the agent's own host. "No text match, no Enter" prevented a
  mangled prompt from being sent, twice.
- **Dry runs first.** Planning motion and keystrokes before emitting them costs nothing.
- **Backup → validate → atomic replace** for every credential or settings change.
- **Cross-checking claims**: schema validation *and* a live request *and* an end-to-end run, rather
  than any one of them.
- **Distinguishing "not observed" from "not present"** — the discipline that mistake 5 broke, and
  every other conclusion kept.

## The generalisation

| Surface-level symptom | Underlying decision error |
|---|---|
| corrupted source file | using a stateful shell as if it were stateful across invocations |
| four partial messages | assuming a newline is a newline in every field |
| three attachments instead of six | reading "no error" as "accepted" |
| clicks swallowed by an invisible dialog | reading "not observed" as "not present" |
| click opened an image preview | using geometry instead of semantics |
| twelve attachments | downgrading a failed precondition to a warning |

For a GUI automation to be trustworthy it must, at every committing boundary, **assert what it
believes** and **stop when the assertion fails**. That single habit covers most of the table above.
