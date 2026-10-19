"""Settings, with environment-variable overrides."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


DEFAULT_CLAUDE_MODEL = "claude-sonnet-5-5"

# Ready-made endpoints for --provider shortcuts. Any other OpenAI-compatible
# server works too: use provider "openai-compatible" and set base_url.
PROVIDER_PRESETS = {
    "ollama": {"base_url": "http://localhost:11434/v1", "key_env": None},
    "groq": {"base_url": "https://api.groq.com/openai/v1", "key_env": "GROQ_API_KEY"},
    "openrouter": {"base_url": "https://openrouter.ai/api/v1", "key_env": "OPENROUTER_API_KEY"},
    "gemini": {"base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
               "key_env": "GEMINI_API_KEY"},
    "github": {"base_url": "https://models.github.ai/inference", "key_env": "GITHUB_TOKEN"},
    "openai": {"base_url": "https://api.openai.com/v1", "key_env": "OPENAI_API_KEY"},
}
PROVIDERS = ["anthropic", "openai-compatible", *PROVIDER_PRESETS]


@dataclass
class Config:
    # Who writes the edits. "anthropic" (Claude, the default), a preset name from
    # PROVIDER_PRESETS, or "openai-compatible" with base_url set.
    provider: str = field(default_factory=lambda: os.environ.get("DIFFSMITH_PROVIDER", "anthropic"))
    # Required for non-Claude providers; defaults to Claude Sonnet for "anthropic".
    model: str | None = field(default_factory=lambda: os.environ.get("DIFFSMITH_MODEL"))
    base_url: str | None = field(default_factory=lambda: os.environ.get("DIFFSMITH_BASE_URL"))
    # Overrides the provider's usual key variable (e.g. GROQ_API_KEY).
    api_key: str | None = field(default_factory=lambda: os.environ.get("DIFFSMITH_API_KEY"))
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

    # ---- resolved provider settings ----------------------------------------
    @property
    def resolved_model(self) -> str | None:
        if self.model:
            return self.model
        return DEFAULT_CLAUDE_MODEL if self.provider == "anthropic" else None

    @property
    def resolved_base_url(self) -> str | None:
        if self.base_url:
            return self.base_url
        return PROVIDER_PRESETS.get(self.provider, {}).get("base_url")

    @property
    def key_env(self) -> str | None:
        """Environment variable the API key is read from, if any."""
        if self.provider == "anthropic":
            return "ANTHROPIC_API_KEY"
        if self.provider == "openai-compatible":
            return "OPENAI_API_KEY"
        return PROVIDER_PRESETS.get(self.provider, {}).get("key_env")

    @property
    def resolved_api_key(self) -> str | None:
        if self.api_key:
            return self.api_key
        return os.environ.get(self.key_env) if self.key_env else None

    def problems(self) -> list[str]:
        """Settings errors to show before doing any work."""
        out = []
        if self.provider not in PROVIDERS:
            out.append(f"Unknown provider {self.provider!r}. Choose one of: {', '.join(PROVIDERS)}.")
            return out
        if not self.resolved_model:
            out.append(f"Set a model for {self.provider}, e.g. --model qwen2.5-coder:14b "
                       "(or DIFFSMITH_MODEL).")
        if self.provider != "anthropic" and not self.resolved_base_url:
            out.append("openai-compatible needs --base-url (or DIFFSMITH_BASE_URL).")
        needs_key = self.provider not in ("ollama", "openai-compatible")
        if needs_key and not self.resolved_api_key:
            out.append(f"{self.key_env} is not set. Run: export {self.key_env}=your-key")
        return out
