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

# 3a. (Re)create the framing-free "aligned" audio for apples-to-apples runs (gitignored)
ffmpeg -y -i warandpeace/audio/wap_v1_p1_ch1.mp3 -ss 32.0 -to 855.0 \
    -c:a libmp3lame -q:a 2 warandpeace/audio/wap_v1_p1_ch1_aligned.mp3

# 3b. Run an experiment (everything after `--` is forwarded to transcribe_audio.py)
# (conditioning is off by default now — pass --condition-previous to re-enable it)
python3 run.py --label turbo --audio warandpeace/audio/wap_v1_p1_ch1_aligned.mp3 \
    --ref warandpeace/reference/wap_v1_p1_ch1.txt -- --language en

# 4. Score an existing transcript directly
python3 score.py --ref warandpeace/reference/wap_v1_p1_ch1.txt --hyp warandpeace/transcripts/chunked.md
```

## Caveats when reading WER

Reported WER slightly overstates raw ASR error because the narrator speaks framing absent from
the book text ("Vol 1 Part 1 1805 Chapter 1", "End of chapter 1") and reads French phrases. These
affect all methods equally, so **relative** comparisons between configs are valid.

## Key findings

- **The villain is `condition_on_previous_text=True`** — it triggers repetition-loop
  hallucinations (single-shot large-v3 → 400% WER). Chunking contains it but loop incidence is
  highly chunk-boundary-sensitive (re-cut audio sent large-v3 to 99.9%).
- **Disabling `condition_on_previous_text` eliminates the loops** (now the default; re-enable
  with `--condition-previous`) → clean apples-to-apples accuracy on the framing-free audio:
  large-v3 **3.9%** WER (85s), turbo **4.8%** (34s).
- **Bigger isn't worse, looping was:** with conditioning off, large-v3 is slightly *more*
  accurate than turbo; turbo's real edge is being **2.5× faster**. See `results.md`.
