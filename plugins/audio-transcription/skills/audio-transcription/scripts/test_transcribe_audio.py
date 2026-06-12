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
                # the fake covers only 1s of each 3s region, which would rightly
                # trigger gap recovery — disable it to test silence-skip alone
                "--no-second-pass",
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

def _tone_audio(*sections, sr=16000):
    """Build 16 kHz audio from (seconds, amplitude) sections; amp 0 = silence."""
    import numpy as np

    parts = []
    for seconds, amp in sections:
        n = int(seconds * sr)
        if amp:
            t = np.arange(n)
            parts.append((amp * np.sin(2 * np.pi * 440 * t / sr)).astype(np.float32))
        else:
            parts.append(np.zeros(n, dtype=np.float32))
    return np.concatenate(parts)


class FindCoverageGapsTests(unittest.TestCase):
    """Uncovered spans inside speech regions = candidate Whisper deletions."""

    def test_gap_between_segments_inside_region(self):
        segments = [
            {"start": 0.0, "end": 4.0, "text": "a"},
            {"start": 7.0, "end": 10.0, "text": "b"},
        ]
        gaps = ta.find_coverage_gaps(segments, [(0.0, 10.0)])
        self.assertEqual(gaps, [(4.0, 7.0)])

    def test_gap_shorter_than_minimum_is_ignored(self):
        segments = [
            {"start": 0.0, "end": 4.6, "text": "a"},
            {"start": 5.0, "end": 10.0, "text": "b"},
        ]
        self.assertEqual(ta.find_coverage_gaps(segments, [(0.0, 10.0)]), [])

    def test_silence_between_regions_is_not_a_gap(self):
        segments = [
            {"start": 0.0, "end": 10.0, "text": "a"},
            {"start": 50.0, "end": 60.0, "text": "b"},
        ]
        # regions already exclude 10-50s: intentional silence, not a deletion
        gaps = ta.find_coverage_gaps(segments, [(0.0, 10.0), (50.0, 60.0)])
        self.assertEqual(gaps, [])

    def test_uncovered_region_head_and_tail_are_gaps(self):
        segments = [{"start": 12.0, "end": 18.0, "text": "a"}]
        gaps = ta.find_coverage_gaps(segments, [(10.0, 20.0)])
        self.assertEqual(gaps, [(10.0, 12.0), (18.0, 20.0)])

    def test_no_segments_means_whole_region_is_a_gap(self):
        self.assertEqual(ta.find_coverage_gaps([], [(0.0, 8.0)]), [(0.0, 8.0)])

    def test_overlapping_segments_are_merged_before_gap_search(self):
        segments = [
            {"start": 0.0, "end": 5.0, "text": "a"},
            {"start": 4.0, "end": 6.0, "text": "b"},
            {"start": 8.0, "end": 10.0, "text": "c"},
        ]
        self.assertEqual(ta.find_coverage_gaps(segments, [(0.0, 10.0)]), [(6.0, 8.0)])


class VoicedSecondsTests(unittest.TestCase):
    """Voiced time inside a window, from the global frame mask."""

    def test_counts_only_voiced_frames_in_window(self):
        audio = _tone_audio((2, 0.1), (2, 0.0), (2, 0.1))
        mask, frame_s, _ = ta._speech_frame_mask(audio, 16000)
        # window covering the silent middle: ~0 voiced
        self.assertLess(ta.voiced_seconds(mask, frame_s, 2.2, 3.8), 0.2)
        # window covering the first tone: ~1s voiced
        self.assertGreater(ta.voiced_seconds(mask, frame_s, 0.5, 1.5), 0.8)


class SegmentSuspectTests(unittest.TestCase):
    def test_low_avg_logprob_is_suspect(self):
        seg = {"start": 0.0, "end": 3.0, "text": "hello there friend",
               "avg_logprob": -1.5, "compression_ratio": 1.2}
        self.assertTrue(ta.segment_suspect(seg))

    def test_high_compression_ratio_is_suspect(self):
        seg = {"start": 0.0, "end": 3.0, "text": "la la la la la la la",
               "avg_logprob": -0.2, "compression_ratio": 3.1}
        self.assertTrue(ta.segment_suspect(seg))

    def test_sparse_text_over_long_span_is_suspect(self):
        # 10 chars over 8s = 1.25 chars/s — way below plausible speech density
        seg = {"start": 0.0, "end": 8.0, "text": "uh huh ok",
               "avg_logprob": -0.3, "compression_ratio": 1.1}
        self.assertTrue(ta.segment_suspect(seg))

    def test_normal_segment_is_not_suspect(self):
        seg = {"start": 0.0, "end": 4.0,
               "text": "the quick brown fox jumps over the lazy dog today",
               "avg_logprob": -0.25, "compression_ratio": 1.4}
        self.assertFalse(ta.segment_suspect(seg))

    def test_missing_quality_fields_are_not_suspect(self):
        # fakes/tests may omit whisper's quality keys; absence is not evidence
        seg = {"start": 0.0, "end": 2.0, "text": "short normal sentence here"}
        self.assertFalse(ta.segment_suspect(seg))


class QualityGateTests(unittest.TestCase):
    def test_empty_text_is_rejected(self):
        self.assertFalse(ta.passes_quality_gates({"start": 0, "end": 1, "text": "  "}))

    def test_whisper_silence_rule_is_rejected(self):
        seg = {"start": 0, "end": 1, "text": "thanks for watching",
               "no_speech_prob": 0.9, "avg_logprob": -1.4}
        self.assertFalse(ta.passes_quality_gates(seg))

    def test_high_compression_is_rejected(self):
        seg = {"start": 0, "end": 1, "text": "la la la la la",
               "compression_ratio": 3.0, "avg_logprob": -0.2}
        self.assertFalse(ta.passes_quality_gates(seg))

    def test_normal_segment_passes(self):
        seg = {"start": 0, "end": 1, "text": "hello world",
               "no_speech_prob": 0.05, "avg_logprob": -0.2, "compression_ratio": 1.3}
        self.assertTrue(ta.passes_quality_gates(seg))

    def test_missing_quality_fields_pass(self):
        self.assertTrue(ta.passes_quality_gates({"start": 0, "end": 1, "text": "hi"}))


class SecondPassTests(unittest.TestCase):
    """Gap recovery + suspect retry over a finished result."""

    SR = 16000

    def test_recovers_voiced_uncovered_gap(self):
        # 10s of continuous tone; main result only covers 0-4s -> 4-10s is a
        # voiced hole that must be re-transcribed and spliced in on the timeline
        audio = _tone_audio((10, 0.1))
        result = {
            "segments": [{"start": 0.0, "end": 4.0, "text": "covered"}],
            "text": "covered", "language": "en",
        }
        calls = []

        def fake_transcribe(slice_audio, prompt, language):
            calls.append((len(slice_audio), prompt, language))
            return {"segments": [{"start": 0.5, "end": 5.0, "text": "recovered"}],
                    "text": "recovered", "language": "en"}

        out, stats = ta.second_pass(result, audio, [(0.0, 10.0)], fake_transcribe, "ctx")

        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][1], "ctx")
        self.assertEqual(calls[0][2], "en")
        self.assertEqual(stats["gaps_recovered"], 1)
        texts = [s["text"] for s in out["segments"]]
        self.assertEqual(texts, ["covered", "recovered"])
        # recovered segment is offset to the original timeline (window starts ~3.8s)
        self.assertGreater(out["segments"][1]["start"], 4.0)
        self.assertEqual(out["text"], "covered recovered")

    def test_silent_gap_is_not_retranscribed(self):
        # the uncovered 4-10s span is pure silence -> no re-transcription call
        audio = _tone_audio((4, 0.1), (6, 0.0))
        result = {
            "segments": [{"start": 0.0, "end": 4.0, "text": "covered"}],
            "text": "covered", "language": "en",
        }
        calls = []

        def fake_transcribe(slice_audio, prompt, language):
            calls.append(1)
            return {"segments": [], "text": ""}

        out, stats = ta.second_pass(result, audio, [(0.0, 10.0)], fake_transcribe, None)
        self.assertEqual(calls, [])
        self.assertEqual(stats["gaps_recovered"], 0)
        self.assertEqual([s["text"] for s in out["segments"]], ["covered"])

    def test_recovered_segments_failing_gates_are_dropped(self):
        audio = _tone_audio((10, 0.1))
        result = {
            "segments": [{"start": 0.0, "end": 4.0, "text": "covered"}],
            "text": "covered", "language": "en",
        }

        def fake_transcribe(slice_audio, prompt, language):
            return {"segments": [{"start": 0.0, "end": 5.0, "text": "ghost",
                                  "no_speech_prob": 0.95, "avg_logprob": -1.8}],
                    "text": "ghost"}

        out, stats = ta.second_pass(result, audio, [(0.0, 10.0)], fake_transcribe, None)
        self.assertEqual([s["text"] for s in out["segments"]], ["covered"])
        self.assertEqual(stats["gaps_recovered"], 0)

    def test_suspect_segment_replaced_when_retry_scores_better(self):
        audio = _tone_audio((6, 0.1))
        bad = {"start": 0.0, "end": 6.0, "text": "garbled garbage words here",
               "avg_logprob": -1.6, "compression_ratio": 1.2}
        result = {"segments": [bad], "text": bad["text"], "language": "en"}

        def fake_transcribe(slice_audio, prompt, language):
            return {"segments": [{"start": 0.1, "end": 5.9, "text": "clean retry text",
                                  "avg_logprob": -0.3, "compression_ratio": 1.3}],
                    "text": "clean retry text"}

        out, stats = ta.second_pass(result, audio, [(0.0, 6.0)], fake_transcribe, None)
        self.assertEqual(stats["suspects"], 1)
        self.assertEqual(stats["replaced"], 1)
        self.assertEqual([s["text"] for s in out["segments"]], ["clean retry text"])
        self.assertEqual(out["text"], "clean retry text")

    def test_suspect_segment_kept_when_retry_is_worse(self):
        audio = _tone_audio((6, 0.1))
        bad = {"start": 0.0, "end": 6.0, "text": "original suspect text okay",
               "avg_logprob": -1.2, "compression_ratio": 1.2}
        result = {"segments": [bad], "text": bad["text"], "language": "en"}

        def fake_transcribe(slice_audio, prompt, language):
            return {"segments": [{"start": 0.0, "end": 6.0, "text": "worse retry",
                                  "avg_logprob": -2.5, "compression_ratio": 1.3}],
                    "text": "worse retry"}

        out, stats = ta.second_pass(result, audio, [(0.0, 6.0)], fake_transcribe, None)
        self.assertEqual(stats["suspects"], 1)
        self.assertEqual(stats["replaced"], 0)
        self.assertEqual([s["text"] for s in out["segments"]],
                         ["original suspect text okay"])

    def test_clean_result_is_untouched_and_makes_no_calls(self):
        audio = _tone_audio((6, 0.1))
        good = {"start": 0.0, "end": 6.0,
                "text": "a perfectly normal sentence spanning the whole region",
                "avg_logprob": -0.2, "compression_ratio": 1.4}
        result = {"segments": [good], "text": good["text"], "language": "en"}

        def fake_transcribe(slice_audio, prompt, language):
            raise AssertionError("clean result must not trigger re-transcription")

        out, stats = ta.second_pass(result, audio, [(0.0, 6.0)], fake_transcribe, None)
        self.assertEqual(out["segments"], [good])
        self.assertEqual(stats, {"gaps_found": 0, "gaps_recovered": 0,
                                 "suspects": 0, "replaced": 0})


class SecondPassFlagTests(unittest.TestCase):
    def test_second_pass_is_on_by_default(self):
        self.assertTrue(ta.build_parser().parse_args(["a.mp3"]).second_pass)

    def test_no_second_pass_opts_out(self):
        args = ta.build_parser().parse_args(["a.mp3", "--no-second-pass"])
        self.assertFalse(args.second_pass)


class SecondPassWiringTests(unittest.TestCase):
    def test_main_recovers_dropped_speech_in_voiced_gap(self):
        import numpy as np

        sr = ta.SAMPLE_RATE
        # 12s of continuous tone: one region, chunked in two
        audio = _tone_audio((12, 0.1), sr=sr)

        with tempfile.TemporaryDirectory() as d:
            audio_path = Path(d) / "a.mp3"
            audio_path.write_bytes(b"x" * 100)
            out = Path(d) / "o.md"

            calls = []

            def fake_transcribe(slice_audio, initial_prompt, language):
                calls.append(len(slice_audio) / sr)
                # text long enough to not trip the sparse-density suspect check
                if len(calls) == 1:
                    return {"segments": [{"start": 0.0, "end": 6.0,
                                          "text": "first chunk full of normal spoken words"}],
                            "text": "first chunk full of normal spoken words",
                            "language": "en"}
                if len(calls) == 2:
                    # whisper "drops" the second chunk's tail: covers only 6-8s
                    return {"segments": [{"start": 0.0, "end": 2.0, "text": "second"}],
                            "text": "second", "language": "en"}
                return {"segments": [{"start": 0.0, "end": 4.0, "text": "rescued"}],
                        "text": "rescued", "language": "en"}

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
                "--checkpoint-chunks", "2", "--checkpoint-min-seconds", "1",
                "--no-snap-boundaries", "--parallel-slots", "0",
            ]
            try:
                with contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(io.StringIO()):
                    ta.main()
            finally:
                (
                    ta.command_available, ta.choose_backend,
                    ta.load_audio_array, ta.make_mlx_transcribe_fn, sys.argv,
                ) = original

            # 2 chunk calls + 1 gap-recovery call for the voiced 8-12s hole
            self.assertEqual(len(calls), 3)
            self.assertLess(calls[2], 5.0)  # only the hole, not the whole file
            content = out.read_text()
            self.assertIn("first", content)
            self.assertIn("second", content)
            self.assertIn("rescued", content)


class _FakeFasterSegment:
    def __init__(self, start, end, text, avg_logprob=-0.3, compression_ratio=1.3,
                 no_speech_prob=0.05):
        self.start, self.end, self.text = start, end, text
        self.avg_logprob = avg_logprob
        self.compression_ratio = compression_ratio
        self.no_speech_prob = no_speech_prob


class FasterBackendTests(unittest.TestCase):
    """faster-whisper (CTranslate2): explicit opt-in backend with beam search."""

    def _stub_module(self, captured):
        class FakeModel:
            def __init__(self, model_name, **kwargs):
                captured["model_name"] = model_name
                captured["model_kwargs"] = kwargs

            def transcribe(self, audio, **kwargs):
                captured["transcribe_kwargs"] = kwargs
                segments = iter([
                    _FakeFasterSegment(0.0, 2.0, " hello"),
                    _FakeFasterSegment(2.0, 4.0, " world"),
                ])
                info = types.SimpleNamespace(language="en")
                return segments, info

        return types.SimpleNamespace(WhisperModel=FakeModel)

    def test_transcribe_fn_converts_to_standard_result_dict(self):
        captured = {}
        sys.modules["faster_whisper"] = self._stub_module(captured)
        try:
            args = types.SimpleNamespace(beam_size=5, condition_previous=False, language=None)
            fn = ta.make_faster_transcribe_fn("large-v3", args)
            result = fn([0.0] * 16000, "ctx", None)
        finally:
            del sys.modules["faster_whisper"]

        self.assertEqual(captured["model_name"], "large-v3")
        self.assertEqual(captured["transcribe_kwargs"]["beam_size"], 5)
        self.assertEqual(captured["transcribe_kwargs"]["initial_prompt"], "ctx")
        self.assertEqual(result["language"], "en")
        self.assertEqual(result["text"], "hello world")
        seg = result["segments"][0]
        self.assertEqual((seg["start"], seg["end"]), (0.0, 2.0))
        # quality fields survive conversion so second-pass gates keep working
        self.assertEqual(seg["avg_logprob"], -0.3)
        self.assertEqual(seg["compression_ratio"], 1.3)
        self.assertEqual(seg["no_speech_prob"], 0.05)

    def test_explicit_faster_is_allowed_even_on_apple_silicon(self):
        original = (ta.module_available, ta.is_apple_silicon)
        ta.module_available = lambda name: True
        ta.is_apple_silicon = lambda: True
        try:
            self.assertEqual(ta.choose_backend("faster"), "faster")
        finally:
            ta.module_available, ta.is_apple_silicon = original

    def test_missing_faster_whisper_fails_with_install_hint(self):
        original = ta.module_available
        ta.module_available = lambda name: name != "faster_whisper"
        try:
            with contextlib.redirect_stderr(io.StringIO()) as err:
                with self.assertRaises(SystemExit) as ctx:
                    ta.choose_backend("faster")
            self.assertEqual(ctx.exception.code, 4)
            self.assertIn("faster-whisper", err.getvalue())
        finally:
            ta.module_available = original

    def test_parser_accepts_faster_backend_and_model(self):
        args = ta.build_parser().parse_args(["a.mp3", "--backend", "faster"])
        self.assertEqual(args.backend, "faster")
        self.assertEqual(args.faster_model, "large-v3")

    def test_load_audio_array_uses_decode_audio(self):
        captured = {}

        def decode_audio(path, sampling_rate):
            captured["path"], captured["rate"] = path, sampling_rate
            return [0.0] * sampling_rate

        sys.modules["faster_whisper"] = types.SimpleNamespace(decode_audio=decode_audio)
        try:
            out = ta.load_audio_array("faster", Path("/tmp/x.mp3"))
        finally:
            del sys.modules["faster_whisper"]
        self.assertEqual(len(out), 16000)
        self.assertEqual(captured["rate"], ta.SAMPLE_RATE)

    def test_main_runs_faster_backend_without_touching_torch(self):
        audio = _tone_audio((4, 0.1))

        with tempfile.TemporaryDirectory() as d:
            audio_path = Path(d) / "a.mp3"
            audio_path.write_bytes(b"x" * 100)
            out = Path(d) / "o.md"

            def fake_transcribe(slice_audio, initial_prompt, language):
                return {"segments": [{"start": 0.0, "end": 4.0,
                                      "text": "spoken words from the faster backend"}],
                        "text": "spoken words from the faster backend",
                        "language": "en"}

            def explode(requested):
                raise AssertionError("faster backend must not consult torch devices")

            original = (
                ta.command_available, ta.choose_backend, ta.choose_device,
                ta.load_audio_array, ta.make_faster_transcribe_fn, sys.argv,
            )
            ta.command_available = lambda name: True
            ta.choose_backend = lambda requested: "faster"
            ta.choose_device = explode
            ta.load_audio_array = lambda backend, path: audio
            ta.make_faster_transcribe_fn = lambda model, args: fake_transcribe
            sys.argv = [
                "transcribe_audio.py", str(audio_path), "--output", str(out),
                "--backend", "faster", "--parallel-slots", "0",
            ]
            try:
                with contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(io.StringIO()):
                    ta.main()
            finally:
                (
                    ta.command_available, ta.choose_backend, ta.choose_device,
                    ta.load_audio_array, ta.make_faster_transcribe_fn, sys.argv,
                ) = original

            self.assertIn("spoken words from the faster backend", out.read_text())
