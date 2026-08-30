"""The wardrobe and the weather in, one outfit out. The project's second door
to OpenAI.

`suggest_looks` assembles the three AI-free pieces Stage 2 built before it —
`build_rule` (2.1), the profile columns (2.2) and `serialize_wardrobe` (2.3) —
into the two messages `03-AI-CONTRACTS.md` specifies, and returns the model's
answer parsed and **unjudged**.

`validate_look_response` is what judges it — `03`'s validation table, the eight
of its nine rules that have a field to read at Stage 2, run in the documented
order against the wardrobe that was actually sent — in seven calls, because
rule 3 became one slot of rule 9's table at 2.11b. It calls nothing, raises
nothing and owns no loop: it returns a verdict beside the normalised response,
and 2.7 decides whether to spend the one retry through `correction=` or to
answer `502 stylist_failed`. That is 1.2b's split between `tag_item` and
`validate_tags` with the retry one seam further out, because re-calling the
stylist takes the whole request rather than one extra argument.

Pure with respect to the request: it holds no `Session` and reads no `Settings`
beyond the model pin and the fake flag, so 2.7 can decide *what* wardrobe the
stylist sees — `ready`-only, `is_archived`, and the swimwear/sleepwear exclusion
once that vocabulary exists (`AUDITS.md` O-21).

**What escapes, measured against openai 2.52.0 rather than read from its
documentation** — the practice `DECISIONS.md` 044 established against
Cloudinary's own exception base class, owed to this module since then and paid
here. `OpenAIError` covers less than it looks: a `200` whose body is not JSON raises
`json.JSONDecodeError` from inside the SDK, a `200` carrying JSON of the wrong
shape returns a `ChatCompletion` with `choices=None`, and a `200` with a
`text/html` body makes `create()` return a **`str`**. None of the three is an
`OpenAIError`, and all three would otherwise surface in a route as
`TypeError`/`AttributeError`. They are read here into the one `ValueError` this
module documents, so 2.7 catches two things — no usable answer, or a provider
exception — and not five.
"""

import json
import logging
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any, Final

from openai import AsyncOpenAI
from openai.types.chat import (
    ChatCompletionMessageParam,
    ChatCompletionSystemMessageParam,
    ChatCompletionUserMessageParam,
)
from openai.types.shared_params.response_format_json_schema import JSONSchema

from app.core.config import settings
from app.enums import Category, Layer
from app.schemas.item import ItemResponse
from app.services.serializer import serialize_wardrobe
from app.services.weather import requires_outerwear

logger = logging.getLogger(__name__)

PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "stylist_system.md"

# Read once at import, as `03-AI-CONTRACTS.md` requires of every prompt. Unlike
# the vision prompt there is no `{{VOCABULARY}}` to render: this one names no
# enum member, so the file is the prompt and nothing generates part of it. That
# is also why it carries no version constant — `PROMPT_VERSION` exists in
# `vision.py` because 1.11 mines it against a golden set, and nothing reads a
# stylist equivalent: no column, no task.
SYSTEM_PROMPT: Final = PROMPT_PATH.read_text(encoding="utf-8")

_LOOK_PROPERTIES: dict[str, Any] = {
    "occasion": {"type": "string"},
    "title": {"type": "string"},
    "item_ids": {"type": "array", "items": {"type": "string"}},
    "reasoning": {"type": "string"},
    "weather_note": {"type": "string"},
}

# `category` is a plain string rather than the seven `Category` members. It is
# display text — 2.9 renders the description, nothing branches on it — and the
# vocabulary is about to gain two members (O-21), so constraining it here would
# narrow a contract on behalf of a reader that does not exist.
_MISSING_PIECE_PROPERTIES: dict[str, Any] = {
    "category": {"type": "string"},
    "description": {"type": "string"},
    "reason": {"type": "string"},
}


def _object(properties: dict[str, Any]) -> dict[str, Any]:
    # Strict mode rejects a schema whose `required` differs from its properties,
    # so it is derived rather than restated — `VISION_SCHEMA`'s rule, which is
    # the reason a forgotten edit there is impossible rather than merely
    # unlikely.
    return {
        "type": "object",
        "additionalProperties": False,
        "required": list(properties),
        "properties": properties,
    }


# Single-day only. `packing_list` and its `by_category` map are **not** built
# here: packing is Stage 4's headline feature and its schema is designed beside
# the trip user message and the reuse arithmetic, not guessed now as a field
# that would be null on every call this project makes for two stages.
# `03-AI-CONTRACTS.md` says so in the same words.
#
# `confidence`, `look_id` and `day` are struck from `03`'s look object rather
# than deferred: none has a column, a renderer or a task, and in strict mode
# every property is one the model must produce on every call. `AUDITS.md` O-9
# asked for that decision before this schema existed; `DECISIONS.md` 086 refused
# the vision `confidence` a branch on the same evidence.
#
# `day` survived O-9 at 2.4 and lost the same argument at 2.5, on a measurement
# rather than on principle: the one live call answered `"day": 14` for a request
# dated 2026-03-14 while `USE_FAKE_AI` answered `1`, so the model and the fake
# disagreed about what the field meant and nothing read either. `02-DATA-MODEL.md`
# gives a look `for_date`, not a day number, so no stage has a column for it.
# Stage 4 reintroduces it beside the trip schema that needs it. `AUDITS.md` O-24,
# `DECISIONS.md` 163.
#
# No `minItems` anywhere. It is not verified against this pin, and "at least one
# look" is rule 4 of `03`'s validation table, which is 2.5's.
STYLIST_SCHEMA: JSONSchema = {
    "name": "outfit_recommendation",
    "strict": True,
    "schema": _object(
        {
            "looks": {"type": "array", "items": _object(_LOOK_PROPERTIES)},
            "missing_pieces": {"type": "array", "items": _object(_MISSING_PIECE_PROPERTIES)},
            "message": {"type": "string"},
        }
    ),
}

# `03-AI-CONTRACTS.md`'s wording, the same sentence `vision.py` sends and
# deliberately not imported from it: the two contracts are independent, and a
# shared constant would make a change to one prompt's retry a silent change to
# the other's.
_CORRECTION: Final = "Your previous response was invalid: {reason}. Correct it."

# `03-AI-CONTRACTS.md`'s anchored block, transcribed with its own line breaks.
# It is printed after `Build 1 look.` rather than inside the REQUEST block, for
# the reason the outerwear line sits after the weather rule: it constrains
# every instruction above it, and a reader — human or model — takes the later
# of two conflicting instructions as the operative one.
_ANCHOR_BLOCK: Final = (
    "ANCHOR: {anchor_id}\n"
    "This item MUST appear in the look. Build the rest of the outfit around it.\n"
    "If it cannot work for this occasion or weather, still include it and\n"
    "explain the tension in `reasoning`."
)

# `03-AI-CONTRACTS.md`'s swap block, in three pieces because two of its four
# lines depend on a field that can be absent. The role line is omitted with
# `replace_role` and the rejection line with `exclude_item_ids`, which is
# `_outerwear_line`'s rule applied again: a line printed about a field the user
# did not send is an instruction nobody gave.
_LOCKED_BLOCK: Final = "LOCKED: {locked_ids}\nThese items MUST appear unchanged."
_REPLACE_LINE: Final = "Replace only the {role} with a different option from the wardrobe."
# Transcribed with `03`'s singular, which is what one tap sends. The ids are
# joined the way LOCKED's are, so a second swap of the same role reads as a
# longer list rather than as a second sentence.
_REJECTED_LINE: Final = "Do not return the previously rejected item {excluded_ids}."

# The two categories a dress replaces. Read by rule 9, which refuses a dress
# beside either, and by the fake, which must not build one.
_SEPARATES: Final = frozenset({Category.TOP, Category.BOTTOM})


@dataclass(frozen=True, slots=True)
class StylistContext:
    """Everything about the request that is not the wardrobe.

    Built by 2.7 from the request body, the user's row and the forecast, so that
    this module holds no `Session` and no clock: `forecast_summary` and
    `weather_rule` arrive already computed by `services/weather.py`, which is
    what keeps the weather behaviour a pure function of three numbers
    (`DECISIONS.md` 004).

    `include_outerwear` is three-state on purpose — `True` forces a coat,
    `False` forbids one, `None` leaves the weather rule in charge — and it is
    `04-API-SPEC.md`'s spelling. `01-ARCHITECTURE.md` called the same field
    `wants_outerwear`, corrected in this commit against the authoritative
    document.

    `anchor_id` is a `short_id`, not the UUID `POST /looks/suggest` receives.
    The wire carries the row's UUID (`04-API-SPEC.md` keeps `short_id` out of
    the client's hands) and 2.7 resolves it against the wardrobe it is about to
    send, so this module still sees only the identifiers it prints.
    `locked_ids` and `excluded_ids` are the same substitution, one field along.

    `replace_role` is `str` rather than the `Role` the request schema enforces,
    for `occasion`'s reason: this module prints the word and never branches on
    it, and typing it here would make a prompt builder import a wire
    vocabulary to interpolate a string.
    """

    date: date
    occasion: str
    forecast_summary: str
    weather_rule: str
    notes: str | None = None
    include_outerwear: bool | None = None
    anchor_id: str | None = None
    locked_ids: tuple[str, ...] = ()
    excluded_ids: tuple[str, ...] = ()
    replace_role: str | None = None
    height_cm: int | None = None
    style_notes: str | None = None
    preferences: str | None = None


@dataclass(frozen=True, slots=True)
class MissingPiece:
    category: str
    description: str
    reason: str


@dataclass(frozen=True, slots=True)
class Look:
    occasion: str
    title: str
    item_ids: tuple[str, ...]
    reasoning: str
    weather_note: str


@dataclass(frozen=True, slots=True)
class StylistResponse:
    """The model's answer, parsed and not yet judged.

    Frozen slotted dataclasses rather than Pydantic models, following
    `ItemTags` at `DECISIONS.md` 086: Pydantic is this project's wire-body type
    and the wire body for a look is 2.7's *hydrated* shape, where `item_ids`
    have become full items. A Pydantic model here would validate the same shape
    a second time under rules that are not the schema's.
    """

    looks: tuple[Look, ...]
    missing_pieces: tuple[MissingPiece, ...]
    message: str


@lru_cache(maxsize=1)
def _client() -> AsyncOpenAI:
    """Built on first use, never at import — `DECISIONS.md` 079's reasoning,
    which is unchanged here: `AsyncOpenAI(api_key="")` raises in the
    constructor, `OPENAI_API_KEY` is empty in CI, and this module is on the
    import path to `app.main` from 2.7.

    Its own client rather than `vision._client`, so the two contracts can be
    given different timeouts or pins without touching each other. The cost is
    that `tests/conftest.py`'s no-live-OpenAI guard has to name both doors, and
    it now does.
    """
    return AsyncOpenAI(
        api_key=settings.OPENAI_API_KEY,
        timeout=settings.OPENAI_TIMEOUT_SECONDS,
    )


def _profile_block(context: StylistContext) -> str:
    """`03`'s two-sentence profile line, with either half dropped when the
    column is null.

    The whole block is omitted rather than rendered empty when both are: a
    heading followed by nothing tells the model a profile exists and is blank,
    which is not what a user who has never opened the profile screen means.
    `AUDITS.md` O-6 closed the mechanism at 2.2 and recorded that in practice
    these two columns are usually still empty.
    """
    sentences = []
    if context.height_cm is not None:
        sentences.append(f"Height: {context.height_cm} cm.")
    if context.style_notes:
        sentences.append(f"Preferences: {context.style_notes}")
    if not sentences:
        return ""
    return "USER PROFILE:\n" + " ".join(sentences) + "\n\n"


def _preferences_block(context: StylistContext) -> str:
    if context.preferences is None:
        return ""
    return context.preferences + "\n\n"


def _outerwear_line(include_outerwear: bool | None) -> str:
    if include_outerwear is None:
        return ""
    if include_outerwear:
        return "Outerwear: the user has asked for outerwear. Include one.\n"
    return "Outerwear: the user has asked for no outerwear. Include none.\n"


def _locked_block(context: StylistContext) -> str:
    block = _LOCKED_BLOCK.format(locked_ids=", ".join(context.locked_ids))
    if context.replace_role is not None:
        block += "\n" + _REPLACE_LINE.format(role=context.replace_role)
    if context.excluded_ids:
        block += "\n" + _REJECTED_LINE.format(excluded_ids=", ".join(context.excluded_ids))
    return block


def _user_message(wardrobe: Sequence[ItemResponse], context: StylistContext) -> str:
    """`03-AI-CONTRACTS.md`'s user message, single-day block.

    The outerwear preference is printed **after** the weather rule and not
    beside the occasion, because it overrides that rule and a reader — human or
    model — takes the later of two conflicting instructions as the operative
    one. The system prompt says which wins in words; this puts them in that
    order on the page as well.
    """
    request = f"REQUEST:\nDate: {context.date.isoformat()}\nOccasion: {context.occasion}\n"
    if context.notes:
        request += f"Notes: {context.notes}\n"
    request += (
        f"Weather: {context.forecast_summary}\n"
        f"Weather rule: {context.weather_rule}\n"
        f"{_outerwear_line(context.include_outerwear)}"
        f"Build 1 look."
    )
    if context.anchor_id is not None:
        request += "\n\n" + _ANCHOR_BLOCK.format(anchor_id=context.anchor_id)
    # After the anchor, for the reason the anchor is after `Build 1 look.`: the
    # locks are the narrowest instruction in the message, and the later of two
    # conflicting ones is the operative one. In practice the two never arrive
    # together — the ↻ badge sends no anchor, because every item it keeps is
    # locked anyway and an anchor on the swapped tile would set rule 7 against
    # rule 8.
    if context.locked_ids:
        request += "\n\n" + _locked_block(context)
    return (
        f"WARDROBE ({len(wardrobe)} items):\n"
        f"{serialize_wardrobe(wardrobe)}\n\n"
        f"{_profile_block(context)}"
        f"{_preferences_block(context)}"
        f"{request}"
    )


def _first(wardrobe: Sequence[ItemResponse], category: Category) -> ItemResponse | None:
    return next((item for item in wardrobe if item.category == category), None)


def _fake_items(wardrobe: Sequence[ItemResponse], context: StylistContext) -> list[ItemResponse]:
    """The placeholder's picks: shoes, then a top and a bottom or a dress.

    Four of the request's fields change the answer rather than decorate it, and
    the reason is the same each time: a fake that cannot satisfy the rule the
    request has just switched on answers a look the validator rejects twice, so
    every `USE_FAKE_AI` request carrying that field would be a `502` — the
    opposite of what the flag exists for (`DECISIONS.md` 159). The anchor
    displaces the pick of its own category and leads the list, which is rule 7.
    The locked items are all kept and displace the picks that share a category
    with them, and an excluded id is never picked at all, which is rule 8. A
    dress already in the look is not joined by a top and a bottom, and half a
    pair is not joined by a dress, which is rule 9 — the clause added at 2.11b,
    when generalising the rule turned every anchored or locked dress under the
    flag into a `502`.
    """
    excluded = frozenset(context.excluded_ids)
    locked_ids = frozenset(context.locked_ids)
    # Locks come off the whole wardrobe and the picks off what is left, so a
    # request that locks and excludes one id keeps it: both readings answer a
    # look the validator rejects, and this is the one that says out loud which
    # instruction won.
    locked = [item for item in wardrobe if item.short_id in locked_ids]
    available = [item for item in wardrobe if item.short_id not in excluded]

    anchor = next((item for item in available if item.short_id == context.anchor_id), None)
    # What the request has already put in the look, which decides what is left
    # to pick rather than merely what to filter out afterwards. Rule 9 is why:
    # a dress the user anchored or locked cannot be joined by the pair, and
    # half a pair cannot be joined by a dress.
    committed = {item.category for item in (*locked, anchor) if item is not None}

    pair: list[ItemResponse | None]
    if Category.DRESS in committed:
        pair = []
    elif committed & _SEPARATES:
        pair = [_first(available, Category.TOP), _first(available, Category.BOTTOM)]
    else:
        top = _first(available, Category.TOP)
        bottom = _first(available, Category.BOTTOM)
        pair = [top, bottom] if top and bottom else [_first(available, Category.DRESS)]

    chosen = [item for item in [_first(available, Category.SHOES), *pair] if item is not None]

    if anchor is not None:
        chosen = [anchor, *(item for item in chosen if item.category is not anchor.category)]

    held = {item.category for item in locked}
    return [*locked, *(item for item in chosen if item.category not in held)]


def _fake_response(wardrobe: Sequence[ItemResponse], context: StylistContext) -> StylistResponse:
    """The `USE_FAKE_AI` answer, built from the wardrobe it was handed.

    `STAGE-2` 2.4 says "a recorded fixture" and `06-TESTING-STRATEGY.md` says
    fixtures are real recorded responses. **Neither is achievable here and the
    reason is arithmetic, not preference:** `short_id`s are generated per row by
    `scripts/seed_demo.py`, so they differ on every seed, and a fixture with
    literal ids would fail 2.5's rule 1 — the hallucination guard — on every
    call. The `USE_FAKE_AI` path exists to make E2E journeys 6 and 7
    deterministic, and a fake that can only ever produce a `502` does the
    opposite. `DECISIONS.md` 159.

    Deterministic and deliberately not clever: the first shoes, then the first
    top and bottom, falling back to the first dress when the wardrobe has no
    pair, with the anchor and the locks displacing whichever of them share a
    category and the excluded ids never picked at all. No
    styling, no weather, no ordering by anything. The text says out
    loud that it is a placeholder, which is `DECISIONS.md` 081's mitigation for
    the same rule broken the same way on the vision side — a demo accidentally
    run with the flag on is visible on screen rather than passing for a look.
    """
    return StylistResponse(
        looks=(
            Look(
                occasion=context.occasion,
                title="Placeholder look",
                item_ids=tuple(item.short_id for item in _fake_items(wardrobe, context)),
                reasoning=(
                    "Placeholder response: USE_FAKE_AI is on, so no model was called. "
                    "These items were picked by category, not styled."
                ),
                weather_note="Placeholder response: the weather rule was not applied.",
            ),
        ),
        missing_pieces=(),
        message="Placeholder response from USE_FAKE_AI. No model was called.",
    )


def _content(completion: Any) -> str:
    """The one string the model sent back, or `ValueError`.

    Every check here fires on something measured against openai 2.52.0, not on
    something imagined — see the module docstring. `getattr` rather than
    `completion.choices` because in the `text/html` case `completion` is a
    `str`, which the SDK's own type annotation says is impossible.
    """
    choices = getattr(completion, "choices", None)
    if not choices:
        logger.warning(
            "Stylist model returned no choices", extra={"answer_type": type(completion).__name__}
        )
        raise ValueError("The stylist model returned no choices.")

    content = choices[0].message.content
    if content is None:
        logger.warning(
            "Stylist model returned no content",
            extra={"finish_reason": choices[0].finish_reason},
        )
        raise ValueError("The stylist model returned no content.")
    return str(content)


def _build(payload: Any) -> StylistResponse:
    """The parsed JSON into the typed answer.

    Shape is `STYLIST_SCHEMA`'s guarantee and is not re-checked field by field;
    what this catches is an answer that is not that shape **at all**, which the
    measured leniencies above make reachable. Semantics — every id real, shoes
    present, no two outer layers — are `validate_look_response`'s below, and so
    is normalising the case of a returned id (`DECISIONS.md` 156).
    """
    try:
        return StylistResponse(
            looks=tuple(
                Look(
                    occasion=look["occasion"],
                    title=look["title"],
                    item_ids=tuple(look["item_ids"]),
                    reasoning=look["reasoning"],
                    weather_note=look["weather_note"],
                )
                for look in payload["looks"]
            ),
            missing_pieces=tuple(
                MissingPiece(
                    category=piece["category"],
                    description=piece["description"],
                    reason=piece["reason"],
                )
                for piece in payload["missing_pieces"]
            ),
            message=payload["message"],
        )
    except (KeyError, TypeError, IndexError) as exc:
        raise ValueError(f"The stylist model's answer was not the documented shape: {exc}") from exc


async def suggest_looks(
    wardrobe: Sequence[ItemResponse],
    context: StylistContext,
    correction: str | None = None,
) -> StylistResponse:
    """One wardrobe and one request in, one unjudged recommendation out.

    `correction` is the violation 2.5 found in the previous answer, and it is
    the whole of the retry: same wardrobe, same schema, one more instruction.
    Calling this twice is 2.5's decision, not this function's.

    Raises `ValueError` when no usable answer arrived — no choices, no content,
    unparseable JSON, or JSON that is not the documented shape. Lets the
    provider's own exceptions escape untouched, so 2.7 can tell "OpenAI did not
    answer" apart from "OpenAI answered nonsense" the way 1.3 does on the vision
    side (`DECISIONS.md` 086).
    """
    if settings.USE_FAKE_AI:
        return _fake_response(wardrobe, context)

    content: list[Any] = [{"type": "text", "text": _user_message(wardrobe, context)}]
    if correction is not None:
        content.append({"type": "text", "text": _CORRECTION.format(reason=correction)})

    messages: list[ChatCompletionMessageParam] = [
        ChatCompletionSystemMessageParam(role="system", content=SYSTEM_PROMPT),
        ChatCompletionUserMessageParam(role="user", content=content),
    ]

    completion = await _client().chat.completions.create(
        model=settings.OPENAI_STYLIST_MODEL,
        messages=messages,
        response_format={"type": "json_schema", "json_schema": STYLIST_SCHEMA},
    )

    # json.JSONDecodeError subclasses ValueError, so a truncated answer and an
    # empty one are one exception type for the caller to catch.
    return _build(json.loads(_content(completion)))


@dataclass(frozen=True, slots=True)
class LookValidation:
    """The verdict, and the response the caller should go on to use.

    `response` is normalised rather than the object that went in: the model's
    ids are upper-cased before rule 1 looks them up (`DECISIONS.md` 156), and
    2.7 persists and hydrates from this field so an id cannot be case-shifted in
    one place and not another. `violation` is the first rule that failed, worded
    for the model, or `None`.
    """

    response: StylistResponse
    violation: str | None

    @property
    def ok(self) -> bool:
        return self.violation is None


def _normalised(response: StylistResponse) -> StylistResponse:
    """`.upper()` on every returned id, and nothing else.

    `app/core/short_id.py`'s alphabet is upper-case only, so case is the one
    difference between what a model might send and what a row holds that is not
    a hallucination. It is deliberately not `.strip()` as well: nothing has been
    measured that pads an id, and a guess about whitespace would be code no test
    can justify. Transliteration is not an option at all — the alphabet drops
    *both* halves of every confusable pair, so a returned `0` maps to no legal
    character and is a hallucination rather than a typo.
    """
    return replace(
        response,
        looks=tuple(
            replace(look, item_ids=tuple(item_id.upper() for item_id in look.item_ids))
            for look in response.looks
        ),
    )


def _unknown_id(looks: tuple[Look, ...], known: Mapping[str, ItemResponse]) -> str | None:
    for look in looks:
        for item_id in look.item_ids:
            if item_id not in known:
                return f"unknown item id {item_id}; it is not in the wardrobe you were given"
    return None


def _incomplete(looks: tuple[Look, ...], known: Mapping[str, ItemResponse]) -> str | None:
    for look in looks:
        categories = {known[item_id].category for item_id in look.item_ids}
        if Category.SHOES not in categories:
            return "the look has no shoes"
        if Category.DRESS in categories:
            continue
        if not {Category.TOP, Category.BOTTOM} <= categories:
            return "the look has neither a top and a bottom nor a dress"
    return None


def _wrong_count(looks: tuple[Look, ...]) -> str | None:
    # `03`'s rule 4 is `len(looks) == expected_days`; a single-day request is a
    # trip of length one, so the expected count is 1 and is not a parameter until
    # Stage 4 has a request that can ask for another number.
    if len(looks) != 1:
        return f"you returned {len(looks)} looks and exactly 1 was requested"
    return None


def _missing_outerwear(
    looks: tuple[Look, ...], known: Mapping[str, ItemResponse], context: StylistContext
) -> str | None:
    """Rule 6, and the one narrowing `03`'s table does not print.

    It does not run when the user asked for no outerwear. `DECISIONS.md` 158
    gave an explicit `include_outerwear` precedence over the weather rule and
    the system prompt says so in words, so a look that obeyed the user at 12°C
    is correct — and enforcing the rule over it would spend the retry and then
    answer `502` to the one answer that did what it was told.
    """
    if context.include_outerwear is False:
        return None
    if not requires_outerwear(context.weather_rule):
        return None
    for look in looks:
        if not any(known[item_id].category is Category.OUTERWEAR for item_id in look.item_ids):
            return "the weather rule requires outerwear and the look contains none"
    return None


def _missing_anchor(looks: tuple[Look, ...], context: StylistContext) -> str | None:
    """Rule 7, and it needs no wardrobe to answer.

    `anchor_id` is a `short_id` read off a row, so it is upper-case by
    construction, and `_normalised` has already upper-cased the model's ids —
    which is the one way the two spellings could otherwise have disagreed.
    """
    if context.anchor_id is None:
        return None
    for look in looks:
        if context.anchor_id not in look.item_ids:
            return f"the look does not contain the anchored item {context.anchor_id}, and it must"
    return None


def _broken_lock(looks: tuple[Look, ...], context: StylistContext) -> str | None:
    """Rule 8, and like rule 7 it needs no wardrobe to answer.

    Both halves are gated on `locked_ids`, which is `03-AI-CONTRACTS.md`'s own
    wording — *when `locked_item_ids` were supplied, every one of them appears,
    and the rejected item does not*. An exclusion sent without locks is still
    printed to the model; what this declines to do is spend the retry and then
    a `502` enforcing it, on a request that locked nothing and therefore asked
    for a reroll rather than a swap.
    """
    if not context.locked_ids:
        return None
    for look in looks:
        for locked in context.locked_ids:
            if locked not in look.item_ids:
                return f"the look does not contain the locked item {locked}, and it must"
        for rejected in context.excluded_ids:
            if rejected in look.item_ids:
                return f"the look contains the rejected item {rejected}, and it must not"
    return None


@dataclass(frozen=True, slots=True)
class SlotRule:
    label: str
    limit: int
    holds: Callable[[ItemResponse], bool]


# Rule 9's table: what a person can wear one of at a time. A table rather than
# seven near-identical loops, because the rule is one sentence in `03` and the
# thing that varies between slots is which column names them.
#
# **`outer` is read by `layer` and the rest by `category`**, which is not an
# inconsistency but the two questions the vocabulary can answer. Rule 3 asked
# it of the layer — `LAYERS_BY_CATEGORY` admits `mid` for outerwear, so a
# cardigan under a coat is one outer layer and two coats are two — and this
# table absorbs that reading unchanged. The base top needs **both** columns,
# because `top` is the one category `LAYERS_BY_CATEGORY` answers `None` for: a
# top is legitimately `base` or `mid`, so `category` alone would refuse the
# overshirt the prompt allows and `layer` alone would refuse the jeans.
#
# `accessories` is the one slot with a limit above 1, and it is the system
# prompt's own number — "add a bag and up to two accessories".
SLOT_RULES: Final[tuple[SlotRule, ...]] = (
    SlotRule("outer layer items", 1, lambda item: item.layer is Layer.OUTER),
    SlotRule(
        "base-layer tops",
        1,
        lambda item: item.category is Category.TOP and item.layer is Layer.BASE,
    ),
    SlotRule("bottoms", 1, lambda item: item.category is Category.BOTTOM),
    SlotRule("dresses", 1, lambda item: item.category is Category.DRESS),
    SlotRule("pairs of shoes", 1, lambda item: item.category is Category.SHOES),
    SlotRule("bags", 1, lambda item: item.category is Category.BAG),
    SlotRule("accessories", 2, lambda item: item.category is Category.ACCESSORY),
)


def _slot_conflict(looks: tuple[Look, ...], known: Mapping[str, ItemResponse]) -> str | None:
    """Rule 9: one item per slot, and a dress instead of separates.

    Rule 2 says a look is not missing anything; this says it does not wear
    anything twice. The two halves are one rule because they are one question
    asked of one look — *can a person put this on?* — and a dress beside a pair
    of jeans is the same answer as two pairs of jeans.

    It absorbs rule 3, which was this rule with one slot in it. The number
    stays in `03`'s table: eight documents, a test and three code comments name
    it, and renumbering to buy nothing is how a reference becomes wrong.
    """
    for look in looks:
        for slot in SLOT_RULES:
            worn = [item_id for item_id in look.item_ids if slot.holds(known[item_id])]
            if len(worn) > slot.limit:
                named = ", ".join(worn[: slot.limit + 1])
                return (
                    f"the look contains {len(worn)} {slot.label} "
                    f"and may contain at most {slot.limit}: {named}"
                )

        if any(known[item_id].category is Category.DRESS for item_id in look.item_ids):
            separate = next(
                (item_id for item_id in look.item_ids if known[item_id].category in _SEPARATES),
                None,
            )
            if separate is not None:
                return (
                    f"the look contains a dress and the separate item {separate}: "
                    "a dress is worn instead of a top and a bottom, not beside one"
                )
    return None


def _violation(
    response: StylistResponse, wardrobe: Sequence[ItemResponse], context: StylistContext
) -> str | None:
    """`03`'s table, in `03`'s order, stopping at the first failure.

    The order is load-bearing rather than cosmetic. Rule 1 is what makes every
    later rule able to look an id up at all, so it runs first and returns before
    the rest can raise a `KeyError` on a hallucinated id. One violation rather
    than a list because it is a sentence sent back to the model, and one
    concrete instruction is likelier to be obeyed than five.

    Rule 5 is absent: it reads `packing_list.item_ids`, and `STYLIST_SCHEMA`
    carries no `packing_list` until Stage 4 designs it beside the trip message
    (`DECISIONS.md` 157). Rule 7 arrived with the anchor at 2.10, rule 8 with
    the swap at 2.11, and rule 9 at 2.11a, widened at 2.11b. **Rule 3 is not
    missing** — it is one slot of rule 9 since 2.11b, so the chain is seven
    calls for eight rules, and rule 9 runs last because it is last in the
    table, which is the only ordering this function claims.
    """
    known = {item.short_id: item for item in wardrobe}
    return (
        _unknown_id(response.looks, known)
        or _incomplete(response.looks, known)
        or _wrong_count(response.looks)
        or _missing_outerwear(response.looks, known, context)
        or _missing_anchor(response.looks, context)
        or _broken_lock(response.looks, context)
        or _slot_conflict(response.looks, known)
    )


def validate_look_response(
    response: StylistResponse,
    wardrobe: Sequence[ItemResponse],
    context: StylistContext,
) -> LookValidation:
    """One answer judged against the wardrobe it was built from.

    `wardrobe` is the sequence that was **sent** to the model, not every row the
    user owns. After 2.6a that is the narrower list — `ready`, not archived, no
    swimwear or sleepwear — and an id the model was never shown is a
    hallucination whether or not the garment is in the drawer.

    Calls nothing and raises nothing. The retry, the give-up log and
    `502 stylist_failed` are 2.7's, which is the only place that holds the
    request needed to ask the model a second time.
    """
    normalised = _normalised(response)
    violation = _violation(normalised, wardrobe, context)
    if violation is not None:
        logger.warning("Stylist response rejected", extra={"violation": violation})
    return LookValidation(response=normalised, violation=violation)
