"""Production defaults for injected collaborators."""

from __future__ import annotations

import secrets


class RandomIdGenerator:
    def new_id(self) -> str:
        return secrets.token_hex(4)
