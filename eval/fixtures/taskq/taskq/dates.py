from datetime import date, timedelta


def parse_due(text, today=None):
    """Parse 'today', 'tomorrow', or an ISO date like 2026-01-31."""
    today = today or date.today()
    text = text.strip().lower()
    if text == "today":
        return today
    if text == "tomorrow":
        return today + timedelta(days=1)
    return date.fromisoformat(text)


def is_overdue(task, today=None):
    today = today or date.today()
    return bool(task.due) and not task.done and task.due < today
