"""Task logic. No I/O, no printing, no cache: every call loads fresh state."""

from __future__ import annotations

from dataclasses import replace

from .errors import IdGenerationError, TaskNotFoundError
from .interfaces import IdGenerator, TaskRepository
from .model import StatusFilter, Task, TaskStatus
from .validation import normalize_title, validate_task_id

_MAX_ID_ATTEMPTS = 20


def _find_index(tasks: list[Task], task_id: str) -> int:
    for index, task in enumerate(tasks):
        if task.id == task_id:
            return index
    raise TaskNotFoundError(task_id)


class TaskService:
    def __init__(self, repository: TaskRepository, id_generator: IdGenerator) -> None:
        self._repository = repository
        self._id_generator = id_generator

    def add(self, title: str) -> Task:
        clean = normalize_title(title)
        tasks = self._repository.load_all()
        existing = {task.id for task in tasks}
        for _ in range(_MAX_ID_ATTEMPTS):
            candidate = self._id_generator.new_id()
            try:
                validate_task_id(candidate)
            except ValueError:
                continue
            if candidate in existing:
                continue
            task = Task(candidate, clean)
            self._repository.save_all([*tasks, task])
            return task
        raise IdGenerationError()

    def list_tasks(self, status_filter: StatusFilter = StatusFilter.ALL) -> list[Task]:
        return [t for t in self._repository.load_all() if status_filter.matches(t)]

    def complete(self, task_id: str) -> Task:
        return self._set_status(task_id, TaskStatus.COMPLETED)

    def reopen(self, task_id: str) -> Task:
        return self._set_status(task_id, TaskStatus.PENDING)

    def edit(self, task_id: str, title: str) -> Task:
        clean = normalize_title(title)
        tasks = self._repository.load_all()
        index = _find_index(tasks, task_id)
        tasks[index] = replace(tasks[index], title=clean)
        self._repository.save_all(tasks)
        return tasks[index]

    def delete(self, task_id: str) -> None:
        tasks = self._repository.load_all()
        del tasks[_find_index(tasks, task_id)]
        self._repository.save_all(tasks)

    def _set_status(self, task_id: str, status: TaskStatus) -> Task:
        tasks = self._repository.load_all()
        index = _find_index(tasks, task_id)
        tasks[index] = replace(tasks[index], status=status)
        self._repository.save_all(tasks)
        return tasks[index]
