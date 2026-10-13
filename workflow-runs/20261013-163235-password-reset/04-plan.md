# 4. Implementation plan (run 20261013-163235-password-reset)

Inputs: `01-requirements.md`, `02-architecture.md` (revision 1, approved), `03-design-review.md` (round 2, approve) and the approved decisions in `state.json`, as given in the task brief. The planner did not read `state.json` itself.

## Approved decisions applied
- Python 3.11 or later: `requires-python = ">=3.11"`. NFKC is kept (D17).
- Invalid-confirm limit is 10/hr per client.
- The user_id logging (D18) was declined. No identifier of any kind may appear in any log event. Log records contain only fixed event text and the exception class name. This applies to every event: request send failure, revoker failure, notice failure and confirm paths.
- pytest is the only dev dependency. There is no pytest-cov. Ad hoc coverage runs only if `coverage` is already installed. Otherwise it is reported as "not measured".

## Architecture details changed by this plan (override 02-architecture.md where they differ)
1. **Revoker-failure log (D18 reversed).**
   - The event is the fixed text "session revoke failed" plus the exception class name only. It has no user_id.
   - Architecture items A6, D18, R3 and the AC-15 row are read accordingly.
2. **N1: single normalisation.**
   - `policy.py` exposes `normalize_password(s) -> str` (NFKC).
   - `validate_password(policy, password, normalized_email) -> PolicyResult`. `PolicyResult` is a frozen dataclass with `normalized: str | None` and `violations: tuple[PolicyViolation, ...]`.
   - Order inside `validate_password`:
     1. A non-str password returns `(None, (INVALID_TYPE,))`.
     2. Raw-length guard: if `len(raw) > 4 * max_length`, return `(None, (TOO_LONG,))` without normalising. This is a cost bound, not a policy rule.
     3. Normalise once.
     4. Check TOO_SHORT and TOO_LONG on the normalised length.
     5. Check COMMON by comparing the casefolded normalised password against the casefolded denylist.
     6. Check EQUALS_EMAIL by comparing `normalized.casefold()` with `normalize_password(email).casefold()`.
   - The service never normalises itself. It passes `result.normalized` to `hasher.verify` and `hasher.hash`.
   - Hashing runs only when `violations` is empty. SAME_AS_CURRENT is appended after the verify.
3. **N2: client_id contract.**
   - Callers must supply a non-empty, real client id.
   - An empty, `None`, non-str or over-long `client_id` maps to the shared `client:invalid` bucket. If a web layer passes junk for every user, all users share one 20/hr request bucket and are silently throttled.
   - The "harmless to real users" wording in `_client_key` and R11 is replaced by this statement. It goes in the README and in the `request_password_reset` docstring.
4. **N3: scope of never-raises.**
   - The guarantee covers input values and types, not infrastructure failure.
   - Exceptions from `users.get_by_email`, `tokens.issue`, the clock or the token generator propagate unchanged (fail loudly). Only `EmailSender.send` failures are swallowed.
5. **N4(a).** The SAME_AS_CURRENT test lives in `test_confirm.py`, because the check is in the service.

## Tasks
`PY` is the interpreter chosen in Task 0. All commands run from `C:\Users\KusumaPriyaBellamkon\Documents\AutomatedDocumentationSync`. Each task ends with all earlier tests still green.

**Task 0 - Environment check (no files).**
- Run `python --version`. If it is below 3.11, try `py -0p`, `py -3.11` and `py -3.12`, and use whichever is 3.11 or later.
- Run `PY -c "import hashlib,os; print(hashlib.scrypt(b'x', salt=os.urandom(16), n=2**14, r=8, p=1, maxmem=64*1024*1024, dklen=32).hex()[:4])"`.
- Run `PY -m pytest --version`. If pytest is missing, run `PY -m pip install pytest` once. This is the only permitted install.
- Verified by: the three commands succeed.
- If no interpreter is 3.11 or later, or scrypt is unavailable, stop and report in `05-implementation.md`. Do not fall back to pbkdf2, because that is a design change.

**Task 1 - Skeleton and pyproject.**
- Create `pyproject.toml`:
  - `requires-python = ">=3.11"` and no runtime dependencies.
  - `[project.optional-dependencies] dev = ["pytest"]`.
  - `[tool.pytest.ini_options] pythonpath = ["src"], testpaths = ["tests"]`.
  - A minimal `[build-system]` that is declared but not installed.
- Create `src/pwreset/__init__.py` (empty) and `tests/test_smoke.py` with one import test.
- Verified by: `PY -m pytest -q` shows 1 passed.
- AC: groundwork for AC-16.

**Task 2 - errors, config, interfaces, system.**
- Create `src/pwreset/errors.py`:
  - `PasswordResetError`.
  - `InvalidResetTokenError` with the fixed message "Invalid or expired reset token.".
  - `PolicyViolation` Enum (TOO_SHORT, TOO_LONG, COMMON, EQUALS_EMAIL, SAME_AS_CURRENT, INVALID_TYPE).
  - `PasswordPolicyError(violations)` with a message built from enum names only.
- Create `src/pwreset/config.py`: frozen `PasswordPolicy` (small casefolded denylist), `RateLimitConfig` (5, 20, 10, 1 hour) and `ResetConfig` (30 minutes, `base_url="https://example.invalid/reset"`).
- Create `src/pwreset/interfaces.py`:
  - The Protocols `Clock`, `TokenGenerator`, `EmailSender`, `SessionRevoker`, `PasswordHasher`, `UserRepository` (including `get_by_id`) and `TokenRepository` (`issue`, `peek_valid`, `consume`).
  - The dataclasses `User` (`password_hash` with `repr=False`), `TokenRecord` and `EmailMessage` (`body` with `repr=False`).
  - The `TokenRepository` docstring states the transaction contract: consume and the password write happen in one transaction.
- Create `src/pwreset/system.py` with `SystemClock` and `SecretsTokenGenerator` (`secrets.token_urlsafe(32)`).
- Create `tests/test_errors_config.py`:
  - All `InvalidResetTokenError` instances have an identical `str()`.
  - The `PasswordPolicyError` message contains only enum names.
  - Config defaults match the architecture.
  - `repr` of `User` and `EmailMessage` hides the hash and body.
  - A generated token has length 43 and two tokens differ.
- Verified by: `PY -m pytest tests/test_errors_config.py -q`.
- AC: AC-8 (message part), AC-15 (repr part), FR-3.

**Task 3 - Hashing.**
- Create `src/pwreset/hashing.py`: `ScryptPasswordHasher(n=2**14, r=8, p=1, salt_bytes=16)`.
  - Format `scrypt$n$r$p$<b64 salt>$<b64 dk>`, explicit `maxmem` of 64 MiB and `hmac.compare_digest`.
  - A malformed stored value returns False and never raises.
- Create `tests/test_hashing.py`:
  - New password verifies and old fails.
  - The stored value does not contain the plaintext.
  - Two hashes of the same password differ.
  - Parameters are encoded in the format.
  - Malformed, empty and truncated stored values return False.
  - Exactly one test uses the default parameters. The rest use `n=2**4`.
- Verified by: `PY -m pytest tests/test_hashing.py -q`.
- AC: AC-10, AC-15.

**Task 4 - Policy (N1).**
- Create `src/pwreset/policy.py` with `normalize_password`, `PolicyResult` and `validate_password` as specified above. The layout comment lists `normalize_password` (N4c).
- Create `tests/test_policy.py`:
  - Too short at 11 and ok at 12. Ok at 128 and TOO_LONG at 129 (normalised length).
  - The raw guard returns TOO_LONG with `normalized is None` for `len > 4*max`, and normalisation is not invoked (spy or monkeypatch).
  - Common password in a different case.
  - EQUALS_EMAIL for a different case, and EQUALS_EMAIL for a full-width form of the email.
  - Non-str passwords (`None`, `int`, `bytes`) give `INVALID_TYPE` only.
  - Normalisation runs exactly once per call.
  - A full-width string normalises to its ASCII form in `PolicyResult.normalized`.
  - Multiple violations are collected together. A clean password returns no violations.
- Verified by: `PY -m pytest tests/test_policy.py -q`.
- AC: AC-9 (policy part), D17, N1.

**Task 5 - Rate limiter and fakes.**
- Create `src/pwreset/rate_limit.py`: `SlidingWindowLimiter(clock, limit, window)` with `_prune` (exclusive boundary, empty keys deleted), `is_blocked`, `record` and `hit`.
- Create `tests/conftest.py` with:
  - `FakeClock` (settable, `advance()`).
  - `RecordingEmailSender` (optional raise with optional message text).
  - `RecordingRevoker` (optional raise).
  - `SequenceTokenGenerator`.
  - A cheap `ScryptPasswordHasher(n=2**4)` fixture.
  - A spy hasher that counts `hash` and `verify` calls.
- Create `tests/test_rate_limit.py` (limiter-unit part):
  - Allowed up to the limit, then denied.
  - Blocked at window minus 1 microsecond, accepted again at exactly the window.
  - Denied hits are not recorded.
  - `is_blocked` does not record.
  - Keys are isolated, and empty keys are deleted.
- Verified by: `PY -m pytest tests/test_rate_limit.py -q`.
- AC: AC-11 (mechanics), AC-16.

**Task 6 - In-memory repositories.**
- Create `src/pwreset/memory.py`:
  - `InMemoryUserRepository` with `add`, `get_by_email`, `get_by_id`, `set_password_hash` and test-only `snapshot()`.
  - `InMemoryTokenRepository` with `issue` (supersedes), `peek_valid` (exclusive expiry, read-only), single-valued `consume` (deletes the record and clears `by_user`) and test-only `snapshot()` and `dump()`.
- Create `tests/test_tokens_storage.py`:
  - `dump()` contains the sha256 hash and not the plaintext. `TokenRecord` has no plaintext field.
  - `issue` supersedes the earlier token for the same user and leaves other users untouched.
  - `peek_valid` at `expires_at - 1 microsecond` returns the record. At `expires_at` and later it returns None. `peek_valid` does not modify state.
  - The first `consume` returns the record and the second returns None. After consume `by_user` is cleared and a later `issue` works.
  - `consume` on an expired record returns None.
  - `get_by_id` and `get_by_email` work, and unknown ids return None.
- Verified by: `PY -m pytest tests/test_tokens_storage.py -q`.
- AC: AC-4, AC-6 and AC-7 (repository parts), AC-5 (boundary).

**Task 7 - Service: request path.**
- Create `src/pwreset/service.py` (part 1):
  - `ResetRequestAck`.
  - The `PasswordResetService` constructor and a `__repr__` that prints the class name only.
  - The helpers `_email_parts`, `_client_key` and `_token_hash`.
  - The `pwreset` logger.
  - `request_password_reset`. Its docstring states the N2 contract and the N3 scope. A send failure is logged as a fixed event plus the exception class name only. Repository exceptions are not caught.
- Add the service factory fixture to `tests/conftest.py`. It builds the service with repositories, three limiters and the fakes, all on one `FakeClock`, plus a seeded user.
- Create `tests/test_request.py` and the request-path part of `tests/test_rate_limit.py`:
  - **AC-1:** a registered email gives exactly one message to that address, containing base_url and the token.
  - **AC-2:** unknown, malformed (no `@`, two `@`, whitespace, empty local part) and non-str or over-long emails give no send, no repository write, no exception and an ack equal to the registered case. The token generator is not called. Non-str `client_id` (`None`, `int`, `bytes`) never raises.
  - **AC-3:** case and whitespace variants.
  - **AC-11 service level:** the 6th request is silent with an equal ack. Blocked at window minus 1 microsecond, accepted at the window.
  - **AC-12:** 20 different emails from one client, then the 21st sends nothing.
  - A client-denied request still counts against the email limiter, and the reverse (A1).
  - **N2 pin:** an empty, `None` or over-long `client_id` shares the `client:invalid` bucket across different users. The 21st request sends nothing.
  - **N3:** a raising `get_by_email` propagates. A raising `tokens.issue` propagates and nothing is sent.
  - **A2:** a send failure after issue leaves the earlier token invalid and the ack equal. A second request after a successful send supersedes the first token.
  - A send failure never propagates.
- Verified by: `PY -m pytest tests/test_request.py tests/test_rate_limit.py -q`.
- AC: AC-1, AC-2, AC-3, AC-11, AC-12 and the extras N2, N3, A2.

**Task 8 - Service: confirm path.**
- Extend `src/pwreset/service.py` (part 2): `confirm_password_reset(token, new_password, client_id)` in this order.
  1. Read `now` once.
  2. Compute the client key. If the client is blocked, raise `InvalidResetTokenError`.
  3. Compute `_token_hash`, then `peek_valid`. If missing, record an invalid attempt and raise.
  4. `get_by_id`. If None, record an invalid attempt and raise.
  5. Call `validate_password` once. If there are no violations and `hasher.verify` matches the current hash, append SAME_AS_CURRENT.
  6. On any violation raise `PasswordPolicyError`. The token is not consumed and the attempt is not counted.
  7. `hasher.hash` of `result.normalized`, then `consume`. If None, record an invalid attempt and raise.
  8. `set_password_hash`.
  9. Revoke. A failure is logged as the fixed text "session revoke failed" plus the exception class name only.
  10. Send the notice. A failure is logged as a fixed event plus the exception class name only.
- Add the failing-users wrapper to `tests/conftest.py`.
- Create `tests/test_confirm.py`, `tests/test_hooks_notify.py`, `tests/test_no_leaks.py` and the confirm-limit part of `tests/test_rate_limit.py`.
- `test_confirm`:
  - **AC-5:** success at T+N-1s and at T+N-1 microsecond. Failure at exactly T+N, T+N+1 microsecond and later.
  - **AC-6:** second use fails, the hash is unchanged and `by_user` is cleared.
  - **AC-7:** the older token fails after a newer one, and the newer works.
  - **AC-8:** unknown, malformed, non-str, over-long, tampered, expired and used tokens all raise `InvalidResetTokenError` with an identical `str()`.
  - **AC-9:** short, long, common, equals-email, SAME_AS_CURRENT and non-str passwords each raise `PasswordPolicyError`, then the same token still works.
  - SAME_AS_CURRENT and the NFKC reuse case live here (N4a). The fixture builds the stored hash from the NFKC-normalised password, with a comment that registration is outside this library (N4b).
  - A spy hasher confirms an over-long password and any password with another violation never reach `hash` or `verify`.
  - **AC-10:** the new hash verifies the new password and not the old one.
  - **B1:** owner deleted after issue gives `InvalidResetTokenError` and an invalid-attempt record.
  - **B3:** `set_password_hash` raises, so the exception propagates, the token is burned, the password is unchanged, the revoker and notice sender are not called and no invalid attempt is recorded.
  - A hasher failure does not burn the token.
  - **N4d:** more policy violations than the limit do not count toward the invalid-confirm limit, and a valid token still works afterwards.
  - **N4e:** an over-long token (more than 256 characters) raises `InvalidResetTokenError` and counts as an invalid attempt. An over-long or non-str `client_id` maps to `client:invalid` and confirm still works.
- `test_rate_limit` (confirm part), AC-13:
  - 10 invalid confirms, then a valid token is rejected with the same error. After the window it succeeds.
  - Deleted-owner and non-str token attempts count toward the limit.
- `test_hooks_notify`, AC-14:
  - The revoker is called once with the user id.
  - One notice is sent to the user's email.
  - A revoker failure or a notice failure does not break the reset, and the other hook still runs.
- `test_no_leaks`, AC-15:
  - caplog and `repr` of the service, repositories, `EmailMessage`, `User`, `TokenRecord` and the exception strings contain neither a token nor a password.
  - A sender that raises with the token in its message produces a log with only the exception class name.
  - The revoker-failure log contains the fixed text and the exception class name only. It has no user_id, email, token or password.
  - Across all logging scenarios, no record contains the user id or the email.
- Verified by: `PY -m pytest -q` (full suite).
- AC: AC-5 to AC-10, AC-13, AC-14, AC-15 and the extras B1, B3, N4.

**Task 9 - Exports, README, final checks.**
- Update `src/pwreset/__init__.py` to export the public API.
- Create `README.md`:
  - Usage example.
  - Security notes: the uniform ack and the honest timing claim (use an enqueuing sender); the NFKC decision; the log policy (fixed events plus exception class name, no identifiers); the TTL and boundary rules; the limiter semantics (attempts not sends, no short-circuit, sentinel buckets, unbounded key count).
  - The quota DoS (R8) and supersession DoS (R9) trade-offs.
  - The N2 client_id contract.
  - The N3 scope note.
  - The B3 transaction guidance.
  - The reminder that registration must hash the NFKC-normalised password.
  - Python 3.11 or later and the stdlib-only runtime.
- Add `tests/test_public_api.py`: root imports work, and `import pwreset` pulls in no third-party module. Remove `tests/test_smoke.py` if redundant.
- Verified by:
  - `PY -m pytest -q` is all green.
  - A grep shows no `time.sleep`, `socket` or `requests` in `src` or `tests`.
  - Ad hoc coverage only if `coverage` is already installed: `PY -m coverage run --branch -m pytest -q`, then `PY -m coverage report`. Do not install it. Otherwise report "not measured".
  - A secret scan of the new files.
- AC: AC-16, NFR-3, NFR-5 (target), NFR-6.

## Test strategy

All tests use pytest, one shared `FakeClock` and in-memory fakes. There is no sleep, no network and no filesystem access.

| AC | Tests (task) |
|---|---|
| AC-1 | `test_request` registered email gives one message with the token (7) |
| AC-2 | `test_request` parametrized unknown, malformed and non-str input, plus non-str client_id (7) |
| AC-3 | `test_request` case and whitespace variants (7) |
| AC-4 | `test_tokens_storage` `dump()` and record shape (6) |
| AC-5 | `test_confirm` microsecond boundaries (8), repository boundary (6) |
| AC-6 | `test_confirm` second use and `test_tokens_storage` consume (8, 6) |
| AC-7 | `test_confirm` older versus newer token (8) |
| AC-8 | `test_confirm` identical error type and message across all token failures, including over-long (8) |
| AC-9 | `test_policy` (4), `test_confirm` including SAME_AS_CURRENT and non-str password (8) |
| AC-10 | `test_hashing` (3), `test_confirm` (8) |
| AC-11 | `test_rate_limit` mechanics (5), service level with microsecond boundary (7) |
| AC-12 | `test_rate_limit` 20 emails from one client (7) |
| AC-13 | `test_rate_limit` confirm limit of 10, valid token rejected, accepted after the window (8) |
| AC-14 | `test_hooks_notify` (8) |
| AC-15 | `test_no_leaks` (8), `test_errors_config` repr checks (2) |
| AC-16 | Whole suite, plus the grep and `sys.modules` checks (9) |

Extra tests:

| Extra | Test (task) |
|---|---|
| B1 deleted owner | `test_confirm` (8) |
| B3 failure after consume | `test_confirm` (8) |
| A2 supersession and failed send | `test_request` (7) |
| N1 single normalisation, raw guard first, normalised EQUALS_EMAIL | `test_policy` (4), spy hasher in `test_confirm` (8) |
| N2 shared `client:invalid` bucket | `test_request` (7) |
| N3 repository errors propagate | `test_request` (7) |
| N4a SAME_AS_CURRENT in `test_confirm` | (8) |
| N4b NFKC reuse fixture note | (8) |
| N4c layout comment mentions `normalize_password` | (4) |
| N4d policy violations not counted toward the invalid-confirm limit | `test_confirm` (8) |
| N4e over-long token and client_id | `test_confirm` (8) |
| Declined user_id logging: no identifier in any log | `test_no_leaks` (8) |

## Dependencies and risks

Dependencies:
- A Python 3.11 or later interpreter (Task 0). The default `python` may be older, so the implementer checks `python --version`, uses `py -3.11` or whichever interpreter is 3.11 or later, and reports if none exists.
- pytest, installed once if missing. It is the only dev dependency. No pytest-cov and no runtime dependencies.
- OpenSSL-backed `hashlib.scrypt`, verified in Task 0 on this Windows machine (R2).

Risks:
- **P1.** The interpreter is below 3.11. Mitigated by Task 0 and a stop-and-report rule.
- **P2.** scrypt is missing or memory-limited. The explicit `maxmem` is set and verified in Tasks 0 and 3. Only one test uses default parameters. The fallback to pbkdf2 would need approval.
- **P3.** The NFKC raw guard of `4 * max_length` is a cost bound only. NFKC can change length, so the real rules apply to the normalised string. The README states this.
- **P4.** Logging leaks. Because the user_id logging was declined, `test_no_leaks` asserts no identifier appears in any log record in any scenario.
- **P5.** Accepted and documented risks: timing side channel (R1), quota DoS (R8), supersession DoS (R9), failure after consume in memory (R10), unbounded limiter keys (R4), non-thread-safe stores (R5).
- **P6.** N3: a repository failure in the request path propagates (fail loudly). This is tested and documented.
- **P7.** The NFKC reuse test depends on how the fixture builds the stored hash. The registration assumption is documented.
- **P8.** Coverage may be unmeasurable without installing a dependency. It is a target, not a gate.
- **P9.** The workspace is not a git repository. The implementer runs no git commands. Branching is handled by the release stage.

## Decisions needed from the human
None blocking. All decisions in `state.json` are approved.

Non-blocking note: if no interpreter of version 3.11 or later exists on this machine, the implementer will stop at Task 0 and report. The human can then install one or change the version decision.

---
Orchestrator note (not part of the planner's output): risk P9 is out of date. The workspace is now a Git repository (`main`, initial commit 449ef71, clean tree, no remote). The implementer still runs no git commands; the release stage creates the branch and commits.
