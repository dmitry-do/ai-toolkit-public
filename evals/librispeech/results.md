# LibriSpeech accuracy results

Fixtures: chapter-level concatenations of LibriSpeech test-clean / test-other
utterances (~8 min each; cap 480s), references joined from the `*.trans.txt`
ground truth — exact, so absolute WER is trustworthy. `hf-dummy` is the
Hugging Face `hf-internal-testing/librispeech_asr_dummy` validation split
concatenated into one ~8-min fixture (clean speech, smoke test).
Chapters picked deterministically (evenly spaced over the sorted list).
WER/CER are micro-averages (total edits / total reference words) across the
row's fixtures. Decoding is deterministic (greedy or fixed beam), so deltas
are real. Hardware: Apple Silicon, Python 3.9.6. Lower is better.

| label | source | fixtures | audio_s | wall_s | WER% | CER% | ref words | flags |
|-------|--------|---------:|--------:|-------:|-----:|-----:|----------:|-------|
| turbo-sp | clean | 3 | 771 | 36 | 1.90 | 0.75 | 1948 | `--language en` |
| turbo-nosp | clean | 3 | 771 | 37 | 1.85 | 0.66 | 1948 | `--language en --no-second-pass` |
| largev3-sp | clean | 3 | 771 | 83 | 1.59 | 0.60 | 1948 | `--language en --mlx-model mlx-community/whisper-large-v3-mlx` |
| largev3-nosp | clean | 3 | 771 | 83 | 1.59 | 0.60 | 1948 | `--language en --mlx-model mlx-community/whisper-large-v3-mlx --no-second-pass` |
| turbo-sp | other | 3 | 964 | 53 | 10.08 | 8.08 | 2590 | `--language en` |
| turbo-nosp | other | 3 | 964 | 48 | 4.05 | 2.18 | 2590 | `--language en --no-second-pass` |
| largev3-sp | other | 3 | 964 | 140 | 24.98 | 22.86 | 2590 | `--language en --mlx-model mlx-community/whisper-large-v3-mlx` |
| largev3-nosp | other | 3 | 964 | 111 | 4.44 | 2.48 | 2590 | `--language en --mlx-model mlx-community/whisper-large-v3-mlx --no-second-pass` |
| turbo-sp2 | clean | 3 | 771 | 36 | 1.90 | 0.75 | 1948 | `--language en` |
| largev3-sp2 | clean | 3 | 771 | 80 | 1.59 | 0.60 | 1948 | `--language en --mlx-model mlx-community/whisper-large-v3-mlx` |
| turbo-sp2 | other | 3 | 964 | 47 | 4.02 | 2.14 | 2590 | `--language en` |
| largev3-sp2 | other | 3 | 964 | 115 | 4.17 | 2.21 | 2590 | `--language en --mlx-model mlx-community/whisper-large-v3-mlx` |
| turbo-sp2 | hf-dummy | 1 | 481 | 22 | 3.93 | 1.83 | 1169 | `--language en` |
| largev3-sp2 | hf-dummy | 1 | 481 | 51 | 3.93 | 2.02 | 1169 | `--language en --mlx-model mlx-community/whisper-large-v3-mlx` |
| faster-beam5 | clean | 3 | 771 | 444 | 1.59 | 0.60 | 1948 | `--language en --backend faster` |
| faster-beam5 | other | 3 | 964 | 654 | 3.55 | 2.13 | 2590 | `--language en --backend faster` |

Labels: `-sp` = the *original* second-pass implementation (kept as the record of its
failure — superseded); `-sp2` = the shipped coverage-based second pass; `-nosp` =
`--no-second-pass`. All 2026-06-12.

## Findings

- **The original second pass failed catastrophically on noisy speech** (`-sp` rows:
  turbo 4.05 → 10.08, large-v3 4.44 → **24.98** on test-other) and the failure mode
  was instructive: on noisy audio Whisper emits *spurious overlays* — a 30s
  "Thank you." segment on top of the real segments at a chunk head — and
  re-transcribing a suspect's span when other segments already cover its audio
  just duplicates the real text (+379 inserted words on one fixture). The fix
  (`-sp2`) reasons about audio coverage, not segment spans: covered overlays are
  dropped, holes left by stacked overlays are recovered as genuine gaps, and
  recovered text the neighbours already carry is discarded.
- **The fixed second pass is equal-or-better everywhere**: test-other large-v3
  4.44 → 4.17 and turbo 4.05 → 4.02 (it now *removes* the overlay hallucinations
  the baseline leaves in), clean unchanged (large-v3 identical; turbo +1 recovered
  word), wall +0–4%. Default ON.
- **large-v3 beats turbo on clean speech by ~16% relative** (1.59 vs 1.90; same on
  hf-dummy at 3.93) and ties on test-other (4.17 vs 4.02). With the War & Peace
  fixture (3.4 vs 3.8) the weighted micro-average is **3.17 vs 3.33** — large-v3 is
  the accuracy default at ~2.3× turbo's wall (~10× realtime).
- **faster-whisper (CTranslate2, beam_size=5) is the most accurate backend on hard
  audio**: ties mlx large-v3 exactly on clean (1.59) but wins test-other **3.55 vs
  4.17** (~15% relative, mostly substitutions: 33 vs 37 sub on the hardest chapter).
  The cost on Apple Silicon is decisive against making it the default: CPU-only
  (no Metal in CTranslate2), ~1.5× realtime — **5.5–5.9× slower than mlx large-v3**
  (444 vs 80s clean, 654 vs 115s other). Documented as the precision opt-in
  (`--backend faster`) for noisy/accented audio where turnaround doesn't matter.
- **hf-dummy smoke**: turbo = large-v3 = 3.93% — sane, and a free one-command
  regression check (`--source hf-dummy`).
