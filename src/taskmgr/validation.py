"""The single title rule and the task id rule, used on write and on load."""

from __future__ import annotations

import re
import unicodedata

from .errors import InvalidTitleError, TitleProblem

MAX_TITLE_LENGTH = 200
MAX_ID_LENGTH = 64

_ID_PATTERN = re.compile(r"[A-Za-z0-9_-]{1,64}")


def normalize_title(title: object) -> str:
    if not isinstance(title, str):
        raise InvalidTitleError(TitleProblem.INVALID_TYPE)
    stripped = title.strip()
    if not stripped:
        raise InvalidTitleError(TitleProblem.EMPTY)
    if len(stripped) > MAX_TITLE_LENGTH:
        raise InvalidTitleError(TitleProblem.TOO_LONG)
    # Cc covers C0, DEL and C1; Cs covers lone surrogates that cannot be encoded.
    if any(unicodedata.category(ch) in ("Cc", "Cs") for ch in stripped):
        raise InvalidTitleError(TitleProblem.CONTROL_CHARS)
    return stripped


def validate_task_id(value: object) -> str:
    if not isinstance(value, str) or _ID_PATTERN.fullmatch(value) is None:
        raise ValueError("invalid task id")
    return value
