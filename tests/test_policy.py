import pytest

from pwreset import policy as policy_mod
from pwreset.config import PasswordPolicy
from pwreset.errors import PolicyViolation as V
from pwreset.policy import normalize_password, validate_password

P = PasswordPolicy()
EMAIL = "user@example.com"


def v(pw, email=EMAIL):
    return validate_password(P, pw, email)


def test_length_bounds():
    assert v("a" * 11).violations == (V.TOO_SHORT,)
    assert v("a1" * 6).violations == ()
    assert v("ab" * 64).violations == ()
    assert v("ab" * 64 + "c").violations == (V.TOO_LONG,)


def test_length_on_normalised():
    # 129 full-width chars normalise to 129 ASCII chars -> TOO_LONG;
    # 'ffi' ligature (1 char) normalises to 3, so 43 of them = 129.
    assert V.TOO_LONG in v("ﬃ" * 43).violations
    assert v("ﬃ" * 42).violations == ()  # 126 chars


def test_raw_guard_skips_normalisation(monkeypatch):
    def boom(s):
        raise AssertionError("normalise called")

    monkeypatch.setattr(policy_mod, "normalize_password", boom)
    res = v("a" * (4 * 128 + 1))
    assert res.normalized is None
    assert res.violations == (V.TOO_LONG,)


def test_raw_guard_boundary_still_normalises():
    res = v("a" * (4 * 128))
    assert res.normalized is not None
    assert res.violations == (V.TOO_LONG,)


def test_common_case_insensitive():
    assert V.COMMON in v("PassWord1234").violations


def test_equals_email_case_and_fullwidth():
    assert V.EQUALS_EMAIL in v("USER@example.com").violations
    fullwidth = "".join(chr(ord(c) + 0xFEE0) if "!" <= c <= "~" else c for c in EMAIL)
    assert fullwidth != EMAIL
    assert V.EQUALS_EMAIL in v(fullwidth).violations


@pytest.mark.parametrize("bad", [None, 12345, b"password-bytes"])
def test_non_str(bad):
    res = v(bad)
    assert res.violations == (V.INVALID_TYPE,)
    assert res.normalized is None


def test_repr_hides_normalised_password():
    pw = "Distinct-Repr-Secret-42"
    res = v(pw)
    assert res.normalized == pw
    assert pw not in repr(res)


@pytest.mark.parametrize("bad", ["valid-prefix-\ud800-suffix-1", "\udc80" * 12])
def test_unencodable_utf8_is_invalid_type(bad):
    res = v(bad)
    assert res.violations == (V.INVALID_TYPE,)
    assert res.normalized is None


def test_normalised_exactly_once(monkeypatch):
    calls = []
    real = policy_mod.normalize_password

    def spy(s):
        calls.append(s)
        return real(s)

    monkeypatch.setattr(policy_mod, "normalize_password", spy)
    # forbid_email path normalises the email too: password once + email once.
    v("a-fine-password-1")
    assert calls.count("a-fine-password-1") == 1
    assert len(calls) == 2


def test_fullwidth_normalised_in_result():
    fw = "".join(chr(ord(c) + 0xFEE0) for c in "abcdefghijkl1234")
    assert v(fw).normalized == "abcdefghijkl1234"
    assert normalize_password(fw) == "abcdefghijkl1234"


def test_multiple_violations_and_clean():
    res = v("short")
    assert res.violations == (V.TOO_SHORT,)
    pol = PasswordPolicy(min_length=20, denylist=frozenset({"password1234"}))
    res = validate_password(pol, "password1234", EMAIL)
    assert res.violations == (V.TOO_SHORT, V.COMMON)
    assert v("correct horse battery").violations == ()
