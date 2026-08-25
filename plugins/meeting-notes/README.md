# 📝 meeting-notes

meeting-notes turns a folder of meeting transcripts into one readable summary per meeting: a
TLDR, the decisions, and action items with a name and a date on each. It works out which
transcripts are new, gives each one its own isolated subagent, and runs them in parallel.

## 🎬 Demo

Finding the new transcripts mechanically, the parallel subagents, the tell check coming back
clean, stowing what's done, and the summary that fell out.

![meeting-notes demo](https://raw.githubusercontent.com/dmitry-do/ai-toolkit-public/main/docs/assets/meeting-notes-demo.png)

## ⚙️ How it works

![How meeting-notes works](https://raw.githubusercontent.com/dmitry-do/ai-toolkit-public/main/docs/assets/meeting-notes-how-it-works.png)

Most of the design defends against two failure modes you won't see unless you look for them:

- **Cross-contamination.** One context summarising six meetings blends them — a decision from
  Tuesday turns up in Monday's notes. So each transcript gets its own isolated subagent, and since
  they're independent, they run in parallel. You never need to `/clear` between files.
- **The silent subagent.** A subagent can end its turn with no error after reading the transcript
  but before writing anything, and nothing about that looks like a failure. A reconcile step checks
  every launched transcript came back with a summary on disk, and resumes the ones that didn't —
  without it, a meeting is dropped for good.

Two more rules earn their place: only the orchestrator writes the tracker, so parallel rows can't
race and drop; and a row is written before its transcript is stowed, so nothing can slip out of
every ledger. A mechanical tell-check greps each new summary and escalates only the files with hits
to [`humanizer`](https://github.com/blader/humanizer).

## 📄 Transcript in, summary out

![A transcript, and the summary written from it](https://raw.githubusercontent.com/dmitry-do/ai-toolkit-public/main/docs/assets/meeting-notes-summary.png)

Left is what the recorder hands you: timestamps, names, and a conversation nobody structured.
Right is what lands in `summaries/`: a TLDR, the decisions as decisions, and action items with a
name and a timeline on each.

## 📦 Install in Claude Code

```
/plugin marketplace add dmitry-do/ai-toolkit-public
/plugin install meeting-notes@ai-toolkit-public
```

## 🌐 Claude Web

Works on claude.ai over uploaded or pasted transcripts (no local `rec/` folder needed) — package
the skill folder with `scripts/package-skill.sh meeting-notes` and upload it in
**Customize → Skills**.

Optionally escalates to the [`humanizer`](https://github.com/blader/humanizer) skill when its tell check finds issues and
that skill is installed; it works fine without it. Mine, MIT-licensed (see the root
[LICENSE](../../LICENSE)).
