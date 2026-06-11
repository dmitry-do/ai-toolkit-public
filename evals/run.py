#!/usr/bin/env python3
"""Run one transcription config, time it, score it, append a row to results.md.

  python3 run.py --label chunked --audio warandpeace/audio/wap_v1_p1_ch1.mp3 \
      --ref warandpeace/reference/wap_v1_p1_ch1.txt -- --language en

Everything after `--` is passed straight to transcribe_audio.py, so any plugin flag
(--checkpoint-chunks, --mlx-model, --language, ...) can be swept. The transcript is
written to transcripts/<label>.md and scored against --ref with score.py.
"""
from __future__ import annotations

import argparse
import importlib.util
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_SCRIPT = (
    HERE.parent
    / "plugins/audio-transcription/skills/audio-transcription/scripts/transcribe_audio.py"
)

_spec = importlib.util.spec_from_file_location("score", HERE / "score.py")
score = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(score)


def parse_args(argv):
    parser = argparse.ArgumentParser(description="Run + score a transcription config.")
    parser.add_argument("--label", required=True, help="Short name for this run (also the output filename).")
    parser.add_argument("--audio", required=True, help="Audio fixture to transcribe.")
    parser.add_argument("--ref", required=True, help="Reference text to score against.")
    parser.add_argument("--results", default=str(HERE / "results.md"), help="Results table to append to.")
    parser.add_argument("--script", default=str(DEFAULT_SCRIPT), help="transcribe_audio.py path.")
    parser.add_argument("--outdir", default=None, help="Where to write the transcript (default: alongside --ref's chapter transcripts/).")
    # everything after "--" is forwarded to transcribe_audio.py
    if "--" in argv:
        split = argv.index("--")
        own, passthrough = argv[:split], argv[split + 1:]
    else:
        own, passthrough = argv, []
    args = parser.parse_args(own)
    args.passthrough = passthrough
    return args


def fixture_label(audio_path):
    return "clip" if "clip" in Path(audio_path).stem else "full"


def append_row(results_path, row):
    path = Path(results_path)
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    # insert the row right after the table (before a trailing "## Notes" if present)
    line = (
        f"| {row['label']} | {row['fixture']} | {row['wall_s']:.0f} | {row['wer']:.1f} | "
        f"{row['cer']:.1f} | {row['model']} | {row['flags']} | {row['notes']} |\n"
    )
    if "## Notes" in text:
        head, _, tail = text.partition("## Notes")
        path.write_text(head.rstrip() + "\n" + line + "\n## Notes" + tail, encoding="utf-8")
    else:
        path.write_text(text.rstrip() + "\n" + line, encoding="utf-8")


def main(argv):
    args = parse_args(argv)
    outdir = Path(args.outdir) if args.outdir else (Path(args.ref).resolve().parent.parent / "transcripts")
    outdir.mkdir(parents=True, exist_ok=True)
    out_md = outdir / f"{args.label}.md"

    cmd = [sys.executable, args.script, args.audio, "--output", str(out_md), *args.passthrough]
    print(f"[run] {' '.join(cmd)}", file=sys.stderr)
    start = time.perf_counter()
    proc = subprocess.run(cmd, stderr=subprocess.STDOUT, stdout=subprocess.PIPE, text=True)
    wall = time.perf_counter() - start
    if proc.returncode != 0:
        sys.stderr.write(proc.stdout[-2000:])
        sys.exit(f"transcription failed (exit {proc.returncode})")

    reference = Path(args.ref).read_text(encoding="utf-8")
    hypothesis = score.extract_transcript(out_md.read_text(encoding="utf-8"))
    w = score.wer(reference, hypothesis)
    c = score.cer(reference, hypothesis)

    # crude model guess from passthrough; flags = the passthrough string
    model = "whisper-large-v3-mlx"
    if "--mlx-model" in args.passthrough:
        model = args.passthrough[args.passthrough.index("--mlx-model") + 1]
    elif "--whisper-model" in args.passthrough:
        model = "whisper:" + args.passthrough[args.passthrough.index("--whisper-model") + 1]

    row = {
        "label": args.label,
        "fixture": fixture_label(args.audio),
        "wall_s": wall,
        "wer": w["wer"] * 100,
        "cer": c * 100,
        "model": model,
        "flags": "`" + (" ".join(args.passthrough) or "(defaults)") + "`",
        "notes": "",
    }
    append_row(args.results, row)
    print(
        f"[{args.label}] wall={wall:.0f}s WER={row['wer']:.1f}% CER={row['cer']:.1f}% "
        f"(ref={w['ref_words']}w hyp={w['hyp_words']}w) -> {out_md}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
