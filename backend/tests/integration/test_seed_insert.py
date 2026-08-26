"""What `scripts/seed_demo.py` writes for the demo account itself.

`tests/unit/test_seed_data.py` walks the committed item table without a
database. This is the other half and it is one row: the user, inserted the way
the script inserts it, so that a field dropped from that constructor is caught
here rather than at a defence. Task 1.10 recorded that nothing tested the
insert at all; this covers the part 2.2 added to it.
"""

from sqlalchemy.orm import Session

from app.models.user import User
from scripts.seed_demo import (
    DEMO_HOME_CITY,
    DEMO_HOME_LAT,
    DEMO_HOME_LON,
    DEMO_USER_ID,
    _insert,
)


def test_the_demo_account_is_seeded_with_a_home_location(db: Session) -> None:
    # No items: the user row is what this asserts, and an empty table keeps the
    # test to one insert. AUDITS.md O-20 measured that no row on the live
    # database had a home location, which left 2.12's weather strip with
    # nothing to show on the one account a visitor signs into.
    _insert(db, ())

    user = db.get(User, DEMO_USER_ID)
    assert user is not None
    assert user.home_city == DEMO_HOME_CITY
    assert user.home_lat is not None
    assert (round(user.home_lat, 2), round(user.home_lon or 0, 2)) == (
        DEMO_HOME_LAT,
        DEMO_HOME_LON,
    )
