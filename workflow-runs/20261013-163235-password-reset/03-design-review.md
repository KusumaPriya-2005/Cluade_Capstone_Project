# 3. Design review (run 20261013-163235-password-reset) - round 2 (re-review of architecture revision 1)

Round 1 (verdict: approve with changes; blocking B1-B3, advisory A1-A11) led to architecture revision 1. This document is the current review. Round 1 findings are tracked in the status table below.

## Previous findings status

| ID | Was | Status | Evidence in revision 1 |
|---|---|---|---|
| B1 | Blocking | Resolved | `get_by_id` is now in the `UserRepository` list. Confirm checks `None` and raises `InvalidResetTokenError` with an invalid-attempt record (D13). Test "Extra B1". |
| B2 | Blocking | Resolved | `_email_parts`, `_client_key` and `_token_hash` guard non-str, empty and over-long input, with sentinel keys. Confirm covers a non-str token and a non-str password (`INVALID_TYPE` only after token validation). D15, and parametrized tests for `None`, `int` and `bytes`. See N3 for a residual wording gap. |
| B3 | Blocking | Resolved | The "Failure after consume" section states the behaviour: the exception propagates and the token stays burned. The hash is computed before consume. The `TokenRepository` contract and README require one transaction in a real implementation. D14, R10, test "Extra B3". |
| A1 | Advisory | Resolved | D9, R8 and the limiter semantics text. A test pins that a client-denied request still counts against the email limiter. |
| A2 | Advisory | Resolved | Documented as inherent to FR-5 (R9). Test "Extra A2". |
| A3 | Advisory | Resolved | Claim reworded. The dummy work is dropped (D4). The token generator is called once per issue. |
| A4 | Advisory | Resolved | In-memory `consume` deletes the record and clears `by_user` (D19). The AC-6 test checks it. |
| A5 | Advisory | Resolved | Keys are sha256 digests or fixed sentinels, with length caps (D16). R4 covers key count. |
| A6 | Advisory | Resolved | The opaque `user_id` is logged on revoker failure only (D18). The AC-15 test uses a sender that raises with the token in its message. |
| A7 | Advisory | Resolved | D17 documents NFKC. `max_length` is enforced before hashing, with a spy-hasher test. See N1 for a flow inconsistency. |
| A8 | Advisory | Resolved | `snapshot()` and `dump()` accessors. The AC-2 row is corrected. One shared FakeClock. |
| A9 | Advisory | Resolved | Microsecond cases are in the AC-5 and AC-11 rows. |
| A10 | Advisory | Resolved | `pytest-cov` removed. |
| A11 | Advisory | Resolved | Listed first under "Decisions needed from the human". |

## Coverage

All 13 FRs, 7 NFRs and 16 ACs are covered. I re-checked the new material for consistency.

- **Flow vs interface lists.** Every call in the confirm and request flows exists in the Protocols: `peek_valid`, `consume`, `get_by_id`, `issue`, `set_password_hash`, `hasher.verify` and `hasher.hash`. The only gap is that `normalize_password` is used by the service but missing from the `policy.py` layout comment (N4).
- **Order of operations in confirm.** The order is block check, peek, owner lookup, policy and reuse check, hash, consume, password write, revoke, notify. It satisfies AC-5, AC-6, AC-7, AC-8, AC-9 and AC-13, and it satisfies NFR-7 through the single `consume` call. Policy errors do not consume the token or count as invalid attempts. Hashing before consume keeps a hasher failure from burning the token.
- **Limiter semantics vs AC-11..13.** Denied hits are not recorded, so the window recovers on schedule (AC-11). The per-client limiter works across different emails (AC-12). A blocked client is rejected before the token is examined, so a valid token is also rejected (AC-13). The boundary convention is exclusive everywhere (D8).
- **Test table vs design.** Every AC has a row, and the Extra B1, B3 and A2 rows match the design. Small gaps are in N4.

| Requirement | Design element | Gap |
|---|---|---|
| FR-1, FR-2, AC-1..3 | Request flow, constant ack, sentinel keys | N2, N3 |
| FR-3, FR-4, FR-5, AC-4..8 | sha256 hash, exclusive TTL, `issue`, `peek_valid`, `consume` | None |
| FR-6..8, AC-9, AC-10 | Confirm flow, policy, scrypt, NFKC | N1, N4 |
| FR-9, AC-11..13 | Three sliding-window limiters | N2 |
| FR-10 | `strip().lower()` | None |
| FR-11, FR-12, AC-14 | Revoker and notice after the password write | None |
| FR-13, NFR-4, NFR-7, AC-16 | Protocols, fakes, shared FakeClock, atomic `consume` | None |
| NFR-1, NFR-2, AC-15 | Hash lookup, fixed errors and log events, `repr=False` | N3 |
| NFR-3, NFR-5, NFR-6 | stdlib only, pytest only, README | None |

## Findings

No blocking findings remain.

| ID | Severity | Issue | Suggested fix |
|---|---|---|---|
| N1 | Advisory | In the confirm flow, `pw = normalize_password(new_password)` runs before `validate_password`. The "cheap guard" (raw `len > 4 * max_length` returns `TOO_LONG` before normalising) therefore never protects the service path, and the normalisation cost is unbounded for a huge password. The 4x guard is also approximate, because NFKC can shrink or expand length. The password is normalised twice (service and policy), and `EQUALS_EMAIL` compares against `user.email`, which is not NFKC-normalised. | Apply the length guard first in the service, or have `validate_password` return the normalised string. Normalise only once, and only if the guard passes. State that the guard is a cost bound and not a policy rule. |
| N2 | Advisory | The shared `client:invalid` bucket is described as "harmless to real users", which is not true if the web layer passes an empty or `None` `client_id` (a proxy misconfiguration). Every real user is then in one 20/hr bucket, so the whole service is throttled to 20 resets per hour, silently, because the ack is uniform. | Document in the README that the caller must supply a non-empty client identifier. Reword R11 and the `_client_key` text. Add a test pinning the shared-bucket behaviour. |
| N3 | Advisory | "Request never raises for any input" covers input types only. `users.get_by_email` and `tokens.issue` exceptions are not mentioned and would propagate, and only on the registered path. That gives a rare existence oracle (an error for a known email). The "reset send failed" log event also appears only for registered emails. This is an internal log, not caller-visible. | Say explicitly that the guarantee covers input, not infrastructure failure. State that repository errors propagate (fail loudly) or are caught and logged as a fixed event with an identical ack. Pick one and add a test. |
| N4 | Advisory | Minor test and layout inconsistencies. (a) The `SAME_AS_CURRENT` check lives in the service but the AC-9 row lists it under `test_policy`. (b) The NFKC reuse test needs a fixture user whose stored hash was made from the normalised password. Registration is outside this library, so state the assumption. (c) The `policy.py` layout comment omits `normalize_password`. (d) No test says that policy violations do not count toward the invalid-confirm limit. (e) No test covers over-long token or `client_id` handling. | Move (a) to `test_confirm`. Add the fixture note for (b). Fix the layout comment for (c). Add the two small tests for (d) and (e). |
| N5 | Advisory | Scope growth. The revision adds NFKC, `INVALID_TYPE`, sentinel buckets and length caps. All of it is defensible and small, but NFKC (D17) and the `user_id` logging (D18) go beyond the requirements. Both have declared fallbacks. | Keep. The plan should treat "Decisions needed from the human" items 3 to 5 as non-blocking, with the stated fallbacks if they are unanswered. Item 1 (the 10/hr invalid-confirm limit) needs an answer or an explicit default acceptance. |

Security and privacy: no new concerns. Uniform errors, hash lookup, the 256-bit token, a reuse check that runs only after token validation, fixed log events and opaque ids are all sound. Over-engineering: none significant.

## Verdict

**Approve.** All three blocking and all eleven advisory findings from round 1 are resolved. The revised design covers every FR, NFR and AC with a consistent flow, interface list and test table. N1 to N5 are advisory and can be folded into the implementation plan. N1 to N3 are the most worth acting on.
