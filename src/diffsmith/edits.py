"""Parse the model's SEARCH/REPLACE blocks and apply them to files.

Format the model is asked to produce:

    FILE: path/to/file.py
    <<<<<<< SEARCH
    exact lines currently in the file
    =======
    the lines that replace them
    >>>>>>> REPLACE

An empty SEARCH section creates the file (or appends to it if it exists).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

_BLOCK = re.compile(
    r"^FILE:[ \t]*(?P<path>[^\n]+?)[ \t]*\n"
    r"(?:```[^\n]*\n)?"
    r"<{5,}[ \t]*SEARCH[ \t]*\n(?P<search>.*?)^={5,}[ \t]*\n(?P<replace>.*?)^>{5,}[ \t]*REPLACE[ \t]*$",
    re.MULTILINE | re.DOTALL,
)
_COMMIT = re.compile(r"^COMMIT:[ \t]*(?P<msg>.+)$", re.MULTILINE)
_NEED = re.compile(r"^NEED_FILES:[ \t]*(?P<files>.+)$", re.MULTILINE)


class EditError(ValueError):
    pass


@dataclass
class Edit:
    path: str
    search: str
    replace: str


def parse_edits(text: str) -> list[Edit]:
    edits = []
    for m in _BLOCK.finditer(text):
        path = m.group("path").strip().strip("`").strip()
        edits.append(Edit(path, m.group("search"), m.group("replace")))
    return edits


def parse_commit_message(text: str) -> str | None:
    m = _COMMIT.search(text)
    return m.group("msg").strip() if m else None


def parse_needed_files(text: str) -> list[str]:
    m = _NEED.search(text)
    if not m:
        return []
    return [p.strip().strip("`") for p in m.group("files").split(",") if p.strip()]


def _safe_path(root: Path, rel: str) -> Path:
    target = (root / rel).resolve()
    if root != target and root not in target.parents:
        raise EditError(f"Refusing to write outside the repository: {rel}")
    if ".git" in Path(rel).parts:
        raise EditError(f"Refusing to edit git internals: {rel}")
    return target


def _find_loose(haystack: str, needle: str) -> tuple[int, int] | None:
    """Match ignoring trailing whitespace on each line. Returns (start, end) offsets."""
    h_lines = haystack.splitlines(keepends=True)
    n_lines = [ln.rstrip() for ln in needle.splitlines()]
    if not n_lines:
        return None
    stripped = [ln.rstrip() for ln in h_lines]
    hits = [i for i in range(len(h_lines) - len(n_lines) + 1)
            if stripped[i:i + len(n_lines)] == n_lines]
    if len(hits) != 1:
        return None
    start = sum(len(ln) for ln in h_lines[:hits[0]])
    end = start + sum(len(ln) for ln in h_lines[hits[0]:hits[0] + len(n_lines)])
    return start, end


def apply_edit(root: Path, edit: Edit) -> str:
    """Apply one edit in place. Returns the path that changed."""
    target = _safe_path(root, edit.path)

    if not edit.search.strip():
        target.parent.mkdir(parents=True, exist_ok=True)
        existing = target.read_text() if target.exists() else ""
        if existing and not existing.endswith("\n"):
            existing += "\n"
        target.write_text(existing + edit.replace)
        return edit.path

    if not target.exists():
        raise EditError(f"{edit.path}: file does not exist, so its SEARCH text can't match")
    content = target.read_text()

    count = content.count(edit.search)
    if count == 1:
        new = content.replace(edit.search, edit.replace, 1)
    elif count > 1:
        raise EditError(f"{edit.path}: SEARCH text matches {count} places; it must be unique")
    else:
        span = _find_loose(content, edit.search)
        if span is None:
            raise EditError(f"{edit.path}: SEARCH text not found in the file")
        replacement = edit.replace
        if content[span[1] - 1:span[1]] == "\n" and not replacement.endswith("\n"):
            replacement += "\n"
        new = content[:span[0]] + replacement + content[span[1]:]

    target.write_text(new)
    return edit.path


def apply_edits(root: str | Path, edits: list[Edit]) -> list[str]:
    root = Path(root).resolve()
    changed = []
    for edit in edits:
        changed.append(apply_edit(root, edit))
    return sorted(set(changed))
