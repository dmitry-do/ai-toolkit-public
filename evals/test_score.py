"""Tests for the self-contained WER/CER scorer.

Run: python3 -m unittest test_score -v
"""
import importlib.util
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).with_name("score.py")
spec = importlib.util.spec_from_file_location("score", MODULE_PATH)
score = importlib.util.module_from_spec(spec)
spec.loader.exec_module(score)


class WerTests(unittest.TestCase):
    def test_single_substitution(self):
        r = score.wer("a b c d", "a x c d")
        self.assertEqual(r["substitutions"], 1)
        self.assertEqual(r["insertions"], 0)
        self.assertEqual(r["deletions"], 0)
        self.assertEqual(r["ref_words"], 4)
        self.assertAlmostEqual(r["wer"], 0.25)

    def test_single_insertion(self):
        r = score.wer("a b c", "a b c d")
        self.assertEqual(r["insertions"], 1)
        self.assertEqual(r["substitutions"], 0)
        self.assertEqual(r["deletions"], 0)
        self.assertAlmostEqual(r["wer"], 1 / 3)

    def test_single_deletion(self):
        r = score.wer("a b c d", "a b c")
        self.assertEqual(r["deletions"], 1)
        self.assertAlmostEqual(r["wer"], 0.25)

    def test_normalization_ignores_case_and_punctuation(self):
        r = score.wer("Hello, World!", "hello   world")
        self.assertAlmostEqual(r["wer"], 0.0)


class CerTests(unittest.TestCase):
    def test_single_char_substitution(self):
        self.assertAlmostEqual(score.cer("abcd", "abxd"), 0.25)


class ExtractTranscriptTests(unittest.TestCase):
    SAMPLE = (
        "# Title\n\n"
        "## Source\n"
        "- Audio: `x.mp3`\n"
        "- Backend: `mlx`\n\n"
        "## Transcript\n\n"
        "[00:00-00:05] Hello there\n\n"
        "[00:05-00:10] General Kenobi\n"
    )

    def test_extracts_spoken_text_only(self):
        out = score.extract_transcript(self.SAMPLE)
        self.assertEqual(out, "Hello there General Kenobi")


if __name__ == "__main__":
    unittest.main()
