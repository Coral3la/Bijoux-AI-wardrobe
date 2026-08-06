"""Password hashing and JWT issue/verify. No database, no fixtures, no network —
`security.py` imports no ORM and no session, which is the property that keeps
these runnable before task 0.10 builds any scaffolding (`DECISIONS.md` 038)."""

import jwt
import pytest

from app.core.config import settings
from app.core.security import (
    DUMMY_PASSWORD_HASH,
    MAX_PASSWORD_BYTES,
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)

PASSWORD = "correct horse battery staple"

# 40 characters, 80 bytes in UTF-8 — the case DECISIONS.md 036 documents.
HEBREW_PASSWORD = "סיסמה" * 8


def test_verifies_the_password_it_hashed() -> None:
    assert verify_password(PASSWORD, hash_password(PASSWORD)) is True


def test_rejects_a_different_password() -> None:
    assert verify_password("something else", hash_password(PASSWORD)) is False


def test_hashes_the_same_password_differently_each_time() -> None:
    assert hash_password(PASSWORD) != hash_password(PASSWORD)


def test_accepts_a_password_of_exactly_the_byte_limit() -> None:
    password = "x" * MAX_PASSWORD_BYTES

    assert verify_password(password, hash_password(password)) is True


def test_rejects_a_password_one_byte_over_the_limit() -> None:
    with pytest.raises(ValueError) as excinfo:
        hash_password("x" * (MAX_PASSWORD_BYTES + 1))

    assert "bytes" in str(excinfo.value)


def test_rejects_a_password_that_is_short_in_characters_but_long_in_bytes() -> None:
    assert len(HEBREW_PASSWORD) < MAX_PASSWORD_BYTES
    assert len(HEBREW_PASSWORD.encode("utf-8")) > MAX_PASSWORD_BYTES

    with pytest.raises(ValueError):
        hash_password(HEBREW_PASSWORD)


@pytest.mark.parametrize(
    "password,stored_hash",
    [
        pytest.param(
            "x" * (MAX_PASSWORD_BYTES + 1), hash_password(PASSWORD), id="password_too_long"
        ),
        pytest.param(PASSWORD, "not-a-bcrypt-hash", id="unreadable_hash"),
        pytest.param(PASSWORD, "", id="empty_hash"),
    ],
)
def test_verify_returns_false_rather_than_raising(password: str, stored_hash: str) -> None:
    assert verify_password(password, stored_hash) is False


def test_nothing_verifies_against_the_dummy_hash() -> None:
    for candidate in ("", PASSWORD, DUMMY_PASSWORD_HASH):
        assert verify_password(candidate, DUMMY_PASSWORD_HASH) is False


def test_round_trips_the_subject() -> None:
    assert decode_access_token(create_access_token("a-subject")) == "a-subject"


def test_carries_only_the_three_expected_claims() -> None:
    payload = jwt.decode(
        create_access_token("a-subject"),
        settings.JWT_SECRET,
        algorithms=[settings.JWT_ALGORITHM],
    )

    assert set(payload) == {"sub", "iat", "exp"}


def test_lifetime_matches_the_configured_expiry() -> None:
    payload = jwt.decode(
        create_access_token("a-subject"),
        settings.JWT_SECRET,
        algorithms=[settings.JWT_ALGORITHM],
    )

    assert payload["exp"] - payload["iat"] == settings.JWT_EXPIRE_DAYS * 86400


def test_rejects_an_expired_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "JWT_EXPIRE_DAYS", -1)
    token = create_access_token("a-subject")

    with pytest.raises(jwt.ExpiredSignatureError):
        decode_access_token(token)


def test_rejects_a_token_signed_with_another_secret() -> None:
    token = jwt.encode(
        {"sub": "a-subject", "exp": 9999999999},
        settings.JWT_SECRET + "-wrong",
        algorithm=settings.JWT_ALGORITHM,
    )

    with pytest.raises(jwt.InvalidSignatureError):
        decode_access_token(token)


def test_rejects_a_tampered_token() -> None:
    token = create_access_token("a-subject")
    head, payload, signature = token.split(".")

    with pytest.raises(jwt.InvalidTokenError):
        decode_access_token(f"{head}.{payload}x.{signature}")


@pytest.mark.parametrize(
    "token", ["", "garbage", "a.b.c"], ids=["empty", "not_a_jwt", "three_parts"]
)
def test_rejects_a_malformed_token(token: str) -> None:
    with pytest.raises(jwt.DecodeError):
        decode_access_token(token)


def test_rejects_a_token_with_no_expiry() -> None:
    token = jwt.encode({"sub": "a-subject"}, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)

    with pytest.raises(jwt.MissingRequiredClaimError):
        decode_access_token(token)


def test_rejects_a_token_with_no_subject() -> None:
    token = jwt.encode({"exp": 9999999999}, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)

    with pytest.raises(jwt.MissingRequiredClaimError):
        decode_access_token(token)


def test_rejects_a_token_signed_with_another_algorithm() -> None:
    token = jwt.encode(
        {"sub": "a-subject", "exp": 9999999999}, settings.JWT_SECRET, algorithm="HS512"
    )

    with pytest.raises(jwt.InvalidAlgorithmError):
        decode_access_token(token)
