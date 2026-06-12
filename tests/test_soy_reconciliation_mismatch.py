"""
SoY reconstruction-vs-reported quantity reconciliation (`FifoLedger.reconcile_with_soy_position`).

The cost-basis behaviour is the documented requirement (see SOY_H_* / SOY_F_* in
tests/fixtures/group2_soy_handling.yaml and tests/docs/spec_fifo.md):
  - reconstruction sufficient (>= reported) -> keep the historical lot-level cost, trimmed to the
    reported quantity (more accurate than the broker's reported aggregate);
  - reconstruction insufficient (< reported) / inconsistent -> fall back to the reported SoY cost.

This file pins the ADDED requirement: **any** quantity divergence between the replay and the
reported SoY snapshot must emit a WARNING — including over-reconstruction (a disposal missing from
the input trades), which previously kept the historical lots SILENTLY. The cost basis / figures are
unchanged; only the warning is added.
"""
import logging
import uuid
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

from src.engine.fifo_manager import FifoLedger, FifoLot
from src.domain.enums import AssetCategory
from src.utils.currency_converter import CurrencyConverter
from src.utils.exchange_rate_provider import ECBExchangeRateProvider


def _ledger():
    return FifoLedger(
        asset_internal_id=uuid.uuid4(), asset_category=AssetCategory.STOCK,
        asset_multiplier_from_asset=None,
        currency_converter=MagicMock(spec=CurrencyConverter),
        exchange_rate_provider=MagicMock(spec=ECBExchangeRateProvider),
        internal_working_precision=28, decimal_rounding_mode="ROUND_HALF_EVEN",
    )


def _asset(soy_qty, soy_cost="700"):
    a = SimpleNamespace(
        soy_quantity=Decimal(soy_qty), soy_cost_basis_amount=Decimal(soy_cost),
        soy_cost_basis_currency="EUR", internal_asset_id=uuid.uuid4(),
        asset_category=AssetCategory.STOCK,
    )
    a.get_classification_key = lambda: "ISIN:TESTRECON"
    return a


def _long_lot(qty, unit, date="2023-05-01", tx="HB1"):
    q, u = Decimal(qty), Decimal(unit)
    return FifoLot(acquisition_date=date, quantity=q, unit_cost_basis_eur=u,
                   total_cost_basis_eur=q * u, source_transaction_id=tx)


def _recon_warning(caplog):
    return any("reconstruction" in r.message.lower() and r.levelname == "WARNING"
               for r in caplog.records)


class TestSoyReconciliationMismatch:

    def test_exact_match_uses_reconstructed_lots_no_warning(self, caplog):
        """Replay == reported: keep the real reconstructed lots, no warning."""
        led = _ledger()
        led.lots.append(_long_lot("100", "5"))
        with caplog.at_level(logging.WARNING):
            led.reconcile_with_soy_position(_asset("100"), 2025)
        assert sum(l.quantity for l in led.lots) == Decimal("100")
        assert led.lots[0].acquisition_date == "2023-05-01"
        assert led.lots[0].total_cost_basis_eur == Decimal("500")
        assert not _recon_warning(caplog)

    def test_over_reconstruction_keeps_historical_lots_but_warns(self, caplog):
        """Replay 105 but SoY reports 100 (a sale missing from the data): KEEP the historical lots
        trimmed to 100 (date/cost preserved, figures unchanged) AND emit a WARNING."""
        led = _ledger()
        led.lots.append(_long_lot("105", "5"))
        with caplog.at_level(logging.WARNING):
            led.reconcile_with_soy_position(_asset("100", "700"), 2025)
        # behaviour unchanged: historical lots trimmed to reported qty, NOT the SoY-fallback
        assert sum(l.quantity for l in led.lots) == Decimal("100")
        assert led.lots[0].acquisition_date == "2023-05-01"        # reconstructed, not 2024-12-31
        assert led.lots[0].total_cost_basis_eur == Decimal("500")  # historical 100*5, not reported 700
        # new requirement: the divergence is surfaced
        assert _recon_warning(caplog)

    def test_under_reconstruction_falls_back_and_warns(self, caplog):
        """Replay 95 but SoY reports 100 (a buy missing): fall back to reported cost + WARN."""
        led = _ledger()
        led.lots.append(_long_lot("95", "5"))
        with caplog.at_level(logging.WARNING):
            led.reconcile_with_soy_position(_asset("100", "700"), 2025)
        assert sum(l.quantity for l in led.lots) == Decimal("100")
        assert led.lots[0].acquisition_date == "2024-12-31"
        assert led.lots[0].total_cost_basis_eur == Decimal("700")
        assert _recon_warning(caplog)
