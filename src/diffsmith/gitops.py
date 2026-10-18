"""Thin wrapper around the git command line."""

from __future__ import annotations

import subprocess
from pathlib import Path


class GitError(RuntimeError):
    pass


class GitRepo:
    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        if not (self.root / ".git").exists():
            raise GitError(f"{self.root} is not a git repository")

    def _git(self, *args: str, check: bool = True) -> str:
        proc = subprocess.run(
            ["git", *args], cwd=self.root, capture_output=True, text=True
        )
        if check and proc.returncode != 0:
            raise GitError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
        return proc.stdout

    def head(self) -> str | None:
        proc = subprocess.run(
            ["git", "rev-parse", "--verify", "-q", "HEAD"],
            cwd=self.root, capture_output=True, text=True,
        )
        return proc.stdout.strip() if proc.returncode == 0 else None

    def tracked_files(self) -> list[str]:
        """Tracked plus untracked-but-not-ignored files, relative to the root."""
        out = self._git("ls-files", "--cached", "--others", "--exclude-standard", "-z")
        return sorted({p for p in out.split("\0") if p})

    def is_clean(self) -> bool:
        return self._git("status", "--porcelain").strip() == ""

    def dirty_paths(self) -> list[str]:
        lines = self._git("status", "--porcelain", "-z").split("\0")
        return [ln[3:] for ln in lines if len(ln) > 3]

    def diff(self) -> str:
        self._git("add", "-N", ".")  # so new files show up in the diff
        return self._git("diff")

    def commit_all(self, message: str) -> str:
        self._git("add", "-A")
        self._git("commit", "-q", "-m", message)
        return self._git("rev-parse", "HEAD").strip()

    def rollback(self) -> None:
        """Throw away every uncommitted change, including new files."""
        self._git("reset", "-q", "--hard")
        self._git("clean", "-q", "-fd")

    @property
    def cache_dir(self) -> Path:
        """Inside .git, so the index cache is never committed or cleaned."""
        path = self.root / ".git" / "diffsmith"
        path.mkdir(parents=True, exist_ok=True)
        return path
