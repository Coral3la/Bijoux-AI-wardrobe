"""`POST /looks/suggest`, measured end to end with the model faked.

The stylist is replaced at the binding **the route imported** — the lesson
`tests/conftest.py` records from task 1.3, where a fake installed on the
definition let the retry out to the live API. `validate_look_response` is
deliberately *not* faked: the hallucination guard and the retry are what this
endpoint is for, so the answers below are judged by the real rules.

No fixture file. `short_id`s are generated per row (`DECISIONS.md` 159), so
every answer here is built from the ids the wardrobe fixture actually planted —
except the one that is meant to be a hallucination.
"""

import uuid
from collections.abc import Callable
from dataclasses import replace
from datetime import date, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from openai import APITimeoutError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.v1.routes import looks as looks_route
from app.enums import Category, Condition, ItemStatus, Layer
from app.models.item import Item
from app.models.look import Look, LookItem
from app.models.user import User
from app.services.stylist import Look as StylistLook
from app.services.stylist import MissingPiece, StylistResponse
from app.services.weather import Forecast

# The forecast is faked in every test but one, so this date is never measured
# against the provider's horizon. It is `03-AI-CONTRACTS.md`'s worked example.
WHEN = date(2026, 3, 14)

# Warm and dry on purpose: rule 6 does not fire, so an answer with no coat is a
# valid answer and the tests below are about this endpoint rather than about the
# weather table, which `tests/unit/test_weather.py` already measures.
FORECAST = Forecast(
    date=WHEN,
    temp_min_c=18.0,
    temp_max_c=24.0,
    precip_mm=0.0,
    wind_kph=10.0,
    condition=Condition.CLEAR,
)

WARDROBE: tuple[tuple[Category, Layer], ...] = (
    (Category.SHOES, Layer.STANDALONE),
    (Category.TOP, Layer.BASE),
    (Category.BOTTOM, Layer.BASE),
    (Category.DRESS, Layer.STANDALONE),
    (Category.BAG, Layer.STANDALONE),
    (Category.ACCESSORY, Layer.STANDALONE),
)


class FakeStylist:
    """The answers `suggest_looks` will give, in order, and what it was asked.

    The last answer repeats, so a test that expects one call and a test that
    expects two can both hand over a single response. An `Exception` in the
    queue is raised rather than returned.
    """

    def __init__(self, *answers: StylistResponse | Exception) -> None:
        self.answers = list(answers)
        self.wardrobes: list[tuple[str, ...]] = []
        self.contexts: list[Any] = []
        self.corrections: list[str | None] = []

    async def __call__(
        self, wardrobe: Any, context: Any, correction: str | None = None
    ) -> StylistResponse:
        self.wardrobes.append(tuple(item.short_id for item in wardrobe))
        self.contexts.append(context)
        self.corrections.append(correction)
        answer = self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]
        if isinstance(answer, Exception):
            raise answer
        return answer

    @property
    def calls(self) -> int:
        return len(self.wardrobes)


def answer(*item_ids: str, message: str = "A work outfit for a mild day.") -> StylistResponse:
    return StylistResponse(
        looks=(
            StylistLook(
                occasion="work",
                title="Morning meetings",
                item_ids=item_ids,
                reasoning="The straight jean balances the oversized shirt.",
                weather_note="24°C — no coat needed.",
            ),
        ),
        missing_pieces=(
            MissingPiece(
                category="shoes",
                description="a neutral closed shoe",
                reason="nothing water-resistant in the wardrobe",
            ),
        ),
        message=message,
    )


@pytest.fixture
def user(make_user: Callable[..., User]) -> User:
    # Tel Aviv, the coordinates `04-API-SPEC.md`'s own PATCH /me example uses.
    return make_user(home_city="Tel Aviv", home_lat=32.08, home_lon=34.78)


@pytest.fixture
def wardrobe(user: User, make_item: Callable[..., Item]) -> list[Item]:
    return [
        make_item(user_id=user.id, status=ItemStatus.READY, category=category, layer=layer)
        for category, layer in WARDROBE
    ]


@pytest.fixture
def forecasts(monkeypatch: pytest.MonkeyPatch) -> list[tuple[float, float, date]]:
    """Open-Meteo, recorded instead of called."""
    asked: list[tuple[float, float, date]] = []

    async def _forecast(lat: float, lon: float, on: date) -> Forecast:
        asked.append((lat, lon, on))
        return replace(FORECAST, date=on)

    monkeypatch.setattr(looks_route, "get_forecast", _forecast)
    return asked


@pytest.fixture
def stylist(monkeypatch: pytest.MonkeyPatch) -> Callable[..., FakeStylist]:
    def _install(*answers: StylistResponse | Exception) -> FakeStylist:
        fake = FakeStylist(*answers)
        monkeypatch.setattr(looks_route, "suggest_looks", fake)
        return fake

    return _install


def request_body(**overrides: Any) -> dict[str, Any]:
    return {"occasion": "work", "date": WHEN.isoformat()} | overrides


def suggest(
    client: TestClient,
    user: User,
    authorization: Callable[[User], dict[str, str]],
    **overrides: Any,
) -> Any:
    return client.post(
        "/api/v1/looks/suggest", json=request_body(**overrides), headers=authorization(user)
    )


def test_a_suggestion_comes_back_with_its_items_hydrated(
    client: TestClient,
    user: User,
    wardrobe: list[Item],
    forecasts: list[Any],
    stylist: Callable[..., FakeStylist],
    authorization: Callable[[User], dict[str, str]],
    cloudinary_configured: None,
) -> None:
    shoes, top, bottom = wardrobe[0], wardrobe[1], wardrobe[2]
    stylist(answer(shoes.short_id, top.short_id, bottom.short_id))

    response = suggest(client, user, authorization)

    assert response.status_code == 200
    body = response.json()
    look = body["looks"][0]
    # The whole point of the hydration step: ids in, garments out.
    assert [item["short_id"] for item in look["items"]] == [
        shoes.short_id,
        top.short_id,
        bottom.short_id,
    ]
    assert look["items"][0]["image_url"].startswith("https://")
    assert look["occasion"] == "work"
    assert look["reasoning"] and look["weather_note"]
    assert body["missing_pieces"][0]["category"] == "shoes"
    assert body["message"] == "A work outfit for a mild day."


def test_the_look_is_persisted_unsaved_with_the_model_s_ordering(
    client: TestClient,
    db: Session,
    user: User,
    wardrobe: list[Item],
    forecasts: list[Any],
    stylist: Callable[..., FakeStylist],
    authorization: Callable[[User], dict[str, str]],
    cloudinary_configured: None,
) -> None:
    chosen = [wardrobe[2], wardrobe[0], wardrobe[1]]
    stylist(answer(*[item.short_id for item in chosen]))

    response = suggest(client, user, authorization)

    row = db.get(Look, uuid.UUID(response.json()["looks"][0]["id"]))
    assert row is not None
    assert row.is_saved is False
    assert row.occasion == "work"
    assert row.for_date == WHEN

    rows = db.scalars(
        select(LookItem).where(LookItem.look_id == row.id).order_by(LookItem.position)
    ).all()
    assert [item.item_id for item in rows] == [item.id for item in chosen]
    assert [item.position for item in rows] == [0, 1, 2]
    # Left NULL deliberately until 2.11 has a reader and a vocabulary — O-25.
    assert all(item.role is None for item in rows)


def test_an_item_id_the_wardrobe_does_not_hold_never_reaches_the_client(
    client: TestClient,
    user: User,
    wardrobe: list[Item],
    forecasts: list[Any],
    stylist: Callable[..., FakeStylist],
    authorization: Callable[[User], dict[str, str]],
    cloudinary_configured: None,
) -> None:
    # The hallucination guard. `ZZZZZZ` is not planted anywhere — it is a
    # literal precisely because it must not be a row.
    fake = stylist(answer(wardrobe[0].short_id, wardrobe[1].short_id, "ZZZZZZ"))

    response = suggest(client, user, authorization)

    assert response.status_code == 502
    assert response.json()["code"] == "stylist_failed"
    assert fake.calls == 2


def test_a_look_that_was_refused_twice_leaves_no_rows_behind(
    client: TestClient,
    db: Session,
    user: User,
    wardrobe: list[Item],
    forecasts: list[Any],
    stylist: Callable[..., FakeStylist],
    authorization: Callable[[User], dict[str, str]],
    cloudinary_configured: None,
) -> None:
    # No shoes: rule 2. A rejected look is never persisted, so nothing in the
    # `looks` table can be mistaken later for a suggestion that was served.
    stylist(answer(wardrobe[1].short_id, wardrobe[2].short_id))

    assert suggest(client, user, authorization).status_code == 502
    assert db.scalar(select(func.count()).select_from(Look).where(Look.user_id == user.id)) == 0


def test_one_violation_is_retried_once_with_the_violation_named(
    client: TestClient,
    user: User,
    wardrobe: list[Item],
    forecasts: list[Any],
    stylist: Callable[..., FakeStylist],
    authorization: Callable[[User], dict[str, str]],
    cloudinary_configured: None,
) -> None:
    fake = stylist(
        answer(wardrobe[1].short_id, wardrobe[2].short_id),
        answer(wardrobe[0].short_id, wardrobe[1].short_id, wardrobe[2].short_id),
    )

    response = suggest(client, user, authorization)

    assert response.status_code == 200
    assert fake.calls == 2
    assert fake.corrections[0] is None
    assert fake.corrections[1] == "the look has no shoes"
    # The same wardrobe both times: a retry is one more instruction, not a
    # smaller prompt.
    assert fake.wardrobes[0] == fake.wardrobes[1]


def test_a_provider_failure_is_not_retried(
    client: TestClient,
    user: User,
    wardrobe: list[Item],
    forecasts: list[Any],
    stylist: Callable[..., FakeStylist],
    authorization: Callable[[User], dict[str, str]],
    cloudinary_configured: None,
) -> None:
    # `03-AI-CONTRACTS.md`: a timeout reads to the user like invalid output and
    # "the request is not retried automatically". There is no violation to name,
    # so the one retry is not spent.
    fake = stylist(APITimeoutError(request=None))  # type: ignore[arg-type]

    response = suggest(client, user, authorization)

    assert response.status_code == 502
    assert response.json()["code"] == "stylist_failed"
    assert fake.calls == 1


def test_five_usable_items_are_refused_before_anything_leaves_the_process(
    client: TestClient,
    user: User,
    make_item: Callable[..., Item],
    forecasts: list[Any],
    stylist: Callable[..., FakeStylist],
    authorization: Callable[[User], dict[str, str]],
) -> None:
    for category, layer in WARDROBE[:5]:
        make_item(user_id=user.id, status=ItemStatus.READY, category=category, layer=layer)
    fake = stylist(answer("NEVER1"))

    response = suggest(client, user, authorization)

    assert response.status_code == 400
    assert response.json()["code"] == "wardrobe_too_small"
    assert fake.calls == 0
    assert forecasts == []


def test_the_stylist_is_shown_only_ready_unarchived_and_unexcluded_items(
    client: TestClient,
    user: User,
    wardrobe: list[Item],
    make_item: Callable[..., Item],
    make_user: Callable[..., User],
    forecasts: list[Any],
    stylist: Callable[..., FakeStylist],
    authorization: Callable[[User], dict[str, str]],
    cloudinary_configured: None,
) -> None:
    # O-21's other half, and the two filters that predate it, measured together
    # because they are one list.
    make_item(user_id=user.id, status=ItemStatus.READY, category=Category.SWIMWEAR)
    make_item(user_id=user.id, status=ItemStatus.READY, category=Category.SLEEPWEAR)
    make_item(user_id=user.id, status=ItemStatus.READY, category=Category.TOP, is_archived=True)
    make_item(user_id=user.id, status=ItemStatus.PROCESSING, category=Category.TOP)
    make_item(user_id=make_user().id, status=ItemStatus.READY, category=Category.TOP)

    fake = stylist(answer(wardrobe[0].short_id, wardrobe[1].short_id, wardrobe[2].short_id))
    assert suggest(client, user, authorization).status_code == 200

    assert set(fake.wardrobes[0]) == {item.short_id for item in wardrobe}


def test_an_account_with_no_home_location_cannot_ask_for_a_look(
    client: TestClient,
    make_user: Callable[..., User],
    make_item: Callable[..., Item],
    forecasts: list[Any],
    stylist: Callable[..., FakeStylist],
    authorization: Callable[[User], dict[str, str]],
) -> None:
    homeless = make_user()
    for category, layer in WARDROBE:
        make_item(user_id=homeless.id, status=ItemStatus.READY, category=category, layer=layer)
    fake = stylist(answer("NEVER1"))

    response = suggest(client, homeless, authorization)

    assert response.status_code == 400
    assert response.json()["code"] == "home_location_missing"
    assert fake.calls == 0


def test_a_date_beyond_the_forecast_horizon_is_refused(
    client: TestClient,
    user: User,
    wardrobe: list[Item],
    stylist: Callable[..., FakeStylist],
    authorization: Callable[[User], dict[str, str]],
) -> None:
    # `get_forecast` is deliberately *not* faked here: the horizon is checked
    # locally, so nothing leaves the process and the real function is the one
    # under test at this seam.
    fake = stylist(answer("NEVER1"))
    beyond = date.today() + timedelta(days=looks_route.FORECAST_HORIZON_DAYS + 1)

    response = suggest(client, user, authorization, date=beyond.isoformat())

    assert response.status_code == 400
    assert response.json()["code"] == "forecast_unavailable"
    assert fake.calls == 0


def test_an_occasion_outside_the_vocabulary_is_refused(
    client: TestClient,
    user: User,
    wardrobe: list[Item],
    forecasts: list[Any],
    stylist: Callable[..., FakeStylist],
    authorization: Callable[[User], dict[str, str]],
) -> None:
    # The only thing enforcing the six values: `looks.occasion` is TEXT.
    fake = stylist(answer("NEVER1"))

    response = suggest(client, user, authorization, occasion="office")

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"
    assert fake.calls == 0


# --- the anchor, task 2.10 ---------------------------------------------------


def test_the_anchor_reaches_the_stylist_as_a_short_id(
    client: TestClient,
    user: User,
    wardrobe: list[Item],
    forecasts: list[Any],
    stylist: Callable[..., FakeStylist],
    authorization: Callable[[User], dict[str, str]],
    cloudinary_configured: None,
) -> None:
    # The wire carries the UUID and the prompt prints the `short_id`; this
    # endpoint is the only place that knows both.
    shoes, top, bottom = wardrobe[0], wardrobe[1], wardrobe[2]
    fake = stylist(answer(shoes.short_id, top.short_id, bottom.short_id))

    response = suggest(client, user, authorization, anchor_item_id=str(top.id))

    assert response.status_code == 200
    assert fake.contexts[0].anchor_id == top.short_id


def test_a_look_without_the_anchor_is_retried_and_then_refused(
    client: TestClient,
    user: User,
    wardrobe: list[Item],
    forecasts: list[Any],
    stylist: Callable[..., FakeStylist],
    authorization: Callable[[User], dict[str, str]],
    cloudinary_configured: None,
) -> None:
    # Rule 7 through the endpoint that owns the retry: a look which is complete
    # and legal in every other way still fails, because the garment she is
    # holding is not in it.
    shoes, top, bottom, bag = wardrobe[0], wardrobe[1], wardrobe[2], wardrobe[4]
    fake = stylist(answer(shoes.short_id, top.short_id, bottom.short_id))

    response = suggest(client, user, authorization, anchor_item_id=str(bag.id))

    assert response.status_code == 502
    assert response.json()["code"] == "stylist_failed"
    assert fake.calls == 2
    assert f"anchored item {bag.short_id}" in str(fake.corrections[1])


def test_a_second_answer_that_honours_the_anchor_is_accepted(
    client: TestClient,
    user: User,
    wardrobe: list[Item],
    forecasts: list[Any],
    stylist: Callable[..., FakeStylist],
    authorization: Callable[[User], dict[str, str]],
    cloudinary_configured: None,
) -> None:
    shoes, top, bottom, bag = wardrobe[0], wardrobe[1], wardrobe[2], wardrobe[4]
    stylist(
        answer(shoes.short_id, top.short_id, bottom.short_id),
        answer(shoes.short_id, top.short_id, bottom.short_id, bag.short_id),
    )

    response = suggest(client, user, authorization, anchor_item_id=str(bag.id))

    assert response.status_code == 200
    assert bag.short_id in [item["short_id"] for item in response.json()["looks"][0]["items"]]


def test_an_anchor_belonging_to_another_account_is_refused(
    client: TestClient,
    user: User,
    wardrobe: list[Item],
    make_item: Callable[..., Item],
    make_user: Callable[..., User],
    forecasts: list[Any],
    stylist: Callable[..., FakeStylist],
    authorization: Callable[[User], dict[str, str]],
) -> None:
    hers = make_item(user_id=make_user().id, status=ItemStatus.READY, category=Category.TOP)
    fake = stylist(answer("NEVER1"))

    response = suggest(client, user, authorization, anchor_item_id=str(hers.id))

    assert response.status_code == 422
    assert response.json()["code"] == "anchor_unavailable"
    # Answered from rows already in hand: neither Open-Meteo nor OpenAI is asked.
    assert fake.calls == 0
    assert forecasts == []


@pytest.mark.parametrize(
    ("columns", "why"),
    [
        ({"status": ItemStatus.PROCESSING, "category": Category.TOP}, "still being tagged"),
        ({"status": ItemStatus.READY, "category": Category.TOP, "is_archived": True}, "archived"),
        ({"status": ItemStatus.READY, "category": Category.SWIMWEAR}, "an excluded category"),
    ],
)
def test_an_anchor_the_stylist_never_sees_is_refused(
    columns: dict[str, Any],
    why: str,
    client: TestClient,
    user: User,
    wardrobe: list[Item],
    make_item: Callable[..., Item],
    forecasts: list[Any],
    stylist: Callable[..., FakeStylist],
    authorization: Callable[[User], dict[str, str]],
) -> None:
    # Owned, and still not styleable. `_wardrobe` never sends it, so rule 1
    # would call the id a hallucination — letting it through would buy two model
    # calls and a 502 for a question this lookup answers for nothing.
    unseen = make_item(user_id=user.id, **columns)
    fake = stylist(answer("NEVER1"))

    response = suggest(client, user, authorization, anchor_item_id=str(unseen.id))

    assert response.status_code == 422, why
    assert response.json()["code"] == "anchor_unavailable"
    assert fake.calls == 0


def test_an_anchor_that_is_not_a_uuid_is_the_schema_s_own_rejection(
    client: TestClient,
    user: User,
    wardrobe: list[Item],
    forecasts: list[Any],
    stylist: Callable[..., FakeStylist],
    authorization: Callable[[User], dict[str, str]],
) -> None:
    # A `short_id` in this field is the mistake the type is there to catch, and
    # it never reaches `_anchor` — so the code is `validation_error`, not
    # `anchor_unavailable`.
    fake = stylist(answer("NEVER1"))

    response = suggest(client, user, authorization, anchor_item_id=wardrobe[0].short_id)

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"
    assert fake.calls == 0


def test_a_request_with_no_anchor_sends_none(
    client: TestClient,
    user: User,
    wardrobe: list[Item],
    forecasts: list[Any],
    stylist: Callable[..., FakeStylist],
    authorization: Callable[[User], dict[str, str]],
    cloudinary_configured: None,
) -> None:
    # `STAGE-2`'s last acceptance criterion, at the seam it is about.
    shoes, top, bottom = wardrobe[0], wardrobe[1], wardrobe[2]
    fake = stylist(answer(shoes.short_id, top.short_id, bottom.short_id))

    assert suggest(client, user, authorization).status_code == 200
    assert fake.contexts[0].anchor_id is None
