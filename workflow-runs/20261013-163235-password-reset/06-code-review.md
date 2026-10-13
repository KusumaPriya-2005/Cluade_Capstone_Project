# 6. Code review (run 20261013-163235-password-reset), re-review after rework round 1

The first review (verdict: pass; advisories A-1..A-6) was followed by rework round 1 (A-1, A-2, A-3). This document is the current review and supersedes the first one. Findings A-1..A-6 are tracked in the status table below.

## Scope reviewed
- Inputs: `04-plan.md`, `05-implementation.md` (original report plus the "Rework round 1" section) and the previous review (A-1..A-6).
- Reworked files, read in full:
  - `src/pwreset/policy.py`
  - `tests/test_policy.py`
  - `tests/test_confirm.py`
  - `tests/test_no_leaks.py`
  - `tests/test_request.py` (lines 1-120, which include `test_ac2_uniform`)
- Files skipped in the first review, now read in full:
  - `src/pwreset/config.py`, `system.py`, `__init__.py` and `pyproject.toml`
  - `tests/test_hashing.py`, `test_tokens_storage.py`, `test_errors_config.py` and `test_public_api.py`
- Also checked: the `SpyHasher` and `make_env` definitions in `tests/conftest.py`, and a README grep for text on encodability or `INVALID_TYPE`.
- The reviewer did not run the tests. The implementer's claim of **125 passed in 0.43s** is reported as claimed, not verified.
- No secrets found. The only password-like strings are obvious fixtures.
- Reviewed the files directly.

## Rework verification

**A-1 (repr of `PolicyResult`): resolved.**
- `policy.py:23` declares `normalized: str | None = field(repr=False)`.
- `test_repr_hides_normalised_password` (`test_policy.py:64-68`) uses a distinctive password. It first asserts `res.normalized == pw`, so the field is populated. It then asserts `pw not in repr(res)`. The test would fail without the fix.
- `field(repr=False)` on a field with no default, followed by a field without a default, is valid for a frozen dataclass. `violations` follows it with no default, so the ordering is legal.

**A-2 (lone surrogate): resolved.** Evidence is in `policy.py:32-42` and `test_confirm.py:114-128`.
- **Hasher never sees the password.**
  - `validate_password` runs `password.encode("utf-8")` after the type check and the raw-length guard, before NFKC. On `UnicodeEncodeError` it returns `PolicyResult(None, (INVALID_TYPE,))`.
  - In the service, a result with violations skips `verify` and `hash` (plan step 5). The new test confirms this through `SpyHasher`: `verify_calls == []` and `hash_calls == []`.
  - `hash_calls` is cleared after `issue`. `verify_calls` is not cleared, but it is empty at that point, and the same pattern is used in the existing `test_spy_hasher_not_reached_by_violations`.
  - The seeded user hash is created from the real `hasher`, not the spy, which `make_env` appears to do. The reviewer did not trace `make_env` further.
- **Token not burned.** The test calls `confirm(env, tok)` with a valid password afterwards and asserts that it succeeds and that the new hash verifies.
- **No leak.**
  - `PasswordPolicyError` is built from enum names only. The test asserts that the password and the marker string "unencodable-secret" are absent from `str(ei.value)` and from `caplog.text` at DEBUG level.
  - The exception is raised before any `UnicodeEncodeError` can be created, so its message (which would name a character) never exists.
- **Ordering is correct.**
  - The type check comes first, then the raw-length guard, then the encode check, then NFKC.
  - An over-long surrogate string returns `TOO_LONG` with no encode attempt. That is a cheap bound and acceptable.
  - NFKC of an encodable string stays encodable, so there is no post-normalisation hole.
  - `test_raw_guard_skips_normalisation` and `test_raw_guard_boundary_still_normalises` are unaffected.
- **Meaningful tests.** Before the fix, `hasher.hash` would have raised `UnicodeEncodeError`, not `PasswordPolicyError`. So `pytest.raises(PasswordPolicyError)` and the spy assertions could fail.
- **`test_unencodable_utf8_is_invalid_type`** covers two inputs: a mid-string `\ud800` and a run of `\udc80`. It asserts `violations == (INVALID_TYPE,)` and `normalized is None`.

**A-3 (weak assertions): resolved.**
- `test_no_leaks.py:10, 26-27, 38-39`: `REJECTED_PW = "rejq7"` is the password actually sent. It is a short, distinctive string that cannot occur in a token, a log text or an exception text unless it leaks. It is asserted absent from `str(pe.value)`, from the logs and from the blob. The assertion can fail.
- `test_request.py:43-51`: the registered-email env must have sent exactly one message. The ack must be non-empty and equal to the registered ack. The no-send, no-write and `gen.count == 0` assertions are kept. The ack comparison is still between constants, but the test no longer relies on it alone, which is acceptable.

**Regressions: none found.**
- `INVALID_TYPE` now means "not a str, or not encodable as UTF-8". Both lead to an identical, non-leaking `PasswordPolicyError`.
- The README (N3 and the uniform-ack text) does not contradict this, which agrees with the implementer's note.

## Findings (new in this round)
| ID | Severity | file:line | Issue | Suggested fix |
|---|---|---|---|---|
| A-7 | advisory | `src/pwreset/hashing.py` (`hash`) and `tests/test_hashing.py` | `ScryptPasswordHasher.hash` still raises `UnicodeEncodeError` for a lone-surrogate string when called directly. `verify` swallows it and returns False. Only the service guard (policy) protects the confirm path, and there is no hasher-level test or docstring note. Direct callers of the hasher can still hit the exception, and the exception text names a character of the password. | Optional: add a docstring note that callers must pass `validate_password`-checked text. Or add a one-line test that pins the behaviour. |
| A-8 | advisory | `README.md` (security notes) | The README does not say that a password that cannot be encoded as UTF-8 is reported as `INVALID_TYPE`. It is not wrong, only silent on this case. | Optional: add one sentence. |
| A-9 | advisory | `tests/test_public_api.py:25-26` | The subprocess gets only `PYTHONPATH` and `SYSTEMROOT` as its environment. This is fine on Windows and Linux CI, but it is slightly fragile on other platforms (for example a missing `PATH` or `LD_LIBRARY_PATH`). It is not a defect in the code. | Optional: copy `os.environ` and override `PYTHONPATH`. |

## Review of the previously skipped files
- **`config.py`:**
  - The dataclasses are frozen. The defaults match the plan: 12/128, 5/20/10 with a 1-hour window, a 30-minute TTL and the `example.invalid` URL.
  - The denylist entries are all casefolded. `policy.py:49` casefolds them again, which is the A-5 cost (unchanged).
  - A comment in `config.py` says entries must be casefolded, but the policy casefolds anyway. This is consistent.
- **`system.py`:** `SystemClock` returns an aware UTC time. `SecretsTokenGenerator` uses `secrets.token_urlsafe(32)`, which is 43 characters. Correct.
- **`__init__.py`:** the exports are complete and `__all__` is consistent. `test_public_api` checks that every name resolves.
- **`pyproject.toml`:** `requires-python >=3.11`, no runtime dependencies, dev extra `pytest` only, and `pythonpath` and `testpaths` are set. Matches the plan.
- **`test_hashing.py`:** meaningful tests. They cover verify of new versus old, no plaintext in the stored value, salting, the encoded parameters, malformed input, and truncation (`stored[:-8]`, which pins the earlier truncated-key bug fix). Exactly one test uses the default parameters, as planned.
- **`test_tokens_storage.py`:** it covers `dump()` with the hash and not the plaintext, the `TokenRecord` fields, supersession for the same user only, the exclusive expiry boundary with a read-only `peek_valid`, single-use `consume` with `by_user` cleared and re-issue, expired `consume`, and the user repository lookups. This matches the plan's AC-4, AC-5, AC-6 and AC-7 repository parts.
- **`test_errors_config.py`:** adequate. The `TokenRecord` "no plaintext field" check is done with `hasattr` and, in `test_tokens_storage`, with the field set.
- **`test_public_api.py`:** it checks the exports and, in a subprocess, that `import pwreset` pulls in no non-stdlib module. This gives real evidence for AC-16 and NFR-3. See A-9.

## Previous findings status
| ID | Previous severity | Status | Note |
|---|---|---|---|
| A-1 | advisory | Resolved | `repr=False` on `normalized`, plus a test that can fail |
| A-2 | advisory | Resolved | The encode check returns `INVALID_TYPE`. The hasher is not reached, the token is kept and nothing leaks. Tests are meaningful. |
| A-3 | advisory | Resolved | The exact rejected password is asserted absent. The AC-2 test checks that the registered env really sent a message. |
| A-4 | advisory | Unchanged, not required | `assert result.normalized is not None` at `service.py:186-187` |
| A-5 | advisory | Unchanged, not required | The denylist is rebuilt on every call (`policy.py:49`) |
| A-6 | advisory | Unchanged, by design | `PasswordPolicyError` versus `InvalidResetTokenError` reveals whether the token was valid. This follows AC-9 and is documented. |

## Acceptance criteria
AC-1 to AC-16 are still Met, as in the previous review. The reworked tests strengthen AC-2, AC-9 and AC-15. NFR-5 (branch coverage) is not measured, and NFR-3 was only run on Python 3.14.7. Both were already known and accepted.

## Verdict
**Pass.** There are no blocking findings. A-1, A-2 and A-3 are resolved and verified by reading the code and the tests. No regressions were found, and the new advisories A-7 to A-9 are optional. The 125 passed result is the implementer's claim and was not verified by the reviewer. The verifier stage should confirm it.

---
Orchestrator note (not part of the reviewer's output): the reviewer's earlier remark that the project is not a git repository was wrong and has been removed from the text above. The workspace is a Git repository (`main`, initial commit 449ef71); the application files are untracked.
