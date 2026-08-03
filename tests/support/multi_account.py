# tests/support/multi_account.py
"""
Multi-account (per-Depot) test harness builders.

The YAML spec harness forces a single ClientAccountID, so per-Depot scenarios
(co-held securities, internal transfers, per-account cash) previously had to
hand-roll CSV writers in every test file. These builders centralize that:
row constructors with an EXPLICIT account for trades, positions, cash balances
and cash transactions, plus a writer that produces the canonical quoted-CSV
shape the parsers expect. (Corporate actions and Options_EAE have no builder
yet; only their column tuples are re-exported.)

Column orders are the canonical tuples from src/parsers/column_validator.py —
imported, not copied, so parser-format changes fail loudly here.

legal_basis: GT-ESTG20-012 with GT-ESTG20-013.
§20 Abs. 4 S. 7 EStG mandates FIFO for fungible securities in
Sammelverwahrung; the *per-Depot* dimension is administrative, not statutory —
BMF 14.05.2025 (GZ IV C 1 - S 2252/00075/016/070) Rz. 97 S. 2 applies FIFO
"auf das einzelne Depot bezogen", and Rz. 98 counts a sub-depot as a Depot.
Rz. 98 is why the account is an explicit per-row parameter here rather than a
global: the ledger key has to reach the finest account identifier IBKR reports.
Verbatim text, the Tier 1 / Tier 2 split, and the open question about whether
the Depot boundary transposes to a foreign broker are recorded in
reference/tax-law/estg-20-kapitalvermoegen.md, section "Abs. 4 -- Satz 7".
Do not restate the rule here; cite that file.
"""
import csv
import io
from decimal import Decimal
from typing import Any, List, Optional, Sequence

from src.parsers.column_validator import (
    TRADES_COLUMNS,
    CASH_TRANSACTIONS_COLUMNS,
    POSITIONS_COLUMNS,
    CORPORATE_ACTIONS_COLUMNS,
    CASH_BALANCE_COLUMNS,
)


def write_csv(path: str, headers: Sequence[str], rows: List[List[Any]]) -> None:
    """Write rows under the given canonical header (BOM-prefixed, all-quoted —
    the shape real IBKR exports and the parsers use)."""
    buf = io.StringIO()
    w = csv.writer(buf, quoting=csv.QUOTE_ALL)
    w.writerow(list(headers))
    for r in rows:
        w.writerow(["" if c is None else str(c) for c in r])
    with open(path, "w", encoding="utf-8-sig", newline="") as fh:
        fh.write(buf.getvalue())


def conid_for(isin: str) -> str:
    return "CON" + isin[:7]


def trade_row(account: str, isin: str, date: str, qty, price, side: str, open_close: str,
              tx_id: str, currency: str = "EUR", symbol: Optional[str] = None,
              asset_class: str = "STK", sub_category: str = "COMMON",
              commission="0", multiplier="1", notes: str = "") -> List[Any]:
    """One Trades row (TRADES_COLUMNS order). qty signed (+buy/-sell)."""
    return [account, currency, asset_class, sub_category, symbol or isin[:6],
            f"{symbol or isin[:6]} security", isin, None, None, None, date,
            Decimal(str(qty)), Decimal(str(price)), Decimal(str(commission)), currency,
            side, tx_id, notes, None, conid_for(isin), None, Decimal(str(multiplier)),
            open_close]


def position_row(account: str, isin: str, qty, cost, currency: str = "EUR",
                 price="100", symbol: Optional[str] = None) -> List[Any]:
    """One Positions row (POSITIONS_COLUMNS order) for SoY/EoY snapshots."""
    q = Decimal(str(qty))
    return [account, currency, "STK", "COMMON", symbol or isin[:6],
            f"{symbol or isin[:6]} security", isin, q, q * Decimal(str(price)),
            Decimal(str(price)), Decimal(str(cost)), None, conid_for(isin), None,
            Decimal("1")]


def cash_balance_row(account: str, currency: str, soy, eoy,
                     year: int = 2025) -> List[Any]:
    """One Cash_Balance row (CASH_BALANCE_COLUMNS order)."""
    return [account, currency, f"{year}0101", f"{year}1231",
            Decimal(str(soy)), Decimal(str(eoy))]


def cash_transaction_row(account: str, currency: str, amount, tx_type: str, date: str,
                         symbol: str = "", description: str = "", isin: str = "",
                         asset_class: str = "", sub_category: str = "",
                         country_code: str = "", tx_id: str = "") -> List[Any]:
    """One Cash_Transactions row (CASH_TRANSACTIONS_COLUMNS order)."""
    return [account, currency, asset_class, sub_category, symbol, description, date,
            Decimal(str(amount)), tx_type, conid_for(isin) if isin else "", "",
            isin, country_code, tx_id]


__all__ = [
    "write_csv", "conid_for", "trade_row", "position_row", "cash_balance_row",
    "cash_transaction_row",
    "TRADES_COLUMNS", "CASH_TRANSACTIONS_COLUMNS", "POSITIONS_COLUMNS",
    "CORPORATE_ACTIONS_COLUMNS", "CASH_BALANCE_COLUMNS",
]
