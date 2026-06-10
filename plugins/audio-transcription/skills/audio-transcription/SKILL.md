---
name: audio-transcription
description: Use when a user wants to transcribe supported wav, mp3, or m4a audio recordings, such as meetings, phone calls, interviews, lectures, conferences, songs, voice memos, or podcasts, into Markdown; needs to check or request installation of transcription dependencies like mlx-whisper, openai-whisper, torch, or ffmpeg; or wants to run a bundled Whisper transcription script directly.
---

# Audio Transcription

Use this skill to transcribe supported audio recordings into timestamped Markdown, including meeting recordings, phone calls, interviews, lectures, conference sessions, voice memos, podcasts, and songs.

Supported audio formats: `wav`, `mp3`, and `m4a`.

The bundled script lives at `${CLAUDE_PLUGIN_ROOT}/skills/audio-transcription/scripts/transcribe_audio.py`, where `${CLAUDE_PLUGIN_ROOT}` is the plugin's installed root directory (the parent of `skills/`). If the variable is not set in the shell, substitute the absolute plugin root path.

## Apple Silicon Requirement

On any Apple Silicon Mac (`darwin` with `arm64` or `aarch64`), use `mlx-whisper`. This is a requirement for this skill, not a preference.

- Check for Apple Silicon with `uname -s` and `uname -m`, or use the bundled script's `--check`.
- If Apple Silicon is detected and `mlx-whisper` is missing, stop and ask the user before installing it.
- Do not use the `openai-whisper`/Torch backend on Apple Silicon for this skill.
- Default MLX model: `mlx-community/whisper-large-v3-mlx`.
- Model source: `https://huggingface.co/mlx-community/whisper-large-v3-mlx`.
- `mlx-whisper` can load the model directly from Hugging Face with `path_or_hf_repo="mlx-community/whisper-large-v3-mlx"`; the first run may download model weights.
- Manual model download command, if the user approves network access:

  ```bash
  python3 -m pip install 'huggingface_hub[hf_xet]'
  huggingface-cli download --local-dir whisper-large-v3-mlx mlx-community/whisper-large-v3-mlx
  ```

  To use the downloaded copy, pass `--mlx-model ./whisper-large-v3-mlx` (or an absolute path) to the bundled script; otherwise the script loads the model from Hugging Face into the HF cache.

## Workflow

1. Identify the audio files and desired output location. If the scope is unclear, ask whether to transcribe one file or all audio files in the folder.
2. Use the project's active Python interpreter when one exists, such as `.venv/bin/python`; otherwise use `python3`. Check dependencies before running long jobs:

   ```bash
   python3 ${CLAUDE_PLUGIN_ROOT}/skills/audio-transcription/scripts/transcribe_audio.py --check
   ```

   Substitute `python3` in all examples below with the interpreter chosen in this step; the same interpreter must be used for `--check`, dependency installs, and the transcription run.

3. If the file is not `wav`, `mp3`, or `m4a`, stop and tell the user the supported formats.
4. If dependencies are missing, tell the user what is missing and ask permission before installing anything.
   - Apple Silicon required backend: `python3 -m pip install mlx-whisper`
   - Portable fallback: `python3 -m pip install openai-whisper torch`
   - System dependency: install `ffmpeg` with the user's package manager, such as Homebrew or apt.
5. Run the bundled script when dependencies are present:

   ```bash
   python3 ${CLAUDE_PLUGIN_ROOT}/skills/audio-transcription/scripts/transcribe_audio.py "recording.mp3" --backend auto
   ```

6. Verify the output Markdown exists, is non-empty, and contains either timestamped segments or a transcript body.

## Bundled Script

Common commands:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/audio-transcription/scripts/transcribe_audio.py "recording.mp3"
python3 ${CLAUDE_PLUGIN_ROOT}/skills/audio-transcription/scripts/transcribe_audio.py "recording.mp3" --output "recording.md" --language en
python3 ${CLAUDE_PLUGIN_ROOT}/skills/audio-transcription/scripts/transcribe_audio.py "meeting-recording.m4a" --title "Meeting Recording" --note "Optional context"
python3 ${CLAUDE_PLUGIN_ROOT}/skills/audio-transcription/scripts/transcribe_audio.py "recording.mp3" --backend mlx --mlx-model mlx-community/whisper-large-v3-mlx
```

Non-Apple-Silicon fallback command:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/audio-transcription/scripts/transcribe_audio.py "recording.mp3" --backend whisper --whisper-model medium
```

For batch transcription, loop over discovered audio files and skip existing `.md` outputs unless the user explicitly wants regeneration.

### Incremental output

By default the script transcribes long audio in chunks and rewrites the Markdown after each chunk (atomic temp-file + rename), so an interrupted run still leaves a partial transcript on disk. Chunking targets ~10 checkpoints but never makes a chunk shorter than 120s, so short clips stay a single chunk.

- `--checkpoint-chunks N` — target number of checkpoints (default 10). `--checkpoint-chunks 1` disables chunking (single-shot, original behavior).
- `--checkpoint-min-seconds S` — minimum chunk length (default 120). Chunk boundaries lose cross-chunk context, so smaller chunks transcribe more frequently but can roughen sentences split across a boundary.

## Dependency Guidance

- Use `mlx-whisper` on macOS Apple Silicon. The bundled script enforces this and exits if `--backend whisper` is requested on Apple Silicon.
- Use `openai-whisper` plus `torch` as the general fallback across platforms.
- Whisper model downloads may require network access. Ask the user before running a command that will download packages or model weights.
- `ffmpeg` must be available on `PATH` for most audio formats.

## Output

The default output is a Markdown file next to the audio file with the same basename. It contains:

- A title heading.
- A `Source` section with audio filename, backend, model, language, and optional speaker metadata.
- A `Transcript` section with `[start-end] text` segments when segment timestamps are available.
