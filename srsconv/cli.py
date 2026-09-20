from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .formats import parse_ankitsv, parse_apkg, parse_jsonl, write_ankitsv, write_jsonl

READERS = {"ankitsv": parse_ankitsv, "apkg": parse_apkg, "jsonl": parse_jsonl}
WRITERS = {"ankitsv": write_ankitsv, "jsonl": write_jsonl}

# Formats whose reader wants raw bytes rather than decoded text. apkg is a
# zip file, not text, so it can't go through the read_text() path below.
BINARY_READ_FORMATS = {"apkg"}

EXTENSION_FORMATS = {
    ".tsv": "ankitsv",
    ".txt": "ankitsv",
    ".jsonl": "jsonl",
    ".apkg": "apkg",
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
        description="Convert spaced-repetition cards between ankitsv, jsonl, and apkg",
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
    if to_format not in WRITERS:
        raise ValueError(
            f"can't write format {to_format!r}; supported outputs: {sorted(WRITERS)}"
        )

    if from_format in BINARY_READ_FORMATS:
        cards = READERS[from_format](args.input.read_bytes())
    else:
        cards = READERS[from_format](args.input.read_text(encoding="utf-8"))
    args.output.write_text(WRITERS[to_format](cards), encoding="utf-8")

    print(f"converted {len(cards)} card(s): {from_format} -> {to_format}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
