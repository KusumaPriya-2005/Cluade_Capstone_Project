"""Fakes for the taskmgr tests (not collected by pytest)."""

from __future__ import annotations

import os
from collections.abc import Sequence
from pathlib import Path

from taskmgr import json_store
from taskmgr.model import Task


class SequenceIdGenerator:
    def __init__(self) -> None:
        self.calls = 0

    def new_id(self) -> str:
        self.calls += 1
        return f"id{self.calls:06d}"


class AlwaysSameIdGenerator:
    def __init__(self, task_id: str) -> None:
        self.task_id = task_id
        self.calls = 0

    def new_id(self) -> str:
        self.calls += 1
        return self.task_id


class SpyTaskRepository:
    def __init__(self, inner) -> None:
        self.inner = inner
        self.load_calls = 0
        self.save_calls = 0

    def load_all(self) -> list[Task]:
        self.load_calls += 1
        return self.inner.load_all()

    def save_all(self, tasks: Sequence[Task]) -> None:
        self.save_calls += 1
        self.inner.save_all(tasks)


class _Proxy:
    """Stands in for a module; overridden attributes win, the rest delegate."""

    def __init__(self, real, **overrides) -> None:
        self._real = real
        self.__dict__.update(overrides)

    def __getattr__(self, name):
        return getattr(self._real, name)


def _is_temp_name(name) -> bool:
    base = os.path.basename(str(name))
    return base.startswith(".tasks-") and base.endswith(".tmp")


def patch_replace_fails(monkeypatch, target) -> None:
    """os.replace in json_store raises PermissionError only for destination target."""
    real = json_store.os.replace

    def fake(src, dst, *args, **kwargs):
        if Path(dst) == Path(target):
            raise PermissionError("replace denied")
        return real(src, dst, *args, **kwargs)

    monkeypatch.setattr(json_store, "os", _Proxy(json_store.os, replace=fake))


def patch_unlink_fails(monkeypatch) -> None:
    """os.unlink in json_store raises OSError only for .tasks-*.tmp files."""
    real = json_store.os.unlink

    def fake(path, *args, **kwargs):
        if _is_temp_name(path):
            raise OSError("unlink denied")
        return real(path, *args, **kwargs)

    monkeypatch.setattr(json_store, "os", _Proxy(json_store.os, unlink=fake))


def patch_dump_fails(monkeypatch) -> None:
    """json.dump in json_store raises OSError only when writing to a temp file."""
    real = json_store.json.dump

    def fake(obj, fp, *args, **kwargs):
        if _is_temp_name(getattr(fp, "name", "")):
            raise OSError("dump failed")
        return real(obj, fp, *args, **kwargs)

    monkeypatch.setattr(json_store, "json", _Proxy(json_store.json, dump=fake))
