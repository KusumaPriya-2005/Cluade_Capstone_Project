"""Plain data: task status, status filter and the frozen Task."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class TaskStatus(Enum):
    PENDING = "pending"
    COMPLETED = "completed"


class StatusFilter(Enum):
    ALL = "all"
    PENDING = "pending"
    COMPLETED = "completed"

    def matches(self, task: Task) -> bool:
        if self is StatusFilter.ALL:
            return True
        return task.status.value == self.value


@dataclass(frozen=True)
class Task:
    id: str
    title: str
    status: TaskStatus = TaskStatus.PENDING
