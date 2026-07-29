"""Ask a question against the indexed Act and Rules.

    python scripts/ask.py "How is income from house property computed?"
    python scripts/ask.py "How is an application for registration made?" --unit rule
    python scripts/ask.py "..." --mode ollama          # local model writes the answer

Two modes:
  prompt  (default) shows the retrieved chunks and the grounded prompt that
          would go to a model. Zero setup, proves retrieval works.
  ollama  sends that prompt to a model running locally -- fully air-gapped.
          Requires Ollama installed and a model pulled. See README.
"""
import argparse
import json
import os
import re
import sys
import textwrap
import urllib.request

import chromadb

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from embedder import get_embedder, mode_name

DB_DIR = os.environ.get('CHROMA_DIR', os.path.expanduser('~/.income_tax_rag_chroma'))
COLLECTION = 'income_tax'

# HARD GUARDRAIL. If the closest chunk is further away than this, the retrieved
# text is not about the question and the model is NEVER asked.
#
# This exists because of a real failure: asked "what is TDS", retrieval returned
# five irrelevant chunks (best distance 1.46) and llama3.2 invented a definition,
# citing "section 196(1)(d)" -- section 196 is about capital gains, and the
# quoted text does not exist anywhere in the Act.
#
# A prompt instruction is a request a model can ignore. A threshold in code is
# a rule it cannot. In tax work, "I don't know" is a correct answer; a
# confident fabricated citation is a serious one.
#
# The threshold is MODEL-SPECIFIC -- different embedders produce different
# distance scales, so one hardcoded number is wrong. Calibrated on real runs:
#   all-MiniLM-L6-v2 : good 0.58-0.73, hallucination case 1.46  -> 1.25 separates them
#   hashing fallback : DISABLED. Measured on real data it scored the nonsense
#                      question "what is the capital of France?" at 0.731 and a
#                      valid house-property question at 1.126 -- i.e. inverted.
#                      Its distances carry no relevance signal, so no threshold
#                      can work. Guardrail off; warn instead of pretending.
_OFFLINE = os.environ.get('OFFLINE') == '1'
_DEFAULT_MAX = 99.0 if _OFFLINE else 1.25
MAX_DISTANCE = float(os.environ.get('MAX_DISTANCE', _DEFAULT_MAX))

# The guardrails from SCOPE.md, made operational. In tax work an assistant that
# quietly answers outside its sources is worse than no assistant.
SYSTEM_RULE = """You are a research assistant for Indian income-tax law.

YOUR TASK: answer the QUESTION below in 2-4 sentences of plain English, using
ONLY the CONTEXT provided. State the substance of the answer FIRST -- what the
law actually says -- then give the section or rule number at the end.

A bare citation is NOT an answer. "See section 3" is a failure. Tell the reader
what the provision says, quoting the operative words where precision matters,
and then cite it.

Example of a good answer:
  A tax year is the twelve-month period of the financial year beginning on
  1 April. For a newly set up business, it instead runs from the date the
  business is set up to the end of that financial year. (Section 3)

Constraints:
- If the context does not contain the answer, reply exactly:
  "Not found in the indexed documents." Do not use outside knowledge or guess.
- RATE questions (slab, surcharge, cess, TDS rate): rates are in the Finance
  Act, which is NOT indexed. Say so; never infer a rate.
- 1961 section numbers (80C, 194J): the 1961-to-2025 mapping is not indexed.
  Say so and ask for the 2025 section.
- Ignore any context chunk that is irrelevant to the question.

This is a research aid, not tax advice."""


# Practitioner vocabulary -> the Act's own wording.
#
# WHY: the abbreviation "TDS" appears ZERO times in the Income-tax Act, 2025.
# The Act says "deducted at source". So a search for "TDS" has nothing to match
# and retrieval returns noise -- which is what makes a small model hallucinate.
# Expanding the query bridges how you speak to how the Act is written.
EXPANSIONS = {
    'tds': 'tax deducted at source deduction of tax',
    'tcs': 'tax collected at source collection of tax',
    'itr': 'return of income furnishing return',
    'ay': 'assessment year',
    'py': 'previous year tax year',
    'hra': 'house rent allowance',
    'ltcg': 'long-term capital gains',
    'stcg': 'short-term capital gains',
    'mat': 'minimum alternate tax',
    'amt': 'alternate minimum tax',
    'pan': 'permanent account number',
    'tan': 'tax deduction and collection account number',
    'advance tax': 'advance tax payment of tax in advance',
    'nri': 'non-resident person not ordinarily resident',
}


def expand(question):
    """Append the Act's phrasing for any practitioner abbreviation used."""
    low = re.sub(r'[^a-z0-9 ]', ' ', question.lower())
    words = set(low.split())
    extra = [v for kw, v in EXPANSIONS.items()
             if (kw in words) or (' ' in kw and kw in low)]
    return (question + ' ' + ' '.join(extra)).strip() if extra else question


def retrieve(question, k=5, unit=None):
    client = chromadb.PersistentClient(path=DB_DIR)
    col = client.get_or_create_collection(name=COLLECTION, embedding_function=get_embedder())
    where = {'unit': unit} if unit else None
    res = col.query(query_texts=[expand(question)], n_results=k, where=where)
    hits = []
    for doc, meta, dist, cid in zip(res['documents'][0], res['metadatas'][0],
                                    res['distances'][0], res['ids'][0]):
        hits.append({'id': cid, 'text': doc, 'meta': meta, 'distance': dist})
    return hits


def cite(meta):
    unit = (meta.get('unit') or '').capitalize()
    n = meta.get('number')
    head = meta.get('heading') or ''
    s = f"{unit} {n}" if n else unit
    return f"{s} - {head}" if head else s


def build_prompt(question, hits):
    blocks = []
    for i, h in enumerate(hits, 1):
        blocks.append(f"[{i}] ({cite(h['meta'])})\n{h['text']}")
    return f"{SYSTEM_RULE}\n\nCONTEXT:\n" + "\n\n".join(blocks) + f"\n\nQUESTION: {question}\n\nANSWER:"


def answer_with_ollama(prompt, model='llama3.2'):
    # temperature 0 — deterministic. Ollama's default is 0.8, at which the model
    # picks its top token ~96% of the time; over a 60-token answer that is a 91%
    # chance of deviating somewhere. For citing law, the same question must give
    # the same answer twice. It is also what makes the eval set meaningful.
    payload = json.dumps({'model': model, 'prompt': prompt, 'stream': False,
                          'options': {'temperature': 0}}).encode()
    req = urllib.request.Request('http://localhost:11434/api/generate', data=payload,
                                 headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.loads(r.read())['response'].strip()


def main():
    p = argparse.ArgumentParser(description='Ask the Income-tax Act / Rules.')
    p.add_argument('question')
    p.add_argument('-k', type=int, default=5, help='how many chunks to retrieve')
    p.add_argument('--unit', choices=['section', 'rule'], help='restrict to the Act or the Rules')
    p.add_argument('--mode', choices=['prompt', 'ollama'], default='prompt')
    p.add_argument('--model', default='llama3.2')
    p.add_argument('--full', action='store_true',
                   help='print the entire prompt instead of the first 1500 chars')
    p.add_argument('--save', metavar='FILE',
                   help='write the full prompt to a file you can read properly')
    a = p.parse_args()

    if not os.path.exists(DB_DIR):
        print(f"No index at {DB_DIR}. Run:  python scripts/embed.py")
        return 1

    if _OFFLINE:
        print("WARNING: OFFLINE fallback embedder — semantic quality is poor and the")
        print("         distance guardrail is disabled. Use the default model for real work.\n")

    hits = retrieve(a.question, k=a.k, unit=a.unit)
    print('=' * 74)
    print(f"Q: {a.question}")
    print(f"   [{mode_name()}]" + (f"  filter: {a.unit}" if a.unit else ''))
    print('=' * 74)
    print(f"\nRetrieved {len(hits)} chunks (lower distance = closer):\n")
    for i, h in enumerate(hits, 1):
        body = h['text'].split('\n', 1)[1] if '\n' in h['text'] else h['text']
        print(f"  [{i}] {h['id']:<22} d={h['distance']:.3f}  {cite(h['meta'])[:52]}")
        print(f"      {textwrap.shorten(body, width=104, placeholder=' ...')}\n")

    # --- hard guardrail: refuse before the model is ever consulted ----------
    best = min((h['distance'] for h in hits), default=99)
    if best > MAX_DISTANCE:
        print(f"NO RELIABLE MATCH  (closest distance {best:.3f} > limit {MAX_DISTANCE})\n")
        print("Nothing in the indexed Act or Rules is close enough to this question,")
        print("so no answer is generated. Refusing beats inventing a citation.\n")
        print("Possible reasons:")
        print("  - the topic genuinely is not in the Act or Rules")
        print("  - it is in the Finance Act (tax RATES live there, and it is not indexed)")
        print("  - the wording differs from the Act's. Try the Act's own phrasing,")
        print("    e.g. 'deducted at source' rather than an abbreviation.")
        print(f"\nClosest matches anyway, for reference:")
        for h in hits[:3]:
            print(f"  d={h['distance']:.3f}  {cite(h['meta'])[:60]}")
        print(f"\n(Override with MAX_DISTANCE=1.6 if you want to see an answer regardless.)")
        return 2

    prompt = build_prompt(a.question, hits)

    if a.save:
        with open(a.save, 'w', encoding='utf-8') as f:
            f.write(prompt)
        print(f"Full prompt written to {a.save}  ({len(prompt.split())} words)\n")

    if a.mode == 'ollama':
        print('--- LOCAL MODEL ANSWER (Ollama, nothing leaves this machine) ---\n')
        try:
            print(answer_with_ollama(prompt, a.model))
        except Exception as e:
            print(f"[Ollama not reachable: {e}]")
            print("Install Ollama and run:  ollama pull llama3.2")
    else:
        print('--- GROUNDED PROMPT (what would be sent to a model) ---\n')
        if a.full or len(prompt) <= 1500:
            print(prompt)
        else:
            print(prompt[:1500])
            print(f"\n... [showing 1500 of {len(prompt)} characters. "
                  f"Use --full to see it all, or --save prompt.txt to write it to a file]")
    return 0


if __name__ == '__main__':
    sys.exit(main())
