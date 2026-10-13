"""Password policy.

Layout: ``normalize_password`` (NFKC, the single normalisation used for policy,
reuse check and hashing), ``PolicyResult`` and ``validate_password``.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field

from .config import PasswordPolicy
from .errors import PolicyViolation


def normalize_password(s: str) -> str:
    """NFKC-normalise a password."""
    return unicodedata.normalize("NFKC", s)


@dataclass(frozen=True)
class PolicyResult:
    normalized: str | None = field(repr=False)
    violations: tuple[PolicyViolation, ...]


def validate_password(policy: PasswordPolicy, password: object, normalized_email: str) -> PolicyResult:
    """Validate ``password``; normalise exactly once.

    The raw-length guard (``> 4 * max_length``) is a cost bound, not a policy rule.
    """
    if not isinstance(password, str):
        return PolicyResult(None, (PolicyViolation.INVALID_TYPE,))
    if len(password) > 4 * policy.max_length:
        return PolicyResult(None, (PolicyViolation.TOO_LONG,))

    try:
        password.encode("utf-8")  # e.g. a lone surrogate cannot be encoded
    except UnicodeEncodeError:
        return PolicyResult(None, (PolicyViolation.INVALID_TYPE,))

    normalized = normalize_password(password)
    violations: list[PolicyViolation] = []
    if len(normalized) < policy.min_length:
        violations.append(PolicyViolation.TOO_SHORT)
    if len(normalized) > policy.max_length:
        violations.append(PolicyViolation.TOO_LONG)
    folded = normalized.casefold()
    if folded in {d.casefold() for d in policy.denylist}:
        violations.append(PolicyViolation.COMMON)
    if policy.forbid_email and folded == normalize_password(normalized_email).casefold():
        violations.append(PolicyViolation.EQUALS_EMAIL)
    return PolicyResult(normalized, tuple(violations))
