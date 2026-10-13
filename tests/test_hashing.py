import pytest

from pwreset.hashing import ScryptPasswordHasher


@pytest.fixture
def hasher():
    return ScryptPasswordHasher(n=2**4)


def test_verify_new_and_not_old(hasher):
    stored = hasher.hash("new-password-123")
    assert hasher.verify("new-password-123", stored)
    assert not hasher.verify("old-password-123", stored)


def test_plaintext_not_in_stored(hasher):
    assert "new-password-123" not in hasher.hash("new-password-123")


def test_salted(hasher):
    assert hasher.hash("same-password-1") != hasher.hash("same-password-1")


def test_format_encodes_params():
    h = ScryptPasswordHasher(n=2**4, r=8, p=1)
    parts = h.hash("x" * 12).split("$")
    assert parts[:4] == ["scrypt", "16", "8", "1"]
    assert len(parts) == 6


@pytest.mark.parametrize(
    "stored",
    ["", "garbage", "scrypt$16$8$1$", "scrypt$16$8$1$@@@$@@@", "scrypt$x$8$1$AAAA$AAAA", "md5$16$8$1$AAAA$AAAA"],
)
def test_malformed_returns_false(hasher, stored):
    assert hasher.verify("whatever-password", stored) is False


def test_truncated_returns_false(hasher):
    stored = hasher.hash("some-password-12")
    assert hasher.verify("some-password-12", stored[:-8]) is False


def test_default_parameters_once():
    h = ScryptPasswordHasher()
    stored = h.hash("default-params-pw")
    assert stored.startswith("scrypt$16384$8$1$")
    assert h.verify("default-params-pw", stored)
