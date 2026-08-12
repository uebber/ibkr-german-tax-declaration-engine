# src/utils/account_utils.py
"""Per-Depot (per custody account) helpers.

FIFO is applied per single custody account. The Depot boundary comes from Tier 2 --
BMF-Schreiben vom 14.05.2025, GZ IV C 1 - S 2252/00075/016/070, Rz. 97 Satz 2 -- not from
the statute: § 20 Abs. 4 Satz 7 EStG supplies the FIFO fiction itself but never says "je
Depot". See reference/tax-law/estg-20-kapitalvermoegen.md for both, and for the open
question of whether that boundary transposes to a foreign broker's sub-accounts.

The engine keys securities FIFO ledgers by ``(account_key, asset_id)``, and a disposal
consumes the lots of the account it was made from. Events / positions without an account
(e.g. test fixtures or older exports) collapse to a single DEFAULT account, so
single-account behaviour is unchanged.

Currency ledgers use the same key shape and the same real account, but they get there by
a different route and the two must not be crossed. Securities are per Depot because
Rz. 97 draws that boundary for the Fifo rule of 20 Abs. 4 Satz 7 ([GT-ESTG20-013]), and
that provision cannot reach a currency balance (the GT-FX-008 correction). A currency
balance is per account because each account's is its own Kapitalforderung -- Rz. 131 2,
[GT-FX-009] -- so a move between two of them is a disposal and an acquisition, which one
pooled balance could not be.
"""
from typing import Optional

DEFAULT_ACCOUNT = "__DEFAULT__"


def account_key(account_id: Optional[str]) -> str:
    """Normalise an account id to a non-empty ledger key (DEFAULT when absent)."""
    if account_id is None:
        return DEFAULT_ACCOUNT
    s = str(account_id).strip()
    return s if s else DEFAULT_ACCOUNT
