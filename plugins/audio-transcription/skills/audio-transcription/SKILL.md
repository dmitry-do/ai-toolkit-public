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
- Default MLX model: `mlx-community/whisper-large-v3-mlx` — **the most accurate model is the default.** Pass `--mlx-model mlx-community/whisper-large-v3-turbo` when turnaround matters more than precision.
- **Multilingual:** both models support ~99 languages and **auto-detect the spoken language** when `--language` is omitted (the detected language is written to the output). Pass `--language <code>` (e.g. `en`, `es`, `ru`) to pin it. Accuracy varies by language and is generally highest for English; the figures below were measured on English audio.
- Accuracy vs. speed tradeoff (measured on LibriSpeech test-clean/test-other chapters + a LibriVox audiobook chapter; see `evals/results.md` and `evals/librispeech/results.md`):
  - **Accuracy:** large-v3 beats turbo overall — **3.17% vs 3.33% weighted WER**, with the edge concentrated on clean speech (LibriSpeech clean **1.59% vs 1.90%**, audiobook **3.4% vs 3.8%**); on noisy/accented speech (test-other) they are within noise of each other (4.17% vs 4.02%).
  - **Speed:** that precision costs **~2.3× the time** — still ~10× realtime.
  - **Example — a 10-minute recording (Apple Silicon):** large-v3 finishes in **~65 s**; turbo in **~26 s**.
  - **Rule of thumb:** keep the large-v3 default. Reach for `--mlx-model mlx-community/whisper-large-v3-turbo` for long batches, quick drafts, or anything where a ~5–15% relative accuracy edge isn't worth 2.3× the wait.
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
python3 ${CLAUDE_PLUGIN_ROOT}/skills/audio-transcription/scripts/transcribe_audio.py "recording.mp3" --backend mlx --mlx-model mlx-community/whisper-large-v3-turbo  # turbo = ~2.3× faster, slightly less accurate
```

Non-Apple-Silicon fallback command:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/audio-transcription/scripts/transcribe_audio.py "recording.mp3" --backend whisper --whisper-model medium
```

For batch transcription, loop over discovered audio files and skip existing `.md` outputs unless the user explicitly wants regeneration.

### Incremental output

By default the script transcribes long audio in chunks and rewrites the Markdown after each chunk (atomic temp-file + rename), so an interrupted run still leaves a partial transcript on disk. Chunking targets ~10 checkpoints but never makes a chunk shorter than 45s, so short clips stay a single chunk.

- `--checkpoint-chunks N` — target number of checkpoints (default 10). `--checkpoint-chunks 1` disables chunking (single-shot, original behavior).
- `--checkpoint-min-seconds S` — minimum chunk length (default 45). Boundary snapping (default-on) lands cuts in pauses, so chunks this small stay accuracy-neutral while giving more frequent crash-safety checkpoints; it keeps cuts above Whisper's 30s internal window. Measured: floor 45 ≈ floor 120 on WER and speed (sweep in `evals/results.md`); going below ~20s starts to cost accuracy and wall time.
- Each chunk is transcribed with only the user's `--prompt` — the previous chunk's text is deliberately **not** carried across the boundary (carrying it conditions the decoder across chunks and can make Whisper silently drop the start of a chunk; measured at ~75 words lost).

### Silence skipping (on by default)

The script detects speech regions by energy and skips silences longer than ~2s (`--skip-silence`, default on). On silence-heavy recordings this is both faster and **more accurate** — Whisper hallucinates phrases (e.g. "Thank you.") in long silences, and skipping them removes those. Measured on a fixture with 300s of inserted silence: 4.3% vs 5.2% WER, ~15% faster.

- Timestamps keep the original timeline (a sentence after a skipped gap keeps its real start time).
- It self-gates: it only engages when it would save ≥10s (or ≥20% of a short file), so continuous recordings are transcribed exactly as before; if no speech is detected at all, the full audio is transcribed.
- The threshold is conservative (30 dB under the loud parts, 0.3s padding, only >2s silences) — a quiet speaker 25 dB below the rest of the room is fully retained.
- Pass `--no-skip-silence` to opt out, e.g. for music with long genuinely-quiet passages where even faint content matters.

### Boundary snapping (on by default)

Chunk boundaries are snapped to the nearest detected speech pause (`--snap-boundaries`, default on), so a cut lands in silence instead of mid-word. A word split across a hard cut gets mis-transcribed on both sides; landing the cut in a pause avoids that. It self-gates — if a boundary already sits in a quiet spot, or no pause is nearby, the cut stays put (measured mean shift ~1s on continuous narration).

- The win grows as chunks shrink toward Whisper's 30s window. At ~34s chunks, equal-spaced cuts degrade badly (turbo 5.1%, large-v3 **8.8%** WER) while snapped cuts hold (turbo 4.3%, large-v3 **3.7%**). At the default chunk size it's a small, consistent improvement (4.3% → 4.0%).
- It composes with silence skipping: pauses are snapped *within* each speech region, so skipped silence and clean cuts stack.
- Chunk count and coverage are preserved (boundaries never cross a neighbour or move the region's outer edges), so resume and checkpointing are unaffected.
- Pass `--no-snap-boundaries` to use exact evenly-spaced cuts instead.

### Resuming after a failure (automatic)

During a chunked run the script also writes a small sidecar, `<output>.progress.json`, after every chunk (deleted automatically on success). If a chunk fails or the run is interrupted (crash, `Ctrl-C`, machine sleep), simply **re-run the same command** — the script detects the sidecar and resumes from the last completed chunk automatically; no flag needed.

- Resume only proceeds when the run identity is unchanged — same audio (path + size), model, language, and chunk plan. Change any of those (e.g. a different `--checkpoint-chunks`) and it safely starts fresh rather than stitching mismatched chunks.
- To force a full restart, delete the `<output>.progress.json` sidecar before re-running.
- Resume applies to chunked runs only (single-shot writes once, at the end, so there is nothing partial to resume).

### Second pass (on by default)

After the main transcription the script audits the result against the audio itself (`--second-pass`, default on) and repairs three Whisper failure modes locally:

- **Recovers silently deleted speech.** Whisper fails by leaving a hole — no token, no error. Spans inside speech regions that no segment covers but that contain voiced sound are re-transcribed in isolation and spliced in on the original timeline.
- **Drops spurious overlays.** On noisy audio Whisper sometimes emits a hallucinated segment (a 30s "Thank you.") *on top of* the real segments at a chunk head. A suspect segment whose span is already covered by other segments is removed.
- **Retries low-confidence segments.** A segment flagged by Whisper's own quality signals (`avg_logprob`, `compression_ratio`, implausibly sparse text for its span) that is the sole coverage of its audio is re-transcribed as a fresh window and replaced only when the retry scores better.

Measured: on noisy speech (LibriSpeech test-other chapters) it removes hallucination overlays and recovers deletions — large-v3 4.44% → 4.17% WER, turbo 4.05% → 4.02% — and on the audiobook fixture large-v3 3.5% → 3.4%. On clean recordings it self-gates to (near) zero extra model calls, so the cost is ~0–4% wall time. Recovered text that merely duplicates its neighbours (Whisper timestamps under-cover) is discarded. Pass `--no-second-pass` to opt out.

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
