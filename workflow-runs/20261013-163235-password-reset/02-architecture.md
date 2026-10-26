# 2. Architecture (run 20261013-163235-password-reset) - revision 1 (design-review rework round 1 of 2)

## Overview
A small, framework-free, stdlib-only Python 3.11 package, `pwreset`, in a `src/` layout. A single `PasswordResetService` orchestrates two operations: `request_password_reset(email, client_id)` and `confirm_password_reset(token, new_password, client_id)`. Everything with side effects or nondeterminism is injected through `typing.Protocol` interfaces: Clock, TokenGenerator, EmailSender, SessionRevoker, UserRepository, TokenRepository and PasswordHasher. In-memory repositories and a sliding-window rate limiter are included.

- Only the SHA-256 of the token is persisted. Passwords use salted scrypt.
- Request never raises, for any input type. It always returns the same constant acknowledgement.
- Honest uniformity claim (FR-2/NFR-1): same outward result, same exceptions (none) and same limiter behaviour for registered, unknown, malformed and non-str input. Timing differences from the repository write and the send call are mitigated by an async or enqueuing sender, which is documented. In-process timing equality is not claimed.
- All invalid-token failures raise one error type with one fixed message.
- The atomic "consume token" is a single repository method. A real database implements it as one conditional UPDATE, in the same transaction as the password write (see B3 handling below).
- Accepted defaults: 30-minute TTL with exclusive expiry, 12-128 character policy with a small denylist, 5/hr per email, 20/hr per client, reject reuse of the current password, FR-11 and FR-12 in scope, in-memory only, coverage as a target. A proposed invalid-confirm limit of 10/hr per client is flagged for the human.

## Package layout
```
pyproject.toml            # requires-python >=3.11; no runtime deps; [project.optional-dependencies] dev = ["pytest"]; pythonpath=["src"], testpaths=["tests"]
README.md                 # usage + security notes (NFR-6)
src/pwreset/
  __init__.py             # public exports
  errors.py               # exception types
  config.py               # ResetConfig, PasswordPolicy, RateLimitConfig (frozen dataclasses)
  interfaces.py           # Protocols + plain dataclasses (User, TokenRecord, EmailMessage)
  system.py               # SystemClock, SecretsTokenGenerator
  hashing.py              # ScryptPasswordHasher
  policy.py               # validate_password(policy, password, email) -> list[PolicyViolation]
  rate_limit.py           # SlidingWindowLimiter
  memory.py               # InMemoryUserRepository, InMemoryTokenRepository
  service.py              # PasswordResetService, ResetRequestAck
tests/
  conftest.py             # fakes + fixtures
  test_request.py  test_confirm.py  test_tokens_storage.py  test_hashing.py
  test_policy.py  test_rate_limit.py  test_hooks_notify.py  test_no_leaks.py
```
pytest is the only dev dependency. Coverage (NFR-5, a target and not a gate) is measured ad hoc. `pytest-cov` is not listed and would be added only if the human approves it in the plan.

## Components

**errors.py**
- `PasswordResetError(Exception)` is the base class.
- `InvalidResetTokenError`: unknown, malformed, non-str, tampered, expired, used, superseded, owner deleted, or client blocked on confirm. It has a single fixed message, "Invalid or expired reset token.", and carries no fields.
- `PasswordPolicyError(violations: tuple[PolicyViolation, ...])`. `PolicyViolation` is an Enum: `TOO_SHORT`, `TOO_LONG`, `COMMON`, `EQUALS_EMAIL`, `SAME_AS_CURRENT`, `INVALID_TYPE`. The message is built from the fixed enum names only and never includes the password.
- Rate limiting on request never raises. On confirm it raises `InvalidResetTokenError` (D5).
- Any other exception (for example from `set_password_hash`) propagates unchanged. See "Failure after consume".

**interfaces.py** (structural Protocols)
- `Clock.now() -> datetime`: timezone-aware UTC.
- `TokenGenerator.new_token() -> str`.
- `EmailSender.send(message: EmailMessage) -> None`.
- `SessionRevoker.revoke_sessions(user_id: str) -> None`.
- `PasswordHasher.hash(password) -> str` and `verify(password, stored) -> bool`.
- `UserRepository`:
  - `get_by_email(normalized_email) -> User | None`
  - `get_by_id(user_id) -> User | None` (**added, B1**)
  - `set_password_hash(user_id, password_hash) -> None`
- `TokenRepository`:
  - `issue(record: TokenRecord) -> None`: atomically supersedes all outstanding records for `record.user_id`, then stores the new one.
  - `peek_valid(token_hash, now) -> TokenRecord | None`: read-only. Returns the record only if it exists, is unused, and `now < expires_at`.
  - `consume(token_hash, now) -> TokenRecord | None`: atomic check-and-mark-used. It returns the record if this call won, otherwise `None`. A SQL implementation is `UPDATE ... SET used_at=:now WHERE token_hash=:h AND used_at IS NULL AND expires_at > :now`, then check the row count.
  - Documented contract: a real implementation should run `consume` and the following `set_password_hash` in one transaction, so a failed password write rolls the consume back (B3). The in-memory implementation cannot do this and its behaviour is pinned by a test.
- Dataclasses:
  - `User(id, email, password_hash)`: `password_hash` has `repr=False`. `email` is stored normalized. `id` is an opaque identifier (for example a UUID string), never derived from the email.
  - `TokenRecord(token_hash, user_id, expires_at, used_at=None)`: no plaintext field, which satisfies AC-4 structurally.
  - `EmailMessage(to, subject, body)`: `body` has `repr=False` because it carries the token.

**config.py**
- `PasswordPolicy(min_length=12, max_length=128, denylist=frozenset({...small list...}), forbid_email=True)`.
- `RateLimitConfig(per_email=5, per_client=20, invalid_confirm_per_client=10, window=timedelta(hours=1))`. The 10/hr invalid-confirm default is a proposal, listed under "Decisions needed from the human".
- `ResetConfig(token_ttl=timedelta(minutes=30), base_url="https://example.invalid/reset", policy, rate_limits)`.

**system.py**
- `SystemClock` returns `datetime.now(timezone.utc)`.
- `SecretsTokenGenerator` returns `secrets.token_urlsafe(32)`, which is 256 bits.

**hashing.py**: `ScryptPasswordHasher(n=2**14, r=8, p=1, salt_bytes=16)`
- `hash` is `hashlib.scrypt` with an `os.urandom` salt. The output is a self-describing string `scrypt$n$r$p$<b64 salt>$<b64 dk>`, so parameters can be upgraded later.
- `verify` parses the string, recomputes, and compares with `hmac.compare_digest`. A malformed stored value returns False.
- `n`, `r` and `p` are constructor parameters so tests can use a cheap `n=2**4`.
- It sets `maxmem` explicitly (for example 64 MiB).
- It is never called with a password longer than `max_length` after normalisation, because the policy check runs first. This bounds the scrypt cost an attacker can trigger (A7).

**policy.py**: pure function `validate_password(policy, password, normalized_email) -> list[PolicyViolation]`.
- Non-str input returns `[INVALID_TYPE]` and does no other work.
- Unicode decision (A7): the password is normalised with NFKC (`unicodedata.normalize`, stdlib) before any policy check, reuse check or hashing. This follows NIST SP 800-63B guidance, so visually equivalent forms hash identically. Length is `len()` of the normalised string, which counts code points and not graphemes.
- Cheap guard before normalisation: if the raw `len(password)` exceeds `4 * max_length`, return `[TOO_LONG]` without normalising. This bounds the normalisation cost.
- The denylist match is casefolded. Equality to the email is case-insensitive.
- `max_length` is enforced before any hashing. The service skips `hasher.verify` and `hasher.hash` whenever there are violations.
- The same normalisation function (`normalize_password`) is exposed and used by the service for hash and verify.
- The reuse check (`SAME_AS_CURRENT`) lives in the service because it needs the hasher and the current hash.

**rate_limit.py**: `SlidingWindowLimiter(clock, limit, window)`
- State is `dict[str, deque[datetime]]`. Keys are always short fixed-format strings (see key derivation below).
- `_prune(key, now)` drops timestamps `<= now - window`, the same exclusive-at-boundary convention as the TTL. It deletes empty keys.
- `is_blocked(key) -> bool`: true if the count is at least the limit. It does not record.
- `record(key) -> None`.
- `hit(key) -> bool`: if not blocked, record and return True. Otherwise return False without recording, so denied attempts do not extend the lockout and the key recovers when the window passes.
- Three instances are held by the service: per-email, per-client-request, and per-client-invalid-confirm.
- Semantics (A1, documented in the README):
  - Counts reflect attempts and not sends. Both request limiters are evaluated on every request with no short-circuit. A request denied by the client limiter still counts against the email limiter, and the reverse.
  - Inherent trade-off: anyone who knows a victim's email can burn its 5/hr quota and block that user's reset for the window. This follows from FR-9 plus the uniform response, because a distinguishable response would leak state. Mitigation is outside this library (caller-side CAPTCHA, authenticated client identification).

**memory.py**
- `InMemoryUserRepository`: dict by normalized email plus a `by_id` index. Helpers: `add(user)` and a test-only `snapshot() -> dict[str, User]` (A8).
- `InMemoryTokenRepository`: `by_hash: dict[str, TokenRecord]` and `by_user: dict[str, str]`.
  - `issue` removes the user's previous hash from `by_hash` (found via `by_user`), stores the new record, and updates `by_user`. Older tokens become unknown and fail with the same error (AC-7).
  - `consume` (A4) is single-valued. It removes the record from `by_hash` and its `by_user` entry, and returns the record only once. A second call returns `None` (AC-6). A later `issue` therefore never touches a stale hash. `used_at` exists on `TokenRecord` for SQL parity, and the in-memory store simply deletes consumed records.
  - Test-only `snapshot() -> list[TokenRecord]` returns all stored records, and `dump() -> str` (the repr of the snapshot) is what AC-4 asserts against.
  - No locks are used (NFR-7 does not require them).

**service.py**: `PasswordResetService(users, tokens, email_sender, session_revoker, hasher, clock, token_gen, config)`
- Constructor wiring only, with a `__repr__` that prints just the class name.
- `ResetRequestAck`: a frozen dataclass with a fixed `message` ("If the account exists, a reset email has been sent."), compared by value.
- Input hardening helpers (B2, A5):
  - `_email_parts(raw) -> tuple[str, str | None]` returns `(limiter_key, normalized_or_None)`.
    - If `raw` is not a `str` or `len(raw) > 320`, return `("email:invalid", None)`, a fixed sentinel key.
    - Otherwise `norm = raw.strip().lower()`. The key is `"email:" + sha256(norm).hexdigest()`, which is fixed size. `normalized` is `norm` if `_is_plausible_email(norm)` (length at most 254, exactly one `@`, non-empty local and domain parts, no whitespace), else `None`.
    - Implausible emails never reach the repository.
  - `_client_key(client_id) -> str`: a non-str, empty, or `len > 256` value maps to the sentinel `"client:invalid"`. Otherwise `"client:" + sha256(client_id).hexdigest()`. Sentinel buckets are shared, so garbage input is limited together. This is harmless to real users and never raises.
  - `_token_hash(token) -> str | None`: returns `None` for a non-str, empty, or `len > 256` token (treated as invalid). Otherwise it returns the sha256 hex.

## Data model
- `User{id, email(normalized, unique), password_hash}`.
- `TokenRecord{token_hash (sha256 hex of the token), user_id, expires_at, used_at|None}`.
- Token hash: SHA-256 of the high-entropy token. A slow KDF is unnecessary for a 256-bit random secret. The lookup is by exact hash in a dict or index, so there is no secret-dependent string comparison (NFR-1).
- Rate-limiter state is in-memory only: key to deque of timestamps. Keys are fixed-size digests or fixed sentinels, so key size is bounded (A5). The number of keys is still unbounded, which is documented in R4.

## Data flow

**Request** `request_password_reset(email, client_id) -> ResetRequestAck`. It never raises.
```
email_key, norm = _email_parts(email)
client_key = _client_key(client_id)
email_ok  = email_limiter.hit(email_key)       # both always evaluated, no short-circuit
client_ok = client_limiter.hit(client_key)
if email_ok and client_ok and norm is not None:
    user = users.get_by_email(norm)
    if user is not None:
        token = token_gen.new_token()
        tokens.issue(TokenRecord(sha256(token), user.id, now + ttl))   # supersedes earlier token
        try: email_sender.send(EmailMessage(to=user.email, body=base_url + token))
        except Exception: log fixed event "reset send failed", exception TYPE only
return ACK   # identical constant on every path
```
- The dummy token and message work on the unknown path is dropped (A3). It was cosmetic, it gave no real timing guarantee, and it coupled `SequenceTokenGenerator` consumption to the path. The token generator is now called exactly once per real issue.
- Honest claim: the paths are indistinguishable by return value, exceptions and limiter behaviour. The remaining timing difference (repository lookup, write and send call) is mitigated by a production sender that enqueues, documented in the README. Tests assert no write, no send and an equal ack, and do not assert wall-clock equality.
- Supersession and failed send (A2): `issue` happens before `send`. If the send fails (swallowed), the user's earlier link is already dead and no new token was delivered. The user can request again. Accepted and documented, with a test pinning it. Re-ordering was rejected because the token must be stored before it is delivered, otherwise a fast click races the write.
- Inherent to FR-5 (A2, documented): anyone who can trigger a request for an email can invalidate the owner's outstanding link. This is the counterpart of the quota DoS above.

**Confirm** `confirm_password_reset(token, new_password, client_id) -> None`
```
now = clock.now()                              # read once; one FakeClock is shared by all components
ckey = _client_key(client_id)
if invalid_limiter.is_blocked(ckey): raise InvalidResetTokenError      # AC-13, even with valid token
th = _token_hash(token)                        # None for non-str / empty / over-long
rec = tokens.peek_valid(th, now) if th else None
if rec is None: invalid_limiter.record(ckey); raise InvalidResetTokenError
user = users.get_by_id(rec.user_id)
if user is None:                               # B1: owner deleted after issue
    invalid_limiter.record(ckey); raise InvalidResetTokenError
pw = normalize_password(new_password) if isinstance(new_password, str) else None
violations = validate_password(policy, new_password, user.email)       # INVALID_TYPE for non-str, length check first
if not violations and hasher.verify(pw, user.password_hash): violations.append(SAME_AS_CURRENT)
if violations: raise PasswordPolicyError(violations)   # token not consumed (AC-9); not counted as an invalid attempt
new_hash = hasher.hash(pw)                     # before consume, so a hasher failure does not burn the token
if tokens.consume(th, now) is None:            # lost a race
    invalid_limiter.record(ckey); raise InvalidResetTokenError
users.set_password_hash(user.id, new_hash)     # may raise: see "Failure after consume"
try: session_revoker.revoke_sessions(user.id)
except Exception: log fixed event "session revoke failed" + opaque user_id + exception type
try: email_sender.send(password-changed notice to user.email)
except Exception: log fixed event "notice send failed", exception type only
```
- B2 confirm behaviour for bad types:
  - A non-str, empty or over-long `token` is invalid. It records an invalid attempt and raises `InvalidResetTokenError`.
  - A non-str `new_password` is only examined after the token is proven valid. It then raises `PasswordPolicyError((INVALID_TYPE,))`, the token is not consumed, and nothing is hashed.
  - A non-str `client_id` maps to the sentinel key, so confirm never fails for that reason.

## Failure after consume (B3)
The order is `consume`, then `set_password_hash`, then revoke, then notify.
- If `set_password_hash` raises, the exception propagates unchanged to the caller. The in-memory token is already consumed and the password is unchanged. Revoker and notifier are not called. No invalid attempt is recorded. The user must request a new reset.
- This is explicitly accepted for the in-memory implementation. The caller learns of the failure (no silent success), and no state is half-applied. A leaked token is never usable, so security is not weakened, only availability.
- Rejected alternatives: write the password first and then consume (a crash or race leaves a usable token on a changed account, and two requests can both write); best-effort "un-consume" (non-atomic, and it re-opens a used token).
- Production guidance (README and `TokenRepository` docstring): a real implementation does consume and password write in one database transaction. Then a failed write rolls the consume back and the token stays usable. NFR-7 is satisfied because the interface shape allows this. The service does not own transactions (no new unit-of-work interface, to keep scope small).
- Revoker and notifier failures (R3) are logged and do not undo the reset.

## Error handling
- Request never raises for any input, including `None`, `int` and `bytes` for `email` or `client_id`. Sender failures are swallowed and logged with the exception type only.
- Confirm raises only `InvalidResetTokenError` (identical type and message for every token failure, AC-8), `PasswordPolicyError` (only after the token is proven valid, so it leaks nothing), or an unexpected repository or hasher exception, which propagates (B3).
- Logging uses a `pwreset` logger and fixed event strings. No email, token, password or exception message text is logged, only the exception class name.
- Decision (A6): the revoker-failure event also logs the opaque `user_id`, because a failed revocation is security-relevant and ops must know whose sessions survived. `user_id` is an opaque identifier (not the email) and AC-15 covers only tokens and passwords. No other event logs an identifier. Because the request path must not leak existence, `user_id` is never logged on the request path.
- Secret-bearing dataclass fields use `repr=False`.

## Test layout (pytest, no sleeps, no network)
`conftest.py` provides:
- One `FakeClock` (settable `now`, `advance()`), shared by the service and all three limiters, so the service and limiter always read the same time (A8).
- `RecordingEmailSender` (list of messages, optional raise, optional exception text).
- `RecordingRevoker` (optional raise).
- `SequenceTokenGenerator` (deterministic tokens).
- A cheap `ScryptPasswordHasher(n=2**4)` fixture.
- A `service` factory fixture that exposes the repositories, limiters and fakes.
- A failing-users wrapper whose `set_password_hash` raises (B3).

| AC | Test file / focus |
|---|---|
| AC-1 | test_request: registered email gives exactly one message to that address containing the token |
| AC-2 | test_request: unknown, malformed and non-str (`None`, `int`, `bytes`, over-long) emails, parametrized, give no email, no repository write, no exception, and an ack equal to the registered case. Also non-str `client_id` (`None`, `int`, `bytes`) never raises. The token generator is not called on these paths |
| AC-3 | test_request: parametrized case and whitespace variants |
| AC-4 | test_tokens_storage: `snapshot()`/`dump()` of the token repository contains the sha256 hash and not the plaintext token |
| AC-5 | test_confirm: success at T+N-1s and at T+N-1 microsecond; failure at exactly T+N, T+N+1 microsecond and later (exclusive boundary) |
| AC-6 | test_confirm: second use fails, the hash is unchanged, and `by_user` is cleared (a later issue works cleanly) |
| AC-7 | test_confirm: two requests, the older token fails and the newer works |
| AC-8 | test_confirm: unknown, malformed, non-str (`None`, `int`, `bytes`), tampered, expired and used tokens all raise the same type and `str()` |
| AC-9 | test_policy plus test_confirm: short, long, common, equals-email, same-as-current and non-str password each raise `PasswordPolicyError`, then the same token still works. Also a test that an over-long password never reaches the hasher (spy hasher) and that NFKC-equivalent forms are treated as equal (for example a full-width password versus its ASCII form for the reuse check) |
| AC-10 | test_hashing: verify new succeeds and old fails; hash differs from plaintext; two hashes of the same password differ; self-describing format; one test with default scrypt params |
| AC-11 | test_rate_limit: 5 sends then the 6th is silent and returns the same ack; at window minus 1 microsecond still blocked and at exactly the window accepted again; a test pinning that a request denied by the client limiter still counts against the email limiter (A1) |
| AC-12 | test_rate_limit: 20 different emails from one client, the 21st sends nothing |
| AC-13 | test_rate_limit: N invalid confirms, then a valid token is rejected; after the window it succeeds. Includes a deleted-owner invalid attempt and non-str token attempts counting toward the limit |
| AC-14 | test_hooks_notify: revoker called once with the user id; one notice sent to the user's email; revoker or sender failure does not break the reset |
| AC-15 | test_no_leaks: caplog and `repr` of service, repositories, `EmailMessage`, `User`, `TokenRecord`, and the exception strings contain neither token nor password. A sender that raises with the token in its message must produce a log with only the exception type. The revoker-failure log contains the user id but neither token nor password |
| AC-16 | whole suite: only injected clock and fakes, no `time.sleep`, no sockets |
| Extra B1 | test_confirm: owner deleted after issue gives `InvalidResetTokenError` and an invalid-attempt record |
| Extra B3 | test_confirm: `set_password_hash` raises, so the exception propagates, the token is burned (second use fails), the password is unchanged, and the revoker and notice sender are not called |
| Extra A2 | test_request: send failure after issue leaves the earlier token invalid and the ack equal; a second request after a successful send supersedes the first token |

## Key decisions

| ID | Decision | Alternatives rejected | Reason |
|---|---|---|---|
| D1 | Token hash is SHA-256; the token is 32 random bytes (urlsafe) | Slow KDF for tokens; HMAC with a server key; storing plaintext | 256-bit random secrets do not need stretching. A fast hash gives O(1) lookup by hash, with no timing oracle and no key management. |
| D2 | Passwords use `hashlib.scrypt` (n=2^14, r=8, p=1, 16-byte salt, self-describing string) | `pbkdf2_hmac`; a third-party argon2/bcrypt | scrypt is memory-hard and in the stdlib. The hasher is a Protocol, so swapping is easy. |
| D3 | Uniform response is a constant `ResetRequestAck`; request never raises for any input type; sender errors are swallowed | Returning a bool or the sent status; raising on rate limit; propagating sender errors | Any difference in output or exceptions leaks existence or limit state. |
| D4 (revised) | Uniformity means same return value, same exceptions and same limiter behaviour on all paths. Limiters are keyed by a fixed-size digest of the normalized email whether or not it exists. No dummy token or message work. The send-delay timing is mitigated by an async sender, documented | Dummy work or dummy sends on the unknown path; a fixed `sleep` pad | Dummy work was cosmetic, gave no real guarantee, and coupled test generator order to the path. Sleeping is slow and untestable. |
| D5 | A blocked client on confirm gets the same `InvalidResetTokenError` | A distinct `RateLimitedError` | One error shape means limiter state cannot be a token-validity oracle. |
| D6 | Atomic consume is `consume(hash, now) -> record or None`, preceded by a read-only `peek_valid` so policy errors do not burn the token. The new hash is computed before consume | A single `get` plus a separate `mark_used`; consuming before validation and restoring on failure | One check-and-set maps to a conditional UPDATE and removes the double-use race (NFR-7). |
| D7 | Supersession is part of `TokenRepository.issue` | A separate invalidate call; "latest-wins" at confirm | One atomic operation, with no window in which two tokens are valid. |
| D8 | Expiry and limiter windows use the same exclusive boundary | Inclusive boundary | Matches the accepted decision, and one rule is easy to test. |
| D9 | Sliding-window log limiter with denied hits not recorded, and both request limiters always evaluated | Fixed-window counters; token bucket; recording denied hits; short-circuiting | Exact with an injected clock and recovers on schedule. Counts mean attempts, not sends. |
| D10 | The reuse check verifies against the current hash, as violation `SAME_AS_CURRENT`, and only runs when there are no other violations | Skipping it; comparing plaintext | Accepted requirement. It is only reachable after the token is proven valid, and skipping on other violations bounds scrypt cost. |
| D11 | Time is aware-UTC `datetime` from `Clock.now()` | Float epoch; naive datetimes | Clear arithmetic and easy to fake. |
| D12 | `src/` layout, pure-stdlib runtime, flat module set (about 9 files) | A sub-package per layer; a single file | Small enough to review. |
| D13 | `UserRepository.get_by_id`; `None` after token validation maps to `InvalidResetTokenError` plus an invalid-attempt record | Raising a distinct error; ignoring the missing user | Keeps one error shape and does not reveal that an account was deleted. |
| D14 | After `consume`, a `set_password_hash` failure propagates and the token stays burned in memory. Real implementations do both in one transaction | Password first, then consume; best-effort un-consume; a new unit-of-work interface | Avoids a usable token on a changed account, and avoids non-atomic restore. A unit-of-work interface is over-scoped here. |
| D15 | Bad types: non-str email or client_id uses a sentinel key (email path treated as unknown); non-str or over-long token is invalid; non-str password gives `INVALID_TYPE` only after token validation | Raising `TypeError`; coercing with `str()` | Request must never raise, and `str()` coercion could stringify secrets. |
| D16 | Limiter keys are sha256 digests (or fixed sentinels) with input length caps (email 320 raw, client 256, token 256) | Raw strings as keys | Bounds key size and hashing cost against attacker-chosen input. Key count remains unbounded (R4). |
| D17 | Passwords are NFKC-normalised before policy, reuse check and hash; `max_length` is enforced before any hashing | No normalisation; NFC only | Follows NIST SP 800-63B, and visually equal passwords behave identically. |
| D18 | The revoker-failure log includes the opaque `user_id`; no other event logs an identifier | Log no identifiers at all | A failed revocation is security-relevant and ops must act on it. The id is opaque and is not a token or password. |
| D19 | In-memory `consume` deletes the record and clears `by_user`; test-only `snapshot()` accessors on both in-memory repositories | Marking `used_at` and keeping stale pointers | A single behaviour. AC-6 needs only that a second consume returns `None`. |

## Risks
- R1 A timing side channel remains for the repository lookup, write and send call. Mitigation: a production sender should enqueue (documented). Tests assert no write, no send and an equal ack, and do not assert wall-clock equality.
- R2 `hashlib.scrypt` may be missing or limited on some OpenSSL builds. The default `n=2^14` needs about 16 MiB, so `maxmem` is set explicitly. The implementer should verify on this Windows environment.
- R3 Revoker or notifier failures after the commit are logged (the revoker failure with the opaque user id) and not rolled back. A failed revocation could leave old sessions alive. Ops should alert on the event.
- R4 The in-memory limiter dicts can grow without bound under many unique keys. Key size is now bounded, but key count is not, and pruning happens only on access. Acceptable for this scope, noted in the README.
- R5 The in-memory repositories are not thread-safe (NFR-7). The Protocols keep a real atomic and transactional implementation possible.
- R6 Rate limiting by the caller-supplied `client_id` is only as good as that value (spoofable, or shared behind a NAT). The caller's concern.
- R7 Email plausibility is deliberately minimal, so a malformed but plausible address can reach the sender. Deliverability validation is out of scope.
- R8 Quota DoS (inherent to FR-9 plus the uniform response): anyone knowing an email can exhaust its 5/hr request quota. Documented in the README security notes.
- R9 Supersession DoS (inherent to FR-5): anyone who can request a reset for an email can invalidate the owner's outstanding link, and a swallowed send failure leaves the owner with no valid link. Documented and pinned by a test.
- R10 In-memory failure after consume: a failing `set_password_hash` burns the token. Documented, tested, and resolved in a real implementation by one transaction.
- R11 The shared sentinel buckets (`email:invalid`, `client:invalid`) mean junk input is limited collectively. This is harmless to real users and keeps the path uniform.

## Decisions needed from the human
1. Invalid-confirm limit: confirm the proposed default of 10 invalid confirm attempts per client per hour (it was not in the accepted defaults and is configurable). It was open question 4 in the requirements and is not yet answered.
2. Acknowledge the inherent trade-offs: the quota DoS (R8) and the supersession DoS (R9).
3. Confirm NFKC normalisation of passwords (D17). If it is declined, the fallback is no normalisation, with the same `max_length` guard.
4. Confirm logging the opaque `user_id` on revoker failures (D18). If it is declined, the fallback is no identifier.
5. Confirm that `pytest-cov` is not added. Coverage is measured ad hoc unless the human approves it.

## Changes since round 0
- B1: Added `UserRepository.get_by_id` to the interface list. In confirm, `None` after token validation raises `InvalidResetTokenError` and records an invalid attempt (D13, test "Extra B1").
- B2: Request never raises for non-str `email` or `client_id`. Non-str or over-long email maps to the sentinel key `email:invalid` and the unknown path. Non-str or over-long `client_id` maps to `client:invalid`. Implausible emails skip the repository. Confirm defines behaviour for a non-str token (invalid, counted) and a non-str `new_password` (`PasswordPolicyError(INVALID_TYPE)` after token validation, not consumed). New `INVALID_TYPE` violation, D15, and parametrized tests for `None`, `int` and `bytes`.
- B3: Behaviour after consume is explicit. A `set_password_hash` exception propagates, the token stays burned, the password is unchanged, and hooks do not run. The hash is now computed before consume. The `TokenRepository` contract and the README state that a real implementation does consume and the password write in one transaction. Test "Extra B3" added (D14, R10).
- A1: Rate-limit semantics (attempts not sends, no short-circuit) and the quota DoS documented as inherent (D9, R8). Test pinning that a client-denied request still counts against the email limiter.
- A2: Supersession-before-send and the failed-send outcome are accepted and documented as inherent to FR-5 (R9). Test "Extra A2" pins it. No re-ordering.
- A3: FR-2/NFR-1 claim reworded to "same outward result and limiter behaviour; timing mitigated by an async sender". The dummy token and message work is dropped (D4). The token generator is called once per real issue.
- A4: In-memory `consume` deletes the record and clears `by_user` (D19). AC-6 test checks it.
- A5: Limiter keys are sha256 digests or fixed sentinels, with length caps checked before hashing and before the limiter (D16). README note on key count (R4).
- A6: The opaque `user_id` is logged for revoker failures only, as a fixed-text event (D18). Test with a sender that raises an exception containing the token. The log shows only the exception type.
- A7: NFKC decision documented (D17). `max_length` is enforced before any hashing, and a spy-hasher test checks it. The reuse check is skipped when other violations exist.
- A8: Test-only `snapshot()` accessors on both in-memory repositories (and `dump()` for AC-4). The AC-2 row is fixed to "no write, no send, equal ack". One FakeClock is shared by the service and all limiters.
- A9: Microsecond boundary tests added to the AC-5 and AC-11 rows.
- A10: `pytest-cov` removed from the layout. pytest is the only dev dependency.
- A11: The invalid-confirm limit default of 10/hr is listed first under "Decisions needed from the human".
