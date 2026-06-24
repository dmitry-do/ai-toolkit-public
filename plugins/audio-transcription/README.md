# 🎙️ audio-transcription

Turn `wav`, `mp3`, and `m4a` recordings — meetings, calls, interviews, lectures, podcasts, voice
memos, songs — into timestamped Markdown with Whisper. On Apple Silicon it uses `mlx-whisper`;
everywhere else it falls back to `openai-whisper`.

## Install in Claude Code

```
/plugin marketplace add dmitry-do/ai-toolkit-public
/plugin install audio-transcription@ai-toolkit-public
```

## Claude Web

Claude Code only — not available on claude.ai, because it needs local `mlx-whisper`/`ffmpeg` and
reads audio files from your machine, neither of which the claude.ai sandbox provides.

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

**Requirements:** Apple Silicon → `pip install mlx-whisper`; other platforms → `pip install openai-whisper torch`; `ffmpeg` on `PATH`. The skill asks before installing anything or downloading model weights.

## Structure

```
plugins/audio-transcription/
├── .claude-plugin/plugin.json   # marketplace manifest
├── README.md                    # this file
└── skills/audio-transcription/
    ├── SKILL.md                 # defaults, anti-patterns, "Tested with" stamp
    ├── scripts/transcribe_audio.py   # the transcription script
    └── examples/                # a real worked input → output

evals/audio-transcription/EVALS.md   # behavioral scenarios — NOT installed with the plugin
evals/                               # WER accuracy harness + fixtures — NOT installed
```

Mine, MIT-licensed (see the root [LICENSE](../../LICENSE)).
