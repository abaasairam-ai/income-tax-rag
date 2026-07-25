# Chunks — what was produced and how to judge it

Stage 1 (chunking) output. Nothing has been embedded or stored in a database yet
— these files are deliberately readable so you can inspect them before we go on.

## Files

| File | Chunks | Median | Max (normal) |
|---|---|---|---|
| `act-chunks.jsonl` | 910 | 362 words | 704 words |
| `rules-chunks.jsonl` | 595 | 327 words | 704 words |

**1,505 chunks total**, of which **83 are whole-table chunks** (see below).

One JSON object per line. Open in any text editor.

## Fields

```
id        section-393-p1        unique chunk id ("-table" = whole table)
source    "Income-tax Act, 2025 (as amended by Finance Act, 2026)"
unit      section | rule
number    393                   section/rule number
heading   "Tax to be deducted at source"
chapter   "CHAPTER XIX - COLLECTION AND RECOVERY OF TAX"
part      1                     which piece of the section (0 = whole table)
of_parts  16                    how many pieces the section became
table_header_repeated  true     column header re-attached to this part
is_full_table          false    true = the entire table as one chunk
words     559
text      citation header + the actual legal text
```

Every chunk's `text` **begins with a citation line**, e.g.

```
Income-tax Act, 2025 ... | Section 393 - Tax to be deducted at source | CHAPTER XIX - ... | part 1 of 16
393. (1) Where any income or sum of the nature specified in column B ...
```

That header does two jobs: the section number becomes searchable text, and the
citation is already sitting in the chunk when the model answers.

## Verification performed

- **Coverage:** all 536 Act sections and all 333 Rules present. No gaps.
- **Integrity:** no empty chunks, no duplicate ids, no chunk over 637 words.
- **Chapters:** every Act chunk carries its chapter.
- **Eye check:** section 2 (definitions), section 393 (TDS) read correctly.

## Table handling (fixed)

Tables were the main weakness, so two things now happen:

1. **The column header is repeated** at the top of every part that falls after a
   table starts (205 chunks). So a retrieved TDS row still carries
   `Sl.No | Nature of income | Payer | Rate | Threshold limit | A B C D`
   and you can tell which column a figure belongs to. A marker line
   `(table header repeated)` shows where the original text resumes.

2. **The whole table is also stored as a single chunk** (`is_full_table: true`,
   id ends `-table`, 83 of them). Useful for questions that compare rows —
   "which payments attract 10%?" — where one row alone can't answer.

   ⚠️ **Caveat:** a whole-table chunk (e.g. `section-393-table`, 7,205 words) is
   far longer than an embedding model's input limit (~500 words for the usual
   small models). Its *vector* therefore only reflects the opening portion, even
   though the full text is stored. Treat these as reading/context material, not
   as the primary retrieval target. The per-part chunks are what will actually
   match a query reliably.

   The capture runs from the `TABLE` marker to the end of the section, so where
   a section continues past its table the chunk includes that tail. Tables over
   10,000 words are skipped entirely — s.536's repeal schedule (31,850 words) is
   not something anyone retrieves whole.

## Known limitations — read this before trusting retrieval

1. **Continuation parts may still begin mid-structure** where the content isn't
   a table (no header to repeat). Single-part chunks are fully self-contained.

3. **23 chunks have no heading** — from 4 Rules whose headings are formatted
   unusually in the source. Their text and numbering are correct.

4. **Footnote markers survive in the text** (e.g. `81[`, `10b[`) — artefacts of
   amendment marking in the official PDF. Harmless for retrieval, slightly ugly
   in quoted answers.

## How the splitting works

Structure first, size second:

1. Split at section / rule boundaries.
2. If a section exceeds 600 words, split at its own sub-clause boundaries,
   trying levels in order: `(1)` → `(a)`/`(i)` → `(A)` → numbered table rows.
3. If a section has no sub-structure at all (e.g. s.536 repeal tables), pack by
   a line budget — which still never cuts mid-line.
4. Short sections are left whole.

**No overlap between chunks.** Sections are self-contained, and overlapping
would duplicate law — worse than useless in a tax assistant.

## Rebuilding

```bash
python scripts/chunk.py chunks/
```

Expects the cleaned text produced from the official PDFs (see `docs-text/`).
