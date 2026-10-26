# 1. Requirements (run 20261013-163235-password-reset)

**Goal**: Provide a small, testable Python library/service layer that lets a user who forgot their password request a reset via their registered email address and set a new password with a secure, expiring, single-use token. The design must resist account enumeration and abuse. No web framework, real email, or real database is in scope.

Codebase check: the workspace is greenfield. Only the `.claude` scaffold exists and there is no application code, so there are no existing user, auth, or hashing modules to reuse or conflict with.

## Functional requirements
- FR-1: Request reset. `request_password_reset(email)` accepts an email address. If it matches a registered account, the service generates a reset token and hands a reset message (containing the token) to an injected email-sender interface.
- FR-2: Uniform response. The request operation returns the same outward result, and takes no externally observable different path, whether or not the email is registered (no account enumeration). This also covers malformed or unknown emails.
- FR-3: Token generation. Tokens are cryptographically random with at least 128 bits of entropy (e.g. `secrets`). Only a hash of the token is stored, never the plaintext.
- FR-4: Token expiry. Each token expires after a configurable TTL (default proposed: 30 minutes). Expired tokens are rejected.
- FR-5: Single use. A token is consumed on successful use and cannot be reused. A newly issued token for the same account invalidates earlier outstanding tokens.
- FR-6: Confirm reset. `confirm_password_reset(token, new_password)` validates the token (exists, unexpired, unused) and the new password against the policy. On success it updates the stored password hash and consumes the token.
- FR-7: Password policy. The new password must meet a configurable policy (proposed default: at least 12 characters, a maximum length of 128, not equal to the email, not in a small common-password denylist). Violations are rejected with a clear, non-sensitive error and the token is NOT consumed.
- FR-8: Password storage. Passwords are stored only as salted hashes using a slow KDF available in the Python stdlib (e.g. `hashlib.scrypt` or `pbkdf2_hmac`). Plaintext passwords and tokens are never logged or stored.
- FR-9: Rate limiting. Reset requests are limited per email (normalised) and per client identifier (e.g. IP, passed in as a string), with configurable limits (proposed default: 5 per hour per email, 20 per hour per client). Excess requests return the same uniform response as FR-2 without sending email. Confirm attempts with invalid tokens are also limited per client.
- FR-10: Email normalisation. Emails are compared case-insensitively after trimming whitespace.
- FR-11: Session and credential invalidation hook. After a successful reset, the service calls an injectable callback or interface (e.g. `revoke_sessions(user_id)`), so existing sessions can be revoked.
- FR-12: Notification. After a successful reset, a "your password was changed" notice is sent via the email-sender interface.
- FR-13: Persistence abstraction. Users and tokens are accessed through repository interfaces, with in-memory implementations provided for tests and demo. Clock, token generator, and email sender are injectable for deterministic tests.

## Non-functional requirements
- NFR-1: Security. Use constant-time comparison or hash lookup for tokens. Keep timing differences between known and unknown emails minimal (e.g. do equivalent work, or do the sending asynchronously or injected). Error messages must not reveal account existence.
- NFR-2: No secrets, tokens, or passwords in logs, exceptions, or `repr` output.
- NFR-3: Python 3.10 or later (to be confirmed). Standard library only for runtime code, with pytest as the only dev dependency. Add no other dependencies.
- NFR-4: Testability. All time, randomness, and I/O are injected. The tests are deterministic and need no network or filesystem.
- NFR-5: Test coverage. Every acceptance criterion has at least one pytest test, and branch coverage of the core module is at least 90% (target, not a gate unless confirmed).
- NFR-6: Code is typed (type hints), with docstrings on the public API, and a short README section on usage and security notes.
- NFR-7: Thread safety for the in-memory stores is not required, but the interfaces must not preclude an atomic "consume token" operation. This prevents double-use races in a real database.

## Acceptance criteria
- AC-1: Given a registered email, when `request_password_reset` is called, then exactly one message containing a token is passed to the email sender, addressed to that email.
- AC-2: Given an unregistered or malformed email, when `request_password_reset` is called, then no email is sent and the return value and raised exceptions (none) are identical to the registered-email case.
- AC-3: Given a registered email with different letter case or surrounding whitespace, when a reset is requested, then it is treated as the registered account.
- AC-4: Given a stored token record, then it contains only the token hash. The plaintext token appears nowhere in the repository state.
- AC-5: Given a token issued at time T with TTL N, when confirm is called at T+N or later (boundary to be fixed in the design), then it fails with an invalid-token error. When called before expiry, it succeeds.
- AC-6: Given a token that was already used successfully, when confirm is called again with it, then it fails and the password is unchanged.
- AC-7: Given two tokens requested for the same account, when the older one is used after the newer was issued, then the older one fails.
- AC-8: Given an unknown, malformed, or tampered token, when confirm is called, then it fails with the same error type and message as an expired or used token.
- AC-9: Given a valid token and a password violating the policy (too short, too long, common, equal to email), when confirm is called, then it fails with a policy error and the token remains usable until expiry.
- AC-10: Given a valid token and a compliant password, when confirm is called, then the stored hash verifies the new password and does not verify the old one. The stored value is not the plaintext and uses a per-password salt (two hashes of the same password differ).
- AC-11: Given the per-email limit has been reached, when further requests are made within the window, then no additional emails are sent and the response remains identical to AC-2. After the window passes, requests are accepted again.
- AC-12: Given the per-client limit has been reached across different emails, then further requests from that client send no email.
- AC-13: Given repeated invalid-token confirm attempts beyond the limit from one client, then further attempts are rejected, even with a valid token, until the window passes.
- AC-14: Given a successful reset, then the session-revocation hook is called once with the user id, and a password-changed notice is sent to the user's email.
- AC-15: Given any operation, then logs, exception messages, and `repr` of service objects contain neither plaintext tokens nor passwords (verified by caplog and string assertions).
- AC-16: Given the test suite, then it runs with `pytest` with no network, no real clock sleeps, and no external services.

## Assumptions / out of scope
Assumptions
- A1: Delivery is a Python package (e.g. `src/` layout) with pytest tests. No HTTP endpoints. A caller (future web layer) supplies the email address, client identifier, and new password.
- A2: A user has exactly one registered email, and email is unique.
- A3: Email delivery is an interface (`EmailSender` protocol) with a fake used in tests. No SMTP.
- A4: Storage is in-memory behind repository interfaces. No real database.
- A5: Reset link or URL formatting is the caller's concern. The service passes the raw token to the sender, and the message template carries a placeholder base URL setting.
- A6: Defaults in FR-4, FR-7, and FR-9 are proposals and are configurable.
- A7: Accounts have no 2FA or email-verified state to consider.

Out of scope
- Web or API layer, UI, CAPTCHA, localisation of messages.
- Real SMTP or provider integration, real database or migrations.
- User registration, login, session management (beyond the revocation hook), account lockout, MFA.
- Breached-password online checks (e.g. HIBP) and distributed or persistent rate limiting (in-memory only).
- Email change flow and "forgot email" recovery.

## Open questions for the human
1. Minimum Python version to target (3.10, 3.11, 3.12)?
2. Confirm the token TTL default (30 min proposed) and whether expiry is inclusive or exclusive at the exact boundary.
3. Confirm the password policy (min 12, max 128, denylist, no composition rules, per NIST guidance), or supply your organisation's policy.
4. Confirm rate-limit numbers and windows (5/hour per email, 20/hour per client, invalid confirm attempts limit).
5. Should a "password changed" notification (FR-12) and session revocation hook (FR-11) be in scope, or deferred?
6. Is an in-memory-only persistence acceptable, or should a simple SQLite (stdlib) repository also be delivered?
7. Should the reset request always return the same generic success value, or should it raise on rate limiting for the caller to translate (note: raising would leak limit state per email, so uniform output is proposed)?
8. Is a `src/` layout with `pyproject.toml` acceptable, and any preferred package name?
9. Should reuse of the current password as the new password be rejected?
10. Is a coverage threshold a hard gate for verification (NFR-5)?
