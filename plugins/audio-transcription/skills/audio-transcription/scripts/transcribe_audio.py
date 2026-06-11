#!/usr/bin/env python3
from __future__ import annotations

import argparse
import contextlib
import importlib
import importlib.util
import json
import os
import platform
import shutil
import sys
import time
from pathlib import Path

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows fallback
    fcntl = None


DEFAULT_MLX_MODEL = "mlx-community/whisper-large-v3-turbo"
MLX_MODEL_SOURCE_URL = "https://huggingface.co/mlx-community/whisper-large-v3-turbo"
MLX_MODEL_DOWNLOAD_COMMAND = "huggingface-cli download --local-dir whisper-large-v3-turbo mlx-community/whisper-large-v3-turbo"
DEFAULT_WHISPER_MODEL = "large-v3"
DEFAULT_LOCK_DIR = Path("/tmp/audio-transcription-locks")
SUPPORTED_AUDIO_SUFFIXES = (".wav", ".mp3", ".m4a")
SAMPLE_RATE = 16000
DEFAULT_CHECKPOINT_CHUNKS = 10
DEFAULT_CHECKPOINT_MIN_SECONDS = 120.0


def fail(message: str, code: int = 1) -> None:
    print(message, file=sys.stderr)
    raise SystemExit(code)


def module_available(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def command_available(name: str) -> bool:
    return shutil.which(name) is not None


def environment_report(apple_silicon: bool) -> list[tuple[str, bool, str]]:
    report = [
        ("ffmpeg", command_available("ffmpeg"), "required for decoding supported audio formats"),
        ("mlx_whisper", module_available("mlx_whisper"), "required Apple Silicon backend"),
    ]
    if not apple_silicon:
        report.extend([
            ("whisper", module_available("whisper"), "reference OpenAI Whisper backend"),
            ("torch", module_available("torch"), "required by reference OpenAI Whisper"),
        ])
    return report


def print_check() -> int:
    apple_silicon = is_apple_silicon()
    print(f"{'ok' if apple_silicon else 'info':8} {'apple_silicon':12} {platform.system()} {platform.machine()}")
    if apple_silicon:
        print(f"{'info':8} {'required':12} Apple Silicon must use mlx-whisper for this skill")
        print(f"{'info':8} {'mlx_model':12} {DEFAULT_MLX_MODEL}")
        print(f"{'info':8} {'model_url':12} {MLX_MODEL_SOURCE_URL}")

    report = environment_report(apple_silicon)
    for name, available, note in report:
        status = "ok" if available else "missing"
        print(f"{status:8} {name:12} {note}")

    has_mlx = module_available("mlx_whisper")
    has_whisper = module_available("whisper") and module_available("torch")
    if command_available("ffmpeg") and ((apple_silicon and has_mlx) or (not apple_silicon and (has_mlx or has_whisper))):
        return 0

    sys.stdout.flush()
    print("", file=sys.stderr)
    print("Install hints:", file=sys.stderr)
    if not command_available("ffmpeg"):
        print("- Install ffmpeg with your system package manager.", file=sys.stderr)
    if apple_silicon and not has_mlx:
        print("- Apple Silicon requires MLX Whisper: python3 -m pip install mlx-whisper", file=sys.stderr)
        print(f"- MLX model: {DEFAULT_MLX_MODEL}", file=sys.stderr)
        print(f"- Model source: {MLX_MODEL_SOURCE_URL}", file=sys.stderr)
        print(f"- Optional manual download: {MLX_MODEL_DOWNLOAD_COMMAND}", file=sys.stderr)
    if not apple_silicon and not has_whisper:
        print("- Portable fallback: python3 -m pip install openai-whisper torch", file=sys.stderr)
    return 1


def is_apple_silicon() -> bool:
    return sys.platform == "darwin" and platform.machine() in {"arm64", "aarch64"}


def choose_backend(requested: str) -> str:
    has_mlx = module_available("mlx_whisper")
    has_whisper = module_available("whisper") and module_available("torch")

    if is_apple_silicon():
        if requested == "whisper":
            fail(
                "Apple Silicon detected. This skill must use mlx-whisper on Apple Silicon; "
                f"use --backend mlx with model {DEFAULT_MLX_MODEL}. Model source: {MLX_MODEL_SOURCE_URL}",
                4,
            )
        if not has_mlx:
            fail(
                "Apple Silicon detected, but mlx-whisper is missing. "
                "Ask the user before installing it with: python3 -m pip install mlx-whisper. "
                f"Default model: {DEFAULT_MLX_MODEL}. Model source: {MLX_MODEL_SOURCE_URL}",
                4,
            )
        return "mlx"

    if requested == "mlx":
        if not has_mlx:
            fail("Missing dependency: mlx-whisper. Install with: python3 -m pip install mlx-whisper", 4)
        return "mlx"

    if requested == "whisper":
        if not has_whisper:
            fail("Missing dependencies: openai-whisper and torch. Install with: python3 -m pip install openai-whisper torch", 4)
        return "whisper"

    if has_whisper:
        return "whisper"
    if has_mlx:
        return "mlx"

    fail(
        "No transcription backend is installed. Run with --check for install hints, then ask the user before installing dependencies.",
        4,
    )


def choose_device(requested: str) -> str:
    if requested != "auto":
        return requested

    torch = importlib.import_module("torch")
    if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
        return "mps"
    if torch.cuda.is_available():
        return "cuda"
    return "cpu"


def read_prompt(args: argparse.Namespace) -> str | None:
    parts: list[str] = []
    if args.prompt:
        parts.append(args.prompt.strip())
    if args.prompt_file:
        if not args.prompt_file.exists():
            fail(f"Prompt file not found: {args.prompt_file}", 2)
        parts.append(args.prompt_file.read_text(encoding="utf-8").strip())
    prompt = "\n".join(part for part in parts if part)
    return prompt or None


def validate_audio_path(audio_path: Path) -> None:
    if audio_path.suffix.lower() not in SUPPORTED_AUDIO_SUFFIXES:
        supported = ", ".join(suffix.lstrip(".") for suffix in SUPPORTED_AUDIO_SUFFIXES)
        fail(f"Unsupported audio format: {audio_path.suffix or '(none)'}. Supported formats: {supported}.", 2)


def format_ts(seconds: float) -> str:
    total = int(round(seconds))
    hours = total // 3600
    minutes = (total % 3600) // 60
    secs = total % 60
    if hours:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def plan_chunks(duration, target_chunks=DEFAULT_CHECKPOINT_CHUNKS, floor_seconds=DEFAULT_CHECKPOINT_MIN_SECONDS):
    """Split a duration (seconds) into contiguous (start, end) chunks.

    Aims for ``target_chunks`` chunks but never makes a chunk shorter than
    ``floor_seconds``, so short audio collapses to a single chunk.
    """
    if duration <= 0:
        return [(0.0, 0.0)]
    n = max(1, min(target_chunks, int(duration // floor_seconds)))
    size = duration / n
    return [(i * size, duration if i == n - 1 else (i + 1) * size) for i in range(n)]


def offset_segments(segments, offset):
    """Return copies of ``segments`` with start/end shifted by ``offset`` seconds."""
    shifted = []
    for seg in segments:
        moved = dict(seg)
        moved["start"] = seg.get("start", 0.0) + offset
        moved["end"] = seg.get("end", 0.0) + offset
        shifted.append(moved)
    return shifted


def build_chunk_prompt(base_prompt, prev_text, tail_chars=200):
    """Combine the user prompt with the tail of the previous chunk's text."""
    tail = prev_text[-tail_chars:].strip() if prev_text else ""
    parts = [part for part in (base_prompt, tail) if part]
    return " ".join(parts).strip() or None


def transcribe_chunked(audio, chunks, transcribe_fn, on_progress, base_prompt=None, resume_state=None):
    """Transcribe ``audio`` chunk-by-chunk, persisting after each via ``on_progress``.

    ``transcribe_fn(audio_slice, initial_prompt, language)`` returns a result dict.
    ``on_progress(accumulated_result)`` is called after every chunk so the caller
    can write partial output to disk; ``accumulated_result`` carries ``done`` (the
    number of chunks finished so far) and ``text_parts`` so progress can be
    checkpointed and later resumed. Pass ``resume_state`` (from a prior run) to
    skip the chunks already completed. Returns the accumulated result dict.
    """
    if resume_state:
        all_segments = list(resume_state.get("segments") or [])
        text_parts = list(resume_state.get("text_parts") or [])
        language = resume_state.get("language")
        start_index = int(resume_state.get("done") or 0)
    else:
        all_segments, text_parts, language, start_index = [], [], None, 0

    for index in range(start_index, len(chunks)):
        start_s, end_s = chunks[index]
        slice_audio = audio[int(start_s * SAMPLE_RATE):int(end_s * SAMPLE_RATE)]
        prompt = build_chunk_prompt(base_prompt, text_parts[-1] if text_parts else "")
        result = transcribe_fn(slice_audio, prompt, language)
        if language is None:
            language = result.get("language")
        all_segments.extend(offset_segments(result.get("segments") or [], start_s))
        chunk_text = (result.get("text") or "").strip()
        if chunk_text:
            text_parts.append(chunk_text)
        on_progress({
            "segments": all_segments,
            "text": " ".join(text_parts),
            "language": language,
            "text_parts": list(text_parts),
            "done": index + 1,
        })
    return {"segments": all_segments, "text": " ".join(text_parts), "language": language}


def progress_path(output_path):
    """Sidecar file recording chunked-transcription progress for ``--resume``."""
    return output_path.with_name(output_path.name + ".progress.json")


def resume_signature(audio_path, model_name, language, chunks):
    """Identity of a chunked run; resuming is only valid when this is unchanged."""
    audio_path = Path(audio_path)
    return {
        "audio": str(audio_path.resolve()),
        "audio_size": audio_path.stat().st_size,
        "model": model_name,
        "language": language or "",
        "chunks": [[round(start, 3), round(end, 3)] for start, end in chunks],
    }


def write_progress(progress_file, signature, accumulated):
    """Atomically persist the signature + accumulated segments and completed-chunk count."""
    data = dict(signature)
    data["done"] = accumulated.get("done", 0)
    data["language_detected"] = accumulated.get("language")
    data["segments"] = accumulated.get("segments") or []
    data["text_parts"] = accumulated.get("text_parts") or []
    progress_file = Path(progress_file)
    tmp_path = progress_file.with_name(progress_file.name + ".tmp")
    tmp_path.write_text(json.dumps(data), encoding="utf-8")
    os.replace(tmp_path, progress_file)


def load_progress(progress_file, signature):
    """Return resumable state when the sidecar matches ``signature``, else ``None``.

    Returns ``None`` if the file is missing/corrupt, the run identity changed
    (audio, model, language, or chunk plan), or there is nothing useful to resume
    (no chunk finished yet, or every chunk already finished).
    """
    progress_file = Path(progress_file)
    if not progress_file.exists():
        return None
    try:
        data = json.loads(progress_file.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return None
    if any(data.get(key) != signature.get(key) for key in signature):
        return None
    done = int(data.get("done") or 0)
    if done <= 0 or done >= len(signature["chunks"]):
        return None
    return {
        "done": done,
        "segments": data.get("segments") or [],
        "text_parts": data.get("text_parts") or [],
        "language": data.get("language_detected"),
    }


def load_audio_array(backend, audio_path):
    """Load audio as a 16 kHz mono numpy array using the backend's loader."""
    module_name = "mlx_whisper.audio" if backend == "mlx" else "whisper.audio"
    return importlib.import_module(module_name).load_audio(str(audio_path))


def make_mlx_transcribe_fn(model_name, args):
    """Build a transcribe callable for the mlx-whisper backend (model is cached)."""
    mlx_whisper = importlib.import_module("mlx_whisper")

    def transcribe_fn(audio, initial_prompt, language):
        kwargs = {
            "path_or_hf_repo": model_name,
            "verbose": False,
            "temperature": 0.0,
            "condition_on_previous_text": getattr(args, "condition_previous", False),
            "task": "transcribe",
        }
        if initial_prompt:
            kwargs["initial_prompt"] = initial_prompt
        chosen = language or args.language
        if chosen:
            kwargs["language"] = chosen
        return mlx_whisper.transcribe(audio, **kwargs)

    return transcribe_fn


def make_whisper_transcribe_fn(model_name, args, device):
    """Build a transcribe callable for the openai-whisper backend (model loaded once)."""
    whisper = importlib.import_module("whisper")
    load_kwargs = {"device": device}
    if args.model_dir:
        args.model_dir.mkdir(parents=True, exist_ok=True)
        load_kwargs["download_root"] = str(args.model_dir)
    model = whisper.load_model(model_name, **load_kwargs)

    def transcribe_fn(audio, initial_prompt, language):
        kwargs = {
            "task": "transcribe",
            "verbose": False,
            "temperature": 0,
            "beam_size": args.beam_size,
            "best_of": args.beam_size,
            "condition_on_previous_text": getattr(args, "condition_previous", False),
            "fp16": device != "cpu",
        }
        if initial_prompt:
            kwargs["initial_prompt"] = initial_prompt
        chosen = language or args.language
        if chosen:
            kwargs["language"] = chosen
        return model.transcribe(audio, **kwargs)

    return transcribe_fn


def acquire_transcription_slot(lock_dir: Path, slots: int):
    lock_dir.mkdir(parents=True, exist_ok=True)
    while True:
        for index in range(slots):
            handle = (lock_dir / f"slot-{index}.lock").open("w")
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                handle.close()
                continue
            print(f"Acquired transcription slot {index + 1}/{slots}.", file=sys.stderr)
            return handle
        print("Waiting for a transcription slot...", file=sys.stderr)
        time.sleep(30)


@contextlib.contextmanager
def transcription_slot(lock_dir: Path, slots: int):
    if slots <= 0 or fcntl is None:
        yield
        return

    # Acquisition happens outside the yield so a BlockingIOError raised by the
    # with-body cannot be caught by the slot-probe loop (which would silently
    # release the lock and mask the real error).
    handle = acquire_transcription_slot(lock_dir, slots)
    try:
        yield
    finally:
        fcntl.flock(handle, fcntl.LOCK_UN)
        handle.close()


def transcribe_mlx(audio_path: Path, model_name: str, args: argparse.Namespace, prompt: str | None) -> tuple[dict, str | None]:
    model_path = Path(model_name).expanduser()
    if model_name.startswith(("/", "./", "../", "~")) and not model_path.exists():
        fail(f"MLX model path not found: {model_path}", 2)

    print(f"Transcribing {audio_path.name} with mlx-whisper...", file=sys.stderr)
    if model_name == DEFAULT_MLX_MODEL:
        print(f"Using MLX model {model_name} from {MLX_MODEL_SOURCE_URL}", file=sys.stderr)
    transcribe_fn = make_mlx_transcribe_fn(model_name, args)
    return transcribe_fn(str(audio_path), prompt, None), None


def transcribe_openai_whisper(
    audio_path: Path,
    model_name: str,
    args: argparse.Namespace,
    prompt: str | None,
) -> tuple[dict, str]:
    whisper = importlib.import_module("whisper")
    device = choose_device(args.device)

    def run(selected_device: str) -> dict:
        print(f"Loading Whisper {model_name} on {selected_device}...", file=sys.stderr)
        load_kwargs = {"device": selected_device}
        if args.model_dir:
            args.model_dir.mkdir(parents=True, exist_ok=True)
            load_kwargs["download_root"] = str(args.model_dir)
        model = whisper.load_model(model_name, **load_kwargs)

        transcribe_kwargs = {
            "task": "transcribe",
            "verbose": False,
            "temperature": 0,
            "beam_size": args.beam_size,
            "best_of": args.beam_size,
            "condition_on_previous_text": getattr(args, "condition_previous", False),
            "fp16": selected_device != "cpu",
        }
        if prompt:
            transcribe_kwargs["initial_prompt"] = prompt
        if args.language:
            transcribe_kwargs["language"] = args.language

        print(f"Transcribing {audio_path.name}...", file=sys.stderr)
        return model.transcribe(str(audio_path), **transcribe_kwargs)

    try:
        return run(device), device
    except RuntimeError as exc:
        if device == "cpu":
            raise
        print(f"Device {device} failed: {exc}", file=sys.stderr)
        print("Retrying on CPU...", file=sys.stderr)
        return run("cpu"), "cpu"


def write_markdown(
    output_path: Path,
    audio_path: Path,
    backend: str,
    model_name: str,
    device: str | None,
    args: argparse.Namespace,
    result: dict,
) -> None:
    title = args.title or audio_path.stem
    language = result.get("language") or args.language or "unknown"

    lines = [f"# {title}", "", "## Source"]
    lines.append(f"- Audio: `{audio_path.name}`")
    lines.append(f"- Backend: `{backend}`")
    lines.append(f"- Model: `{model_name}`")
    if device:
        lines.append(f"- Device: `{device}`")
    lines.append(f"- Detected language: `{language}`")
    if args.speaker:
        lines.append(f"- Speaker: {args.speaker}")
    if args.note:
        for note in args.note:
            lines.append(f"- Note: {note}")

    lines.extend(["", "## Transcript", ""])
    segments = result.get("segments") or []
    for segment in segments:
        text = str(segment.get("text", "")).strip()
        if not text:
            continue
        start = format_ts(float(segment.get("start", 0)))
        end = format_ts(float(segment.get("end", 0)))
        lines.append(f"[{start}-{end}] {text}")
        lines.append("")

    if not segments and result.get("text"):
        lines.append(str(result["text"]).strip())
        lines.append("")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = output_path.with_name(output_path.name + ".tmp")
    tmp_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    os.replace(tmp_path, output_path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Transcribe an audio file to timestamped Markdown.")
    parser.add_argument("audio", nargs="?", type=Path, help="Audio file to transcribe.")
    parser.add_argument("--output", type=Path, help="Markdown output path. Defaults to the audio basename with .md.")
    parser.add_argument(
        "--backend",
        choices=["auto", "mlx", "whisper"],
        default="auto",
        help="Backend to use. On Apple Silicon, mlx is required and whisper is rejected.",
    )
    parser.add_argument("--model", help="Model for the selected backend. Overrides backend-specific defaults.")
    parser.add_argument("--mlx-model", default=DEFAULT_MLX_MODEL)
    parser.add_argument("--whisper-model", default=DEFAULT_WHISPER_MODEL)
    parser.add_argument("--model-dir", type=Path, help="Download/cache directory for openai-whisper models.")
    parser.add_argument("--device", default="auto", help="Device for openai-whisper: auto, cpu, cuda, or mps.")
    parser.add_argument("--language", help="Optional language code, such as en. Omit for auto-detection.")
    parser.add_argument("--prompt", help="Optional initial prompt with names, jargon, or context.")
    parser.add_argument("--prompt-file", type=Path, help="Text file containing additional prompt context.")
    parser.add_argument("--title", help="Markdown title. Defaults to the audio filename stem.")
    parser.add_argument("--speaker", help="Optional speaker metadata for the Source section.")
    parser.add_argument("--note", action="append", help="Optional Source note. Can be used multiple times.")
    parser.add_argument("--beam-size", type=int, default=5)
    parser.add_argument("--lock-dir", type=Path, default=DEFAULT_LOCK_DIR)
    parser.add_argument("--parallel-slots", type=int, default=1)
    parser.add_argument(
        "--condition-previous",
        action="store_true",
        help="Enable condition_on_previous_text (off by default; turning it on risks repetition-loop hallucinations on long audio).",
    )
    parser.add_argument(
        "--checkpoint-chunks",
        type=int,
        default=DEFAULT_CHECKPOINT_CHUNKS,
        help="Target number of incremental write checkpoints. 1 disables chunking (single-shot).",
    )
    parser.add_argument(
        "--checkpoint-min-seconds",
        type=float,
        default=DEFAULT_CHECKPOINT_MIN_SECONDS,
        help="Minimum chunk length in seconds; prevents tiny chunks on short audio.",
    )
    parser.add_argument("--check", action="store_true", help="Check local dependencies and print install hints.")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.check:
        raise SystemExit(print_check())

    if not args.audio:
        parser.error("audio is required unless --check is used")
    if not args.audio.exists():
        fail(f"Audio file not found: {args.audio}", 2)
    validate_audio_path(args.audio)
    if not command_available("ffmpeg"):
        fail("Missing system dependency: ffmpeg. Ask the user before installing it.", 4)

    backend = choose_backend(args.backend)
    model_name = args.model or (args.mlx_model if backend == "mlx" else args.whisper_model)
    output_path = args.output or args.audio.with_suffix(".md")
    prompt = read_prompt(args)

    with transcription_slot(args.lock_dir, args.parallel_slots):
        chunks = []
        if args.checkpoint_chunks > 1:
            audio = load_audio_array(backend, args.audio)
            chunks = plan_chunks(
                len(audio) / SAMPLE_RATE,
                args.checkpoint_chunks,
                args.checkpoint_min_seconds,
            )

        if len(chunks) > 1:
            device = None if backend == "mlx" else choose_device(args.device)
            transcribe_fn = (
                make_mlx_transcribe_fn(model_name, args)
                if backend == "mlx"
                else make_whisper_transcribe_fn(model_name, args, device)
            )

            prog_file = progress_path(output_path)
            signature = resume_signature(args.audio, model_name, args.language, chunks)
            resume_state = load_progress(prog_file, signature)
            if resume_state:
                print(
                    f"Resuming: {resume_state['done']}/{len(chunks)} chunks already done; "
                    f"continuing from chunk {resume_state['done'] + 1}.",
                    file=sys.stderr,
                )
            elif prog_file.exists():
                print(
                    "Saved progress found but it does not match this run "
                    "(audio, model, language, or chunk plan changed); starting fresh.",
                    file=sys.stderr,
                )

            print(
                f"Transcribing {args.audio.name} in {len(chunks)} chunks with {backend}; "
                "writing after each.",
                file=sys.stderr,
            )

            def write_checkpoint(accumulated):
                write_markdown(output_path, args.audio, backend, model_name, device, args, accumulated)
                write_progress(prog_file, signature, accumulated)
                print(
                    f"  checkpoint: chunk {accumulated['done']}/{len(chunks)}, "
                    f"{len(accumulated['segments'])} segments -> {output_path}",
                    file=sys.stderr,
                )

            try:
                result = transcribe_chunked(
                    audio, chunks, transcribe_fn, write_checkpoint,
                    base_prompt=prompt, resume_state=resume_state,
                )
            except Exception as exc:
                if prog_file.exists():
                    print(f"\nA chunk failed: {exc}", file=sys.stderr)
                    print(
                        f"Progress was saved to {prog_file}. Re-run the same command to "
                        "resume from the last completed chunk automatically.",
                        file=sys.stderr,
                    )
                raise

            # Completed cleanly — the progress sidecar is no longer needed.
            try:
                prog_file.unlink()
            except OSError:
                pass
        elif backend == "mlx":
            result, device = transcribe_mlx(args.audio, model_name, args, prompt)
        else:
            result, device = transcribe_openai_whisper(args.audio, model_name, args, prompt)

    if not (result.get("segments") or str(result.get("text", "")).strip()):
        fail(f"No transcript text produced for {args.audio}", 3)

    write_markdown(output_path, args.audio, backend, model_name, device, args, result)
    print(output_path)


if __name__ == "__main__":
    main()
