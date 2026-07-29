"""Hybrid retrieval -- a keyword leg (BM25) fused with the existing semantic leg.

WHY THIS EXISTS
---------------
Semantic search alone ranks *procedural phrasing* above *substantive meaning*.
Two measured failures, same cause:

  1. "what certificate must a deductor issue"
     -> Rule 70  "Form of certificate to be furnished under section 151(5)"   0.567
     -> Rule 215 "Certificate of tax deducted or collected at source ..."     0.634
     Rule 70 is an assessee's own deduction claim under s.151. Wrong rule, and
     it won because both HEADINGS share the words "form of certificate to be
     furnished". The embedder matched phrasing, not who does what to whom.

  2. "what is TDS" -> section 390 ranks 5th, topped by Rule 215 both times.
     Procedural rules beat the charging section.

A keyword leg fixes both, because the words that disambiguate are sitting right
there in the heading: Rule 215's title literally contains "tax deducted or
collected at source". Semantic search averaged that away; BM25 cannot.

THE ONE DESIGN DECISION WORTH KNOWING
-------------------------------------
The heading is indexed ALONGSIDE the body text (see _corpus below). That is the
whole fix for case 1. Indexing body text only would leave Rule 215 looking much
like every other procedural rule.

WHY RRF AND NOT A WEIGHTED BLEND
--------------------------------
A Chroma distance of 0.567 and a BM25 score of 12.3 are not on the same scale,
have no shared zero, and no fixed range. Blending them needs an invented weight
that would then need tuning against the eval set -- and the eval set only has 12
cases, so it would be tuned to noise. Reciprocal Rank Fusion throws the scores
away and uses only POSITION, so there is nothing to tune.

THE GUARDRAIL SURVIVES UNCHANGED
--------------------------------
All three callers (ask.py, mcp_server.py, check_db.py) test
`min(h['distance'] for h in hits) > MAX_DISTANCE`. That is a min over the whole
returned set, so reordering cannot affect it. Two rules keep it exactly as
measured on 29 Jul (correct answer 1.219, off-topic 1.365 -- a 0.15 band, with
no room to be casual):

  * BM25-only hits carry distance 99.0, a sentinel. min() ignores them, so a
    keyword match can never make an off-topic question look relevant.
  * The semantic top-1 is ALWAYS force-included in the output, so the value
    min() sees is identical to what it would have been without fusion.

Net effect: the keyword leg can only improve ORDERING. It can never rescue a
question that the semantic guardrail would have refused.
"""

import os
import re

import chromadb

from embedder import get_embedder

# Fetch this many from each leg before fusing. Fusion needs material to work
# with -- asking each leg for only k gives them almost nothing to disagree about.
POOL = int(os.environ.get('HYBRID_POOL', 25))

# RRF's damping constant. 60 is the value from the original Cormack et al.
# paper and is not sensitive -- anything 10-100 behaves much the same. It exists
# to stop rank 1 dominating rank 2 by a factor of 2.
RRF_K = 60

# Sentinel distance for a chunk found by keywords but not by meaning. Chosen to
# be far above any real distance so min() in the guardrail always ignores it.
NO_SEMANTIC_DISTANCE = 99.0

_CACHE = None  # built once per process; ~1,420 chunks is small enough to hold


def _tokenize(text):
    """Lowercase alphanumeric words. Deliberately crude -- no stemming.

    Statutory language is already highly regular ("deducted", "deduction" and
    "deductor" genuinely differ in meaning here), so stemming them together
    would undo the precision this leg exists to provide.
    """
    return re.findall(r'[a-z0-9]+', text.lower())


def _corpus(db_dir, collection):
    """Pull every chunk out of Chroma once and build the BM25 index over it.

    Reads from Chroma rather than re-reading chunks/*.jsonl so there is one
    source of truth -- if the index is rebuilt, this follows automatically and
    cannot drift out of sync with what semantic search is actually searching.
    """
    global _CACHE
    if _CACHE is not None:
        return _CACHE

    from rank_bm25 import BM25Okapi  # imported late so ask.py works without it

    client = chromadb.PersistentClient(path=db_dir)
    col = client.get_or_create_collection(
        name=collection, embedding_function=get_embedder())
    got = col.get(include=['documents', 'metadatas'])

    docs = got['documents']
    metas = got['metadatas']
    ids = got['ids']

    # Heading first, then body. See the module docstring -- this line is the fix.
    blobs = []
    for doc, meta in zip(docs, metas):
        heading = (meta or {}).get('heading') or ''
        unit = (meta or {}).get('unit') or ''
        number = (meta or {}).get('number')
        head = f"{unit} {number} {heading}" if number else f"{unit} {heading}"
        blobs.append(f"{head} {head} {doc}")  # heading twice = modest weighting

    _CACHE = {
        'ids': ids,
        'docs': docs,
        'metas': metas,
        'bm25': BM25Okapi([_tokenize(b) for b in blobs]),
    }
    return _CACHE


def keyword_hits(question, k, unit, db_dir, collection):
    """Top-k chunks by literal word overlap, in the same shape retrieve() returns."""
    corpus = _corpus(db_dir, collection)
    scores = corpus['bm25'].get_scores(_tokenize(question))

    order = sorted(range(len(scores)), key=lambda i: -scores[i])
    out = []
    for i in order:
        if scores[i] <= 0:
            break  # no shared words at all -- everything below this is noise
        meta = corpus['metas'][i] or {}
        if unit and meta.get('unit') != unit:
            continue
        out.append({
            'id': corpus['ids'][i],
            'text': corpus['docs'][i],
            'meta': meta,
            'distance': NO_SEMANTIC_DISTANCE,
            'bm25': float(scores[i]),
        })
        if len(out) >= k:
            break
    return out


def fuse(semantic, keyword, k=5):
    """Reciprocal Rank Fusion. Uses rank position only; scores are discarded."""
    points = {}
    best = {}

    for leg in (semantic, keyword):
        for rank, hit in enumerate(leg, start=1):
            hid = hit['id']
            points[hid] = points.get(hid, 0.0) + 1.0 / (RRF_K + rank)
            # Keep whichever copy has the real semantic distance. The keyword
            # leg's copy carries the 99.0 sentinel, so "lower wins" is correct.
            if hid not in best or hit['distance'] < best[hid]['distance']:
                best[hid] = dict(hit)

    ranked = sorted(points, key=lambda h: -points[h])
    out = [best[h] for h in ranked[:k]]

    # Guarantee the semantic top-1 is present, so the guardrail's min() sees
    # exactly the distance it would have seen without fusion. Without this, a
    # strongly-keyworded question could push the best semantic hit out of the
    # top k and make a valid question look like it failed the threshold.
    if semantic:
        top = semantic[0]
        if all(h['id'] != top['id'] for h in out):
            out = [dict(top)] + out[:k - 1]

    for i, hit in enumerate(out, start=1):
        hit['rrf_rank'] = i
    return out
