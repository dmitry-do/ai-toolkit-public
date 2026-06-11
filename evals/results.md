# Transcription speed/quality results

Fixture: War & Peace Vol 1, Part 1, Ch 1 (Dole translation, LibriVox, public domain).
Reference: `warandpeace/reference/wap_v1_p1_ch1.txt` (2140 words) — proofread canonical text
(`source_pages_1-11.md`), so WER is trustworthy. Two audio cuts:
`audio/wap_v1_p1_ch1.mp3` (862s, includes LibriVox intro/outro framing) and
`audio/wap_v1_p1_ch1_aligned.mp3` (823s, trimmed to "Well, prince…" → "…apprenticeship."
so it matches the reference exactly — apples-to-apples).
Hardware: Apple Silicon, mlx-whisper, Python 3.9.6. Lower WER/CER is better.

| label | fixture | wall_s | WER% | CER% | model | flags | notes |
|-------|---------|-------:|-----:|-----:|-------|-------|-------|
| single-shot-largev3 | full | 306 | 400.7 | 346.6 | whisper-large-v3-mlx | `--checkpoint-chunks 1 --language en` | repetition loop ×545 from ~07:40; unusable |
| chunked-largev3 | full | 89 | 15.8 | 11.7 | whisper-large-v3-mlx | `--language en` | chunking contains the loop, but 165 deletions remain |
| chunked-turbo | full | 40 | 8.5 | 6.7 | whisper-large-v3-turbo | `--language en --mlx-model …turbo` | |
| clip-baseline | clip | 9 | 9.2 | 4.3 | whisper-large-v3-mlx | `--language en` | clean 87s opening |
| turbo-aligned | aligned | 39 | 14.3 | 7.8 | whisper-large-v3-turbo | `…turbo` (cond on) | re-chunking re-triggered loops |
| largev3-aligned | aligned | 111 | 99.9 | 60.6 | whisper-large-v3-mlx | `--language en` (cond on) | catastrophic loop, 3287 words |
| **turbo-aligned-nocond** | aligned | 34 | **4.8** | 2.0 | whisper-large-v3-turbo | `…turbo --no-condition-previous` | loops gone |
| **largev3-aligned-nocond** | aligned | 85 | **3.9** | 1.6 | whisper-large-v3-mlx | `--no-condition-previous` | loops gone; most accurate |

## Findings

- **The villain is `condition_on_previous_text=True`.** It causes whisper repetition-loop
  hallucinations. Single-shot large-v3 loops catastrophically (400% WER).
- **Chunking helps but doesn't cure it.** Default chunking contained the loop on the full audio
  (large-v3 15.8%, turbo 8.5%), but loop incidence is *highly sensitive to chunk boundaries*:
  re-cutting (aligned) shifted boundaries and re-triggered loops — large-v3 → 99.9%, turbo → 14.3%.
- **`--no-condition-previous` eliminates the loops** → clean, stable accuracy: turbo 4.8%,
  large-v3 3.9% on identical framing-free audio. True ASR error ≈ 4% WER / ~2% CER (residual =
  French phrases + proper nouns, e.g. Lucca→"Lucha").
- **"Why was large-v3 worse than turbo?"** It wasn't — it was being destroyed by the loop. With
  conditioning off, the bigger model is *slightly more accurate* (3.9% vs 4.8%), as expected.
  Turbo's real edge is **speed: 2.5× faster** (34s vs 85s) for ~1% WER.
- Caveats: `run.py` wall includes a model's first-use download (turbo: 226s first, 40s cached);
  WER on the un-trimmed `full` audio is inflated by the narrator's spoken framing.

## Next levers

- **Strongly recommended: make `--no-condition-previous` the default** (`condition_on_previous_text
  =False`). Prevents the catastrophic-loop failure mode (400%/99.9% WER); accuracy cost is
  negligible here. Bigger robustness win than the model choice.
- Model default is now turbo (speed). For max accuracy at ~2.5× the time, large-v3 + cond-off.
- VAD / silence-skip. (Parallel chunks unlikely to help — single shared MLX GPU.)
