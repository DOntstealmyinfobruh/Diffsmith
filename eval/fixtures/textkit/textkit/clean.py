import re


def collapse_whitespace(text):
    return re.sub(r"\s+", " ", text).strip()


def strip_html(text):
    return re.sub(r"<[^>]+>", "", text)
