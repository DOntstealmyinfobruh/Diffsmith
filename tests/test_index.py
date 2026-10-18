from diffsmith.embeddings import HashingEmbedder, tokenize
from diffsmith.gitops import GitRepo
from diffsmith.index import CodeIndex, chunk_text


def test_tokenize_splits_identifiers():
    assert tokenize("getUserName apply_discount HTTPServer") == [
        "get", "user", "name", "apply", "discount", "http", "server"]


def test_chunking_overlaps_and_covers_file():
    text = "\n".join(f"line {i}" for i in range(1, 131))
    chunks = chunk_text("a.py", text, size=60, overlap=10)
    assert [(c.start, c.end) for c in chunks] == [(1, 60), (51, 110), (101, 130)]


def test_search_finds_relevant_file(repo):
    index = CodeIndex(GitRepo(repo), HashingEmbedder()).build()
    hits = index.search("validate the discount percent in apply_discount", top_k=2)
    assert hits[0].path == "shop/pricing.py"


def test_index_cache_is_incremental(repo):
    gr = GitRepo(repo)
    first = CodeIndex(gr, HashingEmbedder()).build()
    assert first.stats["reused_chunks"] == 0

    second = CodeIndex(gr, HashingEmbedder()).build()
    assert second.stats["embedded_chunks"] == 0

    (repo / "shop" / "pricing.py").write_text("def apply_discount(p, d):\n    return p\n")
    third = CodeIndex(gr, HashingEmbedder()).build()
    assert third.stats["embedded_chunks"] == 1
    # results stay correct after a partial refresh
    assert "shop/cart.py" in [h.path for h in third.search("Cart class total items", top_k=2)]


def test_cache_is_not_committed(repo):
    gr = GitRepo(repo)
    CodeIndex(gr, HashingEmbedder()).build()
    assert gr.is_clean()
