# Transcription speed/quality results

Fixture: War & Peace Vol 1, Part 1, Ch 1 (Dole translation, LibriVox, public domain).
Audio: `warandpeace/audio/wap_v1_p1_ch1.mp3` (862s / ~14.4 min). Reference:
`warandpeace/reference/wap_v1_p1_ch1.txt` (2218 words, OCR-derived — absolute WER
overstates ASR error; compare methods relative to each other). Hardware: Apple Silicon,
mlx-whisper, Python 3.9.6. Lower WER/CER is better.

| label | fixture | wall_s | WER% | CER% | model | flags | notes |
|-------|---------|-------:|-----:|-----:|-------|-------|-------|
| baseline-single-shot | full | 306 | 399.5 | 346.2 | whisper-large-v3-mlx | `--checkpoint-chunks 1 --language en` | **Repetition-loop hallucination from ~07:40** — one phrase repeats 545×; only first ~7.5 min usable. UNUSABLE baseline. |
| chunked-default | full | 89 | 17.9 | 12.6 | whisper-large-v3-mlx | `--language en` (default chunking, ~7×123s) | Loop gone (max repeat 2×). Also **3.4× faster** — single-shot wasted ~200s generating the loop. Usable baseline. |
| clip-baseline | clip | 9 | 9.2 | 4.3 | whisper-large-v3-mlx | `--language en` |  |
| chunked-turbo | full | 40 | 10.9 | 7.6 | mlx-community/whisper-large-v3-turbo | `--language en --mlx-model mlx-community/whisper-large-v3-turbo` | **2.2× faster than large-v3 AND lower WER.** First run was 226s incl. one-time model download; 40s cached. One minor 14× repeat in a chunk. |

## Notes

- The single-shot baseline exposed a catastrophic failure: `condition_on_previous_text=True`
  let whisper-large-v3 fall into a repetition loop ~halfway through and never recover.
- **Confirmed:** the chunked path contains the loop (per-chunk conditioning resets at chunk
  boundaries) — WER 399% → 17.9%, and wall 306s → 89s since the loop was burning compute.
  This makes chunking a *correctness* feature, not just crash-safety/speed.
- Remaining WER (17.9%) is inflated by: OCR noise in the reference, the narrator's spoken
  structural intro ("Vol 1 Part 1 1805 Chapter 1") absent from the book text, and chunk-boundary
  seams. Trim the intro / spot-check the diff to estimate true ASR error.
- **whisper-large-v3-turbo wins on this fixture: 40s vs 89s (2.2× faster) at WER 10.9% vs 17.9%.**
  Strong candidate for the default model. (Turbo still showed one minor 14× in-chunk repeat, so
  loop-resistance still relies on chunking.)
- **Timing caveat:** `run.py` wall includes the model download on a model's *first* use — the
  turbo first run measured 226s; cached it is 40s. Re-run cached for fair speed numbers.
- Next levers: expose a `condition_on_previous_text` flag so single-shot is safe too; VAD/silence
  skip; confirm turbo's quality on the full chapter isn't a fluke (spot-check the diff vs large-v3).
