# Behavioral evals — `meeting-notes`

These check that the **skill behaves** — triggers on the right asks, isolates each transcript,
skips finished ones, and holds the output format (checkbox action items, `##`/`###` headings,
preserved proper nouns). This is a prompt-only skill, so there's no separate accuracy harness;
the worked example in [`examples/`](./examples/) is the reference output.

Each scenario is input → expected behavior → verdict criterion. Run them by hand, or wire the
trigger set at the bottom into `skill-creator`'s `scripts/run_loop.py`.

## Scenarios

### S1 — Triggers on a batch ask
- **Input:** "process the recordings in rec/" (or the `/meeting-notes` command)
- **Expected:** Skill triggers, reads `rec/` and `RECORDINGS.md`, and builds the unprocessed list before doing anything.
- **Verdict:** Pass if it enters the workflow and inventories first; fail if it ignores the ask or starts summarizing without checking `RECORDINGS.md`.

### S2 — One isolated subagent per transcript
- **Input:** Three unprocessed `.txt` files in `rec/`.
- **Expected:** Launches three subagents in parallel, each told it sees exactly one transcript. No shared context.
- **Verdict:** Pass if each transcript is handled in isolation; fail if it processes them in one context (where attendees/decisions can leak between meetings).

### S3 — Skips already-processed transcripts
- **Input:** Five files in `rec/`, two already marked ✅ Completed in `RECORDINGS.md`.
- **Expected:** Processes only the three new files; leaves the two completed summaries untouched.
- **Verdict:** Pass if completed files are skipped; fail if it reprocesses or overwrites them.

### S4 — Action items come out as checkboxes, not tables or bold-name lists
- **Input:** A transcript with several owner-assigned tasks.
- **Expected:** Every action item is `- [ ] task -- person, timeline`. No tables, no `- **Name:** task`, no numbered lists.
- **Verdict:** Pass if all items use the checkbox + double-dash format; fail on any table/bold-name/numbered rendering.

### S5 — Heading levels are `##`/`###`, never `#`
- **Input:** Any transcript.
- **Expected:** Document title is `##`, sections are `###` (sub-sections `####`). No `#` h1 anywhere.
- **Verdict:** Pass if no h1 appears; fail if the title or any section uses `#`.

### S6 — Interview transcript switches to the interview template
- **Input:** A candidate interview transcript.
- **Expected:** Detects the interview and uses the interview format (background, strengths, growth areas, still-to-clarify, decision), not the standard meeting template.
- **Verdict:** Pass if it uses the interview template; fail if it forces the standard layout onto an interview.

### S7 — Russian transcript is translated, proper nouns preserved
- **Input:** A `[RU]` transcript naming people, a company, and a product.
- **Expected:** Summary is in English; names, company, and product stay in their original form rather than being anglicised or translated.
- **Verdict:** Pass if the meaning is translated but proper nouns are intact; fail if a name/product gets translated into a common noun.

### S8 — Humanizer pass runs before finalizing
- **Input:** Any transcript that produces a first-draft summary with AI tells.
- **Expected:** Step 3 runs the `humanizer` skill over each summary before it's reported as done.
- **Verdict:** Pass if the finalized summary is humanized; fail if the raw draft is delivered.

### S9 — Filename with no date is flagged, not guessed
- **Input:** A transcript whose filename has no leading `YYYYMMDD`.
- **Expected:** The subagent flags the missing date instead of inventing one for the `yyyy-mm-dd_` filename.
- **Verdict:** Pass if it surfaces the ambiguity; fail if it silently fabricates a date.

## What broke and how I fixed it

Two real failures from using the skill; the prescriptive rules in `SKILL.md` exist because of them.

### F1 — Action items rendered as bold-name lists and tables
- **Symptom:** Across a batch, summaries formatted action items inconsistently — some as `- **Marcus:** draft the spec`, some as Markdown tables, some as prose. None were tickable, and scanning a week of meetings meant re-reading every layout.
- **Root cause:** With no format pinned, each subagent picked whatever the model defaulted to that run.
- **Fix:** Pin one format in the subagent prompt — `- [ ] task -- person, timeline` checkboxes, with tables/bold-name/numbered lists explicitly forbidden. The batch is now uniform and the items render as a real checklist.
- **Covered by:** scenario S4 and the action-item anti-pattern in `SKILL.md`.

### F2 — Meetings cross-contaminated when processed together
- **Symptom:** Running several transcripts in one context produced summaries where an action item or attendee from one meeting showed up in another's notes.
- **Root cause:** Shared context — the model carried details across transcripts it should have treated as unrelated.
- **Fix:** One isolated subagent per transcript, each told no other transcripts exist in its context. Contamination disappeared, and there's no need to `/clear` between files.
- **Covered by:** scenario S2 and the isolation anti-pattern in `SKILL.md`.

## Trigger-rate test set

For `skill-creator`'s `scripts/run_loop.py` (or any should-trigger / should-not harness). Goal:
high recall on the left, no false fires on the right. Tighten the `SKILL.md` `description` from
whichever side fails.

### Should trigger
1. "process the recordings in rec/"
2. "generate meeting notes"
3. "/meeting-notes"
4. "summarize the meetings in my rec folder"
5. "turn these meeting transcripts into notes"
6. "I dropped three transcripts in rec/, write them up"
7. "process the new interview transcripts"
8. "clean up the standup transcripts into summaries"
9. "make notes from yesterday's call transcript in rec/"
10. "pull the action items out of the meeting transcripts"

### Should NOT trigger (near-misses)
1. "transcribe this meeting recording" (audio → text — that's `audio-transcription`)
2. "summarize this article for me" (not a meeting transcript)
3. "take notes while I talk" (live note-taking, not a saved transcript)
4. "schedule a sync for next week" (calendar)
5. "what did we decide in the meeting?" (question over current context, no transcript file)
6. "draft an agenda for tomorrow's standup" (content generation)
7. "translate this document into English" (generic translation)
8. "summarize this paragraph I just pasted" (inline text, not the `rec/` batch)
9. "record this call" (recording)
10. "find the recording of last week's meeting" (file search)
