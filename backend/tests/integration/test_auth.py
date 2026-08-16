"""The register, login and /auth/me route tests task 0.5 deferred by name.

0.5 shipped security.py's unit tests because that module imports no ORM and no
session (`DECISIONS.md` 038). Everything here needs a row, and the row needs
the fixture task 0.10 owns.
"""

import uuid
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import security
from app.core.security import create_access_token
from app.models.user import User

REGISTER_URL = "/api/v1/auth/register"
LOGIN_URL = "/api/v1/auth/login"
ME_URL = "/api/v1/auth/me"

PASSWORD = "correct horse battery"


def _body(**overrides: Any) -> dict[str, Any]:
    body = {
        "email": f"{uuid.uuid4().hex}@example.com",
        "password": PASSWORD,
        "display_name": "Coral",
    }
    body.update(overrides)
    return body


# --- register ---------------------------------------------------------------


def test_register_creates_the_row_and_returns_a_token(client: TestClient, db: Session) -> None:
    body = _body()

    response = client.post(REGISTER_URL, json=body)

    assert response.status_code == 201
    assert db.scalar(select(User).where(User.email == body["email"])) is not None


def test_register_returns_the_new_user_alongside_the_token(client: TestClient) -> None:
    response = client.post(REGISTER_URL, json=_body(display_name="Coral"))

    payload = response.json()
    assert payload["token_type"] == "bearer"
    assert payload["user"]["display_name"] == "Coral"


def test_register_returns_a_token_that_identifies_the_new_user(
    client: TestClient, db: Session
) -> None:
    payload = client.post(REGISTER_URL, json=_body()).json()

    subject = security.decode_access_token(payload["access_token"])
    assert subject == payload["user"]["id"]
    assert db.get(User, uuid.UUID(subject)) is not None


def test_register_never_returns_the_password_hash(client: TestClient) -> None:
    payload = client.post(REGISTER_URL, json=_body()).json()

    assert "password_hash" not in payload["user"]


def test_register_stores_a_hash_rather_than_the_password(client: TestClient, db: Session) -> None:
    body = _body()

    client.post(REGISTER_URL, json=body)

    user = db.scalar(select(User).where(User.email == body["email"]))
    assert user is not None
    assert user.password_hash != PASSWORD
    assert security.verify_password(PASSWORD, user.password_hash)


def test_register_trims_the_display_name(client: TestClient) -> None:
    response = client.post(REGISTER_URL, json=_body(display_name="  Coral  "))

    assert response.json()["user"]["display_name"] == "Coral"


def test_register_rejects_a_display_name_that_is_only_whitespace(client: TestClient) -> None:
    # The trim runs before the length check, which is the whole reason
    # StringConstraints was used rather than Field. DECISIONS.md 072.
    response = client.post(REGISTER_URL, json=_body(display_name="   "))

    body = response.json()
    assert response.status_code == 422
    assert body["code"] == "validation_error"
    assert body["detail"].startswith("display_name: ")


def test_register_requires_a_display_name(client: TestClient) -> None:
    body = _body()
    del body["display_name"]

    response = client.post(REGISTER_URL, json=body)

    assert response.status_code == 422
    assert response.json()["detail"].startswith("display_name: ")


def test_register_rejects_a_duplicate_email(client: TestClient) -> None:
    body = _body()
    client.post(REGISTER_URL, json=body)

    response = client.post(REGISTER_URL, json=body)

    assert response.status_code == 409
    assert response.json()["code"] == "email_exists"


def test_register_treats_an_email_as_case_insensitive(client: TestClient) -> None:
    # CITEXT, per 02-DATA-MODEL.md. Nothing in the Python layer lowercases,
    # so this is the column's behaviour or it is nobody's.
    address = f"{uuid.uuid4().hex}@example.com"
    client.post(REGISTER_URL, json=_body(email=address.upper()))

    response = client.post(REGISTER_URL, json=_body(email=address))

    assert response.status_code == 409


def test_register_rejects_a_password_below_the_minimum(client: TestClient) -> None:
    response = client.post(REGISTER_URL, json=_body(password="short"))

    assert response.status_code == 422
    assert response.json()["detail"].startswith("password: ")


def test_register_rejects_a_password_over_the_byte_limit(client: TestClient) -> None:
    # 36 Hebrew characters is 72 bytes; one more is over the line while still
    # reading as a short password. DECISIONS.md 036.
    response = client.post(REGISTER_URL, json=_body(password="ש" * 37))

    body = response.json()
    assert response.status_code == 422
    assert "bytes" in body["detail"]


def test_register_rejects_an_unknown_field(client: TestClient) -> None:
    response = client.post(REGISTER_URL, json=_body(displayname="Coral"))

    assert response.status_code == 422


# --- login ------------------------------------------------------------------


def test_login_returns_a_token_for_correct_credentials(
    client: TestClient, make_user: Callable[..., User]
) -> None:
    user = make_user(password=PASSWORD)

    response = client.post(LOGIN_URL, json={"email": user.email, "password": PASSWORD})

    assert response.status_code == 200
    assert response.json()["user"]["id"] == str(user.id)


def test_login_rejects_a_wrong_password(client: TestClient, make_user: Callable[..., User]) -> None:
    user = make_user(password=PASSWORD)

    response = client.post(LOGIN_URL, json={"email": user.email, "password": "not the password"})

    assert response.status_code == 401
    assert response.json()["code"] == "invalid_credentials"


def test_login_answers_an_unknown_email_exactly_as_a_wrong_password(
    client: TestClient, make_user: Callable[..., User]
) -> None:
    user = make_user(password=PASSWORD)

    known = client.post(LOGIN_URL, json={"email": user.email, "password": "wrong"})
    unknown = client.post(LOGIN_URL, json={"email": "nobody@example.com", "password": "wrong"})

    assert unknown.status_code == known.status_code
    assert unknown.json() == known.json()


def test_login_hashes_even_when_the_email_is_unknown(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The dummy hash closes a timing channel (DECISIONS.md 037), and timing is
    # not assertable. Counting the call is: without the dummy comparison the
    # route returns before verify_password is ever reached.
    calls: list[str] = []

    def counted(password: str, password_hash: str) -> bool:
        calls.append(password_hash)
        return False

    monkeypatch.setattr("app.api.v1.routes.auth.verify_password", counted)

    client.post(LOGIN_URL, json={"email": "nobody@example.com", "password": "wrong"})

    assert len(calls) == 1


def test_login_401_offers_the_bearer_challenge(client: TestClient) -> None:
    # 04-API-SPEC.md: every 401 carries WWW-Authenticate. deps.py always did;
    # this route did not until task 0.10.
    response = client.post(LOGIN_URL, json={"email": "nobody@example.com", "password": "wrong"})

    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_login_rejects_an_unknown_field(client: TestClient) -> None:
    response = client.post(
        LOGIN_URL, json={"email": "a@example.com", "password": "x", "remember": True}
    )

    assert response.status_code == 422


# --- /auth/me ---------------------------------------------------------------


def test_me_returns_the_authenticated_user(
    client: TestClient,
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
) -> None:
    user = make_user(display_name="Coral")

    response = client.get(ME_URL, headers=authorization(user))

    assert response.status_code == 200
    assert response.json()["id"] == str(user.id)


def test_me_without_a_token_is_401(client: TestClient) -> None:
    response = client.get(ME_URL)

    assert response.status_code == 401
    assert response.json()["code"] == "invalid_token"


def test_me_without_a_token_offers_the_bearer_challenge(client: TestClient) -> None:
    response = client.get(ME_URL)

    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_me_rejects_a_token_this_server_did_not_sign(client: TestClient) -> None:
    response = client.get(ME_URL, headers={"Authorization": "Bearer not.a.token"})

    assert response.status_code == 401


def test_me_rejects_a_valid_token_whose_user_no_longer_exists(
    client: TestClient, make_user: Callable[..., User], db: Session
) -> None:
    # 035's fifth failure: a well-formed token whose sub no longer resolves is
    # a 401, not a 404 — the caller asked about a credential, not a resource.
    user = make_user()
    header = {"Authorization": f"Bearer {create_access_token(str(user.id))}"}
    db.delete(user)
    db.commit()

    response = client.get(ME_URL, headers=header)

    assert response.status_code == 401
