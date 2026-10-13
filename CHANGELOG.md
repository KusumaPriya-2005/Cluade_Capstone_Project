# Changelog

All notable changes to this project are documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- `pwreset`, a standard-library-only Python library (3.11 or later) for password reset via a registered email address.
- Request reset and confirm reset operations, with injectable clock, token generator, email sender and repositories.
- Single-use, expiring reset tokens (30 minute default, exclusive expiry). Only a hash of the token is stored, and a newer token invalidates older ones.
- Password hashing with scrypt (per-password salt) and NFKC normalisation of passwords, plus a configurable password policy (12 to 128 characters, denylist, not equal to the email, no reuse of the current password).
- Uniform response for requests, so registered, unknown, malformed and rate-limited emails cannot be told apart.
- Sliding-window rate limiting: 5 requests per hour per email, 20 per hour per client, and 10 invalid confirm attempts per hour per client.
- Session-revocation hook, called once with the user id after a successful reset.
- "Your password was changed" notification sent after a successful reset.
- In-memory user and token repositories.
- pytest suite of 125 tests covering all acceptance criteria. It needs no network and no sleeps.
- README with usage and security notes.

### Notes
- Branch coverage was not measured (the 90% target is unverified).
- Tests ran only on Python 3.14.7. Compatibility with Python 3.11 was checked by inspection only.

### Changed
- `.gitignore` now ignores `__pycache__/`, `*.pyc` and `.pytest_cache/`.
