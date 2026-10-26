import pytest

from conftest import NEW_PASSWORD, USER_EMAIL, USER_ID, extract_token

CLIENT = "10.0.0.1"


def start(env):
    env.service.request_password_reset(USER_EMAIL, CLIENT)
    return extract_token(env.sender.messages[-1])


def test_ac14_revoker_and_notice(env):
    tok = start(env)
    env.service.confirm_password_reset(tok, NEW_PASSWORD, CLIENT)
    assert env.revoker.calls == [USER_ID]
    assert len(env.sender.messages) == 2
    notice = env.sender.messages[1]
    assert notice.to == USER_EMAIL
    assert tok not in notice.body and NEW_PASSWORD not in notice.body


def test_revoker_failure_does_not_break_reset(env):
    tok = start(env)
    env.revoker.raise_exc = True
    env.service.confirm_password_reset(tok, NEW_PASSWORD, CLIENT)
    assert env.hasher.verify(NEW_PASSWORD, env.users.get_by_id(USER_ID).password_hash)
    assert len(env.sender.messages) == 2  # notice still sent


def test_notice_failure_does_not_break_reset(env):
    tok = start(env)
    env.sender.raise_exc = True
    env.service.confirm_password_reset(tok, NEW_PASSWORD, CLIENT)
    assert env.hasher.verify(NEW_PASSWORD, env.users.get_by_id(USER_ID).password_hash)
    assert env.revoker.calls == [USER_ID]


def test_hooks_not_called_on_failure(env):
    start(env)
    with pytest.raises(Exception):
        env.service.confirm_password_reset("bogus", NEW_PASSWORD, CLIENT)
    assert env.revoker.calls == []
    assert len(env.sender.messages) == 1
