# 🧹 deslop

deslop reworks a document in two passes: it checks every claim against the source that document
describes, then rewrites the prose to be direct. Accuracy comes first, because there's no point
polishing a sentence that says the wrong thing. The rework runs on a bundled `claude-opus-4-8`
subagent, one document at a time in isolation.

## 🎬 Demo

A README checked against its skill: a wrong default corrected to what the code actually says, a
made-up figure flagged and cut, and the teaser opening rewritten to lead with the subject.

![deslop demo](https://raw.githubusercontent.com/dmitry-do/ai-toolkit-public/main/docs/assets/deslop-demo.png)

## ⚙️ How it works

![How deslop works](https://raw.githubusercontent.com/dmitry-do/ai-toolkit-public/main/docs/assets/deslop-how-it-works.png)

- **Pass 1 — accuracy, first.** The subagent reads the source of truth (for a plugin README, that's
  the `SKILL.md`, scripts, hooks, and `plugin.json`), then goes through the document claim by claim
  and fixes what the source contradicts.
- **Pass 2 — style, second.** Once the content is true, the prose is made direct: lead with the
  subject, drop the teaser, land each point once. Code blocks and real command output are left as-is.
- **It flags what it can't verify, and never invents.** A claim with no support in the source is
  reported, not backfilled with a plausible-sounding number.
- **`humanizer` is an optional last step.** If it's installed, deslop can hand off to it for a final
  AI-tell cleanup. It isn't required.

## 📦 Install in Claude Code

```
/plugin marketplace add dmitry-do/ai-toolkit-public
/plugin install deslop@ai-toolkit-public
```

## 🌐 Claude Web

The two passes are plain editing and run on claude.ai — package the skill folder with
`scripts/package-skill.sh deslop` and upload it in **Customize → Skills**. Only the model pin
(`agents/deslop.md`, which pins the rework to `claude-opus-4-8`) is Claude Code-only; on claude.ai
the passes run on whatever model you're using.

Mine, MIT-licensed (see the root [LICENSE](../../LICENSE)).
