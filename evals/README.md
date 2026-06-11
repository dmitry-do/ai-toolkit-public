# Transcription evals

Measures the `audio-transcription` plugin for **speed vs. quality** against a known
ground-truth text, so we can compare transcription methods objectively.

## Fixture (public domain)

*War and Peace*, Vol 1, Part 1, Chapter 1 — **Nathan Haskell Dole** translation
(Tolstoy d. 1910, Dole d. 1935; public domain).

- Audio: LibriVox recording, "War and Peace Vol. 1 (Dole Translation)", section 01
  ("Vol 1 Part 1 Ch 1"), 862s / ~14.4 min.
  <https://librivox.org/war-and-peace-vol-1-1805-1806-by-leo-tolstoy/>
- Reference text: OCR of the Dole edition on Internet Archive.
  <https://archive.org/details/warandpeace01dolegoog>
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
# 1. (Re)build the reference text from the Internet Archive OCR
cd warandpeace/reference
curl -sL https://archive.org/download/warandpeace01dolegoog/warandpeace01dolegoog_djvu.txt -o /tmp/wap_dole.txt
python3 build_reference.py /tmp/wap_dole.txt wap_v1_p1_ch1.txt

# 2. Run the scorer's unit tests
cd ../.. && python3 -m unittest test_score -v

# 3. Run an experiment (everything after `--` is forwarded to transcribe_audio.py)
python3 run.py --label chunked --audio warandpeace/audio/wap_v1_p1_ch1.mp3 \
    --ref warandpeace/reference/wap_v1_p1_ch1.txt -- --language en

# 4. Score an existing transcript directly
python3 score.py --ref warandpeace/reference/wap_v1_p1_ch1.txt --hyp warandpeace/transcripts/chunked.md
```

## Caveats when reading WER

Absolute WER is **inflated** and should not be read as raw ASR error:

- The reference is OCR-derived with residual single-character noise.
- The narrator speaks a structural intro ("Vol 1 Part 1 1805 Chapter 1") absent from the book text.
- Chunk boundaries can roughen a sentence split across them.

These affect all methods equally, so **relative** comparisons between configs are valid.

## Key finding so far

Single-shot whisper-large-v3 fell into a **repetition-loop hallucination** (`condition_on_previous_text=True`)
on the full chapter: WER 399%, and it wasted ~200s of compute looping. The default **chunked**
path contains the loop (per-chunk conditioning resets): WER 17.9%, wall 89s. See `results.md`.
