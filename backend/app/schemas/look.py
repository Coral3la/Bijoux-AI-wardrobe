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
from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints

from app.enums import Occasion
from app.schemas.item import ItemResponse


class LookSuggestRequest(BaseModel):
    """`04-API-SPEC.md`'s body, minus the four fields that have no task yet.

    `extra="forbid"` is `ItemUpdate`'s reasoning on a different body:
    `anchor_item_id`, `locked_item_ids`, `exclude_item_ids` and `replace_role`
    arrive at 2.10 and 2.11, and until then a request carrying one is refused
    rather than quietly ignored. A dropped anchor is a look that failed to build
    around the garment the user is holding, reported as a success.
    """

    model_config = ConfigDict(extra="forbid")

    occasion: Occasion
    date: date
    include_outerwear: bool | None = None
    # Stripped but not length-checked: an empty note is falsy, so the prompt
    # omits the line, and a blank one is not worth a 422 to a user who tabbed
    # through the field.
    notes: Annotated[str, StringConstraints(strip_whitespace=True)] | None = None


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
