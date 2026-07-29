"""Sanity check before wiring the MCP server into Claude Desktop.

    python scripts/check_db.py

Answers one question: can this code reach the real index, and how many chunks
are in it? Run this FIRST. If retrieval is broken, find out here -- where the
error is printed plainly -- not through an MCP server that fails silently.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import chromadb
from ask import DB_DIR, COLLECTION, retrieve, cite, MAX_DISTANCE
from embedder import get_embedder, mode_name

print(f"db dir       : {DB_DIR}")
print(f"exists       : {os.path.isdir(DB_DIR)}")
print(f"embedder     : {mode_name()}")
print(f"max distance : {MAX_DISTANCE}")

client = chromadb.PersistentClient(path=DB_DIR)
col = client.get_or_create_collection(name=COLLECTION, embedding_function=get_embedder())
count = col.count()
print(f"chunks       : {count}")

if count == 0:
    print("\nEMPTY. Chroma created a new database instead of opening yours.")
    print("Almost always a path problem, not an index problem.")
    print("Fix: set CHROMA_DIR to the real folder and run again.")
    sys.exit(1)

print("\n--- test query: 'what is a tax year' ---")
hits = retrieve("what is a tax year", k=3)
for h in hits:
    print(f"  {h['distance']:.3f}  {cite(h['meta'])}")

best = min(h['distance'] for h in hits)
print(f"\nbest distance {best:.3f} vs limit {MAX_DISTANCE}"
      f" -> {'PASS' if best <= MAX_DISTANCE else 'would be REFUSED'}")
