"""No database: a short_id is six characters drawn from a fixed alphabet.
Collision retry needs the uq_items_short_id constraint to detect a collision at
all, so it is an integration behaviour and belongs to task 0.10."""

import re

from app.core.short_id import ALPHABET, SHORT_ID_LENGTH, generate_short_id

AMBIGUOUS = "0O1IL"


def test_the_alphabet_excludes_every_character_pair_a_model_can_confuse() -> None:
    assert not set(ALPHABET) & set(AMBIGUOUS)


def test_the_alphabet_is_the_one_the_data_model_specifies() -> None:
    assert ALPHABET == "ABCDEFGHJKMNPQRSTUVWXYZ23456789"


def test_generates_six_characters() -> None:
    assert len(generate_short_id()) == SHORT_ID_LENGTH == 6


def test_generates_only_characters_from_the_alphabet() -> None:
    pattern = re.compile(f"^[{ALPHABET}]{{{SHORT_ID_LENGTH}}}$")
    for _ in range(500):
        assert pattern.match(generate_short_id())


def test_does_not_return_the_same_id_twice_in_a_thousand_draws() -> None:
    # 31**6 is 887,503,681, so a repeat here means the generator is not random
    # rather than that we were unlucky.
    assert len({generate_short_id() for _ in range(1000)}) == 1000
