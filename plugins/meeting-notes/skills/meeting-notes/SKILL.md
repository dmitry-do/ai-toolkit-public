---
name: meeting-notes
description: Process meeting transcripts from rec/ folder into professional markdown summaries. Use when user wants to process meeting recordings, transcripts, or asks to generate meeting notes. Automatically invoked by /meeting-notes command.
---

# meeting-notes

Process meeting recordings into structured, professional summaries, with complete isolation between transcripts.

## When to use this skill

- User runs the `/meeting-notes` command
- User asks to "process meetings", "process recordings", or "generate meeting notes"
- User mentions unprocessed transcripts in the `rec/` folder

## When not to use

This is batch summarization of finished text transcripts. Reach for something else when:

- **The input is audio, not text.** Transcribe it first with the `audio-transcription` skill, then point this skill at the resulting `.txt`.
- **You need live notes during the meeting.** This runs after the fact over a saved transcript, not as captions while people talk.
- **It's a single short transcript and you're already in the conversation.** The per-transcript subagent isolation buys nothing for one file you can summarize inline; its value is keeping a *batch* of meetings from bleeding into each other.
- **You need verbatim minutes or a legal record.** This produces a summary — TLDR, decisions, action items — not a faithful line-by-line transcript.

## Processing workflow

### Step 0: Archive recordings older than 3 months (run first)

Before anything else, prune old entries so the tracker and `rec/` folder stay small. Run the bundled script from the project root:

```bash
python3 "<this skill's directory>/archive-old-recordings.py" --root "<project root>" --months 3
```

(`<this skill's directory>` is the base directory this skill was loaded from. The default `--months` is 3; pass `--dry-run` to preview.)

The script moves tracker rows and their transcript files together, on a single date cutoff, into `archive/` (`archive/RECORDINGS-archive.md` and `archive/rec/`). Moving them as a pair is the whole point, because it preserves the rule Step 1 depends on:

> An unprocessed transcript is a `.txt` in `rec/` with **no row** in `RECORDINGS.md`.

Archive a row but leave its transcript in `rec/`, and Step 1 reprocesses it. The script never splits that pair, and verifies the invariant before it exits. It's idempotent — safe to re-run, merging into the existing archive — and a no-op when nothing is old enough. Don't hand-edit the archive or point Step 1 at it; Step 1 reads `rec/` only.

### Step 1: Identify unprocessed transcripts

1. Read the `rec/` folder — top level only, never `archive/` — to get all `.txt` files.
2. Read `RECORDINGS.md` to see which files are already done (marked ✅ Completed).
3. Build the list of unprocessed transcripts.

### Step 2: Launch isolated subagents

For each unprocessed transcript, launch a separate subagent with the Task tool (`subagent_type="general-purpose"`). Launch all of them in parallel, in a single message with multiple Task calls.

**One subagent per transcript is the whole point, not an optimization.** When meetings shared a context, summaries cross-contaminated — attendees, decisions, and action items from one meeting leaked into another's notes. Isolation is the fix: each subagent sees exactly one transcript and nothing else.

**Subagents never write `RECORDINGS.md`.** Each one writes its own summary file — a distinct path in `summaries/`, safe to do in parallel — but the shared tracker is off-limits. Parallel edits to a single file race, and rows silently disappear. Each subagent instead *returns* its tracker row, and the orchestrator writes them all in one serial pass in Step 4.

Each subagent must receive this exact prompt:

```
You are processing a meeting transcript in complete isolation. No other transcripts exist in your context.

TRANSCRIPT FILE: [filename from rec/ folder]
PROJECT ROOT: [absolute path to project]

Your task:
1. Read the transcript file from rec/[filename]
2. Analyze the meeting content and identify the main topic
3. Determine the appropriate meeting date from the filename (format: YYYYMMDD at the beginning)
4. Create a concise, professional summary in English (translate from Russian if needed)
5. Save the summary as summaries/yyyy-mm-dd_meeting-topic.md in the summaries/ folder
6. Do NOT touch RECORDINGS.md — the orchestrator writes it. Your job ends at the summary file; report the tracker row back instead (see the report format below).

Summary format requirements:
- The document title uses ## (h2), all section headings use ### (h3), and sub-sections use #### (h4). Never use # (h1).
- Start with a TLDR section at the very beginning
- Use clear headings and subheadings
- Use bullet points for key information
- Include sections: overview, key discussion points, decisions made, action items (if any), next steps (if applicable)
- Action Items MUST use checkbox format: - [ ] Action description -- Person, Timeline
  Do NOT use tables, bold-name lists (- **Name:** action), or numbered lists for action items.
  Always use checkboxes with double-dash separator for every action item.

SPECIAL FORMAT for interview transcripts (if the meeting is a candidate interview):
Use the interview template from the skill, with ### headings for all sections.

File naming:
- Extract date from filename (YYYYMMDD format at start)
- Create a concise, hyphenated topic name from the meeting content
- Example: 2025-10-16_daily-standup.md

After completing all steps, report:
- Source transcript filename
- Generated summary filename
- The exact RECORDINGS.md row for the orchestrator to add, one line, pipe-delimited:
  | [source filename] | [summary filename] | ✅ Completed | [today's date] |
  For a corrupted, empty, or too-short transcript, do not fabricate a summary: skip step 5 and return a row with the right status instead — `⚠️ Quality Issues` or `⚠️ Incomplete Recording` — with a short note (e.g. "N/A - fragment too short") where the summary filename would go.
```

The format block above is prescriptive on purpose. Two rules are load-bearing:

- **Action items are checkboxes with a `-- person, timeline` suffix — never tables or `- **Name:** task` bold-name lists.** Left to its own defaults the model drifts into prose, tables, or bold-name lists, none of which render as something you can actually tick off. Pinning one format keeps a batch of summaries consistent.
- **Headings are `##` for the title and `###` for sections — never `#`.** Models reach for `#` by default, but these summaries get embedded in larger docs where an h1 collides with the host document's structure. Stating it explicitly stops the drift.

### Step 3: Humanize output

After all subagents complete, run the [`humanizer`](../../../humanizer) skill over each generated summary to strip AI writing patterns before finalizing. Raw summaries tend to come back with the usual tells (inflated significance, rule-of-three, em-dash pileups); this pass removes them. Keep the register neutral and factual — these are minutes, not a place for personal voice.

### Step 4: Update `RECORDINGS.md` (orchestrator only)

The orchestrator writes the tracker, never the subagents, so there's no concurrent-write race.

1. Collect the row each subagent returned.
2. Read `RECORDINGS.md` and append every row to the end of the table in a single edit (or sequential edits in one turn). Never let two agents write this file at once.
3. Verify: each new source filename appears exactly once and the table wasn't clobbered — `grep -F` each filename and check the row count grew by the number of transcripts processed.

### Step 5: Report results

Once the tracker is updated, report: how many transcripts were processed, the list of generated summary files, confirmation that `RECORDINGS.md` got every row, and any errors.

## Summary templates

### Standard meeting format
```markdown
## Meeting Title

### TLDR
Brief 2-3 sentence summary of key takeaways

### Key Discussion Points
- Point 1
- Point 2
- Point 3

### Decisions Made
- Decision 1
- Decision 2

### Action Items
- [ ] Action item -- Person, Timeline
- [ ] Action item -- Person, Timeline

### Next Steps
What happens after this meeting
```

### Interview format
```markdown
## Candidate Interview: [Name] - [Position]

### TLDR
Brief summary of candidate and recommendation

### Candidate Background
Overview of experience and qualifications

### Technical Discussion
Key topics covered during interview

### Strong points demonstrated
- Strength 1
- Strength 2

### Points of growth
- Area 1
- Area 2

### Still to be clarified
- Question 1
- Question 2

### Comments
Additional observations and notes

### Decision (delete everything except for your rating):
No-go (-1)
Neutral (0)
Go (+1)
```

## Translation guidelines

When processing Russian transcripts, translate everything to English, but:

- Preserve original meaning and context, and keep technical terms accurate.
- **Keep proper nouns in their original form** — names, companies, products. Auto-translation tends to anglicise or mangle them (a surname turned into a common noun, a product name "helpfully" translated), so they're called out for explicit preservation.
- Clarify genuinely ambiguous phrases from context rather than translating them word-for-word.

## File organization

**Input:** meeting transcripts as `.txt` files in `rec/`, named `YYYYMMDD HHMM Transcription [LANG].txt`. The leading `YYYYMMDD` is what the summary date is derived from.

**Output:** one summary per meeting in `summaries/`, named `yyyy-mm-dd_meeting-topic.md`.

**Tracking:** `RECORDINGS.md` gets a new row per processed file — source filename, summary filename, ✅ Completed, and the processing date. This is what step 1 reads to skip already-done transcripts, so re-running the skill never reprocesses a meeting.

**Archive:** Step 0 keeps the working set small. Rows older than the cutoff move to `archive/RECORDINGS-archive.md`, and their transcripts move to `archive/rec/`, out of the `rec/` scan path. Summaries are never archived — they stay in `summaries/`.

A real transcript → summary pair lives in [`examples/`](./examples/).

## Anti-patterns

- **Don't process multiple transcripts in one context.** Shared context cross-contaminates summaries (attendees and decisions leak between meetings). One isolated subagent per transcript, always.
- **Don't format action items as tables, numbered lists, or `- **Name:** task` bold-name lists.** Only `- [ ] task -- person, timeline` checkboxes render as something actionable and scan consistently across a batch.
- **Don't title summaries with `#` (h1).** Use `##` for the title, `###` for sections — these notes get embedded in larger documents.
- **Don't translate proper nouns.** Names, companies, and products stay in their original form even when the rest is translated.
- **Don't skip the humanizer pass.** Raw model summaries carry AI tells; step 3 is not optional.
- **Don't reprocess completed transcripts.** Check `RECORDINGS.md` first and only handle files not already marked ✅ Completed.
- **Don't let subagents write `RECORDINGS.md`.** Concurrent writes to the shared tracker race and silently drop rows. Subagents return their row; the orchestrator writes them serially in step 4.
- **Don't scan `archive/` in step 1.** It reads `rec/` only. Pulling in archived transcripts reprocesses meetings that are already done.

## Known failure modes

- **Cross-meeting contamination** — decisions or attendees from one meeting surface in another's summary. Mitigation: one isolated subagent per transcript (see step 2).
- **Action-item format drift** — items come back as prose, a table, or bold-name lists you can't tick off. Mitigation: the prescriptive checkbox format in the subagent prompt.
- **Wrong / missing date** — a filename without a leading `YYYYMMDD` leaves the date ambiguous. Mitigation: date is parsed from the filename prefix; if it's absent, the subagent flags it rather than guessing.
- **Proper nouns mangled in translation** — names anglicised or product names translated. Mitigation: the explicit preserve-proper-nouns rule in the translation guidelines.
- **Interview misread as a standard meeting** — a candidate interview summarised with the wrong template. Mitigation: the subagent detects interview transcripts and switches to the interview format.
- **Lost tracker rows** — parallel subagents writing the shared `RECORDINGS.md` race, and some rows vanish (the meetings then look unprocessed and get redone). Mitigation: subagents return their row; the orchestrator writes all rows serially in step 4, then verifies each one landed.
- **Archived meeting reprocessed** — a row is archived but its transcript is left in `rec/` (or step 1 scans `archive/`), so the skill treats it as new. Mitigation: the archive script moves rows and transcripts together and checks the coupling on exit; step 1 reads `rec/` only.

## Tested with

- **Runtime:** Claude Code · model `claude-opus-4-8`.
- **Skill type:** prompt-driven workflow plus one bundled mechanical helper, `archive-old-recordings.py` (Step 0).
- **Last validated:** 2026-06-13 — processed the fictional onboarding-sync transcript in `examples/` end to end (standard template, checkbox action items, `##`/`###` headings) and ran the `humanizer` pass on the result.
- **Archive helper:** 2026-06-23 — verified on a scratch tree: correct month cutoff, idempotent no-op when nothing is old enough, rows and transcripts moved together, and the no-reprocessing invariant checked on exit.
