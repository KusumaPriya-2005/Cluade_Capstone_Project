from datetime import timedelta

from pwreset.rate_limit import SlidingWindowLimiter

WINDOW = timedelta(hours=1)
US = timedelta(microseconds=1)


def make(clock, limit=3):
    return SlidingWindowLimiter(clock, limit, WINDOW)


def test_allowed_up_to_limit_then_denied(clock):
    lim = make(clock)
    assert [lim.hit("k") for _ in range(4)] == [True, True, True, False]


def test_window_boundary(clock):
    lim = make(clock)
    for _ in range(3):
        assert lim.hit("k")
    clock.advance(WINDOW - US)
    assert lim.is_blocked("k")
    assert lim.hit("k") is False
    clock.advance(US)
    assert not lim.is_blocked("k")
    assert lim.hit("k") is True


def test_denied_hits_not_recorded(clock):
    lim = make(clock, limit=1)
    assert lim.hit("k")
    clock.advance(timedelta(minutes=30))
    assert lim.hit("k") is False  # denied, must not extend lockout
    clock.advance(timedelta(minutes=30))
    assert lim.hit("k") is True


def test_is_blocked_does_not_record(clock):
    lim = make(clock, limit=1)
    for _ in range(5):
        assert not lim.is_blocked("k")
    assert lim.hit("k")


def test_keys_isolated_and_empty_deleted(clock):
    lim = make(clock, limit=1)
    assert lim.hit("a")
    assert lim.hit("b")
    assert not lim.hit("a")
    clock.advance(WINDOW)
    assert not lim.is_blocked("a")
    assert "a" not in lim._hits
    assert "b" in lim._hits  # pruned only on access
    assert not lim.is_blocked("b")
    assert lim._hits == {}


# ---- confirm limit (AC-13) -------------------------------------------------
import pytest  # noqa: E402

from conftest import NEW_PASSWORD, USER_EMAIL, USER_ID, extract_token  # noqa: E402
from pwreset.errors import InvalidResetTokenError  # noqa: E402

CL = "10.0.0.9"


def _issue(env):
    env.service.request_password_reset(USER_EMAIL, "requester")
    return extract_token(env.sender.messages[-1])


def test_ac13_limit_then_valid_token_rejected_then_ok_after_window(make_env):
    from pwreset.config import ResetConfig  # TTL longer than the window

    env = make_env(config=ResetConfig(token_ttl=timedelta(hours=2)))
    tok = _issue(env)
    for _ in range(10):
        with pytest.raises(InvalidResetTokenError):
            env.service.confirm_password_reset("bogus", NEW_PASSWORD, CL)
    with pytest.raises(InvalidResetTokenError) as ei:
        env.service.confirm_password_reset(tok, NEW_PASSWORD, CL)
    assert str(ei.value) == "Invalid or expired reset token."
    env.clock.advance(WINDOW)
    env.service.confirm_password_reset(tok, NEW_PASSWORD, CL)


def test_ac13_other_client_unaffected(env):
    tok = _issue(env)
    for _ in range(10):
        with pytest.raises(InvalidResetTokenError):
            env.service.confirm_password_reset("bogus", NEW_PASSWORD, CL)
    env.service.confirm_password_reset(tok, NEW_PASSWORD, "someone-else")


def test_ac13_deleted_owner_and_non_str_token_count(env):
    tok = _issue(env)
    env.users.remove(USER_ID)
    for _ in range(5):
        with pytest.raises(InvalidResetTokenError):
            env.service.confirm_password_reset(tok, NEW_PASSWORD, CL)  # B1 path
    for bad in [None, 1, b"x", "", "t" * 300]:
        with pytest.raises(InvalidResetTokenError):
            env.service.confirm_password_reset(bad, NEW_PASSWORD, CL)
    assert env.invalid_limiter.is_blocked(
        "client:" + __import__("hashlib").sha256(CL.encode()).hexdigest()
    )
