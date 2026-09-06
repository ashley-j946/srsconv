import tempfile
import unittest
from pathlib import Path

from srsconv.cli import build_parser, detect_format, main


class DetectFormatTests(unittest.TestCase):
    def test_tsv_extension_is_ankitsv(self):
        self.assertEqual(detect_format(Path("cards.tsv")), "ankitsv")

    def test_txt_extension_is_ankitsv(self):
        self.assertEqual(detect_format(Path("cards.txt")), "ankitsv")

    def test_jsonl_extension_is_jsonl(self):
        self.assertEqual(detect_format(Path("cards.jsonl")), "jsonl")

    def test_extension_matching_is_case_insensitive(self):
        self.assertEqual(detect_format(Path("cards.TSV")), "ankitsv")

    def test_unknown_extension_raises(self):
        with self.assertRaises(ValueError):
            detect_format(Path("cards.csv"))


class MainTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmpdir = Path(self._tmp.name)

    def test_tsv_to_jsonl_round_trip(self):
        src = self.tmpdir / "cards.tsv"
        dst = self.tmpdir / "cards.jsonl"
        src.write_text("front\tback\ninterest\tcompound growth over time\n", encoding="utf-8")

        result = main([str(src), str(dst)])

        self.assertEqual(result, 0)
        self.assertIn('"front": "interest"', dst.read_text(encoding="utf-8"))

    def test_jsonl_to_tsv_round_trip(self):
        src = self.tmpdir / "cards.jsonl"
        dst = self.tmpdir / "cards.tsv"
        src.write_text('{"front": "a", "back": "b"}\n', encoding="utf-8")

        result = main([str(src), str(dst)])

        self.assertEqual(result, 0)
        lines = dst.read_text(encoding="utf-8").splitlines()
        self.assertEqual(lines[1].split("\t")[:2], ["a", "b"])

    def test_unrecognized_extension_requires_explicit_format(self):
        src = self.tmpdir / "cards.csv"
        dst = self.tmpdir / "cards.jsonl"
        src.write_text("front,back\na,b\n", encoding="utf-8")

        with self.assertRaises(ValueError):
            main([str(src), str(dst)])

    def test_from_override_beats_extension_guess(self):
        # named .txt (which would guess ankitsv) but actually holds jsonl
        src = self.tmpdir / "cards.txt"
        dst = self.tmpdir / "cards.jsonl"
        src.write_text('{"front": "a", "back": "b"}\n', encoding="utf-8")

        result = main([str(src), str(dst), "--from", "jsonl"])

        self.assertEqual(result, 0)
        self.assertIn('"front": "a"', dst.read_text(encoding="utf-8"))

    def test_to_override_beats_extension_guess(self):
        src = self.tmpdir / "cards.tsv"
        dst = self.tmpdir / "cards.out"
        src.write_text("front\tback\na\tb\n", encoding="utf-8")

        result = main([str(src), str(dst), "--to", "jsonl"])

        self.assertEqual(result, 0)
        self.assertIn('"front": "a"', dst.read_text(encoding="utf-8"))


class BuildParserTests(unittest.TestCase):
    def test_from_and_to_reject_unknown_format_names(self):
        parser = build_parser()
        with self.assertRaises(SystemExit):
            parser.parse_args(["in.tsv", "out.jsonl", "--from", "csv"])


if __name__ == "__main__":
    unittest.main()
