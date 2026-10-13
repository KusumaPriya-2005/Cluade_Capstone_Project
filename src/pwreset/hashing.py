"""Salted scrypt password hashing (stdlib)."""

from __future__ import annotations

import base64
import hashlib
import hmac
import os

_MAXMEM = 64 * 1024 * 1024
_DKLEN = 32


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


class ScryptPasswordHasher:
    """Format: ``scrypt$n$r$p$<b64 salt>$<b64 derived key>``."""

    def __init__(self, n: int = 2**14, r: int = 8, p: int = 1, salt_bytes: int = 16) -> None:
        self._n = n
        self._r = r
        self._p = p
        self._salt_bytes = salt_bytes

    def __repr__(self) -> str:
        return "ScryptPasswordHasher()"

    def hash(self, password: str) -> str:
        salt = os.urandom(self._salt_bytes)
        dk = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=self._n,
            r=self._r,
            p=self._p,
            maxmem=_MAXMEM,
            dklen=_DKLEN,
        )
        return f"scrypt${self._n}${self._r}${self._p}${_b64(salt)}${_b64(dk)}"

    def verify(self, password: str, stored: str) -> bool:
        try:
            scheme, n, r, p, salt_b64, dk_b64 = stored.split("$")
            if scheme != "scrypt":
                return False
            salt = base64.b64decode(salt_b64, validate=True)
            expected = base64.b64decode(dk_b64, validate=True)
            if not salt or len(expected) != _DKLEN:
                return False
            actual = hashlib.scrypt(
                password.encode("utf-8"),
                salt=salt,
                n=int(n),
                r=int(r),
                p=int(p),
                maxmem=_MAXMEM,
                dklen=_DKLEN,
            )
        except Exception:
            return False
        return hmac.compare_digest(actual, expected)
