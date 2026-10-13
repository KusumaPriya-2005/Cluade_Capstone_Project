# 7. Verification (run 20261013-163235-password-reset), re-verification after rework round 1

This document supersedes the first verification (verdict: READY with caveats; AC-15 partly met because of advisory A-1).

## Commands run and results
All commands ran from the project root. The interpreter is `python` 3.14.7.
- `python -m pytest -q`: **125 passed in 0.35s**. This confirms the implementer's claim of 125.
- `python -m pytest -q -p no:cacheprovider`: 125 passed in 0.35s.
- Each file alone, run as `python -m pytest -q -p no:cacheprovider tests/<file>`:

| File | Passed |
|---|---|
| test_confirm | 32 |
| test_errors_config | 6 |
| test_hashing | 12 |
| test_hooks_notify | 4 |
| test_no_leaks | 4 |
| test_policy | 15 |
| test_public_api | 2 |
| test_rate_limit | 8 |
| test_request | 36 |
| test_tokens_storage | 6 |

  - The counts sum to 125, and there were no failures.
  - Compared with the previous run: test_confirm went from 31 to 32 and test_policy from 12 to 15, which accounts for the 4 new tests.
- Linters and build: the project configures none. They were not run, because nothing exists to run. No build was attempted, since it would write files.
- Coverage: **not measured**. `python -m coverage` gives "No module named coverage", and nothing may be installed. NFR-5's 90% branch target is unverified. It is a target, not a gate.
- Python 3.11: **tests ran only on 3.14.7.**
  - `src` and `tests` were grepped for `match` statements, `except*`, `tomllib`, PEP 695 `type X =` and `[T]` generics, `StrEnum`, `batched` and `override`. There were no 3.12+ constructs. The only hits for "override" are the test argument name `hasher_override`.
  - `policy.py` uses `str | None` with `from __future__ import annotations`, which is fine on 3.11. `requires-python` is `>=3.11`.
  - 3.11 compatibility is by inspection only.

## Own spot checks (read-only `python -B -c`)
- **A-1 is fixed.** `repr(validate_password(PasswordPolicy(), '<a valid password>', ...))` prints `PolicyResult(violations=())`. The normalised password is absent.
- **A-2 is fixed.** The real scrypt hasher was wrapped in `SpyHasher`.
  - A confirm with a valid token and a lone-surrogate password raised `PasswordPolicyError` with violations `(INVALID_TYPE,)`.
  - The error text is "Password does not meet policy: INVALID_TYPE", with no password in it.
  - The hasher's `hash` and `verify` call lists were both empty.
  - The captured DEBUG logs contained no password.
  - The same token then succeeded at T+30min minus 1 microsecond, so it was not burned.
- A-3: the strengthened assertions are in place. The rework's `test_unencodable_password_rejected_token_kept_no_leak` passes (`tests/test_confirm.py` lines 114-128). `test_no_leaks` and `test_ac2_uniform` pass. They were not mutation-tested.
- Scrypt: the hash has 5 `$` separators and the correct password verifies. A stored key truncated to 16 bytes returns False.
- Exclusive expiry: at T+N the confirm raises `InvalidResetTokenError`. At T+N minus 1 microsecond it succeeds.
- Request acks: a mixed-case, whitespace-padded registered email and an unknown email on a fresh env return equal acks. One message was sent, addressed to the registered address.
- After a successful confirm, the revoker was called once with the user id, and a notice was sent (2 messages in total).
- `repr` output: `PasswordResetService()`, `User(id=..., email=...)`, `EmailMessage(to=..., subject='Your password was changed')`. None of them contain the token, the old password, the new password or the hash.

## Acceptance criteria
| AC | Status | Evidence |
|---|---|---|
| AC-1 | Met | `test_ac1_registered_email_one_message`. Spot check: one message sent to the registered address. |
| AC-2 | Met | `test_ac2_uniform`. It now asserts that the registered env really sent a message and that the unknown-email ack is non-empty and equal to it (A-3 fixed). It also asserts no send, no token write and no generator call. Spot check: acks are equal. |
| AC-3 | Met | `test_ac3_case_whitespace`. Spot check with mixed case and whitespace. |
| AC-4 | Met | `test_tokens_storage` (`dump()` and the `TokenRecord` shape). The token is absent from the repr output. |
| AC-5 | Met | `test_ac5_*`. Spot check confirms the exclusive boundary. |
| AC-6 | Met | `test_ac6_second_use_fails`. |
| AC-7 | Met | `test_ac7_older_token_fails_newer_works`. |
| AC-8 | Met | `test_ac8_identical_errors` (identical type and message across variants). |
| AC-9 | Met | `test_ac9_policy_errors_do_not_burn_token`, plus the new unencodable-password test, which keeps the token usable. |
| AC-10 | Met | `test_ac10_new_hash_verifies`, the salt test in `test_hashing`, and the scrypt spot check. |
| AC-11 | Met | `test_ac11_sixth_request_silent_and_boundary`. |
| AC-12 | Met | `test_ac12_client_limit`. |
| AC-13 | Met | `test_ac13_limit_then_valid_token_rejected_then_ok_after_window`. |
| AC-14 | Met | `test_hooks_notify`. Spot check: revoker called once with the user id, and a notice sent. |
| AC-15 | **Met** (was partly met) | `test_no_leaks` (4 tests) now uses the real rejected password and asserts it is absent from the exception text and the logs. The new policy tests include `test_repr_hides_normalised_password`. Spot checks found no password or token in the logs, exception text, or the `repr` of the service, User, EmailMessage or PolicyResult. |
| AC-16 | Met | The suite runs offline. A grep found no sleeps or sockets. `test_public_api` checks that only the stdlib is imported. |

## Documentation quality
- The README still matches the code on limits, exclusive boundaries, the log policy, the N2 and N3 contracts, the B3 ordering, the NFKC reminder, the R8 and R9 trade-offs, and the hash format. The usage example was verified last round, and the public API (`__all__`) is unchanged.
- A-8: the README is silent about passwords that cannot be encoded as UTF-8 (for example lone surrogates) being reported as `INVALID_TYPE`. The README does not contradict this, so it is a minor, optional documentation gap. A one-line note would close it.
- Install note: the README says "pip install pytest", which is correct. It does not mention `pip install -e .[dev]`, which is minor.
- Stale item: plan note P9 in `05-implementation.md` ("workspace not a git repository") is out of date. It is an artifact, not project docs.

## Secrets
`src`, `tests`, `README.md` and `pyproject.toml` were grepped for secret-like assignments, private-key headers, AKIA keys and credentialed URLs. There were no matches. The only password-like strings are fake fixtures. `.env*` files were not read.

## Repository hygiene
- The `.gitignore` is unchanged. It covers the local Claude settings file, `workflow-runs/.active`, `.env*`, `*.pem`, `*.key` and `*.pfx`. It still **lacks `__pycache__/` and `*.pyc`**, so the release stage must add them or stage by explicit paths.
- `git status --short --ignored -uall` shows these untracked paths. Everything is untracked, and nothing is modified.
  - `README.md`, `pyproject.toml`
  - `src/pwreset/*.py`: 10 files
  - `tests/*.py`: conftest plus 10 test files
  - `workflow-runs/20261013-163235-password-reset/01..07 .md` and `state.json`
  - `src/pwreset/__pycache__/*.pyc` and `tests/__pycache__/*.pyc`. These must not be committed. Among them is a stale `test_smoke...pyc`.
- Ignored (`!!`): `.pytest_cache/` (it carries its own inner `.gitignore`) and `workflow-runs/.active`.
- What would be committed: `README.md`, `pyproject.toml`, `src/pwreset/*.py`, `tests/*.py`, the run artifacts, and the `.gitignore` update. `.pytest_cache/` and the `.pyc` files are excluded.

## Remaining issues
1. Advisory and optional: A-4 to A-9 (style and test-quality items from the re-review). A-8 is the README one-line note on non-UTF-8-encodable passwords.
2. Hygiene: `.gitignore` needs `__pycache__/` and `*.pyc`. The release stage will add them.
3. Unverified: branch coverage (not measured) and Python 3.11 execution (inspection only).
4. Known, accepted and documented risks: R4, R5, R8, R9 and R10/B3. There is no timing-equality claim.

## Verdict
**READY.** All 125 tests pass, and AC-1 to AC-16 are all met, including AC-15. A-1, A-2 and A-3 are fixed and confirmed by tests and by the verifier's own spot checks. No secrets were found. No blocking defects remain. Gate `pre-pr` can proceed. The PR should state that coverage was not measured and that tests ran only on Python 3.14.7.
