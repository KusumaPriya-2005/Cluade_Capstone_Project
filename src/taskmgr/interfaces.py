"""Protocols for injected collaborators."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from .model import Task


class TaskRepository(Protocol):
    def load_all(self) -> list[Task]:
        """Tasks in creation order. A missing store gives an empty list."""
        ...

    def save_all(self, tasks: Sequence[Task]) -> None:
        """Replace the whole stored list."""
        ...


class IdGenerator(Protocol):
    def new_id(self) -> str: ...
