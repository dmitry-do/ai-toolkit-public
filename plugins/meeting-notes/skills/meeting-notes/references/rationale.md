# meeting-notes — design rationale

Why the rules in [`SKILL.md`](../SKILL.md) are what they are. Nothing here is needed to
*run* the skill; it exists so the reasoning survives without loading into every invocation.

## Why one isolated subagent per transcript

When meetings shared a context, summaries cross-contaminated — attendees, decisions, and
action items from one meeting leaked into another's notes. Isolation is the fix: each
subagent sees exactly one transcript and nothing else. It also removes any need to `/clear`
between files. This is the whole point of the skill, not an optimization.

## Why subagents never write the tracker

Early runs let every subagent append its own row to `RECORDINGS.md`. Concurrent writes to
one file race; last-writer-wins silently dropped rows, and the "lost" meetings were
reprocessed on the next run. Now each subagent *returns* its row, and the orchestrator
writes them all in one serial pass (Step 4), then verifies each filename landed exactly
once.

## Why the format block is prescriptive

- **Action items are checkboxes with a `-- person, timeline` suffix — never tables or
  `- **Name:** task` bold-name lists.** Left to its own defaults the model drifts into
  prose, tables, or bold-name lists, none of which render as something you can actually
  tick off. Pinning one format keeps a batch of summaries consistent.
- **Headings are `##` for the title and `###` for sections — never `#`.** Models reach for
  `#` by default, but these summaries get embedded in larger docs where an h1 collides
  with the host document's structure. Stating it explicitly stops the drift.

## Why Step 0 moves rows and transcripts together

Archive a tracker row but leave its transcript in `rec/`, and Step 1 sees a rowless `.txt`
— the definition of "unprocessed" — and reprocesses a meeting that was already done. The
script never splits the pair, moves both on a single date cutoff, and verifies the coupling
invariant before it exits.

## Why Step 1 is mechanical

The orchestrator used to read all of `RECORDINGS.md` into context to compute the
unprocessed list — 5–6k tokens on a 126-row project, growing over time, and re-billed as
input on every later turn of the run. The `--list-unprocessed` flag computes the same delta
under the same invariant the archiver already enforces (a row with any status counts as
processed), and the orchestrator sees only the handful of filenames it actually needs.

## Why Step 3 is a grep triage, not an unconditional humanizer pass

A token audit of a real 7-transcript run found Step 3 double-paying: six of the seven
subagents had already humanized their summaries (those rules are now pinned in the subagent
prompt), yet the orchestrator still loaded the full humanizer skill text (~3.5k tokens) and
re-read all seven summaries (~11k). Every residual issue it found was mechanically
greppable — em dashes and Title Case headings. A grep over the new files, escalating
per-file only on hits, catches the same issues for a few hundred tokens.

The check runs only over files written this run for a reason: in the reference project,
141 of 442 historical summaries trip the Title Case check and 110 trip the bold-label
check (they predate the pinned prompt rules). Globbing `summaries/*.md` would trigger a
mass escalation over files nobody asked about.

## Why the subagent report is pinned to three lines

Left open-ended, subagents returned multi-paragraph reports — processing commentary,
meeting recaps, open-ended dictionary musings — worth ~3–4k tokens per run, all of it
re-billed to the orchestrator's context on every subsequent turn. The three fixed lines
(`ROW:` / `TOPIC:` / `DICTIONARY:`) carry everything Steps 4–5 consume.

## Why processed transcripts are stowed per run, not only by age

Age-based archiving (Step 0) keeps the tracker small but leaves `rec/` holding every
transcript from the last three months, processed or not. That makes `rec/` a folder you
can't read: the unprocessed backlog is invisible without cross-referencing the tracker, and
the only thing that knows the difference is the script. Stowing at the end of each run
(Step 4.5) makes `rec/` mean something on sight — if a file is there, it hasn't been done.

The file and its row move together, so the two sides mirror each other: `rec/` +
`RECORDINGS.md` are the pending backlog, `archive/rec/` + `archive/RECORDINGS.md` are the
processing history. Splitting them — file archived, row still live — would leave the live
tracker describing transcripts that aren't there, which is the confusion the mirroring is
meant to remove.

That makes one thing load-bearing: **`--list-unprocessed` must consult both ledgers.** Once
a row is retired, the live tracker alone can no longer answer "has this been processed?", so
a re-downloaded transcript dropped back into `rec/` would read as new and get a second
summary. Checking both costs nothing (it happens inside the script, so no orchestrator
context) and it also makes the ordering inside the stow irrelevant to correctness. Files are
still moved before rows, so an interruption leaves a stale live row (harmless) rather than
an unrowed transcript.

The stow still runs **after** the Step 4 tracker write, because the reverse order has a real
failure: a transcript moved out of `rec/` before any row exists is invisible to every ledger
and every scan path, so the meeting is lost silently. Stow-after-write degrades instead to a
file left in `rec/` with a row already present, which the next run tidies up.

Both modes must also agree on what "processed" means. When `--stow-processed` checked only
the live tracker, a transcript whose row had already been retired read as unprocessed, so it
sat in `rec/` untouched and never reached the collision guard — `rec/` quietly stopped
meaning "pending". Both now read both ledgers.

⚠️ rows are stowed too. A transcript flagged as a bad recording won't be reprocessed
either, so leaving it in `rec/` only inflates the apparent backlog. Its row still records
what happened, and a genuinely better recording of the same meeting arrives as a new file.

## Why Step 2.5 checks reports instead of trusting task completion

A completed subagent task is not evidence that the work happened. When a subagent's stream
ends abnormally the harness has no failing tool call to surface, so it marks the task
complete and returns the last text the agent emitted — which, if the agent narrated before
its first tool call, is an innocuous "I'll start by reading the transcript file."

The pinned three-line report (above) is what makes this detectable: a report is either
well-formed or it isn't, and a missing `ROW:` line is unambiguous in a way that prose
never would be. Checking that the ✅ row's file exists on disk catches the same failure from
the other side. Both checks are cheap, and they run over the same filenames Step 3 already
needs. The failure is also worth catching precisely because it is quiet: the transcript
reappears as unprocessed next run, so the loss is recoverable but invisible, and a run that
reports "4 of 5 processed" without saying why is worse than one that fails loudly.

## Anti-patterns

- **Don't process multiple transcripts in one context.** Shared context cross-contaminates
  summaries (attendees and decisions leak between meetings). One isolated subagent per
  transcript, always.
- **Don't format action items as tables, numbered lists, or `- **Name:** task` bold-name
  lists.** Only `- [ ] task -- person, timeline` checkboxes render as something actionable
  and scan consistently across a batch.
- **Don't title summaries with `#` (h1).** Use `##` for the title, `###` for sections —
  these notes get embedded in larger documents.
- **Don't translate proper nouns.** Names, companies, and products stay in their original
  form even when the rest is translated.
- **Don't reprocess completed transcripts.** Step 1's `--list-unprocessed` computes the
  skip-list mechanically; a row with any status (✅ or ⚠️) counts as processed.
- **Don't let subagents write `RECORDINGS.md`.** Concurrent writes to the shared tracker
  race and silently drop rows. Subagents return their row; the orchestrator writes them
  serially in step 4.
- **Don't scan `archive/` in step 1.** The script reads `rec/` only. Pulling in archived
  transcripts reprocesses meetings that are already done.
- **Don't run the Step 3 checks over `summaries/*.md`.** Only the files written this run —
  historical summaries legitimately trip the patterns in bulk.

## Known failure modes

- **Cross-meeting contamination** — decisions or attendees from one meeting surface in
  another's summary. Mitigation: one isolated subagent per transcript (see step 2).
- **Action-item format drift** — items come back as prose, a table, or bold-name lists you
  can't tick off. Mitigation: the prescriptive checkbox format in the subagent prompt.
- **Wrong / missing date** — a filename without a leading `YYYYMMDD` leaves the date
  ambiguous. Mitigation: date is parsed from the filename prefix; if it's absent, the
  subagent flags it rather than guessing.
- **Proper nouns mangled in translation** — names anglicised or product names translated.
  Mitigation: the explicit preserve-proper-nouns rule in the translation guidelines.
- **Interview misread as a standard meeting** — a candidate interview summarised with the
  wrong template. Mitigation: the subagent detects interview transcripts and switches to
  the interview format.
- **Lost tracker rows** — parallel subagents writing the shared `RECORDINGS.md` race, and
  some rows vanish (the meetings then look unprocessed and get redone). Mitigation:
  subagents return their row; the orchestrator writes all rows serially in step 4, then
  verifies each one landed.
- **Archived meeting reprocessed** — a row is archived but its transcript is left in
  `rec/` (or step 1 scans `archive/`), so the skill treats it as new. Mitigation: the
  archive script moves rows and transcripts together and checks the coupling on exit; the
  `--list-unprocessed` mode reads `rec/` only.
- **Verbose subagent reports** — multi-paragraph narratives inflate the orchestrator's
  context by ~3–4k tokens per run. Mitigation: the pinned three-line report format in the
  subagent prompt.
- **Subagent stops silently mid-task** — the stream ends with no `stop_reason`, an empty
  final message, and no error, after the transcript is read but before the summary is
  written. The task is reported complete and the return value falls back to the agent's
  opening line, so it reads like a normal (if terse) success. Left unchecked the transcript
  gets no row, no summary, and no visible error. Mitigation: Step 2.5 reconciles `ROW:`
  lines and summary files against the launched transcripts, then resumes or relaunches the
  ones that came back short. Observed 2026-07-28 on a 5-transcript run (1 of 5 affected).

## Tested with

- **Runtime:** Claude Code · model `claude-opus-4-8`.
- **Skill type:** prompt-driven workflow plus one bundled mechanical helper,
  `archive-old-recordings.py` (Step 0 archiving, Step 1 unprocessed list).
- **Last validated:** 2026-07-09 — processed the fictional onboarding-sync transcript in
  `examples/` end to end on a scratch tree: Step 1 delta via `--list-unprocessed`, one
  isolated subagent returning the pinned three-line report, both Step 3 tell checks clean
  on the produced summary (structure matches the reference example, including sentence-case
  headings), tracker row appended and verified, and a Step 1 re-run confirming no
  reprocessing. Earlier full validation: 2026-06-13.
- **Archive helper:** 2026-06-23 — verified on a scratch tree: correct month cutoff,
  idempotent no-op when nothing is old enough, rows and transcripts moved together, and
  the no-reprocessing invariant checked on exit.
