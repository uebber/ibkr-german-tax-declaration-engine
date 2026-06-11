# src/utils/account_utils.py
"""Per-Depot (per custody account) helpers.

German FIFO (§20 Abs. 4) is applied per custody account. The engine keys FIFO ledgers by
``(account_key, asset_id)``. Events / positions without an account (e.g. test fixtures or
older exports) collapse to a single DEFAULT account, so single-account behaviour is unchanged.
"""
from typing import Optional

DEFAULT_ACCOUNT = "__DEFAULT__"


def account_key(account_id: Optional[str]) -> str:
    """Normalise an account id to a non-empty ledger key (DEFAULT when absent)."""
    if account_id is None:
        return DEFAULT_ACCOUNT
    s = str(account_id).strip()
    return s if s else DEFAULT_ACCOUNT
