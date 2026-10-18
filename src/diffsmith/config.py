"""Settings, with environment-variable overrides."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


@dataclass
class Config:
    # Model that writes the edits.
    model: str = field(default_factory=lambda: os.environ.get("DIFFSMITH_MODEL", "claude-sonnet-5-5"))
    max_tokens: int = field(default_factory=lambda: _env_int("DIFFSMITH_MAX_TOKENS", 8000))

    # Embedding backend: "auto" uses sentence-transformers when installed,
    # otherwise a dependency-free hashing embedder.
    embedder: str = field(default_factory=lambda: os.environ.get("DIFFSMITH_EMBEDDER", "auto"))
    embedding_model: str = field(
        default_factory=lambda: os.environ.get("DIFFSMITH_EMBEDDING_MODEL", "all-MiniLM-L6-v2")
    )

    # Retrieval.
    top_k_files: int = field(default_factory=lambda: _env_int("DIFFSMITH_TOP_K", 6))
    chunk_lines: int = 60
    chunk_overlap: int = 10
    max_context_chars: int = field(default_factory=lambda: _env_int("DIFFSMITH_MAX_CONTEXT_CHARS", 60_000))
    max_file_bytes: int = 200_000

    # Test gate.
    test_command: str | None = field(default_factory=lambda: os.environ.get("DIFFSMITH_TEST_COMMAND"))
    test_timeout: int = field(default_factory=lambda: _env_int("DIFFSMITH_TEST_TIMEOUT", 300))
    run_tests: bool = True

    # How many times the model may retry after a failed test run.
    max_attempts: int = field(default_factory=lambda: _env_int("DIFFSMITH_MAX_ATTEMPTS", 2))
