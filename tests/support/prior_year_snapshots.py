# tests/support/prior_year_snapshots.py
"""Building the preceding year's snapshots for a fixture fund.

The Vorabpauschale declared in VZ Y is the one computed for calendar Y-1
(18 Abs. 3 InvStG), so it reads three snapshots that are not the tax year's own:
the start of Y-1 (the Satz 2 Ruecknahmepreis), the close of Y-1 (the Satz 3 cap
price and the Rz. 18.4 unit count), and the close of Y-2 (the units the year
opened with). Each is recorded per `(account, asset)`, like every other snapshot
the engine reads.

These builders put a fixture fund in ONE account, because the tests that use
them are about 18 InvStG and not about where a holding sits. What a fund held in
two accounts does to the person's figure is `tests/test_person_level_snapshot.py`.
"""
from datetime import date
from decimal import Decimal
from typing import Optional
import uuid

from src.domain.assets import PositionSnapshot, SnapshotsByAccount
from src.utils.account_utils import account_key

# The account these fixtures book their holdings in. Any non-empty id will do;
# what matters is that it is one account and that it is stated rather than
# implied, so a test reading a registry row knows which key to reach for.
FIXTURE_ACCOUNT = account_key("U1234567")


def snapshot_row(asset_id: uuid.UUID,
                 *,
                 quantity: Optional[Decimal] = None,
                 position_value: Optional[Decimal] = None,
                 mark_price: Optional[Decimal] = None,
                 mark_price_currency: Optional[str] = None,
                 mark_price_date: Optional[date] = None,
                 account: str = FIXTURE_ACCOUNT) -> SnapshotsByAccount:
    """One account's snapshot of one asset, as a registry of its own.

    Returned as a registry rather than a bare record so a caller can hand it
    straight to the engine, and merge a second account's row in with `|` where a
    scenario needs one.
    """
    return {(account, asset_id): PositionSnapshot(
        quantity=quantity,
        position_value=position_value,
        mark_price=mark_price,
        mark_price_currency=mark_price_currency,
        mark_price_date=mark_price_date,
    )}
