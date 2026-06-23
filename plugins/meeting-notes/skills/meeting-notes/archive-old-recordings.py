#!/usr/bin/env python3
"""Archive meeting recordings older than N months.

Keeps the live RECORDINGS.md tracker and the rec/ transcript folder small by
moving old entries into archive/. Tracker rows and transcript files are moved
together on the SAME date cutoff, preserving the invariant the meeting-notes
skill relies on:

    unprocessed transcript = a .txt in rec/ that has NO row in RECORDINGS.md

If a row were archived while its transcript stayed in rec/, the skill would
reprocess it. This script never breaks that coupling, and verifies it before
exiting.

Idempotent: re-running merges into the existing archive without duplicating
rows. Safe to run at the start of every processing session.

Usage:
    archive-old-recordings.py [--root DIR] [--months N] [--dry-run]

    --root     project root containing RECORDINGS.md, rec/ (default: cwd)
    --months   archive entries strictly older than this many months (default 3)
    --dry-run  report what would change without writing anything
"""
import argparse
import calendar
import re
import shutil
import sys
from datetime import date
from pathlib import Path

# A tracker data row: starts with '|', first cell begins with YYYYMMDD HHMM
ROW_RE = re.compile(r"^\|\s*(\d{8})\s+(\d{4})\b")


def months_ago(today: date, n: int) -> date:
    """Date n months before `today`, clamping the day to a valid value."""
    m, y = today.month - n, today.year
    while m <= 0:
        m += 12
        y -= 1
    day = min(today.day, calendar.monthrange(y, m)[1])
    return date(y, m, day)


def data_rows(text: str):
    """Yield (sortkey, source_filename, raw_line) for each tracker data row."""
    for line in text.splitlines():
        m = ROW_RE.match(line)
        if m:
            yield m.group(1) + m.group(2), line.split("|")[1].strip(), line


def build_archive(rows) -> str:
    rows = sorted(rows, key=lambda r: r[0])
    header = (
        "# Archived Meeting Recordings\n\n"
        "Entries moved out of the live [`RECORDINGS.md`](../RECORDINGS.md) tracker to "
        "keep the working set small. Summaries remain in `summaries/`; archived "
        "transcripts are in [`archive/rec/`](rec/), outside the `rec/` scan path, so "
        "the `meeting-notes` skill never reprocesses them.\n\n"
        "| Source File (archive/rec/) | Summary File (summaries/) | Status | Date Processed |\n"
        "|----------------------------|---------------------------|--------|----------------|\n"
    )
    return header + "\n".join(r[2] for r in rows) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description="Archive recordings older than N months.")
    ap.add_argument("--root", default=".", help="project root (default: cwd)")
    ap.add_argument("--months", type=int, default=3, help="age threshold in months")
    ap.add_argument("--dry-run", action="store_true", help="report only, no writes")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    tracker = root / "RECORDINGS.md"
    rec = root / "rec"
    archive = root / "archive"
    archive_rec = archive / "rec"
    archive_tracker = archive / "RECORDINGS-archive.md"

    if not tracker.exists():
        print(f"ERROR: {tracker} not found", file=sys.stderr)
        return 2

    cutoff = months_ago(date.today(), args.months).strftime("%Y%m%d")
    tag = "[dry-run] " if args.dry_run else ""
    print(f"{tag}Today {date.today():%Y-%m-%d}; archiving entries older than "
          f"{args.months} months (source date < {cutoff[:4]}-{cutoff[4:6]}-{cutoff[6:]}).")

    live_text = tracker.read_text()
    keep_lines, archived = [], []
    for line in live_text.splitlines(keepends=True):
        m = ROW_RE.match(line)
        if m and (m.group(1) + m.group(2)) < cutoff + "0000":
            archived.append((m.group(1) + m.group(2), line.split("|")[1].strip(), line.rstrip("\n")))
        else:
            keep_lines.append(line)

    if not archived:
        print("Nothing older than the cutoff. No changes.")
        return 0

    moved = [s for _, s, _ in archived if (rec / s).exists()]
    orphan = len(archived) - len(moved)
    print(f"{tag}Tracker rows to archive : {len(archived)}")
    print(f"{tag}Transcripts to move     : {len(moved)}")
    print(f"{tag}Rows with no transcript : {orphan} (already gone / N-A)")

    # Merge with any existing archive, dedupe by source filename
    existing = list(data_rows(archive_tracker.read_text())) if archive_tracker.exists() else []
    merged = {}
    for key, src, raw in existing + archived:
        merged[src] = (key, src, raw)

    if args.dry_run:
        print("[dry-run] No files written or moved.")
        return 0

    archive.mkdir(exist_ok=True)
    archive_rec.mkdir(exist_ok=True)
    tracker.write_text("".join(keep_lines))
    archive_tracker.write_text(build_archive(merged.values()))
    for _, src, _ in archived:
        srcpath = rec / src
        if srcpath.exists():
            shutil.move(str(srcpath), str(archive_rec / src))

    # Verify the coupling invariant: archiving must not strand a transcript by
    # removing its row while leaving the file in rec/. Such a file has no live
    # row and Step 1 would reprocess it. Note that *pending, never-processed*
    # transcripts also have no live row — but that's by design, not stranding, so
    # the check looks only at the rows we just archived (rec_now & archived), not
    # at every rowless .txt. After a clean run this set is empty because every
    # archived transcript was moved out of rec/.
    archived_sources = {src for _, src, _ in archived}
    live_sources = {src for _, src, _ in data_rows(tracker.read_text())}
    rec_now = {p.name for p in rec.glob("*.txt")} if rec.exists() else set()
    stranded = sorted(rec_now & archived_sources)
    print(f"rec/ now: {len(rec_now)} files; live tracker rows: {len(live_sources)}")
    if stranded:
        print(f"!! WARNING: {len(stranded)} archived transcript(s) still in rec/ "
              f"without a live row (would be reprocessed):", file=sys.stderr)
        for f in stranded:
            print("   -", f, file=sys.stderr)
        return 1
    print("OK: every archived transcript was moved out of rec/. No reprocessing risk.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
