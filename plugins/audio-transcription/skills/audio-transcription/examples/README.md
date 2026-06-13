# Worked example

One real input → real output, so you can see what the skill produces before running it.

- **Input:** `evals/warandpeace/audio/wap_v1_p1_ch1_clip.mp3` — an ~87 s clip of *War and Peace*
  Vol. 1, Pt. 1, Ch. 1, read for [LibriVox](https://librivox.org/) (public domain). The recording
  opens with the reader announcing the volume and chapter, so the transcript does too.
- **Output:** [`war-and-peace-clip.md`](./war-and-peace-clip.md) — the actual file the script wrote,
  not a hand-edited mockup.

Reproduce it from the repo root with the default backend and model:

```bash
ROOT=plugins/audio-transcription/skills/audio-transcription
python3 "$ROOT/scripts/transcribe_audio.py" \
  "evals/warandpeace/audio/wap_v1_p1_ch1_clip.mp3" \
  --output "$ROOT/examples/war-and-peace-clip.md" \
  --language en \
  --title "War and Peace — Vol. 1, Pt. 1, Ch. 1 (opening)"
```

The clip is short enough to be a single chunk, so this run exercises the straight transcription
path (no checkpointing, no resume). The longer fixtures and their WER scores live under `evals/`.
