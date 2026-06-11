# Transcription evals

Measures the `audio-transcription` plugin for **speed vs. quality** against a known
ground-truth text, so we can compare transcription methods objectively.

## Fixture (public domain)

*War and Peace*, Vol 1, Part 1, Chapter 1 — **Nathan Haskell Dole** translation
(Tolstoy d. 1910, Dole d. 1935; public domain).

- Audio: LibriVox recording, "War and Peace Vol. 1 (Dole Translation)", section 01
  ("Vol 1 Part 1 Ch 1"), 862s / ~14.4 min.
  <https://librivox.org/war-and-peace-vol-1-1805-1806-by-leo-tolstoy/>
- Reference text: `warandpeace/reference/source_pages_1-11.md` — proofread canonical text of
  the Dole edition (OCR of the 1889 Crowell scan, hand-corrected against page images).
  OCR origin: <https://archive.org/details/warandpeace01dolegoog>
  **Note:** Project Gutenberg's *War and Peace* is the **Maude** translation, not Dole —
  do not use it as the reference (different wording → meaningless WER).

## Layout

```
score.py            self-contained WER/CER + normalization (no deps); also a CLI
test_score.py       unit tests for the scorer
run.py              run a transcribe config -> time it -> score it -> append a results row
results.md          the scoreboard
warandpeace/
  audio/            wap_v1_p1_ch1.mp3 (full), wap_v1_p1_ch1_clip.mp3 (~90s, fast iteration)
  reference/        cleaned Dole text (full + clip) and build_reference.py
  transcripts/      generated outputs (gitignored; regenerate via run.py)
```

## How to use

```bash
# 1. (Re)build the Chapter I reference from the proofread canonical text
cd warandpeace/reference
python3 build_reference.py source_pages_1-11.md wap_v1_p1_ch1.txt

# 2. Run the scorer's unit tests
cd ../.. && python3 -m unittest test_score -v

# 3. Run an experiment (everything after `--` is forwarded to transcribe_audio.py)
python3 run.py --label chunked --audio warandpeace/audio/wap_v1_p1_ch1.mp3 \
    --ref warandpeace/reference/wap_v1_p1_ch1.txt -- --language en

# 4. Score an existing transcript directly
python3 score.py --ref warandpeace/reference/wap_v1_p1_ch1.txt --hyp warandpeace/transcripts/chunked.md
```

## Caveats when reading WER

Reported WER slightly overstates raw ASR error because the narrator speaks framing absent from
the book text ("Vol 1 Part 1 1805 Chapter 1", "End of chapter 1") and reads French phrases. These
affect all methods equally, so **relative** comparisons between configs are valid.

## Key findings

- **Single-shot whisper-large-v3 is broken on long audio:** a repetition-loop hallucination
  (`condition_on_previous_text=True`) from ~07:40 — WER 400%, ~200s wasted looping.
- **Chunking is a correctness fix** (per-chunk conditioning resets): WER → 15.8%, wall → 89s.
- **whisper-large-v3-turbo wins on speed AND quality:** 40s (cached) and WER 8.5% vs large-v3's
  89s / 15.8%. The gap is deletions (turbo 19 vs large-v3 165): large-v3 still hallucinates at
  chunk seams and drops real speech; turbo is more robust. See `results.md`.
