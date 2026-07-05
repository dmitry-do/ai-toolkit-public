# 📝 meeting-notes

Turn raw meeting transcripts into clean, structured summaries you can actually read. Each transcript
is processed by its own isolated subagent, so one meeting never bleeds context into another.

## Install in Claude Code

```
/plugin marketplace add dmitry-do/ai-toolkit-public
/plugin install meeting-notes@ai-toolkit-public
```

## Install in Claude Web

Works on claude.ai over uploaded/pasted transcripts (no local `rec/` folder needed — see the
"On Claude Web" note in the skill). Package the skill folder:

```bash
scripts/package-skill.sh meeting-notes        # writes dist/meeting-notes-skill.zip
```

Then in claude.ai: **Customize → Skills → Add → Create skill → Upload a skill**, and select the zip.

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
- Optionally runs each summary through the [`humanizer`](https://github.com/blader/humanizer) skill as a final cleanup pass — only when that skill is installed and active.

## Usage

Run the command or just ask:

```
/meeting-notes
```

> "process the recordings in rec/" · "generate meeting notes"

- **Input:** `rec/*.txt`, named `YYYYMMDD HHMM Transcription [LANG].txt` (or uploaded transcripts on claude.ai).
- **Output:** `summaries/yyyy-mm-dd_topic.md`, tracked in `RECORDINGS.md`.
- **Archive:** entries older than three months move to `archive/` (rows + transcripts).

## Structure

```
plugins/meeting-notes/
├── .claude-plugin/plugin.json   # marketplace manifest
├── README.md                    # this file
└── skills/meeting-notes/        # this folder is what uploads to Claude Web
    ├── SKILL.md                 # workflow, templates, anti-patterns
    ├── archive-old-recordings.py # local archiving helper (unused on Claude Web)
    └── examples/                # a real transcript → summary

evals/meeting-notes/EVALS.md     # behavioral scenarios — NOT installed with the plugin
```

Optionally uses the [`humanizer`](https://github.com/blader/humanizer) skill for a final cleanup pass (Step 3) when it's installed — the plugin works fine without it.
Mine, MIT-licensed (see the root [LICENSE](../../LICENSE)).
