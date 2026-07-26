"""Embedding function used by both embed.py and ask.py.

TWO MODES — and the choice matters:

  default   Chroma's built-in model (all-MiniLM-L6-v2). Downloads once (~80MB),
            then works offline forever. Real semantic search: "what happens if
            I pay a vendor late" can find the 180-day rule without sharing a
            single keyword.

  OFFLINE=1 A built-in word-hashing embedder. No download, no network, works on
            a locked-down machine. But it is keyword-ish, NOT semantic -- it
            matches words, not meaning. Use it to prove the pipeline runs;
            switch to the default for real answers.

Either way the documents never leave the machine.
"""
import hashlib
import math
import os
import re

OFFLINE = os.environ.get('OFFLINE') == '1'


class HashingEmbeddingFunction:
    """Zero-dependency fallback: bag-of-words via the hashing trick.

    Each word is hashed into one of `dim` buckets and counted, then the vector
    is L2-normalised so distances behave. No model, no download, no network.
    """

    def __init__(self, dim=512):
        self.dim = dim

    def name(self):
        return 'hashing-bow-512'

    def _one(self, text):
        vec = [0.0] * self.dim
        for word in re.findall(r'[a-z0-9]+', text.lower()):
            h = int(hashlib.md5(word.encode()).hexdigest(), 16)
            vec[h % self.dim] += 1.0
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]

    def __call__(self, input):
        if isinstance(input, str):
            input = [input]
        return [self._one(t) for t in input]

    # chromadb 1.x calls these names explicitly
    def embed_documents(self, input):
        return self.__call__(input)

    def embed_query(self, input):
        return self.__call__(input)


def get_embedder():
    """None means 'use Chroma's default model'."""
    return HashingEmbeddingFunction() if OFFLINE else None


def mode_name():
    return 'OFFLINE word-hashing (keyword-ish)' if OFFLINE else 'all-MiniLM-L6-v2 (semantic)'
