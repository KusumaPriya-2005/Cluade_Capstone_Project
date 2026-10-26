"""Frozen configuration dataclasses."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta

_DEFAULT_DENYLIST = frozenset(
    {
        "password1234",
        "123456789012",
        "qwertyuiop12",
        "iloveyou1234",
        "letmein12345",
        "passwordpassword",
        "administrator",
        "welcome12345",
        "changeme1234",
        "000000000000",
    }
)


@dataclass(frozen=True)
class PasswordPolicy:
    min_length: int = 12
    max_length: int = 128
    # Entries must be casefolded; matching casefolds the candidate too.
    denylist: frozenset[str] = _DEFAULT_DENYLIST
    forbid_email: bool = True


@dataclass(frozen=True)
class RateLimitConfig:
    per_email: int = 5
    per_client: int = 20
    invalid_confirm_per_client: int = 10
    window: timedelta = timedelta(hours=1)


@dataclass(frozen=True)
class ResetConfig:
    token_ttl: timedelta = timedelta(minutes=30)
    base_url: str = "https://example.invalid/reset"
    policy: PasswordPolicy = field(default_factory=PasswordPolicy)
    rate_limits: RateLimitConfig = field(default_factory=RateLimitConfig)
