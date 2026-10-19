"""Measure Diffsmith on the 50 tasks in eval/tasks.py.

Examples
--------
    # Full run with Claude (needs ANTHROPIC_API_KEY):
    python eval/run_eval.py

    # Same, inside repos padded with 10,000 extra files to test scale:
    python eval/run_eval.py --pad 10000

    # No API key needed: check retrieval only (which files would be sent):
    python eval/run_eval.py --retrieval-only --pad 10000

    # No API key needed: replay the reference solutions to prove every task
    # is solvable and every hidden check is correct:
    python eval/run_eval.py --oracle

Scoring
-------
A task counts as completed only if Diffsmith made a commit AND the hidden
acceptance test plus the project's own tests pass on that commit. Nobody edits
anything by hand.

"Broken edits blocked" = edits the test gate rolled back, divided by
(edits rolled back + committed edits that then failed the hidden test).
"""

from __future__ import annotations

import argparse
import json
import os
import random
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "src"))
sys.path.insert(0, str(HERE))

from diffsmith.agent import Diffsmith  # noqa: E402
from diffsmith.config import Config  # noqa: E402
from diffsmith.embeddings import make_embedder  # noqa: E402
from diffsmith.gitops import GitRepo  # noqa: E402
from diffsmith.index import CodeIndex  # noqa: E402
from diffsmith.llm import ScriptedClient  # noqa: E402
from tasks import TASKS  # noqa: E402

FIXTURES = HERE / "fixtures"

# Words for synthetic filler modules. Some overlap with the fixtures' vocabulary
# on purpose, so the filler actually competes with the real files in search.
VOCAB = """account address amount api archive audit balance batch buffer cache cart
category channel client config connection count currency customer data date day
delete detail device discount document due email entry event file filter format
group handler history image import index invoice item job key label ledger limit
line list log message metadata money name node note number order owner page parse
payment priority product profile queue rate record report request resource result
role rule schedule search session setting slug status store string summary tag
task template text thread title token total transaction upload user value word""".split()


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True,
                          text=True).stdout


def _filler_module(rng: random.Random) -> str:
    out = ['"""Generated filler module for scale testing."""', ""]
    for _ in range(rng.randint(2, 5)):
        a, b = rng.sample(VOCAB, 2)
        args = ", ".join(rng.sample(VOCAB, rng.randint(1, 3)))
        out.append(f"def {a}_{b}({args}):")
        out.append(f'    """Return the {a} {b} for the given {args.split(",")[0]}."""')
        for _ in range(rng.randint(2, 6)):
            x, y = rng.sample(VOCAB, 2)
            out.append(f"    {x} = {rng.choice(['len', 'str', 'sorted', 'list'])}({y}) if {y} else None")
        out.append(f"    return {x}")
        out.append("")
    return "\n".join(out)


def pad_repo(root: Path, n: int, seed: int = 0) -> None:
    rng = random.Random(seed)
    for i in range(n):
        d = root / "vendor" / f"pkg{i // 100:03d}"
        d.mkdir(parents=True, exist_ok=True)
        a, b = rng.sample(VOCAB, 2)
        (d / f"{a}_{b}_{i}.py").write_text(_filler_module(rng))


def make_base_repos(work: Path, pad: int) -> dict[str, Path]:
    """One committed repo per fixture (padded if asked); tasks clone from these."""
    bases = {}
    for fixture in sorted({t["fixture"] for t in TASKS}):
        dest = work / f"base-{fixture}"
        shutil.copytree(FIXTURES / fixture, dest,
                        ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"))
        if pad:
            pad_repo(dest, pad)
        git(dest, "init", "-q", "-b", "main")
        git(dest, "config", "user.email", "eval@diffsmith.dev")
        git(dest, "config", "user.name", "Diffsmith Eval")
        git(dest, "add", "-A")
        git(dest, "commit", "-q", "-m", "fixture")
        bases[fixture] = dest
    return bases


def clone_for_task(base: Path, dest: Path) -> Path:
    git(base.parent, "clone", "-q", str(base), str(dest))
    git(dest, "config", "user.email", "eval@diffsmith.dev")
    git(dest, "config", "user.name", "Diffsmith Eval")
    # Reuse the base repo's embeddings so each task doesn't re-embed everything.
    src_cache = base / ".git" / "diffsmith"
    if src_cache.exists():
        shutil.copytree(src_cache, dest / ".git" / "diffsmith", dirs_exist_ok=True)
    return dest


def run_hidden_check(repo: Path, task: dict, scratch: Path) -> tuple[bool, str]:
    test_file = scratch / f"test_hidden_{task['id'].replace('-', '_')}.py"
    test_file.write_text(task["check"])
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", str(test_file), "tests"],
        cwd=repo, capture_output=True, text=True, timeout=300,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    return proc.returncode == 0, (proc.stdout + proc.stderr)[-2000:]


def make_llm(args, task):
    if args.oracle:
        return ScriptedClient(lambda system, messages: task["solution"])
    return None  # Diffsmith builds the Anthropic client from Config


def build_config(args) -> Config:
    cfg = Config()
    cfg.embedder = args.embedder
    if args.provider:
        cfg.provider = args.provider
    if args.base_url:
        cfg.base_url = args.base_url
    if args.model:
        cfg.model = args.model
    return cfg


def evaluate(args) -> dict:
    tasks = [t for t in TASKS if not args.only or t["id"] in args.only]
    cfg = build_config(args)
    if args.attempts:
        cfg.max_attempts = args.attempts
    if args.top_k:
        cfg.top_k_files = args.top_k

    work = Path(tempfile.mkdtemp(prefix="diffsmith-eval-"))
    print(f"Working in {work}")
    t0 = time.time()
    bases = make_base_repos(work, args.pad)

    # Warm each base repo's index once; task clones copy the cache.
    embedder = make_embedder(cfg.embedder, cfg.embedding_model)
    for fixture, base in bases.items():
        start = time.time()
        idx = CodeIndex(GitRepo(base), embedder, cfg.chunk_lines, cfg.chunk_overlap,
                        cfg.max_file_bytes).build()
        print(f"Indexed {fixture}: {idx.stats['files']} files, {idx.stats['chunks']} chunks "
              f"in {time.time() - start:.1f}s ({embedder.name})")

    rows = []
    for n, task in enumerate(tasks, 1):
        repo = clone_for_task(bases[task["fixture"]], work / task["id"])
        row = {"id": task["id"], "request": task["request"]}

        if args.retrieval_only:
            idx = CodeIndex(GitRepo(repo), embedder, cfg.chunk_lines, cfg.chunk_overlap,
                            cfg.max_file_bytes).build()
            hits = [h.path for h in idx.search(task["request"], top_k=cfg.top_k_files)]
            sent = sum(idx.file_sizes.get(p, 0) for p in hits)
            row.update(retrieved=hits, recall=all(f in hits for f in task["files"]),
                       context_reduction=1 - sent / idx.total_chars)
            print(f"[{n:2}/{len(tasks)}] {task['id']}: recall={'yes' if row['recall'] else 'NO '} "
                  f"reduction={row['context_reduction']:.1%}")
            rows.append(row)
            continue

        if args.oracle:
            # A hidden check that already passes before any change would prove nothing.
            baseline_ok, _ = run_hidden_check(repo, task, work)
            row["check_fails_on_baseline"] = not baseline_ok

        tool = Diffsmith(repo, cfg, llm=make_llm(args, task))
        tool._embedder = embedder
        start = time.time()
        try:
            result = tool.run(task["request"])
        except Exception as exc:  # API errors etc. count as failures, not crashes
            row.update(completed=False, committed=False, error=f"{type(exc).__name__}: {exc}",
                       attempts=[], blocked=0, leaked=0, recall=False, context_reduction=0.0)
            rows.append(row)
            print(f"[{n:2}/{len(tasks)}] {task['id']}: ERROR {row['error'][:120]}")
            continue

        hidden_ok, hidden_out = (False, "")
        if result.commit:
            hidden_ok, hidden_out = run_hidden_check(repo, task, work)
        usage = getattr(tool.llm, "usage", None)
        row.update(
            completed=bool(result.commit and hidden_ok),
            committed=bool(result.commit),
            hidden_passed=hidden_ok,
            attempts=[a.outcome for a in result.attempts],
            blocked=result.blocked_edits,
            leaked=int(bool(result.commit) and not hidden_ok),
            retrieved=result.retrieved_files,
            recall=all(f in result.retrieved_files for f in task["files"]),
            context_reduction=result.context_reduction,
            input_tokens=getattr(usage, "input_tokens", 0),
            output_tokens=getattr(usage, "output_tokens", 0),
            seconds=round(time.time() - start, 1),
            error=result.error,
            hidden_output=None if hidden_ok else hidden_out,
        )
        rows.append(row)
        status = "PASS" if row["completed"] else "FAIL"
        print(f"[{n:2}/{len(tasks)}] {task['id']}: {status} attempts={row['attempts']} "
              f"reduction={row['context_reduction']:.1%}")

    summary = summarize(rows, args)
    summary["wall_seconds"] = round(time.time() - t0, 1)
    if not args.keep:
        shutil.rmtree(work, ignore_errors=True)
    return {"summary": summary, "tasks": rows}


def summarize(rows: list[dict], args) -> dict:
    n = len(rows)
    s = {
        "mode": "retrieval-only" if args.retrieval_only else ("oracle" if args.oracle else "llm"),
        "provider": None if (args.retrieval_only or args.oracle) else build_config(args).provider,
        "model": None if (args.retrieval_only or args.oracle) else build_config(args).resolved_model,
        "embedder": args.embedder,
        "padding_files": args.pad,
        "tasks": n,
        "retrieval_recall": round(sum(r["recall"] for r in rows) / n, 4) if n else 0,
        "avg_context_reduction": round(sum(r["context_reduction"] for r in rows) / n, 4) if n else 0,
    }
    if args.oracle:
        s["checks_failing_on_baseline"] = sum(r.get("check_fails_on_baseline", False) for r in rows)
    if not args.retrieval_only:
        blocked = sum(r["blocked"] for r in rows)
        leaked = sum(r["leaked"] for r in rows)
        s.update(
            completed=sum(r["completed"] for r in rows),
            completion_rate=round(sum(r["completed"] for r in rows) / n, 4) if n else 0,
            broken_edits_blocked=blocked,
            broken_edits_committed=leaked,
            block_rate=round(blocked / (blocked + leaked), 4) if blocked + leaked else None,
            input_tokens=sum(r.get("input_tokens", 0) for r in rows),
            output_tokens=sum(r.get("output_tokens", 0) for r in rows),
        )
    return s


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--only", nargs="*", help="task ids to run (default: all 50)")
    p.add_argument("--pad", type=int, default=0, help="add this many filler files to each repo")
    p.add_argument("--embedder", default="auto", choices=["auto", "local", "hashing"])
    p.add_argument("--provider", help="anthropic (default), ollama, groq, openrouter, gemini, "
                   "github, openai, or openai-compatible")
    p.add_argument("--model", help="model name (default for Claude: claude-sonnet-5-5)")
    p.add_argument("--base-url", help="server URL for --provider openai-compatible")
    p.add_argument("--attempts", type=int, help="max attempts per task")
    p.add_argument("--top-k", type=int, help="files sent to the model")
    p.add_argument("--oracle", action="store_true", help="replay reference solutions (no API)")
    p.add_argument("--retrieval-only", action="store_true", help="measure search only (no API)")
    p.add_argument("--out", default=str(HERE / "results" / "latest.json"))
    p.add_argument("--keep", action="store_true", help="keep the temporary repos")
    args = p.parse_args()

    if not (args.oracle or args.retrieval_only):
        problems = build_config(args).problems()
        if problems:
            print("\n".join(problems), file=sys.stderr)
            return 2

    report = evaluate(args)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2))
    print("\n" + json.dumps(report["summary"], indent=2))
    print(f"\nFull results: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
