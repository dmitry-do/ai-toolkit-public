"""Tests for transcribe_audio.py chunking/incremental-write logic.

Run: python3 -m unittest test_transcribe_audio -v
"""
import contextlib
import importlib.util
import io
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).with_name("transcribe_audio.py")
spec = importlib.util.spec_from_file_location("transcribe_audio", MODULE_PATH)
ta = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ta)


class PlanChunksTests(unittest.TestCase):
    def test_short_audio_below_floor_is_single_chunk(self):
        self.assertEqual(
            ta.plan_chunks(60.0, target_chunks=10, floor_seconds=120.0),
            [(0.0, 60.0)],
        )

    def test_long_audio_splits_into_target_chunks(self):
        chunks = ta.plan_chunks(4440.0, target_chunks=10, floor_seconds=120.0)
        self.assertEqual(len(chunks), 10)
        self.assertEqual(chunks[0][0], 0.0)
        self.assertAlmostEqual(chunks[-1][1], 4440.0)
        # contiguous, no gaps/overlaps
        for (_, end), (nxt_start, _) in zip(chunks, chunks[1:]):
            self.assertAlmostEqual(end, nxt_start)
        # every chunk respects the floor
        for start, end in chunks:
            self.assertGreaterEqual(end - start, 120.0 - 1e-9)

    def test_floor_limits_chunk_count(self):
        chunks = ta.plan_chunks(300.0, target_chunks=10, floor_seconds=120.0)
        self.assertEqual(chunks, [(0.0, 150.0), (150.0, 300.0)])

    def test_target_one_yields_single_chunk(self):
        self.assertEqual(
            ta.plan_chunks(4440.0, target_chunks=1, floor_seconds=120.0),
            [(0.0, 4440.0)],
        )


class OffsetSegmentsTests(unittest.TestCase):
    def test_shifts_start_and_end_by_offset(self):
        segs = [
            {"start": 0.0, "end": 2.0, "text": "a"},
            {"start": 2.0, "end": 5.0, "text": "b"},
        ]
        out = ta.offset_segments(segs, 100.0)
        self.assertEqual(
            [(s["start"], s["end"]) for s in out],
            [(100.0, 102.0), (102.0, 105.0)],
        )
        self.assertEqual([s["text"] for s in out], ["a", "b"])
        # original list untouched
        self.assertEqual(segs[0]["start"], 0.0)


class TranscribeChunkedTests(unittest.TestCase):
    def test_offsets_accumulates_and_writes_per_chunk(self):
        audio = list(range(48000))  # stand-in; the fake transcriber ignores content
        chunks = [(0.0, 10.0), (10.0, 20.0), (20.0, 30.0)]
        calls = []

        def fake_transcribe(slice_audio, initial_prompt, language):
            idx = len(calls)
            calls.append({"prompt": initial_prompt, "language": language})
            return {
                "segments": [{"start": 0.0, "end": 5.0, "text": f"chunk{idx}"}],
                "text": f"chunk{idx}",
                "language": "en",
            }

        write_segment_counts = []

        def on_progress(accumulated):
            write_segment_counts.append(len(accumulated["segments"]))

        result = ta.transcribe_chunked(
            audio, chunks, fake_transcribe, on_progress, base_prompt="ctx"
        )

        # one incremental write per chunk
        self.assertEqual(write_segment_counts, [1, 2, 3])
        # timestamps offset by each chunk's start
        self.assertEqual(
            [(s["start"], s["end"]) for s in result["segments"]],
            [(0.0, 5.0), (10.0, 15.0), (20.0, 25.0)],
        )
        # language detected on first chunk, reused after
        self.assertIsNone(calls[0]["language"])
        self.assertEqual(calls[1]["language"], "en")
        self.assertEqual(result["language"], "en")
        # base prompt present in first chunk; prior text carried into later chunk
        self.assertIn("ctx", calls[0]["prompt"])
        self.assertIn("chunk0", calls[1]["prompt"])
        # accumulated text merged in order
        self.assertEqual(result["text"], "chunk0 chunk1 chunk2")


class WriteMarkdownTests(unittest.TestCase):
    """Characterization test guarding the atomic-write refactor."""

    def test_writes_title_source_and_segment_no_temp_left(self):
        args = types.SimpleNamespace(title="T", speaker=None, note=None, language=None)
        result = {
            "language": "en",
            "segments": [{"start": 0.0, "end": 1.0, "text": "hi"}],
            "text": "hi",
        }
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "o.md"
            ta.write_markdown(out, Path("a.mp3"), "mlx", "model", None, args, result)
            content = out.read_text()
            self.assertIn("# T", content)
            self.assertIn("[00:00-00:01] hi", content)
            self.assertEqual(list(Path(d).glob("*.tmp")), [])


class ResumeProgressTests(unittest.TestCase):
    """Sidecar progress file: write after each chunk, validate before resuming."""

    def _sig(self, chunks, size=123, model="m", audio="/tmp/a.mp3", language="en"):
        return {
            "audio": audio,
            "audio_size": size,
            "model": model,
            "language": language,
            "chunks": [[round(s, 3), round(e, 3)] for s, e in chunks],
        }

    def _acc(self, done, text_parts, segments=None):
        return {
            "segments": segments or [],
            "text": " ".join(text_parts),
            "language": "en",
            "text_parts": list(text_parts),
            "done": done,
        }

    def test_write_then_load_round_trips_state(self):
        chunks = [(0.0, 10.0), (10.0, 20.0), (20.0, 30.0)]
        sig = self._sig(chunks)
        acc = self._acc(1, ["a"], [{"start": 0.0, "end": 5.0, "text": "a"}])
        with tempfile.TemporaryDirectory() as d:
            pf = Path(d) / "o.md.progress.json"
            ta.write_progress(pf, sig, acc)
            state = ta.load_progress(pf, sig)
        self.assertEqual(state["done"], 1)
        self.assertEqual(state["text_parts"], ["a"])
        self.assertEqual(state["language"], "en")
        self.assertEqual(len(state["segments"]), 1)

    def test_load_returns_none_when_chunk_plan_differs(self):
        chunks = [(0.0, 10.0), (10.0, 20.0), (20.0, 30.0)]
        sig = self._sig(chunks)
        with tempfile.TemporaryDirectory() as d:
            pf = Path(d) / "o.md.progress.json"
            ta.write_progress(pf, sig, self._acc(1, ["a"]))
            # re-cut audio (different boundaries) must invalidate resume
            self.assertIsNone(ta.load_progress(pf, self._sig([(0.0, 15.0), (15.0, 30.0)])))

    def test_load_returns_none_when_audio_changed(self):
        chunks = [(0.0, 10.0), (10.0, 20.0)]
        sig = self._sig(chunks)
        with tempfile.TemporaryDirectory() as d:
            pf = Path(d) / "o.md.progress.json"
            ta.write_progress(pf, sig, self._acc(1, ["a"]))
            self.assertIsNone(ta.load_progress(pf, self._sig(chunks, size=999)))

    def test_load_returns_none_when_nothing_done_or_complete(self):
        chunks = [(0.0, 10.0), (10.0, 20.0)]
        sig = self._sig(chunks)
        with tempfile.TemporaryDirectory() as d:
            pf = Path(d) / "o.md.progress.json"
            ta.write_progress(pf, sig, self._acc(0, []))
            self.assertIsNone(ta.load_progress(pf, sig))  # nothing done yet
            ta.write_progress(pf, sig, self._acc(2, ["a", "b"]))
            self.assertIsNone(ta.load_progress(pf, sig))  # all chunks done

    def test_load_returns_none_when_missing(self):
        sig = self._sig([(0.0, 10.0), (10.0, 20.0)])
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(ta.load_progress(Path(d) / "nope.json", sig))


class TranscribeChunkedResumeTests(unittest.TestCase):
    def test_resume_skips_done_chunks_and_carries_context(self):
        audio = list(range(48000))
        chunks = [(0.0, 10.0), (10.0, 20.0), (20.0, 30.0)]
        calls = []

        def fake_transcribe(slice_audio, initial_prompt, language):
            idx = len(calls)
            calls.append({"prompt": initial_prompt, "language": language})
            return {
                "segments": [{"start": 0.0, "end": 5.0, "text": f"new{idx}"}],
                "text": f"new{idx}",
                "language": "en",
            }

        resume_state = {
            "done": 2,
            "segments": [
                {"start": 0.0, "end": 5.0, "text": "old0"},
                {"start": 10.0, "end": 15.0, "text": "old1"},
            ],
            "text_parts": ["old0", "old1"],
            "language": "en",
        }
        dones = []
        result = ta.transcribe_chunked(
            audio, chunks, fake_transcribe, lambda a: dones.append(a["done"]),
            base_prompt="ctx", resume_state=resume_state,
        )

        # only the final, unfinished chunk is transcribed
        self.assertEqual(len(calls), 1)
        # restored language is reused (not re-detected), prior text carried into prompt
        self.assertEqual(calls[0]["language"], "en")
        self.assertIn("old1", calls[0]["prompt"])
        # accumulated onto the restored segments, with the right offset for chunk index 2
        self.assertEqual([s["text"] for s in result["segments"]], ["old0", "old1", "new0"])
        self.assertEqual(result["segments"][-1]["start"], 20.0)
        self.assertEqual(result["text"], "old0 old1 new0")
        # checkpoint reports the absolute completed-chunk count
        self.assertEqual(dones, [3])


class AutoResumeTests(unittest.TestCase):
    """Resume is automatic: a matching sidecar is picked up without any flag."""

    def test_resume_flag_no_longer_exists(self):
        parser = ta.build_parser()
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                parser.parse_args(["a.mp3", "--resume"])

    def test_main_auto_resumes_from_matching_sidecar(self):
        with tempfile.TemporaryDirectory() as d:
            audio_path = Path(d) / "a.mp3"
            audio_path.write_bytes(b"x" * 100)
            out = Path(d) / "o.md"
            chunks = [(0.0, 2.0), (2.0, 4.0)]
            sig = ta.resume_signature(audio_path, ta.DEFAULT_MLX_MODEL, None, chunks)
            ta.write_progress(
                ta.progress_path(out),
                sig,
                {
                    "segments": [{"start": 0.0, "end": 1.0, "text": "old0"}],
                    "text": "old0",
                    "language": "en",
                    "text_parts": ["old0"],
                    "done": 1,
                },
            )

            calls = []

            def fake_transcribe(slice_audio, initial_prompt, language):
                calls.append(language)
                return {
                    "segments": [{"start": 0.0, "end": 1.0, "text": "new1"}],
                    "text": "new1",
                    "language": "en",
                }

            original = (
                ta.command_available, ta.choose_backend,
                ta.load_audio_array, ta.make_mlx_transcribe_fn, sys.argv,
            )
            ta.command_available = lambda name: True
            ta.choose_backend = lambda requested: "mlx"
            ta.load_audio_array = lambda backend, path: [0.0] * (4 * ta.SAMPLE_RATE)
            ta.make_mlx_transcribe_fn = lambda model, args: fake_transcribe
            sys.argv = [
                "transcribe_audio.py", str(audio_path), "--output", str(out),
                "--checkpoint-chunks", "2", "--checkpoint-min-seconds", "1",
                "--parallel-slots", "0",
            ]
            try:
                with contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(io.StringIO()):
                    ta.main()
            finally:
                (
                    ta.command_available, ta.choose_backend,
                    ta.load_audio_array, ta.make_mlx_transcribe_fn, sys.argv,
                ) = original

            # only the unfinished chunk was transcribed
            self.assertEqual(len(calls), 1)
            content = out.read_text()
            self.assertIn("old0", content)
            self.assertIn("new1", content)
            # sidecar removed after clean completion
            self.assertFalse(ta.progress_path(out).exists())


if __name__ == "__main__":
    unittest.main()
