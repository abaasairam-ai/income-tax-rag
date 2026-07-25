# Income Tax RAG — source document checklist

Goal: a RAG that answers questions on the **Income-tax Act, 2025** and everything
around it, current up to **30 June 2026**.

Download the PDFs yourself from the official site and drop them into the folders
below. Keep the original filenames where sensible — knowing the notification
number and date later matters for citations.

> **Rule:** only official sources (incometaxindia.gov.in / egazette / PIB).
> Commentary sites are fine for *learning*, but never put them in the RAG — you
> want the RAG grounded in law, not someone's summary.

---

## Priority 1 — the core law (do these first)

### `01-act/` — the Act itself
- [ ] **Income-tax Act, 2025 (as amended by Finance Act, 2026)** — the full bare Act
      https://www.incometaxindia.gov.in/documents/d/guest/income_tax_act_2025_as_amended_by_fa_act_2026-pdf
- [ ] **Income-tax Act, 2025 — original as enacted** (useful for comparison)
      https://www.incometaxindia.gov.in/Documents/Act/Income-tax-Act-2025.pdf
- [ ] **The Schedules to the Act** (16 schedules) — check whether these are inside
      the main PDF or published separately. If separate, grab them.

536 sections · 23 chapters · 16 schedules · in force from 1 April 2026.

### `05-finance-act/` — where the RATES live
- [ ] **Finance Act, 2026** — especially the **First Schedule** (slab rates,
      surcharge, cess, TDS rates). **The Act does not contain the rates.** Without
      this your RAG cannot answer "what's the tax rate."
      Find under Acts: https://www.incometaxindia.gov.in/pages/acts/finance-act.aspx
- [ ] Explanatory Memorandum to the Finance Act, 2026 (if published)

### `02-rules/` — the procedural framework
- [ ] **Income-tax Rules, 2026** — notified by **Notification No. 22/2026 dated
      20 March 2026**, effective 1 April 2026. (Note: "Rules 2026", not 2025.)
      Verify the notification number on the official site before relying on it.
      Rules section: https://www.incometaxindia.gov.in/pages/rules/income-tax-rules.aspx
      Or via notifications list: https://www.incometaxindia.gov.in/notifications
- [ ] Any amendments to the Rules issued up to 30 June 2026

---

## Priority 2 — what makes it actually usable

### `06-mapping-and-faqs/` — the highest-value "extra"
- [ ] **Navigator: Section mapping 1961 → 2025** (official CBDT)
      https://www.incometaxindia.gov.in/documents/20117/43138/new-income-tax-bill-2025-navigator.pdf/8df3eecc-8a0d-e28d-85c7-4db6310a52dd?t=1753871049741
      *Why this matters most:* every real question is asked in OLD language —
      "80C", "194J", "section 10(13A)". Without the mapping your RAG returns
      nothing for the vocabulary people actually use. This one document makes
      your assistant feel smart.
- [ ] **Form Mapping Guide (1961 forms → 2025 forms)** — official
      https://www.incometax.gov.in/iec/foportal/sites/default/files/2026-03/Guide%20to%20IT%20Act%202025%20forms.pdf
- [ ] **CBDT FAQs / explanatory notes on the new Act** — already written as Q&A,
      which retrieves beautifully. Find via the Act landing page below.

### `03-notifications/` — statutory, up to 30 June 2026
- [ ] CBDT notifications issued under the 2025 Act
      https://www.incometaxindia.gov.in/notifications
      Save as: `notification-<no>-<yyyy-mm-dd>-<short-topic>.pdf`

### `04-circulars/` — departmental clarifications, up to 30 June 2026
- [ ] CBDT circulars issued under the 2025 Act
      Save as: `circular-<no>-<yyyy-mm-dd>-<short-topic>.pdf`
      *Remember:* circulars bind the Department, not the taxpayer. Worth noting
      in the RAG's answers later.

---

## Priority 3 — only if you want form-level answers
- [ ] ITR forms notified under the new Act
- [ ] TDS/TCS forms and certificates
- [ ] CBDT Instructions to officers (lowest priority — internal admin)

---

## Folder layout

```
income tax rag/
├── 00-DOWNLOAD-CHECKLIST.md   <- this file
├── source-pdfs/               <- original PDFs, untouched, as downloaded
│   ├── 01-act/
│   ├── 02-rules/
│   ├── 03-notifications/
│   ├── 04-circulars/
│   ├── 05-finance-act/
│   └── 06-mapping-and-faqs/
└── docs-text/                 <- extracted plain text (what the RAG reads)
```

**Why two folders:** keep the PDFs pristine as your source of truth, and work
from extracted text. If chunking goes wrong, you re-extract — you never lose
the original.

---

## Before you extract text — check one thing

Open a PDF and try to **select text with your mouse**.
- Text highlights → good, it's a real text PDF, extraction will work.
- Nothing highlights → it's a scanned image; it needs OCR first. (Official
  CBDT PDFs are usually real text, so this should be fine.)

---

## A note on size (read before chunking)

The Act alone is several hundred pages. That's *good* for a RAG — it's exactly
the kind of document nobody wants to Ctrl+F — but it means chunking strategy
matters more than in a toy project.

The natural cut for an Act is **by section**, not every N words, so that
"what does section 22 say" returns one whole, self-contained section. We'll
work through that together at the chunking stage.

---

## All links in one place

**Start here (main landing pages):**
- Act 2025 hub — https://www.incometaxindia.gov.in/income-tax-act-2025
- Notifications — https://www.incometaxindia.gov.in/notifications
- Circulars — https://www.incometaxindia.gov.in/pages/communications/circulars.aspx
- Rules — https://www.incometaxindia.gov.in/pages/rules/income-tax-rules.aspx
- Finance Acts — https://www.incometaxindia.gov.in/pages/acts/finance-act.aspx

**Direct PDFs:**
| Doc | Link | Status |
|---|---|---|
| Act 2025 (as amended by FA 2026) | https://www.incometaxindia.gov.in/documents/d/guest/income_tax_act_2025_as_amended_by_fa_act_2026-pdf | verified live |
| Act 2025 (original as enacted) | https://www.incometaxindia.gov.in/Documents/Act/Income-tax-Act-2025.pdf | listed; try in browser |
| Navigator — section mapping 1961→2025 | https://www.incometaxindia.gov.in/documents/20117/43138/new-income-tax-bill-2025-navigator.pdf/8df3eecc-8a0d-e28d-85c7-4db6310a52dd?t=1753871049741 | official |
| Form Mapping Guide 1961→2025 | https://www.incometax.gov.in/iec/foportal/sites/default/files/2026-03/Guide%20to%20IT%20Act%202025%20forms.pdf | official |

For notifications & circulars: filter the list pages by date, take everything
up to **30 June 2026** that relates to the 2025 Act, and save each with its
number and date in the filename.

---

## Status

- [ ] All Priority 1 downloaded
- [ ] All Priority 2 downloaded
- [ ] Checked which PDFs are text vs scanned
- [ ] Ready to start Stage 1 (chunking)
