"""Security utilities: password hashing, JWT generation, and login rate limiting."""
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import bcrypt
import jwt

from app.core.config import settings


def get_password_hash(password: str) -> str:
    """Hash a plaintext password using bcrypt with auto-generated salt."""
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plaintext password against a stored bcrypt hash."""
    return bcrypt.checkpw(
        plain_password.encode("utf-8"),
        hashed_password.encode("utf-8"),
    )


def create_access_token(
    data: Dict[str, Any],
    expires_delta: Optional[timedelta] = None,
) -> str:
    """Create a signed JWT access token."""
    to_encode = data.copy()
    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode.update({"iat": now, "exp": expire})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_access_token(token: str) -> Dict[str, Any]:
    """Decode and validate a JWT access token."""
    return jwt.decode(
        token,
        settings.SECRET_KEY,
        algorithms=[settings.ALGORITHM],
        options={"require": ["exp", "sub"]},
    )


class LoginRateLimiter:
    """Sliding-window rate limiter with in-memory fallback.

    Tracks login attempts per key (e.g., client IP or email) to prevent brute-force attacks.
    """

    def __init__(self, max_attempts: int = 5, window_seconds: int = 60) -> None:
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self._in_memory_records: Dict[str, List[float]] = {}

    def is_allowed(self, key: str) -> bool:
        """Check if request under `key` is allowed and record the attempt timestamp."""
        now = time.time()
        cutoff = now - self.window_seconds

        attempts = self._in_memory_records.get(key, [])
        # Prune older entries outside the sliding window
        valid_attempts = [ts for ts in attempts if ts > cutoff]

        if len(valid_attempts) >= self.max_attempts:
            self._in_memory_records[key] = valid_attempts
            return False

        valid_attempts.append(now)
        self._in_memory_records[key] = valid_attempts
        return True

    def reset(self, key: Optional[str] = None) -> None:
        """Clear rate limit records for testing or manual unlocks."""
        if key:
            self._in_memory_records.pop(key, None)
        else:
            self._in_memory_records.clear()


login_rate_limiter = LoginRateLimiter(max_attempts=5, window_seconds=60)
