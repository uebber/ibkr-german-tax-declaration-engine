"""
Discovery tests: interaction of stock mergers (Pass 2) with internal transfers (Pass A).

The real data has no stock mergers, so this is purely about whether the engine's pass ordering
(trades+transfers in Pass A, then mergers in Pass 2, then SoY reconcile) produces the CORRECT tax
outcome when the SAME security is both merged and transferred. Each test asserts the legally-correct
result (tax-neutral merger + tax-neutral transfer -> carried cost basis); a RED test means the
combination is mishandled and warrants a warning/error.

Uses the GZUR(DE000A1DCTL3) -> SGBS(JE00B588CD74) 1:1 merger fixture shape from
tests/test_stock_merger_fifo.py. Self-contained; modifies no existing test.
"""
import csv
import os
from decimal import Decimal

import pytest

from src.pipeline_runner import run_core_processing_pipeline, ProcessingOutput
from src.parsers.column_validator import (
    TRADES_COLUMNS, POSITIONS_COLUMNS, TRANSFERS_COLUMNS, CORPORATE_ACTIONS_COLUMNS,
)
from tests.support.base import FifoTestCaseBase
from tests.support.mock_providers import MockECBExchangeRateProvider

A = "U10000001"
B = "U10000002"
GZUR, GZUR_ISIN = "GZUR", "DE000A1DCTL3"
SGBS, SGBS_ISIN = "SGBS", "JE00B588CD74"


def _conid(isin):
    return "CON" + isin[:7]


def _trade(acct, isin, date, qty, price, side, oc, txid, sym):
    return [acct, "EUR", "STK", "COMMON", sym, sym, isin, None, None, None, date,
            Decimal(qty), Decimal(price), Decimal("0"), "EUR", side, txid, None, None,
            _conid(isin), None, Decimal("1"), oc]


def _pos(acct, isin, qty, cost, sym, price="120"):
    return [acct, "EUR", "STK", "COMMON", sym, sym, isin, Decimal(qty),
            Decimal(qty) * Decimal(price), Decimal(price), Decimal(cost), None, _conid(isin), None, Decimal("1")]


def _transfer_out(src, tgt, isin, date, qty, txid, sym):
    return [src, "EUR", "STK", sym, isin, _conid(isin), date, "INTERNAL", "OUT", tgt,
            Decimal(qty), Decimal("0"), txid]


def _merger(acct, old_sym, old_isin, new_sym, date, qty, value, action_id="110634406"):
    """CA row (CORPORATE_ACTIONS_COLUMNS): GZUR MERGED WITH SGBS 1 FOR 1."""
    desc = f"{old_sym}({old_isin}) MERGED(Acquisition) WITH {new_sym} 1 FOR 1"
    return [acct, old_sym, desc, old_isin, date, "TC", "TC", action_id, _conid(old_isin),
            "", "", "EUR", "0", "0", Decimal(value), Decimal(qty)]


def _write(path, headers, rows):
    with open(path, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(list(headers))
        for r in rows:
            w.writerow(["" if c is None else str(c) for c in r])


class _MTBase(FifoTestCaseBase):
    def _run(self, *, trades, pos_soy, pos_eoy, transfers=None, corp_actions=None, tax_year=2023):
        p = self.config_paths
        from tests.support.csv_creators import (
            create_cash_transactions_csv_string, create_cash_balance_csv_string,
        )
        transfers_path = os.path.join(p["temp_dir_root"], "transfers.csv")
        _write(p["trades"], TRADES_COLUMNS, trades)
        _write(p["pos_start"], POSITIONS_COLUMNS, pos_soy)
        _write(p["pos_end"], POSITIONS_COLUMNS, pos_eoy)
        _write(p["corp_actions"], CORPORATE_ACTIONS_COLUMNS, corp_actions or [])
        _write(transfers_path, TRANSFERS_COLUMNS, transfers or [])
        with open(p["cash"], "w", encoding="utf-8-sig") as fh:
            fh.write(create_cash_transactions_csv_string([]))
        with open(p["cash_balance"], "w", encoding="utf-8-sig") as fh:
            fh.write(create_cash_balance_csv_string([]))
        return run_core_processing_pipeline(
            trades_file_path=p["trades"], cash_transactions_file_path=p["cash"],
            positions_start_file_path=p["pos_start"], positions_end_file_path=p["pos_end"],
            corporate_actions_file_path=p["corp_actions"], interactive_classification_mode=False,
            tax_year_to_process=tax_year, custom_rate_provider=MockECBExchangeRateProvider(Decimal("1.0")),
            cash_balance_file_path=p["cash_balance"], transfers_file_path=transfers_path,
        )

    @staticmethod
    def _sales(out, isin):
        res = []
        for r in out.realized_gains_losses:
            a = out.asset_resolver.get_asset_by_id(r.asset_internal_id)
            if getattr(a, "ibkr_isin", None) == isin:
                res.append(r)
        return res


class TestMergerTransferInteraction(_MTBase):

    def test_B_transfer_then_merge_dest_account(self):
        """buy 130 GZUR @100 in A; transfer A->B; merge GZUR->SGBS in B; sell 130 SGBS from B @120.
        Correct order in the engine (transfer in Pass A before merger in Pass 2). Expect lot-exact:
        cost 13000, gain 2600, acq date 2022-03-01."""
        trades = [
            _trade(A, GZUR_ISIN, "2022-03-01", "130", "100", "BUY", "O", "BG", GZUR),
            _trade(B, SGBS_ISIN, "2023-07-15", "-130", "120", "SELL", "C", "SS", SGBS),
        ]
        transfers = [_transfer_out(A, B, GZUR_ISIN, "2022-06-01", "-130", "TR1", GZUR)]
        corp = [_merger(B, GZUR, GZUR_ISIN, SGBS, "2022-08-22", "-130", "-13000")]
        pos_soy = [_pos(B, SGBS_ISIN, "130", "13000", SGBS)]
        out = self._run(trades=trades, pos_soy=pos_soy, pos_eoy=[], transfers=transfers, corp_actions=corp)
        assert out.eoy_mismatch_error_count == 0
        s = self._sales(out, SGBS_ISIN)
        assert len(s) == 1
        assert s[0].total_cost_basis_eur == Decimal("13000")
        assert s[0].gross_gain_loss_eur == Decimal("2600")
        assert s[0].acquisition_date == "2022-03-01"

    def test_A_merge_then_transfer_output(self):
        """buy 130 GZUR @100 in A; merge GZUR->SGBS in A; transfer SGBS A->B; sell 130 SGBS from B.
        The transfer of the merger OUTPUT runs in Pass A before Pass 2 creates SGBS. Correct GAIN
        (2600) is the requirement; acq-date carry-over is the stretch goal."""
        trades = [
            _trade(A, GZUR_ISIN, "2022-03-01", "130", "100", "BUY", "O", "BG", GZUR),
            _trade(B, SGBS_ISIN, "2023-07-15", "-130", "120", "SELL", "C", "SS", SGBS),
        ]
        corp = [_merger(A, GZUR, GZUR_ISIN, SGBS, "2022-08-22", "-130", "-13000")]
        transfers = [_transfer_out(A, B, SGBS_ISIN, "2022-11-01", "-130", "TR1", SGBS)]
        pos_soy = [_pos(B, SGBS_ISIN, "130", "13000", SGBS)]
        out = self._run(trades=trades, pos_soy=pos_soy, pos_eoy=[], transfers=transfers, corp_actions=corp)
        assert out.eoy_mismatch_error_count == 0
        s = self._sales(out, SGBS_ISIN)
        assert len(s) == 1
        assert s[0].total_cost_basis_eur == Decimal("13000")
        assert s[0].gross_gain_loss_eur == Decimal("2600")

    def test_C_currentyear_sameday_merge_then_transfer_output(self):
        """SoY: A holds 130 GZUR. Same day 2023-08-22: merge GZUR->SGBS in A AND transfer SGBS A->B.
        Then sell 130 SGBS from B. Merger sorts intra-day before transfer -> output exists to move."""
        trades = [
            _trade(B, SGBS_ISIN, "2023-09-01", "-130", "120", "SELL", "C", "SS", SGBS),
        ]
        corp = [_merger(A, GZUR, GZUR_ISIN, SGBS, "2023-08-22", "-130", "-13000")]
        transfers = [_transfer_out(A, B, SGBS_ISIN, "2023-08-22", "-130", "TR1", SGBS)]
        pos_soy = [_pos(A, GZUR_ISIN, "130", "13000", GZUR, price="100")]
        out = self._run(trades=trades, pos_soy=pos_soy, pos_eoy=[], transfers=transfers, corp_actions=corp)
        assert out.eoy_mismatch_error_count == 0
        s = self._sales(out, SGBS_ISIN)
        assert len(s) == 1
        assert s[0].gross_gain_loss_eur == Decimal("2600")

    def test_E_currentyear_sameday_transfer_source_then_merge(self):
        """SoY: A holds 130 GZUR. Same day: transfer GZUR A->B AND merge GZUR->SGBS. If the intent is
        transfer-then-merge, B should end with SGBS. Suspected mishandling (merger sorts first)."""
        trades = [
            _trade(B, SGBS_ISIN, "2023-09-01", "-130", "120", "SELL", "C", "SS", SGBS),
        ]
        corp = [_merger(B, GZUR, GZUR_ISIN, SGBS, "2023-08-22", "-130", "-13000")]
        transfers = [_transfer_out(A, B, GZUR_ISIN, "2023-08-22", "-130", "TR1", GZUR)]
        pos_soy = [_pos(A, GZUR_ISIN, "130", "13000", GZUR, price="100")]
        out = self._run(trades=trades, pos_soy=pos_soy, pos_eoy=[], transfers=transfers, corp_actions=corp)
        assert out.eoy_mismatch_error_count == 0
        s = self._sales(out, SGBS_ISIN)
        assert len(s) == 1
        assert s[0].gross_gain_loss_eur == Decimal("2600")

    def test_F_historical_sameday_transfer_source_then_merge(self):
        """Same as E but HISTORICAL: buy 130 GZUR @100 in A (2021); same day 2022-08-22 transfer
        GZUR A->B and merge GZUR->SGBS in B; SoY 2023 B holds 130 SGBS; sell from B. Historical
        reconstruction runs transfers (Pass A) before mergers (Pass 2), so this is already lot-exact
        (acq 2021-03-01, cost 13000) without the current-year reordering fix."""
        trades = [
            _trade(A, GZUR_ISIN, "2021-03-01", "130", "100", "BUY", "O", "BG", GZUR),
            _trade(B, SGBS_ISIN, "2023-07-15", "-130", "120", "SELL", "C", "SS", SGBS),
        ]
        transfers = [_transfer_out(A, B, GZUR_ISIN, "2022-08-22", "-130", "TR1", GZUR)]
        corp = [_merger(B, GZUR, GZUR_ISIN, SGBS, "2022-08-22", "-130", "-13000")]
        pos_soy = [_pos(B, SGBS_ISIN, "130", "13000", SGBS)]
        out = self._run(trades=trades, pos_soy=pos_soy, pos_eoy=[], transfers=transfers, corp_actions=corp)
        assert out.eoy_mismatch_error_count == 0
        s = self._sales(out, SGBS_ISIN)
        assert len(s) == 1
        assert s[0].total_cost_basis_eur == Decimal("13000")
        assert s[0].gross_gain_loss_eur == Decimal("2600")
        assert s[0].acquisition_date == "2021-03-01"

    def test_D_disjoint_merger_and_transfer(self):
        """Control: transfer of one security + merger of a different security -> both correct."""
        X, X_ISIN = "XSEC", "US000000XS01"
        trades = [
            _trade(A, X_ISIN, "2022-04-01", "100", "10", "BUY", "O", "BX", X),
            _trade(B, X_ISIN, "2023-05-01", "-100", "15", "SELL", "C", "SX", X),
            _trade(A, GZUR_ISIN, "2022-03-01", "130", "100", "BUY", "O", "BG", GZUR),
            _trade(A, SGBS_ISIN, "2023-07-15", "-130", "120", "SELL", "C", "SS", SGBS),
        ]
        transfers = [_transfer_out(A, B, X_ISIN, "2022-09-01", "-100", "TRX", X)]
        corp = [_merger(A, GZUR, GZUR_ISIN, SGBS, "2022-08-22", "-130", "-13000")]
        pos_soy = [_pos(B, X_ISIN, "100", "1000", X, price="10"),
                   _pos(A, SGBS_ISIN, "130", "13000", SGBS)]
        out = self._run(trades=trades, pos_soy=pos_soy, pos_eoy=[], transfers=transfers, corp_actions=corp)
        assert out.eoy_mismatch_error_count == 0
        assert self._sales(out, X_ISIN)[0].gross_gain_loss_eur == Decimal("500")     # 1500-1000
        assert self._sales(out, SGBS_ISIN)[0].gross_gain_loss_eur == Decimal("2600")  # 15600-13000
