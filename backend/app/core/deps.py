import uuid
from collections.abc import Iterator

import jwt
from fastapi import Depends, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.core.security import decode_access_token
from app.db.session import SessionLocal
from app.models.user import User

_bearer = HTTPBearer(auto_error=False)


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    unauthorized = ApiError(
        status.HTTP_401_UNAUTHORIZED,
        "invalid_token",
        "Not authenticated.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None:
        raise unauthorized

    try:
        subject = uuid.UUID(decode_access_token(credentials.credentials))
    except jwt.InvalidTokenError, ValueError:
        raise unauthorized from None

    user = db.get(User, subject)
    if user is None:
        raise unauthorized
    return user
