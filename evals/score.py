#!/usr/bin/env python3
"""Self-contained WER/CER scorer for transcription quality (no dependencies).

Compares a hypothesis transcript against a reference text after normalization
(lowercase, strip punctuation, collapse whitespace). The hypothesis may be a
plain .txt or the plugin's .md output (timestamps/headers are stripped).

  python3 score.py --ref reference.txt --hyp transcript.md

Note: the reference is OCR-derived and may contain residual noise, so absolute
WER overstates ASR error. Relative comparisons between methods (shared reference)
are unaffected.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


def normalize(text):
    """Lowercase, replace non-alphanumeric runs with a space, collapse whitespace."""
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return text.strip()


def tokens(text):
    return normalize(text).split()


def _edit_counts(ref, hyp):
    """Levenshtein with backtrace -> (substitutions, insertions, deletions, hits)."""
    n, m = len(ref), len(hyp)
    dp = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        dp[i][0] = i
    for j in range(m + 1):
        dp[0][j] = j
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            if ref[i - 1] == hyp[j - 1]:
                dp[i][j] = dp[i - 1][j - 1]
            else:
                dp[i][j] = 1 + min(dp[i - 1][j - 1], dp[i - 1][j], dp[i][j - 1])

    sub = ins = dele = hits = 0
    i, j = n, m
    while i > 0 or j > 0:
        if i > 0 and j > 0 and ref[i - 1] == hyp[j - 1] and dp[i][j] == dp[i - 1][j - 1]:
            hits += 1
            i, j = i - 1, j - 1
        elif i > 0 and j > 0 and dp[i][j] == dp[i - 1][j - 1] + 1:
            sub += 1
            i, j = i - 1, j - 1
        elif i > 0 and dp[i][j] == dp[i - 1][j] + 1:
            dele += 1
            i -= 1
        else:
            ins += 1
            j -= 1
    return sub, ins, dele, hits


def wer(reference, hypothesis):
    ref, hyp = tokens(reference), tokens(hypothesis)
    sub, ins, dele, hits = _edit_counts(ref, hyp)
    ref_words = len(ref)
    rate = (sub + ins + dele) / ref_words if ref_words else 0.0
    return {
        "wer": rate,
        "substitutions": sub,
        "insertions": ins,
        "deletions": dele,
        "hits": hits,
        "ref_words": ref_words,
        "hyp_words": len(hyp),
    }


def cer(reference, hypothesis):
    ref = list(normalize(reference).replace(" ", ""))
    hyp = list(normalize(hypothesis).replace(" ", ""))
    sub, ins, dele, _ = _edit_counts(ref, hyp)
    return (sub + ins + dele) / len(ref) if ref else 0.0


def extract_transcript(md_text):
    """Pull the spoken text out of the plugin's Markdown transcript output.

    Concatenates the `[mm:ss-mm:ss] text` lines under `## Transcript`, dropping
    timestamps and the `## Source` metadata block.
    """
    lines = md_text.splitlines()
    try:
        start = next(i for i, ln in enumerate(lines) if ln.strip() == "## Transcript")
    except StopIteration:
        start = -1
    spoken = []
    for ln in lines[start + 1:]:
        match = re.match(r"^\[[\d:.\-]+\]\s*(.*)$", ln.strip())
        if match:
            spoken.append(match.group(1).strip())
        elif ln.strip() and not ln.startswith("#"):
            spoken.append(ln.strip())  # plain transcript body (no segment timestamps)
    return " ".join(part for part in spoken if part).strip()


def _load_hypothesis(path):
    text = Path(path).read_text(encoding="utf-8")
    return extract_transcript(text) if str(path).endswith(".md") else text


def main():
    parser = argparse.ArgumentParser(description="Score a transcript against a reference (WER/CER).")
    parser.add_argument("--ref", required=True, help="Reference text file (.txt).")
    parser.add_argument("--hyp", required=True, help="Hypothesis transcript (.md or .txt).")
    args = parser.parse_args()

    reference = Path(args.ref).read_text(encoding="utf-8")
    hypothesis = _load_hypothesis(args.hyp)

    w = wer(reference, hypothesis)
    c = cer(reference, hypothesis)
    print(f"WER: {w['wer'] * 100:.2f}%  CER: {c * 100:.2f}%")
    print(
        f"  ref_words={w['ref_words']} hyp_words={w['hyp_words']} "
        f"sub={w['substitutions']} ins={w['insertions']} del={w['deletions']} hits={w['hits']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
