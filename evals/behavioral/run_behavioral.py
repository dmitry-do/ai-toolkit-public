#!/usr/bin/env python3
"""Trigger-rate harness for the own skills (audio-transcription, meeting-notes).

The WER harness under ``evals/`` proves a *script* is accurate. This proves a *skill
triggers* — high recall on phrasings that should fire it, no false fires on the
near-misses that should not. Skills measurably under-trigger, and the SKILL.md
``description`` is where that gets fixed; this measures which side is failing.

It is deliberately small (the centerpiece the spec asks for, not a productionised
platform): one script plus per-skill JSON in ``scenarios/``. It is runtime-agnostic —
the *responder* is a swappable command, so the same scenarios can be pointed at
Claude Code, Codex, or OpenCode (the seed of a portability study).

  # deterministic, no model — checks every scenario file is well-formed and balanced
  python3 run_behavioral.py --validate

  # prove the scoring math end-to-end with a built-in oracle responder (no model)
  python3 run_behavioral.py --self-test

  # live: ask a responder "would this skill fire?" for each phrasing and score it
  python3 run_behavioral.py --run --responder './responders/claude_trigger.sh {skill}'

Responder contract: a command that receives the user phrasing on stdin and prints one
JSON object to stdout: {"fired": true|false}. ``{skill}`` / ``{desc}`` in the command
string are substituted per scenario file. See README.md for a ``claude -p`` recipe.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCENARIOS_DIR = HERE / "scenarios"
RESULTS_DIR = HERE / "results"


# ---------------------------------------------------------------- loading -----

def load_scenarios(path):
    """Load and parse one scenario JSON file (raises on malformed JSON)."""
    return json.loads(Path(path).read_text(encoding="utf-8"))


def discover(scenarios_dir=SCENARIOS_DIR):
    return sorted(Path(scenarios_dir).glob("*.json"))


# ------------------------------------------------------------- validation -----

def validate_scenarios(data):
    """Return a list of human-readable problems; empty list means valid.

    A scenario file must name a skill and carry a balanced trigger set so recall
    (should-fire) and false-fire rate (should-not) are measured on equal footing.
    """
    problems = []
    if not isinstance(data, dict):
        return ["top level is not an object"]

    skill = data.get("skill")
    if not skill or not isinstance(skill, str):
        problems.append("missing or non-string 'skill'")

    triggers = data.get("triggers")
    if not isinstance(triggers, dict):
        return problems + ["missing 'triggers' object"]

    fire = triggers.get("should_fire")
    nofire = triggers.get("should_not_fire")
    for name, items in (("should_fire", fire), ("should_not_fire", nofire)):
        if not isinstance(items, list) or not items:
            problems.append("triggers.%s must be a non-empty list" % name)
        elif not all(isinstance(s, str) and s.strip() for s in items):
            problems.append("triggers.%s has empty/non-string entries" % name)

    if isinstance(fire, list) and isinstance(nofire, list):
        if len(fire) != len(nofire):
            problems.append(
                "unbalanced set: %d should_fire vs %d should_not_fire "
                "(keep them equal so the rates compare)" % (len(fire), len(nofire))
            )
        seen = {}
        for side, items in (("should_fire", fire), ("should_not_fire", nofire)):
            for s in items:
                key = s.strip().lower()
                if key in seen:
                    problems.append(
                        "phrase appears in both/again: %r (%s & %s)"
                        % (s, seen[key], side)
                    )
                seen[key] = side
    return problems


# ---------------------------------------------------------------- scoring -----

def confusion(fired_on_should, fired_on_shouldnot):
    """Build a confusion matrix from two lists of booleans (did the skill fire?)."""
    tp = sum(1 for f in fired_on_should if f)
    fn = sum(1 for f in fired_on_should if not f)
    fp = sum(1 for f in fired_on_shouldnot if f)
    tn = sum(1 for f in fired_on_shouldnot if not f)
    return {"tp": tp, "fn": fn, "fp": fp, "tn": tn}


def _ratio(num, den):
    return num / den if den else 0.0


def metrics(c):
    """Precision/recall/F1 plus the two rates that matter for triggering."""
    tp, fn, fp, tn = c["tp"], c["fn"], c["fp"], c["tn"]
    precision = _ratio(tp, tp + fp)
    recall = _ratio(tp, tp + fn)                 # trigger rate on should-fire
    f1 = _ratio(2 * precision * recall, precision + recall)
    return {
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "trigger_rate": recall,
        "false_fire_rate": _ratio(fp, fp + tn),  # fp on should-not
        "accuracy": _ratio(tp + tn, tp + tn + fp + fn),
    }


# -------------------------------------------------------------- responder -----

def oracle_responder(skill, desc, prompt):
    """Built-in keyword responder for --self-test only (no model).

    Fires when the prompt shares a salient token with the skill name. Good enough
    to drive the scoring math deterministically; never used for real measurement.
    """
    keys = {
        "audio-transcription": ("transcribe", "transcript", "caption", "recording", "voice memo"),
        "meeting-notes": ("meeting note", "rec/", "/meeting-notes", "transcripts into", "action items out"),
    }.get(skill, ())
    low = prompt.lower()
    return any(k in low for k in keys)


def shell_responder(cmd, skill, desc, prompt):
    """Run an external responder command, return its 'fired' boolean.

    The prompt is fed on stdin; {skill}/{desc} are substituted into the command.
    """
    filled = cmd.replace("{skill}", skill).replace("{desc}", desc)
    proc = subprocess.run(
        filled, shell=True, input=prompt, capture_output=True, text=True, timeout=120,
    )
    out = proc.stdout.strip()
    # A failed or rate-limited call must not score as "not fired": empty stdout or a
    # non-zero exit would otherwise count as a silent false negative.
    if proc.returncode != 0 or not out:
        raise SystemExit(
            "responder failed (exit %d) for %r:\n%s%s"
            % (proc.returncode, prompt, proc.stdout, proc.stderr)
        )
    try:
        payload = json.loads(out.splitlines()[-1]) if out else {}
    except (ValueError, IndexError):
        raise SystemExit(
            "responder did not return JSON for %r:\n%s%s" % (prompt, proc.stdout, proc.stderr)
        )
    return bool(payload.get("fired"))


# ------------------------------------------------------------------ runs -------

def run_one(data, responder):
    """Score one scenario file; responder(prompt)->bool. Returns a result dict."""
    skill = data["skill"]
    desc = data.get("description", "")
    fire = data["triggers"]["should_fire"]
    nofire = data["triggers"]["should_not_fire"]

    fired_should = [responder(skill, desc, p) for p in fire]
    fired_shouldnot = [responder(skill, desc, p) for p in nofire]
    c = confusion(fired_should, fired_shouldnot)
    m = metrics(c)
    misses = [p for p, f in zip(fire, fired_should) if not f]
    false_fires = [p for p, f in zip(nofire, fired_shouldnot) if f]
    return {
        "skill": skill,
        "counts": {"should_fire": len(fire), "should_not_fire": len(nofire)},
        "confusion": c,
        "metrics": m,
        "misses": misses,
        "false_fires": false_fires,
    }


def format_report(result):
    m = result["metrics"]
    lines = ["", "%s" % result["skill"], "-" * len(result["skill"])]
    lines.append(
        "trigger rate (recall) %5.0f%%   false-fire rate %5.0f%%   F1 %.2f"
        % (m["trigger_rate"] * 100, m["false_fire_rate"] * 100, m["f1"])
    )
    c = result["confusion"]
    lines.append("tp=%d fn=%d  fp=%d tn=%d" % (c["tp"], c["fn"], c["fp"], c["tn"]))
    if result["misses"]:
        lines.append("  under-triggered on:")
        lines += ["    - %s" % p for p in result["misses"]]
    if result["false_fires"]:
        lines.append("  falsely fired on:")
        lines += ["    - %s" % p for p in result["false_fires"]]
    if not result["misses"] and not result["false_fires"]:
        lines.append("  clean: every should-fire fired, every should-not held.")
    return "\n".join(lines)


# ------------------------------------------------------------------- CLI -------

def cmd_validate(files):
    ok = True
    for f in files:
        try:
            data = load_scenarios(f)
        except ValueError as exc:
            print("FAIL %s: invalid JSON (%s)" % (f.name, exc))
            ok = False
            continue
        problems = validate_scenarios(data)
        if problems:
            ok = False
            print("FAIL %s:" % f.name)
            for p in problems:
                print("   - %s" % p)
        else:
            t = data["triggers"]
            print("ok   %s  (%d should-fire / %d should-not)"
                  % (f.name, len(t["should_fire"]), len(t["should_not_fire"])))
    return ok


def cmd_self_test(files):
    print("self-test: scoring the scenarios with the built-in oracle responder")
    all_ok = True
    for f in files:
        data = load_scenarios(f)
        result = run_one(data, oracle_responder)
        print(format_report(result))
        # the oracle is only a sanity check on the wiring, not the skill's real
        # description; we assert the math is internally consistent.
        c, m = result["confusion"], result["metrics"]
        n = sum(c.values())
        assert n == result["counts"]["should_fire"] + result["counts"]["should_not_fire"]
        assert 0.0 <= m["trigger_rate"] <= 1.0 and 0.0 <= m["false_fire_rate"] <= 1.0
    print("\nself-test: scoring math consistent across all scenario files.")
    return all_ok


def cmd_run(files, responder_cmd, out_dir):
    def responder(skill, desc, prompt):
        return shell_responder(responder_cmd, skill, desc, prompt)

    stamp = date.today().isoformat()
    results = []
    for f in files:
        data = load_scenarios(f)
        result = run_one(data, responder)
        print(format_report(result))
        results.append(result)
    if out_dir:
        Path(out_dir).mkdir(parents=True, exist_ok=True)
        out = Path(out_dir) / ("%s-triggers.json" % stamp)
        payload = {"date": stamp, "responder": responder_cmd, "results": results}
        out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print("\nwrote %s" % out)
    return True


def parse_args(argv):
    p = argparse.ArgumentParser(description="Trigger-rate harness for the own skills.")
    p.add_argument("--validate", action="store_true", help="check scenario files are well-formed + balanced (no model)")
    p.add_argument("--self-test", action="store_true", help="score with the built-in oracle responder (no model)")
    p.add_argument("--run", action="store_true", help="score live via --responder")
    p.add_argument("--responder", default=None, help="command; prompt on stdin, prints {\"fired\":bool}; {skill}/{desc} substituted")
    p.add_argument("--skill", default=None, help="limit to one skill (scenario filename stem)")
    p.add_argument("--scenarios", default=str(SCENARIOS_DIR), help="scenarios dir")
    p.add_argument("--out", default=str(RESULTS_DIR), help="where --run writes its dated JSON (use '' to skip)")
    return p.parse_args(argv)


def main(argv):
    args = parse_args(argv)
    files = discover(args.scenarios)
    if args.skill:
        files = [f for f in files if f.stem == args.skill]
    if not files:
        print("no scenario files found in %s" % args.scenarios)
        return 1

    if args.run:
        if not args.responder:
            print("--run needs --responder CMD")
            return 2
        return 0 if cmd_run(files, args.responder, args.out or None) else 1
    if args.self_test:
        return 0 if cmd_self_test(files) else 1
    # default: validate
    return 0 if cmd_validate(files) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
