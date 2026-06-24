# 🎙️ audio-transcription

Turn `wav`, `mp3`, and `m4a` recordings — meetings, calls, interviews, lectures, podcasts, voice
memos, songs — into timestamped Markdown with Whisper. On Apple Silicon it uses `mlx-whisper`;
everywhere else it falls back to `openai-whisper`.

## Install

```
/plugin install audio-transcription@ai-toolkit-public
```

## What it does

- Transcribes a single file or a whole folder into Markdown with `[start-end] text` segments and a
  `Source` block (filename, backend, model, detected language).
- **Picks the right backend.** `mlx-whisper` on Apple Silicon (required there), `openai-whisper`
  elsewhere, and an opt-in `faster-whisper` (beam search) for hard, noisy, accented audio.
- **Survives long jobs.** Chunked transcription checkpoints the Markdown after every chunk and
  auto-resumes from a sidecar if the run is interrupted.
- **Defaults tuned for accuracy.** Silence skipping and boundary snapping are on by default; a
  second pass repairs Whisper's silent deletions and hallucinated overlays. Repetition loops are
  disabled at the source (`condition_on_previous_text` off).

The numbers behind every default are measured — see [`evals/`](../../evals) and the "Tested with"
stamp in the skill.

## Usage

It triggers on natural asks ("transcribe this voice memo", "what does this recording say?"), or run
the bundled script directly:

```bash
ROOT=${CLAUDE_PLUGIN_ROOT}/skills/audio-transcription
python3 "$ROOT/scripts/transcribe_audio.py" --check                       # dependency check
python3 "$ROOT/scripts/transcribe_audio.py" "recording.mp3"               # default: large-v3
python3 "$ROOT/scripts/transcribe_audio.py" "recording.mp3" \
  --mlx-model mlx-community/whisper-large-v3-turbo                          # ~2.3× faster
```

## Requirements

- **Apple Silicon:** `pip install mlx-whisper` (the script enforces this backend here).
- **Other platforms:** `pip install openai-whisper torch`.
- `ffmpeg` on `PATH` for most formats.

The skill asks before installing anything or downloading model weights.

## Learn more

- Skill, defaults, and anti-patterns: [`skills/audio-transcription/SKILL.md`](./skills/audio-transcription/SKILL.md)
- Behavioral scenarios + trigger set: [`skills/audio-transcription/EVALS.md`](./skills/audio-transcription/EVALS.md)
- A real worked input → output: [`skills/audio-transcription/examples/`](./skills/audio-transcription/examples/)

Mine, MIT-licensed (see the root [LICENSE](../../LICENSE)).
