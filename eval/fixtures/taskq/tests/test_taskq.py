from datetime import date

import pytest

from taskq.cli import run
from taskq.dates import is_overdue, parse_due
from taskq.formatting import format_list, format_task
from taskq.models import Task
from taskq.store import TaskNotFound, TaskStore


def test_add_and_list():
    s = TaskStore()
    s.add("write report")
    s.add("call bob", priority="high")
    assert [t.title for t in s.list()] == ["write report", "call bob"]


def test_complete_and_filter():
    s = TaskStore()
    a = s.add("a")
    s.add("b")
    s.complete(a.id)
    assert [t.title for t in s.list(include_done=False)] == ["b"]


def test_missing_task():
    with pytest.raises(TaskNotFound):
        TaskStore().get(99)


def test_validation():
    with pytest.raises(ValueError):
        Task(1, "  ")
    with pytest.raises(ValueError):
        Task(1, "x", priority="urgent")


def test_formatting():
    t = Task(3, "ship it", priority="high", due=date(2026, 1, 2))
    assert format_task(t) == "[ ] #3 ship it (!) due 2026-01-02"
    assert format_list([]) == "No tasks."


def test_dates():
    today = date(2026, 5, 1)
    assert parse_due("tomorrow", today) == date(2026, 5, 2)
    assert parse_due("2026-06-01") == date(2026, 6, 1)
    t = Task(1, "x", due=date(2026, 4, 30))
    assert is_overdue(t, today)


def test_cli():
    s = TaskStore()
    assert run(["add", "buy milk"], s) == "[ ] #1 buy milk"
    assert run(["done", "1"], s) == "[x] #1 buy milk"
    assert run(["list"], s) == "[x] #1 buy milk"
