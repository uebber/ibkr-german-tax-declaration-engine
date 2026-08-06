"""
A forward split on a position carried in from the previous year.

Shape taken from a real case in the maintainer's data whose EoY reconciliation
fails, reduced to its arithmetic and re-expressed with synthetic instruments
and quantities. The point of the
scenario is that it is *fully determined*: the start-of-year quantity is
authoritative (reconcile_with_soy_position pins the ledger to the reported SoY
in every branch, so the previous year's history can only influence cost basis
and acquisition dates), the year's own trades are complete, and the split ratio
is unambiguous. Given a carried-in position, one pre-split buy, a forward split and a sell of
the whole post-split position, the end-of-year quantity can only be zero.

legal_basis: infrastructure/quantity tracking. Nothing here turns on tax law —
but every §20 Abs. 2 figure for the asset is computed from this ledger, so a
quantity that survives the year that should not means at least one disposal was
matched against the wrong lots.
"""
from decimal import Decimal

import pytest

from tests.support.base import FifoTestCaseBase
from tests.support.mock_providers import MockECBExchangeRateProvider

ACCOUNT = "U_SPLIT_TEST"
ISIN = "US000000SPL1"
SYMBOL = "SPLT"
DESC = "SPLIT TEST INC"
CONID = "CONSPLT"


def _trade(date, qty, price, txid, open_close):
    return [ACCOUNT, "EUR", "STK", "COMMON", SYMBOL, DESC, ISIN,
            "", "", "", date, str(qty), str(price), "0", "EUR",
            "BUY" if qty > 0 else "SELL", txid, "", "", CONID, "", "1", open_close]


def _position(qty, cost_basis):
    return [ACCOUNT, "EUR", "STK", "COMMON", SYMBOL, DESC, ISIN,
            Decimal(qty), Decimal("0"), Decimal("10"), Decimal(cost_basis),
            "", CONID, "", Decimal("1")]


class TestForwardSplitAcrossSoy(FifoTestCaseBase):

    def _run(self, positions_end_qty):
        corp_actions = [[
            ACCOUNT, SYMBOL, f"{SYMBOL}(={ISIN}) SPLIT 20 FOR 1 ({SYMBOL}, {DESC}, {ISIN})",
            ISIN, "2023-06-06", "", "FS", "900034843", CONID, "", "",
            "EUR", "0", "0", "0", "95",
        ]]
        return self._run_pipeline(
            trades_data=[
                _trade("20230201", 1, 100.00, "T_PRE", "O"),      # pre-split buy -> 5 held
                _trade("20230607", -100, 5.00, "T_POST", "C"),    # sells the whole post-split position
            ],
            positions_start_data=[_position("4", "400")],          # SoY: 4 shares
            positions_end_data=([_position(positions_end_qty, "0")]
                                if positions_end_qty != "0" else []),
            corporate_actions_data=corp_actions,
            custom_rate_provider=MockECBExchangeRateProvider(Decimal("1.0")),
            tax_year=2023,
        )

    def test_position_is_fully_closed_after_the_split(self):
        """SoY 4 + 1 = 5; 5 x 20 = 100; sell 100 -> 0.

        The broker reports 0, and the engine must agree. If it does not, the
        sell was matched against a ledger the split left in the wrong state,
        and the realised gain reported for it is wrong too.
        """
        out = self._run(positions_end_qty="0")
        assert out.eoy_mismatch_error_count == 0

        ledger_quantities = {
            asset.get_classification_key(): asset.eoy_quantity
            for asset in out.final_assets_by_id.values()
        }
        assert any(ISIN in key for key in ledger_quantities), ledger_quantities

        realized = [r for r in out.realized_gains_losses]
        assert realized, "selling the whole position must realise a gain or loss"
        total_qty = sum(r.quantity_realized for r in realized)
        assert total_qty == Decimal("100"), (
            f"the disposal must consume the full post-split quantity, got {total_qty}")
