"""The wire shapes of `POST /looks/suggest`.

The response is `03-AI-CONTRACTS.md`'s answer with one substitution:
`item_ids` become `items`, full `ItemResponse` objects hydrated from the
wardrobe the route already holds. `04-API-SPEC.md` calls that "hydrated to full
objects" and `06-TESTING-STRATEGY.md`'s stylist eval reads `.items` by name.

`SuggestedLook.id` is the row `POST /looks/suggest` persisted, not anything the
model produced — `look_id` was struck from the schema at 2.4 because the model
had no business inventing one. It is here because a look the user is looking at
has to be nameable: `PATCH /looks/{id}` at 3.2 is the heart button on this very
card, and without the id the client would have to re-fetch a list to find the
row it was just handed. `is_saved`, `feedback` and `worn_at` stay out — those
are Stage 3's columns and two of them do not exist yet. `DECISIONS.md` 172.
"""

import uuid
from datetime import date
from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.enums import Occasion, Role
from app.schemas.item import ItemResponse


class LookSuggestRequest(BaseModel):
    """`04-API-SPEC.md`'s body, whole for the first time since Stage 0.

    `extra="forbid"` is `ItemUpdate`'s reasoning on a different body, and what
    it now refuses is a misspelling rather than a field with no task: a dropped
    key is an instruction the user gave and the look did not obey, reported as
    a success.
    """

    model_config = ConfigDict(extra="forbid")

    occasion: Occasion
    date: date
    include_outerwear: bool | None = None
    # Stripped but not length-checked: an empty note is falsy, so the prompt
    # omits the line, and a blank one is not worth a 422 to a user who tabbed
    # through the field.
    notes: Annotated[str, StringConstraints(strip_whitespace=True)] | None = None
    # The row's UUID, not its `short_id`. `04-API-SPEC.md` keeps `short_id` out
    # of the client's hands entirely — "it exists only for the AI layer" — so
    # the route is what turns this into the id the prompt prints.
    anchor_item_id: uuid.UUID | None = None
    # The three swap fields. Row UUIDs again, for `anchor_item_id`'s reason —
    # `short_id` exists only for the AI layer, and the route is what turns
    # these into the ids the prompt prints.
    locked_item_ids: list[uuid.UUID] = Field(default_factory=list)
    exclude_item_ids: list[uuid.UUID] = Field(default_factory=list)
    replace_role: Role | None = None

    @model_validator(mode="after")
    def _replace_role_needs_locks(self) -> Self:
        """`04-API-SPEC.md`'s second `422`, and it stays `validation_error`.

        A role names which of the locked items may move, so it says nothing at
        all without them: the model would be told to replace the shoes and left
        free to replace everything else too. The ↻ badge always sends both, so
        this is a body no correct client can build — which is the line between
        this and `locked_unavailable`, the `422` a correct client provokes by
        tapping a garment that has since been archived.
        """
        if self.replace_role is not None and not self.locked_item_ids:
            raise ValueError("replace_role names which locked item to replace, so it needs locks")
        return self


class MissingPieceResponse(BaseModel):
    # `category` is a plain string, matching `STYLIST_SCHEMA`: it is display
    # text describing a garment the wardrobe does **not** contain, so it names
    # no row and cannot be validated against the vocabulary a row is tagged with.
    category: str
    description: str
    reason: str


class SuggestedLook(BaseModel):
    id: uuid.UUID
    occasion: Occasion
    title: str
    items: list[ItemResponse]
    reasoning: str
    weather_note: str


class LookSuggestResponse(BaseModel):
    looks: list[SuggestedLook]
    missing_pieces: list[MissingPieceResponse]
    message: str
