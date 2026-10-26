"""JSON file repository: strict loader and atomic writer (version 1 format)."""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import NoReturn

from .errors import (
    CorruptStorageError,
    InvalidTitleError,
    StorageError,
    StorageReason,
)
from .model import Task, TaskStatus
from .validation import normalize_title, validate_task_id

_FORMAT_VERSION = 1
_TASK_KEYS = frozenset({"id", "title", "status"})
_DOC_KEYS = frozenset({"version", "tasks"})
_STATUSES = {status.value: status for status in TaskStatus}


class JsonFileTaskRepository:
    def __init__(self, path: Path) -> None:
        self._path = Path(path)

    def load_all(self) -> list[Task]:
        try:
            raw = self._read_raw()
            if raw is None:
                return []
            document = self._decode_json(raw)
            items = self._check_document(document)
            return self._parse_tasks(items)
        except OSError:
            raise StorageError(self._path, StorageReason.READ_FAILED) from None

    def save_all(self, tasks: Sequence[Task]) -> None:
        tmp: str | None = None
        try:
            if self._path.is_dir():
                raise StorageError(self._path, StorageReason.NOT_A_FILE)
            parent = self._path.parent
            parent.mkdir(parents=True, exist_ok=True)
            document = {
                "version": _FORMAT_VERSION,
                "tasks": [
                    {"id": t.id, "title": t.title, "status": t.status.value} for t in tasks
                ],
            }
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                newline="\n",
                dir=parent,
                prefix=".tasks-",
                suffix=".tmp",
                delete=False,
            ) as handle:
                tmp = handle.name
                json.dump(document, handle, indent=2, ensure_ascii=False)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp, self._path)
        except OSError:
            self._discard(tmp)
            raise StorageError(self._path, StorageReason.WRITE_FAILED) from None
        except Exception:
            self._discard(tmp)
            raise

    @staticmethod
    def _discard(tmp: str | None) -> None:
        if tmp is None:
            return
        try:
            os.unlink(tmp)
        except OSError:
            pass

    def _fail(self, reason: StorageReason) -> NoReturn:
        raise CorruptStorageError(self._path, reason) from None

    def _read_raw(self) -> bytes | None:
        if self._path.is_dir():
            raise StorageError(self._path, StorageReason.NOT_A_FILE)
        try:
            return self._path.read_bytes()
        except FileNotFoundError:
            return None

    def _decode_json(self, raw: bytes) -> object:
        if not raw:
            self._fail(StorageReason.EMPTY_FILE)
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            self._fail(StorageReason.INVALID_ENCODING)
        try:
            return json.loads(text)
        except (ValueError, RecursionError):
            self._fail(StorageReason.INVALID_JSON)

    def _check_document(self, document: object) -> list[object]:
        if not isinstance(document, dict):
            self._fail(StorageReason.BAD_SHAPE)
        if "version" not in document:
            self._fail(StorageReason.MISSING_KEY)
        version = document["version"]
        if not (type(version) is int and version == _FORMAT_VERSION):
            self._fail(StorageReason.BAD_VERSION)
        if "tasks" not in document:
            self._fail(StorageReason.MISSING_KEY)
        if set(document) - _DOC_KEYS:
            self._fail(StorageReason.UNKNOWN_KEY)
        items = document["tasks"]
        if not isinstance(items, list):
            self._fail(StorageReason.BAD_SHAPE)
        return items

    def _parse_tasks(self, items: list[object]) -> list[Task]:
        seen: set[str] = set()
        tasks = []
        for item in items:
            for check in (
                self._check_shape,
                self._check_keys,
                self._check_types,
                self._check_status,
                self._check_id,
                self._check_title,
                self._check_duplicate,
            ):
                check(item, seen)
            tasks.append(Task(item["id"], item["title"], _STATUSES[item["status"]]))
        return tasks

    def _check_shape(self, item: object, seen: set[str]) -> None:
        if not isinstance(item, dict):
            self._fail(StorageReason.BAD_SHAPE)

    def _check_keys(self, item: dict, seen: set[str]) -> None:
        if _TASK_KEYS - set(item):
            self._fail(StorageReason.MISSING_KEY)
        if set(item) - _TASK_KEYS:
            self._fail(StorageReason.UNKNOWN_KEY)

    def _check_types(self, item: dict, seen: set[str]) -> None:
        if not all(isinstance(item[key], str) for key in _TASK_KEYS):
            self._fail(StorageReason.BAD_TYPE)

    def _check_status(self, item: dict, seen: set[str]) -> None:
        if item["status"] not in _STATUSES:
            self._fail(StorageReason.BAD_STATUS)

    def _check_id(self, item: dict, seen: set[str]) -> None:
        try:
            validate_task_id(item["id"])
        except ValueError:
            self._fail(StorageReason.BAD_ID)

    def _check_title(self, item: dict, seen: set[str]) -> None:
        try:
            normalized = normalize_title(item["title"])
        except InvalidTitleError:
            self._fail(StorageReason.BAD_TITLE)
        if normalized != item["title"]:
            self._fail(StorageReason.BAD_TITLE)

    def _check_duplicate(self, item: dict, seen: set[str]) -> None:
        if item["id"] in seen:
            self._fail(StorageReason.DUPLICATE_ID)
        seen.add(item["id"])
