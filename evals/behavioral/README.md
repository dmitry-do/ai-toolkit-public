# Behavioral evals — trigger rate

The WER harness one level up proves a *script* is accurate. This harness proves a *skill
triggers*: high recall on phrasings that should fire it, no false fires on the near-misses
that should not. Skills measurably under-trigger, and the SKILL.md `description` is where
that gets fixed — this measures which side is failing.

One script plus per-skill JSON in `scenarios/` (10 should-fire / 10 should-not each, kept
balanced so the two rates compare). The manual, richer behavior scenarios live in the
per-plugin `evals/<plugin>/EVALS.md` files; this harness automates just the trigger axis.

## Commands

```sh
# deterministic, no model — checks every scenario file is well-formed and balanced
python3 run_behavioral.py --validate

# prove the scoring math end-to-end with a built-in oracle responder (no model)
python3 run_behavioral.py --self-test

# live: ask a responder "would this skill fire?" for each phrasing and score it
python3 run_behavioral.py --run --responder './responders/claude_trigger.sh {skill}'

# one skill only
python3 run_behavioral.py --run --skill meeting-notes --responder './responders/claude_trigger.sh {skill}'
```

`--run` writes a dated JSON (confusion matrix, metrics, the exact misses and false fires)
to `results/` — raw output is gitignored and regenerable; the numbers worth keeping go in
the Results section below.

## The responder

A responder is any command that reads one user phrasing on stdin and prints
`{"fired": true|false}` as its last stdout line. `{skill}` / `{desc}` in the `--responder`
string are substituted per scenario file. Swapping the responder points the same scenarios
at another runtime (Codex, OpenCode) — the seed of a portability study.

`responders/claude_trigger.sh` is the Claude recipe: it asks `claude -p` whether Claude
Code would invoke the skill, given the skill name and description, and normalizes the reply
to strict JSON. It reads the description from `scenarios/<skill>.json` itself (so no free
text crosses the shell command line) and picks its model from `CLAUDE_TRIGGER_MODEL`
(default `haiku` — cheap smoke runs; rerun with your daily-driver model for numbers you
intend to keep):

```sh
CLAUDE_TRIGGER_MODEL=sonnet python3 run_behavioral.py --run \
  --responder './responders/claude_trigger.sh {skill}'
```

Caveat: each scenario file carries a snapshot of the skill's description. If the SKILL.md
frontmatter changes, sync the snapshot or the measurement drifts from what ships.

## Results

| Date | Model | Skill | Trigger rate | False-fire rate | F1 |
| --- | --- | --- | --- | --- | --- |
| 2026-07-06 | haiku | audio-transcription | 100% (10/10) | 0% (0/10) | 1.00 |
| 2026-07-06 | haiku | meeting-notes | 100% (10/10) | 0% (0/10) | 1.00 |
| 2026-08-21 | haiku | trip-plan | 100% (10/10) | 0% (0/10) | 1.00 |

A clean sweep on the current descriptions. The should-not sets hold the judge honest
(mp3→wav conversion, diarization, voiceover generation all correctly refused), but a
perfect score also means these phrasings no longer discriminate — when a description
changes, add the new borderline phrasings before trusting the next run.
