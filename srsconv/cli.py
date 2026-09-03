from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .formats import parse_ankitsv, parse_jsonl, write_ankitsv, write_jsonl

READERS = {"ankitsv": parse_ankitsv, "jsonl": parse_jsonl}
WRITERS = {"ankitsv": write_ankitsv, "jsonl": write_jsonl}

EXTENSION_FORMATS = {
    ".tsv": "ankitsv",
    ".txt": "ankitsv",
    ".jsonl": "jsonl",
}


def detect_format(path: Path) -> str:
    fmt = EXTENSION_FORMATS.get(path.suffix.lower())
    if fmt is None:
        raise ValueError(
            f"can't guess format from extension {path.suffix!r}; pass --from/--to explicitly"
        )
    return fmt


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="srsconv",
        description="Convert spaced-repetition cards between ankitsv and jsonl",
    )
    parser.add_argument("input", type=Path, help="input file")
    parser.add_argument("output", type=Path, help="output file")
    parser.add_argument("--from", dest="from_format", choices=sorted(READERS), default=None)
    parser.add_argument("--to", dest="to_format", choices=sorted(WRITERS), default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    from_format = args.from_format or detect_format(args.input)
    to_format = args.to_format or detect_format(args.output)

    text = args.input.read_text(encoding="utf-8")
    cards = READERS[from_format](text)
    args.output.write_text(WRITERS[to_format](cards), encoding="utf-8")

    print(f"converted {len(cards)} card(s): {from_format} -> {to_format}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
