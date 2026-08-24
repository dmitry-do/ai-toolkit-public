---
name: deslop
description: Rework a document so every claim is true to its source and the prose is direct. Use when the user wants to deslop, fact-check, tighten, or de-slop a README, SKILL.md, release notes, changelog, or other documentation against the code or source it describes — verifying each claim and cutting elliptical, round-the-subject prose. The rework runs on a bundled claude-opus-4-8 subagent, one document at a time.
---

# deslop

Rework a document in two passes: **verify every claim against its source, then make the prose
direct.** Fix what a doc says before polishing how it says it — accuracy first, style second.

deslop does the actual rework on a bundled subagent that is pinned to `claude-opus-4-8`
(`agents/deslop.md`), one document at a time in isolation. The isolation keeps one document's facts
from bleeding into another's; the pinned model is why the rework runs the same regardless of the
session's own model.

## When to use

- "deslop this README", "fact-check this doc against the code", "make this less round-the-subject".
- Reworking a README, `SKILL.md`, release notes, changelog, or API doc so its claims match the
  implementation and its prose is direct.
- After a code change, to bring a doc back in line with what the code now does.

## When not to use

- **Pure creative or opinion writing** with no source of truth to check against — there is nothing
  to verify. For AI *tells* in any prose (em-dashes, rule of three, stock vocabulary), use
  `humanizer` instead.
- **A document whose source you don't have.** deslop verifies against the implementation; without
  it, the accuracy pass can only flag claims, not fix them.

## Workflow

1. **Identify each target document and its source of truth.** For a plugin README the source is
   that plugin's `SKILL.md`, its `scripts/`, `hooks/`, and `plugin.json`. For other docs it is the
   code or reference the claims describe. Ask the user if the source isn't obvious — don't guess a
   source.
2. **Dispatch one `deslop` subagent per document, on claude-opus-4-8.** Use the Task tool with the
   bundled `deslop` agent; its frontmatter pins `model: claude-opus-4-8`, which is what puts the
   rework on that model. Pass it the TARGET path and the SOURCE paths. Independent documents can be
   launched in parallel. If the bundled agent isn't available as a subagent type in this runtime,
   launch a general subagent with an explicit `claude-opus-4-8` model override and the methodology
   from [`../../agents/deslop.md`](../../agents/deslop.md).
3. **Collect each subagent's report** — CORRECTIONS, FLAGGED, STYLE, FILE — and present them
   together. Lead with the factual corrections; they matter more than the prose changes.
4. **Optional: hand off to `humanizer`.** If the `humanizer` skill is installed, offer to run it
   over the reworked files as a final AI-tell cleanup. deslop fixes truth and directness; humanizer
   strips surface tells and adds voice. The plugin works without it.

## The two passes (what the subagent does)

- **Pass 1 — accuracy (first, always).** Read the source, then check the target claim by claim:
  names, flags, filenames, numbers, defaults, behaviour, ordering, and what-runs-where. Fix what
  the source contradicts, correct backwards framings, cut unsupported claims, and **flag** anything
  unverifiable rather than keep it. Never invent a fact to fill a gap.
- **Pass 2 — style (second).** Make the true content direct: lead with the subject, cut
  teaser/round-the-subject openings, land each point once, drop empty scene-setting. Keep the
  document's real voice, its structure, and its code blocks and real output exactly.

Accuracy before style, always — there is no point polishing a sentence that says the wrong thing.
The full worker instructions are in [`../../agents/deslop.md`](../../agents/deslop.md), and a worked
before → after pair is in [`examples/`](./examples/).
