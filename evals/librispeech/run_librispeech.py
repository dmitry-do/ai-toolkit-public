#!/usr/bin/env python3
"""LibriSpeech accuracy eval for the audio-transcription plugin.

Builds long-form fixtures by concatenating a chapter's flac utterances
(single utterances are too short to exercise chunking/VAD/second-pass), runs
the plugin script on each, scores WER/CER with the shared score.py, and
appends a micro-averaged summary row to results.md.

  # 3 chapters from test-clean, plugin defaults (everything after -- is forwarded)
  python3 run_librispeech.py --label turbo-defaults --source clean -- --language en

  # the harder test-other set
  python3 run_librispeech.py --label turbo-defaults --source other -- --language en

  # Hugging Face smoke set (one concatenated fixture from the dummy split)
  python3 run_librispeech.py --label smoke --source hf-dummy -- --language en

Fixtures are cached in work/ (gitignored); delete the directory to rebuild.
"""
from __future__ import annotations

import argparse
import importlib.util
import subprocess
import sys
import time
import wave
from pathlib import Path

HERE = Path(__file__).resolve().parent
EVALS = HERE.parent
TRANSCRIBE_SCRIPT = (
    EVALS.parent
    / "plugins/audio-transcription/skills/audio-transcription/scripts/transcribe_audio.py"
)
SOURCE_ROOTS = {
    "clean": EVALS / "LibriSpeech_clean/test-clean",
    "other": EVALS / "LibriSpeech_other/test-other",
}
HF_DUMMY = "hf-internal-testing/librispeech_asr_dummy"
SAMPLE_RATE = 16000

_spec = importlib.util.spec_from_file_location("score", EVALS / "score.py")
score = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(score)


def pick_evenly(items, k):
    """k items evenly spaced across the list (always including the ends) —
    deterministic speaker diversity, no RNG."""
    if k >= len(items):
        return list(items)
    if k == 1:
        return [items[0]]
    indices = sorted({round(i * (len(items) - 1) / (k - 1)) for i in range(k)})
    return [items[i] for i in indices]


def parse_trans(trans_path):
    """LibriSpeech `<spk>-<chap>.trans.txt` -> {utterance_id: text}."""
    parsed = {}
    for line in Path(trans_path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        utt_id, _, text = line.partition(" ")
        parsed[utt_id] = text
    return parsed


def discover_chapters(root):
    """All `<speaker>/<chapter>` dirs holding a trans file, sorted by id."""
    chapters = []
    for trans in sorted(root.glob("*/*/*.trans.txt")):
        chapters.append(trans.parent)
    return chapters


def build_chapter_fixture(chapter_dir, work_dir, cap_seconds=480.0):
    """Concat a chapter's utterances (up to ``cap_seconds``) into one 16k mono
    wav + matching reference text. Cached: existing outputs are reused."""
    trans = next(chapter_dir.glob("*.trans.txt"))
    texts = parse_trans(trans)
    name = trans.name.replace(".trans.txt", "")
    wav_path = work_dir / f"{name}.wav"
    ref_path = work_dir / f"{name}.ref.txt"
    if wav_path.exists() and ref_path.exists():
        return wav_path, ref_path

    flacs, ref_parts, total = [], [], 0.0
    for utt_id in sorted(texts):
        flac = chapter_dir / f"{utt_id}.flac"
        if not flac.exists():
            continue
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(flac)],
            capture_output=True, text=True, check=True,
        )
        duration = float(probe.stdout.strip())
        if flacs and total + duration > cap_seconds:
            break
        flacs.append(flac)
        ref_parts.append(texts[utt_id])
        total += duration

    work_dir.mkdir(parents=True, exist_ok=True)
    concat_list = work_dir / f"{name}.concat.txt"
    concat_list.write_text(
        "".join(f"file '{flac}'\n" for flac in flacs), encoding="utf-8"
    )
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0",
         "-i", str(concat_list), "-ar", str(SAMPLE_RATE), "-ac", "1", str(wav_path)],
        check=True,
    )
    concat_list.unlink()
    ref_path.write_text(" ".join(ref_parts) + "\n", encoding="utf-8")
    return wav_path, ref_path


def build_hf_dummy_fixture(work_dir):
    """One concatenated wav + reference from the HF librispeech_asr_dummy split."""
    wav_path = work_dir / "hf-dummy.wav"
    ref_path = work_dir / "hf-dummy.ref.txt"
    if wav_path.exists() and ref_path.exists():
        return wav_path, ref_path

    from datasets import load_dataset  # one-line loader, as advertised
    import numpy as np

    dataset = load_dataset(HF_DUMMY, "clean", split="validation")
    arrays, ref_parts = [], []
    for row in dataset:
        audio = row["audio"]
        if int(audio["sampling_rate"]) != SAMPLE_RATE:
            raise SystemExit(f"unexpected sampling rate: {audio['sampling_rate']}")
        arrays.append(np.asarray(audio["array"], dtype=np.float32))
        ref_parts.append(row["text"])

    work_dir.mkdir(parents=True, exist_ok=True)
    pcm = (np.clip(np.concatenate(arrays), -1.0, 1.0) * 32767).astype("<i2")
    with wave.open(str(wav_path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(SAMPLE_RATE)
        wav.writeframes(pcm.tobytes())
    ref_path.write_text(" ".join(ref_parts) + "\n", encoding="utf-8")
    return wav_path, ref_path


def wav_seconds(wav_path):
    with wave.open(str(wav_path), "rb") as wav:
        return wav.getnframes() / wav.getframerate()


def append_row(results_path, line):
    path = Path(results_path)
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    last_table_row = max(
        (i for i, l in enumerate(lines) if l.lstrip().startswith("|")), default=None
    )
    if last_table_row is None:
        lines.append(line)
    else:
        lines.insert(last_table_row + 1, line)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args(argv):
    parser = argparse.ArgumentParser(description="Run + score the plugin on LibriSpeech fixtures.")
    parser.add_argument("--label", required=True, help="Short name for this config.")
    parser.add_argument("--source", required=True, choices=["clean", "other", "hf-dummy"])
    parser.add_argument("--chapters", type=int, default=3, help="Chapters to sample (clean/other).")
    parser.add_argument("--results", default=str(HERE / "results.md"))
    parser.add_argument("--script", default=str(TRANSCRIBE_SCRIPT))
    if "--" in argv:
        split = argv.index("--")
        own, passthrough = argv[:split], argv[split + 1:]
    else:
        own, passthrough = argv, []
    args = parser.parse_args(own)
    args.passthrough = passthrough
    return args


def main(argv):
    args = parse_args(argv)
    work_dir = HERE / "work"
    transcripts_dir = HERE / "transcripts" / args.label
    transcripts_dir.mkdir(parents=True, exist_ok=True)

    if args.source == "hf-dummy":
        fixtures = [build_hf_dummy_fixture(work_dir)]
    else:
        chapters = pick_evenly(discover_chapters(SOURCE_ROOTS[args.source]), args.chapters)
        fixtures = [build_chapter_fixture(c, work_dir) for c in chapters]

    totals = {"err": 0, "ref": 0, "cer_err": 0.0, "cer_ref": 0, "wall": 0.0, "audio": 0.0}
    for wav_path, ref_path in fixtures:
        out_md = transcripts_dir / (wav_path.stem + ".md")
        cmd = [sys.executable, args.script, str(wav_path), "--output", str(out_md), *args.passthrough]
        print(f"[run] {' '.join(cmd)}", file=sys.stderr)
        start = time.perf_counter()
        proc = subprocess.run(cmd, stderr=subprocess.STDOUT, stdout=subprocess.PIPE, text=True)
        wall = time.perf_counter() - start
        if proc.returncode != 0:
            sys.stderr.write(proc.stdout[-2000:])
            sys.exit(f"transcription failed (exit {proc.returncode})")

        reference = ref_path.read_text(encoding="utf-8")
        hypothesis = score.extract_transcript(out_md.read_text(encoding="utf-8"))
        w = score.wer(reference, hypothesis)
        ref_chars = len(score.normalize(reference).replace(" ", ""))
        totals["err"] += w["substitutions"] + w["insertions"] + w["deletions"]
        totals["ref"] += w["ref_words"]
        totals["cer_err"] += score.cer(reference, hypothesis) * ref_chars
        totals["cer_ref"] += ref_chars
        totals["wall"] += wall
        totals["audio"] += wav_seconds(wav_path)
        print(
            f"  [{wav_path.stem}] wall={wall:.0f}s WER={w['wer'] * 100:.1f}% "
            f"(ref={w['ref_words']}w hyp={w['hyp_words']}w "
            f"sub={w['substitutions']} ins={w['insertions']} del={w['deletions']})"
        )

    wer_pct = 100.0 * totals["err"] / totals["ref"] if totals["ref"] else 0.0
    cer_pct = 100.0 * totals["cer_err"] / totals["cer_ref"] if totals["cer_ref"] else 0.0
    flags = "`" + (" ".join(args.passthrough) or "(defaults)") + "`"
    append_row(
        args.results,
        f"| {args.label} | {args.source} | {len(fixtures)} | {totals['audio']:.0f} | "
        f"{totals['wall']:.0f} | {wer_pct:.2f} | {cer_pct:.2f} | {totals['ref']} | {flags} |",
    )
    print(
        f"[{args.label} | {args.source}] fixtures={len(fixtures)} audio={totals['audio']:.0f}s "
        f"wall={totals['wall']:.0f}s WER={wer_pct:.2f}% CER={cer_pct:.2f}%"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
