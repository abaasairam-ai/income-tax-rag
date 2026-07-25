# Income Tax RAG — Private Tax Knowledge Assistant

A retrieval system over the **complete Income-tax Act, 2025** and **Income-tax
Rules, 2026** — parsed, validated and chunked into 1,505 citation-tagged
segments, ready for a Retrieval-Augmented Generation pipeline.

Designed to run **fully local** — documents, embeddings and model all on-machine —
so confidential client data never leaves the device.

| | |
|---|---|
| Income-tax Act, 2025 (as amended by Finance Act, 2026) | 666 pages · **536/536 sections** |
| Income-tax Rules, 2026 [G.S.R. 198(E)] | 422 pages · **333/333 rules** |
| Output | 1,505 chunks · median 362 words |

---

## Why parsing an Act is the hard part

The naive approach — regex for a line starting with a number — finds **868
"sections" where there are 536**. The official PDF fights you:

| Problem | Example |
|---|---|
| No space after the number | `443.9[***]` · `427.(1)` |
| A space *before* the period | `94 . (1)` |
| Slab **tables** that look like section starts | `3. More than 1000000.` |
| **Footnotes** numbered 1–99 at the end of the file | hijacks the whole sequence |
| Headings wrapped in amendment markers | `3[Fee for default in furnishing statements.` |
| Headings split across two lines | — |

The fix was to stop trusting the pattern and require three things at once:

1. the number **continues the sequence** (no jumps),
2. it sits **near** the previous section (not 10,000 lines later),
3. a **real heading** precedes it — which is what separates a section from a
   table row.

Result: 536/536 sections, strictly ordered, every one with its heading and chapter.

## Chunking strategy

Structure first, size second:

1. Split at section / rule boundaries — the natural unit of legal meaning.
2. Sections over 600 words split at their own sub-clause boundaries, trying
   `(1)` → `(a)`/`(i)` → `(A)` → numbered table rows.
3. Short sections stay whole.
4. **No overlap.** Sections are self-contained; overlapping duplicates law,
   which is worse than useless in a tax assistant.

### Tables

Section 393 (TDS) is a large table, and a row torn from its header is
meaningless. So the **column header is re-attached** to every chunk that starts
mid-table (205 chunks), and each table is **also** stored whole (83 chunks) for
questions that compare rows.

⚠️ A whole-table chunk (7,205 words for s.393) exceeds an embedding model's input
limit, so its vector reflects only the opening portion. Treat those as context,
not as the primary retrieval target.

## Every chunk cites itself

```
Income-tax Act, 2025 ... | Section 393 - Tax to be deducted at source | CHAPTER XIX ... | part 1 of 16
393. (1) Where any income or sum of the nature specified in column B ...
```

The section number becomes searchable text, and the citation is already present
when the model answers.

## Layout

```
income-tax-rag/
├── docs-text/      extracted, cleaned text of the Act and Rules
├── chunks/         act-chunks.jsonl · rules-chunks.jsonl (+ README)
├── scripts/        detect.py (section detector) · chunk.py (chunker)
├── SCOPE.md        what is and is NOT indexed — read this
└── 00-DOWNLOAD-CHECKLIST.md
```

**Source PDFs are not in this repo** — they are 102MB and 69MB, over GitHub's
file limit. Download them from
[incometaxindia.gov.in](https://www.incometaxindia.gov.in/income-tax-act-2025);
see the checklist.

## Scope — read before trusting an answer

Indexed: the Act and the Rules, complete, current to **30 June 2026**.

**Not** indexed: circulars, notifications, the **Finance Act 2026 (so tax rates
are not covered — rates live in its First Schedule, not in the Act)**, the
1961→2025 section mapping, and forms. Full detail in [`SCOPE.md`](SCOPE.md).

A research aid, not tax advice. Verify against the official text.

## Rebuild

```bash
python scripts/chunk.py chunks/
```

## Status

Chunking complete and verified. Next: embed into a local Chroma store and wire
up retrieval with a local model via Ollama.
