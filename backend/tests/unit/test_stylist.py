"""The stylist service, with no AI call anywhere.

Everything here is a property of the schema, the prompt file, the message
`suggest_looks` assembles, the fake, or the way an unusable answer is read.
The live call is task 2.4's manual verification step and cannot be a test —
`CONVENTIONS.md` forbids any test calling OpenAI unless it is marked `eval`.

Expected text is **transcribed from `03-AI-CONTRACTS.md`**, never built from
`stylist.py`'s own constants. A derived expectation moves with the mutation it
is supposed to catch, which this project has now learned twice — `DECISIONS.md`
101 and the `RESULT_LIMIT` survivor at 2.2.

The failure cases in the last section are not imagined. Each one was measured
against openai 2.52.0 before it was written, with a local HTTP server standing
in for the API: a `200` carrying `text/html` makes `create()` return a `str`, a
`200` carrying JSON of the wrong shape returns a `ChatCompletion` whose
`choices` is `None`, and neither is an `OpenAIError`. `DECISIONS.md` 161.
"""

import datetime
import json
import uuid
from typing import Any

import pytest
from openai import APIConnectionError, AsyncOpenAI

from app.core.config import settings
from app.schemas.item import ItemResponse
from app.services import stylist
from app.services.serializer import serialize_wardrobe

# `03-AI-CONTRACTS.md`'s own worked ids, all five legal under
# `app/core/short_id.py`'s alphabet since this commit closed `AUDITS.md` O-22.
TOP_ID = "A3F9K2"
JEANS_ID = "7BX1QM"
BOOTS_ID = "SEFA38"
BLAZER_ID = "EH8VVQ"
DRESS_ID = "ZR44QW"

# Transcribed from `03-AI-CONTRACTS.md`'s worked single-day request.
RULE = "Use warmth 2-3 for the base. A mid layer or light outerwear (warmth 2-3) is optional."
SUMMARY = "18°C, no rain."

_EPOCH = datetime.datetime(2026, 8, 26, tzinfo=datetime.UTC)


def _item(short_id: str, **tags: Any) -> ItemResponse:
    """One `ItemResponse` with every column the stylist never reads fixed, so a
    test says only what it is about."""
    fields: dict[str, Any] = {
        "id": uuid.uuid4(),
        "short_id": short_id,
        "status": "ready",
        "image_public_id": "bijoux/demo/photograph",
        "category": None,
        "subcategory": None,
        "fit": None,
        "length": None,
        "rise": None,
        "color_primary": None,
        "color_secondary": None,
        "pattern": None,
        "material": None,
        "formality": None,
        "warmth": None,
        "layer": None,
        "water_resistant": False,
        "display_name": None,
        "attributes": {},
        "ai_confidence": None,
        "user_edited": False,
        "error_message": None,
        # Added at 3.4 with the two columns' first appearance on the wire. Both
        # are required rather than defaulted, so this fixture failed to build
        # until they were written here — the collection error that named all
        # three copies of this dict at once.
        "wear_count": 0,
        "last_worn_at": None,
        "is_archived": False,
        "created_at": _EPOCH,
        "updated_at": _EPOCH,
    }
    return ItemResponse(**(fields | tags))


TOP = _item(TOP_ID, category="top", subcategory="shirt")
JEANS = _item(JEANS_ID, category="bottom", subcategory="jeans")
BOOTS = _item(BOOTS_ID, category="shoes", subcategory="boots")
BLAZER = _item(BLAZER_ID, category="outerwear", subcategory="blazer")
DRESS = _item(DRESS_ID, category="dress", subcategory="dress")

WARDROBE = [TOP, JEANS, BOOTS, BLAZER]


def _context(**overrides: Any) -> stylist.StylistContext:
    fields: dict[str, Any] = {
        "date": datetime.date(2026, 3, 14),
        "occasion": "work",
        "forecast_summary": SUMMARY,
        "weather_rule": RULE,
    }
    return stylist.StylistContext(**(fields | overrides))


def _answer(**overrides: Any) -> dict[str, Any]:
    """`03-AI-CONTRACTS.md`'s response example, single-day."""
    look: dict[str, Any] = {
        "occasion": "work",
        "title": "Morning meetings",
        "item_ids": [TOP_ID, JEANS_ID, BOOTS_ID, BLAZER_ID],
        "reasoning": (
            "The high-rise straight jean balances the oversized shirt and the "
            "tucked front keeps the waist defined."
        ),
        "weather_note": "18°C in the morning — the blazer is enough without a coat.",
    }
    payload: dict[str, Any] = {"looks": [look], "missing_pieces": [], "message": "One look."}
    return payload | overrides


# --- the response schema ----------------------------------------------------


def _objects() -> list[dict[str, Any]]:
    root = stylist.STYLIST_SCHEMA["schema"]
    return [
        root,
        root["properties"]["looks"]["items"],
        root["properties"]["missing_pieces"]["items"],
    ]


def test_every_property_is_required_in_every_object() -> None:
    # Strict mode rejects a schema where they differ, so the failure would be a
    # 400 on a live call, which reads as a model problem.
    for schema in _objects():
        assert schema["required"] == list(schema["properties"])


def test_additional_properties_are_forbidden_in_every_object() -> None:
    for schema in _objects():
        assert schema["additionalProperties"] is False


def test_the_schema_is_strict_and_named() -> None:
    assert stylist.STYLIST_SCHEMA["strict"] is True
    assert stylist.STYLIST_SCHEMA["name"] == "outfit_recommendation"


def test_the_root_carries_exactly_the_three_documented_keys() -> None:
    assert list(stylist.STYLIST_SCHEMA["schema"]["properties"]) == [
        "looks",
        "missing_pieces",
        "message",
    ]


def test_a_look_carries_exactly_the_four_documented_keys() -> None:
    # `confidence` and `look_id` are struck from `03`'s look object: neither has
    # a column, a renderer or a task, and in strict mode every property is one
    # the model must produce on every call. `AUDITS.md` O-9, `DECISIONS.md` 157.
    # `day` is struck at 2.5 on the same test, once a live call had shown it
    # being filled from the date. `AUDITS.md` O-24, `DECISIONS.md` 163.
    # `occasion` is struck at 4.3 on the same test again, and it is the last
    # field to fail it: the trip contract keys an occasion to a day in the
    # *request*, so the model's echo has no reader on either path.
    # `AUDITS.md` O-26, `DECISIONS.md` 193.
    assert list(stylist.STYLIST_SCHEMA["schema"]["properties"]["looks"]["items"]["properties"]) == [
        "title",
        "item_ids",
        "reasoning",
        "weather_note",
    ]


def test_a_trip_look_is_the_same_four_keys_with_a_day_and_a_slot_in_front() -> None:
    # One shared dict rather than two literals, so a change to what a look holds
    # cannot land on one schema and not the other. `DECISIONS.md` 189, 193 — and
    # 4.13 is where that mitigation was paid for, with a second trip-only field.
    assert list(stylist.TRIP_SCHEMA["schema"]["properties"]["looks"]["items"]["properties"]) == [
        "day",
        "slot",
        "title",
        "item_ids",
        "reasoning",
        "weather_note",
    ]


def test_the_slot_property_admits_exactly_the_two_the_vocabulary_holds() -> None:
    # An `enum` where `missing_pieces.category` deliberately has none: this one
    # has a reader — rule 10 matches the pair against the request — so a third
    # value could match nothing and refusing it in the schema is free.
    slot = stylist.TRIP_SCHEMA["schema"]["properties"]["looks"]["items"]["properties"]["slot"]
    assert slot == {"type": "string", "enum": ["day", "evening"]}


def test_the_trip_schema_is_named_for_the_contract_it_answers() -> None:
    assert stylist.TRIP_SCHEMA["name"] == "trip_packing_plan"
    assert stylist.TRIP_SCHEMA["strict"] is True


def test_the_packing_list_holds_item_ids_and_nothing_else() -> None:
    # No `by_category` — strict mode cannot express a free-form category map and
    # the frontend groups from `items[].category`. No `reuse_summary` — Python
    # computes it, because asking a model for arithmetic means checking it.
    packing = stylist.TRIP_SCHEMA["schema"]["properties"]["packing_list"]
    assert list(packing["properties"]) == ["item_ids"]
    assert packing["required"] == ["item_ids"]


def test_the_schema_has_no_packing_list() -> None:
    # Deferred to Stage 4 with the trip user message and the reuse arithmetic
    # rather than shipped as a field that would be null on every call for two
    # stages. `DECISIONS.md` 157.
    assert "packing_list" not in stylist.STYLIST_SCHEMA["schema"]["properties"]


def test_the_schema_uses_no_min_items() -> None:
    # Not verified against this pin, and "at least one look" is rule 4 of `03`'s
    # validation table, which is 2.5's. A keyword the API rejects is a 400.
    assert "minItems" not in json.dumps(stylist.STYLIST_SCHEMA)


# --- the prompt -------------------------------------------------------------


def test_the_system_prompt_is_the_file_on_disk() -> None:
    assert stylist.PROMPT_PATH.read_text(encoding="utf-8") == stylist.SYSTEM_PROMPT


def test_the_prompt_tells_the_model_to_work_with_what_the_wardrobe_has() -> None:
    # Added to `03`'s CONSTRAINTS block at 2.4. Without it, line 292's "obey the
    # weather rule exactly, it is not a suggestion" and the wardrobe-cannot-
    # satisfy bullet point opposite ways on a wardrobe with no qualifying item,
    # and the model chooses. `DECISIONS.md` 158.
    assert (
        "Where the wardrobe holds nothing that satisfies the weather rule, dress the\n"
        "  day from the closest items it does hold" in stylist.SYSTEM_PROMPT
    )
    assert (
        "Never refuse to build a look, and\n"
        "  never return an empty one, because an ideal item is absent." in stylist.SYSTEM_PROMPT
    )


def test_the_prompt_says_missing_pieces_never_replaces_a_look() -> None:
    assert (
        "`missing_pieces` is a note beside a\n"
        "  complete look and never a replacement for one." in stylist.SYSTEM_PROMPT
    )


def test_the_prompt_gives_an_explicit_outerwear_request_precedence() -> None:
    # The field is meaningless if the weather rule can override an explicit
    # choice, and `04-API-SPEC.md` specifies the field. `DECISIONS.md` 158.
    assert (
        "An explicit outerwear instruction from the user overrides the weather rule.\n"
        "  Where none is given, the weather rule decides." in stylist.SYSTEM_PROMPT
    )


def test_the_prompt_keeps_the_anchor_and_locked_conditionals() -> None:
    # Transcribed verbatim from `03` and inert until 2.10 and 2.11 send the
    # blocks. Present rather than added later, so the file and the document can
    # be compared line for line. `DECISIONS.md` 158.
    assert "If an ANCHOR is given, that item must appear in the look." in stylist.SYSTEM_PROMPT
    assert "If LOCKED items are given, all of them must appear unchanged" in stylist.SYSTEM_PROMPT


def test_the_prompt_carries_no_vocabulary_placeholder() -> None:
    # Unlike the vision prompt, nothing is rendered into this one — it names no
    # enum member, so the file is the whole prompt.
    assert "{{" not in stylist.SYSTEM_PROMPT


# --- the user message -------------------------------------------------------


def test_the_wardrobe_block_names_the_item_count() -> None:
    assert stylist._user_message(WARDROBE, _context()).startswith("WARDROBE (4 items):\n")


def test_the_wardrobe_block_is_the_serialiser_output() -> None:
    assert serialize_wardrobe(WARDROBE) in stylist._user_message(WARDROBE, _context())


def test_the_profile_block_carries_height_and_preferences() -> None:
    message = stylist._user_message(
        WARDROBE, _context(height_cm=165, style_notes="prefer high-rise, avoid crop tops")
    )
    assert (
        "USER PROFILE:\nHeight: 165 cm. Preferences: prefer high-rise, avoid crop tops" in message
    )


def test_the_profile_block_is_omitted_when_both_columns_are_empty() -> None:
    # A heading with nothing under it tells the model a profile exists and is
    # blank, which is not what a user who has never filled one in means.
    assert "USER PROFILE" not in stylist._user_message(WARDROBE, _context())


def test_the_profile_block_keeps_the_half_that_is_present() -> None:
    height_only = stylist._user_message(WARDROBE, _context(height_cm=165))
    notes_only = stylist._user_message(WARDROBE, _context(style_notes="no heels"))
    assert "USER PROFILE:\nHeight: 165 cm." in height_only
    assert "Preferences" not in height_only
    assert "USER PROFILE:\nPreferences: no heels" in notes_only
    assert "Height" not in notes_only


def test_the_preferences_block_is_inserted_before_the_request() -> None:
    message = stylist._user_message(
        WARDROBE,
        _context(
            preferences=(
                "USER PREFERENCES (learned from rated looks):\n"
                "- Liked: relaxed tops\n"
                "- Disliked: bodycon dresses\n"
                "- Recently worn (avoid repeating): 7BX1QM"
            )
        ),
    )

    assert (
        "USER PREFERENCES (learned from rated looks):\n"
        "- Liked: relaxed tops\n"
        "- Disliked: bodycon dresses\n"
        "- Recently worn (avoid repeating): 7BX1QM\n\n"
        "REQUEST:"
    ) in message


def test_the_preferences_block_is_omitted_when_the_context_has_none() -> None:
    assert "USER PREFERENCES" not in stylist._user_message(WARDROBE, _context())


def test_the_request_block_is_the_documented_one() -> None:
    # Transcribed from `03-AI-CONTRACTS.md`'s single-day block.
    assert stylist._user_message(WARDROBE, _context()).endswith(
        "REQUEST:\n"
        "Date: 2026-03-14\n"
        "Occasion: work\n"
        f"Weather: {SUMMARY}\n"
        f"Weather rule: {RULE}\n"
        "Build 1 look."
    )


def test_notes_are_printed_when_given() -> None:
    message = stylist._user_message(WARDROBE, _context(notes="meeting with a client"))
    assert "Occasion: work\nNotes: meeting with a client\nWeather:" in message


def test_notes_are_omitted_when_absent() -> None:
    assert "Notes:" not in stylist._user_message(WARDROBE, _context())


@pytest.mark.parametrize(
    ("include_outerwear", "expected"),
    [
        (True, "Outerwear: the user has asked for outerwear. Include one."),
        (False, "Outerwear: the user has asked for no outerwear. Include none."),
    ],
)
def test_an_outerwear_preference_is_printed_after_the_weather_rule(
    include_outerwear: bool, expected: str
) -> None:
    # After, not beside the occasion: it overrides the rule, and a reader takes
    # the later of two conflicting instructions as the operative one.
    message = stylist._user_message(WARDROBE, _context(include_outerwear=include_outerwear))
    assert f"Weather rule: {RULE}\n{expected}\nBuild 1 look." in message


def test_no_outerwear_preference_prints_no_line() -> None:
    assert "Outerwear:" not in stylist._user_message(WARDROBE, _context())


def test_the_anchor_block_is_the_documented_one() -> None:
    # Transcribed from `03-AI-CONTRACTS.md`'s anchored block, line breaks
    # included, and asserted as the tail of the message: it comes after
    # `Build 1 look.` because it constrains it.
    assert stylist._user_message(WARDROBE, _context(anchor_id=JEANS_ID)).endswith(
        "Build 1 look.\n"
        "\n"
        f"ANCHOR: {JEANS_ID}\n"
        "This item MUST appear in the look. Build the rest of the outfit around it.\n"
        "If it cannot work for this occasion or weather, still include it and\n"
        "explain the tension in `reasoning`."
    )


def test_no_anchor_prints_no_block() -> None:
    assert "ANCHOR:" not in stylist._user_message(WARDROBE, _context())


def test_the_locked_block_is_the_documented_one() -> None:
    # `03-AI-CONTRACTS.md`'s swap block, all four lines, as the tail of the
    # message: it is the narrowest instruction in it, so it comes last.
    message = stylist._user_message(
        WARDROBE,
        _context(
            locked_ids=(TOP_ID, JEANS_ID, BLAZER_ID),
            replace_role="shoes",
            excluded_ids=(BOOTS_ID,),
        ),
    )

    assert message.endswith(
        "Build 1 look.\n"
        "\n"
        f"LOCKED: {TOP_ID}, {JEANS_ID}, {BLAZER_ID}\n"
        "These items MUST appear unchanged.\n"
        "Replace only the shoes with a different option from the wardrobe.\n"
        f"Do not return the previously rejected item {BOOTS_ID}."
    )


def test_a_dress_role_appends_the_top_and_bottom_clarifier() -> None:
    # Rule 2 admits `top and bottom OR dress`, so without this line a
    # `replace_role: dress` swap could legally answer with a top+bottom pair.
    # The six other roles have no such alternative, so `_locked_block` prints
    # the clarifier only for `dress`.
    message = stylist._user_message(
        WARDROBE,
        _context(locked_ids=(BOOTS_ID,), replace_role="dress"),
    )

    assert message.endswith(
        f"LOCKED: {BOOTS_ID}\n"
        "These items MUST appear unchanged.\n"
        "Replace only the dress with a different option from the wardrobe.\n"
        "The replacement MUST itself be a dress. "
        "Do not substitute a top and a bottom."
    )


def test_a_non_dress_role_does_not_print_the_dress_clarifier() -> None:
    # The clarifier is scoped to the one role rule 2 makes it necessary for.
    message = stylist._user_message(
        WARDROBE,
        _context(locked_ids=(TOP_ID, JEANS_ID), replace_role="shoes"),
    )

    assert "MUST itself be a dress" not in message


def test_locks_with_no_role_and_no_exclusion_print_two_lines() -> None:
    # `_outerwear_line`'s rule on a longer block: a sentence about a field the
    # user did not send is an instruction nobody gave. Without a role there is
    # nothing to name as replaceable, and without an exclusion nothing was
    # rejected.
    message = stylist._user_message(WARDROBE, _context(locked_ids=(TOP_ID, JEANS_ID)))

    assert message.endswith(f"LOCKED: {TOP_ID}, {JEANS_ID}\nThese items MUST appear unchanged.")


def test_no_locks_prints_no_block() -> None:
    # An exclusion alone is not a swap, and `03` prints the rejection line
    # inside the LOCKED block or not at all.
    assert "LOCKED:" not in stylist._user_message(WARDROBE, _context(excluded_ids=(BOOTS_ID,)))


# --- the request suggest_looks builds ---------------------------------------


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


def _install(monkeypatch: pytest.MonkeyPatch, completions: Any) -> None:
    monkeypatch.setattr(settings, "USE_FAKE_AI", False)
    client = type("Client", (), {"chat": type("Chat", (), {"completions": completions})()})()
    monkeypatch.setattr(stylist, "_client", lambda: client)


@pytest.fixture
def recorded(monkeypatch: pytest.MonkeyPatch) -> _RecordingCompletions:
    completions = _RecordingCompletions(json.dumps(_answer()))
    _install(monkeypatch, completions)
    return completions


@pytest.mark.asyncio
async def test_the_call_sends_the_documented_schema(recorded: _RecordingCompletions) -> None:
    await stylist.suggest_looks(WARDROBE, _context())

    assert recorded.kwargs["response_format"] == {
        "type": "json_schema",
        "json_schema": stylist.STYLIST_SCHEMA,
    }


@pytest.mark.asyncio
async def test_the_call_sends_the_prompt_as_the_system_message(
    recorded: _RecordingCompletions,
) -> None:
    await stylist.suggest_looks(WARDROBE, _context())

    system = recorded.kwargs["messages"][0]
    assert system["role"] == "system"
    assert system["content"] == stylist.SYSTEM_PROMPT


@pytest.mark.asyncio
async def test_the_call_sends_the_assembled_user_message(
    recorded: _RecordingCompletions,
) -> None:
    context = _context(notes="meeting with a client")
    await stylist.suggest_looks(WARDROBE, context)

    user = recorded.kwargs["messages"][1]
    assert user["role"] == "user"
    assert user["content"][0] == {
        "type": "text",
        "text": stylist._user_message(WARDROBE, context),
    }


@pytest.mark.asyncio
async def test_the_call_uses_the_configured_stylist_model(
    recorded: _RecordingCompletions, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "OPENAI_STYLIST_MODEL", "a-different-model")

    await stylist.suggest_looks(WARDROBE, _context())

    assert recorded.kwargs["model"] == "a-different-model"


@pytest.mark.asyncio
async def test_the_call_ignores_the_vision_model_setting(
    recorded: _RecordingCompletions, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The two pins are separate since 2.4 precisely so 1.11's re-pin of the
    # vision model cannot move the stylist's underneath a stage whose acceptance
    # criteria are all about how the stylist behaves. `DECISIONS.md` 160.
    monkeypatch.setattr(settings, "OPENAI_VISION_MODEL", "a-different-model")

    await stylist.suggest_looks(WARDROBE, _context())

    assert recorded.kwargs["model"] == settings.OPENAI_STYLIST_MODEL


@pytest.mark.asyncio
async def test_a_call_with_no_correction_sends_the_user_message_alone(
    recorded: _RecordingCompletions,
) -> None:
    await stylist.suggest_looks(WARDROBE, _context())

    assert len(recorded.kwargs["messages"][1]["content"]) == 1


@pytest.mark.asyncio
async def test_a_correction_is_sent_beside_the_user_message(
    recorded: _RecordingCompletions,
) -> None:
    # `03-AI-CONTRACTS.md`'s wording, and the whole of 2.5's retry: same
    # wardrobe, same schema, one more instruction.
    await stylist.suggest_looks(WARDROBE, _context(), correction="XXXXXX is not in the wardrobe")

    content = recorded.kwargs["messages"][1]["content"]
    assert len(content) == 2
    assert content[1] == {
        "type": "text",
        "text": "Your previous response was invalid: XXXXXX is not in the wardrobe. Correct it.",
    }


# --- the guard that keeps this module off the live API -----------------------


@pytest.mark.asyncio
async def test_the_suite_guard_stands_between_this_module_and_the_live_api() -> None:
    """The one test here that installs no client of its own.

    `tests/conftest.py`'s autouse fixture replaces `_client` in **both** AI
    modules, and until 2.4 it named only `vision`. Every other test in this file
    fakes the call itself, so deleting the stylist half of that guard leaves the
    whole suite green — which is precisely the shape of hole the fixture exists
    to close, and the reason it needs a test that fails when it is removed
    rather than only a comment saying it matters.

    Measured: with the guard removed and a real key in `.env`, this test sends
    the wardrobe to OpenAI. That is the accident being defended against."""
    with pytest.raises(AssertionError, match="reached for the OpenAI client"):
        await stylist.suggest_looks(WARDROBE, _context())


# --- the fake ---------------------------------------------------------------


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "USE_FAKE_AI", True)

    def explode() -> AsyncOpenAI:
        raise AssertionError("the fake branch built a client")

    monkeypatch.setattr(stylist, "_client", explode)


@pytest.mark.asyncio
async def test_the_fake_branch_never_builds_a_client(fake: None) -> None:
    # CI configures no OPENAI_API_KEY, and AsyncOpenAI raises on an empty one.
    assert await stylist.suggest_looks(WARDROBE, _context())


@pytest.mark.asyncio
async def test_the_fake_returns_ids_from_the_wardrobe_it_was_given(fake: None) -> None:
    # The whole reason this is not a recorded fixture: `short_id`s are generated
    # per row, so literal ids would fail 2.5's hallucination guard on every
    # call and no E2E journey could ever see a look. `DECISIONS.md` 159.
    answer = await stylist.suggest_looks(WARDROBE, _context())

    assert set(answer.looks[0].item_ids) <= {item.short_id for item in WARDROBE}


@pytest.mark.asyncio
async def test_the_fake_picks_shoes_a_top_and_a_bottom(fake: None) -> None:
    answer = await stylist.suggest_looks(WARDROBE, _context())

    assert answer.looks[0].item_ids == (BOOTS_ID, TOP_ID, JEANS_ID)


@pytest.mark.asyncio
async def test_the_fake_falls_back_to_a_dress_without_a_pair(fake: None) -> None:
    answer = await stylist.suggest_looks([BOOTS, DRESS, BLAZER], _context())

    assert answer.looks[0].item_ids == (BOOTS_ID, DRESS_ID)


@pytest.mark.asyncio
async def test_the_fake_puts_the_anchor_in_the_look(fake: None) -> None:
    # Rule 7 judges the fake as well as the model. A fake that ignored the
    # anchor would answer a look rule 7 rejects, the retry would answer the
    # same look, and every anchored request under `USE_FAKE_AI` would be a 502.
    answer = await stylist.suggest_looks(WARDROBE, _context(anchor_id=BLAZER_ID))

    assert answer.looks[0].item_ids == (BLAZER_ID, BOOTS_ID, TOP_ID, JEANS_ID)


@pytest.mark.asyncio
async def test_the_fake_lets_the_anchor_displace_its_own_category(fake: None) -> None:
    # A second top beside the anchored one is a look with two base tops, which
    # the system prompt forbids. The anchor replaces the pick it duplicates.
    second_top = _item("HH7TP2", category="top", subcategory="t-shirt")
    answer = await stylist.suggest_looks([*WARDROBE, second_top], _context(anchor_id="HH7TP2"))

    assert answer.looks[0].item_ids == ("HH7TP2", BOOTS_ID, JEANS_ID)


@pytest.mark.asyncio
async def test_an_anchor_the_wardrobe_does_not_hold_leaves_the_fake_alone(fake: None) -> None:
    # 2.7 resolves the anchor against this very list, so this is unreachable
    # through the endpoint. The fake declines to invent an id for it rather than
    # returning one rule 1 would call a hallucination.
    answer = await stylist.suggest_looks(WARDROBE, _context(anchor_id="Q7WXYZ"))

    assert answer.looks[0].item_ids == (BOOTS_ID, TOP_ID, JEANS_ID)


@pytest.mark.asyncio
async def test_the_fake_keeps_the_locks_and_swaps_the_rejected_item(fake: None) -> None:
    # Rule 8 judges the fake as well as the model, so a fake that ignored the
    # locks would make every `USE_FAKE_AI` swap a 502 — the trap the anchor
    # walked into at 2.10, one field along. The second pair of shoes is what
    # the swap has to find.
    loafers = _item("HH7TP2", category="shoes", subcategory="loafers")
    answer = await stylist.suggest_looks(
        [*WARDROBE, loafers],
        _context(locked_ids=(TOP_ID, JEANS_ID), excluded_ids=(BOOTS_ID,), replace_role="shoes"),
    )

    assert answer.looks[0].item_ids == (TOP_ID, JEANS_ID, "HH7TP2")


@pytest.mark.asyncio
async def test_the_fake_never_puts_a_dress_beside_a_top_and_a_bottom(fake: None) -> None:
    # Rule 9 judges the fake too, and this is the clause that made it a 502:
    # a dress in the look — anchored here, locked in a swap — used to be joined
    # by the pair, which is a look nobody can put on.
    answer = await stylist.suggest_looks(WARDROBE + [DRESS], _context(anchor_id=DRESS_ID))

    assert answer.looks[0].item_ids == (DRESS_ID, BOOTS_ID)


@pytest.mark.asyncio
async def test_the_fake_says_out_loud_that_it_is_a_placeholder(fake: None) -> None:
    # `DECISIONS.md` 081's mitigation: a demo accidentally run with the flag on
    # is visible on screen rather than passing for a real look.
    answer = await stylist.suggest_looks(WARDROBE, _context())

    assert "Placeholder" in answer.looks[0].reasoning
    assert "Placeholder" in answer.looks[0].weather_note
    assert "Placeholder" in answer.message


# --- answers that cannot be used --------------------------------------------


class _AnswersWith:
    """A completions stub returning whatever the API is being made to return,
    including the three shapes the SDK does not raise on."""

    def __init__(self, completion: Any) -> None:
        self._completion = completion

    async def create(self, **kwargs: Any) -> Any:
        return self._completion


def _completion(content: str | None, finish_reason: str = "stop") -> Any:
    message = type("Message", (), {"content": content})()
    choice = type("Choice", (), {"message": message, "finish_reason": finish_reason})()
    return type("Completion", (), {"choices": [choice]})()


@pytest.mark.asyncio
async def test_no_content_is_a_value_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _install(monkeypatch, _AnswersWith(_completion(None, finish_reason="length")))

    with pytest.raises(ValueError, match="no content"):
        await stylist.suggest_looks(WARDROBE, _context())


@pytest.mark.asyncio
async def test_a_null_choices_list_is_a_value_error(monkeypatch: pytest.MonkeyPatch) -> None:
    # Measured: a 200 carrying JSON of the wrong shape returns a ChatCompletion
    # whose `choices` is None, which the SDK's own annotation says is
    # impossible. Without the guard this is a TypeError out of a route.
    _install(monkeypatch, _AnswersWith(type("Completion", (), {"choices": None})()))

    with pytest.raises(ValueError, match="no choices"):
        await stylist.suggest_looks(WARDROBE, _context())


@pytest.mark.asyncio
async def test_an_empty_choices_list_is_a_value_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _install(monkeypatch, _AnswersWith(type("Completion", (), {"choices": []})()))

    with pytest.raises(ValueError, match="no choices"):
        await stylist.suggest_looks(WARDROBE, _context())


@pytest.mark.asyncio
async def test_an_answer_that_is_not_a_completion_is_a_value_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Measured: a 200 with a `text/html` body makes `create()` return a `str`.
    # Without the guard this is an AttributeError out of a route.
    _install(monkeypatch, _AnswersWith("<html>gateway</html>"))

    with pytest.raises(ValueError, match="no choices"):
        await stylist.suggest_looks(WARDROBE, _context())


@pytest.mark.asyncio
async def test_truncated_json_is_a_value_error(monkeypatch: pytest.MonkeyPatch) -> None:
    # json.JSONDecodeError subclasses ValueError, so a truncated answer and an
    # empty one are one exception type for 2.7 to catch.
    _install(monkeypatch, _AnswersWith(_completion('{"looks": [')))

    with pytest.raises(ValueError):
        await stylist.suggest_looks(WARDROBE, _context())


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        '{"unexpected": true}',
        "[]",
        '{"looks": [{"occasion": "work"}], "missing_pieces": [], "message": "x"}',
    ],
)
async def test_an_answer_of_the_wrong_shape_is_a_value_error(
    monkeypatch: pytest.MonkeyPatch, payload: str
) -> None:
    _install(monkeypatch, _AnswersWith(_completion(payload)))

    with pytest.raises(ValueError, match="documented shape"):
        await stylist.suggest_looks(WARDROBE, _context())


@pytest.mark.asyncio
async def test_a_provider_exception_escapes_untouched(monkeypatch: pytest.MonkeyPatch) -> None:
    """`ValueError` means the model answered unusably; a provider exception means
    no answer arrived. 2.7 tells them apart, so this module does not merge
    them — `DECISIONS.md` 086's split, applied to the second contract."""

    class _Refuses:
        async def create(self, **kwargs: Any) -> Any:
            raise APIConnectionError(request=None)  # type: ignore[arg-type]

    _install(monkeypatch, _Refuses())

    with pytest.raises(APIConnectionError):
        await stylist.suggest_looks(WARDROBE, _context())


# --- the typed answer -------------------------------------------------------


@pytest.mark.asyncio
async def test_a_documented_answer_parses_into_the_typed_response(
    recorded: _RecordingCompletions,
) -> None:
    answer = await stylist.suggest_looks(WARDROBE, _context())

    assert len(answer.looks) == 1
    assert answer.looks[0].title == "Morning meetings"
    assert answer.looks[0].item_ids == (TOP_ID, JEANS_ID, BOOTS_ID, BLAZER_ID)
    assert answer.missing_pieces == ()
    assert answer.message == "One look."


@pytest.mark.asyncio
async def test_missing_pieces_parse_into_typed_objects(monkeypatch: pytest.MonkeyPatch) -> None:
    piece = {
        "category": "shoes",
        "description": "a neutral closed shoe",
        "reason": "no water-resistant option suitable for the rainy day",
    }
    _install(monkeypatch, _AnswersWith(_completion(json.dumps(_answer(missing_pieces=[piece])))))

    answer = await stylist.suggest_looks(WARDROBE, _context())

    assert answer.missing_pieces == (stylist.MissingPiece(**piece),)


@pytest.mark.asyncio
async def test_returned_ids_are_not_normalised_here(monkeypatch: pytest.MonkeyPatch) -> None:
    # Case-folding what the model sends back is `validate_look_response`'s at
    # 2.5, and so is deciding whether an id is real. `DECISIONS.md` 156.
    lowered = _answer(looks=[dict(_answer()["looks"][0], item_ids=["a3f9k2"])])
    _install(monkeypatch, _AnswersWith(_completion(json.dumps(lowered))))

    answer = await stylist.suggest_looks(WARDROBE, _context())

    assert answer.looks[0].item_ids == ("a3f9k2",)


def test_the_response_is_immutable() -> None:
    look = stylist.Look(title="t", item_ids=(), reasoning="r", weather_note="w")

    # `title` rather than `occasion`, which 4.3 removed: setting an attribute
    # that does not exist raises `AttributeError` on a slotted class too, so the
    # old spelling would have gone on passing without testing immutability at
    # all. `DECISIONS.md` 163 repointed this same test once before.
    with pytest.raises(AttributeError):
        look.title = "evening"  # type: ignore[misc]


# --- the trip message, and the trip fake ------------------------------------


COLD_RULE = "Outerwear is REQUIRED, warmth 3-4."

# The fake rotates its picks by the day index, so a trip needs more than one of
# something to vary. Four items is the single-day wardrobe above; this adds a
# second top and a second bottom, which is the smallest wardrobe that can dress
# three days without repeating a whole look.
TOP_TWO = _item("TANK55", category="top", subcategory="tank")
JEANS_TWO = _item("SHTS47", category="bottom", subcategory="shorts")
TRIP_WARDROBE = [TOP, JEANS, BOOTS, BLAZER, TOP_TWO, JEANS_TWO]


def _trip_day(number: int, slot: str = "day", **overrides: Any) -> stylist.TripDay:
    fields: dict[str, Any] = {
        "day": number,
        "slot": slot,
        "date": datetime.date(2026, 3, 13 + number),
        "occasion": "work",
        "forecast_summary": SUMMARY,
        "weather_rule": RULE,
    }
    return stylist.TripDay(**(fields | overrides))


def _trip_context(days: int = 4, **overrides: Any) -> stylist.TripContext:
    fields: dict[str, Any] = {
        "destination": "Berlin",
        "days": tuple(_trip_day(number) for number in range(1, days + 1)),
        "reuse_target": 12,
    }
    return stylist.TripContext(**(fields | overrides))


def test_the_trip_message_carries_one_line_per_slot_in_the_documents_order() -> None:
    message = stylist._user_message(WARDROBE, _trip_context(days=2))

    assert "Destination: Berlin" in message
    assert "Dates: 2026-03-14 to 2026-03-15 (2 days)" in message
    assert f"Day 1 day | work | {SUMMARY} | {RULE}" in message
    assert f"Day 2 day | work | {SUMMARY} | {RULE}" in message
    assert "Build one look per line above — 2 looks for 2 days." in message


def test_a_date_with_an_evening_writes_two_lines_and_counts_as_one_day() -> None:
    # The two numbers part company here: three looks over two dates. The date
    # line counts days because it is about the trip's length; the build line
    # counts looks because that is what is being asked for.
    context = stylist.TripContext(
        destination="Berlin",
        days=(_trip_day(1), _trip_day(1, slot="evening", occasion="evening"), _trip_day(2)),
        reuse_target=12,
    )

    message = stylist._user_message(WARDROBE, context)

    assert "Dates: 2026-03-14 to 2026-03-15 (2 days)" in message
    assert f"Day 1 day | work | {SUMMARY} | {RULE}" in message
    assert f"Day 1 evening | evening | {SUMMARY} | {RULE}" in message
    assert "Build one look per line above — 3 looks for 2 days." in message


def test_both_slots_of_one_date_carry_the_same_weather_sentence() -> None:
    # One forecast row per calendar day, so the evening is dressed against the
    # afternoon's numbers. What separates the two looks is the occasion, which
    # moves formality rather than warmth. `DECISIONS.md` 225.
    context = stylist.TripContext(
        destination="Berlin",
        days=(
            _trip_day(1, weather_rule=COLD_RULE),
            _trip_day(1, slot="evening", occasion="evening", weather_rule=COLD_RULE),
        ),
        reuse_target=12,
    )

    # `Day ` rather than the pipe: the serialised wardrobe above is pipe-separated
    # too, and this is asking about the day list alone.
    lines = [
        line
        for line in stylist._user_message(WARDROBE, context).splitlines()
        if line.startswith("Day ")
    ]

    assert len(lines) == 2
    assert all(line.endswith(COLD_RULE) for line in lines)


def test_the_packing_constraint_asks_for_reuse_between_the_slots_of_one_day() -> None:
    # Prompt text and not a numbered rule: a hiking day before a formal dinner
    # has no honest shared garment, and refusing that answer would spend the
    # retry and then `502` on the one plan that obeyed every other instruction.
    # `DECISIONS.md` 193's argument for the reuse target, one slot along.
    message = stylist._user_message(WARDROBE, _trip_context(days=2))

    assert "Where a day has both a day and an" in message
    assert "evening look, reuse items between the two wherever the weather rule and" in message


def test_the_trip_message_states_the_reuse_target_as_a_number() -> None:
    # Without an explicit numeric target the model reuses almost nothing, which
    # is the finding `STAGE-4`'s prompt-tuning note is built on.
    message = stylist._user_message(WARDROBE, _trip_context(days=4))

    assert "Aim for at most 12 distinct items across 4 days." in message


def test_the_trip_message_omits_notes_entirely_when_there_are_none() -> None:
    # `_outerwear_line`'s rule: a line printed about a field the user did not
    # send is an instruction nobody gave. `DECISIONS.md` 158.
    assert "Notes:" not in stylist._user_message(WARDROBE, _trip_context())
    assert "Notes: one dinner out" in stylist._user_message(
        WARDROBE, _trip_context(notes="one dinner out")
    )


def test_a_trip_message_carries_the_wardrobe_and_the_profile_like_any_other() -> None:
    message = stylist._user_message(
        WARDROBE, _trip_context(height_cm=165, preferences="- Liked: relaxed tops")
    )

    assert f"WARDROBE ({len(WARDROBE)} items):" in message
    assert "Height: 165 cm." in message
    assert "- Liked: relaxed tops" in message


@pytest.mark.asyncio
async def test_the_fake_builds_one_look_per_entry_numbered_in_order(fake: None) -> None:
    answer = await stylist.suggest_looks(WARDROBE, _trip_context(days=3))

    assert [(look.day, look.slot) for look in answer.looks] == [
        (1, "day"),
        (2, "day"),
        (3, "day"),
    ]


@pytest.mark.asyncio
async def test_the_fake_gives_a_two_slot_day_two_different_looks(fake: None) -> None:
    # The rotation is keyed on the entry index and not on `day.day`, which is
    # what stops a date's two looks being identical — rule 11 refuses that, and
    # the flag exists to make E2E journeys deterministic rather than to `502`.
    context = stylist.TripContext(
        destination="Berlin",
        days=(_trip_day(1), _trip_day(1, slot="evening", occasion="evening")),
        reuse_target=12,
    )

    answer = await stylist.suggest_looks(TRIP_WARDROBE, context)

    assert [(look.day, look.slot) for look in answer.looks] == [(1, "day"), (1, "evening")]
    assert len({frozenset(look.item_ids) for look in answer.looks}) == 2


@pytest.mark.asyncio
async def test_the_fake_never_repeats_a_whole_look(fake: None) -> None:
    # Rule 11 under `USE_FAKE_AI`: picking the first of every category every day
    # returns N identical looks, which is two failed attempts and a `502` on the
    # one path built to make E2E journeys deterministic.
    answer = await stylist.suggest_looks(TRIP_WARDROBE, _trip_context(days=2))

    assert len({frozenset(look.item_ids) for look in answer.looks}) == 2


@pytest.mark.asyncio
async def test_a_wardrobe_too_small_to_vary_still_repeats_and_this_is_the_known_limit(
    fake: None,
) -> None:
    # Stated rather than discovered: rotation cannot invent combinations a
    # wardrobe does not hold, so one top and one bottom dress every day the same
    # way and rule 11 rejects the plan. The demo wardrobe's 64 items are far past
    # this; a four-item fixture is not. `AUDITS.md` O-27's family.
    answer = await stylist.suggest_looks(WARDROBE, _trip_context(days=2))

    assert len({frozenset(look.item_ids) for look in answer.looks}) == 1


@pytest.mark.asyncio
async def test_the_fakes_packing_list_is_the_deduplicated_union_of_its_looks(fake: None) -> None:
    # Rule 5 in both directions, which the fake satisfies by deriving the list
    # from the looks rather than composing it separately.
    answer = await stylist.suggest_looks(TRIP_WARDROBE, _trip_context(days=3))

    worn = {item_id for look in answer.looks for item_id in look.item_ids}
    assert answer.packing_list is not None
    assert set(answer.packing_list) == worn
    assert len(answer.packing_list) == len(set(answer.packing_list))


@pytest.mark.asyncio
async def test_the_fake_packs_a_coat_when_the_day_requires_one(fake: None) -> None:
    # `AUDITS.md` **O-27 closes here.** The fake never picked outerwear, so every
    # request below 16°C failed rule 6 twice and answered `502` — four months of
    # the year on the single-day path, and near-certain across a fourteen-day
    # trip, which is what made a known bug a blocker for this task.
    context = stylist.TripContext(
        destination="Berlin",
        days=(_trip_day(1, weather_rule=COLD_RULE),),
        reuse_target=4,
    )

    answer = await stylist.suggest_looks(WARDROBE, context)

    assert BLAZER_ID in answer.looks[0].item_ids


@pytest.mark.asyncio
async def test_the_single_day_fake_packs_a_coat_too(fake: None) -> None:
    answer = await stylist.suggest_looks(WARDROBE, _context(weather_rule=COLD_RULE))

    assert BLAZER_ID in answer.looks[0].item_ids


@pytest.mark.asyncio
async def test_the_fake_still_obeys_an_explicit_no_coat(fake: None) -> None:
    # Rule 6 does not run when the user asked for no outerwear (`DECISIONS.md`
    # 158), so the fake must not add one either.
    answer = await stylist.suggest_looks(
        WARDROBE, _context(weather_rule=COLD_RULE, include_outerwear=False)
    )

    assert BLAZER_ID not in answer.looks[0].item_ids
