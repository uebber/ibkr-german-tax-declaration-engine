"""
C5 — foreign-currency fees consume currency FIFO lots, results-oriented.

legal_basis: BMF-Schreiben 19.05.2022 (Fremdwährungskonten), Rz. 131
(reference/bmf-guidance/fremdwaehrung-konten.md): SPENDING foreign currency —
including paying a broker fee — is a Veräußerung of the currency; the FX
gain/loss is the difference between the EUR value at consumption and the EUR
acquisition cost of the consumed FIFO lots (§20 Abs. 2 S. 1 Nr. 7 EStG on
interest-bearing accounts).

Scenario (hand-computed): 10000 USD minted by a stock sale at 1,00 EUR/USD
(currency basis 10000 EUR, stock G/L exactly 0); a 500-USD broker fee paid
when the rate is 1,20 EUR/USD consumes 500 USD: value at consumption 600 EUR
vs basis 500 EUR -> FX GAIN 100,00. The legal review found no test reaching
the fee-consumption path. All data synthetic.
"""
import datetime
from decimal import Decimal

import pytest

from src.domain.enums import AssetCategory
from tests.support.base import FifoTestCaseBase
from tests.support.mock_providers import MockECBExchangeRateProvider

ACCT = "U10000001"
TAX_YEAR = 2025
ISIN = "US000000QQQ1"


class TestFeeConsumesCurrencyLots(FifoTestCaseBase):
    def test_usd_fee_realises_fx_gain_against_minted_lots(self):
        rate_provider = MockECBExchangeRateProvider(
            foreign_to_eur_init_value=Decimal("1.00"),
            currency_schedules={"USD": [
                (datetime.date(2025, 1, 1), Decimal("1.00")),
                (datetime.date(2025, 6, 1), Decimal("1.20")),
            ]},
        )
        trades = [
            # Sell 100 QQQ @ 100 USD on 2025-03-01 (rate 1,00): proceeds
            # 10000 USD = 10000 EUR, equal to the SoY basis -> stock G/L 0.
            [ACCT, "USD", "STK", "COMMON", "QQQ1", ISIN, ISIN,
             None, None, None, "2025-03-01", Decimal("-100"), Decimal("100"),
             Decimal("0"), "USD", "SELL", "T1", None, None, "CONQQQ1", None,
             Decimal("1"), "C"],
        ]
        pos_soy = [[ACCT, "USD", "STK", "COMMON", "QQQ1", ISIN, ISIN,
                    Decimal("100"), Decimal("10000"), Decimal("100"),
                    Decimal("10000"), None, "CONQQQ1", None, Decimal("1")]]
        cash_tx = [
            # 500-USD broker fee on 2025-06-15 (rate 1,20).
            [ACCT, "USD", "STK", "COMMON", "QQQ1",
             "BALANCE OF MONTHLY MINIMUM FEE", "2025-06-15",
             Decimal("-500"), "Other Fees", "CONQQQ1", None, ISIN, "US", "F1"],
        ]
        cash_balance = [[ACCT, "USD", "20250101", "20251231",
                         Decimal("0"), Decimal("9500")]]

        out = self._run_pipeline(
            trades_data=trades,
            positions_start_data=pos_soy,
            positions_end_data=[],
            cash_transactions_data=cash_tx,
            cash_balance_data=cash_balance,
            custom_rate_provider=rate_provider,
            tax_year=TAX_YEAR,
        )

        assert out.eoy_mismatch_error_count == 0
        # The stock sale is exactly G/L-neutral by construction.
        stock_rgls = [r for r in out.realized_gains_losses
                      if r.asset_category_at_realization == AssetCategory.STOCK]
        assert sum(r.gross_gain_loss_eur for r in stock_rgls) == Decimal("0.00")
        # The fee consumed 500 USD acquired at 1,00 and spent at 1,20:
        # FX gain = 500 × (1,20 − 1,00) = 100,00 — the Rz. 131 result.
        fx_rgls = [r for r in out.realized_gains_losses
                   if r.asset_category_at_realization == AssetCategory.CASH_BALANCE]
        assert fx_rgls, "the fee must consume currency lots and realise FX"
        assert sum(r.gross_gain_loss_eur for r in fx_rgls) == Decimal("100.00")
        assert all(r.realization_date == "2025-06-15" for r in fx_rgls), \
            "the FX realization happens when the currency is SPENT (fee date)"
