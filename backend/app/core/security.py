"""Password hashing and JWT issue/verify.

Imports no ORM and no session by design (`DECISIONS.md` 038), which is what
lets this module be unit-tested without a database or a fixture.
"""

import secrets
from datetime import UTC, datetime, timedelta

import bcrypt
import jwt

from app.core.config import settings

MAX_PASSWORD_BYTES = 72


def hash_password(password: str) -> str:
    encoded = password.encode("utf-8")
    if len(encoded) > MAX_PASSWORD_BYTES:
        raise ValueError(f"password must be at most {MAX_PASSWORD_BYTES} bytes once UTF-8 encoded")
    return bcrypt.hashpw(encoded, bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        # An over-long password and an unreadable stored hash both raise, and
        # both mean the same thing to the caller: these credentials do not match.
        return False


# Login compares against this when the email is unknown, so an unregistered
# address costs the same as a registered one (`DECISIONS.md` 037). Hashing a
# value nobody knows is what makes it impossible to authenticate against — a
# hard-coded hash of a known string would not be.
DUMMY_PASSWORD_HASH = hash_password(secrets.token_urlsafe(32))


def create_access_token(subject: str) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": subject,
        "iat": now,
        "exp": now + timedelta(days=settings.JWT_EXPIRE_DAYS),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> str:
    payload = jwt.decode(
        token,
        settings.JWT_SECRET,
        algorithms=[settings.JWT_ALGORITHM],
        options={"require": ["exp", "sub"]},
    )
    subject = payload["sub"]
    if not isinstance(subject, str):
        raise jwt.InvalidTokenError("token subject is not a string")
    return subject
