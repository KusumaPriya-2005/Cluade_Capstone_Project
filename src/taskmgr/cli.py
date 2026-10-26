"""Thin argparse front end: parse, call the service, render text, map errors to exit codes."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import TextIO

from .errors import StorageError, TaskManagerError
from .interfaces import IdGenerator
from .json_store import JsonFileTaskRepository
from .model import StatusFilter, Task, TaskStatus
from .service import TaskService
from .system import RandomIdGenerator

EXIT_OK = 0
EXIT_DOMAIN = 1
EXIT_USAGE = 2
EXIT_STORAGE = 3


def default_store_path() -> Path:
    return Path.home() / ".taskmgr" / "tasks.json"


def _path_arg(value: str) -> Path:
    if value == "":
        raise argparse.ArgumentTypeError("path must not be empty")
    return Path(value)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="taskmgr",
        description="Personal task list. A title or id that starts with '-' needs '--' before it.",
    )
    parser.add_argument(
        "--file",
        type=_path_arg,
        default=None,
        help="task file (default: ~/.taskmgr/tasks.json); give it before the command",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    add = commands.add_parser("add", help="add a task")
    add.add_argument("title")
    listing = commands.add_parser("list", help="list tasks")
    listing.add_argument(
        "--filter", dest="filter", choices=[f.value for f in StatusFilter], default="all"
    )
    for name, text in (("done", "mark a task completed"), ("undo", "mark a task pending"),
                       ("delete", "delete a task")):
        sub = commands.add_parser(name, help=text)
        sub.add_argument("id")
    edit = commands.add_parser("edit", help="change a task title")
    edit.add_argument("id")
    edit.add_argument("title")
    return parser


def _row(task: Task) -> str:
    mark = "x" if task.status is TaskStatus.COMPLETED else " "
    return f"[{mark}] {task.id}  {task.title}  ({task.status.value})"


def render_tasks(tasks: Sequence[Task], status_filter: StatusFilter) -> str:
    if not tasks:
        if status_filter is StatusFilter.ALL:
            return "No tasks yet."
        return f"No {status_filter.value} tasks."
    return "\n".join(_row(task) for task in tasks)


def _emit(stream: TextIO, text: str) -> None:
    line = text + "\n"
    try:
        stream.write(line)
    except UnicodeEncodeError:
        encoding = stream.encoding or "ascii"
        stream.write(line.encode(encoding, errors="replace").decode(encoding))


def _exit_code(exc: SystemExit) -> int:
    code = exc.code
    if code is None:
        return EXIT_OK
    if isinstance(code, int):
        return code
    return EXIT_USAGE


def _dispatch(args: argparse.Namespace, service: TaskService, out: TextIO) -> None:
    command = args.command
    if command == "add":
        _emit(out, f"Added: {_row(service.add(args.title))}")
    elif command == "list":
        status_filter = StatusFilter(args.filter)
        _emit(out, render_tasks(service.list_tasks(status_filter), status_filter))
    elif command == "done":
        _emit(out, f"Completed: {_row(service.complete(args.id))}")
    elif command == "undo":
        _emit(out, f"Reopened: {_row(service.reopen(args.id))}")
    elif command == "edit":
        _emit(out, f"Updated: {_row(service.edit(args.id, args.title))}")
    else:
        service.delete(args.id)
        _emit(out, f"Deleted: {args.id}")


def main(
    argv: Sequence[str] | None = None,
    *,
    id_generator: IdGenerator | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    out = sys.stdout if stdout is None else stdout
    err = sys.stderr if stderr is None else stderr
    try:
        args = build_parser().parse_args(argv)
    except SystemExit as exc:
        return _exit_code(exc)
    try:
        path = default_store_path() if args.file is None else args.file
        service = TaskService(
            JsonFileTaskRepository(path),
            RandomIdGenerator() if id_generator is None else id_generator,
        )
        _dispatch(args, service, out)
        return EXIT_OK
    except StorageError as exc:
        _emit(err, f"error: {exc}")
        return EXIT_STORAGE
    except TaskManagerError as exc:
        _emit(err, f"error: {exc}")
        return EXIT_DOMAIN
