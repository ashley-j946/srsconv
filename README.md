# srsconv

Converts spaced-repetition flashcards between two plain-text formats:

- **ankitsv** — tab-separated, one card per line, modeled on Anki's
  plain-text note export but extended with SM-2 scheduling columns
  (`interval`, `ease`, `due`, `reps`, `lapses`).
- **jsonl** — one JSON object per line, same fields, easier to grep/diff/edit
  with a script than tab-separated text.

Anki's own export is fine for opening in a spreadsheet, but it's awkward to
script against: tabs as a delimiter make it hard to store multi-line content,
and there's no null-safe way to represent "this card has never been
reviewed" versus "this card is due today". jsonl fixes both. This tool moves
cards between the two without losing scheduling state.

## Example

`cards.tsv`:

```
front	back	tags	interval	ease	due	reps	lapses
capital of France	Paris	geography	12	250	2026-09-20	4	0
2 + 2	4	math arithmetic	0	250		0	0
```

The second row is a brand-new card: no interval, no due date yet, default
ease factor.

```
$ python -m srsconv.cli cards.tsv cards.jsonl
converted 2 card(s): ankitsv -> jsonl

$ cat cards.jsonl
{"front": "capital of France", "back": "Paris", "tags": ["geography"], "interval_days": 12, "ease_factor": 250, "due": "2026-09-20", "reps": 4, "lapses": 0}
{"front": "2 + 2", "back": "4", "tags": ["math", "arithmetic"], "interval_days": 0, "ease_factor": 250, "due": null, "reps": 0, "lapses": 0}
```

Converting back the other way works the same way:

```
$ python -m srsconv.cli cards.jsonl cards2.tsv
converted 2 card(s): jsonl -> ankitsv
```

Format is guessed from the file extension (`.tsv`/`.txt` -> ankitsv,
`.jsonl` -> jsonl, `.apkg` -> apkg, `.xml` -> mnemosyne). Use `--from`/`--to`
to override.

`apkg` and `mnemosyne` are read-only: they can be used as `--from`, not
`--to`. Rebuilding a collection Anki or Mnemosyne will accept back (decks,
note types, media, in Mnemosyne's case its own grade-based scheduler) is a
lot more than this tool needs to do, so there's no writer for either.

```
$ python -m srsconv.cli MyDeck.apkg cards.jsonl
converted 84 card(s): apkg -> jsonl

$ python -m srsconv.cli export.xml cards.jsonl
converted 84 card(s): mnemosyne -> jsonl
```

## Known limitations

- `due` dates in ankitsv/jsonl are plain ISO calendar dates. When reading a
  real `.apkg`, review cards convert cleanly (Anki stores their due date as
  a day count relative to the collection's creation date), but cards still
  in a learning step only have a due *timestamp*, which gets truncated to a
  date; the time of day and any short-term learning schedule are lost.
- Reading `.apkg` only looks at the first two fields of each note, so note
  types with more than two fields (e.g. cloze deletions) will lose
  everything past the second field.
- Mnemosyne doesn't store an interval directly; it derives one from a card's
  grade at scheduling time using its own lookup table. Reading its XML
  export approximates `interval_days` as the gap between the item's last and
  next review timestamps instead, which is usually close but isn't the
  exact figure Mnemosyne would compute.
- Multi-line card content is stored in ankitsv with newlines swapped for the
  literal text `<br>`, the same convention Anki's plain-text export uses.
  If a card's own text already contains that literal substring, it will read
  back as a line break instead.

## Development

No dependencies beyond the standard library. Run the tests with:

```
python -m unittest discover -s tests
```
