"""Load the chunks into a local Chroma database. Run this once.

    python scripts/embed.py

What happens: each chunk's text is turned into a vector (a list of numbers
representing its meaning) and stored on disk with its metadata. Nothing is
uploaded -- the embedding model runs on this machine.

The database lives in ~/.income_tax_rag_chroma by default, deliberately OUTSIDE
any cloud-synced folder. OneDrive/Dropbox lock SQLite files mid-sync and Chroma
throws "disk I/O error". Override with CHROMA_DIR if you want it elsewhere.
"""
import glob
import json
import os
import sys

import chromadb

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from embedder import get_embedder, mode_name

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHUNKS_DIR = os.path.join(HERE, 'chunks')
DB_DIR = os.environ.get('CHROMA_DIR', os.path.expanduser('~/.income_tax_rag_chroma'))
COLLECTION = 'income_tax'

# Whole-table chunks (is_full_table) are far longer than the embedding model's
# input limit, so their vector only reflects the opening portion -- which makes
# them poor retrieval targets that can crowd out the accurate per-part chunks.
# They stay in the JSONL for reading; they are not indexed by default.
INDEX_FULL_TABLES = os.environ.get('INDEX_FULL_TABLES') == '1'


def load_chunks():
    out = []
    for path in sorted(glob.glob(os.path.join(CHUNKS_DIR, '*.jsonl'))):
        with open(path, encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    out.append(json.loads(line))
    return out


def main():
    chunks = load_chunks()
    if not chunks:
        print(f"No chunks found in {CHUNKS_DIR}. Run scripts/chunk.py first.")
        return 1

    skipped = 0
    if not INDEX_FULL_TABLES:
        before = len(chunks)
        chunks = [c for c in chunks if not c.get('is_full_table')]
        skipped = before - len(chunks)

    print(f"Embedding mode : {mode_name()}")
    print(f"Chunks to index: {len(chunks)}" + (f"  (skipped {skipped} whole-table chunks)" if skipped else ""))
    print(f"Database       : {DB_DIR}")
    print("First run downloads a small model (~80MB), then works offline.\n")

    client = chromadb.PersistentClient(path=DB_DIR)
    try:
        client.delete_collection(COLLECTION)
    except Exception:
        pass
    col = client.get_or_create_collection(name=COLLECTION, embedding_function=get_embedder())

    # Chroma metadata values must be scalars, so keep it flat and filterable.
    ids, docs, metas = [], [], []
    for c in chunks:
        ids.append(c['id'])
        docs.append(c['text'])
        metas.append({
            'unit': c.get('unit') or '',
            'number': int(c.get('number') or 0),
            'heading': c.get('heading') or '',
            'chapter': c.get('chapter') or '',
            'part': int(c.get('part') or 0),
            'of_parts': int(c.get('of_parts') or 0),
            'source': c.get('source') or '',
        })

    batch = 200
    for i in range(0, len(ids), batch):
        col.add(ids=ids[i:i + batch], documents=docs[i:i + batch], metadatas=metas[i:i + batch])
        print(f"  indexed {min(i + batch, len(ids))}/{len(ids)}", flush=True)

    print(f"\nDone. {col.count()} chunks in collection '{COLLECTION}'.")
    print("Now ask it something:")
    print('  python scripts/ask.py "How is income from house property computed?"')
    return 0


if __name__ == '__main__':
    sys.exit(main())
