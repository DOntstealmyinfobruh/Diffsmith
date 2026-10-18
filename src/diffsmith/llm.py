"""Model clients and the prompt that asks for SEARCH/REPLACE edits."""

from __future__ import annotations

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
