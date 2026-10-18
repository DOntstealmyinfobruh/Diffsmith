from textkit.case import to_camel, to_snake
from textkit.clean import collapse_whitespace, strip_html
from textkit.slug import slugify
from textkit.stats import reading_time_minutes, top_words, word_count
from textkit.wrap import truncate, wrap


def test_slugify():
    assert slugify("Hello, World!") == "hello-world"
    assert slugify("  Spaces  ") == "spaces"


def test_case():
    assert to_snake("parseHttpRequest") == "parse_http_request"
    assert to_camel("parse_http_request") == "parseHttpRequest"


def test_stats():
    text = "the cat and the hat and the bat"
    assert word_count(text) == 8
    assert top_words(text, 2) == ["the", "and"]
    assert reading_time_minutes("word " * 450) == 2


def test_wrap():
    assert wrap("one two three four", width=9) == ["one two", "three", "four"]
    assert truncate("abcdefghij", 8) == "abcde..."
    assert truncate("short", 8) == "short"


def test_clean():
    assert collapse_whitespace("  a \n\t b  ") == "a b"
    assert strip_html("<b>hi</b> there") == "hi there"
