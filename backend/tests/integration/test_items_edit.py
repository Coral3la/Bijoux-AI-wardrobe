"""`PATCH`, `DELETE` and `POST /retag` — the three endpoints that write to a
row a user has already seen.

The `PATCH` half is mostly about one sentence: **what is validated is the
request merged over the stored row**, not the request alone. `04-API-SPEC.md`
said the second through task 1.4 and a literal reading of it passes a category
change that leaves `subcategory` and `rise` describing a different garment.

The retag half is about what a row must look like before `tag_and_store` is
queued against it. The task itself is recorded rather than run — the `queued`
fixture in `conftest.py` is autouse — so these tests assert the wiring and the
row, and `test_tagging.py` owns what the task then does with it.
"""

import uuid
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.enums import CATEGORY_DEPENDENT_FIELDS, REQUIRED_TAG_FIELDS
from app.models.item import Item
from app.models.user import User

pytestmark = pytest.mark.usefixtures("cloudinary_configured")

ITEMS_URL = "/api/v1/items"

# A tagged pair of jeans: every category-dependent field populated, so a
# category change has all five to clear and the clearing is observable.
JEANS: dict[str, Any] = {
    "status": "ready",
    "category": "bottom",
    "subcategory": "jeans",
    "fit": "straight",
    "length": "full",
    "rise": "high",
    "color_primary": "light_blue",
    "pattern": "denim_wash",
    "material": "denim",
    "formality": 2,
    "warmth": 2,
    "layer": "base",
    "display_name": "light blue straight jeans",
}


def _url(item: Item, suffix: str = "") -> str:
    return f"{ITEMS_URL}/{item.id}{suffix}"


# --- PATCH: what gets validated -------------------------------------------


def test_patching_a_tag_writes_it_and_sets_user_edited(
    client: TestClient,
    db: Session,
    make_item: Callable[..., Item],
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
) -> None:
    user = make_user()
    item = make_item(user_id=user.id, **JEANS)

    response = client.patch(_url(item), json={"fit": "skinny"}, headers=authorization(user))

    assert response.status_code == 200
    assert response.json()["fit"] == "skinny"
    assert response.json()["user_edited"] is True
    db.refresh(item)
    assert item.fit == "skinny"


def test_an_unsent_field_is_left_alone(
    client: TestClient,
    make_item: Callable[..., Item],
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
) -> None:
    user = make_user()
    item = make_item(user_id=user.id, **JEANS)

    response = client.patch(
        _url(item), json={"display_name": "my good jeans"}, headers=authorization(user)
    )

    assert response.json()["subcategory"] == "jeans"
    assert response.json()["rise"] == "high"


def test_an_explicit_null_clears_the_field(
    client: TestClient,
    make_item: Callable[..., Item],
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
) -> None:
    # The other half of exclude_unset: absent means "leave it", null means
    # "clear it", and one code path has to tell them apart.
    user = make_user()
    item = make_item(user_id=user.id, **JEANS)

    response = client.patch(_url(item), json={"rise": None}, headers=authorization(user))

    assert response.status_code == 200
    assert response.json()["rise"] is None


def test_the_merged_row_is_what_is_validated_not_the_request(
    client: TestClient,
    make_item: Callable[..., Item],
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
) -> None:
    # `fit: "skinny"` is a legal member of the enum and carries no category of
    # its own, so request-only validation has nothing to judge it against. It
    # is wrong only beside the stored `category: "top"`.
    user = make_user()
    item = make_item(
        user_id=user.id, status="ready", category="top", subcategory="tank", layer="base"
    )

    response = client.patch(_url(item), json={"fit": "skinny"}, headers=authorization(user))

    assert response.status_code == 422
    assert "fit" in response.json()["detail"]


def test_a_coercion_is_refused_rather_than_applied_silently(
    client: TestClient,
    db: Session,
    make_item: Callable[..., Item],
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
) -> None:
    # The whole of 028's split. The vision path would null this and carry on,
    # because there is nobody to tell; here there is somebody with a form open,
    # and a 200 whose body differs from what they typed is the worst answer.
    user = make_user()
    item = make_item(user_id=user.id, **JEANS)

    response = client.patch(_url(item), json={"fit": "flared"}, headers=authorization(user))

    assert response.status_code == 422
    db.refresh(item)
    assert item.fit == "straight"


def test_the_422_does_not_claim_the_value_was_set_to_null(
    client: TestClient,
    make_item: Callable[..., Item],
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
) -> None:
    # The vocabulary's coercion reasons end ", set to null", which describes
    # what the *vision* path does. Nothing was set to null here — the request
    # was refused — so the clause is cut before it reaches the client.
    user = make_user()
    item = make_item(user_id=user.id, **JEANS)

    response = client.patch(_url(item), json={"fit": "flared"}, headers=authorization(user))

    assert "set to" not in response.json()["detail"]


def test_a_value_outside_the_vocabulary_is_422(
    client: TestClient,
    make_item: Callable[..., Item],
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
) -> None:
    user = make_user()
    item = make_item(user_id=user.id, **JEANS)

    response = client.patch(
        _url(item), json={"color_primary": "burgundy"}, headers=authorization(user)
    )

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"
    assert "color_primary" in response.json()["detail"]


def test_an_unknown_key_is_422_rather_than_a_200_that_changed_nothing(
    client: TestClient,
    make_item: Callable[..., Item],
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
) -> None:
    # extra="forbid" is the only thing that can catch this: validate_tag_dict
    # inspects the keys it knows and would report a clean row (030).
    #
    # The known field beside it is load-bearing, and a mutation found that out.
    # With the typo alone, `extra="ignore"` drops the key, the dump is empty,
    # and the empty-body branch answers 422 as well — so the test passed with
    # the guard removed. A second, valid field makes the body non-empty, and
    # then only Pydantic can produce the 422.
    user = make_user()
    item = make_item(user_id=user.id, **JEANS)

    response = client.patch(
        _url(item),
        json={"colour_primary": "navy", "fit": "skinny"},
        headers=authorization(user),
    )

    assert response.status_code == 422


def test_an_empty_body_is_422(
    client: TestClient,
    make_item: Callable[..., Item],
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
) -> None:
    user = make_user()
    item = make_item(user_id=user.id, **JEANS)

    response = client.patch(_url(item), json={}, headers=authorization(user))

    assert response.status_code == 422


def test_a_blank_display_name_is_422(
    client: TestClient,
    make_item: Callable[..., Item],
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
) -> None:
    # validate_tag_dict checks only that it is a string, so the emptiness rule
    # lives in the schema. A blank name is a tile with nothing on it (086).
    user = make_user()
    item = make_item(user_id=user.id, **JEANS)

    response = client.patch(_url(item), json={"display_name": "   "}, headers=authorization(user))

    assert response.status_code == 422


# --- PATCH: the category-clearing rule -------------------------------------


def test_changing_the_category_clears_every_dependent_field(
    client: TestClient,
    make_item: Callable[..., Item],
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
) -> None:
    user = make_user()
    item = make_item(user_id=user.id, **JEANS)

    response = client.patch(_url(item), json={"category": "shoes"}, headers=authorization(user))

    assert response.status_code == 200
    body = response.json()
    assert [body[field] for field in CATEGORY_DEPENDENT_FIELDS] == [None] * 5


def test_a_dependent_field_sent_with_the_category_survives(
    client: TestClient,
    make_item: Callable[..., Item],
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
) -> None:
    # "For any of them the same request does not supply" — a supplied field is
    # not cleared and then re-set, it is simply never cleared.
    user = make_user()
    item = make_item(user_id=user.id, **JEANS)

    response = client.patch(
        _url(item),
        json={"category": "shoes", "subcategory": "boots"},
        headers=authorization(user),
    )

    assert response.status_code == 200
    assert response.json()["subcategory"] == "boots"
    assert response.json()["rise"] is None


def test_sending_the_category_it_already_has_clears_nothing(
    client: TestClient,
    make_item: Callable[..., Item],
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
) -> None:
    # The rule is keyed on the category *changing*, not on the key being
    # present: otherwise a client echoing the whole object back loses five
    # fields for sending the value that was already there.
    user = make_user()
    item = make_item(user_id=user.id, **JEANS)

    response = client.patch(_url(item), json={"category": "bottom"}, headers=authorization(user))

    assert response.json()["rise"] == "high"
    assert response.json()["subcategory"] == "jeans"


def test_a_category_dependent_field_on_a_processing_row_is_422(
    client: TestClient,
    make_item: Callable[..., Item],
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
) -> None:
    # Documented in STAGE-1 1.4: a processing row has no category, and whether
    # a silhouette is meaningful cannot be decided without one.
    user = make_user()
    item = make_item(user_id=user.id)

    response = client.patch(_url(item), json={"fit": "slim"}, headers=authorization(user))

    assert response.status_code == 422
    assert "fit" in response.json()["detail"]


def test_patching_another_users_item_is_404(
    client: TestClient,
    make_item: Callable[..., Item],
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
) -> None:
    owner = make_user()
    intruder = make_user()
    item = make_item(user_id=owner.id, **JEANS)

    response = client.patch(_url(item), json={"fit": "skinny"}, headers=authorization(intruder))

    assert response.status_code == 404
    assert response.json()["code"] == "not_found"


# --- PATCH: the status a completed edit clears -----------------------------
#
# `REQUIRED_TAG_FIELDS` is imported rather than transcribed, because a field
# gaining or losing "required" in the vocabulary must move these tests with it.
# What is written by hand is the *boundary*: exactly one field held back is the
# incomplete case, and it is spelled by removing one key from a complete body
# rather than by asserting against the tuple's own length.


def _complete_tags() -> dict[str, Any]:
    """Every required field `JEANS` carries — nine of the ten.

    Built by intersecting with `REQUIRED_TAG_FIELDS` so the two
    cannot drift. The tenth is `water_resistant`, which `JEANS`
    does not set and which no body here needs to: the column is
    NOT NULL with a server default, so the row arrives carrying
    `False` and is already complete in that field. That is the
    free pass named in `DECISIONS.md` 116, and it is visible here
    rather than hidden — a body of nine keys clearing a `failed`
    status is what proves it.
    """
    return {field: JEANS[field] for field in REQUIRED_TAG_FIELDS if field in JEANS}


def test_a_completed_edit_clears_a_failed_status(
    client: TestClient,
    make_item: Callable[..., Item],
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
) -> None:
    # O-3's whole promise: tagging could not read the photograph, a person
    # supplied the answer, and nothing else in the product clears that tile.
    user = make_user()
    item = make_item(user_id=user.id, status="failed", error_message="No usable answer")

    response = client.patch(_url(item), json=_complete_tags(), headers=authorization(user))

    assert response.status_code == 200
    assert response.json()["status"] == "ready"
    assert response.json()["error_message"] is None
    assert response.json()["user_edited"] is True


def test_an_incomplete_edit_leaves_the_row_failed(
    client: TestClient,
    make_item: Callable[..., Item],
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
) -> None:
    # One field short of the set, and the message that explains the failure
    # stays with the failure. `subcategory` rather than `category`, so the
    # request is a legal one that simply does not finish the row.
    user = make_user()
    item = make_item(user_id=user.id, status="failed", error_message="No usable answer")
    body = _complete_tags()
    del body["subcategory"]

    response = client.patch(_url(item), json=body, headers=authorization(user))

    assert response.status_code == 200
    assert response.json()["status"] == "failed"
    assert response.json()["error_message"] == "No usable answer"
    assert response.json()["subcategory"] is None


def test_a_completed_edit_does_not_touch_a_processing_row(
    client: TestClient,
    make_item: Callable[..., Item],
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
) -> None:
    # A background task is in flight and writes every tag column when it
    # lands (089), so a status written here would be overwritten by a task
    # that never knew about it.
    user = make_user()
    item = make_item(user_id=user.id, status="processing")

    response = client.patch(_url(item), json=_complete_tags(), headers=authorization(user))

    assert response.status_code == 200
    assert response.json()["status"] == "processing"


def test_clearing_a_field_does_not_demote_a_ready_row(
    client: TestClient,
    make_item: Callable[..., Item],
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
) -> None:
    # The rule runs in one direction. A user clearing a tag is answering,
    # not failing, and 109 already depends on a `ready` row being able to
    # carry a null beside four real tags.
    user = make_user()
    item = make_item(user_id=user.id, **JEANS)

    response = client.patch(_url(item), json={"color_primary": None}, headers=authorization(user))

    assert response.status_code == 200
    assert response.json()["status"] == "ready"
    assert response.json()["color_primary"] is None


def test_water_resistant_false_still_completes_the_row(
    client: TestClient,
    make_item: Callable[..., Item],
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
) -> None:
    # `is None`, never falsiness. `water_resistant` is the one required field
    # whose legitimate value is falsy, and reading it the other way would
    # leave every non-waterproof garment permanently failed. The same trap is
    # already commented at `vision.py`'s `_missing_fields`.
    user = make_user()
    item = make_item(user_id=user.id, status="failed", error_message="No usable answer")
    body = _complete_tags()
    body["water_resistant"] = False

    response = client.patch(_url(item), json=body, headers=authorization(user))

    assert response.status_code == 200
    assert response.json()["status"] == "ready"
    assert response.json()["water_resistant"] is False


# --- DELETE ----------------------------------------------------------------


def test_delete_archives_the_row_and_returns_it(
    client: TestClient,
    make_item: Callable[..., Item],
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
) -> None:
    user = make_user()
    item = make_item(user_id=user.id, **JEANS)

    response = client.delete(_url(item), headers=authorization(user))

    assert response.status_code == 200
    assert response.json()["is_archived"] is True
    assert response.json()["id"] == str(item.id)


def test_an_archived_item_leaves_the_wardrobe(
    client: TestClient,
    make_item: Callable[..., Item],
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
) -> None:
    # The round trip the exclusion test in test_items_rows.py cannot make: a
    # DELETE that archives correctly and a GET that stopped filtering are
    # indistinguishable from a client unless both ends are asserted.
    user = make_user()
    item = make_item(user_id=user.id, **JEANS)
    client.delete(_url(item), headers=authorization(user))

    listed = client.get(ITEMS_URL, headers=authorization(user))

    assert listed.json()["total"] == 0


def test_deleting_twice_gives_the_same_answer(
    client: TestClient,
    make_item: Callable[..., Item],
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
) -> None:
    user = make_user()
    item = make_item(user_id=user.id, **JEANS)
    client.delete(_url(item), headers=authorization(user))

    second = client.delete(_url(item), headers=authorization(user))

    assert second.status_code == 200
    assert second.json()["is_archived"] is True


def test_deleting_another_users_item_is_404(
    client: TestClient,
    make_item: Callable[..., Item],
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
) -> None:
    owner = make_user()
    intruder = make_user()
    item = make_item(user_id=owner.id, **JEANS)

    response = client.delete(_url(item), headers=authorization(intruder))

    assert response.status_code == 404


# --- retag -----------------------------------------------------------------


def test_retag_returns_202_with_the_row_back_to_processing(
    client: TestClient,
    make_item: Callable[..., Item],
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
) -> None:
    user = make_user()
    item = make_item(user_id=user.id, **JEANS)

    response = client.post(_url(item, "/retag"), headers=authorization(user))

    assert response.status_code == 202
    assert response.json()["status"] == "processing"


def test_retag_queues_the_task_for_that_row(
    client: TestClient,
    make_item: Callable[..., Item],
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
    queued: list[uuid.UUID],
) -> None:
    user = make_user()
    item = make_item(user_id=user.id, **JEANS)

    client.post(_url(item, "/retag"), headers=authorization(user))

    assert queued == [item.id]


def test_retag_clears_a_previous_failure_message(
    client: TestClient,
    make_item: Callable[..., Item],
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
) -> None:
    # A processing row still carrying the reason it failed last time is
    # incoherent, and error_message is on the wire.
    user = make_user()
    item = make_item(user_id=user.id, status="failed", error_message="No usable answer")

    response = client.post(_url(item, "/retag"), headers=authorization(user))

    assert response.json()["error_message"] is None


def test_retag_keeps_the_tags_the_row_already_had(
    client: TestClient,
    make_item: Callable[..., Item],
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
) -> None:
    # Nulling them at enqueue would destroy good data to make a failed retag
    # look tidier: _store leaves the tag columns alone on the failure path, so
    # a previously-good item keeps what it had.
    user = make_user()
    item = make_item(user_id=user.id, **JEANS)

    response = client.post(_url(item, "/retag"), headers=authorization(user))

    assert response.json()["category"] == "bottom"
    assert response.json()["display_name"] == "light blue straight jeans"


def test_retag_on_an_edited_item_is_409(
    client: TestClient,
    make_item: Callable[..., Item],
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
    queued: list[uuid.UUID],
) -> None:
    user = make_user()
    item = make_item(user_id=user.id, user_edited=True, **JEANS)

    response = client.post(_url(item, "/retag"), headers=authorization(user))

    assert response.status_code == 409
    assert response.json()["code"] == "item_edited"
    assert queued == []


def test_force_retags_an_edited_item(
    client: TestClient,
    make_item: Callable[..., Item],
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
) -> None:
    user = make_user()
    item = make_item(user_id=user.id, user_edited=True, **JEANS)

    response = client.post(_url(item, "/retag?force=true"), headers=authorization(user))

    assert response.status_code == 202


def test_a_forced_retag_does_not_clear_user_edited(
    client: TestClient,
    make_item: Callable[..., Item],
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
) -> None:
    # The accepted cost of never resetting the flag: a hand-corrected item
    # needs force on every later retag. 02 gives the column a second job —
    # measuring how often the AI was wrong — that a reset would destroy.
    user = make_user()
    item = make_item(user_id=user.id, user_edited=True, **JEANS)

    response = client.post(_url(item, "/retag?force=true"), headers=authorization(user))

    assert response.json()["user_edited"] is True


def test_retag_on_a_row_that_is_already_processing_is_allowed(
    client: TestClient,
    make_item: Callable[..., Item],
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
    queued: list[uuid.UUID],
) -> None:
    # Two tasks can then write the same row, last write winning, at a cost of
    # a fraction of a cent. Refusing would strand a row whose owning process
    # died for up to ten minutes, which is the failure a user actually meets.
    user = make_user()
    item = make_item(user_id=user.id)

    response = client.post(_url(item, "/retag"), headers=authorization(user))

    assert response.status_code == 202
    assert queued == [item.id]


def test_retagging_another_users_item_is_404(
    client: TestClient,
    make_item: Callable[..., Item],
    make_user: Callable[..., User],
    authorization: Callable[[User], dict[str, str]],
    queued: list[uuid.UUID],
) -> None:
    owner = make_user()
    intruder = make_user()
    item = make_item(user_id=owner.id, **JEANS)

    response = client.post(_url(item, "/retag"), headers=authorization(intruder))

    assert response.status_code == 404
    assert queued == []
