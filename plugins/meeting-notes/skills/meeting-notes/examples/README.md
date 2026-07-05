# Worked example

One real input → real output, so you can see what the skill produces before running it. The
meeting is fictional (no real people or company), so there's nothing to anonymise.

- **Input:** [`rec/20260605 1400 Transcription [EN].txt`](./rec/) — a raw ~2.5-minute product-sync
  transcript, complete with the disfluencies a real recording carries ("um", "yeah okay", false
  starts).
- **Output:** [`summaries/2026-06-05_onboarding-redesign-sync.md`](./summaries/2026-06-05_onboarding-redesign-sync.md)
  — the summary the skill produces, after the optional `humanizer` pass from step 3 of the workflow (run here because `humanizer` was installed).

What the example exercises:

- **The standard (non-interview) template** — TLDR, discussion points, decisions, action items, next steps.
- **The action-item format rule** — every item is a checkbox with a `-- person, timeline` suffix.
  No tables, no `- **Name:** task` bold-name lists. (Why that rule exists: see the failure modes in
  `../SKILL.md`.)
- **Heading levels** — document title is `##`, sections are `###`. Never `#`.
- **Filename derivation** — the `20260605` prefix becomes the `2026-06-05` date, and the topic is
  hyphenated from the content.

To reproduce, drop the transcript into a `rec/` folder at your project root and run `/meeting-notes`
(or "process the recordings in rec/"). The skill launches one isolated subagent for the file, writes
the summary to `summaries/`, and records it in `RECORDINGS.md`.
