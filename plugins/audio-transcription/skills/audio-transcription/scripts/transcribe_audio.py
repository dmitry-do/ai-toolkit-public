#!/usr/bin/env python3
from __future__ import annotations

import argparse
import bisect
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


def _speech_frame_mask(audio, sample_rate=SAMPLE_RATE, frame_seconds=0.03):
    """RMS energy per frame -> (boolean speech mask, frame length s, duration s).

    The threshold sits 30 dB under the loud (95th-percentile) frames with an
    absolute floor, so a noisy-but-quiet recording degrades to "everything is
    speech" rather than to dropped words. ``mask`` is ``None`` when the clip is
    shorter than a single frame. Shared by ``detect_speech_regions`` (which
    cares about long gaps) and ``detect_pauses`` (which cares about short ones).
    """
    np = importlib.import_module("numpy")
    audio = np.asarray(audio, dtype=np.float32)
    duration = len(audio) / sample_rate
    frame = max(1, int(frame_seconds * sample_rate))
    n_frames = len(audio) // frame
    frame_s = frame / sample_rate
    if n_frames == 0:
        return None, frame_s, duration
    frames = audio[: n_frames * frame].reshape(n_frames, frame).astype(np.float64)
    rms = np.sqrt(np.mean(frames ** 2, axis=1))
    threshold = max(1e-4, float(np.percentile(rms, 95)) * 10 ** (-30 / 20))
    return rms >= threshold, frame_s, duration


def detect_speech_regions(audio, sample_rate=SAMPLE_RATE, frame_seconds=0.03,
                          min_silence_seconds=2.0, pad_seconds=0.3):
    """Find (start, end) speech regions in seconds using frame RMS energy.

    Conservative by design: only silences longer than ``min_silence_seconds``
    split regions, each region keeps ``pad_seconds`` of margin, and the
    threshold sits 30 dB under the loud frames (with an absolute floor), so a
    noisy-but-quiet recording degrades to "everything is speech" rather than
    to dropped words. Returns [] when no frame rises above the threshold.
    """
    speech, frame_s, duration = _speech_frame_mask(audio, sample_rate, frame_seconds)
    if speech is None:
        return [(0.0, duration)] if duration > 0 else []
    if not speech.any():
        return []

    raw = []
    start = None
    for index, is_speech in enumerate(speech):
        if is_speech and start is None:
            start = index
        elif not is_speech and start is not None:
            raw.append((start * frame_s, index * frame_s))
            start = None
    if start is not None:
        raw.append((start * frame_s, duration))

    merged = [list(raw[0])]
    for region_start, region_end in raw[1:]:
        if region_start - merged[-1][1] < min_silence_seconds:
            merged[-1][1] = region_end
        else:
            merged.append([region_start, region_end])
    return [
        (max(0.0, s - pad_seconds), min(duration, e + pad_seconds)) for s, e in merged
    ]


def detect_pauses(audio, sample_rate=SAMPLE_RATE, frame_seconds=0.03,
                  min_pause_seconds=0.35):
    """Center time (s) of every interior silence run >= ``min_pause_seconds``.

    These are the quiet spots — sentence and breath gaps — a chunk boundary can
    land in without splitting a word. Uses the same energy threshold as
    ``detect_speech_regions`` but reports the short pauses that function merges
    over (it only splits on >= 2 s gaps). Leading silence is reported (harmless,
    far from interior cuts); a trailing run to EOF is not, since it makes no
    useful interior boundary. Returns [] for silence or sub-frame clips.
    """
    speech, frame_s, _duration = _speech_frame_mask(audio, sample_rate, frame_seconds)
    if speech is None or not speech.any():
        return []
    pauses = []
    start = None
    for index, is_speech in enumerate(speech):
        if not is_speech and start is None:
            start = index
        elif is_speech and start is not None:
            if (index - start) * frame_s >= min_pause_seconds:
                pauses.append((start + index) / 2 * frame_s)
            start = None
    return pauses


def _nearest_pause(sorted_pauses, target, max_distance):
    """Nearest value in ``sorted_pauses`` within ``max_distance`` of ``target``,
    or ``None`` if the closest pause is farther than the window allows."""
    pos = bisect.bisect_left(sorted_pauses, target)
    best, best_distance = None, max_distance
    for j in (pos - 1, pos):
        if 0 <= j < len(sorted_pauses):
            distance = abs(sorted_pauses[j] - target)
            if distance <= best_distance:
                best, best_distance = sorted_pauses[j], distance
    return best


def snap_boundaries(chunks, pauses, max_shift_fraction=0.5):
    """Move each interior chunk boundary onto the nearest detected pause.

    ``chunks`` is a contiguous (start, end) list within ONE region. Each interior
    cut is pulled to the nearest pause within ``max_shift_fraction`` of the
    nominal chunk length, so the cut falls in silence instead of mid-word; a cut
    with no pause in range is left where it was. The region's outer start/end are
    never moved and boundaries stay strictly increasing (a snap never crosses a
    neighbour), so chunk count and coverage are preserved.
    """
    if len(chunks) < 2 or not pauses:
        return chunks
    pauses = sorted(pauses)
    region_start, region_end = chunks[0][0], chunks[-1][1]
    interior = [start for start, _ in chunks[1:]]  # cut points = each chunk's start after the first
    nominal = (region_end - region_start) / len(chunks)
    max_shift = max_shift_fraction * nominal

    points = [region_start]
    prev = region_start
    for index, boundary in enumerate(interior):
        next_ideal = interior[index + 1] if index + 1 < len(interior) else region_end
        candidate = _nearest_pause(pauses, boundary, max_shift)
        if candidate is not None and prev < candidate < next_ideal:
            boundary = candidate
        if boundary <= prev:  # safety: never invert or collapse a chunk to zero
            boundary = interior[index]
        points.append(boundary)
        prev = boundary
    points.append(region_end)
    return [(points[i], points[i + 1]) for i in range(len(points) - 1)]


def worth_skipping(kept_seconds, duration_seconds, min_save_seconds=10.0,
                   min_save_fraction=0.2):
    """Whether trimming silence saves enough time to justify moving chunk
    boundaries away from the untrimmed plan."""
    saved = duration_seconds - kept_seconds
    return saved >= min(min_save_seconds, min_save_fraction * duration_seconds)


def plan_chunks_over_regions(regions, target_chunks=DEFAULT_CHECKPOINT_CHUNKS,
                             floor_seconds=DEFAULT_CHECKPOINT_MIN_SECONDS,
                             pauses=None):
    """Apportion ``target_chunks`` across speech regions, then chunk each region.

    Returns (start, end) chunks in original-timeline seconds; the gaps between
    regions are simply absent from the plan, so silence is never transcribed.
    When ``pauses`` (from ``detect_pauses``) is given, each region's interior
    cuts are snapped onto the nearest pause so boundaries fall in silence.
    """
    total = sum(end - start for start, end in regions)
    chunks = []
    for start, end in regions:
        share = max(1, round(target_chunks * (end - start) / total)) if total > 0 else 1
        region_chunks = [
            (start + chunk_start, start + chunk_end)
            for chunk_start, chunk_end in plan_chunks(end - start, share, floor_seconds)
        ]
        if pauses:
            region_chunks = snap_boundaries(region_chunks, pauses)
        chunks.extend(region_chunks)
    return chunks


def offset_segments(segments, offset):
    """Return copies of ``segments`` with start/end shifted by ``offset`` seconds."""
    shifted = []
    for seg in segments:
        moved = dict(seg)
        moved["start"] = seg.get("start", 0.0) + offset
        moved["end"] = seg.get("end", 0.0) + offset
        shifted.append(moved)
    return shifted


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
        # Pass only the user's prompt — never the previous chunk's text. A carried
        # tail conditions the decoder across the boundary, which can make Whisper
        # silently drop the head of the chunk (measured: 75 words / 30 s lost).
        result = transcribe_fn(slice_audio, base_prompt, language)
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
    parser.add_argument(
        "--skip-silence",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Detect speech regions by energy and skip silences longer than ~2s "
        "instead of transcribing them (on by default; only engages when it saves "
        "meaningful time). Timestamps keep the original timeline. "
        "Disable with --no-skip-silence.",
    )
    parser.add_argument(
        "--snap-boundaries",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Snap each chunk boundary to the nearest detected speech pause so "
        "cuts land in silence instead of mid-word (on by default; a no-op when a "
        "boundary already sits in a quiet spot). Disable with --no-snap-boundaries.",
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
        trimmed = False
        if args.checkpoint_chunks > 1 or args.skip_silence:
            audio = load_audio_array(backend, args.audio)
            duration = len(audio) / SAMPLE_RATE
            regions = [(0.0, duration)]
            if args.skip_silence:
                detected = detect_speech_regions(audio)
                kept = sum(end - start for start, end in detected)
                if not detected:
                    print(
                        "Silence skip: no speech detected above the threshold; "
                        "transcribing the full audio.",
                        file=sys.stderr,
                    )
                elif worth_skipping(kept, duration):
                    regions = detected
                    print(
                        f"Silence skip: transcribing {kept:.0f}s of speech in "
                        f"{len(detected)} regions (skipping {duration - kept:.0f}s of silence).",
                        file=sys.stderr,
                    )
            trimmed = regions != [(0.0, duration)]
            pauses = detect_pauses(audio) if args.snap_boundaries else None
            chunks = plan_chunks_over_regions(
                regions,
                args.checkpoint_chunks,
                args.checkpoint_min_seconds,
                pauses=pauses,
            )
            if pauses and chunks != plan_chunks_over_regions(
                regions, args.checkpoint_chunks, args.checkpoint_min_seconds
            ):
                print(
                    f"Boundary snap: cut points moved onto detected pauses "
                    f"({len(pauses)} pauses found).",
                    file=sys.stderr,
                )

        if len(chunks) > 1 or trimmed:
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
