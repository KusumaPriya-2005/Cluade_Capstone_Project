"""Protocols for injected collaborators, plus plain data classes."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol


@dataclass
class User:
    id: str
    email: str  # stored normalised (stripped, lower-case)
    password_hash: str = field(repr=False)


@dataclass
class TokenRecord:
    """Stored token state. Holds only the token hash, never the plaintext."""

    token_hash: str
    user_id: str
    expires_at: datetime
    used_at: datetime | None = None


@dataclass
class EmailMessage:
    to: str
    subject: str
    body: str = field(repr=False)  # may carry the token


class Clock(Protocol):
    def now(self) -> datetime:
        """Timezone-aware UTC time."""
        ...


class TokenGenerator(Protocol):
    def new_token(self) -> str: ...


class EmailSender(Protocol):
    def send(self, message: EmailMessage) -> None: ...


class SessionRevoker(Protocol):
    def revoke_sessions(self, user_id: str) -> None: ...


class PasswordHasher(Protocol):
    def hash(self, password: str) -> str: ...

    def verify(self, password: str, stored: str) -> bool: ...


class UserRepository(Protocol):
    def get_by_email(self, normalized_email: str) -> User | None: ...

    def get_by_id(self, user_id: str) -> User | None: ...

    def set_password_hash(self, user_id: str, password_hash: str) -> None: ...


class TokenRepository(Protocol):
    """Token storage.

    Transaction contract: a real implementation must run ``consume`` and the
    following ``UserRepository.set_password_hash`` in ONE transaction, so that
    a failed password write rolls the consume back and the token stays usable.
    The in-memory implementation cannot do this; a failed write burns the token.
    A SQL ``consume`` is a single conditional UPDATE
    (``... WHERE token_hash=:h AND used_at IS NULL AND expires_at > :now``)
    followed by a row-count check.
    """

    def issue(self, record: TokenRecord) -> None:
        """Atomically supersede all outstanding tokens of the user, store ``record``."""
        ...

    def peek_valid(self, token_hash: str, now: datetime) -> TokenRecord | None:
        """Read-only. Record if it exists, is unused and ``now < expires_at``."""
        ...

    def consume(self, token_hash: str, now: datetime) -> TokenRecord | None:
        """Atomic check-and-mark-used. Returns the record only to the winning call."""
        ...
