"""
Per-Depot FIFO: internal Depotübertragung (transfer) handling.

German FIFO (§20 Abs. 4 S. 7 EStG) is applied per custody account (Depot). An internal transfer
of a security/cash between two of the same person's accounts is tax-neutral (§43 Abs. 1 S. 5,
Fußstapfentheorie): the FIFO lots — acquisition date and EUR cost basis — carry over from the
source account ledger to the target account ledger; no gain is realised.

These tests pin:
  - FifoLedger.transfer_out_long_lots / receive_transferred_lots (partial drain, lot split,
    basis/date preservation, insufficient-quantity guard).
  - DomainEventFactory.create_events_from_transfers (OUT legs -> InternalTransferEvent; IN legs
    and EUR cash ignored).
"""
import uuid
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from src.engine.fifo_manager import FifoLedger, FifoLot
from src.domain.enums import AssetCategory
from src.domain.events import InternalTransferEvent
from src.utils.currency_converter import CurrencyConverter
from src.utils.exchange_rate_provider import ECBExchangeRateProvider
from src.parsers.raw_models import RawTransferRecord
from src.parsers.domain_event_factory import DomainEventFactory


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ledger(asset_id=None):
    return FifoLedger(
        asset_internal_id=asset_id or uuid.uuid4(),
        asset_category=AssetCategory.STOCK,
        asset_multiplier_from_asset=None,
        currency_converter=MagicMock(spec=CurrencyConverter),
        exchange_rate_provider=MagicMock(spec=ECBExchangeRateProvider),
        internal_working_precision=28,
        decimal_rounding_mode="ROUND_HALF_EVEN",
    )


def _lot(acq_date, qty, unit_cost, tx_id):
    q, u = Decimal(qty), Decimal(unit_cost)
    return FifoLot(acquisition_date=acq_date, quantity=q, unit_cost_basis_eur=u,
                   total_cost_basis_eur=q * u, source_transaction_id=tx_id)


def _xfer_row(**kw):
    base = {
        "ClientAccountID": "U10000001", "CurrencyPrimary": "USD", "AssetClass": "STK",
        "Symbol": "BNS", "Description": "BANK OF NOVA SCOTIA", "Conid": "111", "ISIN": "CA0641491075",
        "Date": "2023-06-01", "SettleDate": "2023-06-03", "Type": "INTERNAL", "Direction": "OUT",
        "TransferAccount": "U10000002", "Quantity": "-80", "CashTransfer": "0", "TransactionID": "TX1",
    }
    base.update(kw)
    return RawTransferRecord(**base)


# ---------------------------------------------------------------------------
# FifoLedger drain / receive
# ---------------------------------------------------------------------------

class TestTransferLots:

    def test_whole_lot_moved_preserves_basis_and_date(self):
        src = _ledger()
        src.lots.append(_lot("2022-01-10", "100", "12.50", "BUY1"))
        drained = src.transfer_out_long_lots(Decimal("100"), "TX1")
        assert len(src.lots) == 0
        assert len(drained) == 1
        assert drained[0].acquisition_date == "2022-01-10"
        assert drained[0].quantity == Decimal("100")
        assert drained[0].unit_cost_basis_eur == Decimal("12.50")

    def test_partial_drain_splits_boundary_lot(self):
        src = _ledger()
        src.lots.append(_lot("2022-01-10", "100", "10.00", "BUY1"))
        src.lots.append(_lot("2022-03-15", "50", "20.00", "BUY2"))
        drained = src.transfer_out_long_lots(Decimal("120"), "TX1")
        # 100 from lot 1 + 20 from lot 2; lot 2 keeps 30.
        assert sum(l.quantity for l in drained) == Decimal("120")
        assert len(src.lots) == 1
        assert src.lots[0].quantity == Decimal("30")
        assert src.lots[0].acquisition_date == "2022-03-15"
        # The split-off piece keeps lot 2's date and unit cost.
        moved_from_lot2 = [l for l in drained if l.acquisition_date == "2022-03-15"][0]
        assert moved_from_lot2.quantity == Decimal("20")
        assert moved_from_lot2.unit_cost_basis_eur == Decimal("20.00")

    def test_receive_merges_and_sorts_by_date(self):
        tgt = _ledger()
        tgt.lots.append(_lot("2022-05-01", "10", "5.00", "EXISTING"))
        tgt.receive_transferred_lots([_lot("2021-01-01", "10", "9.00", "OLD")])
        # Re-sorted: the older acquired lot comes first (FIFO).
        assert [l.acquisition_date for l in tgt.lots] == ["2021-01-01", "2022-05-01"]

    def test_insufficient_quantity_raises(self):
        src = _ledger()
        src.lots.append(_lot("2022-01-10", "50", "10.00", "BUY1"))
        with pytest.raises(ValueError):
            src.transfer_out_long_lots(Decimal("80"), "TX1")

    def test_round_trip_is_value_neutral(self):
        """Draining and receiving moves the exact lots: total quantity and basis are conserved."""
        src = _ledger()
        src.lots.append(_lot("2022-01-10", "100", "10.00", "BUY1"))
        src.lots.append(_lot("2022-03-15", "50", "20.00", "BUY2"))
        tgt = _ledger(src.asset_internal_id)
        drained = src.transfer_out_long_lots(Decimal("130"), "TX1")
        tgt.receive_transferred_lots(drained)
        src_qty = sum(l.quantity for l in src.lots)
        tgt_qty = sum(l.quantity for l in tgt.lots)
        assert src_qty == Decimal("20") and tgt_qty == Decimal("130")
        # Combined basis unchanged: 100*10 + 50*20 = 2000.
        combined = sum(l.total_cost_basis_eur for l in src.lots) + sum(l.total_cost_basis_eur for l in tgt.lots)
        assert combined == Decimal("2000.00")


def _short(open_date, qty, unit_proceeds, tx_id):
    from src.engine.fifo_manager import ShortFifoLot
    q, u = Decimal(qty), Decimal(unit_proceeds)
    return ShortFifoLot(opening_date=open_date, quantity_shorted=q, unit_sale_proceeds_eur=u,
                        total_sale_proceeds_eur=q * u, source_transaction_id=tx_id)


class TestTransferShortLots:
    """A transferred SHORT position carries its open-short sale proceeds + opening date too."""

    def test_whole_short_lot_moved_preserves_proceeds_and_date(self):
        src = _ledger()
        src.short_lots.append(_short("2022-01-10", "100", "12.50", "SO1"))
        drained = src.transfer_out_short_lots(Decimal("100"), "TX1")
        assert len(src.short_lots) == 0 and len(drained) == 1
        assert drained[0].opening_date == "2022-01-10"
        assert drained[0].quantity_shorted == Decimal("100")
        assert drained[0].unit_sale_proceeds_eur == Decimal("12.50")

    def test_partial_short_drain_splits_boundary(self):
        src = _ledger()
        src.short_lots.append(_short("2022-01-10", "100", "10.00", "SO1"))
        src.short_lots.append(_short("2022-03-15", "50", "20.00", "SO2"))
        drained = src.transfer_out_short_lots(Decimal("120"), "TX1")
        assert sum(l.quantity_shorted for l in drained) == Decimal("120")
        assert len(src.short_lots) == 1 and src.short_lots[0].quantity_shorted == Decimal("30")
        moved2 = [l for l in drained if l.opening_date == "2022-03-15"][0]
        assert moved2.quantity_shorted == Decimal("20")
        assert moved2.unit_sale_proceeds_eur == Decimal("20.00")

    def test_insufficient_short_raises(self):
        src = _ledger()
        src.short_lots.append(_short("2022-01-10", "50", "10.00", "SO1"))
        with pytest.raises(ValueError):
            src.transfer_out_short_lots(Decimal("80"), "TX1")

    def test_receive_short_sorts_by_open_date(self):
        tgt = _ledger()
        tgt.short_lots.append(_short("2022-05-01", "10", "5.00", "EXIST"))
        tgt.receive_transferred_short_lots([_short("2021-01-01", "10", "9.00", "OLD")])
        assert [l.opening_date for l in tgt.short_lots] == ["2021-01-01", "2022-05-01"]


# ---------------------------------------------------------------------------
# Factory: transfer rows -> InternalTransferEvent
# ---------------------------------------------------------------------------

class TestTransferEventFactory:

    def _factory(self):
        return DomainEventFactory(asset_resolver=_make_resolver())

    def test_out_leg_becomes_transfer_event(self):
        factory = self._factory()
        events = factory.create_events_from_transfers([_xfer_row()])
        assert len(events) == 1
        ev = events[0]
        assert isinstance(ev, InternalTransferEvent)
        assert ev.account_id == "U10000001"          # source (OUT leg)
        assert ev.target_account_id == "U10000002"   # destination
        assert ev.quantity == Decimal("80")          # abs of -80

    def test_in_leg_is_ignored(self):
        factory = self._factory()
        in_leg = _xfer_row(ClientAccountID="U10000002", Direction="IN",
                           TransferAccount="U10000001", Quantity="80", TransactionID="TX1")
        assert factory.create_events_from_transfers([in_leg]) == []

    def test_eur_cash_transfer_skipped(self):
        factory = self._factory()
        eur_cash = _xfer_row(AssetClass="CASH", CurrencyPrimary="EUR", Symbol="EUR",
                             Quantity="0", CashTransfer="-3162.44")
        assert factory.create_events_from_transfers([eur_cash]) == []

    def test_non_eur_cash_transfer_uses_cash_amount(self):
        factory = self._factory()
        usd_cash = _xfer_row(AssetClass="CASH", CurrencyPrimary="USD", Symbol="USD",
                            ISIN=None, Conid=None, Quantity="0", CashTransfer="-250.00")
        events = factory.create_events_from_transfers([usd_cash])
        assert len(events) == 1
        assert events[0].quantity == Decimal("250.00")


# ---------------------------------------------------------------------------
# Minimal resolver for the factory tests
# ---------------------------------------------------------------------------

def _make_resolver():
    from src.identification.asset_resolver import AssetResolver
    from src.classification.asset_classifier import AssetClassifier

    classifier = MagicMock(spec=AssetClassifier)

    def _prelim(ibkr_asset_class=None, ibkr_sub_category=None, description="", symbol=None):
        if (ibkr_asset_class or "").upper() == "CASH":
            return (AssetCategory.CASH_BALANCE, None)
        return (AssetCategory.STOCK, None)

    classifier.preliminary_classify.side_effect = _prelim
    return AssetResolver(classifier)
