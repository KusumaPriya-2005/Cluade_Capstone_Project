import hashlib
import logging
from datetime import timedelta

import pytest

from conftest import (
    NEW_PASSWORD, OLD_PASSWORD, USER_EMAIL, USER_ID, FailingSetHashUsers, SpyHasher, extract_token,
)
from pwreset.config import ResetConfig
from pwreset.errors import InvalidResetTokenError, PasswordPolicyError, PolicyViolation as V
from pwreset.policy import normalize_password

CLIENT = "10.0.0.1"
TTL = timedelta(minutes=30)
US = timedelta(microseconds=1)


def issue(env, client=CLIENT):
    env.service.request_password_reset(USER_EMAIL, client)
    return extract_token(env.sender.messages[-1])


def confirm(env, token, pw=NEW_PASSWORD, client=CLIENT):
    return env.service.confirm_password_reset(token, pw, client)


def current_hash(env):
    return env.users.get_by_id(USER_ID).password_hash


# AC-5
@pytest.mark.parametrize("delta", [TTL - timedelta(seconds=1), TTL - US])
def test_ac5_before_expiry_succeeds(env, delta):
    tok = issue(env)
    env.clock.advance(delta)
    confirm(env, tok)
    assert env.hasher.verify(NEW_PASSWORD, current_hash(env))


@pytest.mark.parametrize("delta", [TTL, TTL + US, TTL + timedelta(days=1)])
def test_ac5_at_or_after_expiry_fails(env, delta):
    tok = issue(env)
    old = current_hash(env)
    env.clock.advance(delta)
    with pytest.raises(InvalidResetTokenError):
        confirm(env, tok)
    assert current_hash(env) == old


# AC-6
def test_ac6_second_use_fails(env):
    tok = issue(env)
    confirm(env, tok)
    h = current_hash(env)
    with pytest.raises(InvalidResetTokenError):
        confirm(env, tok, "Another-Password-789")
    assert current_hash(env) == h
    assert env.tokens.by_user == {}


# AC-7
def test_ac7_older_token_fails_newer_works(env):
    t1 = issue(env)
    t2 = issue(env)
    with pytest.raises(InvalidResetTokenError):
        confirm(env, t1)
    confirm(env, t2)


# AC-8
def test_ac8_identical_errors(env):
    used = issue(env)
    confirm(env, used)
    expired = issue(env)
    env.clock.advance(TTL)
    bad_tokens = [
        "unknown-token", "", "has space", None, 123, b"bytes", "x" * 257, used, expired,
        expired + "x", expired[:-1] + ("A" if expired[-1] != "A" else "B"),
    ]
    msgs = set()
    types = set()
    for i, bad in enumerate(bad_tokens):
        with pytest.raises(InvalidResetTokenError) as ei:
            confirm(env, bad, client=f"client-{i}")
        msgs.add(str(ei.value))
        types.add(type(ei.value))
    assert msgs == {"Invalid or expired reset token."}
    assert len(types) == 1


# AC-9
@pytest.mark.parametrize(
    "pw,violation",
    [
        ("short1", V.TOO_SHORT),
        ("ab" * 64 + "c", V.TOO_LONG),
        ("Password1234", V.COMMON),
        (USER_EMAIL, V.EQUALS_EMAIL),
        (OLD_PASSWORD, V.SAME_AS_CURRENT),
        (None, V.INVALID_TYPE),
        (12345, V.INVALID_TYPE),
        (b"bytes-password-1", V.INVALID_TYPE),
    ],
)
def test_ac9_policy_errors_do_not_burn_token(env, pw, violation):
    tok = issue(env)
    with pytest.raises(PasswordPolicyError) as ei:
        confirm(env, tok, pw)
    assert violation in ei.value.violations
    confirm(env, tok)  # same token still works


def test_unencodable_password_rejected_token_kept_no_leak(make_env, hasher, caplog):
    spy = SpyHasher(hasher)
    env = make_env(hasher_override=spy)
    tok = issue(env)
    spy.hash_calls.clear()
    bad = "unencodable-secret-\ud800-tail-1"
    with caplog.at_level(logging.DEBUG):
        with pytest.raises(PasswordPolicyError) as ei:
            confirm(env, tok, bad)
    assert ei.value.violations == (V.INVALID_TYPE,)
    assert bad not in str(ei.value) and "unencodable-secret" not in str(ei.value)
    assert "unencodable-secret" not in caplog.text
    assert spy.verify_calls == [] and spy.hash_calls == []
    confirm(env, tok)  # token not burned
    assert env.hasher.verify(NEW_PASSWORD, current_hash(env))


def test_n4a_same_as_current_nfkc_reuse(env):
    tok = issue(env)
    fullwidth = "".join(chr(ord(c) + 0xFEE0) if "!" <= c <= "~" else c for c in OLD_PASSWORD)
    assert fullwidth != OLD_PASSWORD and normalize_password(fullwidth) == OLD_PASSWORD
    with pytest.raises(PasswordPolicyError) as ei:
        confirm(env, tok, fullwidth)
    assert ei.value.violations == (V.SAME_AS_CURRENT,)


def test_spy_hasher_not_reached_by_violations(make_env, hasher):
    spy = SpyHasher(hasher)
    env = make_env(hasher_override=spy)
    spy.hash_calls.clear()
    tok = issue(env)
    for pw in ["x" * 5000, "short", "Password1234", USER_EMAIL, None]:
        with pytest.raises(PasswordPolicyError):
            confirm(env, tok, pw)
    assert spy.verify_calls == [] and spy.hash_calls == []


def test_spy_hasher_normalised_password_used(make_env, hasher):
    spy = SpyHasher(hasher)
    env = make_env(hasher_override=spy)
    tok = issue(env)
    fw = "".join(chr(ord(c) + 0xFEE0) for c in "Fresh-Pass-1234".replace("-", "")) + "!"
    confirm(env, tok, fw)
    assert spy.verify_calls == [normalize_password(fw)]
    assert spy.hash_calls[-1] == normalize_password(fw)


# AC-10
def test_ac10_new_hash_verifies(env):
    tok = issue(env)
    confirm(env, tok)
    h = current_hash(env)
    assert env.hasher.verify(NEW_PASSWORD, h)
    assert not env.hasher.verify(OLD_PASSWORD, h)
    assert NEW_PASSWORD not in h


# B1
def test_b1_owner_deleted(env):
    tok = issue(env)
    env.users.remove(USER_ID)
    with pytest.raises(InvalidResetTokenError):
        confirm(env, tok)
    assert len(env.invalid_limiter._hits) == 1


# B3
def test_b3_set_password_hash_fails(make_env):
    env = make_env(users_wrapper=FailingSetHashUsers)
    tok = issue(env)
    old = current_hash(env)
    with pytest.raises(RuntimeError):
        confirm(env, tok)
    assert current_hash(env) == old
    assert env.revoker.calls == []
    assert len(env.sender.messages) == 1  # only the reset email, no notice
    assert env.invalid_limiter._hits == {}
    with pytest.raises(InvalidResetTokenError):  # token burned
        confirm(env, tok)


def test_hasher_failure_does_not_burn_token(make_env, hasher):
    class FlakyHasher(SpyHasher):
        fail = False

        def hash(self, password):
            if self.fail:
                raise RuntimeError("hasher down")
            return super().hash(password)

    h = FlakyHasher(hasher)
    env = make_env(hasher_override=h)
    tok = issue(env)
    h.fail = True
    with pytest.raises(RuntimeError):
        confirm(env, tok)
    h.fail = False
    confirm(env, tok)


# N4d
def test_n4d_policy_violations_not_counted(env):
    tok = issue(env)
    for _ in range(env.config.rate_limits.invalid_confirm_per_client + 3):
        with pytest.raises(PasswordPolicyError):
            confirm(env, tok, "short")
    confirm(env, tok)


# N4e
def test_n4e_overlong_token_counts_as_invalid(env):
    with pytest.raises(InvalidResetTokenError):
        confirm(env, "t" * 257)
    key = "client:" + hashlib.sha256(CLIENT.encode()).hexdigest()
    assert len(env.invalid_limiter._hits[key]) == 1


@pytest.mark.parametrize("junk", [None, 7, b"c", "", "c" * 300])
def test_n4e_junk_client_id_still_works(env, junk):
    tok = issue(env)
    confirm(env, tok, client=junk)
    assert env.hasher.verify(NEW_PASSWORD, current_hash(env))


def test_custom_config_ttl(make_env):
    env = make_env(config=ResetConfig(token_ttl=timedelta(minutes=5)))
    tok = issue(env)
    env.clock.advance(timedelta(minutes=5))
    with pytest.raises(InvalidResetTokenError):
        confirm(env, tok)
