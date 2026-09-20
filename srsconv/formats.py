"""Card model plus readers/writers for the formats srsconv converts between.

ankitsv: a tab-separated format modeled on Anki's plain-text note export,
extended with SM-2 scheduling columns. Due dates here are plain ISO calendar
dates rather than Anki's internal collection-relative day integers.

jsonl: one JSON object per line, same fields, meant for scripts that would
rather not deal with tab-escaping.

apkg: a real Anki package (zip file containing a SQLite collection). Read
only — see parse_apkg for why there's no writer.
"""

from __future__ import annotations

import dataclasses
import datetime
import io
import json
import sqlite3
import tempfile
import zipfile
from typing import Optional

ANKITSV_COLUMNS = ["front", "back", "tags", "interval", "ease", "due", "reps", "lapses"]

# Anki's plain-text export can't contain a literal newline inside a field, so
# multi-line card content is stored with newlines swapped for this marker.
_NEWLINE_MARKER = "<br>"

# Anki stores a note's fields as one string joined with this byte (0x1f, the
# ASCII "unit separator"), regardless of how many fields the note type has.
_APKG_FIELD_SEPARATOR = "\x1f"

DEFAULT_EASE_FACTOR = 250  # SM-2 default of 2.50, stored as basis points
MIN_EASE_FACTOR = 130  # SM-2 floor of 1.30


@dataclasses.dataclass
class Card:
    front: str
    back: str
    tags: list[str] = dataclasses.field(default_factory=list)
    interval_days: int = 0
    ease_factor: int = DEFAULT_EASE_FACTOR
    due: Optional[datetime.date] = None
    reps: int = 0
    lapses: int = 0


def _split_lines(text: str) -> list[str]:
    return text.replace("\r\n", "\n").replace("\r", "\n").split("\n")


def parse_ankitsv(text: str) -> list[Card]:
    lines = [line for line in _split_lines(text) if line.strip() != ""]
    if not lines:
        return []

    header = lines[0].split("\t")
    unknown = set(header) - set(ANKITSV_COLUMNS)
    if unknown:
        raise ValueError(f"unknown ankitsv column(s): {sorted(unknown)}")

    cards = []
    for line in lines[1:]:
        fields = line.split("\t")
        if len(fields) > len(header):
            raise ValueError(f"row has more fields than header: {line!r}")
        # Rows are allowed to omit trailing columns (e.g. a new card with no
        # scheduling data yet), so pad with empty strings rather than error.
        fields += [""] * (len(header) - len(fields))
        row = dict(zip(header, fields))
        cards.append(_row_to_card(row))
    return cards


def _row_to_card(row: dict) -> Card:
    front = row.get("front", "").replace(_NEWLINE_MARKER, "\n")
    back = row.get("back", "").replace(_NEWLINE_MARKER, "\n")
    tags_field = row.get("tags", "")
    tags = tags_field.split() if tags_field.strip() else []

    interval_field = row.get("interval", "")
    interval_days = int(interval_field) if interval_field.strip() else 0

    ease_field = row.get("ease", "")
    ease_factor = int(ease_field) if ease_field.strip() else DEFAULT_EASE_FACTOR

    due_field = row.get("due", "")
    due = datetime.date.fromisoformat(due_field) if due_field.strip() else None

    reps_field = row.get("reps", "")
    reps = int(reps_field) if reps_field.strip() else 0

    lapses_field = row.get("lapses", "")
    lapses = int(lapses_field) if lapses_field.strip() else 0

    return Card(
        front=front,
        back=back,
        tags=tags,
        interval_days=interval_days,
        ease_factor=ease_factor,
        due=due,
        reps=reps,
        lapses=lapses,
    )


def write_ankitsv(cards: list[Card]) -> str:
    lines = ["\t".join(ANKITSV_COLUMNS)]
    for card in cards:
        front = _escape_ankitsv_field(card.front)
        back = _escape_ankitsv_field(card.back)
        row = [
            front,
            back,
            " ".join(card.tags),
            str(card.interval_days),
            str(card.ease_factor),
            card.due.isoformat() if card.due else "",
            str(card.reps),
            str(card.lapses),
        ]
        lines.append("\t".join(row))
    return "\n".join(lines) + "\n"


def _escape_ankitsv_field(value: str) -> str:
    if "\t" in value:
        raise ValueError(f"field cannot contain a literal tab: {value!r}")
    return value.replace("\n", _NEWLINE_MARKER)


def parse_jsonl(text: str) -> list[Card]:
    cards = []
    for line in _split_lines(text):
        if line.strip() == "":
            continue
        obj = json.loads(line)
        due_value = obj.get("due")
        cards.append(
            Card(
                front=obj["front"],
                back=obj["back"],
                tags=list(obj.get("tags", [])),
                interval_days=int(obj.get("interval_days", 0)),
                ease_factor=int(obj.get("ease_factor", DEFAULT_EASE_FACTOR)),
                due=datetime.date.fromisoformat(due_value) if due_value else None,
                reps=int(obj.get("reps", 0)),
                lapses=int(obj.get("lapses", 0)),
            )
        )
    return cards


def write_jsonl(cards: list[Card]) -> str:
    lines = []
    for card in cards:
        obj = {
            "front": card.front,
            "back": card.back,
            "tags": card.tags,
            "interval_days": card.interval_days,
            "ease_factor": card.ease_factor,
            "due": card.due.isoformat() if card.due else None,
            "reps": card.reps,
            "lapses": card.lapses,
        }
        lines.append(json.dumps(obj, ensure_ascii=False))
    return "\n".join(lines) + ("\n" if lines else "")


def parse_apkg(data: bytes) -> list[Card]:
    """Read cards out of a real Anki package (.apkg).

    An .apkg is a zip file containing a SQLite collection database plus any
    media. This only reads that database; there is no writer, since
    reconstructing a collection that Anki will accept back (decks, note
    types, media references) is a lot more than this tool needs to do.

    Only the first two fields of each note are used as front/back, so note
    types with more than two fields (e.g. cloze deletions) will lose
    everything past the second field.
    """
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        names = archive.namelist()
        db_name = "collection.anki21" if "collection.anki21" in names else "collection.anki2"
        if db_name not in names:
            raise ValueError("not an Anki package: no collection.anki2(1) database found")
        db_bytes = archive.read(db_name)

    # sqlite3 can only open a database from a path on disk, so the extracted
    # bytes have to be written to a temp file first.
    with tempfile.NamedTemporaryFile(suffix=".anki2") as tmp:
        tmp.write(db_bytes)
        tmp.flush()
        connection = sqlite3.connect(tmp.name)
        try:
            (creation_ts,) = connection.execute("SELECT crt FROM col").fetchone()
            creation_date = datetime.date.fromtimestamp(creation_ts)
            rows = connection.execute(
                """
                SELECT notes.flds, notes.tags, cards.type, cards.ivl,
                       cards.factor, cards.due, cards.reps, cards.lapses
                FROM cards JOIN notes ON cards.nid = notes.id
                """
            ).fetchall()
        finally:
            connection.close()

    return [_apkg_row_to_card(row, creation_date) for row in rows]


def _apkg_row_to_card(row: tuple, creation_date: datetime.date) -> Card:
    flds, tags_field, card_type, ivl, factor, due, reps, lapses = row
    fields = flds.split(_APKG_FIELD_SEPARATOR)
    front = fields[0] if fields else ""
    back = fields[1] if len(fields) > 1 else ""
    tags = tags_field.split() if tags_field.strip() else []

    # ivl is negative while a card is still stuck in a learning step, where
    # it holds a number of seconds rather than days; treat that as no
    # established interval yet rather than a nonsensical negative one.
    interval_days = ivl if ivl > 0 else 0

    # factor is ease*1000 (e.g. 2500 for 250%); brand-new cards have factor 0.
    ease_factor = factor // 10 if factor else DEFAULT_EASE_FACTOR

    return Card(
        front=front,
        back=back,
        tags=tags,
        interval_days=interval_days,
        ease_factor=ease_factor,
        due=_apkg_due_to_date(card_type, due, creation_date),
        reps=reps,
        lapses=lapses,
    )


def _apkg_due_to_date(
    card_type: int, due: int, creation_date: datetime.date
) -> Optional[datetime.date]:
    if card_type == 0:
        # New: due is the card's position in the new-card queue, not a date.
        return None
    if card_type in (1, 3):
        # Learning / relearning: due is a Unix timestamp.
        return datetime.date.fromtimestamp(due)
    # Review (type 2): due is a day count relative to the collection's
    # creation date.
    return creation_date + datetime.timedelta(days=due)
