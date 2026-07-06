#!/bin/sh
# Responder for run_behavioral.py — asks `claude -p` whether a skill would fire.
#
# Contract (run_behavioral.py): the user phrasing arrives on stdin; print one JSON
# object {"fired": true|false} as the last stdout line. Canonical invocation:
#
#   python3 run_behavioral.py --run --responder './responders/claude_trigger.sh {skill}'
#
# $1 is the skill name; the description is read from scenarios/<skill>.json here,
# not passed via {desc}, so free text never crosses the shell command line.
# CLAUDE_TRIGGER_MODEL picks the model (default: haiku — cheap smoke runs; rerun
# with your daily-driver model for numbers you intend to keep).
set -eu

skill="$1"
model="${CLAUDE_TRIGGER_MODEL:-haiku}"
here="$(cd "$(dirname "$0")" && pwd)"
phrasing="$(cat)"

desc="$(python3 -c 'import json, sys; print(json.load(open(sys.argv[1]))["description"])' \
    "$here/../scenarios/$skill.json")"

reply="$(claude -p --model "$model" "You are Claude Code deciding whether to invoke an installed skill for a user message.

Skill: $skill
Skill description: $desc

User message: \"$phrasing\"

Would you invoke this skill for that message? Answer with exactly one line of JSON and nothing else: {\"fired\": true} or {\"fired\": false}" </dev/null)"

# Normalize: pull the verdict out of the reply, emit strict JSON for the harness.
printf '%s\n' "$reply" | python3 -c '
import json, re, sys
text = sys.stdin.read()
m = re.search(r"\{[^{}]*\"fired\"[^{}]*\}", text)
if not m:
    sys.exit("no {\"fired\": ...} JSON in responder reply:\n" + text)
print(json.dumps({"fired": bool(json.loads(m.group(0))["fired"])}))
'
