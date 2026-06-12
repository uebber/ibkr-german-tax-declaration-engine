"""
Cross-account (per-Depot) integration tests — §20 Abs. 4 S. 7 EStG (FIFO per custody account).

legal_basis: §20 Abs. 4 S. 7 EStG (reference/tax-law/estg-20-kapitalvermoegen.md) — FIFO je
Depot; §43 Abs. 1 S. 5 EStG / Fußstapfentheorie for tax-neutral Depotübertragungen; BMF
Fremdwährung guidance (reference/bmf-guidance/fremdwaehrung-konten.md) for per-Depot FX.

These build multi-account input CSVs directly (the shared YAML harness forces a single
ClientAccountID, so it can't express these scenarios) and run the full pipeline. They pin the
behaviours that a green single-account suite missed:

  - a security co-held in two Depots and sold from one consumes only THAT Depot's lots
    (per-Depot result differs from the account-agnostic/merged result);
  - an internal transfer carries cost basis AND acquisition date across the Depot move
    (Fußstapfentheorie, §43 Abs. 1 S. 5) and realises no gain;
  - a foreign currency disposed from an account that had NO opening balance still realises FX
    (the CHF/HKD regression: it used to be silently skipped);
  - single-account input still collapses to the identical result (backward compatibility).

Nothing here modifies existing tests or shared helpers.
"""
import csv
import os
from decimal import Decimal

import pytest

from src.pipeline_runner import run_core_processing_pipeline, ProcessingOutput
from src.domain.enums import AssetCategory, RealizationType
from src.parsers.column_validator import (
    TRADES_COLUMNS, POSITIONS_COLUMNS, CASH_BALANCE_COLUMNS, TRANSFERS_COLUMNS,
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


def _transfer_out(src, tgt, isin, date, qty, txid, ccy="EUR", asset_class="STK", symbol=None):
    """OUT leg of an INTERNAL transfer (column order = TRANSFERS_COLUMNS). qty negative."""
    return [src, ccy, asset_class, symbol or isin[:6], isin, _conid(isin), date,
            "INTERNAL", "OUT", tgt, Decimal(qty), Decimal("0"), txid]


def _write(path, headers, rows):
    with open(path, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(list(headers))
        for r in rows:
            w.writerow(["" if c is None else str(c) for c in r])


class _CrossAccountBase(FifoTestCaseBase):
    """Adds a transfers file + direct pipeline call (with transfers) on top of the shared paths."""

    def _run_cross(self, *, trades, pos_soy, pos_eoy, cash_balance=None, transfers=None,
                   rate_provider=None, tax_year=2025) -> ProcessingOutput:
        p = self.config_paths
        transfers_path = os.path.join(p["temp_dir_root"], "transfers.csv")
        _write(p["trades"], TRADES_COLUMNS, trades)
        _write(p["pos_start"], POSITIONS_COLUMNS, pos_soy)
        _write(p["pos_end"], POSITIONS_COLUMNS, pos_eoy)
        _write(p["cash"], TRADES_COLUMNS[:0] or ["x"], [])  # placeholder, replaced below
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
        if transfers is not None:
            _write(transfers_path, TRANSFERS_COLUMNS, transfers)
        else:
            _write(transfers_path, TRANSFERS_COLUMNS, [])

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
            transfers_file_path=transfers_path,
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


class TestInternalTransferAcrossYears(_CrossAccountBase):

    def test_buy_A_transfer_to_B_sell_from_B_carries_basis_and_date(self):
        """Buy 100 X @10 in A (2024), transfer A->B (2024, tax-neutral), sell 100 from B (2025).
        The gain must use the ORIGINAL cost (1000) and acquisition date (2024-03-01), NOT the
        deliberately-wrong SoY-snapshot cost basis (8888). Proves Fußstapfentheorie carry-over."""
        isin = "US000000TR01"
        trades = [
            _trade(A, isin, "2024-03-01", "100", "10", "BUY", "O", "T1"),
            _trade(B, isin, "2025-09-01", "-100", "15", "SELL", "C", "T2"),
        ]
        transfers = [_transfer_out(A, B, isin, "2024-06-01", "-100", "TR1")]
        # SoY 2025: held in B; cost basis intentionally WRONG to detect a fallback.
        pos_soy = [_pos(B, isin, "100", "8888")]
        pos_eoy = []  # sold out in 2025
        out = self._run_cross(trades=trades, pos_soy=pos_soy, pos_eoy=pos_eoy, transfers=transfers)

        assert out.eoy_mismatch_error_count == 0
        sales = self._rgls_for_isin(out, isin)
        assert len(sales) == 1
        rgl = sales[0]
        assert rgl.total_cost_basis_eur == Decimal("1000"), "must carry original basis, not SoY 8888"
        assert rgl.acquisition_date == "2024-03-01", "must carry original acquisition date"
        assert rgl.gross_gain_loss_eur == Decimal("500")

    def test_partial_transfer_splits_lot_basis_preserved_both_sides(self):
        """Buy 100 X @10 in A (2024), transfer 60 to B, sell 40 from A and 60 from B in 2025. Both
        sales must use the ORIGINAL per-unit basis (10) and date — the lot is split, not reset."""
        isin = "US000000TR03"
        trades = [
            _trade(A, isin, "2024-03-01", "100", "10", "BUY", "O", "T1"),
            _trade(A, isin, "2025-07-01", "-40", "15", "SELL", "C", "SA"),
            _trade(B, isin, "2025-07-01", "-60", "20", "SELL", "C", "SB"),
        ]
        transfers = [_transfer_out(A, B, isin, "2024-06-01", "-60", "TR1")]
        pos_soy = [_pos(A, isin, "40", "400"), _pos(B, isin, "60", "600")]  # post-transfer
        out = self._run_cross(trades=trades, pos_soy=pos_soy, pos_eoy=[], transfers=transfers)

        assert out.eoy_mismatch_error_count == 0
        sales = self._rgls_for_isin(out, isin)
        assert len(sales) == 2
        by_qty = {r.quantity_realized: r for r in sales}
        assert by_qty[Decimal("40")].total_cost_basis_eur == Decimal("400")   # 40 @ 10
        assert by_qty[Decimal("40")].gross_gain_loss_eur == Decimal("200")    # 600 - 400
        assert by_qty[Decimal("60")].total_cost_basis_eur == Decimal("600")   # 60 @ 10
        assert by_qty[Decimal("60")].gross_gain_loss_eur == Decimal("600")    # 1200 - 600
        assert all(r.acquisition_date == "2024-03-01" for r in sales)

    def test_transfer_itself_realises_no_gain(self):
        """The transfer leg must not create any RGL for the moved security in its move year."""
        isin = "US000000TR02"
        trades = [
            _trade(A, isin, "2024-03-01", "100", "10", "BUY", "O", "T1"),
            _trade(B, isin, "2025-09-01", "-100", "15", "SELL", "C", "T2"),
        ]
        transfers = [_transfer_out(A, B, isin, "2024-06-01", "-100", "TR1")]
        pos_soy = [_pos(B, isin, "100", "1000")]
        out = self._run_cross(trades=trades, pos_soy=pos_soy, pos_eoy=[], transfers=transfers)
        # Exactly one realisation (the 2025 sale), none from the transfer.
        assert len(self._rgls_for_isin(out, isin)) == 1


class TestHistoricalTransferReconstruction(_CrossAccountBase):

    def test_buy_independentbuy_transfer_historicalsell_then_taxyearsell(self):
        """Interleaved historical reconstruction.

        A buys 100 X @10 (2023-01); B independently buys 50 X @40 (2023-02); 100 transferred A->B
        (2023-03) so B holds [100@10 (acq 2023-01), 50@40 (acq 2023-02)]; B sells 60 in 2024 (FIFO
        consumes 60@10, history) leaving [40@10, 50@40]=90; B sells the remaining 90 in 2025.

        Correct per-Depot FIFO with carried basis: 2025 cost = 40*10 + 50*40 = 2400, gain = 300,
        and acquisition dates are the REAL lot dates (2023-01-15 / 2023-02-15).

        The SoY cost basis is deliberately WRONG (9999): the non-interleaved 3-pass reconstruction
        marks B's ledger inconsistent (it sims B's own 2024 sale before the transfer delivers the
        lots) and falls back to the SoY-reported cost at a 2024-12-31 fallback date — so it would
        return 9999 / 2024-12-31. A correct chronological replay ignores the wrong SoY cost."""
        isin = "US000000HT01"
        trades = [
            _trade(A, isin, "2023-01-15", "100", "10", "BUY", "O", "HA1"),
            _trade(B, isin, "2023-02-15", "50", "40", "BUY", "O", "HB1"),
            _trade(B, isin, "2024-04-15", "-60", "20", "SELL", "C", "HS1"),  # historical sale
            _trade(B, isin, "2025-06-15", "-90", "30", "SELL", "C", "CS1"),  # tax-year sale
        ]
        transfers = [_transfer_out(A, B, isin, "2023-03-15", "-100", "TR1")]
        pos_soy = [_pos(B, isin, "90", "9999")]  # WRONG cost on purpose; correct replay must not use it
        out = self._run_cross(trades=trades, pos_soy=pos_soy, pos_eoy=[], transfers=transfers)

        assert out.eoy_mismatch_error_count == 0
        sales = self._rgls_for_isin(out, isin)  # only the 2025 sale is in-year
        total_qty = sum(r.quantity_realized for r in sales)
        total_cost = sum(r.total_cost_basis_eur for r in sales)
        total_gain = sum(r.gross_gain_loss_eur for r in sales)
        assert total_qty == Decimal("90")
        assert total_cost == Decimal("2400"), f"expected lot-exact carried basis 2400, got {total_cost}"
        assert total_gain == Decimal("300")
        # acquisition dates must be the real lot dates, never the SoY-fallback date.
        acqs = {r.acquisition_date for r in sales}
        assert "2024-12-31" not in acqs, f"reconstruction fell back to SoY date: {acqs}"
        assert acqs <= {"2023-01-15", "2023-02-15"}, acqs


class TestShortPositionTransfer(_CrossAccountBase):

    def test_short_opened_in_A_transferred_then_covered_in_B(self):
        """Sell-to-open 100 X @50 in A (2024, short, proceeds 5000), transfer the open short to B
        (2024), buy-to-cover 100 @30 in B (2025). The cover must realise against the CARRIED short
        proceeds: gain = 5000 - 3000 = 2000. (Before short-transfer support this warned 'insufficient
        short lots' and the short stayed stranded in A.)"""
        isin = "US000000SH01"
        trades = [
            _trade(A, isin, "2024-03-01", "-100", "50", "SELL", "O", "SO1"),  # short open
            _trade(B, isin, "2025-09-01", "100", "30", "BUY", "C", "SC1"),    # cover
        ]
        transfers = [_transfer_out(A, B, isin, "2024-06-01", "-100", "TR1")]
        pos_soy = [_pos(B, isin, "-100", "5000")]  # short carried into 2025 in B
        out = self._run_cross(trades=trades, pos_soy=pos_soy, pos_eoy=[], transfers=transfers)

        assert out.eoy_mismatch_error_count == 0
        covers = self._rgls_for_isin(out, isin)
        assert len(covers) == 1
        assert covers[0].realization_type == RealizationType.SHORT_POSITION_COVER
        assert covers[0].gross_gain_loss_eur == Decimal("2000")


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
