# Diffsmith

**Plain-English request in, tested Git commit out.**

Diffsmith is an AI code-editing assistant. You describe a change ("add a `--pending` flag to the list command"). It finds the files that matter in your repository, asks Claude to write the edit, runs your project's own tests, and either commits the change or rolls it back.

```
$ diffsmith "Completing a task that is already done should raise a ValueError"
Searched 7 files; sent 6 to the model.
  attempt 1: committed taskq/store.py
Committed 3f9c2a1e7b: Raise when completing a finished task
```

## How it works

```
 request ──► 1. Search ──► 2. Edit ──► 3. Test gate ──► 4. Commit
               FAISS +       Claude      project's        git commit
               BM25          writes      own tests        │
               picks the     SEARCH/       │ fail         │
               few files     REPLACE       ▼              │
               that matter   blocks     roll back, send   │
                                        test output back  │
                                        to Claude, retry ─┘
```

1. **Search.** Every file is split into overlapping 60-line chunks and embedded into a FAISS index. A BM25 keyword index runs alongside it, so rare identifiers like `from_str` count for more than common words. The two rankings are merged, and only the top files go to the model. The index is cached in `.git/diffsmith` and updated incrementally, so only changed files are re-embedded.
2. **Edit.** Claude receives the request, a file listing, and the full text of the retrieved files. It replies with exact `SEARCH/REPLACE` blocks. It can ask for files it wasn't shown (`NEED_FILES:`) before editing. Edits that don't match the file exactly, match in more than one place, or point outside the repo are rejected.
3. **Test gate.** Diffsmith first checks that the test suite passes *before* the change; a suite that's already red can't judge an edit. After applying the edit, it runs the tests again. On failure it hard-resets the tree, including deleting new files, and sends the failing output back to Claude for another attempt (2 attempts by default).
4. **Commit.** Only a passing edit is committed, with Claude's commit message and the original request in the body.

## Install

```bash
git clone https://github.com/<you>/diffsmith && cd diffsmith
pip install -e ".[local-embeddings]"     # includes the free local embedding model
export ANTHROPIC_API_KEY=sk-ant-...
```

Python 3.10+. The local embedding model (`all-MiniLM-L6-v2`, about 90 MB) downloads on first use and then runs offline. Without `sentence-transformers` installed, Diffsmith falls back to a built-in hashing embedder that needs no download.

## Usage

```bash
cd your-repo                                  # must be a git repo with a clean tree
diffsmith "add input validation to apply_discount"
diffsmith "rename the --out flag to --output" --dry-run   # test it, don't commit
diffsmith "..." --show-diff --attempts 3
diffsmith index --query "where is the retry logic"        # see what search finds
diffsmith serve                                           # HTTP API on 127.0.0.1:8000
```

The test command is detected automatically (pytest, `npm test`, `cargo test`, `go test`). Override it with `--test-command "make test"`.

**HTTP API:**

```bash
curl -X POST localhost:8000/edit -H 'content-type: application/json' \
     -d '{"repo": "/abs/path/to/repo", "request": "add a --verbose flag", "dry_run": true}'
```

The server can edit repositories on its own machine, so it listens on localhost only. It never accepts a test command from the request body, and `DIFFSMITH_ALLOWED_ROOTS=/path/a:/path/b` limits which repos it may touch.

| Setting | Default |
|---|---|
| `DIFFSMITH_MODEL` | `claude-sonnet-5-5` |
| `DIFFSMITH_EMBEDDER` | `auto` (local model, else hashing) |
| `DIFFSMITH_TOP_K` | `6` files sent to the model |
| `DIFFSMITH_MAX_ATTEMPTS` | `2` |
| `DIFFSMITH_TEST_COMMAND` | auto-detected |

## Evaluation

`eval/` contains 50 tasks across three small Python projects (a to-do library, text utilities, and a money ledger): features, bug fixes, CLI changes, and a few changes that require updating existing tests. Each task has:

- a **hidden acceptance test** that Diffsmith never sees, run after the commit together with the project's own tests;
- a **reference solution**, used only to prove the task is solvable.

A task counts as **completed** only if Diffsmith committed a change and the hidden test plus the existing tests pass, with no human edits.

```bash
python eval/run_eval.py                         # full run with Claude (uses your API key)
python eval/run_eval.py --pad 10000             # same, with 10,000 filler files per repo
python eval/run_eval.py --retrieval-only --pad 10000   # search quality only, no API key
python eval/run_eval.py --oracle                # verify every task and check, no API key
```

### Results so far

| Run | What it shows | Result |
|---|---|---|
| `--oracle` | All 50 hidden checks fail on the original code and pass with the reference solution | 50/50 |
| `--retrieval-only`, no padding | Every file each task needs was found | 100% |
| `--retrieval-only`, +1,000 files | Needed files found / share of code *not* sent | 98% / 99.5% |
| `--retrieval-only`, +10,000 files | Needed files found / share of code *not* sent | 96% / 99.9% |
| **Full run with Claude** | **Completion rate, broken edits blocked** | ***run `python eval/run_eval.py` and fill in*** |

Retrieval numbers above use the hashing fallback embedder (the only one available in the build environment); the local model should match or beat them. The context-reduction figure depends on repository size: in the unpadded 7-file fixtures, sending 6 files saves only about 8%. Raw JSON for each run is in `eval/results/`.

## Development

```bash
pip install -e ".[dev]"
pytest                        # 27 tests, offline, use a scripted fake model
```

## License

MIT
