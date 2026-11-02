#!/usr/bin/env python3
"""
edit_plan.py - make the next version of a markdown plan from a list of exact edits.

Long plans get revised many times (the Osaka plan reached v38). Each round used
to be a hand-written script: copy vN to vN+1, change the version in the title,
replace text that must match exactly once, then check that no link got lost.
This is that script, so the checks run every time.

    python3 scripts/edit_plan.py plan_v37.md edits.json
    python3 scripts/edit_plan.py plan_v37.md edits.json --out plan_v38.md
    python3 scripts/edit_plan.py plan_v37.md --compact-links      # no edits, only shrink links
    python3 scripts/edit_plan.py --compare plan_v37.md plan_v38.md  # link diff only

edits.json is a list. Each edit replaces `old` with `new`. `count` is how many
times `old` must occur (default 1). If any edit does not match its count, the
script stops and writes nothing:

    [
      {"old": "Maples by the river.", "new": "Do not skip it: the maples are red."},
      {"old": "(drop?)", "new": "", "count": 2}
    ]

What it does:
- Writes vN+1 next to vN (from `_vN` in the file name), unless --out is given.
- Changes `vN` to `vN+1` in the first heading line.
- Applies the edits in order. Each one sees the result of the edit before it.
- Prints the link diff: links removed, links added, and repeated links that lost
  a copy. A dropped place loses its link on purpose. A lost repeat usually is not.
- Prints the size against the 65,536-byte Telegram limit.

--compact-links shortens Google Maps search links. It writes `+` for spaces and,
when the link has a query_place_id, cuts the query text to three words. The place
ID decides where the link goes, and the query is only a fallback. The script
confirms that the set of place IDs is the same before and after.

Exit codes: 0 written, 1 an edit did not match or the place IDs changed.
"""

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import parse_qsl, quote_plus, unquote_plus, urlsplit

LIMIT = 65536
LINK_RE = re.compile(r"\]\((https?://[^)\s]+)\)")
MAPS_RE = re.compile(r"https://www\.google\.com/maps/search/\?[^)\s]+")
VERSION_RE = re.compile(r"_v(\d+)(?=[._-])")


def links(text):
    return Counter(LINK_RE.findall(text))


def place_ids(text):
    out = Counter()
    for url in MAPS_RE.findall(text):
        for k, v in parse_qsl(urlsplit(url).query):
            if k == "query_place_id":
                out[v] += 1
    return out


def compact(url):
    parts = urlsplit(url)
    params = parse_qsl(parts.query, keep_blank_values=True)
    has_id = any(k == "query_place_id" for k, _ in params)
    out = []
    for k, v in params:
        if k == "query":
            words = unquote_plus(v).split()
            if has_id:
                words = words[:3]
            v = quote_plus(" ".join(words), safe="")
        else:
            v = quote_plus(v, safe="")
        out.append("%s=%s" % (k, v))
    return "%s://%s%s?%s" % (parts.scheme, parts.netloc, parts.path, "&".join(out))


def link_diff(before, after):
    a, b = links(before), links(after)
    removed = sorted(u for u in a if u not in b)
    added = sorted(u for u in b if u not in a)
    fewer = sorted(u for u in a if u in b and b[u] < a[u])
    print("Links: %d before, %d after" % (sum(a.values()), sum(b.values())))
    for title, items in (("removed", removed), ("added", added),
                         ("repeat lost a copy", fewer)):
        if items:
            print("  %s (%d):" % (title, len(items)))
            for u in items[:20]:
                print("    %s" % u)
            if len(items) > 20:
                print("    ... and %d more" % (len(items) - 20))
    if fewer:
        print("  Check the repeats: a place that stays in the plan keeps every link.")


def size_line(path):
    n = path.stat().st_size
    state = "OK" if n <= LIMIT else "OVER by %s" % format(n - LIMIT, ",")
    print("Size: %s bytes of %s (%s)" % (format(n, ","), format(LIMIT, ","), state))


def next_path(src):
    m = list(VERSION_RE.finditer(src.name))
    if not m:
        sys.exit("No _vN in %s. Give --out." % src.name)
    m = m[-1]
    n = int(m.group(1))
    name = src.name[:m.start()] + "_v%d" % (n + 1) + src.name[m.end():]
    return src.with_name(name), n


def main():
    ap = argparse.ArgumentParser(description="Make the next version of a markdown plan.")
    ap.add_argument("src", nargs="?", help="current version, for example plan_v37.md")
    ap.add_argument("edits", nargs="?", help="JSON list of {old, new, count}")
    ap.add_argument("--out", help="output file (default: the _vN+1 name next to src)")
    ap.add_argument("--compact-links", action="store_true",
                    help="shorten Google Maps links, keeping every place ID")
    ap.add_argument("--compare", nargs=2, metavar=("OLD", "NEW"),
                    help="only print the link diff between two files")
    args = ap.parse_args()

    if args.compare:
        old, new = (Path(p) for p in args.compare)
        link_diff(old.read_text(encoding="utf-8"), new.read_text(encoding="utf-8"))
        size_line(new)
        return 0

    if not args.src or (not args.edits and not args.compact_links):
        ap.error("give src and edits, or src and --compact-links, or --compare")
    src = Path(args.src)
    text = src.read_text(encoding="utf-8")
    if args.out:
        dst, n = Path(args.out), None
        m = list(VERSION_RE.finditer(src.name))
        if m:
            n = int(m[-1].group(1))
    else:
        dst, n = next_path(src)
    if dst.resolve() == src.resolve():
        sys.exit("--out is the source file. Every version stays, so pick a new name.")

    t = text
    if n is not None:
        lines = t.split("\n")
        for i, line in enumerate(lines):
            if line.startswith("#"):
                lines[i] = re.sub(r"\bv%d\b" % n, "v%d" % (n + 1), line)
                break
        t = "\n".join(lines)

    edits = []
    if args.edits:
        edits = json.loads(Path(args.edits).read_text(encoding="utf-8"))
        if not isinstance(edits, list):
            sys.exit("edits.json must be a list of {old, new, count}")
    problems = []
    for i, e in enumerate(edits, 1):
        old, new, want = e.get("old"), e.get("new", ""), int(e.get("count", 1))
        if not old:
            problems.append("edit %d has no old text" % i)
            continue
        found = t.count(old)
        if found != want:
            problems.append("edit %d: expected %d, found %d: %r" % (i, want, found, old[:70]))
            continue
        t = t.replace(old, new)
    if problems:
        print("Nothing written. Fix these edits first:")
        for p in problems:
            print("  " + p)
        return 1

    edited = t
    if args.compact_links:
        ids_before = place_ids(t)
        t = MAPS_RE.sub(lambda m: compact(m.group(0)), t)
        if place_ids(t) != ids_before:
            print("Nothing written: link compaction changed the place IDs.")
            return 1

    dst.write_text(t, encoding="utf-8")
    print("Wrote %s (%d edit(s))" % (dst, len(edits)))
    # The diff compares the edits only. Compacted links are new strings for the
    # same places, so listing them as removed and added would bury real losses.
    link_diff(text, edited)
    if args.compact_links:
        saved = len(edited.encode("utf-8")) - len(t.encode("utf-8"))
        print("Compacted Google Maps links: %s bytes saved, place IDs unchanged"
              % format(saved, ","))
    size_line(dst)
    return 0


if __name__ == "__main__":
    sys.exit(main())
