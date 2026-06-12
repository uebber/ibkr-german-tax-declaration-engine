"""
Per-Depot FIFO: non-EUR CASH internal transfers must carry the sender's cost basis.

An internal transfer of foreign currency between two of the same person's own accounts is NOT a
Veräußerung (no change of ownership) — so it is tax-neutral and the moved currency keeps the
sender's acquisition date + EUR cost basis (§43 Abs. 1 S. 5 Fußstapfentheorie), exactly like a
security transfer (§20 Abs. 4 S. 7 per-Depot FIFO; §20 Abs. 2 Nr. 7 for the FX gain). When the
receiving Depot later spends that currency, the FX gain must be measured from the ORIGINAL
acquisition rate, not from the start-of-year (SoY) rate.

These tests pin that requirement. The currently-known gap: HISTORICAL (pre-tax-year) cash transfers
are dropped from the currency reconstruction (calculation_engine Pass A skips CashBalance transfers),
so the receiver's currency basis is reset to the SoY ECB rate — understating/overstating the FX gain
on a later spend (and, because the aggregate is what flows to Anlage KAP, mis-stating the return).

Nothing here modifies existing tests or shared application code.
"""
import csv
import os
from datetime import date
from decimal import Decimal

import pytest

from src.pipeline_runner import run_core_processing_pipeline, ProcessingOutput
from src.domain.enums import AssetCategory, RealizationType
from src.parsers.column_validator import (
    TRADES_COLUMNS, POSITIONS_COLUMNS, CASH_BALANCE_COLUMNS, CASH_TRANSACTIONS_COLUMNS,
    TRANSFERS_COLUMNS,
)
from tests.support.base import FifoTestCaseBase
from tests.support.mock_providers import MockECBExchangeRateProvider

A = "U10000001"   # Depot A (sender)
B = "U10000002"   # Depot B (receiver)


# --------------------------------------------------------------------------- row builders
def _conid(isin: str) -> str:
    return "CON" + isin[:7]


def _trade(acct, isin, date_str, qty, price, side, oc, txid, ccy="USD", symbol=None):
    """One Trades row (column order = TRADES_COLUMNS). qty signed; commission 0."""
    return [acct, ccy, "STK", "COMMON", symbol or isin[:6], isin, isin,
            None, None, None, date_str, Decimal(qty), Decimal(price), Decimal("0"), ccy,
            side, txid, None, None, _conid(isin), None, Decimal("1"), oc]


def _pos(acct, isin, qty, cost, ccy="USD", price="100", symbol=None):
    """One Positions row (column order = POSITIONS_COLUMNS)."""
    return [acct, ccy, "STK", "COMMON", symbol or isin[:6], isin, isin,
            Decimal(qty), Decimal(qty) * Decimal(price), Decimal(price), Decimal(cost),
            None, _conid(isin), None, Decimal("1")]


def _cash_bal(acct, ccy, soy, eoy):
    """One Cash_Balance row (column order = CASH_BALANCE_COLUMNS)."""
    return [acct, ccy, "20250101", "20251231", Decimal(soy), Decimal(eoy)]


def _div(acct, ccy, amount, date_str, txid, symbol="AAPL", isin="US0378331005"):
    """A foreign-currency dividend that mints `amount` of `ccy` into `acct` on `date_str`
    (column order = CASH_TRANSACTIONS_COLUMNS)."""
    return [acct, ccy, "STK", "COMMON", symbol, f"{symbol} CASH DIVIDEND", date_str,
            Decimal(amount), "Dividends", _conid(isin), None, isin, "US", txid]


def _transfer_cash(src, tgt, ccy, date_str, amount, txid):
    """OUT leg of an INTERNAL non-EUR CASH transfer (column order = TRANSFERS_COLUMNS).
    CashTransfer is negative on the OUT leg."""
    return [src, ccy, "CASH", ccy, None, None, date_str,
            "INTERNAL", "OUT", tgt, Decimal("0"), Decimal(amount), txid]


def _write(path, headers, rows):
    with open(path, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(list(headers))
        for r in rows:
            w.writerow(["" if c is None else str(c) for c in r])


def _usd_provider():
    """USD appreciates 0.80 -> 0.95 (SoY) -> 1.00 (spend). EUR per 1 USD."""
    return MockECBExchangeRateProvider(
        foreign_to_eur_init_value=Decimal("1.00"),
        currency_schedules={"USD": [
            (date(2023, 6, 15), Decimal("0.80")),   # A acquires USD here
            (date(2024, 12, 31), Decimal("0.95")),  # SoY-2025 fallback rate
            (date(2025, 9, 1), Decimal("1.00")),    # B spends USD here
        ]},
    )


class _Base(FifoTestCaseBase):
    """Direct multi-account pipeline call with a transfers + cash-transactions file."""

    def _run(self, *, trades, pos_soy, pos_eoy, cash_balance, transfers=None,
             cash_transactions=None, rate_provider=None, tax_year=2025) -> ProcessingOutput:
        p = self.config_paths
        transfers_path = os.path.join(p["temp_dir_root"], "transfers.csv")
        _write(p["trades"], TRADES_COLUMNS, trades)
        _write(p["pos_start"], POSITIONS_COLUMNS, pos_soy)
        _write(p["pos_end"], POSITIONS_COLUMNS, pos_eoy)
        _write(p["cash"], CASH_TRANSACTIONS_COLUMNS, cash_transactions or [])
        _write(p["cash_balance"], CASH_BALANCE_COLUMNS, cash_balance)
        from tests.support.csv_creators import create_corporate_actions_csv_string
        with open(p["corp_actions"], "w", encoding="utf-8-sig") as fh:
            fh.write(create_corporate_actions_csv_string([]))
        _write(transfers_path, TRANSFERS_COLUMNS, transfers or [])

        return run_core_processing_pipeline(
            trades_file_path=p["trades"],
            cash_transactions_file_path=p["cash"],
            positions_start_file_path=p["pos_start"],
            positions_end_file_path=p["pos_end"],
            corporate_actions_file_path=p["corp_actions"],
            interactive_classification_mode=False,
            tax_year_to_process=tax_year,
            custom_rate_provider=rate_provider or _usd_provider(),
            cash_balance_file_path=p["cash_balance"],
            transfers_file_path=transfers_path,
        )

    @staticmethod
    def _usd_fx(out):
        res = []
        for r in out.realized_gains_losses:
            if r.asset_category_at_realization != AssetCategory.CASH_BALANCE:
                continue
            a = out.asset_resolver.get_asset_by_id(r.asset_internal_id)
            if (getattr(a, "currency", "") or "").upper() == "USD":
                res.append(r)
        return res


# --------------------------------------------------------------------------- ledger-level anchor
class TestCurrencyLedgerTransferMechanism:
    """The generic FIFO drain/receive works for a CASH_BALANCE ledger too — the mechanism to carry
    currency basis exists; the engine just has to call it for cash transfers."""

    def _ledger(self):
        import uuid
        from unittest.mock import MagicMock
        from src.engine.fifo_manager import FifoLedger
        from src.utils.currency_converter import CurrencyConverter
        from src.utils.exchange_rate_provider import ECBExchangeRateProvider
        return FifoLedger(
            asset_internal_id=uuid.uuid4(), asset_category=AssetCategory.CASH_BALANCE,
            asset_multiplier_from_asset=None,
            currency_converter=MagicMock(spec=CurrencyConverter),
            exchange_rate_provider=MagicMock(spec=ECBExchangeRateProvider),
            internal_working_precision=28, decimal_rounding_mode="ROUND_HALF_EVEN",
        )

    def test_currency_lot_moves_with_basis_and_date(self):
        from src.engine.fifo_manager import FifoLot
        src = self._ledger()
        # 1000 USD acquired 2023-06-15 at 0.80 EUR/USD -> 800 EUR basis.
        src.lots.append(FifoLot(acquisition_date="2023-06-15", quantity=Decimal("1000"),
                                unit_cost_basis_eur=Decimal("0.80"),
                                total_cost_basis_eur=Decimal("800"), source_transaction_id="DIV"))
        tgt = self._ledger()
        drained = src.transfer_out_long_lots(Decimal("1000"), "XFER")
        tgt.receive_transferred_lots(drained)
        assert len(src.lots) == 0
        assert len(tgt.lots) == 1
        assert tgt.lots[0].acquisition_date == "2023-06-15"
        assert tgt.lots[0].unit_cost_basis_eur == Decimal("0.80")
        assert tgt.lots[0].total_cost_basis_eur == Decimal("800")


# --------------------------------------------------------------------------- the gap (integration)
class TestHistoricalCashTransferBasis(_Base):

    def test_historical_transfer_carries_sender_basis_to_receiver(self):
        """A receives 1000 USD as a 2023 dividend @0.80 (800 EUR basis), transfers it to B in 2023.
        B holds 1000 USD at SoY 2025, then spends it buying a stock for 1000 USD @1.00 in 2025.

        Correct: FX gain = 1000*(1.00-0.80) = 200 EUR (carried basis).
        Gap today: B's USD basis is reset to the SoY rate 0.95 -> FX gain only 50 EUR."""
        stockz = "US000000BZ01"
        trades = [_trade(B, stockz, "2025-09-01", "10", "100", "BUY", "O", "BZ1")]  # consume 1000 USD
        cash_transactions = [_div(A, "USD", "1000", "2023-06-15", "DIVA")]
        transfers = [_transfer_cash(A, B, "USD", "2023-08-01", "-1000", "XF1")]
        pos_soy = []                                  # USD lives in cash, not positions
        pos_eoy = [_pos(B, stockz, "10", "1000")]     # B holds the bought stock at EoY
        cash_balance = [
            _cash_bal(A, "USD", "0", "0"),            # A: +1000 div -1000 transfer = 0
            _cash_bal(B, "USD", "1000", "0"),         # B: +1000 received, -1000 spent = 0
        ]
        out = self._run(trades=trades, pos_soy=pos_soy, pos_eoy=pos_eoy,
                        cash_balance=cash_balance, transfers=transfers,
                        cash_transactions=cash_transactions)

        assert out.eoy_mismatch_error_count == 0
        fx = self._usd_fx(out)
        assert fx, "B spending the transferred USD must realise an FX gain"
        total = sum(r.gross_gain_loss_eur for r in fx)
        assert total == Decimal("200"), (
            f"FX gain must use A's carried 0.80 basis (=200 EUR), got {total}. "
            f"50 EUR means the receiver's basis was reset to the SoY rate (the bug).")
        assert any(r.realization_type == RealizationType.FX_IMPLICIT_SECURITY_PURCHASE for r in fx)

    def test_historical_transfer_realises_no_gain_on_the_move_itself(self):
        """The transfer leg is tax-neutral: the ONLY USD FX realisation is the 2025 spend, never the
        2023 move."""
        stockz = "US000000BZ02"
        trades = [_trade(B, stockz, "2025-09-01", "10", "100", "BUY", "O", "BZ2")]
        cash_transactions = [_div(A, "USD", "1000", "2023-06-15", "DIVA")]
        transfers = [_transfer_cash(A, B, "USD", "2023-08-01", "-1000", "XF1")]
        out = self._run(trades=trades, pos_soy=[], pos_eoy=[_pos(B, stockz, "10", "1000")],
                        cash_balance=[_cash_bal(A, "USD", "0", "0"), _cash_bal(B, "USD", "1000", "0")],
                        transfers=transfers, cash_transactions=cash_transactions)
        assert out.eoy_mismatch_error_count == 0
        assert len(self._usd_fx(out)) == 1, "exactly one FX realisation (the spend), none from the move"

    def test_aggregate_fx_across_both_depots_is_basis_correct(self):
        """The aggregate that flows to Anlage KAP must equal the economically-correct FX on the round
        trip (acquired @0.80, spent @1.00 -> 200 EUR), independent of which Depot spent it. A realises
        nothing on the move; B realises the full 200."""
        stockz = "US000000BZ03"
        trades = [_trade(B, stockz, "2025-09-01", "10", "100", "BUY", "O", "BZ3")]
        cash_transactions = [_div(A, "USD", "1000", "2023-06-15", "DIVA")]
        transfers = [_transfer_cash(A, B, "USD", "2023-08-01", "-1000", "XF1")]
        out = self._run(trades=trades, pos_soy=[], pos_eoy=[_pos(B, stockz, "10", "1000")],
                        cash_balance=[_cash_bal(A, "USD", "0", "0"), _cash_bal(B, "USD", "1000", "0")],
                        transfers=transfers, cash_transactions=cash_transactions)
        assert out.eoy_mismatch_error_count == 0
        aggregate = sum(r.gross_gain_loss_eur for r in self._usd_fx(out))
        assert aggregate == Decimal("200"), f"aggregate USD FX must be 200, got {aggregate}"


# --------------------------------------------------------------------------- current-year path
class TestCurrentYearCashTransferBasis(_Base):

    def test_current_year_transfer_carries_basis(self):
        """Same economics but the transfer happens IN the tax year (2025). A mints 1000 USD @0.80
        (2025-02 dividend), transfers to B (2025-04), B spends it @1.00 (2025-09). Carried-basis FX
        gain = 200. (Current-year transfers run through the main event loop / _apply_internal_transfer.)"""
        stockz = "US000000BZ04"
        rp = MockECBExchangeRateProvider(
            foreign_to_eur_init_value=Decimal("1.00"),
            currency_schedules={"USD": [
                (date(2024, 12, 31), Decimal("0.80")),
                (date(2025, 2, 1), Decimal("0.80")),
                (date(2025, 9, 1), Decimal("1.00")),
            ]},
        )
        trades = [_trade(B, stockz, "2025-09-01", "10", "100", "BUY", "O", "BZ4")]
        cash_transactions = [_div(A, "USD", "1000", "2025-02-01", "DIVA")]
        transfers = [_transfer_cash(A, B, "USD", "2025-04-01", "-1000", "XF1")]
        out = self._run(trades=trades, pos_soy=[], pos_eoy=[_pos(B, stockz, "10", "1000")],
                        cash_balance=[_cash_bal(A, "USD", "0", "0"), _cash_bal(B, "USD", "0", "0")],
                        transfers=transfers, cash_transactions=cash_transactions, rate_provider=rp)
        assert out.eoy_mismatch_error_count == 0
        total = sum(r.gross_gain_loss_eur for r in self._usd_fx(out))
        assert total == Decimal("200"), f"current-year transfer must carry 0.80 basis (=200), got {total}"
