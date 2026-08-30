"""The wire shapes of the four `/looks` endpoints.

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

`feedback` arrived at 3.3 and `worn_at` arrives here at 3.4 — the
three-commits-over-one-shape churn `DECISIONS.md` 182 accepted on purpose,
now spent in full. Nothing in Stage 4 adds a fourth.

**`feedback` is `Literal[-1, 1]`, not `Literal[FEEDBACK_UP, FEEDBACK_DOWN]`**,
which is what 3.1 said this task would write and which does not type-check:
PEP 586 admits literal values only, and `Final` does not exempt a name —
`error: Parameter 1 of Literal[...] is invalid`. Pydantic accepts the spelling
happily at runtime, so this is a `mypy` finding rather than a broken import.
The two constants are still the single definition; what changed is that a
**test** compares `get_args` against them instead of the compiler.
`tests/unit/test_look_schemas.py`, and `DECISIONS.md` 181 is corrected.

**Five columns are nullable and typed non-null here**, which is not a new claim:
`title`, `occasion`, `reasoning` and `weather_note` were already non-null on
`SuggestedLook`, and `GET /looks` reads back rows that only `_persist` can have
written — it writes all five on every path. The reliance is on there being one
writer, and it is named here because the next writer is Stage 4's packing run.
"""

import uuid
from datetime import date
from typing import Annotated, Literal, Self

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
    # `None` is a real state and the commonest one: a look nobody has rated.
    # 3.5 counts rated looks and needs it to stay distinguishable from a
    # neutral score, which is why the column has no server default (181).
    feedback: Literal[-1, 1] | None
    # The day this look was **most recently** worn, which is not the same claim
    # as any of its items' `last_worn_at`: one column holds one date, so wearing
    # the same look on a second day overwrites this, while each garment keeps
    # the latest day it was worn in *any* look. `DECISIONS.md` 184.
    worn_at: date | None


class LookSuggestResponse(BaseModel):
    looks: list[LookResponse]
    missing_pieces: list[MissingPieceResponse]
    message: str


class LookListResponse(BaseModel):
    looks: list[LookResponse]
    total: int


# The fields whose `NULL` is not a state any screen can render. `feedback` is
# deliberately absent: see the validator below.
_UNCLEARABLE = ("is_saved", "title")


class LookWearRequest(BaseModel):
    """`POST /looks/{id}/wear`, whose whole body is one required date.

    Required rather than defaulted to the server's today: the button that sends
    it is in a browser, and a browser east of UTC calls a day by a name the
    server would not. The client owns the calendar it is standing in, and this
    endpoint records what it is told.

    **No upper bound, deliberately.** A future date reads as nonsense and is
    still not refused: `todayInLocalTime()` in the browser is routinely the
    server's tomorrow, so a strict check would be a `422` that a *correct*
    client provokes by being east of Greenwich — which is the one thing
    `CONVENTIONS.md` says a validation error must never be. The column is
    descriptive rather than a claim about time. `DECISIONS.md` 184.
    """

    model_config = ConfigDict(extra="forbid")

    date: date


class LookUpdate(BaseModel):
    """`PATCH /looks/{id}`, carrying all three of `04-API-SPEC.md`'s keys.

    `extra="forbid"` is `ItemUpdate`'s and `LookSuggestRequest`'s reasoning
    unchanged: a dropped key is an instruction the user gave and the row did not
    obey, reported as a success.

    **One of the three can be cleared and two cannot**, which is the whole of
    `_no_clearing_what_has_no_empty_state` below.

    `title` cannot be cleared. The column stays nullable — the model writes one
    on every row and a future writer may not — but the API offers no way back
    to `NULL`, because an empty heading is not a state any screen draws. Same
    `StringConstraints` spelling as `ItemUpdate.display_name`, and for the same
    reason: `Field(strip_whitespace=True)` silently does nothing (072).
    """

    model_config = ConfigDict(extra="forbid")

    is_saved: bool | None = None
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)] | None = None
    feedback: Literal[-1, 1] | None = None

    @model_validator(mode="after")
    def _no_clearing_what_has_no_empty_state(self) -> Self:
        """`null` clears `feedback` and is refused on the other two.

        Every field is typed optional so that any may be left out, which is what
        `exclude_unset` reads in the route. That spelling also admits an
        explicit `null`, and the three columns answer it differently:

        - `is_saved` is `NOT NULL`, so `null` reaches Postgres as an
          `IntegrityError` and a `500` with no `code`.
        - `title` would take it and leave the card with an empty heading.
        - `feedback` **should** take it. `NULL` is unrated, which is the state
          every look starts in and the one 3.5 counts against — so a mis-tapped
          thumb that could not be taken back would permanently change what the
          stylist is told about this user.

        Narrowed at 3.3. Until then this refused a `null` on any field, which
        was right for the two fields that existed and would have been wrong for
        this one by inheritance rather than by decision.
        """
        cleared = [
            name
            for name in _UNCLEARABLE
            if name in self.model_fields_set and getattr(self, name) is None
        ]
        if cleared:
            raise ValueError(f"{', '.join(sorted(cleared))}: cannot be cleared, only changed")
        return self
