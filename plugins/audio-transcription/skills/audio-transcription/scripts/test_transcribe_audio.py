"""Tests for transcribe_audio.py chunking/incremental-write logic.

Run: python3 -m unittest test_transcribe_audio -v
"""
import importlib.util
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


if __name__ == "__main__":
    unittest.main()
