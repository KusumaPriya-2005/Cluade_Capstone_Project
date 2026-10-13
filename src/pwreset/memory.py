"""In-memory repositories (not thread-safe)."""

from __future__ import annotations

from datetime import datetime

from .interfaces import TokenRecord, User


class InMemoryUserRepository:
    def __init__(self) -> None:
        self._by_email: dict[str, User] = {}
        self._by_id: dict[str, User] = {}

    def __repr__(self) -> str:
        return "InMemoryUserRepository()"

    def add(self, user: User) -> None:
        self._by_email[user.email] = user
        self._by_id[user.id] = user

    def get_by_email(self, normalized_email: str) -> User | None:
        return self._by_email.get(normalized_email)

    def get_by_id(self, user_id: str) -> User | None:
        return self._by_id.get(user_id)

    def set_password_hash(self, user_id: str, password_hash: str) -> None:
        self._by_id[user_id].password_hash = password_hash

    def remove(self, user_id: str) -> None:
        """Delete a user (used to simulate a deleted owner)."""
        user = self._by_id.pop(user_id, None)
        if user is not None:
            self._by_email.pop(user.email, None)

    def snapshot(self) -> dict[str, User]:
        """Test-only: copy of users by id."""
        return dict(self._by_id)


class InMemoryTokenRepository:
    def __init__(self) -> None:
        self.by_hash: dict[str, TokenRecord] = {}
        self.by_user: dict[str, str] = {}

    def __repr__(self) -> str:
        return "InMemoryTokenRepository()"

    def issue(self, record: TokenRecord) -> None:
        old = self.by_user.get(record.user_id)
        if old is not None:
            self.by_hash.pop(old, None)
        self.by_hash[record.token_hash] = record
        self.by_user[record.user_id] = record.token_hash

    def peek_valid(self, token_hash: str, now: datetime) -> TokenRecord | None:
        rec = self.by_hash.get(token_hash)
        if rec is None or rec.used_at is not None or not now < rec.expires_at:
            return None
        return rec

    def consume(self, token_hash: str, now: datetime) -> TokenRecord | None:
        rec = self.peek_valid(token_hash, now)
        if rec is None:
            return None
        del self.by_hash[token_hash]
        if self.by_user.get(rec.user_id) == token_hash:
            del self.by_user[rec.user_id]
        return rec

    def snapshot(self) -> list[TokenRecord]:
        """Test-only: all stored records."""
        return list(self.by_hash.values())

    def dump(self) -> str:
        """Test-only: repr of all repository state (AC-4)."""
        return repr((self.snapshot(), dict(self.by_user)))
