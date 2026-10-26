"""Production implementations of Clock and TokenGenerator."""

from __future__ import annotations

import secrets
from datetime import datetime, timezone


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(timezone.utc)


class SecretsTokenGenerator:
    """256-bit URL-safe random tokens (43 characters)."""

    def new_token(self) -> str:
        return secrets.token_urlsafe(32)
