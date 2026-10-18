"""Code search: chunk files, embed the chunks, store them in FAISS.

The index is cached in .git/diffsmith and updated incrementally: on each run
only files whose content changed are re-embedded, so large repositories
(10,000+ files) are embedded once and then stay cheap to refresh.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

import faiss
import numpy as np

from .embeddings import Embedder, tokenize
from .gitops import GitRepo

log = logging.getLogger(__name__)

SKIP_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg", ".webp", ".pdf", ".zip", ".gz",
    ".tar", ".whl", ".so", ".dll", ".dylib", ".exe", ".bin", ".pyc", ".lock", ".min.js",
    ".woff", ".woff2", ".ttf", ".eot", ".mp3", ".mp4", ".mov", ".db", ".sqlite",
}
PATH_BONUS = 0.3  # extra score when request words appear in the file path
SKIP_NAMES = {"package-lock.json", "yarn.lock", "poetry.lock", "uv.lock", "Cargo.lock"}


@dataclass
class Chunk:
    path: str
    start: int  # 1-based line number
    end: int
    text: str


@dataclass
class FileHit:
    path: str
    score: float


_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]{2,}")


def keyword_terms(text: str) -> list[str]:
    """Words for keyword search: split words plus whole identifiers (from_str, getUser)."""
    terms = [t for t in tokenize(text) if not t.isdigit()]  # bare numbers are noise
    terms += [m.lower() for m in _IDENT.findall(text)
              if "_" in m.strip("_") or any(c.isupper() for c in m[1:])]
    return terms


class BM25:
    """Classic Okapi BM25 over chunks. Rare words count for much more than common ones."""

    def __init__(self, docs: list[list[str]], k1: float = 1.2, b: float = 0.75):
        self.k1, self.b = k1, b
        self.postings: dict[str, list[tuple[int, int]]] = defaultdict(list)
        self.lengths = [len(d) for d in docs]
        self.avg_len = (sum(self.lengths) / len(docs)) if docs else 1.0
        for i, doc in enumerate(docs):
            for term, tf in Counter(doc).items():
                self.postings[term].append((i, tf))
        self.n = len(docs)

    def scores(self, query_terms: list[str]) -> dict[int, float]:
        out: dict[int, float] = defaultdict(float)
        for term in set(query_terms):
            posting = self.postings.get(term)
            if not posting:
                continue
            idf = math.log(1 + (self.n - len(posting) + 0.5) / (len(posting) + 0.5))
            for doc, tf in posting:
                norm = tf + self.k1 * (1 - self.b + self.b * self.lengths[doc] / self.avg_len)
                out[doc] += idf * tf * (self.k1 + 1) / norm
        return out


def _sha(data: bytes) -> str:
    return hashlib.sha1(data).hexdigest()


def is_indexable(path: str, data: bytes, max_bytes: int) -> bool:
    name = Path(path).name
    if name in SKIP_NAMES or any(name.endswith(ext) for ext in SKIP_EXTENSIONS):
        return False
    if len(data) > max_bytes or b"\0" in data[:8192]:
        return False
    return True


def chunk_text(path: str, text: str, size: int = 60, overlap: int = 10) -> list[Chunk]:
    lines = text.splitlines()
    if not lines:
        return [Chunk(path, 1, 1, path)]
    chunks = []
    step = max(1, size - overlap)
    for start in range(0, len(lines), step):
        body = "\n".join(lines[start:start + size])
        # The path goes into every chunk so file names are searchable too.
        chunks.append(Chunk(path, start + 1, min(len(lines), start + size), f"{path}\n{body}"))
        if start + size >= len(lines):
            break
    return chunks


class CodeIndex:
    def __init__(self, repo: GitRepo, embedder: Embedder, chunk_lines: int = 60,
                 chunk_overlap: int = 10, max_file_bytes: int = 200_000):
        self.repo = repo
        self.embedder = embedder
        self.chunk_lines = chunk_lines
        self.chunk_overlap = chunk_overlap
        self.max_file_bytes = max_file_bytes
        self.chunks: list[Chunk] = []
        self.file_sizes: dict[str, int] = {}
        self._faiss: faiss.Index | None = None
        self._bm25: BM25 | None = None
        self.stats: dict[str, int] = {}

    # ---- persistence -------------------------------------------------------
    @property
    def _cache_prefix(self) -> Path:
        return self.repo.cache_dir / f"index-{self.embedder.name}"

    def _load_cache(self) -> tuple[dict, np.ndarray | None]:
        meta_path = self._cache_prefix.with_suffix(".json")
        vec_path = self._cache_prefix.with_suffix(".npy")
        if not (meta_path.exists() and vec_path.exists()):
            return {}, None
        try:
            meta = json.loads(meta_path.read_text())
            vecs = np.load(vec_path)
            return meta, vecs
        except Exception:  # corrupt cache: rebuild
            return {}, None

    def _save_cache(self, files: dict, vecs: np.ndarray) -> None:
        self._cache_prefix.with_suffix(".json").write_text(json.dumps(files))
        np.save(self._cache_prefix.with_suffix(".npy"), vecs)

    # ---- build -------------------------------------------------------------
    def build(self) -> "CodeIndex":
        cached_meta, cached_vecs = self._load_cache()
        cached_files = cached_meta.get("files", {}) if cached_meta else {}

        new_files: dict[str, dict] = {}
        all_chunks: list[Chunk] = []
        vec_parts: list[np.ndarray] = []
        to_embed: list[Chunk] = []
        to_embed_slots: list[int] = []  # index into vec_parts placeholder list
        reused = embedded = 0

        for rel in self.repo.tracked_files():
            full = self.repo.root / rel
            try:
                data = full.read_bytes()
            except (OSError, IsADirectoryError):
                continue
            if not is_indexable(rel, data, self.max_file_bytes):
                continue
            text = data.decode("utf-8", errors="replace")
            self.file_sizes[rel] = len(text)
            digest = _sha(data)
            chunks = chunk_text(rel, text, self.chunk_lines, self.chunk_overlap)
            first = len(all_chunks)
            all_chunks.extend(chunks)
            new_files[rel] = {"sha": digest, "first": first, "count": len(chunks)}

            old = cached_files.get(rel)
            if (old and old["sha"] == digest and old["count"] == len(chunks)
                    and cached_vecs is not None):
                vec_parts.append(cached_vecs[old["first"]:old["first"] + old["count"]])
                reused += len(chunks)
            else:
                to_embed_slots.append(len(vec_parts))
                vec_parts.append(np.empty((0, 0), dtype="float32"))  # placeholder
                to_embed.extend(chunks)
                embedded += len(chunks)

        if to_embed:
            # vec_parts has exactly one entry per file, in file order, so a
            # placeholder's slot number is also its position in new_files.
            fresh = self._embed_batched([c.text for c in to_embed])
            counts = [info["count"] for info in new_files.values()]
            cursor = 0
            for slot in to_embed_slots:
                vec_parts[slot] = fresh[cursor:cursor + counts[slot]]
                cursor += counts[slot]

        dim = self.embedder.dim
        vecs = np.vstack(vec_parts).astype("float32") if vec_parts else np.zeros((0, dim), "float32")
        self.chunks = all_chunks
        self._faiss = faiss.IndexFlatIP(dim)
        if len(vecs):
            self._faiss.add(vecs)
        self._bm25 = BM25([keyword_terms(c.text) for c in all_chunks])
        self._save_cache({"files": new_files, "embedder": self.embedder.name}, vecs)
        self.stats = {"files": len(new_files), "chunks": len(all_chunks),
                      "reused_chunks": reused, "embedded_chunks": embedded}
        log.info("Index built: %s", self.stats)
        return self

    def _embed_batched(self, texts: list[str], batch: int = 512) -> np.ndarray:
        parts = [self.embedder.embed(texts[i:i + batch]) for i in range(0, len(texts), batch)]
        return np.vstack(parts)

    # ---- search ------------------------------------------------------------
    def search(self, query: str, top_k: int = 6, candidate_chunks: int = 400) -> list[FileHit]:
        """Hybrid search: FAISS vector ranking + BM25 keyword ranking, merged by
        normalized score fusion, plus a bonus for request words found in the path."""
        if self._faiss is None or not self.chunks:
            return []

        # Dense ranking of files (best chunk per file).
        qvec = self.embedder.embed([query])
        n = min(candidate_chunks, len(self.chunks))
        scores, ids = self._faiss.search(qvec, n)
        dense: dict[str, float] = {}
        for score, idx in zip(scores[0], ids[0]):
            if idx >= 0:
                path = self.chunks[idx].path
                dense[path] = max(dense.get(path, -1e9), float(score))

        # Keyword ranking of files.
        keyword: dict[str, float] = {}
        if self._bm25 is not None:
            for idx, score in self._bm25.scores(keyword_terms(query)).items():
                path = self.chunks[idx].path
                keyword[path] = max(keyword.get(path, 0.0), score)

        # Score fusion: scale each ranking so its best file scores 1.0, then add
        # them up. Unlike rank-only fusion this keeps the size of a lead, so a file
        # that is the only one mentioning a rare identifier still wins.
        # The hashing embedder is itself word-based (without BM25's rare-word
        # weighting), so its vote counts less; a real embedding model is an
        # independent, semantic signal and gets equal weight.
        dense_weight = 0.5 if self.embedder.name.startswith("hashing") else 1.0
        fused: dict[str, float] = defaultdict(float)
        for ranking, weight in ((dense, dense_weight), (keyword, 1.0)):
            if not ranking:
                continue
            top = max(ranking.values())
            if top <= 0:
                continue
            for path, score in ranking.items():
                fused[path] += weight * max(score, 0.0) / top

        q_words = set(tokenize(query))
        for path in fused:
            path_words = set(tokenize(path))
            if q_words and path_words:
                fused[path] += PATH_BONUS * len(q_words & path_words) / len(path_words)

        ranked = sorted((FileHit(p, s) for p, s in fused.items()), key=lambda h: h.score,
                        reverse=True)
        return ranked[:top_k]

    @property
    def total_chars(self) -> int:
        return sum(self.file_sizes.values())
