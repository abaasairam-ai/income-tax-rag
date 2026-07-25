# Scope & coverage — what this RAG does and does NOT know

Keep this honest and keep it visible. In tax work, an assistant that quietly
answers outside its sources is worse than no assistant.

## Currently indexed

| Document | Version / date | Coverage |
|---|---|---|
| **Income-tax Act, 2025** [30 of 2025] | as amended by Finance Act, 2026; downloaded 10 Jun 2026 | COMPLETE — 23 chapters, sections 1–536 |
| **Income-tax Rules, 2026** | G.S.R. 198(E) dated 20-3-2026; downloaded 22 Jun 2026 | COMPLETE — 422 pages |

Both in force from **1 April 2026** (applies from FY 2026-27).

## NOT indexed — the gaps that matter

- **Circulars** — not included. Too many to collect individually; deferred.
- **Notifications** — not included, beyond the one notifying the Rules itself.
- **Finance Act, 2026** — not included. **This is the significant one: the Act
  does not contain tax rates.** Slabs, surcharge, cess and TDS rates live in the
  Finance Act's First Schedule. The RAG therefore *cannot* answer rate questions.
- **Section mapping 1961 → 2025** — not included. Questions phrased in old
  section numbers ("80C", "194J") will not retrieve well.
- **Forms** (ITR / TDS) — not included.
- Case law, commentary, departmental instructions — out of scope by design.

Everything is current **up to 30 June 2026**. Anything issued after that is unknown.

---

## Disclaimer to display on screen

Show this in the app, above or beside the answer box:

> **Sources:** Income-tax Act, 2025 (as amended by Finance Act, 2026) and
> Income-tax Rules, 2026 — complete, current to 30 June 2026.
>
> **Not included:** circulars, notifications, the Finance Act 2026 (so **tax
> rates are not covered**), 1961→2025 section mapping, and forms.
>
> Answers are drawn only from the indexed documents and cite the section they
> come from. If the answer is not in those documents the assistant will say so
> rather than guess. This is a research aid, not tax advice — verify against the
> official text before relying on it.

## Rules for answering (build these into the prompt)

1. Answer **only** from retrieved text; otherwise say "Not found in the indexed documents."
2. Always cite the section or rule number.
3. If asked about a **rate**, state that rates are in the Finance Act, which is
   not indexed — do not infer a rate from the Act.
4. If asked using a **1961 section number**, say the mapping is not indexed and
   ask for the 2025 section, rather than guessing an equivalent.
