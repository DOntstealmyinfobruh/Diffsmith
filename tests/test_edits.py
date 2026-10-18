import pytest

from diffsmith.edits import (EditError, apply_edits, parse_commit_message, parse_edits,
                             parse_needed_files)

REPLY = """Here is the change.

FILE: shop/pricing.py
<<<<<<< SEARCH
    return round(price * (1 - percent / 100), 2)
=======
    if not 0 <= percent <= 100:
        raise ValueError("percent must be between 0 and 100")
    return round(price * (1 - percent / 100), 2)
>>>>>>> REPLACE

FILE: shop/tax.py
<<<<<<< SEARCH
=======
TAX_RATE = 0.08
>>>>>>> REPLACE

COMMIT: Validate discount percent and add tax rate
"""


def test_parse_blocks_and_commit():
    edits = parse_edits(REPLY)
    assert [e.path for e in edits] == ["shop/pricing.py", "shop/tax.py"]
    assert edits[1].search == ""
    assert parse_commit_message(REPLY) == "Validate discount percent and add tax rate"


def test_parse_needed_files():
    assert parse_needed_files("NEED_FILES: a.py, `b/c.py`") == ["a.py", "b/c.py"]
    assert parse_needed_files("nothing") == []


def test_apply_edits(repo):
    changed = apply_edits(repo, parse_edits(REPLY))
    assert changed == ["shop/pricing.py", "shop/tax.py"]
    assert "ValueError" in (repo / "shop/pricing.py").read_text()
    assert (repo / "shop/tax.py").read_text() == "TAX_RATE = 0.08\n"


def test_trailing_whitespace_is_tolerated(repo):
    reply = REPLY.replace("    return round(price * (1 - percent / 100), 2)\n=======",
                          "    return round(price * (1 - percent / 100), 2)   \n=======")
    apply_edits(repo, parse_edits(reply)[:1])
    assert "ValueError" in (repo / "shop/pricing.py").read_text()


def test_missing_search_text_raises(repo):
    bad = "FILE: shop/pricing.py\n<<<<<<< SEARCH\nnot in file\n=======\nx\n>>>>>>> REPLACE\n"
    with pytest.raises(EditError, match="not found"):
        apply_edits(repo, parse_edits(bad))


def test_ambiguous_search_text_raises(repo):
    (repo / "dup.py").write_text("x = 1\nx = 1\n")
    bad = "FILE: dup.py\n<<<<<<< SEARCH\nx = 1\n=======\nx = 2\n>>>>>>> REPLACE\n"
    with pytest.raises(EditError, match="2 places"):
        apply_edits(repo, parse_edits(bad))


@pytest.mark.parametrize("path", ["../evil.py", ".git/config"])
def test_refuses_paths_outside_repo(repo, path):
    bad = f"FILE: {path}\n<<<<<<< SEARCH\n=======\nboom\n>>>>>>> REPLACE\n"
    with pytest.raises(EditError):
        apply_edits(repo, parse_edits(bad))
