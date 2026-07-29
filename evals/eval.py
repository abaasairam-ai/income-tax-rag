"""
Measure how good the retrieval actually is.

    python evals/eval.py
    python evals/eval.py --k 10          # more generous
    python evals/eval.py --no-expansion  # A/B test: does query expansion help?

WHY THIS EXISTS
    Twice now, sound reasoning about retrieval turned out to be wrong when
    measured. Without a test set you are changing things and hoping.

WHAT IT MEASURES
    Hit@1   the correct section was the TOP result
    Hit@3   it was somewhere in the top 3
    Hit@5   it was somewhere in the top 5
    MRR     mean reciprocal rank -- 1.0 if always first, 0.5 if always second,
            0.33 if always third. One number for "how high up is it usually".
    Refusal on out-of-scope questions, did the guardrail correctly refuse?

    Retrieval is measured, not answer wording. Either the right section came
    back or it did not -- no judgement call.
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, 'scripts'))

import chromadb                                    # noqa: E402
from embedder import get_embedder, mode_name       # noqa: E402
import ask as A                                    # noqa: E402


def retrieve(question, k, expand):
    client = chromadb.PersistentClient(path=A.DB_DIR)
    col = client.get_or_create_collection(name=A.COLLECTION,
                                          embedding_function=get_embedder())
    q = A.expand(question) if expand else question
    res = col.query(query_texts=[q], n_results=k)
    return [{'unit': m.get('unit'), 'number': m.get('number'),
             'heading': m.get('heading'), 'distance': d}
            for m, d in zip(res['metadatas'][0], res['distances'][0])]


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--k', type=int, default=5)
    p.add_argument('--no-expansion', action='store_true')
    p.add_argument('--verbose', action='store_true')
    a = p.parse_args()
    expand = not a.no_expansion

    data = json.load(open(os.path.join(HERE, 'eval_set.json'), encoding='utf-8'))

    print('=' * 74)
    print('RETRIEVAL EVAL')
    print('=' * 74)
    print(f"embedder        : {mode_name()}")
    print(f"top-k           : {a.k}")
    print(f"query expansion : {'ON' if expand else 'OFF'}")
    print(f"refusal limit   : distance > {A.MAX_DISTANCE}\n")

    hits = {1: 0, 3: 0, 5: 0}
    rr_total = 0.0
    failures = []
    cases = data['in_scope']

    for c in cases:
        got = retrieve(c['q'], max(a.k, 5), expand)
        # "expect" may be a single number or a list of acceptable answers.
        # An eval failure sometimes means the TEST is wrong, not the system --
        # e.g. a question answerable from either a section or its rule.
        want = c['expect'] if isinstance(c['expect'], list) else [c['expect']]
        units = c['unit'] if isinstance(c['unit'], list) else [c['unit']] * len(want)
        pairs = set(zip(units, want))
        rank = None
        for i, g in enumerate(got, start=1):
            if (g['unit'], g['number']) in pairs:
                rank = i
                break
        if rank:
            rr_total += 1 / rank
            for n in (1, 3, 5):
                if rank <= n:
                    hits[n] += 1
        else:
            failures.append((c, got))

        mark = f"#{rank}" if rank else "MISS"
        flag = '  ' if rank == 1 else ('~ ' if rank else 'X ')
        exp = f"{c['unit'] if isinstance(c['unit'],str) else '/'.join(c['unit'])} {c['expect']}"
        print(f" {flag}{mark:<5} expected {exp:<18} | {c['q'][:48]}")
        if a.verbose and rank != 1:
            for g in got[:3]:
                print(f"          got: {g['unit']} {g['number']} d={g['distance']:.3f} "
                      f"{str(g['heading'])[:40]}")

    n = len(cases)
    print('\n' + '-' * 74)
    print(f"  Hit@1  {hits[1]:>2}/{n}  = {hits[1]/n:6.1%}   correct section was the top result")
    print(f"  Hit@3  {hits[3]:>2}/{n}  = {hits[3]/n:6.1%}   in the top 3")
    print(f"  Hit@5  {hits[5]:>2}/{n}  = {hits[5]/n:6.1%}   in the top 5")
    print(f"  MRR          = {rr_total/n:6.3f}   1.0 = always first")

    # ---- out-of-scope: should the guardrail refuse? ----
    print('\n' + '=' * 74)
    print('OUT OF SCOPE — the guardrail should refuse these')
    print('=' * 74)
    refused = 0
    for c in data['out_of_scope']:
        got = retrieve(c['q'], 5, expand)
        best = min(g['distance'] for g in got)
        ok = best > A.MAX_DISTANCE
        refused += ok
        print(f"  {'REFUSED ' if ok else 'ANSWERED'}  best d={best:.3f}  | {c['q'][:46]}")
        if not ok:
            print(f"            should refuse: {c['why']}")
    m = len(data['out_of_scope'])
    print(f"\n  Correctly refused {refused}/{m} = {refused/m:.0%}")

    if failures:
        print('\n' + '=' * 74)
        print('FAILURES — worth reading, this is where to improve')
        print('=' * 74)
        for c, got in failures:
            print(f"\n  Q: {c['q']}")
            print(f"     wanted {c['unit']} {c['expect']}, got:")
            for g in got[:3]:
                print(f"       {g['unit']} {g['number']:<4} d={g['distance']:.3f}  "
                      f"{str(g['heading'])[:46]}")

    print('\n' + '=' * 74)
    print("Re-run after ANY change to chunking, embedding or expansion.")
    print("If the numbers go down, the change was bad — regardless of how")
    print("sensible it sounded. That is the whole point.")
    print('=' * 74)


if __name__ == '__main__':
    main()
