"""taskmgr: personal task list library and CLI (stdlib only)."""

from __future__ import annotations

from .errors import (
    CorruptStorageError,
    IdGenerationError,
    InvalidTitleError,
    StorageError,
    StorageReason,
    TaskManagerError,
    TaskNotFoundError,
    TitleProblem,
)
from .interfaces import IdGenerator, TaskRepository
from .json_store import JsonFileTaskRepository
from .memory import InMemoryTaskRepository
from .model import StatusFilter, Task, TaskStatus
from .service import TaskService
from .system import RandomIdGenerator
from .validation import MAX_ID_LENGTH, MAX_TITLE_LENGTH, normalize_title, validate_task_id

__all__ = [
    "CorruptStorageError", "IdGenerationError", "IdGenerator", "InMemoryTaskRepository",
    "InvalidTitleError", "JsonFileTaskRepository", "MAX_ID_LENGTH", "MAX_TITLE_LENGTH",
    "RandomIdGenerator", "StatusFilter", "StorageError", "StorageReason", "Task",
    "TaskManagerError", "TaskNotFoundError", "TaskRepository", "TaskService",
    "TaskStatus", "TitleProblem", "normalize_title", "validate_task_id",
]
