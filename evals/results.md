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
| large-v3 | 16 | 51s | 82 | 15.0 | 12.1 | 1939 | superseded — this was the prompt carry, see below |
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
  **(Superseded 2026-06-11: the deletion was driven by the cross-chunk prompt carry, since
  removed — the same n=16 config now scores 4.7%. See the silence-skip section below.)**
- **Keep chunks comfortably above Whisper's 30s internal window.** Slices near ~50s start losing
  audio at the hard cuts. The plugin's `--checkpoint-min-seconds 120` floor is load-bearing: it
  guarantees ≥120s chunks regardless of `--checkpoint-chunks`, keeping every run in the safe zone.
  Don't lower the floor below ~120s. *(Still good guidance for checkpoint efficiency, though the
  catastrophic boundary deletion itself is gone with the prompt carry — see below.)*
- **Conditioning-off makes single-shot safe.** With `condition_on_previous_text=False` (the default),
  even no-chunking single-shot is clean (large-v3 4.0%, turbo 4.2%) — the old 400%/99.9%-WER
  catastrophes were the conditioning-driven loop, now gone. Chunking is no longer needed to *contain*
  loops; it only earns incremental on-disk checkpoints (and, past the safe zone, hurts).
- Residual ~4% WER is French phrases + proper nouns (Lucca→"Lucha", etc.), shared by all configs.

## Long audio: does chunking matter? (40-min loop test)

The aligned clip looped 3× into a **2469s (~41 min)** file (`/tmp/loop40.mp3`, regenerate with
`ffmpeg -f concat`), scored against a 3×-concatenated 6420-word reference. Single-shot vs the default
10-chunk plan, both models, conditioning off:

| config | chunks | chunk len | wall_s | WER% | CER% |
|--------|-------:|----------:|-------:|-----:|-----:|
| turbo | 1 (single-shot) | 2469s | 91 | 4.3 | 1.5 |
| turbo | 10 (default) | ~247s | 97 | 4.3 | 1.7 |
| large-v3 | 1 (single-shot) | 2469s | 246 | 4.0 | 1.5 |
| large-v3 | 10 (default) | ~247s | 250 | 3.9 | 1.6 |

- **Chunking is accuracy-neutral, even at 40 min.** single-shot ≈ chunked for both models (turbo
  4.3 = 4.3; large-v3 4.0 vs 3.9, within noise), for **~5% extra wall time**. Accuracy also does
  **not degrade with length** — these match the 13.7-min fixture.
- **No loops at 40-min single-shot** for *either* model (turbo 4.3%, large-v3 4.0%). Conditioning-off
  holds at length — even the big model that historically blew up to 400% is stable single-shot now.
- **But single-shot writes to disk only once, at the very end.** The chunked path writes after every
  chunk (verified: 481 turbo / 370 large-v3 segments on disk *mid-run*) — a checkpoint roughly every
  ~4 min on a 40-min job. A crash/interrupt loses everything under single-shot, nothing-since-last-chunk
  under chunking.
- **Verdict:** on long audio, **keep chunking on** — not for accuracy (it's a wash) but for the
  incremental on-disk saves, which cost ~5% time and zero accuracy. The default (target 10, floor 120s)
  is exactly right: ~10 checkpoints on a 40-min file, and it auto-collapses to single-shot on short clips.

## Silence skipping (VAD) + the prompt-carry fix (2026-06-11)

New fixtures, built from the aligned 823s audio so the 2161-word reference stays exact:
**silence-heavy** = audio split at a natural pause (400s) with 300s of encoded silence inserted
(1123s total, 27% silence); **quiet-speaker** = second half attenuated −25 dB (823s). All runs
turbo, `--language en`, no prompt carry unless marked.

| config | fixture | wall_s | WER% | CER% | notes |
|--------|---------|-------:|-----:|-----:|-------|
| defaults (skip-silence on) | aligned | 34 | 4.3 | 1.6 | VAD self-gates to a no-op on continuous speech |
| defaults (skip-silence on) | silence-heavy | 34 | 4.3 | 1.8 | skips the 300s gap; **no silence hallucinations** |
| `--no-skip-silence` | silence-heavy | 40 | 5.2 | 2.7 | hallucinates in the gap ("Thank you." ×48 words) |
| defaults (skip-silence on) | quiet-speaker | 33 | 4.7 | 1.9 | −25 dB speech stays above threshold, fully kept |
| with prompt carry (old code) | silence-heavy | 32 | 7.9 | 5.3 | head-of-chunk deletion, ~75 words lost |
| large-v3 n=16 (51s chunks) | aligned | 89 | 4.7 | 2.1 | **the 15.0% "cliff" was the carry** — now fine |

### The real boundary villain was the cross-chunk prompt carry

The chunked path used to pass the previous chunk's last ~200 chars as `initial_prompt` to the
next chunk. That is cross-boundary conditioning by another name — the same failure family as
`condition_on_previous_text` — and it can make Whisper **silently delete the head of a chunk**
(reproduced deterministically: a 133s chunk emitted a truncated 22s segment and dropped ~30s /
75 words of real speech; the identical audio slice with no carried prompt transcribes perfectly).
The carry is now removed: every chunk gets only the user's `--prompt`. Verified equal-or-better
on every fixture, and it retroactively explains the n=16 boundary-deletion cliff (15.0% → 4.7%
at identical 51s chunks).

### Silence skipping (`--skip-silence`, default ON)

Energy VAD: 30ms RMS frames; threshold = max(1e-4, 95th-percentile × −30 dB); silences < 2s are
kept inside regions; regions get 0.3s padding; timestamps keep the original timeline. It only
engages when it would save ≥ 10s (or ≥ 20% of short audio), so continuous recordings keep the
exact untrimmed chunk plan; if no speech is detected at all it falls back to transcribing
everything. On the silence-heavy fixture it is **faster (34 vs 40s) and more accurate (4.3 vs
5.2%)** — the WER win is removing Whisper's silence hallucinations, and the time win grows with
the silent fraction and with slower models. Conservative by construction: a quiet speaker 25 dB
under the loud one is fully retained. Opt out with `--no-skip-silence` (e.g. music with long
genuinely-quiet passages).

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
- **Done:** VAD / silence-skip (`--skip-silence`, default ON) + cross-chunk prompt carry removed —
  see the 2026-06-11 section above.
- Parallel chunks unlikely to help — single shared MLX GPU. Possible future lever: snap chunk
  boundaries to detected pauses (VAD already finds them) for even cleaner cuts.
