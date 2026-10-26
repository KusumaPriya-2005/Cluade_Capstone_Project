"""Domain errors. Messages are fixed text and never echo file contents or titles."""

from __future__ import annotations

from enum import Enum
from pathlib import Path


class TitleProblem(Enum):
    EMPTY = "empty"
    TOO_LONG = "too_long"
    INVALID_TYPE = "invalid_type"
    CONTROL_CHARS = "control_chars"


class StorageReason(Enum):
    READ_FAILED = "read_failed"
    WRITE_FAILED = "write_failed"
    NOT_A_FILE = "not_a_file"
    INVALID_ENCODING = "invalid_encoding"
    INVALID_JSON = "invalid_json"
    EMPTY_FILE = "empty_file"
    BAD_SHAPE = "bad_shape"
    BAD_VERSION = "bad_version"
    UNKNOWN_KEY = "unknown_key"
    MISSING_KEY = "missing_key"
    BAD_TYPE = "bad_type"
    BAD_STATUS = "bad_status"
    BAD_ID = "bad_id"
    BAD_TITLE = "bad_title"
    DUPLICATE_ID = "duplicate_id"


_TITLE_MESSAGES = {
    TitleProblem.EMPTY: "Title must not be empty.",
    TitleProblem.TOO_LONG: "Title is too long (maximum 200 characters).",
    TitleProblem.INVALID_TYPE: "Title must be text.",
    TitleProblem.CONTROL_CHARS: "Title must not contain control characters.",
}


class TaskManagerError(Exception):
    """Base class for all taskmgr errors."""


class InvalidTitleError(TaskManagerError):
    def __init__(self, problem: TitleProblem) -> None:
        super().__init__(_TITLE_MESSAGES[problem])
        self.problem = problem


class TaskNotFoundError(TaskManagerError):
    def __init__(self, task_id: str) -> None:
        super().__init__(f"Task not found: {ascii(task_id[:64])}")
        self.task_id = task_id


class IdGenerationError(TaskManagerError):
    def __init__(self) -> None:
        super().__init__("Could not generate a unique task id.")


class StorageError(TaskManagerError):
    def __init__(self, path: Path, reason: StorageReason) -> None:
        super().__init__(f"Storage problem ({reason.value}): {path}")
        self.path = path
        self.reason = reason


class CorruptStorageError(StorageError):
    def __init__(self, path: Path, reason: StorageReason) -> None:
        TaskManagerError.__init__(
            self,
            f"Storage file is corrupt ({reason.value}): {path}. The file was not modified.",
        )
        self.path = path
        self.reason = reason
