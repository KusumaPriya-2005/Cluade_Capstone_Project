"""pwreset: password reset service layer (stdlib only)."""

from .config import PasswordPolicy, RateLimitConfig, ResetConfig
from .errors import (
    InvalidResetTokenError,
    PasswordPolicyError,
    PasswordResetError,
    PolicyViolation,
)
from .hashing import ScryptPasswordHasher
from .interfaces import (
    Clock,
    EmailMessage,
    EmailSender,
    PasswordHasher,
    SessionRevoker,
    TokenGenerator,
    TokenRecord,
    TokenRepository,
    User,
    UserRepository,
)
from .memory import InMemoryTokenRepository, InMemoryUserRepository
from .policy import PolicyResult, normalize_password, validate_password
from .rate_limit import SlidingWindowLimiter
from .service import PasswordResetService, ResetRequestAck
from .system import SecretsTokenGenerator, SystemClock

__all__ = [
    "Clock", "EmailMessage", "EmailSender", "InMemoryTokenRepository",
    "InMemoryUserRepository", "InvalidResetTokenError", "PasswordHasher",
    "PasswordPolicy", "PasswordPolicyError", "PasswordResetError",
    "PasswordResetService", "PolicyResult", "PolicyViolation", "RateLimitConfig",
    "ResetConfig", "ResetRequestAck", "ScryptPasswordHasher", "SecretsTokenGenerator",
    "SessionRevoker", "SlidingWindowLimiter", "SystemClock", "TokenGenerator",
    "TokenRecord", "TokenRepository", "User", "UserRepository",
    "normalize_password", "validate_password",
]
