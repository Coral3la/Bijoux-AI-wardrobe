"""The wire shapes of the five `/sets` endpoints.

**One set object, answered by the three endpoints that answer a set.**
`04-API-SPEC.md` prints it once and `ItemSetResponse` is the whole of it:
`POST /sets`, `GET /sets/{set_id}` and `POST /sets/{set_id}/items` return
exactly this, and `DELETE /sets/{set_id}/items/{item_id}` returns it or nothing
at all. `DECISIONS.md` 034's rule, applied to a fifth resource.

**`items` is hydrated to the full `ItemResponse`**, not to ids and not to a
narrower projection. One shape for one resource again: the item detail screen
draws thumbnails of the other members, and a second item shape would be a
second thing to keep in step with `GET /items`. The list always holds at least
two elements — a set that would hold fewer does not exist — and it can hold an
**archived** one, because archiving a garment does not unmake the fact that it
was bought with another.

**Neither request model can express a set that is too small, and only one of
them tries.** `item_ids` carries `min_length=2` here, so *fewer than two* is a
`validation_error` from Pydantic and needs no code in the route; the
deduplication that has to happen before that count is meaningful is the
validator below. `ItemSetMemberRequest` has no such rule to state: it adds one
garment to a set that already satisfies the invariant.
"""

import datetime
import uuid
from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.schemas.item import ItemResponse


class ItemSetCreateRequest(BaseModel):
    """`POST /sets`'s body: a name nobody has to give, and two or more garments.

    `extra="forbid"`, as every request body in this API is: a dropped key is an
    instruction the user gave and the server did not obey, reported as a
    success.

    **The list is deduplicated before the count is checked**, which is
    `04-API-SPEC.md`'s wording exactly — `["a", "a"]` is a `422`
    `validation_error` naming `item_ids` and not a one-member set. Both halves
    are refusals rather than repairs: silently collapsing the duplicate would
    answer `201` to a request that asked for something this API cannot build,
    and no correct client can send either body, which is what makes this a
    request-shape rule in `POST /items/upload`'s sense (`DECISIONS.md` 048)
    rather than a code of its own.
    """

    model_config = ConfigDict(extra="forbid")

    # Stripped and non-empty when present, exactly as `display_name` is on
    # `ItemUpdate`: a name made of spaces is a set labelled with nothing, and
    # there is no rename to correct it with. Absent and `null` both mean the
    # set has no name, which is the ordinary case.
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)] | None = None
    item_ids: Annotated[list[uuid.UUID], Field(min_length=2)]

    @model_validator(mode="after")
    def _members_are_distinct(self) -> Self:
        if len(set(self.item_ids)) != len(self.item_ids):
            raise ValueError("item_ids: the same garment cannot be named twice")
        return self


class ItemSetMemberRequest(BaseModel):
    """`POST /sets/{set_id}/items`'s body: one garment.

    One id per request rather than a list, and `04-API-SPEC.md` gives the
    reason: the control that calls it picks one garment from the wardrobe, and
    a partial failure over a list would need a response shape this API has
    nowhere else.
    """

    model_config = ConfigDict(extra="forbid")

    item_id: uuid.UUID


class ItemSetResponse(BaseModel):
    """The set object, whole.

    `name` is `null` where the user gave none. `items` is in `GET /items`' own
    order — `created_at DESC, short_id` — so the set lists its garments the way
    the wardrobe does, and every element carries a `set_id` equal to this
    object's `id`.
    """

    id: uuid.UUID
    name: str | None
    items: list[ItemResponse]
    created_at: datetime.datetime
