import logging

import pytest

from conftest import NEW_PASSWORD, OLD_PASSWORD, USER_EMAIL, USER_ID, extract_token
from pwreset.errors import InvalidResetTokenError, PasswordPolicyError

CLIENT = "10.0.0.1"
SECRET_EXC = "boom-with-secret"
REJECTED_PW = "rejq7"  # too short, distinctive


def all_text(caplog):
    return "\n".join(r.getMessage() + " " + str(r.args) + " " + str(r.exc_info) for r in caplog.records)


def assert_clean(text, *forbidden):
    for f in forbidden:
        assert f not in text


def test_repr_and_logs_have_no_secrets(env, caplog):
    with caplog.at_level(logging.DEBUG):
        env.service.request_password_reset(USER_EMAIL, CLIENT)
        tok = extract_token(env.sender.messages[0])
        with pytest.raises(PasswordPolicyError) as pe:
            env.service.confirm_password_reset(tok, REJECTED_PW, CLIENT)
        with pytest.raises(InvalidResetTokenError) as ie:
            env.service.confirm_password_reset("nope", NEW_PASSWORD, CLIENT)
        env.service.confirm_password_reset(tok, NEW_PASSWORD, CLIENT)
    reprs = [
        repr(env.service), repr(env.users), repr(env.tokens), env.tokens.dump(),
        repr(env.users.snapshot()), repr(env.sender.messages),
        repr(env.tokens.snapshot()), str(pe.value), str(ie.value),
        repr(env.hasher), all_text(caplog),
    ]
    blob = "\n".join(reprs)
    assert REJECTED_PW not in str(pe.value) and REJECTED_PW not in all_text(caplog)
    assert_clean(blob, tok, NEW_PASSWORD, OLD_PASSWORD, REJECTED_PW)
    assert tok not in repr(env.sender.messages)


def test_send_failure_log_class_name_only(env, caplog):
    env.sender.raise_exc = True
    env.sender.exc_text = SECRET_EXC
    with caplog.at_level(logging.DEBUG):
        env.service.request_password_reset(USER_EMAIL, CLIENT)
    text = all_text(caplog)
    assert "RuntimeError" in text
    assert_clean(text, SECRET_EXC, USER_EMAIL, USER_ID, "tok-")


def test_revoker_failure_log_fixed_text_and_class_only(env, caplog):
    env.service.request_password_reset(USER_EMAIL, CLIENT)
    tok = extract_token(env.sender.messages[0])
    env.revoker.raise_exc = True
    env.revoker.exc_text = SECRET_EXC
    with caplog.at_level(logging.DEBUG):
        env.service.confirm_password_reset(tok, NEW_PASSWORD, CLIENT)
    assert [r.getMessage() for r in caplog.records] == ["session revoke failed: RuntimeError"]
    assert_clean(all_text(caplog), SECRET_EXC, USER_ID, USER_EMAIL, tok, NEW_PASSWORD)


def test_no_identifier_in_any_log_scenario(env, caplog):
    with caplog.at_level(logging.DEBUG):
        env.sender.raise_exc = True
        env.sender.exc_text = SECRET_EXC
        env.service.request_password_reset(USER_EMAIL, CLIENT)  # send failure
        env.sender.raise_exc = False
        env.service.request_password_reset(USER_EMAIL, CLIENT)
        tok = extract_token(env.sender.messages[-1])
        env.revoker.raise_exc = True
        env.sender.raise_exc = True  # notice failure too
        env.service.confirm_password_reset(tok, NEW_PASSWORD, CLIENT)
        for _ in range(3):
            with pytest.raises(InvalidResetTokenError):
                env.service.confirm_password_reset("bad", NEW_PASSWORD, CLIENT)
    assert caplog.records
    assert_clean(all_text(caplog), USER_ID, USER_EMAIL, "user@", CLIENT, tok, NEW_PASSWORD, SECRET_EXC)
