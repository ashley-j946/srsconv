import datetime
import unittest

from srsconv.formats import Card, parse_ankitsv, parse_jsonl, write_ankitsv, write_jsonl

# Each case is a fully-formed Card. We check that both formats can round-trip
# it (parse(write(card)) == card), which is where the awkward encoding
# decisions (newlines, missing scheduling data, tab-separation) actually bite.
ROUND_TRIP_CASES = [
    (
        "plain card",
        Card(front="capital of France", back="Paris"),
    ),
    (
        "multiple tags",
        Card(front="2 + 2", back="4", tags=["math", "arithmetic"]),
    ),
    (
        "no tags",
        Card(front="H2O", back="water", tags=[]),
    ),
    (
        "multi-line front and back",
        Card(front="line one\nline two", back="answer one\nanswer two"),
    ),
    (
        "unicode content",
        Card(front="猫", back="ねこ (cat)", tags=["日本語"]),
    ),
    (
        "new card with no scheduling history",
        Card(front="unreviewed", back="still new", interval_days=0, reps=0, lapses=0, due=None),
    ),
    (
        "mature card with full scheduling",
        Card(
            front="mature",
            back="card",
            tags=["leech"],
            interval_days=90,
            ease_factor=270,
            due=datetime.date(2026, 12, 1),
            reps=12,
            lapses=2,
        ),
    ),
    (
        "ease factor at the SM-2 floor",
        Card(front="hard card", back="keeps lapsing", ease_factor=130, lapses=5),
    ),
]


class RoundTripTests(unittest.TestCase):
    def test_ankitsv_round_trip(self):
        for name, card in ROUND_TRIP_CASES:
            with self.subTest(case=name):
                [result] = parse_ankitsv(write_ankitsv([card]))
                self.assertEqual(result, card)

    def test_jsonl_round_trip(self):
        for name, card in ROUND_TRIP_CASES:
            with self.subTest(case=name):
                [result] = parse_jsonl(write_jsonl([card]))
                self.assertEqual(result, card)


class AnkitsvParsingTests(unittest.TestCase):
    def test_row_shorter_than_header_pads_with_defaults(self):
        # Some exporters drop trailing empty columns instead of writing
        # empty fields, so a data row can be shorter than the header.
        text = "front\tback\ttags\tinterval\tease\tdue\treps\tlapses\nhello\tworld\n"
        [card] = parse_ankitsv(text)
        self.assertEqual(card, Card(front="hello", back="world"))

    def test_header_only_subset_of_columns(self):
        text = "front\tback\nhello\tworld\n"
        [card] = parse_ankitsv(text)
        self.assertEqual(card, Card(front="hello", back="world"))

    def test_blank_lines_are_ignored(self):
        text = "front\tback\n\nhello\tworld\n\n"
        cards = parse_ankitsv(text)
        self.assertEqual(cards, [Card(front="hello", back="world")])

    def test_empty_file_gives_no_cards(self):
        self.assertEqual(parse_ankitsv(""), [])

    def test_unknown_column_is_rejected(self):
        text = "front\tback\tmnemonic\nhello\tworld\tnote\n"
        with self.assertRaises(ValueError):
            parse_ankitsv(text)

    def test_row_longer_than_header_is_rejected(self):
        text = "front\tback\nhello\tworld\textra\n"
        with self.assertRaises(ValueError):
            parse_ankitsv(text)

    def test_literal_tab_in_field_is_rejected_on_write(self):
        with self.assertRaises(ValueError):
            write_ankitsv([Card(front="bad\tfield", back="x")])


class JsonlParsingTests(unittest.TestCase):
    def test_minimal_line_only_front_and_back(self):
        text = '{"front": "hello", "back": "world"}\n'
        [card] = parse_jsonl(text)
        self.assertEqual(card, Card(front="hello", back="world"))

    def test_null_due_becomes_none(self):
        text = '{"front": "a", "back": "b", "due": null}\n'
        [card] = parse_jsonl(text)
        self.assertIsNone(card.due)

    def test_blank_lines_are_ignored(self):
        text = '{"front": "a", "back": "b"}\n\n\n'
        cards = parse_jsonl(text)
        self.assertEqual(len(cards), 1)

    def test_empty_file_gives_no_cards(self):
        self.assertEqual(parse_jsonl(""), [])


if __name__ == "__main__":
    unittest.main()
