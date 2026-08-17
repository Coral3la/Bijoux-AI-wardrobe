"""The vision service, with no AI call anywhere.

Everything here is a property of the schema, the rendered prompt, the fake, or
the request `tag_item` builds. The live call is task 1.1's manual verification
step and cannot be a test — `CONVENTIONS.md` forbids any test calling OpenAI
unless it is marked `eval`.

Note what is deliberately *not* asserted: that the schema's enum arrays equal
`enums.py`'s. Both come from `enums.py`, so that comparison is a tautology and
`06-TESTING-STRATEGY.md` records it as one rather than letting it read as a
drift detector. What is asserted below is the part of the schema that is a
choice — the strict subset's shape, which a tidy-up would break.
"""

import json
from typing import Any

import pytest
from openai import AsyncOpenAI

from app.core.config import settings
from app.enums import (
    SUBCATEGORIES,
    Category,
    ColorPrimary,
    Fit,
    Layer,
    Length,
    Material,
    Pattern,
    Rise,
    validate_tag_dict,
)
from app.services import vision

UNCONSTRAINED = ("subcategory", "fit", "length", "rise")


# --- the response schema ----------------------------------------------------


def test_every_property_is_required() -> None:
    # Strict mode rejects a schema where they differ, so the failure would be a
    # 400 on the first live call, which reads as a model problem.
    schema = vision.VISION_SCHEMA["schema"]
    assert schema["required"] == list(schema["properties"])


def test_additional_properties_are_forbidden() -> None:
    assert vision.VISION_SCHEMA["schema"]["additionalProperties"] is False


def test_the_schema_is_strict() -> None:
    assert vision.VISION_SCHEMA["strict"] is True


def test_every_property_carries_a_type() -> None:
    # A bare {"enum": [...]} does not appear anywhere in the supported strict
    # subset; the documented form is always type plus enum.
    for name, spec in vision.VISION_SCHEMA["schema"]["properties"].items():
        assert "type" in spec, name


def test_a_nullable_enum_keeps_null_out_of_the_enum_array() -> None:
    # The vendor's documented shape for an optional enum, and it contradicts
    # plain JSON Schema — under which a null would fail the enum constraint.
    # Moving null into the array is the obvious tidy and is wrong.
    secondary = vision.VISION_SCHEMA["schema"]["properties"]["color_secondary"]

    assert secondary["type"] == ["string", "null"]
    assert None not in secondary["enum"]
    assert secondary["enum"] == ColorPrimary.values()


def test_the_category_dependent_and_coerced_fields_carry_no_enum() -> None:
    # subcategory because its validity depends on category, which JSON Schema
    # cannot express cleanly; fit, length and rise because an out-of-vocabulary
    # value there is coerced to null rather than retried, so constraining them
    # would buy nothing. All four are validated in Python instead.
    properties = vision.VISION_SCHEMA["schema"]["properties"]

    for name in UNCONSTRAINED:
        assert "enum" not in properties[name], name


def test_the_bounded_numbers_carry_both_bounds() -> None:
    properties = vision.VISION_SCHEMA["schema"]["properties"]

    assert (properties["formality"]["minimum"], properties["formality"]["maximum"]) == (1, 5)
    assert (properties["warmth"]["minimum"], properties["warmth"]["maximum"]) == (1, 5)
    assert (properties["confidence"]["minimum"], properties["confidence"]["maximum"]) == (0, 1)


# --- the rendered prompt ----------------------------------------------------


def test_the_placeholder_is_replaced() -> None:
    assert vision.VOCABULARY_PLACEHOLDER not in vision.SYSTEM_PROMPT


def test_a_prompt_file_without_the_placeholder_raises_at_load(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The guard is tested, not merely intended. A prompt that silently lost its
    # vocabulary still returns plausible tags, and the three fields the schema
    # does not constrain are exactly the ones that would quietly degrade.
    stripped = tmp_path / "vision_system.md"
    stripped.write_text(
        vision.SYSTEM_PROMPT.replace(vision._vocabulary_block(), ""), encoding="utf-8"
    )
    monkeypatch.setattr(vision, "PROMPT_PATH", stripped)

    with pytest.raises(ValueError, match=r"\{\{VOCABULARY\}\}"):
        vision._load_system_prompt()


@pytest.mark.parametrize(
    "vocabulary",
    [Category, Fit, Length, Rise, ColorPrimary, Pattern, Material, Layer],
    ids=lambda v: v.__name__.lower(),
)
def test_every_vocabulary_value_reaches_the_prompt(vocabulary: type) -> None:
    # The whole point of rendering the block rather than writing it out: drop a
    # field from _vocabulary_block and this fails, where the schema would not
    # notice for fit, length or rise at all.
    for value in vocabulary.values():
        assert value in vision.SYSTEM_PROMPT, value


def test_every_subcategory_reaches_the_prompt_under_its_category() -> None:
    # subcategory is a plain string in the schema, so the prompt is the only
    # place the mapping is ever stated to the model.
    for category, subs in SUBCATEGORIES.items():
        for sub in subs:
            assert sub in vision.SYSTEM_PROMPT, sub
        assert category.value in vision.SYSTEM_PROMPT


def test_the_prompt_keeps_the_rules_the_schema_cannot_express() -> None:
    # rise-only-for-bottoms and the 20% rule for color_secondary are semantic,
    # not structural; nothing but the prompt carries them to the model.
    assert "rise" in vision.SYSTEM_PROMPT
    assert "at least 20%" in vision.SYSTEM_PROMPT
    assert "0.35" in vision.SYSTEM_PROMPT


# --- the fake ---------------------------------------------------------------


def test_the_fake_is_valid_input_to_the_validator() -> None:
    # If 1.2 tightens validate_tag_dict, this fails here rather than at 5.1.
    # A fixture that has quietly stopped being valid input is the same shape of
    # problem as a test that has quietly stopped asserting anything.
    report = validate_tag_dict(vision._FAKE_TAGS)

    assert report.errors == ()
    assert report.coerced == ()


def test_the_fake_survives_validation_unchanged() -> None:
    assert validate_tag_dict(vision._FAKE_TAGS).tags == vision._FAKE_TAGS


def test_the_fake_carries_exactly_the_documented_fields() -> None:
    assert set(vision._FAKE_TAGS) == set(vision.VISION_SCHEMA["schema"]["properties"])


def test_the_fake_confidence_is_above_the_review_threshold() -> None:
    # Below 0.35 the item is accepted but flagged for review, which would make
    # every fake-tagged item in Stages 1 to 4 wear a warning it has not earned.
    assert vision._FAKE_TAGS["confidence"] >= 0.35


@pytest.mark.asyncio
async def test_the_fake_branch_never_builds_a_client(monkeypatch: pytest.MonkeyPatch) -> None:
    # CI configures no OPENAI_API_KEY, and AsyncOpenAI raises on an empty one.
    # This is what keeps USE_FAKE_AI usable there.
    monkeypatch.setattr(settings, "USE_FAKE_AI", True)

    def explode() -> AsyncOpenAI:
        raise AssertionError("the OpenAI client was built")

    monkeypatch.setattr(vision, "_client", explode)

    assert await vision.tag_item("https://example.invalid/x") == vision._FAKE_TAGS


@pytest.mark.asyncio
async def test_the_fake_branch_returns_a_copy(monkeypatch: pytest.MonkeyPatch) -> None:
    # 1.3 renames `confidence` to `ai_confidence` on the way to the column, so a
    # caller mutating the result must not reach the module constant.
    monkeypatch.setattr(settings, "USE_FAKE_AI", True)

    first = await vision.tag_item("https://example.invalid/x")
    first["category"] = "mutated"

    assert vision._FAKE_TAGS["category"] == "top"
    assert (await vision.tag_item("https://example.invalid/x"))["category"] == "top"


# --- the request tag_item builds --------------------------------------------


class _RecordingCompletions:
    def __init__(self, content: str | None, finish_reason: str = "stop") -> None:
        self._content = content
        self._finish_reason = finish_reason
        self.kwargs: dict[str, Any] = {}

    async def create(self, **kwargs: Any) -> Any:
        self.kwargs = kwargs
        message = type("Message", (), {"content": self._content})()
        choice = type("Choice", (), {"message": message, "finish_reason": self._finish_reason})()
        return type("Completion", (), {"choices": [choice]})()


@pytest.fixture
def recorded(monkeypatch: pytest.MonkeyPatch) -> _RecordingCompletions:
    monkeypatch.setattr(settings, "USE_FAKE_AI", False)
    completions = _RecordingCompletions(json.dumps(vision._FAKE_TAGS))
    client = type("Client", (), {"chat": type("Chat", (), {"completions": completions})()})()
    monkeypatch.setattr(vision, "_client", lambda: client)
    return completions


@pytest.mark.asyncio
async def test_the_call_sends_the_documented_schema(recorded: _RecordingCompletions) -> None:
    await vision.tag_item("https://res.cloudinary.invalid/a")

    assert recorded.kwargs["response_format"] == {
        "type": "json_schema",
        "json_schema": vision.VISION_SCHEMA,
    }


@pytest.mark.asyncio
async def test_the_call_sends_the_image_at_low_detail(recorded: _RecordingCompletions) -> None:
    # detail: "low" is the cost decision in 03-AI-CONTRACTS.md — roughly four
    # times cheaper than "high" and sufficient for garment classification.
    await vision.tag_item("https://res.cloudinary.invalid/a")

    image = recorded.kwargs["messages"][1]["content"][0]
    assert image == {
        "type": "image_url",
        "image_url": {"url": "https://res.cloudinary.invalid/a", "detail": "low"},
    }


@pytest.mark.asyncio
async def test_the_call_sends_the_rendered_prompt_as_the_system_message(
    recorded: _RecordingCompletions,
) -> None:
    await vision.tag_item("https://res.cloudinary.invalid/a")

    system = recorded.kwargs["messages"][0]
    assert system["role"] == "system"
    assert system["content"] == vision.SYSTEM_PROMPT


@pytest.mark.asyncio
async def test_the_call_uses_the_configured_vision_model(
    recorded: _RecordingCompletions, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "OPENAI_VISION_MODEL", "a-different-model")

    await vision.tag_item("https://res.cloudinary.invalid/a")

    assert recorded.kwargs["model"] == "a-different-model"


@pytest.mark.asyncio
async def test_the_response_is_returned_unvalidated(recorded: _RecordingCompletions) -> None:
    # 1.2 owns validation. A tag dict this service silently corrected would rob
    # validate_tags of the input it exists to judge.
    assert await vision.tag_item("https://res.cloudinary.invalid/a") == vision._FAKE_TAGS


@pytest.mark.asyncio
async def test_a_response_with_no_content_raises_a_value_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "USE_FAKE_AI", False)
    completions = _RecordingCompletions(None, finish_reason="length")
    client = type("Client", (), {"chat": type("Chat", (), {"completions": completions})()})()
    monkeypatch.setattr(vision, "_client", lambda: client)

    with pytest.raises(ValueError):
        await vision.tag_item("https://res.cloudinary.invalid/a")


@pytest.mark.asyncio
async def test_a_truncated_response_raises_a_value_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # json.JSONDecodeError subclasses ValueError, so 1.2 has one type to catch
    # for "the response was not usable" rather than two.
    monkeypatch.setattr(settings, "USE_FAKE_AI", False)
    completions = _RecordingCompletions('{"category": "to')
    client = type("Client", (), {"chat": type("Chat", (), {"completions": completions})()})()
    monkeypatch.setattr(vision, "_client", lambda: client)

    with pytest.raises(ValueError):
        await vision.tag_item("https://res.cloudinary.invalid/a")
