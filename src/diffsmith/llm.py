"""Model clients and the prompt that asks for SEARCH/REPLACE edits."""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Callable, Protocol


class LLMClient(Protocol):
    def complete(self, system: str, messages: list[dict]) -> str: ...


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    calls: int = 0


class AnthropicClient:
    """Calls Claude through the official SDK. Reads ANTHROPIC_API_KEY from the environment."""

    def __init__(self, model: str, max_tokens: int = 8000):
        import anthropic

        self._client = anthropic.Anthropic()
        self.model = model
        self.max_tokens = max_tokens
        self.usage = Usage()

    def complete(self, system: str, messages: list[dict]) -> str:
        resp = self._client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system,
            messages=messages,
        )
        self.usage.calls += 1
        self.usage.input_tokens += getattr(resp.usage, "input_tokens", 0)
        self.usage.output_tokens += getattr(resp.usage, "output_tokens", 0)
        return "".join(block.text for block in resp.content if block.type == "text")


class LLMError(RuntimeError):
    """A model request failed (bad key, unknown model, server down, ...)."""


_THINK = re.compile(r"<think>.*?</think>", re.DOTALL)


class OpenAICompatibleClient:
    """Any server speaking the OpenAI chat-completions format: Ollama, Groq,
    OpenRouter, Gemini, GitHub Models, OpenAI, vLLM, LM Studio, ...

    Uses only the standard library. Retries rate-limit (429) and transient
    server errors with backoff, since free tiers hit their limits often.
    """

    def __init__(self, base_url: str, model: str, api_key: str | None = None,
                 max_tokens: int = 8000, timeout: int = 600, max_retries: int = 5,
                 sleep: Callable[[float], None] = time.sleep):
        self.url = base_url.rstrip("/") + "/chat/completions"
        self.model = model
        self.api_key = api_key
        self.max_tokens = max_tokens
        self.timeout = timeout
        self.max_retries = max_retries
        self._sleep = sleep
        self.usage = Usage()

    def _post(self, payload: dict) -> dict:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        body = json.dumps(payload).encode()
        for attempt in range(self.max_retries + 1):
            req = urllib.request.Request(self.url, data=body, headers=headers, method="POST")
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    return json.loads(resp.read().decode())
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode(errors="replace")[:500]
                retryable = exc.code == 429 or exc.code >= 500
                if retryable and attempt < self.max_retries:
                    wait = exc.headers.get("Retry-After") if exc.headers else None
                    try:
                        delay = float(wait) if wait else 2 ** attempt * 2
                    except ValueError:
                        delay = 2 ** attempt * 2
                    self._sleep(min(delay, 60))
                    continue
                raise LLMError(f"HTTP {exc.code} from {self.url}: {detail}") from exc
            except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
                if attempt < min(self.max_retries, 2):  # a down server rarely recovers fast
                    self._sleep(2 ** attempt)
                    continue
                raise LLMError(f"Could not reach {self.url}: {exc}") from exc
        raise LLMError("unreachable")  # pragma: no cover

    def complete(self, system: str, messages: list[dict]) -> str:
        data = self._post({
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": [{"role": "system", "content": system}, *messages],
        })
        self.usage.calls += 1
        usage = data.get("usage") or {}
        self.usage.input_tokens += usage.get("prompt_tokens", 0) or 0
        self.usage.output_tokens += usage.get("completion_tokens", 0) or 0
        try:
            content = data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError(f"Unexpected response: {str(data)[:300]}") from exc
        # Reasoning models (DeepSeek-R1, Qwen3, ...) may include their thinking.
        return _THINK.sub("", content)


def make_llm(config) -> LLMClient:
    """Build the client the config asks for. Claude is the default."""
    problems = config.problems()
    if problems:
        raise LLMError(" ".join(problems))
    if config.provider == "anthropic":
        return AnthropicClient(config.resolved_model, config.max_tokens)
    return OpenAICompatibleClient(config.resolved_base_url, config.resolved_model,
                                  config.resolved_api_key, config.max_tokens)


@dataclass
class ScriptedClient:
    """Returns canned responses. Used by tests and offline demos."""

    responses: list[str] | Callable[[str, list[dict]], str]
    calls: list[list[dict]] = field(default_factory=list)
    usage: Usage = field(default_factory=Usage)

    def complete(self, system: str, messages: list[dict]) -> str:
        self.calls.append([dict(m) for m in messages])  # snapshot; caller keeps appending
        self.usage.calls += 1
        if callable(self.responses):
            return self.responses(system, messages)
        return self.responses.pop(0)


SYSTEM_PROMPT = """You are Diffsmith, a careful senior engineer who edits code in an existing repository.

You get a change request, the repository's file list, and the full text of the files most likely to matter.
Make the smallest correct change that satisfies the request. Match the existing style. Keep existing
behavior and tests working. Add or update tests when the request changes behavior and the repo has tests.

Reply with edits in exactly this format, one block per change:

FILE: relative/path/to/file.ext
<<<<<<< SEARCH
lines copied exactly from the current file, enough to be unique
=======
the new lines that replace them
>>>>>>> REPLACE

Rules:
- SEARCH must match the current file exactly, character for character, and match only one place.
- To create a new file, use an empty SEARCH section.
- Several blocks for the same file are fine; they are applied in order.
- Do not use code fences around blocks.
- End with one line: COMMIT: <short imperative commit message, under 72 characters>

If you need to see a file that was not shown before you can edit safely, reply with only:
NEED_FILES: path/one.py, path/two.py
"""


def build_user_prompt(request: str, file_list: list[str], files: dict[str, str],
                      max_listing: int = 400) -> str:
    listing = file_list[:max_listing]
    more = len(file_list) - len(listing)
    parts = [f"## Change request\n{request.strip()}\n", "## Repository files"]
    parts.append("\n".join(listing) + (f"\n... and {more} more files" if more > 0 else ""))
    parts.append("\n## Relevant files (full text)")
    for path, text in files.items():
        parts.append(f"### {path}\n<file>\n{text}\n</file>")
    return "\n".join(parts)


def build_retry_prompt(error: str) -> str:
    return (
        "Your previous edit was rolled back, so the files are back to the versions shown above.\n"
        f"Reason:\n{error}\n\n"
        "Write a corrected set of SEARCH/REPLACE blocks against the original files, "
        "and end with a COMMIT line."
    )
