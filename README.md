# pwreset

A small, framework-free password reset service layer. Python 3.11 or later, standard library only at runtime (pytest is the only dev dependency). Storage, email, sessions, clock and token generation are injected through `typing.Protocol` interfaces; in-memory repositories and a sliding-window rate limiter are included.

## Usage

```python
from pwreset import (
    InMemoryTokenRepository, InMemoryUserRepository, PasswordResetService,
    ResetConfig, ScryptPasswordHasher, SecretsTokenGenerator, SystemClock, User,
    normalize_password,
)

hasher = ScryptPasswordHasher()
users = InMemoryUserRepository()
# Registration is outside this library. It MUST hash the NFKC-normalised password.
users.add(User("u-1", "user@example.com", hasher.hash(normalize_password("Old-Password-123"))))

service = PasswordResetService(
    users, InMemoryTokenRepository(), my_email_sender, my_session_revoker,
    hasher, SystemClock(), SecretsTokenGenerator(), ResetConfig(),
)

ack = service.request_password_reset("User@Example.com ", client_id="203.0.113.7")
# The email contains ResetConfig.base_url + "?token=<token>".
service.confirm_password_reset(token, "A-New-Password-456", client_id="203.0.113.7")
```

`my_email_sender` implements `send(EmailMessage)`, and `my_session_revoker` implements `revoke_sessions(user_id)`.

Run the tests with `python -m pytest -q` (after `pip install pytest`). No network, no sleeping, no filesystem.

## Behaviour summary

- Tokens: 256-bit random (`secrets.token_urlsafe(32)`), only the SHA-256 is stored, 30-minute TTL, single use. A new request supersedes earlier tokens.
- Passwords: scrypt (n=2^14, r=8, p=1, 16-byte salt), self-describing format `scrypt$n$r$p$salt$key`. Policy: 12 to 128 characters, not on the denylist, not equal to the email, not equal to the current password.
- `confirm_password_reset` raises `InvalidResetTokenError` (one fixed message for every token failure) or `PasswordPolicyError` (only after the token is proven valid; the token is not consumed).

## Security notes

- **Uniform acknowledgement.** `request_password_reset` returns the same constant `ResetRequestAck` and raises nothing for registered, unknown, malformed, non-str and rate-limited input. Timing: in-process timing equality is NOT claimed. The repository write and the send call take time; use an `EmailSender` that only enqueues the message to hide this.
- **Unicode.** Passwords are NFKC-normalised (NIST SP 800-63B) before policy checks, the reuse check and hashing, so visually equivalent forms behave identically. Length counts code points of the normalised string. A raw-length guard (`> 4 * max_length`) rejects huge inputs before normalising; it is a cost bound, not a policy rule. Registration must hash `normalize_password(password)` or reuse detection and logins will not match.
- **Log policy.** The `pwreset` logger emits fixed event text plus the exception class name only. No identifier (user id, email, client id), token, password or exception message is ever logged. `repr` of the service, repositories, `User` (hash), and `EmailMessage` (body) hides secrets.
- **TTL and boundaries.** Expiry and limiter windows are exclusive at the boundary: a token is valid while `now < expires_at`, and a hit leaves the window when `hit_time <= now - window`.
- **Rate limiting** (sliding window, in memory, not thread-safe): 5/hour per email, 20/hour per client for requests, 10 invalid confirms/hour per client.
  - Counts are attempts, not sends. Both request limiters are evaluated on every request (no short-circuit), so a request denied by one still counts against the other.
  - Limiter keys are SHA-256 digests or fixed sentinels (`email:invalid`, `client:invalid`). The number of keys is unbounded; pruning happens on access.
  - A blocked client on confirm gets the same `InvalidResetTokenError`, even with a valid token. Policy violations are not counted as invalid attempts.
- **Trade-offs (inherent to the uniform response).**
  - Quota DoS (R8): anyone who knows an email can use up its 5/hour request quota and block that user's reset for the window.
  - Supersession DoS (R9): anyone who can request a reset for an email invalidates the owner's outstanding link, and because the old token is invalidated before sending, a swallowed send failure leaves the owner without a valid link (they can request again). Mitigation (CAPTCHA, authenticated client identification) is outside this library.
- **client_id contract (N2).** Callers must supply a non-empty, real client id. An empty, `None`, non-str or over-long (> 256) `client_id` maps to the shared `client:invalid` bucket. If a web layer passes junk for every user, all users share one 20/hour request bucket and are silently throttled.
- **Scope of "never raises" (N3).** The guarantee covers input values and types, not infrastructure failure. Exceptions from `users.get_by_email`, `tokens.issue`, the clock or the token generator propagate unchanged. Only `EmailSender.send` failures are swallowed (and logged by class name).
- **Failure after consume (B3).** Order is hash, consume, `set_password_hash`, revoke, notify. If `set_password_hash` raises, the exception propagates; with the in-memory repositories the token is already burned and the password unchanged. A real implementation must run `TokenRepository.consume` and the password write in one database transaction so a failed write rolls the consume back. `consume` maps to one conditional `UPDATE ... WHERE token_hash=:h AND used_at IS NULL AND expires_at > :now`. Revoker and notice failures are logged and do not undo the reset.
