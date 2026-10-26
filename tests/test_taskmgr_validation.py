import dataclasses
from pathlib import Path

import pytest

from taskmgr.errors import (
    CorruptStorageError,
    IdGenerationError,
    InvalidTitleError,
    StorageError,
    StorageReason,
    TaskManagerError,
    TaskNotFoundError,
    TitleProblem,
)
from taskmgr.model import StatusFilter, Task, TaskStatus
from taskmgr.validation import (
    MAX_ID_LENGTH,
    MAX_TITLE_LENGTH,
    normalize_title,
    validate_task_id,
)


def problem_of(value):
    with pytest.raises(InvalidTitleError) as info:
        normalize_title(value)
    return info.value.problem


@pytest.mark.parametrize("value", ["", "   ", "\t\n", "\x85", "\x1f"])
def test_blank_titles_are_empty(value):
    assert problem_of(value) is TitleProblem.EMPTY


def test_length_boundary():
    assert normalize_title("a" * 200) == "a" * 200
    assert MAX_TITLE_LENGTH == 200
    assert problem_of("a" * 201) is TitleProblem.TOO_LONG


@pytest.mark.parametrize("value", [None, 5, b"x"])
def test_non_str_is_invalid_type(value):
    assert problem_of(value) is TitleProblem.INVALID_TYPE


def test_title_is_stripped():
    assert normalize_title(" Buy milk ") == "Buy milk"


# N5: str.strip() also removes \x1c-\x1f, \x0b, \x0c and \x85 at the edges, so
# CONTROL_CHARS cases use characters that are not stripped (\x00, \x1b, \x9b)
# or put the control character in the interior.
@pytest.mark.parametrize(
    "value",
    ["a\x00b", "a\x1bb", "a\x9bb", "a\nb", "a\tb", "a\x7fb", "a\ud800b", "\x1bx"],
)
def test_control_characters_rejected(value):
    assert problem_of(value) is TitleProblem.CONTROL_CHARS


@pytest.mark.parametrize("value", ["Buy 🥛", "café", "日本語"])
def test_non_ascii_titles_pass(value):
    assert normalize_title(value) == value


def test_title_messages_are_fixed_and_never_contain_the_title():
    for value, problem in [("", TitleProblem.EMPTY), ("a\x1bSECRETb", TitleProblem.CONTROL_CHARS),
                           ("x" * 201, TitleProblem.TOO_LONG), (None, TitleProblem.INVALID_TYPE)]:
        with pytest.raises(InvalidTitleError) as info:
            normalize_title(value)
        assert info.value.problem is problem
        text = str(info.value)
        assert "SECRET" not in text and "\x1b" not in text and "xxx" not in text
    messages = {str(InvalidTitleError(p)) for p in TitleProblem}
    assert len(messages) == len(TitleProblem)


def test_not_found_escapes_control_characters():
    exc = TaskNotFoundError("x\x1b[31m")
    assert "\\x1b" in str(exc)
    assert "\x1b" not in str(exc)
    assert exc.task_id == "x\x1b[31m"


def test_not_found_cuts_long_ids():
    text = str(TaskNotFoundError("a" * 100))
    assert "a" * 64 in text
    assert "a" * 65 not in text


def test_id_generation_error_message():
    assert str(IdGenerationError()) == "Could not generate a unique task id."


@pytest.mark.parametrize("value", ["a1b2c3d4", "a" * 64, "A_b-9"])
def test_valid_ids(value):
    assert validate_task_id(value) == value
    assert MAX_ID_LENGTH == 64


@pytest.mark.parametrize(
    "value", ["", "a" * 65, "a b", "é", "../x", "a\x1bb", "abc\n", None, 5]
)
def test_invalid_ids(value):
    with pytest.raises(ValueError):
        validate_task_id(value)


def test_storage_error_hierarchy():
    assert issubclass(CorruptStorageError, StorageError)
    assert issubclass(StorageError, TaskManagerError)


def test_storage_reasons_are_the_fifteen_codes():
    assert {r.value for r in StorageReason} == {
        "read_failed", "write_failed", "not_a_file", "invalid_encoding", "invalid_json",
        "empty_file", "bad_shape", "bad_version", "unknown_key", "missing_key",
        "bad_type", "bad_status", "bad_id", "bad_title", "duplicate_id",
    }


def test_storage_error_messages_are_fixed():
    p = Path("some") / "file.json"
    plain = StorageError(p, StorageReason.NOT_A_FILE)
    assert str(plain) == f"Storage problem (not_a_file): {p}"
    corrupt = CorruptStorageError(p, StorageReason.BAD_ID)
    assert str(corrupt) == f"Storage file is corrupt (bad_id): {p}. The file was not modified."
    assert corrupt.path == p and corrupt.reason is StorageReason.BAD_ID


def test_status_filter_matches():
    pending = Task("a", "A")
    done = Task("b", "B", TaskStatus.COMPLETED)
    assert [StatusFilter.ALL.matches(t) for t in (pending, done)] == [True, True]
    assert [StatusFilter.PENDING.matches(t) for t in (pending, done)] == [True, False]
    assert [StatusFilter.COMPLETED.matches(t) for t in (pending, done)] == [False, True]


def test_task_defaults_and_frozen():
    task = Task("a", "A")
    assert task.status is TaskStatus.PENDING
    with pytest.raises(dataclasses.FrozenInstanceError):
        task.title = "B"
