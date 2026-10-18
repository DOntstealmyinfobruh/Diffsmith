"""HTTP API.

    diffsmith serve
    curl -X POST localhost:8000/edit -H 'content-type: application/json' \\
         -d '{"repo": "/path/to/repo", "request": "add a --verbose flag"}'

The server edits repositories on the machine it runs on, so it binds to
127.0.0.1 by default. Set DIFFSMITH_ALLOWED_ROOTS (colon-separated paths) to
restrict which repositories it may touch.
"""

from __future__ import annotations

import os
import threading
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from . import __version__
from .agent import Diffsmith
from .config import Config
from .gitops import GitError

app = FastAPI(title="Diffsmith", version=__version__)
_repo_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


class EditRequest(BaseModel):
    repo: str = Field(description="Absolute path to a git repository on the server")
    request: str = Field(min_length=3, description="Plain-English change request")
    dry_run: bool = False
    max_attempts: int | None = Field(default=None, ge=1, le=5)


def _check_allowed(repo: Path) -> None:
    allowed = os.environ.get("DIFFSMITH_ALLOWED_ROOTS")
    if not allowed:
        return
    roots = [Path(r).resolve() for r in allowed.split(":") if r]
    if not any(repo == r or r in repo.parents for r in roots):
        raise HTTPException(403, f"{repo} is outside DIFFSMITH_ALLOWED_ROOTS")


def _lock_for(repo: Path) -> threading.Lock:
    with _locks_guard:
        return _repo_locks.setdefault(str(repo), threading.Lock())


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "version": __version__}


@app.post("/edit")
def edit(body: EditRequest) -> dict:
    repo = Path(body.repo).resolve()
    _check_allowed(repo)
    cfg = Config()  # the test command is never taken from the request body (it runs in a shell)
    if body.max_attempts:
        cfg.max_attempts = body.max_attempts

    lock = _lock_for(repo)
    if not lock.acquire(blocking=False):
        raise HTTPException(409, "Another edit is already running on this repository")
    try:
        try:
            tool = Diffsmith(repo, cfg)
        except GitError as exc:
            raise HTTPException(400, str(exc)) from exc
        result = tool.run(body.request, dry_run=body.dry_run)
        return result.to_dict()
    finally:
        lock.release()
