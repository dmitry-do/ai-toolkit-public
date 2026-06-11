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
- Default MLX model: `mlx-community/whisper-large-v3-turbo` — **use turbo by default.** It is fast and accurate enough for almost everything.
- **Multilingual:** both models support ~99 languages and **auto-detect the spoken language** when `--language` is omitted (the detected language is written to the output). Pass `--language <code>` (e.g. `en`, `es`, `ru`) to pin it. Accuracy varies by language and is generally highest for English; the figures below were measured on English audio.
- Accuracy vs. speed tradeoff (measured on our eval fixture; see `evals/results.md`):
  - **Accuracy:** the larger `mlx-community/whisper-large-v3-mlx` is only marginally more precise — about **96% vs. ~95% word accuracy** (≈0.9 percentage points lower word-error rate; ~10–20% fewer word errors).
  - **Speed:** that precision costs **~2.5× the time.**
  - **Example — a 10-minute recording (Apple Silicon):** turbo finishes in **~25 s**; large-v3 takes **~60 s** for that ~1-point accuracy gain. Both are far faster than realtime.
  - **Rule of thumb:** stick with turbo. Reach for `--mlx-model mlx-community/whisper-large-v3-mlx` only when transcript precision matters more than turnaround (e.g. legal/medical wording, hard-to-hear audio).
- Model source: `https://huggingface.co/mlx-community/whisper-large-v3-turbo`.
- `mlx-whisper` can load the model directly from Hugging Face with `path_or_hf_repo="mlx-community/whisper-large-v3-turbo"`; the first run may download model weights.
- Manual model download command, if the user approves network access:

  ```bash
  python3 -m pip install 'huggingface_hub[hf_xet]'
  huggingface-cli download --local-dir whisper-large-v3-turbo mlx-community/whisper-large-v3-turbo
  ```

  To use the downloaded copy, pass `--mlx-model ./whisper-large-v3-turbo` (or an absolute path) to the bundled script; otherwise the script loads the model from Hugging Face into the HF cache.

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
python3 ${CLAUDE_PLUGIN_ROOT}/skills/audio-transcription/scripts/transcribe_audio.py "recording.mp3" --backend mlx --mlx-model mlx-community/whisper-large-v3-mlx  # large-v3 = ~1pp more accurate, ~2.5× slower
```

Non-Apple-Silicon fallback command:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/audio-transcription/scripts/transcribe_audio.py "recording.mp3" --backend whisper --whisper-model medium
```

For batch transcription, loop over discovered audio files and skip existing `.md` outputs unless the user explicitly wants regeneration.

### Incremental output

By default the script transcribes long audio in chunks and rewrites the Markdown after each chunk (atomic temp-file + rename), so an interrupted run still leaves a partial transcript on disk. Chunking targets ~10 checkpoints but never makes a chunk shorter than 120s, so short clips stay a single chunk.

- `--checkpoint-chunks N` — target number of checkpoints (default 10). `--checkpoint-chunks 1` disables chunking (single-shot, original behavior).
- `--checkpoint-min-seconds S` — minimum chunk length (default 120). Keep chunks well above Whisper's internal 30s window; the 120s floor is measured to be accuracy-neutral.
- Each chunk is transcribed with only the user's `--prompt` — the previous chunk's text is deliberately **not** carried across the boundary (carrying it conditions the decoder across chunks and can make Whisper silently drop the start of a chunk; measured at ~75 words lost).

### Silence skipping (on by default)

The script detects speech regions by energy and skips silences longer than ~2s (`--skip-silence`, default on). On silence-heavy recordings this is both faster and **more accurate** — Whisper hallucinates phrases (e.g. "Thank you.") in long silences, and skipping them removes those. Measured on a fixture with 300s of inserted silence: 4.3% vs 5.2% WER, ~15% faster.

- Timestamps keep the original timeline (a sentence after a skipped gap keeps its real start time).
- It self-gates: it only engages when it would save ≥10s (or ≥20% of a short file), so continuous recordings are transcribed exactly as before; if no speech is detected at all, the full audio is transcribed.
- The threshold is conservative (30 dB under the loud parts, 0.3s padding, only >2s silences) — a quiet speaker 25 dB below the rest of the room is fully retained.
- Pass `--no-skip-silence` to opt out, e.g. for music with long genuinely-quiet passages where even faint content matters.

### Resuming after a failure (automatic)

During a chunked run the script also writes a small sidecar, `<output>.progress.json`, after every chunk (deleted automatically on success). If a chunk fails or the run is interrupted (crash, `Ctrl-C`, machine sleep), simply **re-run the same command** — the script detects the sidecar and resumes from the last completed chunk automatically; no flag needed.

- Resume only proceeds when the run identity is unchanged — same audio (path + size), model, language, and chunk plan. Change any of those (e.g. a different `--checkpoint-chunks`) and it safely starts fresh rather than stitching mismatched chunks.
- To force a full restart, delete the `<output>.progress.json` sidecar before re-running.
- Resume applies to chunked runs only (single-shot writes once, at the end, so there is nothing partial to resume).

### Repetition-loop hallucinations

Whisper can fall into a repetition loop (one phrase repeated for minutes), inflating output and dropping real speech. It is driven by `condition_on_previous_text`, which is **disabled by default** here precisely to prevent these loops. Pass `--condition-previous` to re-enable cross-segment conditioning (slightly better cross-sentence coherence, but it can re-introduce the loops on long audio).

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
