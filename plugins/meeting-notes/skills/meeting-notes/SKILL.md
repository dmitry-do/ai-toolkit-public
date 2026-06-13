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

### Step 1: Identify unprocessed transcripts

1. Read the `rec/` folder to get all `.txt` files.
2. Read `RECORDINGS.md` to see which files are already done (marked ✅ Completed).
3. Build the list of unprocessed transcripts.

### Step 2: Launch isolated subagents

For each unprocessed transcript, launch a separate subagent with the Task tool (`subagent_type="general-purpose"`). Launch all of them in parallel, in a single message with multiple Task calls.

**One subagent per transcript is the whole point, not an optimization.** When meetings shared a context, summaries cross-contaminated — attendees, decisions, and action items from one meeting leaked into another's notes. Isolation is the fix: each subagent sees exactly one transcript and nothing else.

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
6. Update RECORDINGS.md by adding a new row with: source filename, summary filename, ✅ Completed status, and today's date

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
- Brief confirmation that RECORDINGS.md was updated
```

The format block above is prescriptive on purpose. Two rules are load-bearing:

- **Action items are checkboxes with a `-- person, timeline` suffix — never tables or `- **Name:** task` bold-name lists.** Left to its own defaults the model drifts into prose, tables, or bold-name lists, none of which render as something you can actually tick off. Pinning one format keeps a batch of summaries consistent.
- **Headings are `##` for the title and `###` for sections — never `#`.** Models reach for `#` by default, but these summaries get embedded in larger docs where an h1 collides with the host document's structure. Stating it explicitly stops the drift.

### Step 3: Humanize output

After all subagents complete, run the [`humanizer`](../../../humanizer) skill over each generated summary to strip AI writing patterns before finalizing. Raw summaries tend to come back with the usual tells (inflated significance, rule-of-three, em-dash pileups); this pass removes them.

### Step 4: Report results

After all subagents complete, report: how many transcripts were processed, the list of generated summary files, and any errors.

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

A real transcript → summary pair lives in [`examples/`](./examples/).

## Anti-patterns

- **Don't process multiple transcripts in one context.** Shared context cross-contaminates summaries (attendees and decisions leak between meetings). One isolated subagent per transcript, always.
- **Don't format action items as tables, numbered lists, or `- **Name:** task` bold-name lists.** Only `- [ ] task -- person, timeline` checkboxes render as something actionable and scan consistently across a batch.
- **Don't title summaries with `#` (h1).** Use `##` for the title, `###` for sections — these notes get embedded in larger documents.
- **Don't translate proper nouns.** Names, companies, and products stay in their original form even when the rest is translated.
- **Don't skip the humanizer pass.** Raw model summaries carry AI tells; step 3 is not optional.
- **Don't reprocess completed transcripts.** Check `RECORDINGS.md` first and only handle files not already marked ✅ Completed.

## Known failure modes

- **Cross-meeting contamination** — decisions or attendees from one meeting surface in another's summary. Mitigation: one isolated subagent per transcript (see step 2).
- **Action-item format drift** — items come back as prose, a table, or bold-name lists you can't tick off. Mitigation: the prescriptive checkbox format in the subagent prompt.
- **Wrong / missing date** — a filename without a leading `YYYYMMDD` leaves the date ambiguous. Mitigation: date is parsed from the filename prefix; if it's absent, the subagent flags it rather than guessing.
- **Proper nouns mangled in translation** — names anglicised or product names translated. Mitigation: the explicit preserve-proper-nouns rule in the translation guidelines.
- **Interview misread as a standard meeting** — a candidate interview summarised with the wrong template. Mitigation: the subagent detects interview transcripts and switches to the interview format.

## Tested with

- **Runtime:** Claude Code · model `claude-opus-4-8`.
- **Skill type:** prompt-only (no bundled script); validated by running the full workflow.
- **Last validated:** 2026-06-13 — processed the fictional onboarding-sync transcript in `examples/` end to end (standard template, checkbox action items, `##`/`###` headings) and ran the `humanizer` pass on the result.
