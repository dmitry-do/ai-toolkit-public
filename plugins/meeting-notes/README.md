# 📝 meeting-notes

Turn raw meeting transcripts into clean, structured summaries you can actually read. Each transcript
is processed by its own isolated subagent, so one meeting never bleeds context into another.

## Install

```
/plugin install meeting-notes@ai-toolkit
```

## What it does

- Archives entries older than three months before each run (Step 0), moving tracker rows and their transcripts together so `rec/` and `RECORDINGS.md` stay small and nothing already done gets reprocessed.
- Reads unprocessed `.txt` transcripts from a `rec/` folder and tracks what's done in `RECORDINGS.md`.
- Launches one subagent per transcript **in parallel**, each fully isolated — no cross-meeting
  contamination, no need to `/clear` between files.
- Writes a dated summary per meeting to `summaries/yyyy-mm-dd_topic.md` with a TLDR, discussion
  points, decisions, and checkbox action items (`- [ ] task -- person, timeline`).
- Detects interview transcripts and switches to an interview template (background, strengths,
  growth areas, decision).
- Translates Russian transcripts to English while preserving names, terms, and meaning.
- Runs each summary through the [`humanizer`](../humanizer) skill before finalizing.

## Usage

Run the command or just ask:

```
/meeting-notes
```

> "process the recordings in rec/" · "generate meeting notes"

## Input / output

- **Input:** `rec/*.txt`, named `YYYYMMDD HHMM Transcription [LANG].txt`.
- **Output:** `summaries/yyyy-mm-dd_topic.md`, tracked in `RECORDINGS.md`.
- **Archive:** entries older than three months move to `archive/` (rows + transcripts), keeping the working set small.

## Learn more

- Workflow, templates, and anti-patterns: [`skills/meeting-notes/SKILL.md`](./skills/meeting-notes/SKILL.md)
- Behavioral scenarios + trigger set: [`skills/meeting-notes/EVALS.md`](./skills/meeting-notes/EVALS.md)
- A real transcript → summary: [`skills/meeting-notes/examples/`](./skills/meeting-notes/examples/)

Mine, MIT-licensed (see the root [LICENSE](../../LICENSE)).
