"""Card model plus readers/writers for the two formats srsconv converts between.

ankitsv: a tab-separated format modeled on Anki's plain-text note export,
extended with SM-2 scheduling columns. Due dates here are plain ISO calendar
dates, not Anki's internal collection-relative day integers, so this does not
round-trip with a real .apkg file (see README for that limitation).

jsonl: one JSON object per line, same fields, meant for scripts that would
rather not deal with tab-escaping.
"""

from __future__ import annotations

import dataclasses
import datetime
import json
from typing import Optional

ANKITSV_COLUMNS = ["front", "back", "tags", "interval", "ease", "due", "reps", "lapses"]

# Anki's plain-text export can't contain a literal newline inside a field, so
# multi-line card content is stored with newlines swapped for this marker.
_NEWLINE_MARKER = "<br>"

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
