from conftest import git

from diffsmith.agent import Diffsmith
from diffsmith.llm import ScriptedClient

GOOD = """FILE: shop/pricing.py
<<<<<<< SEARCH
    return round(price * (1 - percent / 100), 2)
=======
    if not 0 <= percent <= 100:
        raise ValueError("percent must be between 0 and 100")
    return round(price * (1 - percent / 100), 2)
>>>>>>> REPLACE
COMMIT: Reject discounts outside 0-100
"""

# Breaks the existing test: 50% off 12.0 is no longer 6.0
BROKEN = """FILE: shop/pricing.py
<<<<<<< SEARCH
    return round(price * (1 - percent / 100), 2)
=======
    return round(price * (1 - percent / 10), 2)
>>>>>>> REPLACE
COMMIT: Oops
"""


def test_good_edit_is_committed(repo, config):
    llm = ScriptedClient([GOOD])
    result = Diffsmith(repo, config, llm=llm).run("reject discount percents outside 0-100")
    assert result.success and result.commit
    assert result.files_changed == ["shop/pricing.py"]
    assert result.tested
    log = git(repo, "log", "-1", "--format=%s")
    assert log.strip() == "Reject discounts outside 0-100"
    assert git(repo, "status", "--porcelain") == ""
    # only the relevant files went to the model
    assert "shop/pricing.py" in result.retrieved_files


def test_broken_edit_is_rolled_back_then_retried(repo, config):
    llm = ScriptedClient([BROKEN, GOOD])
    result = Diffsmith(repo, config, llm=llm).run("reject discount percents outside 0-100")
    assert [a.outcome for a in result.attempts] == ["tests_failed", "committed"]
    assert result.blocked_edits == 1
    # the retry prompt carried the failing test output back to the model
    assert "failed" in llm.calls[-1][-1]["content"]


def test_broken_edit_is_never_committed(repo, config):
    config.max_attempts = 1
    head_before = git(repo, "rev-parse", "HEAD")
    result = Diffsmith(repo, config, llm=ScriptedClient([BROKEN])).run("change the discount")
    assert not result.success
    assert git(repo, "rev-parse", "HEAD") == head_before
    assert git(repo, "status", "--porcelain") == ""
    assert "percent / 100" in (repo / "shop/pricing.py").read_text()


def test_bad_search_text_triggers_retry(repo, config):
    bad = "FILE: shop/pricing.py\n<<<<<<< SEARCH\nnope\n=======\nx\n>>>>>>> REPLACE\n"
    result = Diffsmith(repo, config, llm=ScriptedClient([bad, GOOD])).run("validate percent")
    assert [a.outcome for a in result.attempts] == ["edit_failed", "committed"]


def test_new_files_are_removed_on_rollback(repo, config):
    config.max_attempts = 1
    reply = ("FILE: shop/extra.py\n<<<<<<< SEARCH\n=======\nx = 1\n>>>>>>> REPLACE\n" + BROKEN)
    Diffsmith(repo, config, llm=ScriptedClient([reply])).run("something")
    assert not (repo / "shop/extra.py").exists()


def test_need_files_round(repo, config):
    ask = "NEED_FILES: README.md"
    llm = ScriptedClient([ask, GOOD])
    result = Diffsmith(repo, config, llm=llm).run("reject bad discounts")
    assert result.success
    assert "README.md" in result.retrieved_files


def test_dry_run_leaves_repo_untouched(repo, config):
    head_before = git(repo, "rev-parse", "HEAD")
    result = Diffsmith(repo, config, llm=ScriptedClient([GOOD])).run("x y z", dry_run=True)
    assert result.success and result.commit is None
    assert "ValueError" in result.diff
    assert git(repo, "rev-parse", "HEAD") == head_before
    assert git(repo, "status", "--porcelain") == ""


def test_refuses_dirty_tree(repo, config):
    (repo / "README.md").write_text("changed\n")
    result = Diffsmith(repo, config, llm=ScriptedClient([GOOD])).run("anything")
    assert not result.success and "uncommitted" in result.error


def test_refuses_when_baseline_tests_fail(repo, config):
    (repo / "tests" / "test_bad.py").write_text("def test_bad():\n    assert False\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "add failing test")
    result = Diffsmith(repo, config, llm=ScriptedClient([GOOD])).run("anything")
    assert not result.success and "already fails" in result.error


def test_context_reduction_is_measured(repo, config):
    config.top_k_files = 1
    result = Diffsmith(repo, config, llm=ScriptedClient([GOOD])).run("apply_discount percent")
    assert 0 < result.context_chars < result.repo_chars
    assert 0 < result.context_reduction < 1
