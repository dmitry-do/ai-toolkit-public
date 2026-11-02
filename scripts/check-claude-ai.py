#!/usr/bin/env python3
"""
check-claude-ai.py - checks a plugin folder against rules claude.ai's plugin
upload enforces and `claude plugin validate` does not.

    python3 scripts/check-claude-ai.py plugins/<name>

Each rule here was a rejected upload:
- File paths: "Zip file contains path with invalid characters" (a space and
  brackets in an example file name). Allowed: letters, digits, . _ - + @ /
- SKILL.md description: "cannot contain XML tags" (`<format>`). Any < or > is
  refused here, to be safe. Also at most 1024 characters.
- SKILL.md name: lowercase letters, digits and hyphens, at most 64 characters,
  without "claude" or "anthropic".

Exit codes: 0 clean, 1 problems (printed one per line).
"""

import re
import sys
from pathlib import Path

PATH_OK = re.compile(r"[A-Za-z0-9._/@+-]+")
SKIP = {".DS_Store", "__pycache__"}


def description(frontmatter):
    """The description value, with YAML block scalars (| or >) folded to one line."""
    m = re.search(r"^description:[ \t]*(.*)$", frontmatter, re.M)
    if not m:
        return ""
    first = m.group(1).strip()
    if first[:1] in ("|", ">"):
        lines = []
        for line in frontmatter[m.end():].split("\n")[1:]:
            if line and not line[0].isspace():
                break
            lines.append(line.strip())
        return " ".join(l for l in lines if l)
    return first.strip("\"'")


def check(root):
    problems = []
    for p in sorted(root.rglob("*")):
        if any(part in SKIP for part in p.parts):
            continue
        rel = p.relative_to(root).as_posix()
        if not PATH_OK.fullmatch(rel):
            problems.append("path has characters claude.ai rejects: %s" % rel)
    for skill in sorted(root.glob("skills/*/SKILL.md")):
        where = skill.relative_to(root).as_posix()
        m = re.match(r"---\n(.*?)\n---\n", skill.read_text(encoding="utf-8"), re.S)
        if not m:
            problems.append("%s: no frontmatter" % where)
            continue
        fm = m.group(1)
        desc = description(fm)
        name = re.search(r"^name:[ \t]*[\"']?([^\"'\n]*)", fm, re.M)
        name = name.group(1).strip() if name else ""
        if not desc:
            problems.append("%s: empty description" % where)
        if "<" in desc or ">" in desc:
            problems.append("%s: description has < or > (claude.ai reads it as an XML tag)" % where)
        if len(desc) > 1024:
            problems.append("%s: description is %d characters, the limit is 1024" % (where, len(desc)))
        if not re.fullmatch(r"[a-z0-9-]{1,64}", name):
            problems.append("%s: name %r must be 1-64 lowercase letters, digits or hyphens" % (where, name))
        if "claude" in name or "anthropic" in name:
            problems.append("%s: name %r contains a reserved word" % (where, name))
    return problems


def main():
    if len(sys.argv) != 2:
        sys.exit("usage: check-claude-ai.py <plugin-dir>")
    problems = check(Path(sys.argv[1]))
    for p in problems:
        print(p)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
