"""Measure retrieval quality against eval_set.jsonl.

    python evals/run_eval.py
    python evals/run_eval.py --k 10
    python evals/run_eval.py --save        # writes results-<date>.json for comparison

WHAT THIS MEASURES, AND WHAT IT DELIBERATELY DOES NOT
  It measures RETRIEVAL only -- did the right provision come back, and at what
  rank. It does not judge the wording of any answer.

  That is not a shortcut, it is the point. Under MCP the server generates
  nothing; Claude writes the answer from whatever chunks this returns. So
  retrieval is the only part that can fail here, and it is the only part worth
  a score. An eval that grades prose would be grading the model, not the system.

THE METRICS
  hit@1   the right provision ranked first. The number that matters most --
          a user reads the top result.
  hit@3   it was in the top three. Tolerable: the model sees it.
  hit@5   it was retrieved at all within k.
  MRR     mean reciprocal rank. 1.0 = always first, 0.5 = typically second,
          0.33 = typically third. One number that captures ordering, unlike
          hit@k which is blind to whether you scraped in at rank 5.

  Ranking is scored separately from finding, because today's known weakness is
  ordering: "what is TDS" retrieves section 390 but puts it fifth.

REFUSAL CASES
  Entries with "expect_refusal": true must have their closest chunk fall BEYOND
  MAX_DISTANCE, so the guardrail fires. These fail loudly if the threshold is
  ever loosened -- which is exactly when you would want to know.

WHEN A CASE FAILS
  Check the test before the system. An eval failure can mean the expected
  citation was wrong, not that retrieval broke.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'scripts'))

from ask import retrieve, cite, MAX_DISTANCE  # noqa: E402
from embedder import mode_name  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
EVAL_SET = os.path.join(HERE, 'eval_set.jsonl')


def load_cases(path):
    cases = []
    with open(path, encoding='utf-8') as f:
        for line_no, line in enumerate(f, 1):
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            try:
                cases.append(json.loads(line))
            except json.JSONDecodeError as e:
                print(f"  skipping line {line_no}: {e}")
    return cases


def rank_of_expected(hits, expected):
    """1-based rank of the first hit whose citation contains any expected
    string. 0 means not found. Matching is substring on a lowercased citation,
    so "section 3" matches "Section 3 - Definition of tax year" but also
    "Section 35" -- so expectations are compared against the number token too."""
    for i, h in enumerate(hits, 1):
        c = cite(h['meta']).lower()
        number = str(h['meta'].get('number') or '').lower()
        unit = str(h['meta'].get('unit') or '').lower()
        exact = f"{unit} {number}".strip()
        for want in expected:
            w = want.lower().strip()
            if w == exact or w == number or (w in c and w == exact):
                return i
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--k', type=int, default=5)
    ap.add_argument('--save', action='store_true')
    args = ap.parse_args()

    cases = load_cases(EVAL_SET)
    print(f"eval set : {len(cases)} cases")
    print(f"embedder : {mode_name()}")
    print(f"k        : {args.k}")
    print(f"max dist : {MAX_DISTANCE}\n")

    retrieval, refusal, results = [], [], []

    for c in cases:
        hits = retrieve(c['question'], k=args.k)
        best = min((h['distance'] for h in hits), default=99.0)
        row = {'id': c['id'], 'question': c['question'], 'best_distance': round(best, 3)}

        if c.get('expect_refusal'):
            refused = best > MAX_DISTANCE
            row.update(kind='refusal', passed=refused)
            refusal.append(refused)
            mark = 'PASS' if refused else 'FAIL'
            note = '' if refused else '  <- guardrail did NOT fire'
            print(f"  [{mark}] {c['id']:<24} best {best:.3f}{note}")
        else:
            rank = rank_of_expected(hits, c['expect'])
            row.update(kind='retrieval', rank=rank, expect=c['expect'])
            retrieval.append(rank)
            if rank == 1:
                mark = 'PASS'
            elif rank:
                mark = f"rank{rank}"
            else:
                mark = 'MISS'
            top = cite(hits[0]['meta']) if hits else '-'
            print(f"  [{mark:<6}] {c['id']:<24} best {best:.3f}  top: {top[:44]}")

        results.append(row)

    n = len(retrieval)
    if n:
        hit1 = sum(1 for r in retrieval if r == 1) / n
        hit3 = sum(1 for r in retrieval if 1 <= r <= 3) / n
        hit5 = sum(1 for r in retrieval if 1 <= r <= args.k) / n
        mrr = sum((1 / r if r else 0) for r in retrieval) / n
        print(f"\n  retrieval cases : {n}")
        print(f"  hit@1           : {hit1:.0%}")
        print(f"  hit@3           : {hit3:.0%}")
        print(f"  hit@{args.k}           : {hit5:.0%}")
        print(f"  MRR             : {mrr:.3f}")

    if refusal:
        print(f"\n  refusal cases   : {len(refusal)}")
        print(f"  guardrail fired : {sum(refusal)}/{len(refusal)}")

    if args.save:
        import datetime
        out = os.path.join(HERE, f"results-{datetime.date.today()}.json")
        with open(out, 'w', encoding='utf-8') as f:
            json.dump({'k': args.k, 'max_distance': MAX_DISTANCE,
                       'embedder': mode_name(), 'results': results}, f, indent=2)
        print(f"\n  saved: {out}")

    print("\nA failure may mean the expected citation is wrong, not the system.")


if __name__ == '__main__':
    main()
