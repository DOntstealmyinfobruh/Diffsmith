"""Run the project's own test suite and report pass or fail."""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass
class TestRun:
    command: str
    passed: bool
    returncode: int
    output: str
    seconds: float

    def tail(self, chars: int = 4000) -> str:
        return self.output[-chars:]


def detect_test_command(root: str | Path) -> str | None:
    root = Path(root)
    py = shlex.quote(sys.executable)
    if (root / "pytest.ini").exists() or (root / "tests").is_dir() or (root / "test").is_dir() \
            or (root / "conftest.py").exists():
        return f"{py} -m pytest -q -x -p no:cacheprovider"
    pyproject = root / "pyproject.toml"
    if pyproject.exists() and "[tool.pytest" in pyproject.read_text(errors="ignore"):
        return f"{py} -m pytest -q -x -p no:cacheprovider"
    pkg = root / "package.json"
    if pkg.exists():
        try:
            if "test" in json.loads(pkg.read_text()).get("scripts", {}):
                return "npm test --silent"
        except ValueError:
            pass
    if (root / "Cargo.toml").exists():
        return "cargo test --quiet"
    if (root / "go.mod").exists():
        return "go test ./..."
    if list(root.glob("test_*.py")) or list(root.glob("*_test.py")):
        return f"{py} -m pytest -q -x -p no:cacheprovider"
    return None


def run_tests(root: str | Path, command: str, timeout: int = 300) -> TestRun:
    start = time.monotonic()
    try:
        proc = subprocess.run(
            command, shell=True, cwd=root, capture_output=True, text=True, timeout=timeout,
            # no __pycache__ litter, which would dirty the tree and end up in the commit
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        )
        output = (proc.stdout or "") + (proc.stderr or "")
        code = proc.returncode
    except subprocess.TimeoutExpired as exc:
        output = f"Tests timed out after {timeout}s\n{exc.stdout or ''}"
        code = -1
    # pytest exit code 5 means "no tests collected"; treat that as a pass.
    passed = code == 0 or (code == 5 and "pytest" in command)
    return TestRun(command, passed, code, output, time.monotonic() - start)
