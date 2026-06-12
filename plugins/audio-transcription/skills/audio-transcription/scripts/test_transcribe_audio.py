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
        # every chunk gets exactly the user prompt — never the previous chunk's
        # text, which acts as cross-boundary conditioning and can make Whisper
        # silently drop the head of the next chunk (measured: 75 words lost)
        self.assertEqual(calls[0]["prompt"], "ctx")
        self.assertEqual(calls[1]["prompt"], "ctx")
        self.assertEqual(calls[2]["prompt"], "ctx")
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
        # restored language is reused (not re-detected); prompt is the user's only
        self.assertEqual(calls[0]["language"], "en")
        self.assertEqual(calls[0]["prompt"], "ctx")
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


class DetectSpeechRegionsTests(unittest.TestCase):
    """Energy-based VAD: find speech regions, skipping only long silences."""

    SR = 16000

    def _audio(self, *sections):
        """Build 16 kHz audio from (seconds, amplitude) sections; amp 0 = silence."""
        import numpy as np

        parts = []
        for seconds, amp in sections:
            n = int(seconds * self.SR)
            if amp:
                t = np.arange(n)
                parts.append((amp * np.sin(2 * np.pi * 440 * t / self.SR)).astype(np.float32))
            else:
                parts.append(np.zeros(n, dtype=np.float32))
        return np.concatenate(parts)

    def test_pure_silence_yields_no_regions(self):
        self.assertEqual(ta.detect_speech_regions(self._audio((10, 0.0)), self.SR), [])

    def test_continuous_speech_is_one_full_region(self):
        regions = ta.detect_speech_regions(self._audio((10, 0.1)), self.SR)
        self.assertEqual(len(regions), 1)
        self.assertEqual(regions[0][0], 0.0)
        self.assertAlmostEqual(regions[0][1], 10.0, delta=0.05)

    def test_long_silence_splits_regions_with_padding(self):
        audio = self._audio((5, 0.1), (10, 0.0), (5, 0.1))
        regions = ta.detect_speech_regions(audio, self.SR)
        self.assertEqual(len(regions), 2)
        # first region: starts at 0, ends shortly after 5s (padded, not clipped)
        self.assertEqual(regions[0][0], 0.0)
        self.assertGreaterEqual(regions[0][1], 5.0)
        self.assertLess(regions[0][1], 6.0)
        # second region: starts shortly before 15s, runs to the end
        self.assertGreater(regions[1][0], 14.0)
        self.assertLessEqual(regions[1][0], 15.0)
        self.assertAlmostEqual(regions[1][1], 20.0, delta=0.05)

    def test_short_pause_does_not_split(self):
        audio = self._audio((5, 0.1), (1, 0.0), (5, 0.1))
        regions = ta.detect_speech_regions(audio, self.SR)
        self.assertEqual(len(regions), 1)
        self.assertEqual(regions[0][0], 0.0)
        self.assertAlmostEqual(regions[0][1], 11.0, delta=0.05)


class DetectPausesTests(unittest.TestCase):
    """Fine-grained pause detection: the short gaps region-VAD merges over."""

    SR = 16000

    def _audio(self, *sections):
        import numpy as np

        parts = []
        for seconds, amp in sections:
            n = int(seconds * self.SR)
            if amp:
                t = np.arange(n)
                parts.append((amp * np.sin(2 * np.pi * 440 * t / self.SR)).astype(np.float32))
            else:
                parts.append(np.zeros(n, dtype=np.float32))
        return np.concatenate(parts)

    def test_continuous_speech_has_no_pauses(self):
        self.assertEqual(ta.detect_pauses(self._audio((10, 0.1)), self.SR), [])

    def test_short_pause_is_reported_even_though_region_vad_merges_it(self):
        # a 1s gap: too short to split a speech region (needs >=2s) but a valid
        # cut point — detect_pauses must surface it where detect_speech_regions won't
        audio = self._audio((5, 0.1), (1, 0.0), (5, 0.1))
        self.assertEqual(len(ta.detect_speech_regions(audio, self.SR)), 1)
        pauses = ta.detect_pauses(audio, self.SR)
        self.assertEqual(len(pauses), 1)
        self.assertAlmostEqual(pauses[0], 5.5, delta=0.1)  # centered in the gap

    def test_pause_below_threshold_is_ignored(self):
        # 0.2s gap < default 0.35s min_pause -> not a cut point
        audio = self._audio((5, 0.1), (0.2, 0.0), (5, 0.1))
        self.assertEqual(ta.detect_pauses(audio, self.SR), [])

    def test_pure_silence_yields_no_pauses(self):
        self.assertEqual(ta.detect_pauses(self._audio((5, 0.0)), self.SR), [])


class NearestPauseTests(unittest.TestCase):
    def test_picks_closest_within_window(self):
        self.assertEqual(ta._nearest_pause([1.0, 4.0, 9.0], 5.0, 2.0), 4.0)

    def test_returns_none_when_all_outside_window(self):
        self.assertIsNone(ta._nearest_pause([1.0, 9.0], 5.0, 2.0))

    def test_empty_pause_list(self):
        self.assertIsNone(ta._nearest_pause([], 5.0, 2.0))


class SnapBoundariesTests(unittest.TestCase):
    def test_interior_cut_moves_to_nearby_pause(self):
        chunks = [(0.0, 50.0), (50.0, 100.0)]
        # a pause at 47s, within 0.5*nominal(50)=25s of the 50s cut
        snapped = ta.snap_boundaries(chunks, [47.0])
        self.assertEqual(snapped, [(0.0, 47.0), (47.0, 100.0)])

    def test_outer_endpoints_never_move(self):
        chunks = [(10.0, 60.0), (60.0, 110.0)]
        # a pause near the region START must not pull the outer edge in
        snapped = ta.snap_boundaries(chunks, [11.0, 58.0])
        self.assertEqual(snapped[0][0], 10.0)
        self.assertEqual(snapped[-1][1], 110.0)
        self.assertEqual(snapped[0][1], 58.0)  # only the interior cut moved

    def test_no_pause_in_window_leaves_cut_in_place(self):
        chunks = [(0.0, 50.0), (50.0, 100.0)]
        # nearest pause is 30s away (> 0.5*50) -> unchanged
        self.assertEqual(ta.snap_boundaries(chunks, [20.0]), chunks)

    def test_single_chunk_or_no_pauses_is_noop(self):
        self.assertEqual(ta.snap_boundaries([(0.0, 50.0)], [25.0]), [(0.0, 50.0)])
        self.assertEqual(ta.snap_boundaries([(0.0, 50.0), (50.0, 100.0)], []),
                         [(0.0, 50.0), (50.0, 100.0)])

    def test_boundaries_stay_strictly_increasing_and_contiguous(self):
        chunks = [(0.0, 30.0), (30.0, 60.0), (60.0, 90.0)]
        # two pauses that could collide near each other
        snapped = ta.snap_boundaries(chunks, [29.0, 31.0, 58.0])
        starts_ends = [s for s, _ in snapped] + [snapped[-1][1]]
        self.assertTrue(all(a < b for a, b in zip(starts_ends, starts_ends[1:])))
        # contiguous: each chunk's end == next chunk's start
        for (_, end), (nxt, _) in zip(snapped, snapped[1:]):
            self.assertEqual(end, nxt)
        self.assertEqual(len(snapped), 3)  # chunk count preserved


class PlanChunksOverRegionsSnapTests(unittest.TestCase):
    def test_pauses_snap_interior_cuts(self):
        # one 600s region, target 3 -> ideal cuts at 200 and 400
        chunks = ta.plan_chunks_over_regions(
            [(0.0, 600.0)], target_chunks=3, floor_seconds=120.0,
            pauses=[195.0, 410.0],
        )
        self.assertEqual(chunks, [(0.0, 195.0), (195.0, 410.0), (410.0, 600.0)])

    def test_no_pauses_matches_unsnapped_plan(self):
        regions = [(0.0, 600.0)]
        self.assertEqual(
            ta.plan_chunks_over_regions(regions, 3, 120.0, pauses=None),
            ta.plan_chunks_over_regions(regions, 3, 120.0),
        )


class SnapBoundariesDefaultTests(unittest.TestCase):
    def test_snap_boundaries_is_on_by_default(self):
        self.assertTrue(ta.build_parser().parse_args(["a.mp3"]).snap_boundaries)

    def test_no_snap_boundaries_opts_out(self):
        args = ta.build_parser().parse_args(["a.mp3", "--no-snap-boundaries"])
        self.assertFalse(args.snap_boundaries)


class WorthSkippingTests(unittest.TestCase):
    """Silence skipping engages only when it saves real time."""

    def test_trivial_trim_on_long_audio_is_not_worth_it(self):
        self.assertFalse(ta.worth_skipping(821.6, 823.0))

    def test_minutes_of_silence_are_worth_it(self):
        self.assertTrue(ta.worth_skipping(174.0, 474.0))

    def test_large_fraction_of_short_audio_is_worth_it(self):
        self.assertTrue(ta.worth_skipping(6.6, 12.0))


class SkipSilenceDefaultTests(unittest.TestCase):
    def test_skip_silence_is_on_by_default(self):
        args = ta.build_parser().parse_args(["a.mp3"])
        self.assertTrue(args.skip_silence)

    def test_no_skip_silence_opts_out(self):
        args = ta.build_parser().parse_args(["a.mp3", "--no-skip-silence"])
        self.assertFalse(args.skip_silence)


class PlanChunksOverRegionsTests(unittest.TestCase):
    def test_single_full_region_matches_plan_chunks(self):
        self.assertEqual(
            ta.plan_chunks_over_regions([(0.0, 4440.0)], target_chunks=10, floor_seconds=120.0),
            ta.plan_chunks(4440.0, target_chunks=10, floor_seconds=120.0),
        )

    def test_gap_between_regions_is_never_transcribed(self):
        chunks = ta.plan_chunks_over_regions(
            [(0.0, 300.0), (500.0, 800.0)], target_chunks=4, floor_seconds=120.0
        )
        self.assertEqual(
            chunks, [(0.0, 150.0), (150.0, 300.0), (500.0, 650.0), (650.0, 800.0)]
        )

    def test_floor_keeps_short_regions_whole(self):
        chunks = ta.plan_chunks_over_regions(
            [(0.0, 100.0), (200.0, 260.0)], target_chunks=10, floor_seconds=120.0
        )
        self.assertEqual(chunks, [(0.0, 100.0), (200.0, 260.0)])


class SkipSilenceWiringTests(unittest.TestCase):
    def test_main_skips_silence_and_keeps_original_timestamps(self):
        import numpy as np

        sr = ta.SAMPLE_RATE
        t = np.arange(3 * sr)
        loud = (0.1 * np.sin(2 * np.pi * 440 * t / sr)).astype(np.float32)
        audio = np.concatenate([loud, np.zeros(6 * sr, dtype=np.float32), loud])

        with tempfile.TemporaryDirectory() as d:
            audio_path = Path(d) / "a.mp3"
            audio_path.write_bytes(b"x" * 100)
            out = Path(d) / "o.md"

            calls = []

            def fake_transcribe(slice_audio, initial_prompt, language):
                calls.append(len(slice_audio))
                return {
                    "segments": [{"start": 0.0, "end": 1.0, "text": f"part{len(calls)}"}],
                    "text": f"part{len(calls)}",
                    "language": "en",
                }

            original = (
                ta.command_available, ta.choose_backend,
                ta.load_audio_array, ta.make_mlx_transcribe_fn, sys.argv,
            )
            ta.command_available = lambda name: True
            ta.choose_backend = lambda requested: "mlx"
            ta.load_audio_array = lambda backend, path: audio
            ta.make_mlx_transcribe_fn = lambda model, args: fake_transcribe
            sys.argv = [
                "transcribe_audio.py", str(audio_path), "--output", str(out),
                "--skip-silence", "--checkpoint-chunks", "2",
                "--checkpoint-min-seconds", "1", "--parallel-slots", "0",
            ]
            try:
                with contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(io.StringIO()):
                    ta.main()
            finally:
                (
                    ta.command_available, ta.choose_backend,
                    ta.load_audio_array, ta.make_mlx_transcribe_fn, sys.argv,
                ) = original

            # one call per speech region; the 6s silent middle was never transcribed
            self.assertEqual(len(calls), 2)
            for n_samples in calls:
                self.assertLess(n_samples, 4 * sr)
            content = out.read_text()
            self.assertIn("part1", content)
            self.assertIn("part2", content)
            # second region's segment keeps the original-timeline offset (~9s)
            self.assertIn("[00:00-00:01] part1", content)
            self.assertIn("[00:09-00:10] part2", content)


if __name__ == "__main__":
    unittest.main()
