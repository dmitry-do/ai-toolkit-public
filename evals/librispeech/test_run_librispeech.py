"""Tests for the LibriSpeech eval harness's pure helpers.

Run: python3 -m unittest test_run_librispeech -v
"""
import importlib.util
import tempfile
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).with_name("run_librispeech.py")
spec = importlib.util.spec_from_file_location("run_librispeech", MODULE_PATH)
rl = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rl)


class PickEvenlyTests(unittest.TestCase):
    """Deterministic, evenly spaced selection — speaker diversity without RNG."""

    def test_selects_first_last_and_evenly_spaced(self):
        self.assertEqual(rl.pick_evenly(list(range(10)), 3), [0, 4, 9])

    def test_k_of_one_picks_first(self):
        self.assertEqual(rl.pick_evenly(["a", "b", "c"], 1), ["a"])

    def test_k_at_least_population_returns_all(self):
        self.assertEqual(rl.pick_evenly([1, 2], 5), [1, 2])

    def test_no_duplicates_when_k_close_to_n(self):
        picked = rl.pick_evenly(list(range(5)), 4)
        self.assertEqual(len(picked), len(set(picked)))


class ParseTransTests(unittest.TestCase):
    def test_parses_id_and_uppercase_text(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "1688-142285.trans.txt"
            f.write_text(
                "1688-142285-0000 THERE WAS A TIME\n"
                "1688-142285-0001 AND SO IT GOES\n",
                encoding="utf-8",
            )
            parsed = rl.parse_trans(f)
        self.assertEqual(parsed["1688-142285-0000"], "THERE WAS A TIME")
        self.assertEqual(parsed["1688-142285-0001"], "AND SO IT GOES")
        self.assertEqual(len(parsed), 2)
