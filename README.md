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

### Use it from Claude Desktop (MCP)

`scripts/mcp_server.py` exposes this index to Claude Desktop as a tool called
`search_income_tax_act`. Install it with:

```bash
python scripts/add_mcp_server.py
```

That script backs up `claude_desktop_config.json` with a timestamp, refuses to
write if the existing file will not parse, adds one key, and swaps it in via a
temp file. Re-running it is safe — it detects an existing entry rather than
duplicating it. Then fully quit Claude Desktop and reopen.

**The server never writes a sentence.** It returns the retrieved provisions and
their citations; Claude does the wording. That is the whole design: a component
that only ever hands back text it was given **cannot invent a citation**. The
`MAX_DISTANCE` guardrail is enforced before anything is returned, so irrelevant
text is never even shown to the model. The one remaining failure mode is bad
*retrieval* — which is measurable, and measured below.

It imports `expand()`, `retrieve()`, `cite()` and `MAX_DISTANCE` from `ask.py`
rather than copying them, so tuning the guardrail tunes both entry points.

<details>
<summary>Four ways this fails silently on Windows</summary>

Every one of these produced either no error at all or a generic "server
disconnected". None pointed at the cause.

1. **The config is not in `%APPDATA%\Claude`.** Claude Desktop from the
   Microsoft Store is MSIX-packaged, so Windows redirects its AppData into
   `%LOCALAPPDATA%\Packages\Claude_pzs8sxrjxfjjc\LocalCache\Roaming\Claude\`.
   Writing to the obvious path gives a valid config the app never reads, and
   the symptom is **no `mcp-server-*.log` at all** — no start was ever
   attempted. Settings → Developer → Edit Config opens the real folder.
2. **MCP SDK 2.0 renamed `FastMCP` to `MCPServer`** and moved it from
   `mcp.server.fastmcp` up to `mcp.server`. Same decorator API. Any tutorial
   mentioning `FastMCP` is 1.x.
3. **The config needs a full path to the interpreter**, not the bare word
   `python` — Claude Desktop launches with its own environment.
4. **`CHROMA_DIR` must be explicit.** If `~` resolves differently there than in
   your shell, Chroma silently creates an *empty* database and returns zero
   chunks. It looks like a broken index; it is a path problem.

`scripts/check_db.py` answers "is the index actually there?" in one command.
Run it first whenever retrieval seems broken.

</details>

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

### Hybrid retrieval

Meaning-based search alone had a systematic bias: it ranked chunks that *talk
about* a topic above the chunk that *governs* it. Two independent measured cases
— section 390 (the charging provision for TDS) losing to Rule 215 (the
certificate procedure), and Rule 215 itself losing to the unrelated Rule 70
because both titles contain the phrase "form of certificate to be furnished".

So a keyword leg (BM25) was added and fused with the semantic leg using
reciprocal rank fusion. Requires `rank_bm25`. Set `HYBRID=0` to fall back to
pure semantic.

**Hybrid clearly improves ranking. Whether it improves top-1 is still
unresolved**, and the per-tag breakdown below shows it buys one failure class by
paying for another. Full numbers in *Measured accuracy*.

The reason it does not simply win: both legs fail the *same way*. Semantic
favours shared headings; keyword favours word frequency — and "Definitions"
repeats the word "defined" far more often than "Definition of tax year" does.
Adding a second opinion added a second version of the same bias, so fusion
improves "somewhere in the top 5" more than it improves "on top". When the legs
disagree, RRF picks the compromise both mildly like rather than the answer one
of them loved.

The clearest instance is `accommodating-party`. Semantic alone gets it right —
section 184, "Interpretation", tops the list. Hybrid breaks it, because BM25
matches the query words against section 182's *title* ("Treatment of connected
person and accommodating party") while the actual definition sits under the
generic heading. The keyword leg does not merely fail to fix the bias; **it is a
second implementation of it.**

Fixing this needs something that targets the bias directly — penalising the
broader, more general chunk when the question names a specific thing — not a
third leg.

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

## Measured accuracy

Claims about retrieval quality are cheap, so there is an eval set:
`evals/eval_set.jsonl`, **32 cases — 28 retrieval, 4 guardrail** — each naming
the provision that *should* come back, and each tagged with the failure class it
is meant to probe. Run it with:

```bash
python evals/run_eval.py
```

| | semantic only | + hybrid |
|---|---|---|
| Right answer ranked 1st | 39% | **43%** |
| In the top 3 | 64% | **75%** |
| In the top 5 | 82% | **86%** |
| MRR | 0.539 | **0.604** |
| Guardrail refusals correct | 4/4 | 4/4 |

*(`results-2026-07-30-hybrid0.json` and `-hybrid1.json`. An earlier run wrote
both configurations to one date-stamped filename and silently overwrote the
first; the runner now encodes the mode in the name.)*

### The eval set started at 12 cases. Growing it to 32 overturned two of my own published findings.

This is the part worth reading. The first baseline was 12 cases, and this README
previously reported three findings from it. Two of them did not survive contact
with a larger set.

**Withdrawn: "retrieval is confidently wrong, not slightly wrong."** On 12 cases
top-1 and top-3 were *identical* at 60% — nothing ever ranked 2nd or 3rd — and I
concluded that retrieval either nails a question or misses it badly. On 32 cases
top-1 is 39% and top-3 is 64%: a 25-point gap, with cases landing at rank 2 and 3
throughout. The conclusion was an artifact of twelve questions.

**Withdrawn: "hybrid retrieval does not move top-1."** On 12 cases top-1 went 60%
→ 60%, and I recorded that hybrid had failed its stated success test. On 32 cases
it goes 39% → 43%. **But the honest reading is the more useful one:** 4 points
across 28 retrieval cases is a single case, which is still noise. What is *not*
noise is top-3 (+3 cases) and MRR (+0.065). So the defensible claim is that
hybrid clearly improves ranking, and whether it improves top-1 remains
unresolved even at 32 cases.

**Do not compare 39% against the old 60%.** The 20 new cases were written to
probe known weaknesses, not to be a fair sample, so the score was expected to
fall and did. That is the instrument getting sharper, not the system getting
worse. `results-2026-07-29.json` remains the baseline for the original 12 only.

Ground truth for every new case was read from the provision text through the MCP
server, never from the model's memory of the Act — the 2025 Act renumbered
everything. **The trap deliberately avoided:** asking the retriever for the
answer and recording its top hit would have produced 100% top-1 by construction
and measured nothing.

### What the per-tag table shows that the headline hides

Top-1 accuracy by failure class — this is the payoff for tagging:

| tag | semantic | + hybrid | n |
|---|---|---|---|
| procedural-vs-charging | 9% | **27%** | 11 |
| thin-heading | 40% | **20%** | 5 |
| sentinel | 89% | 89% | 9 |
| shorthand | 0% | 0% | 4 |
| guardrail-margin | 50% | 50% | 2 |
| regression-watch | 100% | **0%** | 1 |
| general-beats-specific | 0% | 0% | 1 |

The aggregate says hybrid is better. The per-tag table says hybrid **trades one
failure class for another** — it buys procedural-vs-charging (+2 cases) and pays
for it in thin-heading (−1 case), and it reintroduces a known regression where
section 2 "Definitions" takes the top slot from section 3 "Definition of tax
year". Without tags that trade is invisible, and the next fix would have been
declared a win on the strength of an aggregate that concealed it.

**`shorthand` is the cleanest open problem: 0% top-1 on both, 100% top-5 on
both.** All four abbreviation cases retrieve the right provision, never first.
Query expansion is working; ranking is not.

### The real bias is generality, not procedure

The original diagnosis was that procedural Rules outrank substantive Act
sections. The larger set broke that story in both directions — `return-who-files`
has a Rule beating a section, `updated-return` has a section beating the Rule
literally titled "Furnishing of updated return of income". What is constant is
that **the winner is the broader, more general chunk and the loser is the
specific provision.** Act-versus-Rules is noise. That reframes the fix: the
target is generality, not procedural wording.

### Two findings from the original 12 that did survive

*The guardrail has almost no margin.* A correct answer scored 1.219 against a
threshold of 1.25 — 0.031 from being refused. The larger set tightened this
rather than loosening it: a GST question (adjacent domain, not absurd) scored
**1.349**, closer to the limit than the off-topic control "where can I get a good
dosa" at 1.365, and a second correct-but-weak case landed at 1.214. The entire
band between "correct but weak" and "wrong domain" is about **0.13** wide, so
`MAX_DISTANCE` cannot be tuned without re-running this.

*A near-miss can score better than the right answer.* Rule 70 beat the correct
Rule 215 at 0.567 against 0.634 — a distance that would pass any reasonable
confidence threshold. That is worse than a plain miss, because nothing about the
score looks wrong. A second instance appeared in the larger set: on one advance-
tax phrasing the wrong section scored 0.473 against the correct one's 0.504.
**And that pair only diverges on wording** — the same question phrased slightly
differently passes cleanly, which is why every case now records the exact query
its distance came from.

## Rebuild the chunks

```bash
python scripts/chunk.py chunks/
```

## How this was built

The design decisions here are mine — what to chunk on, where to put the
guardrail, what the eval set should test, when to trust a result. The code was
written with **Claude** as a pair programmer, and the debugging in particular
was collaborative: the four silent MCP failures above took a lot of back and
forth to isolate.

I am a finance professional, not a software engineer. Building this way is the
point rather than a caveat — the interesting question is no longer whether you
can write the code, it is whether you know what to build, can tell when it is
lying to you, and will measure it instead of trusting it.

## Status

Chunking, embedding, retrieval, local generation, guardrails, the MCP server,
the eval set and hybrid retrieval are all complete and verified end-to-end.

Known limitation: top-1 retrieval accuracy sits at **43%** on the 32-case set,
and hybrid retrieval improves ranking without clearly fixing top-1. The cause is
diagnosed above — the retriever prefers the general chunk over the specific one —
and the eval set is now tagged by failure class, so the next attempt can be
judged on whether it fixes that class rather than on an aggregate that hides the
trade.
