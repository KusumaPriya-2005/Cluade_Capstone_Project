"""Exception types and policy violation codes."""

from __future__ import annotations

from enum import Enum


class PasswordResetError(Exception):
    """Base class for all errors raised by this package."""


class InvalidResetTokenError(PasswordResetError):
    """The reset token is unusable (or the client is blocked).

    One fixed message for every cause, so the failure reveals nothing.
    """

    MESSAGE = "Invalid or expired reset token."

    def __init__(self) -> None:
        super().__init__(self.MESSAGE)


class PolicyViolation(Enum):
    TOO_SHORT = "TOO_SHORT"
    TOO_LONG = "TOO_LONG"
    COMMON = "COMMON"
    EQUALS_EMAIL = "EQUALS_EMAIL"
    SAME_AS_CURRENT = "SAME_AS_CURRENT"
    INVALID_TYPE = "INVALID_TYPE"


class PasswordPolicyError(PasswordResetError):
    """The new password violates the policy. The message holds enum names only."""

    def __init__(self, violations: tuple[PolicyViolation, ...]) -> None:
        self.violations = tuple(violations)
        names = ", ".join(v.name for v in self.violations)
        super().__init__(f"Password does not meet policy: {names}")
