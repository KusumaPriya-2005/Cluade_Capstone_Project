# 5. Implementation (run 20261013-163235-password-reset)

Plan Tasks 0-9 are implemented in order. All tests pass: `python -m pytest -q` gives **121 passed in 0.42s**. No git commands were run, and nothing under `workflow-runs/`, `.claude/` or `CLAUDE.md` was touched.

## Files changed
Paths are under the project root. All files are new.
- `pyproject.toml`: `requires-python >=3.11`, no runtime dependencies, dev extra `pytest`, pytest `pythonpath=["src"]`, `testpaths=["tests"]`, setuptools build-system declared but not installed.
- `README.md`: usage, security notes, N2 and N3 contracts, B3 transaction guidance, NFKC registration reminder, R8 and R9 trade-offs, limiter semantics, log policy.
- `src/pwreset/__init__.py`: public exports.
- `src/pwreset/errors.py`: `PasswordResetError`, `InvalidResetTokenError` (fixed message), `PolicyViolation`, `PasswordPolicyError` (message built from enum names only).
- `src/pwreset/config.py`: frozen `PasswordPolicy` (small casefolded denylist), `RateLimitConfig` (5, 20, 10, 1 hour), `ResetConfig` (30 minutes, `https://example.invalid/reset`).
- `src/pwreset/interfaces.py`: the Protocols, `User` and `EmailMessage` with `repr=False` on hash and body, `TokenRecord`, and the transaction-contract docstring on `TokenRepository`.
- `src/pwreset/system.py`: `SystemClock` and `SecretsTokenGenerator`.
- `src/pwreset/hashing.py`: `ScryptPasswordHasher` with `maxmem` of 64 MiB, `hmac.compare_digest`, and malformed input returning False.
- `src/pwreset/policy.py`: `normalize_password` (NFKC), `PolicyResult`, and `validate_password` with the N1 order (type check, raw guard, normalise once, policy checks). The layout comment mentions `normalize_password` (N4c).
- `src/pwreset/rate_limit.py`: `SlidingWindowLimiter` with `_prune` (exclusive boundary, empty keys deleted), `is_blocked`, `record`, `hit`.
- `src/pwreset/memory.py`: in-memory user and token repositories. `issue` supersedes, `peek_valid` is read-only, `consume` is single-valued and clears `by_user`. Test-only `snapshot()` and `dump()`. The user repository also has a `remove()` helper (see deviations).
- `src/pwreset/service.py`: `PasswordResetService`, `ResetRequestAck`, the helpers `_email_parts`, `_client_key` and `_token_hash`, and the request and confirm paths in the plan's order. The N2 and N3 statements are in the docstrings. Logs contain only fixed text plus the exception class name.
- `tests/conftest.py`: `FakeClock`, `RecordingEmailSender`, `RecordingRevoker`, `SequenceTokenGenerator`, `SpyHasher`, the cheap hasher fixture, the `make_env` and `env` service factory (seeded user, three limiters, one shared clock), and the failing-users and failing-tokens wrappers.
- `tests/test_errors_config.py`, `test_hashing.py`, `test_policy.py`, `test_tokens_storage.py`, `test_request.py`, `test_confirm.py`, `test_hooks_notify.py`, `test_no_leaks.py`, `test_public_api.py`.
- `tests/test_rate_limit.py`: limiter unit tests plus the AC-13 confirm-limit tests.
- `tests/test_smoke.py` was created in Task 1 and removed in Task 9 because `test_public_api.py` makes it redundant.

## Tests run (all from the project root, `python` is 3.14.7)
- Task 0: `python --version` gave 3.14.7. The scrypt probe worked (n=2^14, `maxmem` 64 MiB). pytest was missing, so the single permitted `python -m pip install pytest` was run, which installed pytest 9.1.1 (plus its own dependencies iniconfig, pluggy and pygments). Nothing else was installed.
- Task 1: `python -m pytest -q` gave 1 passed.
- Task 2: `tests/test_errors_config.py` gave 6 passed.
- Tasks 3 and 4: `tests/test_hashing.py` and `tests/test_policy.py` together, then the full suite, gave 31 passed.
- Task 5: full suite gave 36 passed after one test fix, then 42 passed with Task 6.
- Task 7: full suite gave 78 passed.
- Task 8: full suite gave 120 passed.
- Task 9, final: `python -m pytest -q` gave **121 passed in 0.42s**.
- Grep for `time.sleep|import socket|\bsocket\b|requests` in `src` and `tests`: the only hit is the English word "requests" in a docstring at `src/pwreset/service.py` line 120. There is no `time.sleep`, no socket and no `requests` module use.
- `test_public_api.py` runs a subprocess that checks `import pwreset` pulls in no non-stdlib module. It passes.
- Secret scan of `src`, `tests`, `README.md` and `pyproject.toml` (patterns: hard-coded secret assignments, private key headers, AKIA keys, URLs with credentials): no matches. The only password-like strings are obviously fake fixture values.
- Coverage: the `coverage` module is not installed, and it was not installed. Branch coverage is **not measured**.

## Deviations from the plan
1. **Truncated-hash bug found by the Task 3 test and fixed.** The first `verify` derived `dklen` from the stored key length. A truncated stored key is a prefix of the full scrypt output, so it verified as True. `verify` now fixes `dklen` at 32 and returns False when the stored key is not 32 bytes. This is a defect fix inside the planned hasher, not a design change.
2. **Request-path limiter tests are in `tests/test_request.py`.** The plan said "request-path part of `tests/test_rate_limit.py`". AC-11 (including the microsecond boundary), AC-12 and the A1 tests are in `test_request.py` because they share its helpers. `test_rate_limit.py` holds the limiter unit tests and the AC-13 confirm-limit tests.
3. **`InMemoryUserRepository.remove(user_id)` added.** It is a small helper used to simulate the B1 deleted-owner case in tests.
4. **Limiter wiring in the service constructor.** `PasswordResetService` takes three optional keyword-only limiters, `email_limiter`, `client_limiter` and `invalid_confirm_limiter`. If they are omitted, it builds them from the clock and `config.rate_limits`. The architecture's positional signature is unchanged, and the test factory injects the limiters so tests can inspect them.
5. **Request email format.** The body is `base_url + "?token=" + token`. The plan only required that the body contain the base URL and the token.
6. **Policy test for "normalisation exactly once".** `validate_password` also normalises the email, as the plan specifies (`normalize_password(email).casefold()`). The test therefore asserts the password is normalised once and the module function is called twice in total.

## Open issues
- Branch coverage is not measured (the `coverage` module is not installed).
- Known, accepted and documented risks, unchanged from the plan: no timing equality claim, quota DoS (R8), supersession DoS (R9), unbounded limiter keys (R4), non-thread-safe in-memory stores (R5), and a token burned when `set_password_hash` fails in memory (R10/B3).
- The default `python` is 3.14.7. The code uses nothing newer than 3.11 syntax, but it could not be tested on 3.11 itself.
- Plan note P9 (workspace not a git repository) is out of date; the repository exists. No git commands were run, so the release stage owns branching.

---

# Rework round 1 (after code review A-1..A-3, chosen by the human at checkpoint 4)

**Files changed**
- `src/pwreset/policy.py` (A-1, A-2): `PolicyResult.normalized` is now `field(repr=False)`. `validate_password` tries `password.encode("utf-8")` after the type and raw-length guards. On `UnicodeEncodeError` (e.g. a lone surrogate) it returns `PolicyResult(None, (INVALID_TYPE,))` before normalisation, so the password never reaches the hasher.
- `tests/test_policy.py`: added `test_repr_hides_normalised_password`. Added `test_unencodable_utf8_is_invalid_type`, parametrised with two lone-surrogate inputs.
- `tests/test_confirm.py`: added `test_unencodable_password_rejected_token_kept_no_leak` and the `logging` import. The test checks:
  - confirm raises `PasswordPolicyError` with `(INVALID_TYPE,)`.
  - The error text and the logs do not contain the password.
  - The `SpyHasher` sees no `hash` or `verify` calls.
  - The same token still works afterwards.
- `tests/test_no_leaks.py` (A-3): a `REJECTED_PW` constant is now the password actually sent in the test. It is asserted absent from `str(pe.value)`, the logs and the combined blob. The old `"short"+"x"` check is gone.
- `tests/test_request.py` (A-3): `test_ac2_uniform` now asserts the registered-email env really sent one message. The unknown or malformed-email ack must be non-empty and equal that registered-email ack. The no-send, no-token-write and `gen.count == 0` assertions are unchanged.

**Tests**
- `python -m pytest -q` finished with **125 passed in 0.43s**.

**Deviations**
- None. In `test_request.py`, `expected` already came from a separate registered-email env, so only the assertion that this env really sent a message was added and the ack check made stricter.

**Open issues**
- README needed no change. It does not mention password encodability and does not contradict A-2.
- A-4, A-5 and A-6 are untouched, as instructed.
