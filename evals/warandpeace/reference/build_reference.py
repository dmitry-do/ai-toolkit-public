#!/usr/bin/env python3
"""Extract and clean the Dole-translation reference text for War & Peace
Vol 1, Part 1, Chapter 1 from the Internet Archive OCR scan.

Source (public domain, Nathan Haskell Dole translation):
  https://archive.org/details/warandpeace01dolegoog
  full text: .../warandpeace01dolegoog_djvu.txt

Download once, then run:
  curl -sL https://archive.org/download/warandpeace01dolegoog/warandpeace01dolegoog_djvu.txt -o wap_dole.txt
  python3 build_reference.py wap_dole.txt wap_v1_p1_ch1.txt

The OCR is moderately noisy; this script does structural cleanup (de-hyphenation,
footnote/header/page-number removal, whitespace collapse) plus a few obvious OCR
fixes. Residual single-character OCR errors remain, so absolute WER computed against
this reference overstates ASR error — inspect the diff to attribute errors. Relative
comparisons between transcription methods are unaffected (shared reference).
"""
from __future__ import annotations

import re
import sys

# Targeted OCR fixes for Chapter 1 (sparse, obvious substitutions).
OCR_FIXES = {
    "Wkll": "Well",
    "ray friend": "my friend",
    "caJl": "call",
    "inon Prince": "mon Prince",
    "Annbtte Sen brer": "Annette Scherer",
    "grippe^": "grippe",
}


def slice_chapter(lines, start_heading=r"^\s*CHAPTER\s+I\.\s*$", end_heading=r"^\s*CHAPTER\s+II\."):
    start = next(i for i, ln in enumerate(lines) if re.match(start_heading, ln))
    end = next(i for i, ln in enumerate(lines) if i > start and re.match(end_heading, ln))
    return lines[start + 1:end]  # drop the "CHAPTER I." heading itself


def drop_footnotes_and_headers(lines):
    """Remove translator footnote blocks, running headers, and page numbers."""
    out = []
    in_footnote = False
    for ln in lines:
        if in_footnote:
            # multi-line footnote ends at the "— N. H. D." signature, a line ending
            # in "*", or a blank line (safety net so we never swallow the chapter body).
            if re.search(r"N\.\s*H\.\s*D", ln) or ln.rstrip().endswith("*"):
                in_footnote = False
                continue
            if not ln.strip():
                in_footnote = False
                out.append(ln)
            continue
        if re.match(r"^\s*\*", ln):  # footnote starts with "*"
            # self-contained on one line (signed, or French note ending in "*")?
            if not (re.search(r"N\.\s*H\.\s*D", ln) or ln.rstrip().endswith("*")):
                in_footnote = True
            continue
        # French footnotes use bullet/dagger markers (OCR renders them •, ‡, ♦, or a
        # lone "t" for †). They are editorial, not narrated. Body dialogue lines that
        # happen to start with a stray "•" contain "said", so guard on that.
        if (re.match(r"^\s*[•‡♦]", ln) or re.match(r"^\s*t\s{2,}", ln)) and "said" not in ln:
            continue
        stripped = ln.strip()
        if re.search(r"WAR\s+AND\s+PEACE", stripped):
            continue
        if re.match(r"^VOL\.", stripped):
            continue
        if re.match(r"^[\dIlxXVi.\-—\s]+$", stripped) and stripped:  # page numbers / stray roman/garbage
            continue
        if re.search(r"Digitized by|Google", stripped):
            continue
        out.append(ln)
    return out


def dehyphenate_and_join(lines):
    """Join line-break hyphenation (word-\\nword) and collapse to paragraphs."""
    paragraphs = []
    buf = ""
    for ln in lines:
        if not ln.strip():
            if buf.strip():
                paragraphs.append(buf.strip())
            buf = ""
            continue
        piece = ln.strip()
        if buf.endswith("-") and not buf.endswith("--"):
            buf = buf[:-1] + piece  # join the split word, no space
        elif buf:
            buf = buf + " " + piece
        else:
            buf = piece
    if buf.strip():
        paragraphs.append(buf.strip())
    return paragraphs


def apply_ocr_fixes(text):
    for bad, good in OCR_FIXES.items():
        text = text.replace(bad, good)
    return text


def main():
    if len(sys.argv) != 3:
        sys.exit("usage: build_reference.py <djvu.txt> <output.txt>")
    src, dst = sys.argv[1], sys.argv[2]
    with open(src, encoding="utf-8", errors="replace") as fh:
        lines = fh.read().splitlines()

    chapter = slice_chapter(lines)
    chapter = drop_footnotes_and_headers(chapter)
    paragraphs = dehyphenate_and_join(chapter)
    text = "\n\n".join(paragraphs)
    text = re.sub(r"[ \t]+", " ", text)  # collapse runs of spaces
    text = apply_ocr_fixes(text)

    with open(dst, "w", encoding="utf-8") as fh:
        fh.write(text.rstrip() + "\n")
    print(f"wrote {dst}: {len(paragraphs)} paragraphs, {len(text.split())} words")


if __name__ == "__main__":
    main()
