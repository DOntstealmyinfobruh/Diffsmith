"""Text embedders used to build the FAISS index.

Two backends:
- SentenceTransformerEmbedder: a small local model (default all-MiniLM-L6-v2).
  Free, runs offline after the first download. Install with
  `pip install diffsmith[local-embeddings]`.
- HashingEmbedder: no dependencies, no download. Splits code identifiers
  (snake_case, camelCase) into words and hashes them into a fixed-size vector.
  Weaker on paraphrase, but fast and fully deterministic, which makes it the
  backend used by the test suite.
"""

from __future__ import annotations

import hashlib
import logging
import re
from typing import Protocol

import numpy as np

log = logging.getLogger(__name__)


class Embedder(Protocol):
    name: str
    dim: int

    def embed(self, texts: list[str]) -> np.ndarray:
        """Return an (n, dim) float32 array of L2-normalized vectors."""
        ...


_WORD = re.compile(r"[A-Z]+(?![a-z])|[A-Z]?[a-z]+|\d+")
_STOP = {
    "the", "a", "an", "and", "or", "to", "of", "in", "for", "on", "is", "it",
    "that", "this", "with", "as", "be", "by", "so", "make", "add", "should",
    "self", "def", "return", "import", "from", "if", "else", "none", "true", "false",
}


def tokenize(text: str) -> list[str]:
    """Split text and identifiers into lowercase words (getUserName -> get, user, name)."""
    words = []
    for raw in re.split(r"[^A-Za-z0-9]+", text):
        for w in _WORD.findall(raw):
            w = w.lower()
            if len(w) > 1 and w not in _STOP:
                words.append(w)
    return words


def _normalize(mat: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(mat, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return (mat / norms).astype("float32")


class HashingEmbedder:
    def __init__(self, dim: int = 1024):
        self.dim = dim
        self.name = f"hashing-{dim}"

    def _bucket(self, token: str) -> tuple[int, float]:
        h = int.from_bytes(hashlib.blake2b(token.encode(), digest_size=8).digest(), "little")
        return h % self.dim, (1.0 if (h >> 63) & 1 else -1.0)

    def embed(self, texts: list[str]) -> np.ndarray:
        mat = np.zeros((len(texts), self.dim), dtype="float32")
        for i, text in enumerate(texts):
            words = tokenize(text)
            # unigrams plus adjacent pairs, sublinear term weighting
            feats: dict[str, int] = {}
            for w in words:
                feats[w] = feats.get(w, 0) + 1
            for a, b in zip(words, words[1:]):
                key = f"{a}_{b}"
                feats[key] = feats.get(key, 0) + 1
            for tok, count in feats.items():
                idx, sign = self._bucket(tok)
                mat[i, idx] += sign * (1.0 + np.log(count))
        return _normalize(mat)


class SentenceTransformerEmbedder:
    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        from sentence_transformers import SentenceTransformer  # optional dependency

        self._model = SentenceTransformer(model_name)
        self.dim = int(self._model.get_sentence_embedding_dimension())
        self.name = f"st-{model_name}"

    def embed(self, texts: list[str]) -> np.ndarray:
        vecs = self._model.encode(texts, batch_size=64, show_progress_bar=False)
        return _normalize(np.asarray(vecs, dtype="float32"))


def make_embedder(kind: str = "auto", model_name: str = "all-MiniLM-L6-v2") -> Embedder:
    if kind == "hashing":
        return HashingEmbedder()
    if kind in ("auto", "local", "sentence-transformers"):
        try:
            return SentenceTransformerEmbedder(model_name)
        except Exception as exc:  # not installed, or model download blocked
            if kind != "auto":
                raise
            log.warning("Local embedding model unavailable (%s); using hashing embedder.", exc)
            return HashingEmbedder()
    raise ValueError(f"Unknown embedder: {kind}")
