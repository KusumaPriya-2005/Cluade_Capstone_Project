import hashlib
import logging
from datetime import timedelta

import pytest

from conftest import USER_EMAIL, RaisingGetByEmailUsers, RaisingIssueTokens, extract_token
from pwreset.errors import InvalidResetTokenError
from pwreset.interfaces import User

CLIENT = "10.0.0.1"
PW = "Brand-New-Password-1"
US = timedelta(microseconds=1)


def client_key(c):
    return "client:" + hashlib.sha256(c.encode()).hexdigest()


def add_users(env, n):
    for i in range(n):
        env.users.add(User(f"u{i}", f"u{i}@example.com", "h"))


def test_ac1_registered_email_one_message(env):
    ack = env.service.request_password_reset(USER_EMAIL, CLIENT)
    assert len(env.sender.messages) == 1
    msg = env.sender.messages[0]
    assert msg.to == USER_EMAIL
    assert env.config.base_url in msg.body
    assert env.gen.count == 1
    assert extract_token(msg) == "tok-" + "0" * 39 + "1"
    assert ack.message


BAD_EMAILS = [
    "nobody@example.com", "no-at-sign", "a@@b.com", "a@b@c.com", "us er@example.com",
    "@example.com", "user@", "", "   ", None, 12345, b"user@example.com", "a" * 400 + "@x.com",
]


@pytest.mark.parametrize("bad", BAD_EMAILS)
def test_ac2_uniform(env, bad, make_env):
    registered_env = make_env()
    expected = registered_env.service.request_password_reset(USER_EMAIL, CLIENT)
    assert len(registered_env.sender.messages) == 1  # ack really came from a registered email
    ack = env.service.request_password_reset(bad, CLIENT)
    assert ack.message and ack == expected
    assert env.sender.messages == []
    assert env.tokens.snapshot() == [] and env.tokens.by_user == {}
    assert env.gen.count == 0


@pytest.mark.parametrize("bad", [None, 42, b"1.2.3.4", "", "x" * 300])
def test_non_str_client_id_never_raises(env, bad):
    ack = env.service.request_password_reset(USER_EMAIL, bad)
    assert ack.message
    assert len(env.sender.messages) == 1


@pytest.mark.parametrize("variant", ["USER@example.com", "  user@example.com  ", " User@Example.COM\t"])
def test_ac3_case_whitespace(env, variant):
    env.service.request_password_reset(variant, CLIENT)
    assert len(env.sender.messages) == 1
    assert env.sender.messages[0].to == USER_EMAIL


def test_ac11_sixth_request_silent_and_boundary(env):
    acks = [env.service.request_password_reset(USER_EMAIL, f"c{i}") for i in range(6)]
    assert len(env.sender.messages) == 5
    assert all(a == acks[0] for a in acks)
    env.clock.advance(timedelta(hours=1) - US)
    env.service.request_password_reset(USER_EMAIL, "cx")
    assert len(env.sender.messages) == 5
    env.clock.advance(US)
    env.service.request_password_reset(USER_EMAIL, "cy")
    assert len(env.sender.messages) == 6


def test_ac12_client_limit(env):
    add_users(env, 20)
    for i in range(20):
        env.service.request_password_reset(f"u{i}@example.com", CLIENT)
    assert len(env.sender.messages) == 20
    env.service.request_password_reset(USER_EMAIL, CLIENT)
    assert len(env.sender.messages) == 20


def test_a1_client_denied_request_counts_against_email_limiter(env):
    add_users(env, 20)
    for i in range(20):
        env.service.request_password_reset(f"u{i}@example.com", CLIENT)
    for _ in range(5):
        env.service.request_password_reset(USER_EMAIL, CLIENT)  # client-denied
    assert env.sender.messages and len(env.sender.messages) == 20
    # The email limiter counted those 5 denied attempts: a fresh client gets nothing.
    env.service.request_password_reset(USER_EMAIL, "other-client")
    assert len(env.sender.messages) == 20


def test_a1_email_denied_request_counts_against_client_limiter(env):
    for _ in range(5):
        env.service.request_password_reset(USER_EMAIL, CLIENT)
    assert len(env.sender.messages) == 5
    for _ in range(15):
        env.service.request_password_reset(USER_EMAIL, CLIENT)  # email-denied
    assert env.client_limiter.is_blocked(client_key(CLIENT))


@pytest.mark.parametrize("junk", ["", None, "x" * 257, 5, b"x"])
def test_n2_invalid_client_shared_bucket(env, junk):
    add_users(env, 21)
    for i in range(20):
        env.service.request_password_reset(f"u{i}@example.com", junk)
    assert len(env.sender.messages) == 20
    env.service.request_password_reset("u20@example.com", "")  # different junk, same bucket
    assert len(env.sender.messages) == 20


def test_n3_get_by_email_propagates(make_env):
    e = make_env(users_wrapper=RaisingGetByEmailUsers)
    with pytest.raises(RuntimeError):
        e.service.request_password_reset(USER_EMAIL, CLIENT)
    assert e.sender.messages == []


def test_n3_issue_propagates_nothing_sent(make_env):
    e = make_env(tokens_wrapper=RaisingIssueTokens)
    with pytest.raises(RuntimeError):
        e.service.request_password_reset(USER_EMAIL, CLIENT)
    assert e.sender.messages == []


def test_a2_send_failure_leaves_earlier_token_invalid(env):
    env.service.request_password_reset(USER_EMAIL, CLIENT)
    old = extract_token(env.sender.messages[0])
    env.sender.raise_exc = True
    ack = env.service.request_password_reset(USER_EMAIL, CLIENT)  # must not raise
    assert ack.message
    assert len(env.sender.messages) == 1
    with pytest.raises(InvalidResetTokenError):
        env.service.confirm_password_reset(old, PW, CLIENT)


def test_a2_second_request_supersedes_first(env):
    env.service.request_password_reset(USER_EMAIL, CLIENT)
    env.service.request_password_reset(USER_EMAIL, CLIENT)
    t1, t2 = (extract_token(m) for m in env.sender.messages)
    with pytest.raises(InvalidResetTokenError):
        env.service.confirm_password_reset(t1, PW, CLIENT)
    env.service.confirm_password_reset(t2, PW, CLIENT)


def test_send_failure_logs_class_only(env, caplog):
    env.sender.raise_exc = True
    env.sender.exc_text = "SECRET-IN-MESSAGE"
    with caplog.at_level(logging.DEBUG, logger="pwreset"):
        env.service.request_password_reset(USER_EMAIL, CLIENT)
    assert "RuntimeError" in caplog.text
    assert "SECRET-IN-MESSAGE" not in caplog.text
