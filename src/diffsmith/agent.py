"""The Diffsmith pipeline: retrieve -> edit -> test -> commit or roll back."""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path, PurePosixPath

from .config import Config
from .edits import EditError, apply_edits, parse_commit_message, parse_edits, parse_needed_files
from .embeddings import make_embedder
from .gitops import GitRepo
from .index import CodeIndex
from .llm import (SYSTEM_PROMPT, AnthropicClient, LLMClient, build_retry_prompt,
                  build_user_prompt)
from .testgate import detect_test_command, run_tests

log = logging.getLogger(__name__)


@dataclass
class Attempt:
    number: int
    outcome: str  # "committed", "tests_failed", "edit_failed", "no_edits", "dry_run_passed"
    files: list[str] = field(default_factory=list)
    detail: str = ""


@dataclass
class EditResult:
    request: str
    success: bool
    commit: str | None = None
    message: str | None = None
    diff: str = ""
    files_changed: list[str] = field(default_factory=list)
    retrieved_files: list[str] = field(default_factory=list)
    attempts: list[Attempt] = field(default_factory=list)
    tested: bool = False
    test_command: str | None = None
    context_chars: int = 0
    repo_chars: int = 0
    error: str | None = None

    @property
    def context_reduction(self) -> float:
        """Share of the repository's code that was NOT sent to the model."""
        if not self.repo_chars:
            return 0.0
        return max(0.0, 1 - self.context_chars / self.repo_chars)

    @property
    def blocked_edits(self) -> int:
        return sum(a.outcome == "tests_failed" for a in self.attempts)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["context_reduction"] = round(self.context_reduction, 4)
        d["blocked_edits"] = self.blocked_edits
        return d


class Diffsmith:
    def __init__(self, repo_path: str | Path, config: Config | None = None,
                 llm: LLMClient | None = None):
        self.config = config or Config()
        self.repo = GitRepo(repo_path)
        self.llm = llm or AnthropicClient(self.config.model, self.config.max_tokens)
        self._index: CodeIndex | None = None
        self._embedder = None

    # ---- setup -------------------------------------------------------------
    def index(self) -> CodeIndex:
        if self._embedder is None:
            self._embedder = make_embedder(self.config.embedder, self.config.embedding_model)
        self._index = CodeIndex(
            self.repo, self._embedder, self.config.chunk_lines,
            self.config.chunk_overlap, self.config.max_file_bytes,
        ).build()
        return self._index

    def _test_command(self) -> str | None:
        return self.config.test_command or detect_test_command(self.repo.root)

    def _baseline_passes(self, command: str) -> tuple[bool, str]:
        """Run tests on the untouched tree once per commit; cache the answer."""
        head = self.repo.head() or "no-head"
        cache = self.repo.cache_dir / "baseline.json"
        try:
            data = json.loads(cache.read_text())
        except (OSError, ValueError):
            data = {}
        key = f"{head}:{command}"
        if key in data:
            return data[key], ""
        run = run_tests(self.repo.root, command, self.config.test_timeout)
        data = {key: run.passed}  # keep only the latest entry
        cache.write_text(json.dumps(data))
        return run.passed, run.tail()

    # ---- context -----------------------------------------------------------
    def _gather_context(self, request: str, extra: list[str] | None = None) -> dict[str, str]:
        assert self._index is not None
        hits = self._index.search(request, top_k=self.config.top_k_files)
        paths = [h.path for h in hits]
        for p in extra or []:
            if p not in paths and (self.repo.root / p).is_file():
                paths.insert(0, p)
        files: dict[str, str] = {}
        budget = self.config.max_context_chars
        for p in paths:
            try:
                text = (self.repo.root / p).read_text(errors="replace")
            except OSError:
                continue
            if len(text) > budget and files:
                continue
            files[p] = text[:budget]
            budget -= len(files[p])
            if budget <= 0:
                break
        return files

    def _file_listing(self, focus: list[str], cap: int = 200) -> list[str]:
        """Files near the retrieved ones first, then the rest, capped."""
        all_files = list(self._index.file_sizes) if self._index else []
        dirs = {str(PurePosixPath(p).parent) for p in focus}
        near = [f for f in all_files if str(PurePosixPath(f).parent) in dirs]
        top = [f for f in all_files if "/" not in f]
        seen, listing = set(), []
        for f in near + top + all_files:
            if f not in seen:
                seen.add(f)
                listing.append(f)
            if len(listing) >= cap:
                break
        return listing

    # ---- main entry point --------------------------------------------------
    def run(self, request: str, dry_run: bool = False, allow_dirty: bool = False) -> EditResult:
        result = EditResult(request=request, success=False)

        if not allow_dirty and not self.repo.is_clean():
            result.error = ("The working tree has uncommitted changes. Commit or stash them first, "
                            "since Diffsmith rolls back failed edits with a hard reset.")
            return result

        index = self.index()
        result.repo_chars = index.total_chars

        command = self._test_command() if self.config.run_tests else None
        result.test_command = command
        if command:
            ok, output = self._baseline_passes(command)
            if not ok:
                result.error = ("The test suite already fails before any change, so it can't "
                                f"tell good edits from bad ones. Fix it first.\n{output}")
                return result

        files = self._gather_context(request)
        result.retrieved_files = list(files)
        listing = self._file_listing(list(files))
        messages = [{"role": "user", "content": build_user_prompt(request, listing, files)}]

        # One round for the model to ask for files it wasn't shown.
        reply = self.llm.complete(SYSTEM_PROMPT, messages)
        needed = parse_needed_files(reply) if not parse_edits(reply) else []
        if needed:
            files = self._gather_context(request, extra=needed)
            result.retrieved_files = list(files)
            listing = self._file_listing(list(files))
            messages = [{"role": "user", "content": build_user_prompt(request, listing, files)}]
            reply = self.llm.complete(SYSTEM_PROMPT, messages)
        result.context_chars = sum(len(t) for t in files.values())

        for number in range(1, self.config.max_attempts + 1):
            if number > 1:
                reply = self.llm.complete(SYSTEM_PROMPT, messages)
            messages.append({"role": "assistant", "content": reply})

            edits = parse_edits(reply)
            if not edits:
                result.attempts.append(Attempt(number, "no_edits", detail=reply[-500:]))
                messages.append({"role": "user", "content": build_retry_prompt(
                    "No SEARCH/REPLACE blocks were found in your reply.")})
                continue

            try:
                changed = apply_edits(self.repo.root, edits)
            except EditError as exc:
                self.repo.rollback()
                result.attempts.append(Attempt(number, "edit_failed", detail=str(exc)))
                messages.append({"role": "user", "content": build_retry_prompt(str(exc))})
                continue

            if command:
                run = run_tests(self.repo.root, command, self.config.test_timeout)
                result.tested = True
                if not run.passed:
                    self.repo.rollback()
                    result.attempts.append(Attempt(number, "tests_failed", changed, run.tail(1500)))
                    messages.append({"role": "user", "content": build_retry_prompt(
                        f"The test command `{command}` failed:\n{run.tail()}")})
                    continue

            result.diff = self.repo.diff()
            result.files_changed = changed
            message = parse_commit_message(reply) or f"Diffsmith: {request[:60]}"
            result.message = message

            if dry_run:
                self.repo.rollback()
                result.attempts.append(Attempt(number, "dry_run_passed", changed))
                result.success = True
                return result

            body = f"{message}\n\nRequested change: {request.strip()}\nGenerated by Diffsmith."
            if command:
                body += " The project's tests passed before this commit."
            result.commit = self.repo.commit_all(body)
            result.attempts.append(Attempt(number, "committed", changed))
            result.success = True
            return result

        result.error = f"No passing edit after {self.config.max_attempts} attempt(s)."
        return result
