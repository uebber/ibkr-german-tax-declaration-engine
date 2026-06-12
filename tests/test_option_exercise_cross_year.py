"""
Cross-year option exercise: the premium adjustment to the stock's cost basis
must survive into later tax years' SoY reconstruction.

legal_basis: §20 Abs. 4 S. 1 EStG / BMF Einzelfragen zur Abgeltungsteuer
(reference/bmf-guidance/abgeltungsteuer-einzelfragen.md, Options): on exercise
of a long call the option premium becomes part of the stock's acquisition
cost; on assignment of a short put the premium received reduces it. The
adjustment is part of the PERMANENT acquisition cost — a sale in a LATER tax
year must realise against the adjusted basis (same bug class as the
Einlagenrückgewähr cross-year carry: a cost-only mutation, invisible to the
quantity-based SoY reconciliation).

Results-oriented: synthetic CSVs in -> declared figures out, hand-computed.
The same scenarios WITHIN one tax year are already covered by the group-8
option lifecycle specs (OPT_CALL_EX_001 etc.); these pin the cross-year carry.
"""
from decimal import Decimal

import pytest

from src.domain.enums import TaxReportingCategory
from src.engine.loss_offsetting import LossOffsettingEngine
from tests.support.base import FifoTestCaseBase
from tests.support.option_helpers import (
    create_option_trade_data, create_stock_trade_data,
)
from tests.support.mock_providers import MockECBExchangeRateProvider

ACCT = "U10000001"
TAX_YEAR = 2025
STOCK_ISIN = "US000000XYZ1"
NO_COMMISSION = Decimal("0")


class _CrossYearOptionBase(FifoTestCaseBase):
    def _run(self, trades_data, positions_start, positions_end):
        out = self._run_pipeline(
            trades_data=trades_data,
            positions_start_data=positions_start,
            positions_end_data=positions_end,
            custom_rate_provider=MockECBExchangeRateProvider(Decimal("1.00")),
            tax_year=TAX_YEAR,
        )
        flv = LossOffsettingEngine(
            realized_gains_losses=out.realized_gains_losses,
            vorabpauschale_items=out.vorabpauschale_items,
            current_year_financial_events=out.processed_income_events,
            asset_resolver=out.asset_resolver,
            tax_year=TAX_YEAR,
        ).calculate_reporting_figures().form_line_values
        return out, flv

    @staticmethod
    def _stock_pos(qty, price, cost):
        """One positions row for the stock (column order = POSITIONS_FILE_HEADERS)."""
        from tests.support.csv_creators import create_positions_csv_string  # noqa: F401
        q, p = Decimal(qty), Decimal(price)
        return [ACCT, "EUR", "STK", "COMMON", "XYZ", STOCK_ISIN, STOCK_ISIN,
                q, q * p, p, Decimal(cost), None, "CONXYZ", None, Decimal("1")]


class TestLongCallExerciseCrossYear(_CrossYearOptionBase):
    def test_premium_carries_into_next_years_stock_basis(self):
        """2024: buy 1 call (premium 200), exercise -> receive 100 XYZ @ 50
        (basis 5000 + 200 = 5200). 2025: sell 100 @ 60 -> gain 800,00 on Z20.
        An engine that drops the premium adjustment in SoY reconstruction
        declares 1000,00 — OVERSTATING the gain by the premium."""
        trades = [
            create_option_trade_data(
                ACCT, "EUR", "XYZ 240620C00050000", "XYZ 20JUN24 50.0 C",
                "XYZ", "CONXYZ", "OPTXYZ1", Decimal("50"), "2024-06-20", "C",
                "2024-06-05", "BL", Decimal("1"), Decimal("2.00"),
                commission=NO_COMMISSION, transaction_id="O1"),
            create_option_trade_data(
                ACCT, "EUR", "XYZ 240620C00050000", "XYZ 20JUN24 50.0 C",
                "XYZ", "CONXYZ", "OPTXYZ1", Decimal("50"), "2024-06-20", "C",
                "2024-06-20", "SL", Decimal("1"), Decimal("0.00"),
                commission=NO_COMMISSION, transaction_id="O2", notes_codes="Ex"),
            create_stock_trade_data(
                ACCT, "EUR", "XYZ", "XYZ Inc", STOCK_ISIN, "CONXYZ",
                "2024-06-20", "BL", Decimal("100"), Decimal("50.00"),
                commission=NO_COMMISSION, transaction_id="S1", notes_codes="Ex"),
            create_stock_trade_data(
                ACCT, "EUR", "XYZ", "XYZ Inc", STOCK_ISIN, "CONXYZ",
                "2025-04-01", "SL", Decimal("100"), Decimal("60.00"),
                commission=NO_COMMISSION, transaction_id="S2"),
        ]
        # SoY 2025: IBKR reports the premium-adjusted basis (5200).
        pos_soy = [self._stock_pos("100", "55", "5200")]
        out, flv = self._run(trades, pos_soy, [])

        assert out.eoy_mismatch_error_count == 0
        assert flv[TaxReportingCategory.ANLAGE_KAP_AKTIEN_GEWINN] == Decimal("800.00"), \
            "stock basis must carry the exercised call's premium (5200), not 5000"


class TestShortPutAssignmentCrossYear(_CrossYearOptionBase):
    def test_received_premium_reduces_next_years_stock_basis(self):
        """2024: sell 1 put short (premium received 300), assigned -> buy 100
        XYZ @ 50 (basis 5000 − 300 = 4700). 2025: sell 100 @ 60 -> gain
        1300,00 on Z20. Dropping the adjustment declares 1000,00 —
        UNDERSTATING the gain by the received premium."""
        trades = [
            create_option_trade_data(
                ACCT, "EUR", "XYZ 240620P00050000", "XYZ 20JUN24 50.0 P",
                "XYZ", "CONXYZ", "OPTXYZ2", Decimal("50"), "2024-06-20", "P",
                "2024-06-05", "SSO", Decimal("1"), Decimal("3.00"),
                commission=NO_COMMISSION, transaction_id="O1"),
            create_option_trade_data(
                ACCT, "EUR", "XYZ 240620P00050000", "XYZ 20JUN24 50.0 P",
                "XYZ", "CONXYZ", "OPTXYZ2", Decimal("50"), "2024-06-20", "P",
                "2024-06-20", "BSC", Decimal("1"), Decimal("0.00"),
                commission=NO_COMMISSION, transaction_id="O2", notes_codes="A"),
            create_stock_trade_data(
                ACCT, "EUR", "XYZ", "XYZ Inc", STOCK_ISIN, "CONXYZ",
                "2024-06-20", "BL", Decimal("100"), Decimal("50.00"),
                commission=NO_COMMISSION, transaction_id="S1", notes_codes="A"),
            create_stock_trade_data(
                ACCT, "EUR", "XYZ", "XYZ Inc", STOCK_ISIN, "CONXYZ",
                "2025-04-01", "SL", Decimal("100"), Decimal("60.00"),
                commission=NO_COMMISSION, transaction_id="S2"),
        ]
        pos_soy = [self._stock_pos("100", "55", "4700")]
        out, flv = self._run(trades, pos_soy, [])

        assert out.eoy_mismatch_error_count == 0
        assert flv[TaxReportingCategory.ANLAGE_KAP_AKTIEN_GEWINN] == Decimal("1300.00"), \
            "stock basis must be reduced by the assigned put's received premium (4700), not 5000"
