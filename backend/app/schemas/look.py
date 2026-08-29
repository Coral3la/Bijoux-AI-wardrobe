"""The wire shapes of the three `/looks` endpoints.

A look on the wire is `03-AI-CONTRACTS.md`'s answer with one substitution:
`item_ids` become `items`, full `ItemResponse` objects. `04-API-SPEC.md` calls
that "hydrated to full objects" and `06-TESTING-STRATEGY.md`'s stylist eval
reads `.items` by name.

`LookResponse.id` is the row `POST /looks/suggest` persisted, not anything the
model produced — `look_id` was struck from the schema at 2.4 because the model
had no business inventing one. It is here because a look the user is looking at
has to be nameable: `PATCH /looks/{id}` is the heart button on this very card,
and without the id the client would have to re-fetch a list to find the row it
was just handed.

**This was `SuggestedLook` until 3.2, and the rename is the point.** `GET
/looks` and `PATCH /looks/{id}` return the same row as `POST /looks/suggest`,
and 3.3 and 3.4 both answer with it again — a second near-identical shape would
mean one row described two ways, with nothing keeping the descriptions in step.
The cost of one shape is that **suggest responses now carry `is_saved: false`**,
a field that endpoint's client had no use for; it is true of the row rather
than padding, which is what made it acceptable.

`feedback` and `worn_at` stay out. Both columns exist from migration `0004`,
and their readers are 3.3 and 3.4 — so this class changes in each of the next
two tasks, three commits over one shape. That churn was accepted deliberately
rather than pre-empted by adding fields now that no endpoint writes and no
screen draws. `DECISIONS.md` 182.

**Five columns are nullable and typed non-null here**, which is not a new claim:
`title`, `occasion`, `reasoning` and `weather_note` were already non-null on
`SuggestedLook`, and `GET /looks` reads back rows that only `_persist` can have
written — it writes all five on every path. The reliance is on there being one
writer, and it is named here because the next writer is Stage 4's packing run.
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


class LookResponse(BaseModel):
    id: uuid.UUID
    occasion: Occasion
    title: str
    items: list[ItemResponse]
    reasoning: str
    weather_note: str
    is_saved: bool


class LookSuggestResponse(BaseModel):
    looks: list[LookResponse]
    missing_pieces: list[MissingPieceResponse]
    message: str


class LookListResponse(BaseModel):
    looks: list[LookResponse]
    total: int


class LookUpdate(BaseModel):
    """`PATCH /looks/{id}`, with two of `04-API-SPEC.md`'s three keys.

    **`feedback` is 3.3's and sending it here is a `422`**, said out loud
    because `04`'s example body prints all three keys together and a reader
    would reasonably expect this to take them. `extra="forbid"` is
    `ItemUpdate`'s and `LookSuggestRequest`'s reasoning unchanged: a dropped key
    is an instruction the user gave and the row did not obey, reported as a
    success.

    `title` cannot be cleared. The column stays nullable — the model writes one
    on every row and a future writer may not — but the API offers no way back
    to `NULL`, because an empty heading is not a state any screen draws. Same
    `StringConstraints` spelling as `ItemUpdate.display_name`, and for the same
    reason: `Field(strip_whitespace=True)` silently does nothing (072).
    """

    model_config = ConfigDict(extra="forbid")

    is_saved: bool | None = None
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)] | None = None

    @model_validator(mode="after")
    def _neither_field_can_be_cleared(self) -> Self:
        """`None` means *omitted* on this body and never *clear it*.

        Both fields are typed optional so that either may be left out, which is
        what `exclude_unset` reads in the route. That spelling also admits an
        explicit `null`, and the two columns answer it differently and both
        badly: `is_saved` is `NOT NULL`, so `null` reaches Postgres as an
        `IntegrityError` and a `500` with no `code`; `title` would take it and
        leave the card with an empty heading. `ItemUpdate` types its fields the
        same way and means the opposite by them — there, clearing a tag is the
        point — so the difference is stated here rather than inferred.
        """
        cleared = [name for name in self.model_fields_set if getattr(self, name) is None]
        if cleared:
            raise ValueError(f"{', '.join(sorted(cleared))}: cannot be cleared, only changed")
        return self
