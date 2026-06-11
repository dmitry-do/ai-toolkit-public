# Transcription speed/quality results

Fixture: War & Peace Vol 1, Part 1, Ch 1 (Dole translation, LibriVox, public domain).
Audio: `warandpeace/audio/wap_v1_p1_ch1.mp3` (862s / ~14.4 min). Reference:
`warandpeace/reference/wap_v1_p1_ch1.txt` (2140 words) — **proofread canonical text**
(`source_pages_1-11.md`, hand-corrected against page images), so WER here is trustworthy.
Hardware: Apple Silicon, mlx-whisper, Python 3.9.6. Lower WER/CER is better.

| label | fixture | wall_s | WER% | CER% | sub/ins/del | model | flags | notes |
|-------|---------|-------:|-----:|-----:|-------------|-------|-------|-------|
| baseline-single-shot | full | 306 | 400.7 | 346.6 | 1194/7459/6 | whisper-large-v3-mlx | `--checkpoint-chunks 1 --language en` | **Repetition-loop hallucination from ~07:40** (one phrase ×545). UNUSABLE. |
| chunked-default | full | 89 | 15.8 | 11.7 | 78/98/**165** | whisper-large-v3-mlx | `--language en` (default chunking) | Loop contained, but **165 deletions** — phantom hallucinations at chunk seams drop real speech (e.g. zero-duration `And I think that's what he was trying to do`). |
| clip-baseline | clip | 9 | 9.2 | 4.3 | 4/9/0 | whisper-large-v3-mlx | `--language en` | Clean 87s opening, no loop region. |
| chunked-turbo | full | 40 | **8.5** | 6.7 | 69/96/**19** | mlx-community/whisper-large-v3-turbo | `--language en --mlx-model …whisper-large-v3-turbo` | **Best: 2.2× faster than large-v3 AND ~half the WER.** First run 226s incl. one-time download; 40s cached. |

## Findings

- **Single-shot large-v3 is broken on long audio:** `condition_on_previous_text=True` triggers a
  repetition loop (~07:40) that never recovers — WER 400%, and ~200s of wasted compute.
- **Chunking is a correctness fix:** per-chunk conditioning resets contain the loop. WER 400% → 15.8%,
  wall 306s → 89s.
- **Why turbo beats large-v3 (the surprising part):** substitutions are nearly equal (large-v3 78,
  turbo 69 — both hear words about equally well), but **deletions differ 165 vs 19**. large-v3 still
  hallucinates/repeats at chunk boundaries and *drops real speech*; turbo (4 decoder layers vs 32) is
  far more robust to that failure mode. Bigger model ≠ better here — turbo wins on speed *and* quality.
- **Residual WER caveat:** the narrator speaks framing absent from the book text ("Vol 1 Part 1 1805
  Chapter 1", "End of chapter 1") and reads French phrases; these add insertions. True ASR error is a
  bit below the reported WER. Trim framing to refine.
- **Timing caveat:** `run.py` wall includes a model's *first-use* download (turbo: 226s first, 40s cached).

## Next levers

- Make `whisper-large-v3-turbo` the plugin default model (faster + more accurate here).
- Expose a `condition_on_previous_text` flag so single-shot is safe too.
- VAD / silence-skip. (Parallel chunks unlikely to help — single shared MLX GPU.)
