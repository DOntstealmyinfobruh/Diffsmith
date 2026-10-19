"""Command line: `diffsmith "add a --verbose flag"`, `diffsmith index`, `diffsmith serve`."""

from __future__ import annotations

import argparse
import json
import logging
import sys

from .config import PROVIDERS, Config


def _config_from_args(args: argparse.Namespace) -> Config:
    cfg = Config()
    if getattr(args, "provider", None):
        cfg.provider = args.provider
    if getattr(args, "base_url", None):
        cfg.base_url = args.base_url
    if getattr(args, "model", None):
        cfg.model = args.model
    if getattr(args, "embedder", None):
        cfg.embedder = args.embedder
    if getattr(args, "test_command", None):
        cfg.test_command = args.test_command
    if getattr(args, "no_tests", False):
        cfg.run_tests = False
    if getattr(args, "attempts", None):
        cfg.max_attempts = args.attempts
    if getattr(args, "top_k", None):
        cfg.top_k_files = args.top_k
    return cfg


def cmd_edit(args: argparse.Namespace) -> int:
    from .agent import Diffsmith
    from .gitops import GitError

    from .llm import LLMError

    cfg = _config_from_args(args)
    problems = cfg.problems()
    if problems:
        for p in problems:
            print(p, file=sys.stderr)
        if cfg.provider == "anthropic" and not cfg.resolved_api_key:
            print("Get a Claude API key at https://console.anthropic.com, or use a free "
                  "provider: --provider ollama --model qwen2.5-coder:7b", file=sys.stderr)
        return 2
    try:
        tool = Diffsmith(args.repo, cfg)
        result = tool.run(args.request, dry_run=args.dry_run, allow_dirty=args.allow_dirty)
    except GitError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    except LLMError as exc:
        print(f"Model error ({cfg.provider}): {exc}", file=sys.stderr)
        if cfg.provider == "ollama" and "Could not reach" in str(exc):
            print("Is Ollama running? Open the Ollama app or run `ollama serve`, and pull the "
                  f"model first: ollama pull {cfg.resolved_model}", file=sys.stderr)
        return 2
    except Exception as exc:  # Claude SDK failures: show the reason, not a traceback
        if type(exc).__module__.startswith("anthropic"):
            print(f"Claude API error: {exc}", file=sys.stderr)
            return 2
        raise

    if args.json:
        print(json.dumps(result.to_dict(), indent=2))
        return 0 if result.success else 1

    print(f"Searched {len(tool._index.file_sizes) if tool._index else 0} files; "
          f"sent {len(result.retrieved_files)} to the model "
          f"({result.context_reduction:.0%} less code than the whole repo).")
    for a in result.attempts:
        print(f"  attempt {a.number}: {a.outcome} {', '.join(a.files)}")
    if result.success:
        if result.commit:
            print(f"Committed {result.commit[:10]}: {result.message}")
        else:
            print(f"Dry run passed; nothing committed. Proposed: {result.message}")
        if args.show_diff or args.dry_run:
            print(result.diff)
        return 0
    print(f"No change made. {result.error}", file=sys.stderr)
    return 1


def cmd_index(args: argparse.Namespace) -> int:
    from .agent import Diffsmith
    from .llm import ScriptedClient

    tool = Diffsmith(args.repo, _config_from_args(args), llm=ScriptedClient([]))
    index = tool.index()
    print(f"Indexed {index.stats['files']} files in {index.stats['chunks']} chunks "
          f"({index.stats['embedded_chunks']} embedded, {index.stats['reused_chunks']} reused "
          f"from cache) with {tool._embedder.name}.")
    if args.query:
        for hit in index.search(args.query, top_k=args.top_k or 6):
            print(f"  {hit.score:.3f}  {hit.path}")
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    uvicorn.run("diffsmith.server:app", host=args.host, port=args.port)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="diffsmith", description=__doc__)
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="command")

    def common(sp):
        sp.add_argument("--repo", default=".", help="path to the git repository (default: .)")
        sp.add_argument("--embedder", choices=["auto", "local", "hashing"])
        sp.add_argument("--top-k", type=int, help="how many files to send to the model")

    e = sub.add_parser("edit", help="make a change from a plain-English request")
    e.add_argument("request")
    common(e)
    e.add_argument("--provider", choices=PROVIDERS,
                   help="who writes the edits (default: anthropic, i.e. Claude)")
    e.add_argument("--model", help="model name (default for Claude: claude-sonnet-5-5)")
    e.add_argument("--base-url", help="server URL for --provider openai-compatible")
    e.add_argument("--test-command", help="override the detected test command")
    e.add_argument("--no-tests", action="store_true", help="skip the test gate (not recommended)")
    e.add_argument("--attempts", type=int, help="max tries when tests fail (default 2)")
    e.add_argument("--dry-run", action="store_true", help="test the change but don't commit")
    e.add_argument("--allow-dirty", action="store_true",
                   help="run even with uncommitted changes (they may be lost on rollback)")
    e.add_argument("--show-diff", action="store_true")
    e.add_argument("--json", action="store_true")
    e.set_defaults(func=cmd_edit)

    i = sub.add_parser("index", help="build or refresh the search index")
    common(i)
    i.add_argument("--query", help="also show the files a request would retrieve")
    i.set_defaults(func=cmd_index)

    s = sub.add_parser("serve", help="run the HTTP API")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8000)
    s.set_defaults(func=cmd_serve)
    return p


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    # `diffsmith "do X"` is shorthand for `diffsmith edit "do X"`.
    if argv and argv[0] not in {"edit", "index", "serve", "-h", "--help", "-v", "--verbose"}:
        argv.insert(0, "edit")
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING,
                        format="%(levelname)s %(name)s: %(message)s")
    if not getattr(args, "func", None):
        build_parser().print_help()
        return 2
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
