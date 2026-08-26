"""PATCH /me — the whole profile body, its partial-update semantics, and the
one rule that is this endpoint's own.

The semantics are `PATCH /items/{id}`'s and are asserted again here rather than
assumed from there: an omitted field is left alone, an explicit null clears,
an unknown key is refused and an empty body is a 422. The rule that is only
this endpoint's is the home location — three columns that travel as one field,
because a city with no coordinates cannot be given a forecast and coordinates
with no city name have nothing to print above the weather strip.
"""

from collections.abc import Callable

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.user import MAX_HEIGHT_CM, MIN_HEIGHT_CM, User

ME_URL = "/api/v1/me"

TEL_AVIV = {"home_city": "Tel Aviv", "home_lat": 32.08, "home_lon": 34.78}


def test_writes_every_field_in_the_documented_body(
    client: TestClient,
    db: Session,
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
) -> None:
    # 04-API-SPEC.md's worked body, verbatim. STAGE-2 2.2 named three of these
    # nine; the stylist prompt at 2.4 reads two of the six it left out.
    user = make_user()

    response = client.patch(
        ME_URL,
        json={
            "display_name": "Coral",
            "height_cm": 165,
            "size_top": "M",
            "size_bottom": "28",
            "size_shoe": "38",
            "style_notes": "prefer high-rise, avoid crop tops",
            **TEL_AVIV,
        },
        headers=authorization(user),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["display_name"] == "Coral"
    assert body["height_cm"] == 165
    assert body["style_notes"] == "prefer high-rise, avoid crop tops"
    assert body["home_city"] == "Tel Aviv"

    db.refresh(user)
    assert user.size_shoe == "38"
    assert user.home_lat is not None
    assert round(user.home_lat, 2) == 32.08


def test_the_response_is_the_whole_user_object(
    client: TestClient,
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
) -> None:
    # One shape for one resource (034): the same keys GET /auth/me returns, so
    # the client replaces its user rather than merging a special case.
    user = make_user()

    patched = client.patch(ME_URL, json={"height_cm": 165}, headers=authorization(user)).json()
    fetched = client.get("/api/v1/auth/me", headers=authorization(user)).json()

    assert patched == fetched


def test_an_omitted_field_is_left_alone(
    client: TestClient,
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
) -> None:
    user = make_user(style_notes="avoid crop tops")

    response = client.patch(ME_URL, json={"height_cm": 165}, headers=authorization(user))

    assert response.json()["style_notes"] == "avoid crop tops"


def test_an_explicit_null_clears_the_field(
    client: TestClient,
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
) -> None:
    user = make_user(style_notes="avoid crop tops")

    response = client.patch(ME_URL, json={"style_notes": None}, headers=authorization(user))

    assert response.json()["style_notes"] is None


def test_an_empty_body_is_422(
    client: TestClient,
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
) -> None:
    user = make_user()

    response = client.patch(ME_URL, json={}, headers=authorization(user))

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"


def test_an_unknown_key_is_422(
    client: TestClient,
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
) -> None:
    # A valid field travels alongside, so only extra="forbid" can produce this
    # answer — without it the dump would be non-empty and the request would be
    # a 200 that silently ignored the typo. Task 1.4 shipped this test with
    # only the typo in it and it passed with the guard removed.
    user = make_user()

    response = client.patch(
        ME_URL, json={"height_cm": 165, "hight_cm": 165}, headers=authorization(user)
    )

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"


def test_a_blank_display_name_is_422(
    client: TestClient,
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
) -> None:
    # The DisplayName annotation, reused from the register body exactly as
    # DECISIONS.md 072 said it would be. Strip runs before min_length.
    user = make_user(display_name="Coral")

    response = client.patch(ME_URL, json={"display_name": "   "}, headers=authorization(user))

    assert response.status_code == 422


def test_a_display_name_is_trimmed_rather_than_stored_padded(
    client: TestClient,
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
) -> None:
    user = make_user()

    response = client.patch(ME_URL, json={"display_name": "  Coral  "}, headers=authorization(user))

    assert response.json()["display_name"] == "Coral"


def test_a_display_name_can_be_cleared(
    client: TestClient,
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
) -> None:
    # New behaviour at 2.2 and a deliberate one: before this endpoint nothing
    # in the API could blank a name. userLabel falls back to the email (071).
    user = make_user(display_name="Coral")

    response = client.patch(ME_URL, json={"display_name": None}, headers=authorization(user))

    assert response.json()["display_name"] is None


def test_a_height_below_the_check_constraint_is_422_not_500(
    client: TestClient,
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
) -> None:
    # Without the bound on the schema this reaches Postgres, where
    # ck_users_height_cm_range is an IntegrityError — a 500 with no `code`.
    user = make_user()

    response = client.patch(
        ME_URL, json={"height_cm": MIN_HEIGHT_CM - 1}, headers=authorization(user)
    )

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"


def test_a_height_above_the_check_constraint_is_422_not_500(
    client: TestClient,
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
) -> None:
    user = make_user()

    response = client.patch(
        ME_URL, json={"height_cm": MAX_HEIGHT_CM + 1}, headers=authorization(user)
    )

    assert response.status_code == 422


def test_both_ends_of_the_height_range_are_accepted(
    client: TestClient,
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
) -> None:
    # The bound is the column's, so its own endpoints must pass; a schema
    # written with > instead of >= would fail exactly here and nowhere else.
    user = make_user()
    headers = authorization(user)

    assert (
        client.patch(ME_URL, json={"height_cm": MIN_HEIGHT_CM}, headers=headers).status_code == 200
    )
    assert (
        client.patch(ME_URL, json={"height_cm": MAX_HEIGHT_CM}, headers=headers).status_code == 200
    )


def test_the_three_home_fields_are_written_together(
    client: TestClient,
    db: Session,
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
) -> None:
    user = make_user()

    response = client.patch(ME_URL, json=dict(TEL_AVIV), headers=authorization(user))

    assert response.status_code == 200
    db.refresh(user)
    assert user.home_city == "Tel Aviv"
    assert user.home_lat is not None and user.home_lon is not None


def test_a_home_city_without_coordinates_is_422(
    client: TestClient,
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
) -> None:
    # The row this refuses is the one 2.7 cannot use: a place name that no
    # forecast can be fetched for.
    user = make_user()

    response = client.patch(ME_URL, json={"home_city": "Tel Aviv"}, headers=authorization(user))

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"


def test_coordinates_without_a_city_are_422(
    client: TestClient,
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
) -> None:
    user = make_user()

    response = client.patch(
        ME_URL, json={"home_lat": 32.08, "home_lon": 34.78}, headers=authorization(user)
    )

    assert response.status_code == 422


def test_a_half_cleared_home_location_is_422(
    client: TestClient,
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
) -> None:
    # All three supplied, one of them null. The count rule alone passes this,
    # which is why the validator checks the values as well as the keys.
    user = make_user(**TEL_AVIV)

    response = client.patch(
        ME_URL,
        json={"home_city": "Tel Aviv", "home_lat": None, "home_lon": 34.78},
        headers=authorization(user),
    )

    assert response.status_code == 422


def test_clearing_only_the_city_is_422(
    client: TestClient,
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
) -> None:
    # Found by mutation. Every other partial request is refused by the rule
    # about values, so the rule about *keys* is reachable only here: one field,
    # supplied, null. Without it this is a 200 that leaves coordinates behind
    # with no city name attached to them.
    user = make_user(**TEL_AVIV)

    response = client.patch(ME_URL, json={"home_city": None}, headers=authorization(user))

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"


def test_the_home_location_can_be_cleared_as_a_unit(
    client: TestClient,
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
) -> None:
    user = make_user(**TEL_AVIV)

    response = client.patch(
        ME_URL,
        json={"home_city": None, "home_lat": None, "home_lon": None},
        headers=authorization(user),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["home_city"] is None
    assert body["home_lat"] is None
    assert body["home_lon"] is None


def test_an_out_of_range_latitude_is_422(
    client: TestClient,
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
) -> None:
    user = make_user()

    response = client.patch(
        ME_URL,
        json={"home_city": "Nowhere", "home_lat": 91.0, "home_lon": 34.78},
        headers=authorization(user),
    )

    assert response.status_code == 422


def test_editing_a_profile_touches_nobody_elses(
    client: TestClient,
    db: Session,
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
) -> None:
    user = make_user()
    other = make_user(display_name="Someone else")

    client.patch(ME_URL, json={"display_name": "Coral"}, headers=authorization(user))

    db.refresh(other)
    assert other.display_name == "Someone else"


def test_without_a_token_it_is_401(client: TestClient) -> None:
    response = client.patch(ME_URL, json={"height_cm": 165})

    assert response.status_code == 401
    assert response.json()["code"] == "invalid_token"
