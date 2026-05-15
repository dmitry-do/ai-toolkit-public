---
name: meeting-notes
description: Process meeting transcripts from rec/ folder into professional markdown summaries. Use when user wants to process meeting recordings, transcripts, or asks to generate meeting notes. Automatically invoked by /meeting-notes command.
---

# meeting-notes

Process meeting recordings into structured, professional summaries with complete isolation between transcripts.

## When to Use This Skill

- User runs `/meeting-notes` command
- User asks to "process meetings", "process recordings", or "generate meeting notes"
- User mentions unprocessed transcripts in rec/ folder

## Processing Workflow

### Step 1: Identify Unprocessed Transcripts

1. Read the `rec/` folder to get all .txt files
2. Read `RECORDINGS.md` to identify which files have already been processed (marked with ✅ Completed)
3. Create a list of unprocessed transcript files

### Step 2: Launch Isolated Subagents

For EACH unprocessed transcript file, launch a separate subagent using the Task tool with subagent_type="general-purpose". Launch ALL subagents in parallel in a SINGLE message with multiple Task tool calls.

**CRITICAL**: Each transcript MUST be processed by a separate subagent to prevent context contamination between different meetings.

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

### Step 3: Humanize Output

After all subagents complete, apply the `/humanizer` skill to each generated summary to remove AI writing patterns before finalizing.

### Step 4: Report Results

After all subagents complete, provide a summary report showing:
- How many transcripts were processed
- List of generated summary files
- Any errors or issues encountered

## Summary Templates

### Standard Meeting Format
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

### Interview Format
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

## Translation Guidelines

When processing Russian transcripts:
- Translate all content to English
- Preserve original meaning and context
- Maintain professional tone in translation
- Keep technical terms accurate
- Preserve proper nouns (names, companies, products)
- Clarify ambiguous phrases with context

## File Organization

**Input**:
- Meeting transcripts as `.txt` files in `rec/` folder
- Format: `YYYYMMDD HHMM Transcription [LANG].txt`

**Output**:
- Summary files in `summaries/` folder: `summaries/yyyy-mm-dd_meeting-topic.md`
- Tracker file: `RECORDINGS.md`

**Tracking**:
Update `RECORDINGS.md` with:
- Source transcript filename
- Generated summary filename
- ✅ Completed status
- Processing date

## Important Notes

- **Context Isolation**: Each transcript is processed by a separate subagent - no context leakage between meetings
- **Parallel Processing**: Launch all subagents in parallel for efficiency
- **Language Support**: Automatically detect and translate Russian content to English
- **Format Detection**: Automatically identify interview vs standard meeting format
- **Date Extraction**: Parse date from filename (YYYYMMDD format)
- **No Manual Cleanup**: Subagent isolation eliminates need for /clear between files
