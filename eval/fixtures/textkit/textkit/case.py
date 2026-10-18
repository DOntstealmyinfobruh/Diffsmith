import re


def to_snake(name):
    """'parseHttpRequest' -> 'parse_http_request'"""
    name = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name)
    return name.replace("-", "_").lower()


def to_camel(name):
    """'parse_http_request' -> 'parseHttpRequest'"""
    head, *rest = name.split("_")
    return head.lower() + "".join(word.capitalize() for word in rest)
