r"""The 50 evaluation tasks.

Each task has:
- fixture:  which project in eval/fixtures it runs against
- request:  the plain-English request Diffsmith receives
- files:    files a correct change is expected to touch (for retrieval recall)
- check:    a hidden acceptance test. Diffsmith never sees it. It runs after the
            commit, together with the project's own tests.
- solution: a reference answer in Diffsmith's SEARCH/REPLACE format. It is used
            only by `run_eval.py --oracle` to prove each task is solvable and its
            check is correct. It is never shown to the model.
"""

TASKS = [
    # ------------------------------------------------------------------ taskq
    dict(
        id="tq-01", fixture="taskq", files=["taskq/store.py"],
        request="Add a clear_done() method to TaskStore that removes all completed tasks and returns how many it removed.",
        check=r'''
from taskq.store import TaskStore
def test_clear_done():
    s = TaskStore(); a = s.add("a"); s.add("b"); s.complete(a.id)
    assert s.clear_done() == 1
    assert [t.title for t in s.list()] == ["b"]
    assert s.clear_done() == 0
''',
        solution=r'''FILE: taskq/store.py
<<<<<<< SEARCH
    def list(self, include_done=True):
=======
    def clear_done(self):
        done = [t.id for t in self._tasks.values() if t.done]
        for task_id in done:
            del self._tasks[task_id]
        return len(done)

    def list(self, include_done=True):
>>>>>>> REPLACE
COMMIT: Add TaskStore.clear_done
'''),
    dict(
        id="tq-02", fixture="taskq", files=["taskq/models.py", "taskq/formatting.py", "tests/test_taskq.py"],
        request='Support a new "urgent" priority above "high". Urgent tasks should be marked with "(!!)" when formatted, the way high-priority tasks get "(!)".',
        check=r'''
from taskq.models import Task
from taskq.formatting import format_task
def test_urgent():
    assert format_task(Task(2, "y", priority="urgent")) == "[ ] #2 y (!!)"
    assert format_task(Task(3, "z", priority="high")) == "[ ] #3 z (!)"
''',
        solution=r'''FILE: taskq/models.py
<<<<<<< SEARCH
PRIORITIES = ("low", "normal", "high")
=======
PRIORITIES = ("low", "normal", "high", "urgent")
>>>>>>> REPLACE
FILE: taskq/formatting.py
<<<<<<< SEARCH
    if task.priority == "high":
        line += " (!)"
=======
    if task.priority == "high":
        line += " (!)"
    elif task.priority == "urgent":
        line += " (!!)"
>>>>>>> REPLACE
FILE: tests/test_taskq.py
<<<<<<< SEARCH
        Task(1, "x", priority="urgent")
=======
        Task(1, "x", priority="critical")
>>>>>>> REPLACE
COMMIT: Add urgent priority
'''),
    dict(
        id="tq-03", fixture="taskq", files=["taskq/models.py"],
        request="Task titles should have leading and trailing whitespace stripped when a task is created.",
        check=r'''
from taskq.store import TaskStore
def test_strip():
    assert TaskStore().add("  milk \n").title == "milk"
''',
        solution=r'''FILE: taskq/models.py
<<<<<<< SEARCH
        if not self.title.strip():
            raise ValueError("title must not be empty")
=======
        if not self.title.strip():
            raise ValueError("title must not be empty")
        self.title = self.title.strip()
>>>>>>> REPLACE
COMMIT: Strip whitespace from task titles
'''),
    dict(
        id="tq-04", fixture="taskq", files=["taskq/store.py"],
        request="Add rename(task_id, new_title) to TaskStore. It returns the task, and raises ValueError if the new title is empty or only whitespace.",
        check=r'''
import pytest
from taskq.store import TaskStore, TaskNotFound
def test_rename():
    s = TaskStore(); t = s.add("old")
    assert s.rename(t.id, "new").title == "new"
    assert s.get(t.id).title == "new"
    with pytest.raises(ValueError):
        s.rename(t.id, "   ")
    with pytest.raises(TaskNotFound):
        s.rename(42, "x")
''',
        solution=r'''FILE: taskq/store.py
<<<<<<< SEARCH
    def delete(self, task_id):
=======
    def rename(self, task_id, new_title):
        task = self.get(task_id)
        if not new_title.strip():
            raise ValueError("title must not be empty")
        task.title = new_title
        return task

    def delete(self, task_id):
>>>>>>> REPLACE
COMMIT: Add TaskStore.rename
'''),
    dict(
        id="tq-05", fixture="taskq", files=["taskq/dates.py"],
        request='Make parse_due understand "yesterday" too.',
        check=r'''
from datetime import date
from taskq.dates import parse_due
def test_yesterday():
    assert parse_due("Yesterday", date(2026, 3, 1)) == date(2026, 2, 28)
''',
        solution=r'''FILE: taskq/dates.py
<<<<<<< SEARCH
    if text == "tomorrow":
=======
    if text == "yesterday":
        return today - timedelta(days=1)
    if text == "tomorrow":
>>>>>>> REPLACE
COMMIT: Accept "yesterday" in parse_due
'''),
    dict(
        id="tq-06", fixture="taskq", files=["taskq/dates.py"],
        request='parse_due should accept relative dates like "in 3 days" or "in 1 day".',
        check=r'''
from datetime import date
from taskq.dates import parse_due
def test_in_days():
    today = date(2026, 5, 1)
    assert parse_due("in 3 days", today) == date(2026, 5, 4)
    assert parse_due("in 1 day", today) == date(2026, 5, 2)
    assert parse_due("today", today) == today
''',
        solution=r'''FILE: taskq/dates.py
<<<<<<< SEARCH
from datetime import date, timedelta
=======
import re
from datetime import date, timedelta
>>>>>>> REPLACE
FILE: taskq/dates.py
<<<<<<< SEARCH
    return date.fromisoformat(text)
=======
    m = re.fullmatch(r"in (\d+) days?", text)
    if m:
        return today + timedelta(days=int(m.group(1)))
    return date.fromisoformat(text)
>>>>>>> REPLACE
COMMIT: Accept "in N days" in parse_due
'''),
    dict(
        id="tq-07", fixture="taskq", files=["taskq/store.py"],
        request="Add TaskStore.overdue(today=None) that returns unfinished tasks whose due date has passed, sorted by due date (earliest first).",
        check=r'''
from datetime import date
from taskq.store import TaskStore
def test_overdue():
    s = TaskStore()
    s.add("late2", due=date(2026, 1, 5))
    s.add("late1", due=date(2026, 1, 2))
    s.add("future", due=date(2026, 3, 1))
    done = s.add("done", due=date(2026, 1, 1)); s.complete(done.id)
    s.add("nodue")
    assert [t.title for t in s.overdue(today=date(2026, 2, 1))] == ["late1", "late2"]
''',
        solution=r'''FILE: taskq/store.py
<<<<<<< SEARCH
from taskq.models import Task
=======
from taskq.dates import is_overdue
from taskq.models import Task
>>>>>>> REPLACE
FILE: taskq/store.py
<<<<<<< SEARCH
    def list(self, include_done=True):
=======
    def overdue(self, today=None):
        late = [t for t in self._tasks.values() if is_overdue(t, today)]
        return sorted(late, key=lambda t: (t.due, t.id))

    def list(self, include_done=True):
>>>>>>> REPLACE
COMMIT: Add TaskStore.overdue
'''),
    dict(
        id="tq-08", fixture="taskq", files=["taskq/store.py"],
        request="Add a find(text) method to TaskStore that returns tasks whose title contains the text, ignoring case, ordered by id.",
        check=r'''
from taskq.store import TaskStore
def test_find():
    s = TaskStore(); s.add("Buy milk"); s.add("call Bob"); s.add("MILK the cow")
    assert [t.id for t in s.find("milk")] == [1, 3]
    assert s.find("zzz") == []
''',
        solution=r'''FILE: taskq/store.py
<<<<<<< SEARCH
    def list(self, include_done=True):
=======
    def find(self, text):
        needle = text.lower()
        return [t for t in self.list() if needle in t.title.lower()]

    def list(self, include_done=True):
>>>>>>> REPLACE
COMMIT: Add TaskStore.find
'''),
    dict(
        id="tq-09", fixture="taskq", files=["taskq/formatting.py"],
        request="When formatting a task, show its tags at the very end of the line in square brackets, comma separated, like `[ ] #1 milk [home, errands]`. Tasks without tags should look exactly as they do now.",
        check=r'''
from datetime import date
from taskq.models import Task
from taskq.formatting import format_task
def test_tags():
    t = Task(1, "a", due=date(2026, 1, 2), tags=["x", "y"])
    assert format_task(t) == "[ ] #1 a due 2026-01-02 [x, y]"
    assert format_task(Task(2, "b")) == "[ ] #2 b"
''',
        solution=r'''FILE: taskq/formatting.py
<<<<<<< SEARCH
        line += f" due {task.due.isoformat()}"
    return line
=======
        line += f" due {task.due.isoformat()}"
    if task.tags:
        line += f" [{', '.join(task.tags)}]"
    return line
>>>>>>> REPLACE
COMMIT: Show tags in formatted tasks
'''),
    dict(
        id="tq-10", fixture="taskq", files=["taskq/cli.py"],
        request='Add a `delete <id>` command to the CLI. It deletes the task and outputs "Deleted #<id>".',
        check=r'''
from taskq.cli import run
from taskq.store import TaskStore
def test_delete_cmd():
    s = TaskStore(); run(["add", "a"], s); run(["add", "b"], s)
    assert run(["delete", "1"], s) == "Deleted #1"
    assert [t.title for t in s.list()] == ["b"]
''',
        solution=r'''FILE: taskq/cli.py
<<<<<<< SEARCH
    done.add_argument("id", type=int)
    return parser
=======
    done.add_argument("id", type=int)

    delete = sub.add_parser("delete")
    delete.add_argument("id", type=int)
    return parser
>>>>>>> REPLACE
FILE: taskq/cli.py
<<<<<<< SEARCH
    raise AssertionError(args.command)
=======
    if args.command == "delete":
        store.delete(args.id)
        return f"Deleted #{args.id}"
    raise AssertionError(args.command)
>>>>>>> REPLACE
COMMIT: Add delete command to CLI
'''),
    dict(
        id="tq-11", fixture="taskq", files=["taskq/cli.py"],
        request="Add a --pending flag to the CLI's list command so it shows only tasks that aren't done.",
        check=r'''
from taskq.cli import run
from taskq.store import TaskStore
def test_pending():
    s = TaskStore(); run(["add", "a"], s); run(["add", "b"], s); run(["done", "1"], s)
    assert run(["list", "--pending"], s) == "[ ] #2 b"
    assert len(run(["list"], s).splitlines()) == 2
''',
        solution=r'''FILE: taskq/cli.py
<<<<<<< SEARCH
    sub.add_parser("list")
=======
    lst = sub.add_parser("list")
    lst.add_argument("--pending", action="store_true")
>>>>>>> REPLACE
FILE: taskq/cli.py
<<<<<<< SEARCH
        return format_list(store.list())
=======
        return format_list(store.list(include_done=not args.pending))
>>>>>>> REPLACE
COMMIT: Add --pending to list command
'''),
    dict(
        id="tq-12", fixture="taskq", files=["taskq/cli.py"],
        request="Let the CLI's add command take a --tag option that can be repeated to attach several tags.",
        check=r'''
from taskq.cli import run
from taskq.store import TaskStore
def test_tags_cli():
    s = TaskStore()
    run(["add", "milk", "--tag", "home", "--tag", "errands"], s)
    run(["add", "plain"], s)
    assert s.get(1).tags == ["home", "errands"]
    assert s.get(2).tags == []
''',
        solution=r'''FILE: taskq/cli.py
<<<<<<< SEARCH
    add.add_argument("--due")
=======
    add.add_argument("--due")
    add.add_argument("--tag", action="append", default=[])
>>>>>>> REPLACE
FILE: taskq/cli.py
<<<<<<< SEARCH
        return format_task(store.add(args.title, args.priority, due=due))
=======
        return format_task(store.add(args.title, args.priority, due=due, tags=args.tag))
>>>>>>> REPLACE
COMMIT: Add repeatable --tag option to add command
'''),
    dict(
        id="tq-13", fixture="taskq", files=["taskq/store.py"],
        request="Add JSON persistence: TaskStore.save(path) writes all tasks to a JSON file, and a TaskStore.load(path) classmethod reads them back, keeping ids, done status, priority, tags and due dates. New tasks added after loading must get ids that don't collide.",
        check=r'''
from datetime import date
from taskq.store import TaskStore
def test_roundtrip(tmp_path):
    s = TaskStore()
    s.add("a", priority="high", due=date(2026, 1, 2), tags=["x"])
    b = s.add("b"); s.complete(b.id); s.add("c"); s.delete(3)
    p = tmp_path / "tasks.json"
    s.save(p)
    t = TaskStore.load(p)
    assert [(x.id, x.title, x.priority, x.done, x.due, x.tags) for x in t.list()] == [
        (1, "a", "high", False, date(2026, 1, 2), ["x"]), (2, "b", "normal", True, None, [])]
    assert t.add("d").id == 3
''',
        solution=r'''FILE: taskq/store.py
<<<<<<< SEARCH
from taskq.models import Task
=======
import json
from datetime import date

from taskq.models import Task
>>>>>>> REPLACE
FILE: taskq/store.py
<<<<<<< SEARCH
    def list(self, include_done=True):
=======
    def save(self, path):
        data = [
            {"id": t.id, "title": t.title, "priority": t.priority, "done": t.done,
             "due": t.due.isoformat() if t.due else None, "tags": t.tags}
            for t in self.list()
        ]
        with open(path, "w") as fh:
            json.dump(data, fh)

    @classmethod
    def load(cls, path):
        store = cls()
        with open(path) as fh:
            for row in json.load(fh):
                due = date.fromisoformat(row["due"]) if row["due"] else None
                task = Task(row["id"], row["title"], row["priority"], row["done"], due, row["tags"])
                store._tasks[task.id] = task
        store._next_id = max(store._tasks, default=0) + 1
        return store

    def list(self, include_done=True):
>>>>>>> REPLACE
COMMIT: Add JSON save and load to TaskStore
'''),
    dict(
        id="tq-14", fixture="taskq", files=["taskq/formatting.py"],
        request='Add a summary(tasks) function to the formatting module that returns text like "3 tasks, 1 done". Use "1 task" (singular) when there is exactly one task.',
        check=r'''
from taskq.models import Task
from taskq.formatting import summary
def test_summary():
    a, b, c = Task(1, "a"), Task(2, "b", done=True), Task(3, "c")
    assert summary([a, b, c]) == "3 tasks, 1 done"
    assert summary([b]) == "1 task, 1 done"
    assert summary([]) == "0 tasks, 0 done"
''',
        solution=r'''FILE: taskq/formatting.py
<<<<<<< SEARCH
def format_list(tasks):
=======
def summary(tasks):
    n = len(tasks)
    done = sum(t.done for t in tasks)
    return f"{n} task{'' if n == 1 else 's'}, {done} done"


def format_list(tasks):
>>>>>>> REPLACE
COMMIT: Add summary() to formatting
'''),
    dict(
        id="tq-15", fixture="taskq", files=["taskq/store.py"],
        request='Let TaskStore.list take sort="priority" to order tasks by priority (most important first), breaking ties by id. The default order stays by id.',
        check=r'''
from taskq.store import TaskStore
def test_sort():
    s = TaskStore(); s.add("a", "low"); s.add("b", "high"); s.add("c"); s.add("d", "high")
    assert [t.title for t in s.list(sort="priority")] == ["b", "d", "c", "a"]
    assert [t.title for t in s.list()] == ["a", "b", "c", "d"]
''',
        solution=r'''FILE: taskq/store.py
<<<<<<< SEARCH
from taskq.models import Task
=======
from taskq.models import PRIORITIES, Task
>>>>>>> REPLACE
FILE: taskq/store.py
<<<<<<< SEARCH
    def list(self, include_done=True):
        tasks = sorted(self._tasks.values(), key=lambda t: t.id)
=======
    def list(self, include_done=True, sort="id"):
        tasks = sorted(self._tasks.values(), key=lambda t: t.id)
        if sort == "priority":
            tasks.sort(key=lambda t: -PRIORITIES.index(t.priority))
>>>>>>> REPLACE
COMMIT: Add priority sort to TaskStore.list
'''),
    dict(
        id="tq-16", fixture="taskq", files=["taskq/store.py"],
        request="Completing a task that is already done should raise a ValueError instead of silently succeeding.",
        check=r'''
import pytest
from taskq.store import TaskStore
def test_double_complete():
    s = TaskStore(); t = s.add("a"); s.complete(t.id)
    with pytest.raises(ValueError):
        s.complete(t.id)
''',
        solution=r'''FILE: taskq/store.py
<<<<<<< SEARCH
        task = self.get(task_id)
        task.done = True
=======
        task = self.get(task_id)
        if task.done:
            raise ValueError(f"task {task_id} is already done")
        task.done = True
>>>>>>> REPLACE
COMMIT: Raise when completing a finished task
'''),
    dict(
        id="tq-17", fixture="taskq", files=["taskq/store.py", "taskq/cli.py"],
        request="Add an uncomplete(task_id) method to TaskStore that marks a task as not done, and an `undo <id>` CLI command that calls it and prints the task.",
        check=r'''
from taskq.cli import run
from taskq.store import TaskStore
def test_undo():
    s = TaskStore(); run(["add", "a"], s); run(["done", "1"], s)
    assert run(["undo", "1"], s) == "[ ] #1 a"
    assert s.uncomplete(1).done is False
''',
        solution=r'''FILE: taskq/store.py
<<<<<<< SEARCH
    def delete(self, task_id):
=======
    def uncomplete(self, task_id):
        task = self.get(task_id)
        task.done = False
        return task

    def delete(self, task_id):
>>>>>>> REPLACE
FILE: taskq/cli.py
<<<<<<< SEARCH
    done.add_argument("id", type=int)
    return parser
=======
    done.add_argument("id", type=int)

    undo = sub.add_parser("undo")
    undo.add_argument("id", type=int)
    return parser
>>>>>>> REPLACE
FILE: taskq/cli.py
<<<<<<< SEARCH
    raise AssertionError(args.command)
=======
    if args.command == "undo":
        return format_task(store.uncomplete(args.id))
    raise AssertionError(args.command)
>>>>>>> REPLACE
COMMIT: Add uncomplete and undo command
'''),

    # ---------------------------------------------------------------- textkit
    dict(
        id="tk-01", fixture="textkit", files=["textkit/slug.py"],
        request='slugify should turn accented letters into plain ASCII, so "Café Déjà Vu" becomes "cafe-deja-vu".',
        check=r'''
from textkit.slug import slugify
def test_accents():
    assert slugify("Café Déjà Vu") == "cafe-deja-vu"
    assert slugify("Hello, World!") == "hello-world"
''',
        solution=r'''FILE: textkit/slug.py
<<<<<<< SEARCH
import re


def slugify(text):
    """'Hello, World!' -> 'hello-world'"""
    text = text.lower()
=======
import re
import unicodedata


def slugify(text):
    """'Hello, World!' -> 'hello-world'"""
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = text.lower()
>>>>>>> REPLACE
COMMIT: Transliterate accents in slugify
'''),
    dict(
        id="tk-02", fixture="textkit", files=["textkit/slug.py"],
        request="Add an optional max_length argument to slugify. Cut the slug to at most that many characters, and never leave a hyphen at the end after cutting.",
        check=r'''
from textkit.slug import slugify
def test_max_length():
    assert slugify("hello big world", max_length=9) == "hello-big"
    assert slugify("hello big world", max_length=6) == "hello"
    assert slugify("hello big world") == "hello-big-world"
''',
        solution=r'''FILE: textkit/slug.py
<<<<<<< SEARCH
def slugify(text):
    """'Hello, World!' -> 'hello-world'"""
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")
=======
def slugify(text, max_length=None):
    """'Hello, World!' -> 'hello-world'"""
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = text.strip("-")
    if max_length is not None:
        text = text[:max_length].rstrip("-")
    return text
>>>>>>> REPLACE
COMMIT: Add max_length to slugify
'''),
    dict(
        id="tk-03", fixture="textkit", files=["textkit/slug.py"],
        request='Let slugify take a sep argument for the separator, defaulting to "-". For example slugify("Hello World", sep="_") gives "hello_world".',
        check=r'''
from textkit.slug import slugify
def test_sep():
    assert slugify("Hello,  World!", sep="_") == "hello_world"
    assert slugify("Hello World") == "hello-world"
''',
        solution=r'''FILE: textkit/slug.py
<<<<<<< SEARCH
def slugify(text):
    """'Hello, World!' -> 'hello-world'"""
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")
=======
def slugify(text, sep="-"):
    """'Hello, World!' -> 'hello-world'"""
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", sep, text)
    return text.strip(sep)
>>>>>>> REPLACE
COMMIT: Add sep argument to slugify
'''),
    dict(
        id="tk-04", fixture="textkit", files=["textkit/case.py"],
        request='to_snake mishandles acronyms: "parseHTTPRequest" should become "parse_http_request" and "HTTPServer" should become "http_server".',
        check=r'''
from textkit.case import to_snake
def test_acronyms():
    assert to_snake("parseHTTPRequest") == "parse_http_request"
    assert to_snake("HTTPServer") == "http_server"
    assert to_snake("parseHttpRequest") == "parse_http_request"
    assert to_snake("getID") == "get_id"
''',
        solution=r'''FILE: textkit/case.py
<<<<<<< SEARCH
    name = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name)
=======
    name = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", name)
    name = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name)
>>>>>>> REPLACE
COMMIT: Handle acronyms in to_snake
'''),
    dict(
        id="tk-05", fixture="textkit", files=["textkit/case.py"],
        request='to_camel should also accept kebab-case and space-separated words, e.g. "parse-http request" -> "parseHttpRequest".',
        check=r'''
from textkit.case import to_camel
def test_camel_inputs():
    assert to_camel("parse-http request") == "parseHttpRequest"
    assert to_camel("parse_http_request") == "parseHttpRequest"
''',
        solution=r'''FILE: textkit/case.py
<<<<<<< SEARCH
    head, *rest = name.split("_")
=======
    head, *rest = re.split(r"[_\-\s]+", name.strip())
>>>>>>> REPLACE
COMMIT: Accept kebab and spaced input in to_camel
'''),
    dict(
        id="tk-06", fixture="textkit", files=["textkit/case.py"],
        request='Add a to_pascal function to the case module: "parse_http_request" -> "ParseHttpRequest".',
        check=r'''
from textkit.case import to_pascal
def test_pascal():
    assert to_pascal("parse_http_request") == "ParseHttpRequest"
    assert to_pascal("word") == "Word"
''',
        solution=r'''FILE: textkit/case.py
<<<<<<< SEARCH
def to_camel(name):
=======
def to_pascal(name):
    """'parse_http_request' -> 'ParseHttpRequest'"""
    return "".join(word.capitalize() for word in name.split("_"))


def to_camel(name):
>>>>>>> REPLACE
COMMIT: Add to_pascal
'''),
    dict(
        id="tk-07", fixture="textkit", files=["textkit/case.py"],
        request='Add to_kebab(name) that converts camelCase or snake_case to kebab-case: "parseHttpRequest" -> "parse-http-request".',
        check=r'''
from textkit.case import to_kebab
def test_kebab():
    assert to_kebab("parseHttpRequest") == "parse-http-request"
    assert to_kebab("parse_http_request") == "parse-http-request"
''',
        solution=r'''FILE: textkit/case.py
<<<<<<< SEARCH
def to_camel(name):
=======
def to_kebab(name):
    """'parseHttpRequest' -> 'parse-http-request'"""
    return to_snake(name).replace("_", "-")


def to_camel(name):
>>>>>>> REPLACE
COMMIT: Add to_kebab
'''),
    dict(
        id="tk-08", fixture="textkit", files=["textkit/stats.py"],
        request='word_count should treat hyphenated words like "well-known" as one word, and count numbers and words with digits ("2026", "3D") as words.',
        check=r'''
from textkit.stats import word_count, top_words
def test_words():
    assert word_count("a state-of-the-art 3D tool from 2026") == 6
    assert word_count("state-of-the-art tool 2026") == 3
    assert word_count("don't stop") == 2
    assert top_words("the cat and the hat and the bat", 2) == ["the", "and"]
''',
        solution=r'''FILE: textkit/stats.py
<<<<<<< SEARCH
WORD = re.compile(r"[A-Za-z']+")
=======
WORD = re.compile(r"[A-Za-z0-9]+(?:['-][A-Za-z0-9]+)*")
>>>>>>> REPLACE
COMMIT: Count hyphenated words and numbers as words
'''),
    dict(
        id="tk-09", fixture="textkit", files=["textkit/stats.py"],
        request="Give top_words a skip_stopwords flag (default False). When it's on, ignore the words the, a, an, and, or, of, to and in.",
        check=r'''
from textkit.stats import top_words
def test_stopwords():
    text = "the cat and the hat and the cat"
    assert top_words(text, 1, skip_stopwords=True) == ["cat"]
    assert top_words(text, 1) == ["the"]
''',
        solution=r'''FILE: textkit/stats.py
<<<<<<< SEARCH
def top_words(text, n=3):
    counts = Counter(w.lower() for w in words(text))
=======
STOPWORDS = {"the", "a", "an", "and", "or", "of", "to", "in"}


def top_words(text, n=3, skip_stopwords=False):
    counts = Counter(w.lower() for w in words(text))
    if skip_stopwords:
        for w in STOPWORDS:
            counts.pop(w, None)
>>>>>>> REPLACE
COMMIT: Add skip_stopwords to top_words
'''),
    dict(
        id="tk-10", fixture="textkit", files=["textkit/stats.py"],
        request="Add sentence_count(text) to the stats module. Sentences end with . ! or ?; text without an ending mark still counts as one sentence, and empty text has zero.",
        check=r'''
from textkit.stats import sentence_count
def test_sentences():
    assert sentence_count("Hi. How are you? Great!") == 3
    assert sentence_count("No end") == 1
    assert sentence_count("Wait... what?!") == 2
    assert sentence_count("   ") == 0
''',
        solution=r'''FILE: textkit/stats.py
<<<<<<< SEARCH
def reading_time_minutes(text, wpm=200):
=======
def sentence_count(text):
    parts = re.split(r"[.!?]+", text)
    return sum(1 for p in parts if p.strip())


def reading_time_minutes(text, wpm=200):
>>>>>>> REPLACE
COMMIT: Add sentence_count
'''),
    dict(
        id="tk-11", fixture="textkit", files=["textkit/stats.py"],
        request="reading_time_minutes should return 0 for empty or whitespace-only text instead of 1. Non-empty text still takes at least 1 minute.",
        check=r'''
from textkit.stats import reading_time_minutes
def test_zero():
    assert reading_time_minutes("") == 0
    assert reading_time_minutes("  \n") == 0
    assert reading_time_minutes("hi") == 1
    assert reading_time_minutes("word " * 450) == 2
''',
        solution=r'''FILE: textkit/stats.py
<<<<<<< SEARCH
def reading_time_minutes(text, wpm=200):
    return max(1, round(word_count(text) / wpm))
=======
def reading_time_minutes(text, wpm=200):
    count = word_count(text)
    if count == 0:
        return 0
    return max(1, round(count / wpm))
>>>>>>> REPLACE
COMMIT: Return 0 reading time for empty text
'''),
    dict(
        id="tk-12", fixture="textkit", files=["textkit/wrap.py"],
        request="wrap() leaves words longer than the width sticking out. Split such words across lines so no line is longer than width.",
        check=r'''
from textkit.wrap import wrap
def test_long_words():
    assert wrap("abcdefghij", width=4) == ["abcd", "efgh", "ij"]
    assert wrap("hi abcdefghij", width=4) == ["hi", "abcd", "efgh", "ij"]
    assert wrap("one two three four", width=9) == ["one two", "three", "four"]
''',
        solution=r'''FILE: textkit/wrap.py
<<<<<<< SEARCH
    for word in text.split():
        candidate = f"{current} {word}" if current else word
=======
    for word in text.split():
        while len(word) > width:
            if current:
                lines.append(current)
                current = ""
            lines.append(word[:width])
            word = word[width:]
        if not word:
            continue
        candidate = f"{current} {word}" if current else word
>>>>>>> REPLACE
COMMIT: Split over-long words in wrap
'''),
    dict(
        id="tk-13", fixture="textkit", files=["textkit/wrap.py"],
        request='Add an ellipsis argument to truncate (default "...") so callers can use a different marker such as the single character "…". The result must still fit within limit.',
        check=r'''
from textkit.wrap import truncate
def test_ellipsis():
    assert truncate("abcdefghij", 8, ellipsis="…") == "abcdefg…"
    assert truncate("abcdefghij", 8) == "abcde..."
''',
        solution=r'''FILE: textkit/wrap.py
<<<<<<< SEARCH
def truncate(text, limit):
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."
=======
def truncate(text, limit, ellipsis="..."):
    if len(text) <= limit:
        return text
    return text[: limit - len(ellipsis)] + ellipsis
>>>>>>> REPLACE
COMMIT: Add ellipsis argument to truncate
'''),
    dict(
        id="tk-14", fixture="textkit", files=["textkit/wrap.py"],
        request="Add a whole_words option to truncate. When true, don't cut a word in half: back off to the last space that fits, then add the ellipsis.",
        check=r'''
from textkit.wrap import truncate
def test_whole_words():
    assert truncate("the quick brown fox", 14, whole_words=True) == "the quick..."
    assert truncate("the quick brown fox", 14) == "the quick b..."
''',
        solution=r'''FILE: textkit/wrap.py
<<<<<<< SEARCH
def truncate(text, limit):
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."
=======
def truncate(text, limit, whole_words=False):
    if len(text) <= limit:
        return text
    cut = text[: limit - 3]
    if whole_words and " " in cut:
        cut = cut[: cut.rfind(" ")]
    return cut + "..."
>>>>>>> REPLACE
COMMIT: Add whole_words option to truncate
'''),
    dict(
        id="tk-15", fixture="textkit", files=["textkit/clean.py"],
        request="strip_html should also decode HTML entities such as &amp;, &lt;, &gt;, &quot; and &#39;.",
        check=r'''
from textkit.clean import strip_html
def test_entities():
    assert strip_html("<p>Tom &amp; Jerry &lt;3 &#39;x&#39;</p>") == "Tom & Jerry <3 'x'"
''',
        solution=r'''FILE: textkit/clean.py
<<<<<<< SEARCH
import re
=======
import html
import re
>>>>>>> REPLACE
FILE: textkit/clean.py
<<<<<<< SEARCH
    return re.sub(r"<[^>]+>", "", text)
=======
    return html.unescape(re.sub(r"<[^>]+>", "", text))
>>>>>>> REPLACE
COMMIT: Decode entities in strip_html
'''),
    dict(
        id="tk-16", fixture="textkit", files=["textkit/clean.py"],
        request="Add normalize_quotes(text) to the clean module. It replaces curly single quotes with ' and curly double quotes with \".",
        check=r'''
from textkit.clean import normalize_quotes
def test_quotes():
    assert normalize_quotes("“It’s fine,” she said ‘ok’") == '"It\'s fine," she said \'ok\''
''',
        solution=r'''FILE: textkit/clean.py
<<<<<<< SEARCH
def strip_html(text):
=======
def normalize_quotes(text):
    return text.translate(str.maketrans({
        "‘": "'", "’": "'", "“": '"', "”": '"'}))


def strip_html(text):
>>>>>>> REPLACE
COMMIT: Add normalize_quotes
'''),
    dict(
        id="tk-17", fixture="textkit", files=["textkit/clean.py"],
        request="strip_html should remove <script> and <style> blocks completely, including the code inside them, not just the tags.",
        check=r'''
from textkit.clean import strip_html
def test_script_style():
    assert strip_html("a<script>var x = 1;</script>b<STYLE type='t'>p {}</STYLE>c") == "abc"
    assert strip_html("<b>hi</b> there") == "hi there"
''',
        solution=r'''FILE: textkit/clean.py
<<<<<<< SEARCH
    return re.sub(r"<[^>]+>", "", text)
=======
    text = re.sub(r"<(script|style)\b[^>]*>.*?</\1\s*>", "", text, flags=re.I | re.S)
    return re.sub(r"<[^>]+>", "", text)
>>>>>>> REPLACE
COMMIT: Drop script and style blocks in strip_html
'''),

    # ----------------------------------------------------------------- ledger
    dict(
        id="lg-01", fixture="ledger", files=["ledger/money.py"],
        request="Let Money be multiplied by an integer, on either side: Money(250) * 3 and 3 * Money(250) both give Money(750).",
        check=r'''
from ledger.money import Money
def test_mul():
    assert Money(250) * 3 == Money(750)
    assert 3 * Money(250, "EUR") == Money(750, "EUR")
''',
        solution=r'''FILE: ledger/money.py
<<<<<<< SEARCH
    def __str__(self):
=======
    def __mul__(self, factor):
        if not isinstance(factor, int):
            return NotImplemented
        return Money(self.cents * factor, self.currency)

    __rmul__ = __mul__

    def __str__(self):
>>>>>>> REPLACE
COMMIT: Support Money * int
'''),
    dict(
        id="lg-02", fixture="ledger", files=["ledger/money.py"],
        request="Make Money amounts comparable with <, <=, > and >= when they share a currency. Comparing different currencies should raise CurrencyMismatch.",
        check=r'''
import pytest
from ledger.errors import CurrencyMismatch
from ledger.money import Money
def test_compare():
    assert Money(1) < Money(2) and Money(2) >= Money(2) and Money(3) > Money(2)
    assert sorted([Money(5), Money(1), Money(3)]) == [Money(1), Money(3), Money(5)]
    with pytest.raises(CurrencyMismatch):
        Money(1, "USD") < Money(2, "EUR")
''',
        solution=r'''FILE: ledger/money.py
<<<<<<< SEARCH
    def __str__(self):
=======
    def __lt__(self, other):
        self._check(other)
        return self.cents < other.cents

    def __le__(self, other):
        self._check(other)
        return self.cents <= other.cents

    def __gt__(self, other):
        self._check(other)
        return self.cents > other.cents

    def __ge__(self, other):
        self._check(other)
        return self.cents >= other.cents

    def __str__(self):
>>>>>>> REPLACE
COMMIT: Add ordering to Money
'''),
    dict(
        id="lg-03", fixture="ledger", files=["ledger/money.py"],
        request='Money.from_str should accept a leading "$" and thousands separators, e.g. "$1,234.50".',
        check=r'''
from ledger.money import Money
def test_dollars():
    assert Money.from_str("$1,234.50") == Money(123450)
    assert Money.from_str("1,000") == Money(100000)
    assert Money.from_str("-3.07") == Money(-307)
''',
        solution=r'''FILE: ledger/money.py
<<<<<<< SEARCH
        whole, _, frac = text.strip().partition(".")
=======
        text = text.strip().replace("$", "").replace(",", "")
        whole, _, frac = text.partition(".")
>>>>>>> REPLACE
COMMIT: Accept $ and commas in Money.from_str
'''),
    dict(
        id="lg-04", fixture="ledger", files=["ledger/money.py"],
        request="Money.from_str silently drops digits after the second decimal place. It should raise ValueError for amounts like \"1.234\" instead.",
        check=r'''
import pytest
from ledger.money import Money
def test_precision():
    with pytest.raises(ValueError):
        Money.from_str("1.234")
    assert Money.from_str("1.2") == Money(120)
''',
        solution=r'''FILE: ledger/money.py
<<<<<<< SEARCH
        whole, _, frac = text.strip().partition(".")
=======
        whole, _, frac = text.strip().partition(".")
        if len(frac) > 2:
            raise ValueError(f"too many decimal places: {text!r}")
>>>>>>> REPLACE
COMMIT: Reject over-precise amounts in from_str
'''),
    dict(
        id="lg-05", fixture="ledger", files=["ledger/money.py"],
        request='Money.from_str crashes on amounts with nothing before the decimal point. Make ".5" and "-.75" work.',
        check=r'''
from ledger.money import Money
def test_leading_dot():
    assert Money.from_str(".5") == Money(50)
    assert Money.from_str("-.75") == Money(-75)
    assert Money.from_str("12.5") == Money(1250)
''',
        solution=r'''FILE: ledger/money.py
<<<<<<< SEARCH
        sign = -1 if whole.startswith("-") else 1
        return cls(sign * (abs(int(whole)) * 100 + int(frac)), currency)
=======
        sign = -1 if whole.startswith("-") else 1
        digits = whole.lstrip("-") or "0"
        return cls(sign * (int(digits) * 100 + int(frac)), currency)
>>>>>>> REPLACE
COMMIT: Accept amounts with a leading decimal point
'''),
    dict(
        id="lg-06", fixture="ledger", files=["ledger/money.py"],
        request='Format Money with thousands separators, e.g. Money(123456789) prints as "1,234,567.89 USD".',
        check=r'''
from ledger.money import Money
def test_commas():
    assert str(Money(123456789)) == "1,234,567.89 USD"
    assert str(Money(-100000)) == "-1,000.00 USD"
    assert str(Money(5)) == "0.05 USD"
''',
        solution=r'''FILE: ledger/money.py
<<<<<<< SEARCH
        return f"{sign}{c // 100}.{c % 100:02d} {self.currency}"
=======
        return f"{sign}{c // 100:,}.{c % 100:02d} {self.currency}"
>>>>>>> REPLACE
COMMIT: Add thousands separators to Money
'''),
    dict(
        id="lg-07", fixture="ledger", files=["ledger/account.py"],
        request="Add Account.transfer(to_account, amount) that moves money between accounts. It must raise InsufficientFunds when the balance is too low and CurrencyMismatch when the accounts use different currencies, without changing either account in those cases.",
        check=r'''
import pytest
from ledger.account import Account
from ledger.errors import CurrencyMismatch, InsufficientFunds
from ledger.money import Money
def test_transfer():
    a, b = Account("a"), Account("b")
    a.deposit(Money(1000))
    a.transfer(b, Money(400))
    assert a.balance == Money(600) and b.balance == Money(400)
    with pytest.raises(InsufficientFunds):
        a.transfer(b, Money(5000))
    e = Account("e", currency="EUR")
    with pytest.raises(CurrencyMismatch):
        a.transfer(e, Money(100))
    assert a.balance == Money(600) and e.transactions == []
''',
        solution=r'''FILE: ledger/account.py
<<<<<<< SEARCH
from ledger.errors import InsufficientFunds
=======
from ledger.errors import CurrencyMismatch, InsufficientFunds
>>>>>>> REPLACE
FILE: ledger/account.py
<<<<<<< SEARCH
        self.transactions.append(("withdraw", amount))
=======
        self.transactions.append(("withdraw", amount))

    def transfer(self, to_account, amount):
        if to_account.currency != self.currency or amount.currency != self.currency:
            raise CurrencyMismatch(f"{self.currency} vs {to_account.currency}")
        self.withdraw(amount)
        to_account.deposit(amount)
>>>>>>> REPLACE
COMMIT: Add Account.transfer
'''),
    dict(
        id="lg-08", fixture="ledger", files=["ledger/account.py"],
        request="Depositing or withdrawing money in a different currency than the account's should raise CurrencyMismatch right away and leave the account unchanged.",
        check=r'''
import pytest
from ledger.account import Account
from ledger.errors import CurrencyMismatch
from ledger.money import Money
def test_currency_check():
    a = Account("a")
    with pytest.raises(CurrencyMismatch):
        a.deposit(Money(100, "EUR"))
    assert a.transactions == []
    a.deposit(Money(100))
    with pytest.raises(CurrencyMismatch):
        a.withdraw(Money(50, "EUR"))
    assert a.balance == Money(100)
''',
        solution=r'''FILE: ledger/account.py
<<<<<<< SEARCH
from ledger.errors import InsufficientFunds
=======
from ledger.errors import CurrencyMismatch, InsufficientFunds
>>>>>>> REPLACE
FILE: ledger/account.py
<<<<<<< SEARCH
    def deposit(self, amount):
        if amount.cents <= 0:
=======
    def _check_currency(self, amount):
        if amount.currency != self.currency:
            raise CurrencyMismatch(f"{amount.currency} vs {self.currency}")

    def deposit(self, amount):
        self._check_currency(amount)
        if amount.cents <= 0:
>>>>>>> REPLACE
FILE: ledger/account.py
<<<<<<< SEARCH
    def withdraw(self, amount):
        if amount.cents <= 0:
=======
    def withdraw(self, amount):
        self._check_currency(amount)
        if amount.cents <= 0:
>>>>>>> REPLACE
COMMIT: Reject transactions in the wrong currency
'''),
    dict(
        id="lg-09", fixture="ledger", files=["ledger/account.py"],
        request="Add an optional overdraft limit to Account, passed as Account(owner, overdraft=Money(...)). Withdrawals may take the balance negative down to minus that limit. Without it, behavior is unchanged.",
        check=r'''
import pytest
from ledger.account import Account
from ledger.errors import InsufficientFunds
from ledger.money import Money
def test_overdraft():
    a = Account("a", overdraft=Money(500))
    a.deposit(Money(1000))
    a.withdraw(Money(1500))
    assert a.balance == Money(-500)
    with pytest.raises(InsufficientFunds):
        a.withdraw(Money(1))
    b = Account("b"); b.deposit(Money(100))
    with pytest.raises(InsufficientFunds):
        b.withdraw(Money(101))
''',
        solution=r'''FILE: ledger/account.py
<<<<<<< SEARCH
    def __init__(self, owner, currency="USD"):
        self.owner = owner
        self.currency = currency
=======
    def __init__(self, owner, currency="USD", overdraft=None):
        self.owner = owner
        self.currency = currency
        self.overdraft = overdraft or Money(0, currency)
>>>>>>> REPLACE
FILE: ledger/account.py
<<<<<<< SEARCH
        if amount.cents > self.balance.cents:
=======
        if amount.cents > self.balance.cents + self.overdraft.cents:
>>>>>>> REPLACE
COMMIT: Add overdraft limit to Account
'''),
    dict(
        id="lg-10", fixture="ledger", files=["ledger/account.py", "ledger/report.py"],
        request='Let deposit and withdraw take an optional memo string. The statement should show the memo after the amount, separated by two spaces, e.g. "deposit  10.00 USD  paycheck". Lines without a memo stay the same, and the CSV export is unchanged.',
        check=r'''
from ledger.account import Account
from ledger.money import Money
from ledger.report import statement, to_csv
def test_memo():
    a = Account("ana")
    a.deposit(Money(1000), memo="paycheck")
    a.withdraw(Money(100))
    lines = statement(a).splitlines()
    assert lines[1] == "deposit  10.00 USD  paycheck"
    assert lines[2] == "withdraw 1.00 USD"
    assert a.balance == Money(900)
    assert to_csv(a) == "kind,cents,currency\ndeposit,1000,USD\nwithdraw,100,USD\n"
''',
        solution=r'''FILE: ledger/account.py
<<<<<<< SEARCH
        self.transactions = []  # list of (kind, Money)
=======
        self.transactions = []  # list of (kind, Money)
        self.memos = []  # parallel to transactions
>>>>>>> REPLACE
FILE: ledger/account.py
<<<<<<< SEARCH
    def deposit(self, amount):
        if amount.cents <= 0:
            raise ValueError("deposit must be positive")
        self.transactions.append(("deposit", amount))

    def withdraw(self, amount):
=======
    def deposit(self, amount, memo=""):
        if amount.cents <= 0:
            raise ValueError("deposit must be positive")
        self.transactions.append(("deposit", amount))
        self.memos.append(memo)

    def withdraw(self, amount, memo=""):
>>>>>>> REPLACE
FILE: ledger/account.py
<<<<<<< SEARCH
        self.transactions.append(("withdraw", amount))
=======
        self.transactions.append(("withdraw", amount))
        self.memos.append(memo)
>>>>>>> REPLACE
FILE: ledger/report.py
<<<<<<< SEARCH
    for kind, amount in account.transactions:
        lines.append(f"{kind:<9}{amount}")
=======
    memos = getattr(account, "memos", [])
    for i, (kind, amount) in enumerate(account.transactions):
        memo = memos[i] if i < len(memos) else ""
        lines.append(f"{kind:<9}{amount}" + (f"  {memo}" if memo else ""))
>>>>>>> REPLACE
COMMIT: Add transaction memos to statements
'''),
    dict(
        id="lg-11", fixture="ledger", files=["ledger/report.py", "tests/test_ledger.py"],
        request="Add a running balance column, balance_cents, as the last column of the CSV export.",
        check=r'''
from ledger.account import Account
from ledger.money import Money
from ledger.report import to_csv
def test_running_balance():
    a = Account("ana"); a.deposit(Money(1000)); a.withdraw(Money(300))
    assert to_csv(a) == ("kind,cents,currency,balance_cents\n"
                         "deposit,1000,USD,1000\nwithdraw,300,USD,700\n")
''',
        solution=r'''FILE: ledger/report.py
<<<<<<< SEARCH
    writer.writerow(["kind", "cents", "currency"])
    for kind, amount in account.transactions:
        writer.writerow([kind, amount.cents, amount.currency])
=======
    writer.writerow(["kind", "cents", "currency", "balance_cents"])
    balance = 0
    for kind, amount in account.transactions:
        balance += amount.cents if kind == "deposit" else -amount.cents
        writer.writerow([kind, amount.cents, amount.currency, balance])
>>>>>>> REPLACE
FILE: tests/test_ledger.py
<<<<<<< SEARCH
    assert to_csv(a) == "kind,cents,currency\ndeposit,1000,USD\n"
=======
    assert to_csv(a) == "kind,cents,currency,balance_cents\ndeposit,1000,USD,1000\n"
>>>>>>> REPLACE
COMMIT: Add running balance to CSV export
'''),
    dict(
        id="lg-12", fixture="ledger", files=["ledger/report.py"],
        request="Add from_csv(text, owner) to the report module. It rebuilds an Account from the text that to_csv produces.",
        check=r'''
from ledger.account import Account
from ledger.money import Money
from ledger.report import from_csv, to_csv
def test_from_csv():
    a = Account("ana", currency="EUR")
    a.deposit(Money(1000, "EUR")); a.withdraw(Money(250, "EUR"))
    b = from_csv(to_csv(a), "ana")
    assert b.owner == "ana" and b.currency == "EUR"
    assert b.transactions == a.transactions
    assert b.balance == Money(750, "EUR")
''',
        solution=r'''FILE: ledger/report.py
<<<<<<< SEARCH
import csv
import io
=======
import csv
import io

from ledger.account import Account
from ledger.money import Money
>>>>>>> REPLACE
FILE: ledger/report.py
<<<<<<< SEARCH
    return buf.getvalue()
=======
    return buf.getvalue()


def from_csv(text, owner):
    rows = list(csv.DictReader(io.StringIO(text)))
    currency = rows[0]["currency"] if rows else "USD"
    account = Account(owner, currency=currency)
    for row in rows:
        amount = Money(int(row["cents"]), row["currency"])
        getattr(account, row["kind"])(amount)
    return account
>>>>>>> REPLACE
COMMIT: Add from_csv
'''),
    dict(
        id="lg-13", fixture="ledger", files=["ledger/fx.py", "ledger/errors.py"],
        request="convert() raises a bare KeyError for currencies it doesn't know. Add an UnknownCurrency error (a LedgerError subclass) in the errors module and raise it instead.",
        check=r'''
import pytest
from ledger.errors import LedgerError, UnknownCurrency
from ledger.fx import convert
from ledger.money import Money
def test_unknown():
    assert issubclass(UnknownCurrency, LedgerError)
    with pytest.raises(UnknownCurrency):
        convert(Money(100, "XYZ"), "USD")
    with pytest.raises(UnknownCurrency):
        convert(Money(100, "USD"), "XYZ")
''',
        solution=r'''FILE: ledger/errors.py
<<<<<<< SEARCH
class InsufficientFunds(LedgerError):
    pass
=======
class InsufficientFunds(LedgerError):
    pass


class UnknownCurrency(LedgerError):
    pass
>>>>>>> REPLACE
FILE: ledger/fx.py
<<<<<<< SEARCH
from ledger.money import Money
=======
from ledger.errors import UnknownCurrency
from ledger.money import Money
>>>>>>> REPLACE
FILE: ledger/fx.py
<<<<<<< SEARCH
    if amount.currency == to_currency:
        return amount
=======
    for code in (amount.currency, to_currency):
        if code not in RATES:
            raise UnknownCurrency(code)
    if amount.currency == to_currency:
        return amount
>>>>>>> REPLACE
COMMIT: Raise UnknownCurrency for unsupported currencies
'''),
    dict(
        id="lg-14", fixture="ledger", files=["ledger/money.py"],
        request="Add a total(amounts, currency=\"USD\") function to the money module that sums a list of Money. An empty list gives zero in that currency; mixed currencies raise CurrencyMismatch.",
        check=r'''
import pytest
from ledger.errors import CurrencyMismatch
from ledger.money import Money, total
def test_total():
    assert total([Money(1), Money(2), Money(3)]) == Money(6)
    assert total([], "EUR") == Money(0, "EUR")
    with pytest.raises(CurrencyMismatch):
        total([Money(1), Money(1, "EUR")])
''',
        solution=r'''FILE: ledger/money.py
<<<<<<< SEARCH
    def __str__(self):
        sign = "-" if self.cents < 0 else ""
        c = abs(self.cents)
        return f"{sign}{c // 100}.{c % 100:02d} {self.currency}"
=======
    def __str__(self):
        sign = "-" if self.cents < 0 else ""
        c = abs(self.cents)
        return f"{sign}{c // 100}.{c % 100:02d} {self.currency}"


def total(amounts, currency="USD"):
    result = Money(0, amounts[0].currency if amounts else currency)
    for amount in amounts:
        result = result + amount
    return result
>>>>>>> REPLACE
COMMIT: Add total() for summing Money
'''),
    dict(
        id="lg-15", fixture="ledger", files=["ledger/report.py"],
        request='Add a line right under the statement title that shows the account currency, like "Currency: USD".',
        check=r'''
from ledger.account import Account
from ledger.money import Money
from ledger.report import statement
def test_currency_line():
    a = Account("ana", currency="EUR"); a.deposit(Money(100, "EUR"))
    lines = statement(a).splitlines()
    assert lines[:2] == ["Statement for ana", "Currency: EUR"]
    assert lines[-1] == "balance  1.00 EUR"
''',
        solution=r'''FILE: ledger/report.py
<<<<<<< SEARCH
    lines = [f"Statement for {account.owner}"]
=======
    lines = [f"Statement for {account.owner}", f"Currency: {account.currency}"]
>>>>>>> REPLACE
COMMIT: Show currency on statements
'''),
    dict(
        id="lg-16", fixture="ledger", files=["ledger/fx.py"],
        request="Give convert() an optional rates argument that overrides the built-in RATES table for that call.",
        check=r'''
from ledger.fx import RATES, convert
from ledger.money import Money
def test_rates():
    assert convert(Money(100, "USD"), "EUR", rates={"USD": 1, "EUR": 2}) == Money(200, "EUR")
    assert convert(Money(1000, "USD"), "EUR") == Money(900, "EUR")
    assert RATES["EUR"] == 0.9
''',
        solution=r'''FILE: ledger/fx.py
<<<<<<< SEARCH
def convert(amount, to_currency):
    if amount.currency == to_currency:
        return amount
    usd = amount.cents / RATES[amount.currency]
    return Money(round(usd * RATES[to_currency]), to_currency)
=======
def convert(amount, to_currency, rates=None):
    rates = rates or RATES
    if amount.currency == to_currency:
        return amount
    usd = amount.cents / rates[amount.currency]
    return Money(round(usd * rates[to_currency]), to_currency)
>>>>>>> REPLACE
COMMIT: Allow custom rates in convert
'''),
]
