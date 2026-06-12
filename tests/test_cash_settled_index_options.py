"""
C1 — cash-settled index options (Barausgleich), results-oriented:
Options_EAE + Trades CSVs in -> declared figures out, hand-computed.

legal_basis:
  - §20 Abs. 2 S. 1 Nr. 3a EStG: gains from Barausgleich of Termingeschäfte
    (reference/tax-law/estg-20-kapitalvermoegen.md, Satz 1 Nr. 3 / 3a).
  - BFH VIII R 55/13: Barausgleich paid by the STILLHALTER is a loss from a
    Termingeschäft under Nr. 3a (not a reduction of the Nr. 11 premium).
  - VZ-2025 form rules (reference/tax-forms/anlage-kap-zeilen.md): derivative
    gains flow into Zeile 19, derivative losses into Zeile 22 (Z21/Z24
    abolished; the §20 Abs. 6 S. 5 cap is retroactively repealed).

STRICT SPLIT (user decision 2026-06-12): the Stillhalter's premium and the
Barausgleich are SEPARATE tax events — Nr. 11 premium income (+300) and a
Nr. 3a settlement loss (−700) — not one netted loss. Zeile 19 nets to −400
either way; the gross Zeile-22 loss declaration must show 700, not 400.

All data synthetic; index option = option without an underlying position
(no UnderlyingConid), which is what routes it to the cash-settlement path.
"""
import csv
from decimal import Decimal

import pytest

from src.pipeline_runner import run_core_processing_pipeline
from src.domain.enums import TaxReportingCategory
from src.engine.loss_offsetting import LossOffsettingEngine
from src.parsers.column_validator import OPTIONS_EAE_COLUMNS
from tests.support.base import FifoTestCaseBase
from tests.support.option_helpers import create_option_trade_data
from tests.support.csv_creators import create_trades_csv_string
from tests.support.mock_providers import MockECBExchangeRateProvider

ACCT = "U10000001"
TAX_YEAR = 2025
NO_COMMISSION = Decimal("0")


def _eae_row(symbol, conid, putcall, strike, expiry, date, tx_type, qty,
             proceeds):
    return [ACCT, "EUR", "1", "OPT", symbol, f"{symbol} index option", conid,
            None, None, "IDX", "100", strike, expiry, putcall, date, tx_type,
            qty, "0", proceeds, "0", "0", "0"]


def _write_eae(path, rows):
    with open(path, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(list(OPTIONS_EAE_COLUMNS))
        for r in rows:
            w.writerow(["" if c is None else str(c) for c in r])


class _IndexOptionBase(FifoTestCaseBase):
    def _run(self, trades_rows, eae_rows):
        import os
        p = self.config_paths
        with open(p["trades"], "w", encoding="utf-8-sig") as fh:
            fh.write(create_trades_csv_string(trades_rows))
        eae_path = os.path.join(p["temp_dir_root"], "options_eae.csv")
        _write_eae(eae_path, eae_rows)
        from tests.support.csv_creators import (
            create_cash_transactions_csv_string, create_corporate_actions_csv_string,
            create_cash_balance_csv_string, create_positions_csv_string,
        )
        for path, gen in [(p["cash"], create_cash_transactions_csv_string),
                          (p["corp_actions"], create_corporate_actions_csv_string),
                          (p["cash_balance"], create_cash_balance_csv_string),
                          (p["pos_start"], create_positions_csv_string),
                          (p["pos_end"], create_positions_csv_string)]:
            with open(path, "w", encoding="utf-8-sig") as fh:
                fh.write(gen([]))
        out = run_core_processing_pipeline(
            trades_file_path=p["trades"],
            cash_transactions_file_path=p["cash"],
            positions_start_file_path=p["pos_start"],
            positions_end_file_path=p["pos_end"],
            corporate_actions_file_path=p["corp_actions"],
            interactive_classification_mode=False,
            tax_year_to_process=TAX_YEAR,
            custom_rate_provider=MockECBExchangeRateProvider(Decimal("1.00")),
            cash_balance_file_path=p["cash_balance"],
            options_eae_file_path=eae_path,
        )
        flv = LossOffsettingEngine(
            realized_gains_losses=out.realized_gains_losses,
            vorabpauschale_items=out.vorabpauschale_items,
            current_year_financial_events=out.processed_income_events,
            asset_resolver=out.asset_resolver,
            tax_year=TAX_YEAR,
        ).calculate_reporting_figures().form_line_values
        return out, flv


class TestLongIndexOptionCashSettlement(_IndexOptionBase):
    def test_itm_settlement_gain_flows_into_zeile_19(self):
        """Buy 1 IDX put (premium 2,00 × 100 = 200); cash-settled ITM for
        +500. Gain = 500 − 200 = 300 -> Termingeschäftsgewinn (Nr. 3a),
        VZ 2025: Zeile 19 = 300,00; no stock lines touched."""
        opt = dict(symbol="IDX 250620P04000000", desc="IDX 20JUN25 4000 P",
                   conid="OPTIDX1", strike=Decimal("4000"), expiry="2025-06-20",
                   putcall="P")
        trades = [
            create_option_trade_data(
                ACCT, "EUR", opt["symbol"], opt["desc"], "IDX", "",
                opt["conid"], opt["strike"], opt["expiry"], opt["putcall"],
                "2025-03-01", "BL", Decimal("1"), Decimal("2.00"),
                commission=NO_COMMISSION, transaction_id="O1"),
            create_option_trade_data(
                ACCT, "EUR", opt["symbol"], opt["desc"], "IDX", "",
                opt["conid"], opt["strike"], opt["expiry"], opt["putcall"],
                "2025-06-20", "SL", Decimal("1"), Decimal("0.00"),
                commission=NO_COMMISSION, transaction_id="O2", notes_codes="Ex"),
        ]
        eae = [
            _eae_row(opt["symbol"], opt["conid"], "P", "4000", "2025-06-20",
                     "2025-06-20", "Exercise", "-1", "0"),
            _eae_row(opt["symbol"], opt["conid"], "P", "4000", "2025-06-20",
                     "2025-06-20", "Cash Settlement", "0", "500"),
        ]
        out, flv = self._run(trades, eae)
        assert out.eoy_mismatch_error_count == 0
        assert flv[TaxReportingCategory.ANLAGE_KAP_AUSLAENDISCHE_KAPITALERTRAEGE_GESAMT] == Decimal("300.00")
        assert flv.get(TaxReportingCategory.ANLAGE_KAP_AKTIEN_GEWINN, Decimal("0")) == Decimal("0.00")
        assert flv.get(TaxReportingCategory.ANLAGE_KAP_SONSTIGE_VERLUSTE, Decimal("0")) == Decimal("0.00")


class TestShortIndexOptionCashSettlement(_IndexOptionBase):
    def test_stillhalter_settlement_net_effect(self):
        """Write 1 IDX call (premium received 3,00 × 100 = 300); assigned,
        Barausgleich paid 700. Strict split (BFH VIII R 55/13): the premium
        is Nr. 11 income (+300), the settlement a separate Nr. 3a loss
        (−700). VZ 2025: Zeile 19 = −400,00 net, Zeile 22 = 700,00 gross."""
        opt = dict(symbol="IDX 250620C04000000", desc="IDX 20JUN25 4000 C",
                   conid="OPTIDX2", strike=Decimal("4000"), expiry="2025-06-20",
                   putcall="C")
        trades = [
            create_option_trade_data(
                ACCT, "EUR", opt["symbol"], opt["desc"], "IDX", "",
                opt["conid"], opt["strike"], opt["expiry"], opt["putcall"],
                "2025-02-01", "SSO", Decimal("1"), Decimal("3.00"),
                commission=NO_COMMISSION, transaction_id="O1"),
            create_option_trade_data(
                ACCT, "EUR", opt["symbol"], opt["desc"], "IDX", "",
                opt["conid"], opt["strike"], opt["expiry"], opt["putcall"],
                "2025-06-20", "BSC", Decimal("1"), Decimal("0.00"),
                commission=NO_COMMISSION, transaction_id="O2", notes_codes="A"),
        ]
        eae = [
            _eae_row(opt["symbol"], opt["conid"], "C", "4000", "2025-06-20",
                     "2025-06-20", "Assignment", "1", "0"),
            _eae_row(opt["symbol"], opt["conid"], "C", "4000", "2025-06-20",
                     "2025-06-20", "Cash Settlement", "0", "-700"),
        ]
        out, flv = self._run(trades, eae)
        assert out.eoy_mismatch_error_count == 0
        # Zeile 19 is the NET under VZ-2025 rules: +300 premium − 700 loss.
        assert flv[TaxReportingCategory.ANLAGE_KAP_AUSLAENDISCHE_KAPITALERTRAEGE_GESAMT] == Decimal("-400.00"), \
            "Stillhalter Barausgleich: net derivative result must be premium 300 − settlement 700"
        # STRICT SPLIT: the gross Zeile-22 declaration is the FULL Nr. 3a
        # settlement loss (700), with the Nr. 11 premium (+300) among Z19's
        # positive components — not one netted 400 loss.
        assert flv[TaxReportingCategory.ANLAGE_KAP_SONSTIGE_VERLUSTE] == Decimal("700.00"), \
            "Barausgleich is a separate Nr. 3a loss; it must not be netted against the Nr. 11 premium"
