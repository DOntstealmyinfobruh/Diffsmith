# Diffsmith

**Plain-English request in, tested Git commit out.**

Diffsmith is an AI code-editing assistant. You describe a change ("add a `--pending` flag to the list command"). It finds the files that matter in your repository, asks a language model (Claude by default, or any OpenAI-compatible model, including free local ones) to write the edit, runs your project's own tests, and either commits the change or rolls it back.

```
$ diffsmith "Completing a task that is already done should raise a ValueError"
Searched 7 files; sent 6 to the model.
  attempt 1: committed taskq/store.py
Committed 3f9c2a1e7b: Raise when completing a finished task
```

## How it works

```
 request ──► 1. Search ──► 2. Edit ──► 3. Test gate ──► 4. Commit
               FAISS +       the model   project's        git commit
               BM25          writes      own tests        │
               picks the     SEARCH/       │ fail         │
               few files     REPLACE       ▼              │
               that matter   blocks     roll back, send   │
                                        test output back  │
                                        to model, retry ──┘
```

1. **Search.** Every file is split into overlapping 60-line chunks and embedded into a FAISS index. A BM25 keyword index runs alongside it, so rare identifiers like `from_str` count for more than common words. The two rankings are merged, and only the top files go to the model. The index is cached in `.git/diffsmith` and updated incrementally, so only changed files are re-embedded.
2. **Edit.** The model receives the request, a file listing, and the full text of the retrieved files. It replies with exact `SEARCH/REPLACE` blocks. It can ask for files it wasn't shown (`NEED_FILES:`) before editing. Edits that don't match the file exactly, match in more than one place, or point outside the repo are rejected.
3. **Test gate.** Diffsmith first checks that the test suite passes *before* the change; a suite that's already red can't judge an edit. After applying the edit, it runs the tests again. On failure it hard-resets the tree, including deleting new files, and sends the failing output back to the model for another attempt (2 attempts by default).
4. **Commit.** Only a passing edit is committed, with the model's commit message and the original request in the body.

## Install

```bash
git clone https://github.com/<you>/diffsmith && cd diffsmith
pip install -e ".[local-embeddings]"     # includes the free local embedding model
export ANTHROPIC_API_KEY=sk-ant-...      # or use a free model, see below
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

### Choosing a model

Claude is the default. Any server that speaks the OpenAI chat-completions format also works, and there are shortcuts for common ones:

| Provider | Cost | Setup |
|---|---|---|
| `anthropic` (default) | Paid API | `export ANTHROPIC_API_KEY=...` |
| `ollama` | Free, runs on your machine | Install [Ollama](https://ollama.com), then `ollama pull qwen2.5-coder:7b` |
| `groq` | Free tier | `export GROQ_API_KEY=...` |
| `openrouter` | Free models available | `export OPENROUTER_API_KEY=...` |
| `gemini` | Free tier | `export GEMINI_API_KEY=...` |
| `github` | Free tier (GitHub Models) | `export GITHUB_TOKEN=...` |
| `openai` | Paid API | `export OPENAI_API_KEY=...` |
| `openai-compatible` | Any other server (vLLM, LM Studio, ...) | `--base-url http://host/v1` |

```bash
diffsmith "add input validation" --provider ollama --model qwen2.5-coder:7b
diffsmith "add input validation" --provider groq --model llama-3.3-70b-versatile
```

Every provider except Claude needs `--model`. Free tiers hit rate limits often; Diffsmith waits and retries automatically. Smaller local models are cheaper but less reliable at precise edits, which the evaluation below measures.

The test command is detected automatically (pytest, `npm test`, `cargo test`, `go test`). Override it with `--test-command "make test"`.

**HTTP API:**

```bash
curl -X POST localhost:8000/edit -H 'content-type: application/json' \
     -d '{"repo": "/abs/path/to/repo", "request": "add a --verbose flag", "dry_run": true}'
```

The server can edit repositories on its own machine, so it listens on localhost only. It never accepts a test command from the request body, and `DIFFSMITH_ALLOWED_ROOTS=/path/a:/path/b` limits which repos it may touch.

| Setting | Default |
|---|---|
| `DIFFSMITH_PROVIDER` | `anthropic` |
| `DIFFSMITH_MODEL` | `claude-sonnet-5-5` for Claude; required otherwise |
| `DIFFSMITH_BASE_URL` | preset for the provider |
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
python eval/run_eval.py --provider ollama --model qwen2.5-coder:7b   # free, local
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
| **Full run, Gemini 3.8 Flash** (free tier) | **Tasks completed / broken edits blocked by the test gate** | **44/50 (88%) / 8 of 10 (80%)** |

In the full run, 8 of the 44 completed tasks passed only on the second attempt, after the test gate rolled back the first edit and sent the failure back to the model. Of the 6 failures, 2 were edits that passed the project's own tests but failed the hidden check (`tq-17`, `lg-09`); the other 4 never produced a passing edit, so nothing was committed. The run used 112,765 input and 27,683 output tokens. Because the free tier allows 20 requests a day, it ran over five days with `--resume`; results are in `eval/results/full-gemini-3.8-flash.json`.

Retrieval numbers above use the hashing fallback embedder (the only one available in the build environment); the local model should match or beat them. The context-reduction figure depends on repository size: in the unpadded 7-file fixtures, sending 6 files saves only about 8%. Raw JSON for each run is in `eval/results/`.

## Development

```bash
pip install -e ".[dev]"
pytest                        # 41 tests, offline: a scripted model and a fake OpenAI-style server
```

## License

MIT
