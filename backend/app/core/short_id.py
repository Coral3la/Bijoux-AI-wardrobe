# backend/app/core/short_id.py
"""The six-character identifier the AI layer uses instead of a UUID.

Imports no ORM and no session, on the same terms as `core/security.py`
(`DECISIONS.md` 038): the alphabet and the length are testable with no
database and no fixture.
"""

import secrets

# No 0/O and no 1/I/L. Only `short_id` is ever sent to or received from the
# model, and a character pair it can transcribe wrongly is a hallucinated item.
ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
SHORT_ID_LENGTH = 6


def generate_short_id() -> str:
    return "".join(secrets.choice(ALPHABET) for _ in range(SHORT_ID_LENGTH))
