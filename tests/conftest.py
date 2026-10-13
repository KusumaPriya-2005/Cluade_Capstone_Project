from datetime import datetime, timedelta, timezone

import pytest

from pwreset.hashing import ScryptPasswordHasher

T0 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


class FakeClock:
    def __init__(self, now: datetime = T0) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now

    def set(self, now: datetime) -> None:
        self._now = now

    def advance(self, delta: timedelta) -> None:
        self._now = self._now + delta


class RecordingEmailSender:
    def __init__(self) -> None:
        self.messages = []
        self.raise_exc = False
        self.exc_text = "send failed"

    def send(self, message) -> None:
        if self.raise_exc:
            raise RuntimeError(self.exc_text)
        self.messages.append(message)


class RecordingRevoker:
    def __init__(self) -> None:
        self.calls = []
        self.raise_exc = False
        self.exc_text = "revoke failed"

    def revoke_sessions(self, user_id: str) -> None:
        if self.raise_exc:
            raise RuntimeError(self.exc_text)
        self.calls.append(user_id)


class SequenceTokenGenerator:
    def __init__(self, prefix: str = "tok") -> None:
        self._prefix = prefix
        self.count = 0

    def new_token(self) -> str:
        self.count += 1
        return f"{self._prefix}-{self.count:040d}"


class SpyHasher:
    """Wraps a real hasher and counts calls."""

    def __init__(self, inner) -> None:
        self._inner = inner
        self.hash_calls = []
        self.verify_calls = []

    def hash(self, password: str) -> str:
        self.hash_calls.append(password)
        return self._inner.hash(password)

    def verify(self, password: str, stored: str) -> bool:
        self.verify_calls.append(password)
        return self._inner.verify(password, stored)


@pytest.fixture
def clock():
    return FakeClock()


@pytest.fixture
def hasher():
    return ScryptPasswordHasher(n=2**4)


@pytest.fixture
def spy_hasher(hasher):
    return SpyHasher(hasher)


# ---- service factory -------------------------------------------------------
from types import SimpleNamespace  # noqa: E402

from pwreset.config import ResetConfig  # noqa: E402
from pwreset.interfaces import User  # noqa: E402
from pwreset.memory import InMemoryTokenRepository, InMemoryUserRepository  # noqa: E402
from pwreset.policy import normalize_password  # noqa: E402
from pwreset.rate_limit import SlidingWindowLimiter  # noqa: E402
from pwreset.service import PasswordResetService  # noqa: E402

USER_ID = "user-id-1"
USER_EMAIL = "user@example.com"
OLD_PASSWORD = "Old-Password-123"
NEW_PASSWORD = "New-Password-456"


class FailingSetHashUsers:
    """Wraps a user repository; set_password_hash raises (B3)."""

    def __init__(self, inner) -> None:
        self._inner = inner

    def get_by_email(self, e):
        return self._inner.get_by_email(e)

    def get_by_id(self, i):
        return self._inner.get_by_id(i)

    def set_password_hash(self, user_id, password_hash):
        raise RuntimeError("db down")


class RaisingGetByEmailUsers(FailingSetHashUsers):
    def get_by_email(self, e):
        raise RuntimeError("db down")

    def set_password_hash(self, user_id, password_hash):
        return self._inner.set_password_hash(user_id, password_hash)


class RaisingIssueTokens:
    def __init__(self, inner) -> None:
        self._inner = inner

    def issue(self, record):
        raise RuntimeError("db down")

    def peek_valid(self, h, now):
        return self._inner.peek_valid(h, now)

    def consume(self, h, now):
        return self._inner.consume(h, now)


@pytest.fixture
def make_env(clock, hasher):
    def factory(*, hasher_override=None, users_wrapper=None, tokens_wrapper=None, config=None):
        cfg = config or ResetConfig()
        h = hasher_override or hasher
        users = InMemoryUserRepository()
        tokens = InMemoryTokenRepository()
        # Registration is outside this library; it must hash the NFKC-normalised
        # password, which is what this fixture does (N4b).
        users.add(User(USER_ID, USER_EMAIL, h.hash(normalize_password(OLD_PASSWORD))))
        rl = cfg.rate_limits
        email_l = SlidingWindowLimiter(clock, rl.per_email, rl.window)
        client_l = SlidingWindowLimiter(clock, rl.per_client, rl.window)
        invalid_l = SlidingWindowLimiter(clock, rl.invalid_confirm_per_client, rl.window)
        sender = RecordingEmailSender()
        revoker = RecordingRevoker()
        gen = SequenceTokenGenerator()
        svc = PasswordResetService(
            users_wrapper(users) if users_wrapper else users,
            tokens_wrapper(tokens) if tokens_wrapper else tokens,
            sender,
            revoker,
            h,
            clock,
            gen,
            cfg,
            email_limiter=email_l,
            client_limiter=client_l,
            invalid_confirm_limiter=invalid_l,
        )
        return SimpleNamespace(
            service=svc, users=users, tokens=tokens, sender=sender, revoker=revoker,
            gen=gen, clock=clock, hasher=h, config=cfg, email_limiter=email_l,
            client_limiter=client_l, invalid_limiter=invalid_l,
        )

    return factory


@pytest.fixture
def env(make_env):
    return make_env()


def extract_token(message) -> str:
    return message.body.split("token=", 1)[1]
