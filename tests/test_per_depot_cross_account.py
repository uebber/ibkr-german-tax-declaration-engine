"""
Cross-account (per-Depot) integration tests — §20 Abs. 4 S. 7 EStG (FIFO per custody account).

legal_basis: §20 Abs. 4 S. 7 EStG (reference/tax-law/estg-20-kapitalvermoegen.md) — FIFO is
applied per Depot, not per person; BMF guidance on Fremdwährung
(reference/bmf-guidance/fremdwaehrung-konten.md) for the per-Depot FX scenario.

These build multi-account input CSVs directly (the shared YAML harness forces a single
ClientAccountID, so it can't express these scenarios) and run the full pipeline. They pin the
behaviours that a green single-account suite missed:

  - a security co-held in two Depots and sold from one consumes only THAT Depot's lots
    (per-Depot result differs from the account-agnostic/merged result);
  - a foreign currency disposed from an account that had NO opening balance still realises FX
    (the CHF/HKD regression: it used to be silently skipped);
  - single-account input still collapses to the identical result (backward compatibility).

Ported as spec from oracle/per-depot-fifo (rework2-plan reuse policy); the internal-transfer
classes follow with the transfer feature (B8b). Nothing here modifies existing tests or
shared helpers.
"""
import csv
import os
from decimal import Decimal

import pytest

from src.pipeline_runner import run_core_processing_pipeline, ProcessingOutput
from src.domain.enums import AssetCategory, RealizationType
from src.parsers.column_validator import (
    TRADES_COLUMNS, POSITIONS_COLUMNS, CASH_BALANCE_COLUMNS,
)
from tests.support.base import FifoTestCaseBase
from tests.support.mock_providers import MockECBExchangeRateProvider

A = "U10000001"   # Depot A
B = "U10000002"   # Depot B


# --------------------------------------------------------------------------- helpers
def _conid(isin: str) -> str:
    return "CON" + isin[:7]


def _trade(acct, isin, date, qty, price, side, oc, txid, ccy="EUR", symbol=None, asset_class="STK"):
    """One Trades row (column order = TRADES_COLUMNS). qty signed; commission 0."""
    return [acct, ccy, asset_class, "COMMON", symbol or isin[:6], isin, isin,
            None, None, None, date, Decimal(qty), Decimal(price), Decimal("0"), ccy,
            side, txid, None, None, _conid(isin), None, Decimal("1"), oc]


def _pos(acct, isin, qty, cost, ccy="EUR", price="100", symbol=None):
    """One Positions row (column order = POSITIONS_COLUMNS)."""
    return [acct, ccy, "STK", "COMMON", symbol or isin[:6], isin, isin,
            Decimal(qty), Decimal(qty) * Decimal(price), Decimal(price), Decimal(cost),
            None, _conid(isin), None, Decimal("1")]


def _cash(acct, ccy, soy, eoy):
    return [acct, ccy, "20250101", "20251231", Decimal(soy), Decimal(eoy)]


def _write(path, headers, rows):
    with open(path, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(list(headers))
        for r in rows:
            w.writerow(["" if c is None else str(c) for c in r])


class _CrossAccountBase(FifoTestCaseBase):
    """Direct pipeline call on multi-account CSVs, on top of the shared paths."""

    def _run_cross(self, *, trades, pos_soy, pos_eoy, cash_balance=None,
                   rate_provider=None, tax_year=2025) -> ProcessingOutput:
        p = self.config_paths
        _write(p["trades"], TRADES_COLUMNS, trades)
        _write(p["pos_start"], POSITIONS_COLUMNS, pos_soy)
        _write(p["pos_end"], POSITIONS_COLUMNS, pos_eoy)
        # cash_transactions + corp_actions: empty (headers only) via the canonical creators
        from tests.support.csv_creators import (
            create_cash_transactions_csv_string, create_corporate_actions_csv_string,
            create_cash_balance_csv_string,
        )
        with open(p["cash"], "w", encoding="utf-8-sig") as fh:
            fh.write(create_cash_transactions_csv_string([]))
        with open(p["corp_actions"], "w", encoding="utf-8-sig") as fh:
            fh.write(create_corporate_actions_csv_string([]))
        if cash_balance is not None:
            _write(p["cash_balance"], CASH_BALANCE_COLUMNS, cash_balance)
        else:
            with open(p["cash_balance"], "w", encoding="utf-8-sig") as fh:
                fh.write(create_cash_balance_csv_string([]))

        return run_core_processing_pipeline(
            trades_file_path=p["trades"],
            cash_transactions_file_path=p["cash"],
            positions_start_file_path=p["pos_start"],
            positions_end_file_path=p["pos_end"],
            corporate_actions_file_path=p["corp_actions"],
            interactive_classification_mode=False,
            tax_year_to_process=tax_year,
            custom_rate_provider=rate_provider or MockECBExchangeRateProvider(Decimal("1.00")),
            cash_balance_file_path=p["cash_balance"],
        )

    @staticmethod
    def _rgls_for_isin(out, isin):
        res = []
        for r in out.realized_gains_losses:
            a = out.asset_resolver.get_asset_by_id(r.asset_internal_id)
            if getattr(a, "ibkr_isin", None) == isin:
                res.append(r)
        return res

    @staticmethod
    def _fx_rgls(out, currency):
        res = []
        for r in out.realized_gains_losses:
            if r.asset_category_at_realization != AssetCategory.CASH_BALANCE:
                continue
            a = out.asset_resolver.get_asset_by_id(r.asset_internal_id)
            if (getattr(a, "currency", "") or "").upper() == currency.upper():
                res.append(r)
        return res


# --------------------------------------------------------------------------- tests
class TestPerDepotSecuritiesFifo(_CrossAccountBase):

    def test_co_held_security_sold_from_one_depot_uses_that_depots_lots(self):
        """X bought 100@10 in A (2023) and 50@40 in B (2024), both held at SoY 2025; sell 50 from
        B. Per-Depot consumes B's 50@40 (cost 2000, loss -500). The merged/account-agnostic result
        would consume A's older 100@10 (cost 500, gain +1000) — so this pins per-Depot behaviour."""
        isin = "US000000CO01"
        trades = [
            _trade(A, isin, "2023-05-01", "100", "10", "BUY", "O", "HA1"),
            _trade(B, isin, "2024-05-01", "50", "40", "BUY", "O", "HB1"),
            _trade(B, isin, "2025-06-01", "-50", "30", "SELL", "C", "S1"),
        ]
        pos_soy = [_pos(A, isin, "100", "1000"), _pos(B, isin, "50", "2000")]
        pos_eoy = [_pos(A, isin, "100", "1000")]  # B sold out; A unchanged
        out = self._run_cross(trades=trades, pos_soy=pos_soy, pos_eoy=pos_eoy)

        assert out.eoy_mismatch_error_count == 0
        sales = self._rgls_for_isin(out, isin)
        assert len(sales) == 1
        rgl = sales[0]
        assert rgl.total_cost_basis_eur == Decimal("2000"), "must consume B's 50@40, not A's 100@10"
        assert rgl.gross_gain_loss_eur == Decimal("-500")
        assert rgl.acquisition_date == "2024-05-01"


class TestPerDepotFxNoOpeningBalance(_CrossAccountBase):

    def test_currency_disposed_from_account_without_opening_balance_realises_fx(self):
        """Depot B holds NO CHF at SoY. In 2025 it sells a CHF stock (mints CHF @1.00) then buys
        another CHF stock (consumes 6000 CHF @1.20) -> FX gain 6000*0.20 = 1200 must be realised.
        This is the exact regression where the FX event was silently skipped because B had no
        opening CHF ledger. A USD balance in A makes the per-account currency path active."""
        chf_rate = [(__import__("datetime").date(2025, 1, 1), Decimal("1.00")),
                    (__import__("datetime").date(2025, 6, 1), Decimal("1.20"))]
        rp = MockECBExchangeRateProvider(
            foreign_to_eur_init_value=Decimal("1.00"),
            currency_schedules={"CHF": chf_rate},
        )
        y, z = "CH000000YYY0", "CH000000ZZZ0"
        trades = [
            _trade(B, y, "2025-03-01", "-200", "50", "SELL", "C", "FY1", ccy="CHF"),  # +10000 CHF @1.00
            _trade(B, z, "2025-09-01", "100", "60", "BUY", "O", "FZ1", ccy="CHF"),    # -6000 CHF @1.20
        ]
        pos_soy = [_pos(B, y, "200", "9000", ccy="CHF", price="50")]
        pos_eoy = [_pos(B, z, "100", "7200", ccy="CHF", price="60")]
        cash_balance = [_cash(A, "USD", "1000", "1000")]  # untouched; activates per-account currency path
        out = self._run_cross(trades=trades, pos_soy=pos_soy, pos_eoy=pos_eoy,
                              cash_balance=cash_balance, rate_provider=rp)

        chf_fx = self._fx_rgls(out, "CHF")
        assert chf_fx, "CHF FX disposal must be realised (was previously skipped)"
        total = sum(r.gross_gain_loss_eur for r in chf_fx)
        assert total == Decimal("1200"), f"expected FX gain 1200, got {total}"
        assert any(r.realization_type == RealizationType.FX_IMPLICIT_SECURITY_PURCHASE for r in chf_fx)


class TestWarningCleanliness(_CrossAccountBase):

    def test_multi_account_run_emits_no_soy_none_or_skipped_fx_warnings(self, caplog):
        """Regression guard: a multi-account run must not log the noise we fixed — per-account
        'SOY quantity None' (now defaults to 0) or skipped FX events (currency ledgers are created
        under the right account). Pins these so a future change fails CI instead of needing a human
        to read logs."""
        import logging
        isin = "US000000WC01"
        trades = [
            _trade(A, isin, "2023-05-01", "100", "10", "BUY", "O", "HA1"),
            _trade(B, isin, "2024-05-01", "50", "40", "BUY", "O", "HB1"),
            _trade(B, isin, "2025-06-01", "-50", "30", "SELL", "C", "S1"),
        ]
        pos_soy = [_pos(A, isin, "100", "1000"), _pos(B, isin, "50", "2000")]
        pos_eoy = [_pos(A, isin, "100", "1000")]
        with caplog.at_level(logging.WARNING):
            self._run_cross(trades=trades, pos_soy=pos_soy, pos_eoy=pos_eoy)
        msgs = [r.message for r in caplog.records]
        assert not any("SOY quantity from positions report is None" in m for m in msgs)
        assert not any("skipping FX event" in m for m in msgs)
        assert not any("No ledger for currency" in m for m in msgs)


class TestSingleAccountStillCollapses(_CrossAccountBase):

    def test_single_account_unchanged(self):
        """One account, no transfers: buy 100 @10 (2024), sell 100 @15 (2025) -> gain 500. The
        per-Depot machinery must collapse to the identical single-ledger result."""
        isin = "US000000SA01"
        trades = [
            _trade(A, isin, "2024-04-01", "100", "10", "BUY", "O", "B1"),
            _trade(A, isin, "2025-08-01", "-100", "15", "SELL", "C", "S1"),
        ]
        pos_soy = [_pos(A, isin, "100", "1000")]
        out = self._run_cross(trades=trades, pos_soy=pos_soy, pos_eoy=[])
        assert out.eoy_mismatch_error_count == 0
        sales = self._rgls_for_isin(out, isin)
        assert len(sales) == 1
        assert sales[0].total_cost_basis_eur == Decimal("1000")
        assert sales[0].gross_gain_loss_eur == Decimal("500")
