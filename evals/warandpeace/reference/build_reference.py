#!/usr/bin/env python3
"""Build the Chapter I reference text from the proofread canonical markdown.

Source: `source_pages_1-11.md` — the Dole translation (1889 Crowell ed., pages 1–11,
Chapters I–III), OCR'd from page images and hand-corrected. Public domain.

The LibriVox recording (section 01) covers Chapter I only, so we extract just that:
everything between "### CHAPTER I." and "### CHAPTER II.", dropping page markers,
headers, and footnotes (editorial, not narrated), keeping the body and the read-aloud
note blockquote, and de-hyphenating the page-break word splits.

  python3 build_reference.py source_pages_1-11.md wap_v1_p1_ch1.txt
"""
from __future__ import annotations

import re
import sys


def slice_chapter_one(lines):
    start = next(i for i, ln in enumerate(lines) if re.match(r"^#+\s*CHAPTER\s+I\.", ln))
    end = next(i for i, ln in enumerate(lines) if i > start and re.match(r"^#+\s*CHAPTER\s+II\.", ln))
    return lines[start + 1:end]


def is_dropped(line):
    s = line.strip()
    if not s:
        return True
    if s == "---":
        return True
    if re.match(r"^\*\*\[p\.", s):       # page marker  **[p. N]**
        return True
    if re.match(r"^#{1,6}\s", s):        # any heading
        return True
    if re.match(r"^>\s*(\\?\*|\[)", s):  # footnote blockquote: > \* ...  or  > [cut off]
        return True
    return False


def clean_markdown(text):
    text = text.replace("\\", "")          # drop escapes (\*, \  etc.)
    text = re.sub(r"[*_]+", "", text)       # emphasis markers
    text = text.replace("†", "").replace("‡", "")  # footnote-ref daggers in body
    text = re.sub(r"^>\s*", "", text)       # leading blockquote marker on a kept quote
    return text.strip()


def main():
    if len(sys.argv) != 3:
        sys.exit("usage: build_reference.py <source_pages_1-11.md> <output.txt>")
    src, dst = sys.argv[1], sys.argv[2]
    lines = open(src, encoding="utf-8").read().splitlines()

    kept = [clean_markdown(ln) for ln in slice_chapter_one(lines) if not is_dropped(ln)]

    # join paragraphs; merge page-break hyphenation (a paragraph ending in "-")
    paragraphs = []
    for para in kept:
        if paragraphs and paragraphs[-1].endswith("-"):
            paragraphs[-1] = paragraphs[-1][:-1] + para
        else:
            paragraphs.append(para)

    text = "\n\n".join(p for p in paragraphs if p)
    text = re.sub(r"[ \t]+", " ", text)
    open(dst, "w", encoding="utf-8").write(text.rstrip() + "\n")
    print(f"wrote {dst}: {len(paragraphs)} paragraphs, {len(text.split())} words")


if __name__ == "__main__":
    main()
