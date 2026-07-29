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

## Running it

```bash
pip install chromadb

python scripts/embed.py                                        # once (~2 min)
python scripts/ask.py "How is income from house property computed?"
python scripts/ask.py "How is registration applied for?" --unit rule
```

`embed.py` downloads a small embedding model (~80MB) on first run, then works
offline forever. The vector database is written to `~/.income_tax_rag_chroma` —
deliberately outside any cloud-synced folder, because OneDrive and Dropbox lock
SQLite files mid-sync and Chroma fails with `disk I/O error`.

### Fully air-gapped answers

Retrieval alone returns the relevant text. For a written answer with nothing
leaving the machine:

```bash
ollama pull llama3.2
python scripts/ask.py "..." --mode ollama
```

Then turn off your network and run it again — it still works. Documents,
embeddings and model are all local.

### Guardrails

**In code — the one that matters.** If the closest chunk is further than
`MAX_DISTANCE` (1.25), the model is never consulted and the script refuses.

This exists because of a real, observed failure. Asked *"what is TDS"*,
retrieval returned five irrelevant chunks (best distance 1.46) and the model
invented a definition, citing "section 196(1)(d)". Section 196 is about capital
gains; that text does not exist anywhere in the Act. A prompt instruction is a
request a model can ignore — a threshold in code is not. In tax work "I don't
know" is a correct answer; a confident fabricated citation is a serious one.

Calibrated on real runs: good matches 0.58–0.73, the hallucination case 1.46.
Override with `MAX_DISTANCE=1.6` to see an answer regardless.

**Temperature 0.** Generation is deterministic. Ollama's default is 0.8, at
which the model picks its top token roughly 96% of the time — which sounds
safe until you raise it to the power of the answer length: over 60 tokens
that is a 91% chance of deviating somewhere. A tax citation must survive being
asked twice. It is also what makes an eval set meaningful — at 0.8 you measure
the sampling, not the system.

**In the prompt.** Answer only from context; cite the section; rate questions →
say rates are in the Finance Act (not indexed); 1961 section numbers → say the
mapping is not indexed.

### Query expansion

The abbreviation **"TDS" appears zero times in the Act** — it says "deducted at
source". So the query is expanded before embedding: `TDS` → `tax deducted at
source deduction of tax`. Same for TCS, ITR, AY, PY, HRA, LTCG, MAT, PAN, TAN
and others. This bridges how a practitioner speaks to how the Act is written.

### Notes

- Whole-table chunks are **not indexed** (83 of them). They exceed the embedding
  model's input limit, so their vectors are unrepresentative and would crowd out
  the accurate per-part chunks. They remain in the JSONL for reading. Set
  `INDEX_FULL_TABLES=1` to include them anyway.
- `OFFLINE=1` swaps in a zero-dependency word-hashing embedder that needs no
  download. Useful on a locked-down machine to prove the pipeline runs, but it
  matches words rather than meaning — rankings are noticeably worse, and the
  distance guardrail is **disabled** because its distances carry no relevance
  signal (measured: it scored "what is the capital of France?" at 0.731 and a
  valid house-property question at 1.126 — inverted). Use the default for real work.
- **Chunks with no substantive content are dropped** — fragments like `(7) (8)`
  where a numbered list split across a boundary. They carried no meaning but
  still occupied a retrieval slot.
- **Table headers are only repeated when the chunk has enough content of its
  own.** One fragment measured 80% header / 20% content, which meant its
  *embedding* described the header rather than the content — so it matched any
  table-ish query and crowded out real answers.

## Rebuild the chunks

```bash
python scripts/chunk.py chunks/
```

## Status

Chunking, embedding and retrieval complete and verified end-to-end.
Next: Ollama for local generation, then an eval set to measure retrieval accuracy.
