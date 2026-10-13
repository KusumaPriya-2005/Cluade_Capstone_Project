from datetime import timedelta

from pwreset.config import PasswordPolicy, RateLimitConfig, ResetConfig
from pwreset.errors import InvalidResetTokenError, PasswordPolicyError, PolicyViolation
from pwreset.interfaces import EmailMessage, TokenRecord, User
from pwreset.system import SecretsTokenGenerator, SystemClock


def test_invalid_token_error_message_identical():
    assert str(InvalidResetTokenError()) == "Invalid or expired reset token."
    assert str(InvalidResetTokenError()) == str(InvalidResetTokenError())


def test_policy_error_message_enum_names_only():
    err = PasswordPolicyError((PolicyViolation.TOO_SHORT, PolicyViolation.COMMON))
    assert "TOO_SHORT" in str(err) and "COMMON" in str(err)
    assert err.violations == (PolicyViolation.TOO_SHORT, PolicyViolation.COMMON)


def test_config_defaults():
    cfg = ResetConfig()
    assert cfg.token_ttl == timedelta(minutes=30)
    assert cfg.base_url == "https://example.invalid/reset"
    assert cfg.policy == PasswordPolicy(12, 128, cfg.policy.denylist, True)
    assert all(d == d.casefold() for d in cfg.policy.denylist)
    rl = RateLimitConfig()
    assert (rl.per_email, rl.per_client, rl.invalid_confirm_per_client) == (5, 20, 10)
    assert rl.window == timedelta(hours=1)


def test_repr_hides_secrets():
    user = User("u1", "a@example.com", "HASHVALUE")
    msg = EmailMessage("a@example.com", "subj", "SECRETBODY")
    assert "HASHVALUE" not in repr(user)
    assert "SECRETBODY" not in repr(msg)
    rec = TokenRecord("hashhex", "u1", SystemClock().now())
    assert not hasattr(rec, "token")


def test_token_generator():
    gen = SecretsTokenGenerator()
    a, b = gen.new_token(), gen.new_token()
    assert len(a) == 43 and a != b


def test_system_clock_is_aware_utc():
    assert SystemClock().now().utcoffset() == timedelta(0)
