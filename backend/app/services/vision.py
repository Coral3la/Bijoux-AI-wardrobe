"""Image URL in, validated tags out.

The project's only path to OpenAI. `tag_item` sends the photograph and returns
the model's answer **unvalidated**; `validate_tags` reads
`enums.validate_tag_dict`'s report and decides between accepting a coercion,
one retry naming the violation, and `TaggingError` (`DECISIONS.md` 028). The
tag dict keeps the model's own key `confidence` throughout; the rename to the
`items.ai_confidence` column happens at persistence in 1.3.

Two failures, deliberately not merged. `TaggingError` means the model answered
and the answer could not be accepted. A `ValueError` or a provider exception
means no usable answer arrived at all — from the first call or from the retry,
which is allowed to escape rather than be relabelled. Task 1.3 catches both and
writes `failed` either way, and the two say different things in `error_message`.

Prompt, schema and validator take their vocabulary **and its category-dependent
rules** from `app/enums.py`, so none of the three can disagree with the other
two. `02-DATA-MODEL.md` remains authoritative over `enums.py` itself, by hand.

openai 2.x: `chat.completions.create` and `chat.completions.parse` are
top-level. Almost every Structured Outputs example online is written against
1.x's `client.beta.chat.completions.parse`, and `client.beta` still exists in
2.x, so the older shape looks current rather than superseded — see the pinned
majors section of `CONVENTIONS.md`. `.parse()` is not used here on purpose: it
builds a schema from a Pydantic model, and what task 1.1 verified is the schema
`03-AI-CONTRACTS.md` wrote down.
"""

import hashlib
import json
import logging
from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from openai import AsyncOpenAI
from openai.types.chat import (
    ChatCompletionMessageParam,
    ChatCompletionSystemMessageParam,
    ChatCompletionUserMessageParam,
)
from openai.types.shared_params.response_format_json_schema import JSONSchema

from app.core.config import settings
from app.enums import (
    FIELD_APPLIES_TO,
    LAYERS_BY_CATEGORY,
    REQUIRED_TAG_FIELDS,
    SUBCATEGORIES,
    VALUE_APPLIES_TO,
    Category,
    ColorPrimary,
    Fit,
    Layer,
    Length,
    Material,
    Pattern,
    Rise,
    TagIssue,
    TagValidation,
    validate_tag_dict,
)

logger = logging.getLogger(__name__)

PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "vision_system.md"
VOCABULARY_PLACEHOLDER = "{{VOCABULARY}}"

# The separator `02-DATA-MODEL.md` uses, so the rendered block and the document
# can be compared by eye. Roughly a hundred extra tokens per call against a
# comma; at this project's call volume that is a fraction of a cent in total,
# so legibility decides it rather than cost.
_SEPARATOR = " · "


def _categories(categories: frozenset[Category]) -> str:
    # Declaration order rather than set order: a frozenset iterates
    # unpredictably between processes, and a prompt that renders differently on
    # every boot cannot be versioned by hashing it.
    return _SEPARATOR.join(category.value for category in Category if category in categories)


def _field_rules(field: str) -> str:
    lines = [
        f"  {'applies to':<14} {_categories(FIELD_APPLIES_TO[field])} — null for any other category"
    ]
    narrowed = VALUE_APPLIES_TO.get(field, {})
    if narrowed:
        lines.append("  these words are narrower than the field:")
        lines += [
            f"  {value:<14} {_categories(categories)}" for value, categories in narrowed.items()
        ]
    return "\n".join(lines)


def _vocabulary_block() -> str:
    """The closed vocabulary and its category rules, rendered for the prompt.

    Load-bearing rather than belt-and-braces for exactly three fields. `fit`,
    `length` and `rise` are plain strings in the response schema — an
    out-of-vocabulary value there is coerced to null rather than retried, so
    constraining them in the schema would buy nothing (`03-AI-CONTRACTS.md`).
    That makes this block the **only** place the model ever learns what those
    three may contain. For every other field Structured Outputs enforces the
    list and this is reinforcement.

    The category rules are here for a second reason. Strict mode guarantees
    membership and nothing else, so `layer: "standalone"` on a top passes the
    schema perfectly and is caught only in Python — every such value used to be
    a silent coercion nobody learned from, which is half of what `DECISIONS.md`
    084 complained about. A prompt is not a guarantee (082), so this reinforces
    `validate_tag_dict` rather than replacing it.
    """
    subcategories = "\n".join(
        f"  {category.value:<14} {_SEPARATOR.join(subs)}"
        for category, subs in SUBCATEGORIES.items()
    )
    layers = "\n".join(
        f"  {category.value:<14} "
        f"{' or '.join(layer.value for layer in Layer if layer in rule.admits)}"
        for category, rule in LAYERS_BY_CATEGORY.items()
    )
    return f"""ALLOWED VALUES — use only these. Never invent a value.
An indented line under a field narrows it further.

category         {_SEPARATOR.join(Category.values())}

subcategory — must belong to the category given above
{subcategories}

fit              {_SEPARATOR.join(Fit.values())} — or null
{_field_rules("fit")}

length           {_SEPARATOR.join(Length.values())} — or null
{_field_rules("length")}

rise             {_SEPARATOR.join(Rise.values())} — or null
{_field_rules("rise")}

color_primary    {_SEPARATOR.join(ColorPrimary.values())}
color_secondary  any color_primary value — or null
pattern          {_SEPARATOR.join(Pattern.values())}
material         {_SEPARATOR.join(Material.values())}

layer            {_SEPARATOR.join(Layer.values())}
  each category takes only these:
{layers}"""


def _load_system_prompt() -> str:
    template = PROMPT_PATH.read_text(encoding="utf-8")
    if VOCABULARY_PLACEHOLDER not in template:
        # Loud at import rather than silent at call time: a prompt missing its
        # vocabulary still produces plausible-looking tags, and the three
        # unconstrained fields are the ones that would quietly degrade.
        raise ValueError(
            f"{PROMPT_PATH.name} does not contain {VOCABULARY_PLACEHOLDER}; "
            "the closed vocabulary would never reach the model."
        )
    return template.replace(VOCABULARY_PLACEHOLDER, _vocabulary_block())


def _prompt_version(prompt: str) -> str:
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:12]


SYSTEM_PROMPT = _load_system_prompt()

# Hashed rather than hand-bumped. Task 1.11 measures accuracy against a prompt
# that has to be identifiable afterwards, and half this prompt is generated from
# `enums.py` — so a version someone remembers to increment is wrong the moment a
# table moves without the constant, and the error surfaces as a baseline
# measured against a prompt nobody can reconstruct. This covers the rendered
# vocabulary because it is taken after the render.
PROMPT_VERSION = _prompt_version(SYSTEM_PROMPT)

_COLORS = ColorPrimary.values()

# `subcategory` is a plain string because its valid values depend on `category`,
# which JSON Schema cannot express cleanly. `fit`, `length` and `rise` are plain
# strings for a different reason: an out-of-vocabulary value there is coerced to
# null rather than retried, so constraining them here would buy nothing. All
# four are validated in Python. `03-AI-CONTRACTS.md`.
_PROPERTIES: dict[str, Any] = {
    "category": {"type": "string", "enum": Category.values()},
    "subcategory": {"type": "string"},
    "fit": {"type": ["string", "null"]},
    "length": {"type": ["string", "null"]},
    "rise": {"type": ["string", "null"]},
    "color_primary": {"type": "string", "enum": _COLORS},
    # A nullable enum adds "null" to the *type union* and leaves the enum array
    # alone. That contradicts plain JSON Schema, under which a null value would
    # fail the enum constraint, and it is the vendor's documented pattern for
    # strict mode. Moving null into the array is the obvious tidy and is wrong.
    "color_secondary": {"type": ["string", "null"], "enum": _COLORS},
    "pattern": {"type": "string", "enum": Pattern.values()},
    "material": {"type": "string", "enum": Material.values()},
    "formality": {"type": "integer", "minimum": 1, "maximum": 5},
    "warmth": {"type": "integer", "minimum": 1, "maximum": 5},
    "layer": {"type": "string", "enum": Layer.values()},
    "water_resistant": {"type": "boolean"},
    "display_name": {"type": "string"},
    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
}

# Typed as the SDK's own TypedDict rather than dict[str, Any], so mypy checks
# the envelope — `name`, `strict`, `schema` — against what the API expects
# instead of only at the call site.
VISION_SCHEMA: JSONSchema = {
    "name": "garment_tags",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        # Derived rather than restated. Strict mode requires every property to
        # appear here, and a second hand-written list is one forgotten edit away
        # from a 400 that reads as a model problem.
        "required": list(_PROPERTIES),
        "properties": _PROPERTIES,
    },
}
# A hand-written placeholder, replaced at task 5.1 by responses recorded from
# the live API and keyed by input. `06-TESTING-STRATEGY.md` requires recorded
# fixtures and this is a deliberate exception to that rule for four stages —
# `DECISIONS.md` 081. It passes `validate_tag_dict` with no errors and no
# coercions, which is asserted rather than assumed, and `rise` and
# `color_secondary` are null so the null paths are exercised too.
#
# `layer: "base"` is now defended by that assertion rather than merely correct:
# since 1.2a a top admits `base` or `mid` and nothing else, so this fake tagged
# `standalone` fails `test_the_fake_is_valid_input_to_the_validator`. That was
# the gap 082 found by mutation and 085 closed.
_FAKE_TAGS: dict[str, Any] = {
    "category": "top",
    "subcategory": "shirt",
    "fit": "relaxed",
    "length": "long_sleeve",
    "rise": None,
    "color_primary": "white",
    "color_secondary": None,
    "pattern": "solid",
    "material": "cotton",
    "formality": 3,
    "warmth": 2,
    "layer": "base",
    "water_resistant": False,
    # Says so out loud: a demo accidentally run with USE_FAKE_AI=true is then
    # visible on screen rather than looking like a real tagging result.
    "display_name": "placeholder white shirt",
    # Above the 0.35 the prompt names as blurred-or-crowded, so the fake does not
    # look like a poor read in the column 1.3 writes and 1.11 mines.
    "confidence": 0.5,
}

# `03-AI-CONTRACTS.md`'s wording. Sent as a second user message rather than
# replayed as a conversation: the image is re-sent either way, and adding the
# rejected answer as an assistant turn would cost tokens on every failure for a
# gain no document asks for. 1.11 can change that deliberately.
_CORRECTION = "Your previous response was invalid: {reason}. Correct it."


@lru_cache(maxsize=1)
def _client() -> AsyncOpenAI:
    """Built on first use, never at import.

    Measured: `AsyncOpenAI(api_key="")` raises `openai.OpenAIError` in the
    constructor. `OPENAI_API_KEY` defaults to an empty string precisely so CI
    can run without an OpenAI account (`07-DEPLOYMENT.md`), so a module-level
    client would raise on *import* — and from task 1.3 this module is on the
    import path to `app.main`, which would stop the whole suite collecting.
    This is 046's lesson about `cloudinary.config()` arriving through a second
    door, with a harder failure.
    """
    return AsyncOpenAI(
        api_key=settings.OPENAI_API_KEY,
        timeout=settings.OPENAI_TIMEOUT_SECONDS,
    )


async def tag_item(image_url: str, correction: str | None = None) -> dict[str, Any]:
    """One garment photograph in, the model's raw tag dict out.

    `correction` is the violation `validate_tags` found in the previous answer.
    It is the whole of the retry: same image, same schema, one more instruction.

    Raises `ValueError` when the response cannot be turned into a dict, and lets
    the provider's own exceptions escape untouched. Both mean no usable answer
    arrived, which `validate_tags` deliberately does not relabel as a
    `TaggingError` — see the module docstring. 1.3 catches both.
    """
    if settings.USE_FAKE_AI:
        # A copy: 1.3 renames `confidence` on the way to the column and must not
        # reach through the return value into the module constant.
        return dict(_FAKE_TAGS)

    content: list[Any] = [
        # detail: "low" is sufficient for garment classification and roughly
        # four times cheaper than "high".
        {"type": "image_url", "image_url": {"url": image_url, "detail": "low"}}
    ]
    if correction is not None:
        content.append({"type": "text", "text": _CORRECTION.format(reason=correction)})

    messages: list[ChatCompletionMessageParam] = [
        ChatCompletionSystemMessageParam(role="system", content=SYSTEM_PROMPT),
        ChatCompletionUserMessageParam(role="user", content=content),
    ]

    completion = await _client().chat.completions.create(
        model=settings.OPENAI_VISION_MODEL,
        messages=messages,
        response_format={"type": "json_schema", "json_schema": VISION_SCHEMA},
    )

    message = completion.choices[0].message
    if message.content is None:
        logger.warning(
            "Vision model returned no content",
            extra={"finish_reason": completion.choices[0].finish_reason},
        )
        raise ValueError("The vision model returned no content.")

    # json.JSONDecodeError subclasses ValueError, so a truncated response and an
    # empty one are one exception type for the caller to catch.
    tags: dict[str, Any] = json.loads(message.content)
    return tags


class TaggingError(Exception):
    """The model answered and the answer could not be accepted.

    Raised only after the one retry `03-AI-CONTRACTS.md` allows. Its message is
    the violation, which 1.3 stores in `items.error_message`. Not an `ApiError`:
    that subclasses `HTTPException` and could only be raised inside a request,
    where `scripts/seed_demo.py` calls this path from a command line
    (`DECISIONS.md` 044).
    """


@dataclass(frozen=True, slots=True)
class ItemTags:
    """The validated result, and the point at which types arrive (080).

    A frozen dataclass rather than a Pydantic model: Pydantic is this project's
    wire-body type, and a model here would re-validate on construction with
    rules that are not `enums.py`'s, giving two validators that can disagree
    about one dict.

    `coerced` carries the discarded values of the **accepted** answer and no
    others. A rejected first attempt's coercions describe tags that were never
    written, so carrying them would let 1.3 record "fit was discarded" beside a
    row whose `fit` came back fine on the retry. They survive in the log.
    """

    category: Category
    subcategory: str
    fit: Fit | None
    length: Length | None
    rise: Rise | None
    color_primary: ColorPrimary
    color_secondary: ColorPrimary | None
    pattern: Pattern
    material: Material
    formality: int
    warmth: int
    layer: Layer
    water_resistant: bool
    display_name: str
    confidence: float
    coerced: tuple[TagIssue, ...]


# The eleven fields whose schema type carries no null. `validate_tag_dict` reads
# every field with `.get`, so an absent key and a null one are the same thing
# there and both pass — correct for `PATCH`'s partial bodies, and wrong as input
# to a typed object. The *check* therefore lives here and not in `enums.py`.
# Strict mode should make it unfireable on model output, like the first and third
# rows of 03's table; it is what stops a short answer becoming a `TypeError`
# escaping a background task instead of a `TaggingError`.
#
# The ten row fields are `REQUIRED_TAG_FIELDS` and are shared with
# `PATCH /items/{id}`, which asks a different question of the same set. The
# eleventh is added here and only here: `confidence` describes an answer rather
# than a garment, so a row a person completed by hand legitimately has none.
# `DECISIONS.md` 116.
_REQUIRED_FIELDS: tuple[str, ...] = (*REQUIRED_TAG_FIELDS, "confidence")


def _missing_fields(tags: Mapping[str, Any]) -> list[str]:
    # `is None` rather than falsiness: water_resistant is legitimately False and
    # formality is never 0, but the next required boolean would be a silent bug.
    missing = [field for field in _REQUIRED_FIELDS if tags.get(field) is None]
    display_name = tags.get("display_name")
    if isinstance(display_name, str) and not display_name.strip():
        # A blank name is a tile with nothing on it — a visible defect where the
        # other ten are structural ones.
        missing.append("display_name")
    return missing


def _inspect(raw: Mapping[str, Any], attempt: int) -> tuple[TagValidation, str]:
    """Validate one answer, log what it discarded, and describe what is wrong.

    The returned string is empty when the answer is acceptable. It is both the
    correction sent to the model and, on the second failure, the `TaggingError`
    message, so it names fields and values rather than describing them.
    """
    report = validate_tag_dict(raw)

    for issue in report.coerced:
        # The only record a discarded value leaves at this layer. `fit: "flared"`
        # came back on real jeans, was correctly nulled, and vanished — so the
        # vocabulary was short a word and nothing said so (`DECISIONS.md` 084).
        # Field and value are enough for 1.11 to separate the two failures it has
        # to count apart: whether the value is in its own enum answers which.
        logger.warning(
            "Vision tag coerced",
            extra={
                "attempt": attempt,
                "field": issue.field,
                "value": issue.value,
                "category": raw.get("category"),
                "reason": issue.reason,
            },
        )

    violations = [issue.reason for issue in report.errors]
    violations += [
        f"{field} must be present and not empty" for field in _missing_fields(report.tags)
    ]
    return report, "; ".join(violations)


def _build(report: TagValidation) -> ItemTags:
    # Constructing a member is only safe after a `.values()` guard has
    # established that it cannot raise (`DECISIONS.md` 028). Both guards ran:
    # `validate_tag_dict` reports a non-member in a strict field as an error and
    # nulls a non-member in a nullable one, and `_missing_fields` has confirmed
    # the eleven are present. This function may only be called on a clean report.
    tags = report.tags
    fit = tags.get("fit")
    length = tags.get("length")
    rise = tags.get("rise")
    color_secondary = tags.get("color_secondary")
    return ItemTags(
        category=Category(tags["category"]),
        subcategory=tags["subcategory"],
        fit=None if fit is None else Fit(fit),
        length=None if length is None else Length(length),
        rise=None if rise is None else Rise(rise),
        color_primary=ColorPrimary(tags["color_primary"]),
        color_secondary=None if color_secondary is None else ColorPrimary(color_secondary),
        pattern=Pattern(tags["pattern"]),
        material=Material(tags["material"]),
        formality=tags["formality"],
        warmth=tags["warmth"],
        layer=Layer(tags["layer"]),
        water_resistant=tags["water_resistant"],
        display_name=tags["display_name"],
        # An integer 1 is a legal confidence and the column is a float.
        confidence=float(tags["confidence"]),
        coerced=report.coerced,
    )


async def validate_tags(raw: dict[str, Any], image_url: str) -> ItemTags:
    """The model's answer in, validated tags out, with at most one retry.

    `image_url` is a parameter because the retry is a second call to the model
    and a tag dict cannot say which photograph it came from. `03` and `STAGE-1`
    both printed a one-argument signature, which cannot hold the retry that 028
    and `06-TESTING-STRATEGY.md` put in this function; corrected at 1.2b.

    Raises `TaggingError` when the second answer is unacceptable too. Calls the
    model **at most once** — the answer in `raw` came from the caller's call, so
    two is the total for the item: a model that fails a strict schema twice is
    failing on the image, and a third call only spends money.
    """
    report, violation = _inspect(raw, attempt=1)
    if not violation:
        return _build(report)

    logger.warning(
        "Vision tags rejected, retrying once",
        extra={"attempt": 1, "violation": violation, "image_url": image_url},
    )
    retried = await tag_item(image_url, correction=violation)

    report, violation = _inspect(retried, attempt=2)
    if not violation:
        return _build(report)

    logger.error(
        "Vision tags rejected twice, giving up",
        extra={"attempt": 2, "violation": violation, "image_url": image_url},
    )
    raise TaggingError(violation)
