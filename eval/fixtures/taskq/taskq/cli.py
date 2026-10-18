import argparse

from taskq.dates import parse_due
from taskq.formatting import format_list, format_task
from taskq.store import TaskStore


def build_parser():
    parser = argparse.ArgumentParser(prog="taskq")
    sub = parser.add_subparsers(dest="command", required=True)

    add = sub.add_parser("add")
    add.add_argument("title")
    add.add_argument("--priority", default="normal")
    add.add_argument("--due")

    sub.add_parser("list")

    done = sub.add_parser("done")
    done.add_argument("id", type=int)
    return parser


def run(argv, store=None):
    """Run one command against a store and return the output text."""
    store = store if store is not None else TaskStore()
    args = build_parser().parse_args(argv)
    if args.command == "add":
        due = parse_due(args.due) if args.due else None
        return format_task(store.add(args.title, args.priority, due=due))
    if args.command == "list":
        return format_list(store.list())
    if args.command == "done":
        return format_task(store.complete(args.id))
    raise AssertionError(args.command)
