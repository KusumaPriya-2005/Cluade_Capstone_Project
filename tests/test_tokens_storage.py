import hashlib
from dataclasses import fields
from datetime import datetime, timedelta, timezone

from pwreset.interfaces import TokenRecord, User
from pwreset.memory import InMemoryTokenRepository, InMemoryUserRepository

T = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
EXP = T + timedelta(minutes=30)
US = timedelta(microseconds=1)


def h(s):
    return hashlib.sha256(s.encode()).hexdigest()


def rec(token, user="u1", expires=EXP):
    return TokenRecord(h(token), user, expires)


def test_dump_has_hash_not_plaintext():
    repo = InMemoryTokenRepository()
    repo.issue(rec("PLAINTEXT-TOKEN"))
    assert h("PLAINTEXT-TOKEN") in repo.dump()
    assert "PLAINTEXT-TOKEN" not in repo.dump()
    assert {f.name for f in fields(TokenRecord)} == {"token_hash", "user_id", "expires_at", "used_at"}


def test_issue_supersedes_same_user_only():
    repo = InMemoryTokenRepository()
    repo.issue(rec("a", "u1"))
    repo.issue(rec("b", "u2"))
    repo.issue(rec("c", "u1"))
    assert repo.peek_valid(h("a"), T) is None
    assert repo.peek_valid(h("c"), T) is not None
    assert repo.peek_valid(h("b"), T) is not None


def test_peek_valid_boundary_and_readonly():
    repo = InMemoryTokenRepository()
    repo.issue(rec("a"))
    before = repo.dump()
    assert repo.peek_valid(h("a"), EXP - US) is not None
    assert repo.peek_valid(h("a"), EXP) is None
    assert repo.peek_valid(h("a"), EXP + US) is None
    assert repo.dump() == before


def test_consume_once_and_clears_by_user():
    repo = InMemoryTokenRepository()
    repo.issue(rec("a"))
    assert repo.consume(h("a"), T) is not None
    assert repo.consume(h("a"), T) is None
    assert repo.by_user == {}
    repo.issue(rec("b"))
    assert repo.peek_valid(h("b"), T) is not None


def test_consume_expired_returns_none():
    repo = InMemoryTokenRepository()
    repo.issue(rec("a"))
    assert repo.consume(h("a"), EXP) is None


def test_user_repo_lookups():
    repo = InMemoryUserRepository()
    u = User("u1", "a@example.com", "hash")
    repo.add(u)
    assert repo.get_by_email("a@example.com") is u
    assert repo.get_by_id("u1") is u
    assert repo.get_by_email("x@example.com") is None
    assert repo.get_by_id("nope") is None
    repo.set_password_hash("u1", "new")
    assert repo.snapshot()["u1"].password_hash == "new"
    repo.remove("u1")
    assert repo.get_by_id("u1") is None and repo.get_by_email("a@example.com") is None
