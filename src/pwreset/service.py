"""Password reset orchestration."""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass

from .config import ResetConfig
from .errors import InvalidResetTokenError, PasswordPolicyError, PolicyViolation
from .interfaces import (
    Clock,
    EmailMessage,
    EmailSender,
    PasswordHasher,
    SessionRevoker,
    TokenGenerator,
    TokenRecord,
    TokenRepository,
    UserRepository,
)
from .policy import validate_password
from .rate_limit import SlidingWindowLimiter

# Log policy: fixed event text plus the exception class name only. No
# identifier (user id, email, client id), token, password or exception message.
_log = logging.getLogger("pwreset")

_MAX_EMAIL_RAW = 320
_MAX_EMAIL_NORM = 254
_MAX_CLIENT = 256
_MAX_TOKEN = 256
_EMAIL_INVALID_KEY = "email:invalid"
_CLIENT_INVALID_KEY = "client:invalid"


@dataclass(frozen=True)
class ResetRequestAck:
    """Constant acknowledgement returned on every request path."""

    message: str = "If the account exists, a reset email has been sent."


def _sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8", errors="surrogatepass")).hexdigest()


def _is_plausible_email(norm: str) -> bool:
    if len(norm) > _MAX_EMAIL_NORM or norm.count("@") != 1:
        return False
    if any(c.isspace() for c in norm):
        return False
    local, domain = norm.split("@")
    return bool(local) and bool(domain)


def _email_parts(raw: object) -> tuple[str, str | None]:
    """Return ``(limiter_key, normalized_or_None)``. Never raises."""
    if not isinstance(raw, str) or len(raw) > _MAX_EMAIL_RAW:
        return _EMAIL_INVALID_KEY, None
    norm = raw.strip().lower()
    key = "email:" + _sha256(norm)
    return key, (norm if _is_plausible_email(norm) else None)


def _client_key(client_id: object) -> str:
    """Limiter key for a client id.

    Empty, None, non-str or over-long values share the ``client:invalid`` bucket.
    """
    if not isinstance(client_id, str) or not client_id or len(client_id) > _MAX_CLIENT:
        return _CLIENT_INVALID_KEY
    return "client:" + _sha256(client_id)


def _token_hash(token: object) -> str | None:
    if not isinstance(token, str) or not token or len(token) > _MAX_TOKEN:
        return None
    return _sha256(token)


class PasswordResetService:
    def __init__(
        self,
        users: UserRepository,
        tokens: TokenRepository,
        email_sender: EmailSender,
        session_revoker: SessionRevoker,
        hasher: PasswordHasher,
        clock: Clock,
        token_gen: TokenGenerator,
        config: ResetConfig,
        *,
        email_limiter: SlidingWindowLimiter | None = None,
        client_limiter: SlidingWindowLimiter | None = None,
        invalid_confirm_limiter: SlidingWindowLimiter | None = None,
    ) -> None:
        rl = config.rate_limits
        self._users = users
        self._tokens = tokens
        self._sender = email_sender
        self._revoker = session_revoker
        self._hasher = hasher
        self._clock = clock
        self._token_gen = token_gen
        self._config = config
        self._email_limiter = email_limiter or SlidingWindowLimiter(clock, rl.per_email, rl.window)
        self._client_limiter = client_limiter or SlidingWindowLimiter(clock, rl.per_client, rl.window)
        self._invalid_limiter = invalid_confirm_limiter or SlidingWindowLimiter(
            clock, rl.invalid_confirm_per_client, rl.window
        )

    def __repr__(self) -> str:
        return "PasswordResetService()"

    def request_password_reset(self, email: str, client_id: str) -> ResetRequestAck:
        """Request a reset. Returns the same constant ack on every path.

        Never raises for any input value or type, and sends nothing for unknown,
        malformed or rate-limited requests. Swallowed: ``EmailSender.send``
        failures (logged as class name only). NOT swallowed (fail loudly):
        exceptions from ``users.get_by_email``, ``tokens.issue``, the clock or
        the token generator propagate unchanged.

        ``client_id`` contract: callers must pass a non-empty, real client
        identifier. An empty, ``None``, non-str or over-long value maps to the
        shared ``client:invalid`` bucket; if a web layer passes junk for every
        user, all users share one 20/hr request bucket and are silently throttled.
        """
        email_key, norm = _email_parts(email)
        client_key = _client_key(client_id)
        # Both limiters are always evaluated (no short-circuit).
        email_ok = self._email_limiter.hit(email_key)
        client_ok = self._client_limiter.hit(client_key)
        if email_ok and client_ok and norm is not None:
            user = self._users.get_by_email(norm)
            if user is not None:
                token = self._token_gen.new_token()
                now = self._clock.now()
                self._tokens.issue(
                    TokenRecord(_sha256(token), user.id, now + self._config.token_ttl)
                )
                try:
                    self._sender.send(
                        EmailMessage(
                            to=user.email,
                            subject="Reset your password",
                            body=f"{self._config.base_url}?token={token}",
                        )
                    )
                except Exception as exc:
                    _log.warning("reset send failed: %s", type(exc).__name__)
        return ResetRequestAck()

    def confirm_password_reset(self, token: str, new_password: str, client_id: str) -> None:
        """Set a new password using a reset token.

        Raises ``InvalidResetTokenError`` (one fixed message) for any token
        problem or a blocked client, and ``PasswordPolicyError`` for a bad
        password (only after the token is proven valid; the token is not
        consumed). Other exceptions (for example from ``set_password_hash``)
        propagate unchanged.
        """
        now = self._clock.now()
        ckey = _client_key(client_id)
        if self._invalid_limiter.is_blocked(ckey):
            raise InvalidResetTokenError()

        th = _token_hash(token)
        rec = self._tokens.peek_valid(th, now) if th is not None else None
        if rec is None:
            self._invalid_limiter.record(ckey)
            raise InvalidResetTokenError()

        user = self._users.get_by_id(rec.user_id)
        if user is None:
            self._invalid_limiter.record(ckey)
            raise InvalidResetTokenError()

        result = validate_password(self._config.policy, new_password, user.email)
        violations = list(result.violations)
        if not violations and result.normalized is not None:
            if self._hasher.verify(result.normalized, user.password_hash):
                violations.append(PolicyViolation.SAME_AS_CURRENT)
        if violations:
            raise PasswordPolicyError(tuple(violations))
        assert result.normalized is not None

        # Hash before consume so a hasher failure does not burn the token.
        new_hash = self._hasher.hash(result.normalized)
        if self._tokens.consume(th, now) is None:
            self._invalid_limiter.record(ckey)
            raise InvalidResetTokenError()

        self._users.set_password_hash(user.id, new_hash)

        try:
            self._revoker.revoke_sessions(user.id)
        except Exception as exc:
            _log.error("session revoke failed: %s", type(exc).__name__)
        try:
            self._sender.send(
                EmailMessage(
                    to=user.email,
                    subject="Your password was changed",
                    body="Your password was changed. If this was not you, contact support.",
                )
            )
        except Exception as exc:
            _log.warning("password change notice failed: %s", type(exc).__name__)
