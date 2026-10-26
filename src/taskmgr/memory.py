"""In-memory repository (not thread-safe)."""

from __future__ import annotations

from collections.abc import Sequence

from .model import Task


class InMemoryTaskRepository:
    def __init__(self) -> None:
        self._tasks: list[Task] = []

    def __repr__(self) -> str:
        return "InMemoryTaskRepository()"

    def load_all(self) -> list[Task]:
        return list(self._tasks)

    def save_all(self, tasks: Sequence[Task]) -> None:
        self._tasks = list(tasks)

    def snapshot(self) -> list[Task]:
        """Test-only: copy of the stored tasks."""
        return list(self._tasks)
