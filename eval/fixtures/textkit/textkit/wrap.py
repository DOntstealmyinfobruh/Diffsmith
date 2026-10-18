def wrap(text, width=40):
    """Greedy word wrap. Returns a list of lines."""
    lines, current = [], ""
    for word in text.split():
        candidate = f"{current} {word}" if current else word
        if len(candidate) <= width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def truncate(text, limit):
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."
