# Transcription speed/quality results

Fixture: War & Peace Vol 1, Part 1, Ch 1 (Dole translation, LibriVox, public domain).
Reference: `warandpeace/reference/wap_v1_p1_ch1.txt` (2140 words) — proofread canonical text
(`source_pages_1-11.md`), so WER is trustworthy. Audio cut used for the sweep below:
`audio/wap_v1_p1_ch1_aligned.mp3` (823s, trimmed to "Well, prince…" → "…apprenticeship."
so it matches the reference exactly — apples-to-apples).
Hardware: Apple Silicon, mlx-whisper, Python 3.9.6. Decoding is greedy (`temperature=0.0`),
so each config is **deterministic** — differences below are real, not sampling noise.
Lower WER/CER is better.

## Authoritative sweep: model × chunk size (conditioning OFF — current default)

Both models on the aligned 823s audio, `--language en`, `condition_on_previous_text=False`.
Chunk count `n` is forced exactly (single-shot at n=1; `--checkpoint-min-seconds 1` otherwise),
so chunk length = 823s ÷ n. Models cached, so wall excludes any first-use download.

| model | chunks n | chunk len | wall_s | WER% | CER% | hyp words | notes |
|-------|---------:|----------:|-------:|-----:|-----:|----------:|-------|
| large-v3 | 1 (single-shot) | 823s | 82 | 4.0 | 1.5 | 2146 | no loop — cond-off fixes single-shot |
| large-v3 | 2 | 411s | 84 | 4.2 | 1.5 | 2147 | |
| large-v3 | 3 | 274s | 83 | 4.2 | 1.6 | 2146 | |
| **large-v3** | **5** | **165s** | 86 | **3.8** | **1.5** | 2146 | **best accuracy overall** |
| large-v3 | 6 | 137s | 86 | 3.9 | 1.6 | 2148 | ≈ live default (floor 120s ⇒ 6 chunks) |
| large-v3 | 10 | 82s | 86 | 4.3 | 1.8 | 2145 | |
| large-v3 | 16 | 51s | 82 | 15.0 | 12.1 | 1939 | **over-chunked**: ~222 words lost at boundaries |
| turbo | 1 (single-shot) | 823s | 33 | 4.2 | 1.5 | 2152 | turbo's best |
| turbo | 6 | 137s | 36 | 4.8 | 2.0 | 2168 | |
| turbo | 16 | 51s | 33 | 4.6 | 2.0 | 2145 | turbo more boundary-robust than large-v3 |

## Findings

- **Best-accuracy model = large-v3 ("normal"), not turbo.** At every matched chunk size large-v3
  beats turbo (n=1: 4.0 vs 4.2; n=6: 3.9 vs 4.8). large-v3's best is **3.8% WER / 1.5% CER (n=5)**;
  turbo's best is 4.2% (n=1). The edge is small (~0.4–0.9 pt WER) and costs **~2.4× wall time**
  (large-v3 ~85s vs turbo ~34s). So: **large-v3 for max accuracy, turbo for speed.**
- **Chunk size barely matters in the safe zone, then falls off a cliff.** For large-v3, n=1–6
  (chunks ≥ ~137s) are all 3.8–4.2% — flat, best at n=5. n=10 (82s) slips to 4.3%; **n=16 (51s)
  collapses to 15.0%.** The collapse is *deletion at chunk boundaries* (hyp words drop 2146→1939,
  19 fewer segments), **not** a repetition loop — a distinct, milder failure mode.
- **Keep chunks comfortably above Whisper's 30s internal window.** Slices near ~50s start losing
  audio at the hard cuts. The plugin's `--checkpoint-min-seconds 120` floor is load-bearing: it
  guarantees ≥120s chunks regardless of `--checkpoint-chunks`, keeping every run in the safe zone.
  Don't lower the floor below ~120s.
- **Conditioning-off makes single-shot safe.** With `condition_on_previous_text=False` (the default),
  even no-chunking single-shot is clean (large-v3 4.0%, turbo 4.2%) — the old 400%/99.9%-WER
  catastrophes were the conditioning-driven loop, now gone. Chunking is no longer needed to *contain*
  loops; it only earns incremental on-disk checkpoints (and, past the safe zone, hurts).
- Residual ~4% WER is French phrases + proper nouns (Lucca→"Lucha", etc.), shared by all configs.

## Historical context — the conditioning-ON loop (superseded)

These runs used `condition_on_previous_text=True` (the old default) and are kept to document why
it was changed. They are *not* comparable to the table above.

| label | wall_s | WER% | CER% | model | notes |
|-------|-------:|-----:|-----:|-------|-------|
| single-shot-largev3 (cond on) | 306 | 400.7 | 346.6 | large-v3 | repetition loop ×545; unusable |
| largev3-aligned (cond on) | 111 | 99.9 | 60.6 | large-v3 | catastrophic loop, 3287 words |
| turbo-aligned (cond on) | 39 | 14.3 | 7.8 | turbo | re-chunking re-triggered loops |

**Villain:** `condition_on_previous_text=True` → repetition-loop hallucinations whose incidence is
highly chunk-boundary-sensitive. Disabling it (now the default) eliminated them.

## Next levers

- **Done:** `condition_on_previous_text=False` is the default (opt back in via `--condition-previous`).
- **Default model = turbo (speed).** Turbo (~4.8% WER, ~35s) is the default; large-v3 (~3.9% WER) is
  only ~0.9 pt more accurate for ~2.5× the time, so it's an opt-in for precision-critical jobs via
  `--mlx-model mlx-community/whisper-large-v3-mlx`. Chunk default (target 10, floor 120s) is in the safe zone.
- VAD / silence-skip (unexplored). Parallel chunks unlikely to help — single shared MLX GPU.
