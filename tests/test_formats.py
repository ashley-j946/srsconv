import datetime
import io
import sqlite3
import tempfile
import unittest
import zipfile
from pathlib import Path

from srsconv.formats import (
    Card,
    DEFAULT_EASE_FACTOR,
    parse_ankitsv,
    parse_apkg,
    parse_jsonl,
    parse_mnemosyne,
    write_ankitsv,
    write_jsonl,
)

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


def _build_apkg_bytes(creation_date, notes):
    """Build an in-memory .apkg: a zip containing a minimal collection.anki2.

    notes is a list of (front, back, tags, card_row) tuples, where card_row
    is (type, ivl, factor, due, reps, lapses) matching Anki's cards table.
    """
    with tempfile.NamedTemporaryFile(suffix=".anki2") as tmp:
        connection = sqlite3.connect(tmp.name)
        try:
            connection.execute("CREATE TABLE col (crt INTEGER)")
            connection.execute("CREATE TABLE notes (id INTEGER, tags TEXT, flds TEXT)")
            connection.execute(
                "CREATE TABLE cards (nid INTEGER, type INTEGER, ivl INTEGER, "
                "factor INTEGER, due INTEGER, reps INTEGER, lapses INTEGER)"
            )
            creation_ts = int(
                datetime.datetime(
                    creation_date.year, creation_date.month, creation_date.day
                ).timestamp()
            )
            connection.execute("INSERT INTO col (crt) VALUES (?)", (creation_ts,))
            for note_id, (front, back, tags, card_row) in enumerate(notes, start=1):
                flds = "\x1f".join([front, back])
                connection.execute(
                    "INSERT INTO notes (id, tags, flds) VALUES (?, ?, ?)",
                    (note_id, tags, flds),
                )
                card_type, ivl, factor, due, reps, lapses = card_row
                connection.execute(
                    "INSERT INTO cards (nid, type, ivl, factor, due, reps, lapses) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (note_id, card_type, ivl, factor, due, reps, lapses),
                )
            connection.commit()
        finally:
            connection.close()
        db_bytes = Path(tmp.name).read_bytes()

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("collection.anki2", db_bytes)
    return buffer.getvalue()


class ApkgParsingTests(unittest.TestCase):
    def test_new_card_has_no_due_date_or_interval(self):
        data = _build_apkg_bytes(
            datetime.date(2026, 1, 1),
            [("front", "back", "", (0, 0, 0, 3, 0, 0))],
        )
        [card] = parse_apkg(data)
        self.assertEqual(card.front, "front")
        self.assertEqual(card.back, "back")
        self.assertIsNone(card.due)
        self.assertEqual(card.interval_days, 0)
        self.assertEqual(card.ease_factor, DEFAULT_EASE_FACTOR)

    def test_review_card_due_is_relative_to_creation_date(self):
        data = _build_apkg_bytes(
            datetime.date(2026, 1, 1),
            [("q", "a", "leech tricky", (2, 10, 2500, 5, 3, 1))],
        )
        [card] = parse_apkg(data)
        self.assertEqual(card.tags, ["leech", "tricky"])
        self.assertEqual(card.interval_days, 10)
        self.assertEqual(card.ease_factor, 250)
        self.assertEqual(card.due, datetime.date(2026, 1, 6))
        self.assertEqual(card.reps, 3)
        self.assertEqual(card.lapses, 1)

    def test_learning_card_due_is_a_truncated_timestamp(self):
        due_dt = datetime.datetime(2026, 3, 1, 9, 0, 0)
        data = _build_apkg_bytes(
            datetime.date(2026, 1, 1),
            [("q", "a", "", (1, -600, 0, int(due_dt.timestamp()), 1, 0))],
        )
        [card] = parse_apkg(data)
        self.assertEqual(card.due, due_dt.date())
        # negative ivl (a learning-step countdown in seconds) isn't an
        # established interval yet
        self.assertEqual(card.interval_days, 0)

    def test_note_with_extra_fields_keeps_only_first_two(self):
        data = _build_apkg_bytes(
            datetime.date(2026, 1, 1),
            [("front only", "back only", "", (0, 0, 0, 0, 0, 0))],
        )
        [card] = parse_apkg(data)
        self.assertEqual((card.front, card.back), ("front only", "back only"))

    def test_missing_collection_database_is_rejected(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("media", "{}")
        with self.assertRaises(ValueError):
            parse_apkg(buffer.getvalue())


class MnemosyneParsingTests(unittest.TestCase):
    def test_item_inside_category_uses_category_as_tag(self):
        text = """
        <mnemosyne>
        <category name="French">
        <item>
        <Q>chat</Q>
        <A>cat</A>
        <grade>2</grade>
        <easiness>2.5</easiness>
        <acq_reps>3</acq_reps>
        <ret_reps>1</ret_reps>
        <lapses>0</lapses>
        <last_rep>1735689600</last_rep>
        <next_rep>1736294400</next_rep>
        </item>
        </category>
        </mnemosyne>
        """
        [card] = parse_mnemosyne(text)
        self.assertEqual(card.front, "chat")
        self.assertEqual(card.back, "cat")
        self.assertEqual(card.tags, ["French"])
        self.assertEqual(card.ease_factor, 250)
        self.assertEqual(card.reps, 4)
        self.assertEqual(card.lapses, 0)
        self.assertEqual(card.interval_days, 7)
        self.assertEqual(card.due, datetime.date.fromtimestamp(1736294400))

    def test_default_category_is_not_kept_as_a_tag(self):
        text = """
        <mnemosyne>
        <category name="default">
        <item><Q>q</Q><A>a</A></item>
        </category>
        </mnemosyne>
        """
        [card] = parse_mnemosyne(text)
        self.assertEqual(card.tags, [])

    def test_explicit_tag_elements_are_collected(self):
        text = """
        <mnemosyne>
        <category name="default">
        <item>
        <Q>q</Q>
        <A>a</A>
        <tag>science</tag>
        <tag>physics</tag>
        </item>
        </category>
        </mnemosyne>
        """
        [card] = parse_mnemosyne(text)
        self.assertEqual(card.tags, ["science", "physics"])

    def test_item_with_no_scheduling_history_is_new(self):
        text = "<mnemosyne><category name=\"default\"><item><Q>q</Q><A>a</A></item></category></mnemosyne>"
        [card] = parse_mnemosyne(text)
        self.assertIsNone(card.due)
        self.assertEqual(card.interval_days, 0)
        self.assertEqual(card.reps, 0)
        self.assertEqual(card.ease_factor, DEFAULT_EASE_FACTOR)

    def test_item_directly_under_root_without_category_wrapper(self):
        text = "<mnemosyne><item><Q>q</Q><A>a</A></item></mnemosyne>"
        [card] = parse_mnemosyne(text)
        self.assertEqual((card.front, card.back), ("q", "a"))


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
