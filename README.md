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
`.jsonl` -> jsonl). Use `--from`/`--to` to override.

## Known limitations

- `due` dates are plain ISO calendar dates. Anki stores due dates internally
  as integers relative to when the collection was created, so this format
  does not round-trip with a real `.apkg` file — reading those would mean
  parsing Anki's SQLite collection, which isn't implemented yet.
- Multi-line card content is stored in ankitsv with newlines swapped for the
  literal text `<br>`, the same convention Anki's plain-text export uses.
  If a card's own text already contains that literal substring, it will read
  back as a line break instead.

## Development

No dependencies beyond the standard library. Run the tests with:

```
python -m unittest discover -s tests
```
