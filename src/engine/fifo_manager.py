import logging
from dataclasses import dataclass, replace
from decimal import Decimal, Context, getcontext as get_global_context
from typing import List, Optional, Tuple
import uuid
from datetime import date as date_obj, datetime

from src.domain.assets import Asset, MarkPosition, Option
from src.domain.events import FinancialEvent, TradeEvent, CorpActionSplitForward, CorpActionMergerCash, CorpActionStockDividend, CorpActionMergerStock, OptionLifecycleEvent, CorporateActionEvent, CorpActionExpireDividendRights
from src.domain.results import RealizedGainLoss
from src.domain.enums import AssetCategory, FinancialEventType, TaxReportingCategory, RealizationType, InvestmentFundType
from src.domain.exceptions import DataIntegrityError, ProcessingError
from src.utils.currency_converter import CurrencyConverter
from src.utils.exchange_rate_provider import ECBExchangeRateProvider
from src.utils.type_utils import parse_ibkr_date, safe_decimal
from src.utils.tax_utils import get_teilfreistellung_rate_for_fund_type
from src.tax_law.holding_period import is_within_section23_speculation_period 
import src.config as global_config

logger = logging.getLogger(__name__)

@dataclass
class FifoLot:
    acquisition_date: str  # YYYY-MM-DD
    quantity: Decimal # Represents shares/units OR contracts for options
    unit_cost_basis_eur: Decimal # Renamed from cost_basis_eur_per_unit
    total_cost_basis_eur: Decimal # Stored with high precision
    source_transaction_id: str # IBKR Transaction ID (or fallback string like "SOY_FALLBACK")
    # False on a lot the historical replay could not reconstruct, where the
    # opening snapshot gave the quantity and the date above is a placeholder
    # standing for "already held when the tax year opened". Nothing may read
    # that date as a fact: § 18 Abs. 2 InvStG reduces the Vorabpauschale by a
    # twelfth for each month before acquisition, so believing a placeholder of
    # 31 December would cut a whole year's deemed income to one twelfth.
    acquisition_date_is_known: bool = True
    # Gross Vorabpauschale declared over the holding period of the units CURRENTLY
    # in this lot, accumulated year by year as the replay passes each year end
    # (src/engine/vorabpauschale_attribution.py). It is what § 19 Abs. 1 Satz 3
    # InvStG deducts from the gain when these units are disposed of, and Satz 4
    # makes it the gross figure, before Teilfreistellung ([GT-INVSTG-030]).
    #
    # A total, not a per-unit rate: it travels with the units, so anything taking
    # units out of the lot takes the same fraction of it with them — a partial
    # sale, and the resize at a checkpoint mark. A split changes the unit count
    # without changing the units, and leaves this alone.
    vorabpauschale_gross_eur: Decimal = Decimal(0)

    def __post_init__(self):
        if not isinstance(self.quantity, Decimal) or not self.quantity.is_finite() or self.quantity <= Decimal(0):
            raise ValueError(f"FifoLot quantity must be a positive finite Decimal: {self.quantity} (type: {type(self.quantity)})")
        if not isinstance(self.unit_cost_basis_eur, Decimal) or not self.unit_cost_basis_eur.is_finite() or self.unit_cost_basis_eur < Decimal(0): # Renamed
            raise ValueError(f"FifoLot unit_cost_basis_eur must be a non-negative finite Decimal: {self.unit_cost_basis_eur}") # Renamed
        if not isinstance(self.total_cost_basis_eur, Decimal) or not self.total_cost_basis_eur.is_finite() or self.total_cost_basis_eur < Decimal(0):
            raise ValueError(f"FifoLot total_cost_basis_eur must be a non-negative finite Decimal: {self.total_cost_basis_eur}")
        if not self.source_transaction_id:
             raise ValueError(f"FifoLot requires a non-empty source_transaction_id.")

        ctx_check = Context(prec=get_global_context().prec)
        expected_total = ctx_check.multiply(self.quantity, self.unit_cost_basis_eur) # Renamed
        
        places_total = abs(global_config.OUTPUT_PRECISION_AMOUNTS.as_tuple().exponent) # Renamed
        places_unit = abs(global_config.OUTPUT_PRECISION_PER_SHARE.as_tuple().exponent) # Renamed
        tolerance_exponent = min(places_total, places_unit) - 1 
        tolerance = Decimal('1e-' + str(tolerance_exponent))

        if abs(self.total_cost_basis_eur - expected_total) > tolerance and expected_total != Decimal(0): 
             logger.warning(
                 f"FifoLot {self.source_transaction_id}: total_cost_basis_eur {self.total_cost_basis_eur} "
                 f"differs significantly from (quantity {self.quantity} * unit_cost_basis_eur {self.unit_cost_basis_eur} = {expected_total}). " # Renamed
                 f"Difference: {self.total_cost_basis_eur - expected_total}. Using provided total_cost_basis_eur."
             )

@dataclass
class ShortFifoLot:
    opening_date: str  # YYYY-MM-DD
    quantity_shorted: Decimal # Represents shares/units OR contracts for options (always positive)
    unit_sale_proceeds_eur: Decimal # Renamed from sale_proceeds_eur_per_unit
    total_sale_proceeds_eur: Decimal # Total sale proceeds when shorted
    source_transaction_id: str # IBKR Transaction ID (or fallback string like "SOY_FALLBACK_SHORT")

    def __post_init__(self):
        if not isinstance(self.quantity_shorted, Decimal) or not self.quantity_shorted.is_finite() or self.quantity_shorted <= Decimal(0):
            raise ValueError(f"ShortFifoLot quantity_shorted must be a positive finite Decimal: {self.quantity_shorted}")
        if not isinstance(self.unit_sale_proceeds_eur, Decimal) or not self.unit_sale_proceeds_eur.is_finite() or self.unit_sale_proceeds_eur < Decimal(0): # Renamed
            raise ValueError(f"ShortFifoLot unit_sale_proceeds_eur must be a non-negative finite Decimal: {self.unit_sale_proceeds_eur}") # Renamed
        if not isinstance(self.total_sale_proceeds_eur, Decimal) or not self.total_sale_proceeds_eur.is_finite() or self.total_sale_proceeds_eur < Decimal(0):
            raise ValueError(f"ShortFifoLot total_sale_proceeds_eur must be a non-negative finite Decimal: {self.total_sale_proceeds_eur}")
        if not self.source_transaction_id:
            raise ValueError(f"ShortFifoLot requires a non-empty source_transaction_id.")

        ctx_check = Context(prec=get_global_context().prec)
        expected_total = ctx_check.multiply(self.quantity_shorted, self.unit_sale_proceeds_eur) # Renamed

        places_total = abs(global_config.OUTPUT_PRECISION_AMOUNTS.as_tuple().exponent) # Renamed
        places_unit = abs(global_config.OUTPUT_PRECISION_PER_SHARE.as_tuple().exponent) # Renamed
        tolerance_exponent = min(places_total, places_unit) - 1
        tolerance = Decimal('1e-' + str(tolerance_exponent))
        
        if abs(self.total_sale_proceeds_eur - expected_total) > tolerance and expected_total != Decimal(0):
            logger.warning(
                f"ShortFifoLot {self.source_transaction_id}: total_sale_proceeds_eur {self.total_sale_proceeds_eur} "
                f"differs significantly from (quantity {self.quantity_shorted} * unit_sale_proceeds_eur {self.unit_sale_proceeds_eur} = {expected_total}). " # Renamed
                f"Difference: {self.total_sale_proceeds_eur - expected_total}. Using provided total_sale_proceeds_eur."
            )

def _take_newest(lots, wanted: Decimal, size_of, resize):
    """Keep `wanted` units from the NEWEST end of a FIFO lot list.

    Used where the reconstruction covers more than the broker reports. The
    excess is a disposal the input does not contain; FIFO consumed oldest-first,
    so the survivors are at the newest end. Lots arrive oldest-first, so this
    walks backwards and returns them oldest-first again.
    """
    kept = []
    remaining = wanted
    for lot in reversed(lots):
        if remaining <= Decimal(0):
            break
        size = size_of(lot)
        if size <= remaining:
            kept.append(lot)
            remaining -= size
        else:
            kept.append(resize(lot, remaining))
            remaining = Decimal(0)
    kept.reverse()
    return kept


@dataclass(frozen=True)
class MarkReconciliation:
    """What happened when a ledger met one checkpoint mark.

    Returned so the engine can grade a disagreement without re-deriving it.
    `started_confirmed` is the grading input: an interval that began at a
    reported snapshot and ends at one has ground truth at both ends, so a
    disagreement is a defect. An interval that began from nothing is expected
    to disagree by whatever was held before the input window opened.
    """
    kept: bool                      # True: reconstruction survived. False: snapshot replaced it.
    started_confirmed: bool
    reconstructed_quantity: Decimal
    reported_quantity: Decimal
    oversell_observed: bool
    mark_label: str
    # The reconstruction held long AND short lots of the same instrument at once. Not a
    # position anyone can hold; it means the input's open/close indicators contradict each
    # other. Distinguished because it has nothing to do with a short trade history, which is
    # what a first-interval disagreement otherwise means.
    offsetting_long_and_short: bool = False


@dataclass
class ConsumedLotDetail:
    consumed_quantity: Decimal
    value_per_unit_eur: Decimal # Cost basis per unit for long, proceeds per unit for short
    original_lot_date: str # Acquisition date for long, opening date for short
    original_lot_source_tx_id: str


def split_position_flip_event(event: TradeEvent, available_long_qty: Decimal, available_short_qty: Decimal) -> List[TradeEvent]:
    """Split a position-flip trade (C;O / O;C) into close + open sub-events.

    Uses available ledger quantities to determine how much closes existing
    position vs opens new opposite position. Amounts are split proportionally.

    Returns a list of 1-2 TradeEvent objects with correct event_types,
    quantities, and proportionally split monetary amounts.
    """
    if not event.is_position_flip:
        return [event]

    abs_qty = event.quantity.copy_abs()

    # Determine close quantity based on event type (close direction)
    if event.event_type == FinancialEventType.TRADE_SELL_LONG:
        close_qty = min(abs_qty, available_long_qty)
        close_type = FinancialEventType.TRADE_SELL_LONG
        open_type = FinancialEventType.TRADE_SELL_SHORT_OPEN
    elif event.event_type == FinancialEventType.TRADE_BUY_SHORT_COVER:
        close_qty = min(abs_qty, available_short_qty)
        close_type = FinancialEventType.TRADE_BUY_SHORT_COVER
        open_type = FinancialEventType.TRADE_BUY_LONG
    else:
        logger.warning(f"Position flip event {event.event_id} has unexpected type {event.event_type.name}. Processing as-is.")
        return [event]

    open_qty = abs_qty - close_qty
    results: List[TradeEvent] = []

    def _make_sub_event(sub_type: FinancialEventType, sub_abs_qty: Decimal) -> TradeEvent:
        """Create a sub-event with proportionally split amounts."""
        ratio = sub_abs_qty / abs_qty
        # Preserve sign convention: BUY qty > 0, SELL qty < 0
        if sub_type in (FinancialEventType.TRADE_BUY_LONG, FinancialEventType.TRADE_BUY_SHORT_COVER):
            signed_qty = sub_abs_qty
        else:
            signed_qty = -sub_abs_qty

        # Proportionally split all monetary amounts
        sub_gross_fc = event.gross_amount_foreign_currency * ratio if event.gross_amount_foreign_currency is not None else None
        sub_gross_eur = event.gross_amount_eur * ratio if event.gross_amount_eur is not None else None
        sub_commission_fc = event.commission_foreign_currency * ratio if event.commission_foreign_currency is not None else None
        sub_commission_eur = event.commission_eur * ratio if event.commission_eur is not None else None
        sub_net = event.net_proceeds_or_cost_basis_eur * ratio if event.net_proceeds_or_cost_basis_eur is not None else None

        return TradeEvent(
            asset_internal_id=event.asset_internal_id,
            event_date=event.event_date,
            account_id=event.account_id,
            event_type=sub_type,
            quantity=signed_qty,
            price_foreign_currency=event.price_foreign_currency,
            commission_foreign_currency=sub_commission_fc,
            commission_currency=event.commission_currency,
            commission_eur=sub_commission_eur,
            net_proceeds_or_cost_basis_eur=sub_net,
            related_option_event_id=None,  # flip events don't arise from option exercise
            is_position_flip=False,
            local_currency=event.local_currency,
            gross_amount_foreign_currency=sub_gross_fc,
            gross_amount_eur=sub_gross_eur,
            ibkr_transaction_id=event.ibkr_transaction_id,
            ibkr_activity_description=event.ibkr_activity_description,
            ibkr_notes_codes=event.ibkr_notes_codes,
        )

    if close_qty > Decimal(0):
        results.append(_make_sub_event(close_type, close_qty))

    if open_qty > Decimal(0):
        results.append(_make_sub_event(open_type, open_qty))

    if not results:
        logger.warning(f"Position flip event {event.event_id}: both close and open quantities are zero. Skipping.")

    logger.info(
        f"Split position flip {event.ibkr_transaction_id}: "
        f"{close_type.name}({close_qty}) + {open_type.name}({open_qty}) from total {abs_qty}"
    )
    return results


class FifoLedger:
    def __init__(self,
                 asset_internal_id: uuid.UUID,
                 asset_category: AssetCategory,
                 asset_multiplier_from_asset: Optional[Decimal], 
                 currency_converter: CurrencyConverter,
                 exchange_rate_provider: ECBExchangeRateProvider,
                 internal_working_precision: int, # Will be renamed internal_calculation_precision where called
                 decimal_rounding_mode: str,
                 fund_type: Optional[InvestmentFundType] = None): 
        self.asset_internal_id: uuid.UUID = asset_internal_id
        self.asset_category: AssetCategory = asset_category
        self.fund_type: Optional[InvestmentFundType] = fund_type 

        if self.asset_category == AssetCategory.INVESTMENT_FUND and self.fund_type is None:
            logger.warning(f"FifoLedger for Investment Fund {asset_internal_id} initialized without a specific fund_type. Defaulting to InvestmentFundType.NONE. This may impact tax calculations if not intended.")
            self.fund_type = InvestmentFundType.NONE


        self.asset_multiplier_info: Optional[Decimal] = None
        if asset_multiplier_from_asset is not None:
            multiplier_dec = safe_decimal(asset_multiplier_from_asset)
            if multiplier_dec is not None and multiplier_dec > Decimal(0):
                self.asset_multiplier_info = multiplier_dec
            elif self.asset_category == AssetCategory.OPTION:
                 logger.warning(f"FifoLedger for Option asset {asset_internal_id} initialized with invalid asset_multiplier_from_asset ({asset_multiplier_from_asset}). Storing as is, but typically should be > 0.")
                 self.asset_multiplier_info = multiplier_dec if multiplier_dec is not None else Decimal(100)

        self.lots: List[FifoLot] = []
        self.short_lots: List[ShortFifoLot] = []
        self.currency_converter: CurrencyConverter = currency_converter
        self.exchange_rate_provider: ECBExchangeRateProvider = exchange_rate_provider

        self.ctx = Context(prec=internal_working_precision, rounding=decimal_rounding_mode)
        self.soy_fallback_lot_source_tx_id = f"SOY_FALLBACK_{asset_internal_id}"
        self.soy_fallback_short_lot_source_tx_id = f"SOY_FALLBACK_SHORT_{asset_internal_id}"
        # Has this ledger ever been pinned to a reported snapshot? False until the first
        # checkpoint mark is processed. It decides how a disagreement is graded: an interval
        # that began at a confirmed snapshot and ends at one has ground truth at both ends, so
        # a mismatch there is the engine's or the input's fault. An interval that began from
        # nothing -- the earliest one, before any snapshot exists -- is expected to disagree by
        # whatever was held before the window opened.
        self._mark_anchor_confirmed = False


    def initialize_lots_from_soy(self,
                                 asset: Asset,
                                 all_historical_events_for_asset: List[FinancialEvent],
                                 tax_year: int):
        """Convenience method: simulate + reconcile in one call (used when no mergers).

        Reconciles against the person-level record on the asset, which is one account's
        only when the person has one account.
        """
        self.simulate_historical_events(asset, all_historical_events_for_asset, tax_year)
        self.reconcile_with_soy_position(asset, tax_year, reported=MarkPosition(
            quantity=asset.soy_quantity,
            cost_basis_amount=asset.soy_cost_basis_amount,
            cost_basis_currency=asset.soy_cost_basis_currency,
        ))

    def begin_historical_simulation(self, asset: Asset):
        """Prepare the ledger for historical replay (unified replayer, AR5):
        resolve the fund type from the asset, clear lot state, reset the
        inconsistency flag. Apply events afterwards via
        apply_historical_event(); reconcile via reconcile_with_soy_position()."""
        if self.asset_category == AssetCategory.INVESTMENT_FUND:
            asset_fund_type = getattr(asset, 'fund_type', None)
            if isinstance(asset_fund_type, InvestmentFundType) and asset_fund_type != InvestmentFundType.NONE:
                 if self.fund_type == InvestmentFundType.NONE:
                     logger.info(f"Updating FifoLedger fund_type for {self.asset_internal_id} from SOY asset object to {asset_fund_type}.")
                     self.fund_type = asset_fund_type
            elif self.fund_type is None:
                 logger.warning(f"FifoLedger for Investment Fund {self.asset_internal_id} still has no specific fund_type after asset load for SOY. Using InvestmentFundType.NONE.")
                 self.fund_type = InvestmentFundType.NONE

        self.lots.clear()
        self.short_lots.clear()
        self._historical_simulation_inconsistent = False

    def announce_historical_simulation(self, asset: Asset, event_count: int):
        """Log the per-asset simulation header (kept here so the log line is
        byte-identical to the pre-AR5 batch implementation)."""
        logger.info(f"Asset {asset.get_classification_key()} (ID: {asset.internal_asset_id}): Simulating "
                    f"{event_count} historical events.")

    def apply_historical_event(self, asset: Asset, hist_event: FinancialEvent, tax_year: int):
        """Apply ONE historical (pre-tax-year) event to the ledger — the
        per-event unit the unified replayer streams. Mutates lot state only;
        emits no current-year RGLs. Inconsistencies (e.g. selling more than
        reconstructed) set a flag that reconcile_with_mark REPORTS but does not
        act on: the reported snapshot is the sole arbiter of which lots survive.
        The flag deciding was what discarded exactly-matching reconstructions."""
        event_date_obj = parse_ibkr_date(hist_event.event_date)
        if not event_date_obj or event_date_obj >= date_obj(tax_year, 1, 1):
            logger.warning(f"Historical event {hist_event.event_id} for asset {asset.internal_asset_id} "
                           f"has date {hist_event.event_date} which is not before tax year {tax_year}. Skipping for SOY init.")
            return

        try:
            if isinstance(hist_event, TradeEvent):
                # Split position flip events (C;O / O;C) using current ledger state
                if hist_event.is_position_flip:
                    avail_long = sum(lot.quantity for lot in self.lots) if self.lots else Decimal(0)
                    avail_short = sum(lot.quantity_shorted for lot in self.short_lots) if self.short_lots else Decimal(0)
                    sub_events = split_position_flip_event(hist_event, avail_long, avail_short)
                else:
                    sub_events = [hist_event]

                for sub in sub_events:
                    if sub.event_type == FinancialEventType.TRADE_BUY_LONG:
                        self.add_long_lot(sub)
                    elif sub.event_type == FinancialEventType.TRADE_SELL_LONG:
                        self.consume_long_lots_for_sale(sub, is_historical_simulation=True)
                    elif sub.event_type == FinancialEventType.TRADE_SELL_SHORT_OPEN:
                        self.add_short_lot(sub)
                    elif sub.event_type == FinancialEventType.TRADE_BUY_SHORT_COVER:
                        self.consume_short_lots_for_cover(sub, is_historical_simulation=True)
            elif isinstance(hist_event, CorpActionSplitForward):
                self.adjust_lots_for_split(hist_event)
            elif isinstance(hist_event, CorpActionStockDividend):
                 self.add_lot_for_stock_dividend(hist_event)
            elif isinstance(hist_event, OptionLifecycleEvent):
                self._close_position_lots_historically(
                    asset, hist_event, hist_event.quantity_contracts)
            elif isinstance(hist_event, CorpActionMergerCash):
                # Bought out for cash: the holding is disposed of and the shares leave the
                # depot. Only the lot effect is applied -- the gain belongs to the year the
                # merger fell in, which the historical replay does not declare.
                self._close_position_lots_historically(
                    asset, hist_event, hist_event.quantity_disposed)
            elif isinstance(hist_event, CorpActionExpireDividendRights):
                # Rights lapse; whatever the ledger holds of them ceases to exist.
                self._close_position_lots_historically(
                    asset, hist_event,
                    sum((lot.quantity for lot in self.lots), Decimal(0)))
            elif isinstance(hist_event, CorporateActionEvent):
                # Every corporate-action kind with a ledger effect must have a branch above.
                # Falling through used to be silent, and silence is how a cash merger left 200
                # ATVI shares in the ledger for every year after 2023 (found by the checkpoint
                # marks, not by the suite). A new kind should stop the run, not vanish.
                raise ProcessingError(
                    f"Historical replay has no handler for {type(hist_event).__name__} "
                    f"({hist_event.event_type.name}) on {asset.get_classification_key()} at "
                    f"{hist_event.event_date}. It was routed into the historical bucket, so it "
                    f"is expected to affect the ledger; leaving it unapplied would carry a "
                    f"phantom holding into every later year.")
        except UserWarning as uw:
            logger.warning(f"Historical simulation warning for asset {asset.internal_asset_id} processing event {hist_event.event_id}: {uw}")
            self._historical_simulation_inconsistent = True

    def _close_position_lots_historically(self, asset: Asset, hist_event,
                                          contracts: Optional[Decimal]) -> None:
        """Remove `contracts` units of this asset's lots for a closing event in the window.

        Expiration, exercise, assignment and cash settlement all end the option
        position; only their tax treatment differs, and no realised gain is
        computed here because the historical replay declares nothing. What the
        replay needs is the lot effect, and without it an option opened and
        closed inside the window leaves a phantom holding that offsets the
        ledger for every year that follows.

        The share leg of an exercise or assignment is NOT handled here: IBKR
        books it as an ordinary stock trade in the Trades file, and that already
        replays against the underlying's own ledger. Touching the underlying
        here would double it.

        Consuming from the oldest end matches the current-year processors, which
        run FIFO over the same lots.
        """
        if contracts is None:
            raise ProcessingError(
                f"Historical option lifecycle event {hist_event.event_id} for asset "
                f"{asset.get_classification_key()} carries no contract count, so the lots it "
                f"closes cannot be determined.")
        remaining = contracts.copy_abs()
        if remaining == Decimal(0):
            return

        closed_long = closed_short = Decimal(0)
        while remaining > Decimal(0) and self.lots:
            lot = self.lots[0]
            take = min(lot.quantity, remaining)
            lot.quantity -= take
            remaining -= take
            closed_long += take
            if lot.quantity == Decimal(0):
                self.lots.pop(0)
        while remaining > Decimal(0) and self.short_lots:
            lot = self.short_lots[0]
            take = min(lot.quantity_shorted, remaining)
            lot.quantity_shorted -= take
            remaining -= take
            closed_short += take
            if lot.quantity_shorted == Decimal(0):
                self.short_lots.pop(0)

        if remaining > Decimal(0):
            # Same treatment as an oversell: the replay could not apply the whole event, which
            # the mark grading then sees. Not fatal here -- a later snapshot may still agree.
            logger.warning(
                f"Historical simulation: option lifecycle event {hist_event.event_id} "
                f"({hist_event.event_type.name}) for {asset.get_classification_key()} wanted to "
                f"close {contracts.copy_abs()} contract(s) but the ledger held "
                f"{closed_long + closed_short}. {remaining} unaccounted for.")
            self._historical_simulation_inconsistent = True
        else:
            logger.debug(
                f"Historical {hist_event.event_type.name} closed {closed_long} long / "
                f"{closed_short} short contract(s) of {asset.get_classification_key()}.")

    def simulate_historical_events(self,
                                    asset: Asset,
                                    all_historical_events_for_asset: List[FinancialEvent],
                                    tax_year: int):
        """Batch wrapper over begin_historical_simulation + apply_historical_event
        (kept for direct callers/tests; the engine streams per event)."""
        self.begin_historical_simulation(asset)
        self.announce_historical_simulation(asset, len(all_historical_events_for_asset))
        for hist_event in all_historical_events_for_asset:
            self.apply_historical_event(asset, hist_event, tax_year)

    def reconcile_with_soy_position(self, asset: Asset, tax_year: int, *,
                                    reported: Optional["MarkPosition"]) -> "MarkReconciliation":
        """Reconcile against the tax year's opening snapshot -- the final mark.

        The SoY record is read from `Positions-{tax_year-1}-EoY.csv`, not from any SoY
        file. Thin wrapper over `reconcile_with_mark`, which every checkpoint uses.

        `reported` is THIS ledger's account's row of that snapshot, because FIFO is
        applied per Depot ([GT-ESTG20-013]). It is passed in rather than read off the
        asset: the record on `Asset` is the person's total across their accounts, and
        handing that to one account's ledger would give every account the whole holding.
        `None` means the snapshot does not list this account for this asset, i.e. it
        reports zero units there.
        """
        return self.reconcile_with_mark(
            asset,
            reported_quantity=reported.quantity if reported is not None else Decimal(0),
            reported_cost_basis=reported.cost_basis_amount if reported is not None else None,
            reported_cost_basis_currency=(reported.cost_basis_currency
                                          if reported is not None else None),
            mark_label=f"{tax_year - 1}-12-31 (opening snapshot)",
            fallback_acquisition_date=f"{tax_year-1}-12-31",
            fx_conversion_date=date_obj(tax_year, 1, 1),
        )

    def reconcile_with_mark(self, asset: Asset, *,
                            reported_quantity: Optional[Decimal],
                            reported_cost_basis: Optional[Decimal],
                            reported_cost_basis_currency: Optional[str],
                            mark_label: str,
                            fallback_acquisition_date: str,
                            fx_conversion_date) -> "MarkReconciliation":
        """Compare the reconstruction against one reported snapshot; on disagreement,
        discard it and take the snapshot.

        The snapshot is ground truth and the reconstruction is not, so the
        comparison is the sole arbiter. In particular the oversell flag does NOT
        force the fallback: an oversell says the replay could not apply
        something, and if the quantity still lands exactly on the broker's
        figure the reconstructed lots -- with their real acquisition dates and
        real cost bases -- are worth more than a synthesised one. Discarding an
        exactly-matching reconstruction because of the flag is what destroyed
        `DE0006766504`'s 2022-12-29 lots (issue #56 investigation).

        A reconstruction that *exceeds* the report is still usable, and is used:
        the excess means a disposal the input does not contain, and FIFO
        consumes oldest-first, so the units that survived to the mark are the
        NEWEST. Real dated lots beat a synthesised one, which is what
        `SOY_H_001` and `SOY_H_002` pin.

        Taking them from the newest end is the correction. The previous version
        filled from the oldest, which those two scenarios cannot distinguish --
        they hold a single lot, so either end returns it. It matters the moment
        the excess is a *phantom acquisition* rather than a missing disposal:
        a ledger holding [130 merged-in units dated 2022, 100 bought 2023]
        against a reported 100 yields the real 2023 lot from the newest end and
        the phantom from the oldest.

        A reconstruction that *falls short* cannot say which units the broker
        means, so there the snapshot replaces it.
        """
        started_confirmed = self._mark_anchor_confirmed
        inconsistent = getattr(self, '_historical_simulation_inconsistent', False)

        reconstructed_long_lots_snapshot = list(self.lots)
        reconstructed_short_lots_snapshot = list(self.short_lots)
        self.lots.clear()
        self.short_lots.clear()

        reconstructed_total_long_qty = sum(lot.quantity for lot in reconstructed_long_lots_snapshot)
        reconstructed_total_short_qty_abs = sum(lot.quantity_shorted for lot in reconstructed_short_lots_snapshot)
        reconstructed_net_qty = self.ctx.subtract(reconstructed_total_long_qty, reconstructed_total_short_qty_abs)

        if reported_quantity is None:
            logger.warning(f"Asset {asset.get_classification_key()}: reported quantity at mark "
                           f"{mark_label} is None. Treating as 0 for ledger initialization.")
            reported_quantity = Decimal(0)
        else:
            reported_quantity = reported_quantity.quantize(global_config.PRECISION_QUANTITY, context=self.ctx)

        logger.info(f"Asset {asset.get_classification_key()} @ {mark_label}: Reconstructed Qty: "
                    f"{reconstructed_net_qty}. Reported Qty: {reported_quantity}. "
                    f"Historical Sim Inconsistent: {inconsistent}")

        # Sign structure must be consistent with the report, not merely the net: a securities
        # ledger holding long and short lots at once that happen to net to the reported figure
        # is not a reconstruction anyone should carry forward.
        covers_long = (reported_quantity > Decimal(0)
                       and reconstructed_total_long_qty >= reported_quantity
                       and reconstructed_total_short_qty_abs == Decimal(0))
        covers_short = (reported_quantity < Decimal(0)
                        and reconstructed_total_short_qty_abs >= reported_quantity.copy_abs()
                        and reconstructed_total_long_qty == Decimal(0))
        covers_flat = (reported_quantity == Decimal(0)
                       and reconstructed_total_long_qty == Decimal(0)
                       and reconstructed_total_short_qty_abs == Decimal(0))
        keeps_reconstruction = covers_long or covers_short or covers_flat

        if keeps_reconstruction:
            if covers_long:
                self.lots.extend(_take_newest(
                    reconstructed_long_lots_snapshot, reported_quantity,
                    lambda lot: lot.quantity,
                    lambda lot, qty: replace(
                        lot, quantity=qty,
                        total_cost_basis_eur=self.ctx.multiply(qty, lot.unit_cost_basis_eur),
                        # The dropped units take their share of the accumulated
                        # Vorabpauschale with them: they were disposed of in a year
                        # the input does not cover, and their deduction went with
                        # that disposal. `replace` would otherwise carry the whole
                        # lot's amount onto the survivors.
                        vorabpauschale_gross_eur=self._scaled_vorabpauschale(
                            lot, qty, lot.quantity))))
            elif covers_short:
                self.short_lots.extend(_take_newest(
                    reconstructed_short_lots_snapshot, reported_quantity.copy_abs(),
                    lambda lot: lot.quantity_shorted,
                    lambda lot, qty: replace(
                        lot, quantity_shorted=qty,
                        total_sale_proceeds_eur=self.ctx.multiply(qty, lot.unit_sale_proceeds_eur))))
            if reported_quantity != Decimal(0):
                logger.info(
                    f"Asset {asset.get_classification_key()} @ {mark_label}: keeping the "
                    f"reconstruction's real lots"
                    + ("." if reconstructed_net_qty == reported_quantity else
                       f"; it exceeds the report by "
                       f"{(reconstructed_net_qty - reported_quantity).copy_abs()}, attributed to "
                       f"disposals the input does not contain, so the oldest units are dropped."))
        else:
            logger.warning(
                f"Asset {asset.get_classification_key()} @ {mark_label}: reconstruction "
                f"(Long: {reconstructed_total_long_qty}, Short: {reconstructed_total_short_qty_abs}, "
                f"Inconsistent: {inconsistent}) disagrees with the reported quantity "
                f"({reported_quantity}). Discarding it and taking the snapshot.")
            if reported_quantity > Decimal(0):
                self._create_fallback_long_lot(
                    asset, reported_quantity, reported_cost_basis,
                    reported_cost_basis_currency, fallback_acquisition_date, fx_conversion_date)
            elif reported_quantity < Decimal(0):
                self._create_fallback_short_lot(
                    asset, reported_quantity.copy_abs(), reported_cost_basis,
                    reported_cost_basis_currency, fallback_acquisition_date, fx_conversion_date)

        if self.lots:
            self.lots.sort(key=lambda lot: (parse_ibkr_date(lot.acquisition_date) or datetime.min.date(), lot.source_transaction_id))
            if any((parse_ibkr_date(lot.acquisition_date) is None) for lot in self.lots):
                 raise ValueError(f"Unparseable acquisition date found in final lots for asset {self.asset_internal_id}.")
        if self.short_lots:
            self.short_lots.sort(key=lambda lot: (parse_ibkr_date(lot.opening_date) or datetime.min.date(), lot.source_transaction_id))
            if any((parse_ibkr_date(lot.opening_date) is None) for lot in self.short_lots):
                 raise ValueError(f"Unparseable opening date found in final short lots for asset {self.asset_internal_id}.")

        # From here on this ledger sits on ground truth, whichever branch ran: either the
        # reconstruction was confirmed by the snapshot, or the snapshot replaced it.
        self._mark_anchor_confirmed = True
        # The flag describes one interval. Reset it so the next interval's grading is its own.
        self._historical_simulation_inconsistent = False

        return MarkReconciliation(
            kept=keeps_reconstruction,
            started_confirmed=started_confirmed,
            reconstructed_quantity=reconstructed_net_qty,
            reported_quantity=reported_quantity,
            oversell_observed=inconsistent,
            mark_label=mark_label,
            offsetting_long_and_short=(reconstructed_total_long_qty > Decimal(0)
                                       and reconstructed_total_short_qty_abs > Decimal(0)),
        )

    def _create_fallback_long_lot(self, asset: Asset, quantity: Decimal,
                                  reported_cost_basis: Optional[Decimal],
                                  reported_cost_basis_currency: Optional[str],
                                  acquisition_date_str: str, fx_conversion_date):
        """Build the one lot that stands in for a discarded reconstruction at a mark.

        The snapshot supplies a quantity and a cost basis. It supplies no acquisition
        date, so the lot carries `acquisition_date_is_known=False`.

        **Exactly one consumer honours that flag: § 18 Abs. 2, which raises rather than
        read the placeholder. § 23 does not.** The holding period is computed straight
        from `acquisition_date`, so a placeholder would decide the Spekulationsfrist
        with no signal either way. This docstring claimed both refused until 2026-08-09;
        it now says what the code does. The assumption the gap rests on, measured over
        2021-2025: two undated lots exist, neither is a `PRIVATE_SALE_ASSET` -- the only
        category § 23 reaches -- and neither has been disposed of. It becomes live the
        day an undated lot is crypto, a metal ETP or a currency balance.

        **A cost basis this cannot use stops the run; it is never replaced by zero.**
        Three substitutions stood here until 2026-08-09 -- an absent basis, one that
        would not convert, and a negative one -- each logged and each making the whole
        of a later disposal a gain. Measured over `Positions-*.csv`, 2021-2025:
        `CostBasisMoney` is blank in 0 of 87 rows, and negative in 21 of 87 which are
        the 21 short rows, none of them long. So the sign carries information rather
        than marking an anomaly, and none of the three was reachable on a long lot.
        """
        if quantity <= Decimal(0): return
        if reported_cost_basis is None or reported_cost_basis_currency is None:
            raise ProcessingError(
                f"Asset {asset.get_classification_key()}: the position snapshot supplies "
                f"{quantity} units with no cost basis, so the gain on their disposal cannot "
                f"be computed. A zero basis would declare the whole proceeds as gain.")
        total_cost_basis_eur = self.ctx.create_decimal(reported_cost_basis)
        if reported_cost_basis_currency.upper() != "EUR":
            converted_eur = self.currency_converter.convert_to_eur(
                original_amount=total_cost_basis_eur,
                original_currency=reported_cost_basis_currency,
                date_of_conversion=fx_conversion_date,
            )
            if converted_eur is None:
                raise ProcessingError(
                    f"Asset {asset.get_classification_key()}: no rate to convert the "
                    f"{reported_cost_basis_currency} cost basis of {quantity} units at "
                    f"{fx_conversion_date}, so their gain on disposal cannot be computed.")
            total_cost_basis_eur = self.ctx.create_decimal(converted_eur)
        if total_cost_basis_eur < Decimal(0):
            raise ProcessingError(
                f"Asset {asset.get_classification_key()}: the snapshot reports a negative "
                f"cost basis {total_cost_basis_eur} EUR for a LONG position of {quantity} "
                f"units. In this broker's exports a negative basis marks a short, so this "
                f"is a contradiction rather than a value to floor at zero.")
        cost_per_unit = self.ctx.divide(total_cost_basis_eur, quantity) if quantity != Decimal(0) else Decimal(0)
        fallback_lot = FifoLot(
            acquisition_date=acquisition_date_str, quantity=quantity,
            unit_cost_basis_eur=cost_per_unit, total_cost_basis_eur=total_cost_basis_eur, # Renamed
            source_transaction_id=self.soy_fallback_lot_source_tx_id,
            acquisition_date_is_known=False,
        )
        self.lots.append(fallback_lot)
        logger.info(
            f"Asset {asset.get_classification_key()}: Created fallback SOY long lot: "
            f"Qty: {fallback_lot.quantity}, Cost/Unit EUR: {fallback_lot.unit_cost_basis_eur}, Acq. Date: {fallback_lot.acquisition_date}" # Renamed
        )

    def _create_fallback_short_lot(self, asset: Asset, quantity_abs: Decimal,
                                   reported_cost_basis: Optional[Decimal],
                                   reported_cost_basis_currency: Optional[str],
                                   opening_date_str: str, fx_conversion_date):
        """Short-side counterpart of `_create_fallback_long_lot`. IBKR reports the
        opening proceeds of a short position in the cost-basis column.

        Proceeds this cannot use stop the run, for the reason given on the long side:
        a zero here makes the entire cover cost a loss. The `copy_abs()` is why there is
        no negative branch to match the long one -- on a short, a negative
        `CostBasisMoney` is the normal sign and carries the meaning.
        """
        if quantity_abs <= Decimal(0): return
        if reported_cost_basis is None or reported_cost_basis_currency is None:
            raise ProcessingError(
                f"Asset {asset.get_classification_key()}: the position snapshot reports a "
                f"short of {quantity_abs} units with no opening proceeds, so the gain on "
                f"covering them cannot be computed. Zero proceeds would declare the whole "
                f"cover cost as a loss.")
        total_proceeds_eur = self.ctx.create_decimal(reported_cost_basis).copy_abs()
        if reported_cost_basis_currency.upper() != "EUR":
            converted_eur = self.currency_converter.convert_to_eur(
                original_amount=total_proceeds_eur,
                original_currency=reported_cost_basis_currency,
                date_of_conversion=fx_conversion_date,
            )
            if converted_eur is None:
                raise ProcessingError(
                    f"Asset {asset.get_classification_key()}: no rate to convert the "
                    f"{reported_cost_basis_currency} opening proceeds of {quantity_abs} "
                    f"short units at {fx_conversion_date}.")
            total_proceeds_eur = self.ctx.create_decimal(converted_eur)
        proceeds_per_unit = self.ctx.divide(total_proceeds_eur, quantity_abs) if quantity_abs != Decimal(0) else Decimal(0)
        fallback_short_lot = ShortFifoLot(
            opening_date=opening_date_str, quantity_shorted=quantity_abs,
            unit_sale_proceeds_eur=proceeds_per_unit, total_sale_proceeds_eur=total_proceeds_eur, # Renamed
            source_transaction_id=self.soy_fallback_short_lot_source_tx_id
        )
        self.short_lots.append(fallback_short_lot)
        logger.info(
            f"Asset {asset.get_classification_key()}: Created fallback SOY short lot: "
            f"Qty Short: {fallback_short_lot.quantity_shorted}, Proceeds/Unit EUR: {fallback_short_lot.unit_sale_proceeds_eur}, Opening Date: {fallback_short_lot.opening_date}" # Renamed
        )

    def drain_all_long_lots(self) -> List[FifoLot]:
        """Remove and return all long lots from this ledger."""
        drained = list(self.lots)
        self.lots.clear()
        return drained

    def drain_all_short_lots(self) -> List[ShortFifoLot]:
        """Remove and return all short lots from this ledger."""
        drained = list(self.short_lots)
        self.short_lots.clear()
        return drained

    def receive_all_lots_from_merger(self,
                                     long_lots: List[FifoLot],
                                     short_lots: List[ShortFifoLot],
                                     ratio: Decimal,
                                     merger_event: CorpActionMergerStock) -> None:
        """
        Atomic prepare-then-commit transfer of lots from a merger source.

        Phase 1 (PREPARE): Constructs all target FifoLot/ShortFifoLot objects.
            FifoLot.__post_init__ / ShortFifoLot.__post_init__ validation runs here.
            If any construction fails, exception propagates — no ledger was touched.

        Phase 2 (COMMIT): Extends self.lots / self.short_lots and re-sorts.
            Cannot fail (just list.extend + sort).
        """
        # Phase 1 — PREPARE (can fail, no ledger mutation)
        prepared_long_lots: List[FifoLot] = []
        for lot in long_lots:
            new_qty = self.ctx.multiply(lot.quantity, ratio)
            new_unit_cost = self.ctx.divide(lot.total_cost_basis_eur, new_qty) if new_qty != Decimal(0) else Decimal(0)
            prepared_long_lots.append(FifoLot(
                acquisition_date=lot.acquisition_date,
                quantity=new_qty,
                unit_cost_basis_eur=new_unit_cost,
                total_cost_basis_eur=lot.total_cost_basis_eur,
                source_transaction_id=str(merger_event.event_id),
                # The new units step into the tax position of the old ones, which
                # is why the acquisition date and cost basis above travel with
                # them. The Vorabpauschalen those units already bore travel for the
                # same reason: they were angesetzt during this holding period and
                # § 19 Abs. 1 Satz 3 deducts them when it ends. Rebuilding the lot
                # without this drops them, and the loss is silent.
                vorabpauschale_gross_eur=lot.vorabpauschale_gross_eur,
            ))

        prepared_short_lots: List[ShortFifoLot] = []
        for lot in short_lots:
            new_qty = self.ctx.multiply(lot.quantity_shorted, ratio)
            new_unit_proceeds = self.ctx.divide(lot.total_sale_proceeds_eur, new_qty) if new_qty != Decimal(0) else Decimal(0)
            prepared_short_lots.append(ShortFifoLot(
                opening_date=lot.opening_date,
                quantity_shorted=new_qty,
                unit_sale_proceeds_eur=new_unit_proceeds,
                total_sale_proceeds_eur=lot.total_sale_proceeds_eur,
                source_transaction_id=str(merger_event.event_id),
            ))

        # Phase 2 — COMMIT (cannot fail)
        self.lots.extend(prepared_long_lots)
        self.lots.sort(key=lambda l: (parse_ibkr_date(l.acquisition_date) or datetime.min.date(), l.source_transaction_id))
        self.short_lots.extend(prepared_short_lots)
        self.short_lots.sort(key=lambda l: (parse_ibkr_date(l.opening_date) or datetime.min.date(), l.source_transaction_id))

    def add_long_lot(self, trade_event: TradeEvent):
        if trade_event.event_type != FinancialEventType.TRADE_BUY_LONG: return
        if trade_event.quantity is None or trade_event.quantity <= Decimal(0): return
        if trade_event.net_proceeds_or_cost_basis_eur is None: return
        if not trade_event.ibkr_transaction_id:
            raise ValueError(f"Missing ibkr_transaction_id for trade {trade_event.event_id} needed for FIFO lot creation.")

        total_cost_basis_eur = self.ctx.create_decimal(trade_event.net_proceeds_or_cost_basis_eur)
        lot_qty_contracts_or_units = trade_event.quantity.quantize(global_config.PRECISION_QUANTITY, context=self.ctx)

        if lot_qty_contracts_or_units == Decimal(0):
            raise DataIntegrityError(f"TradeEvent {trade_event.ibkr_transaction_id} (BUY_LONG) has zero quantity after quantization. Original quantity: {trade_event.quantity}.")
        cost_basis_eur_per_unit = self.ctx.divide(total_cost_basis_eur, lot_qty_contracts_or_units)

        new_lot = FifoLot(
            acquisition_date=trade_event.event_date, quantity=lot_qty_contracts_or_units, 
            unit_cost_basis_eur=cost_basis_eur_per_unit, # Renamed
            total_cost_basis_eur=total_cost_basis_eur,
            source_transaction_id=trade_event.ibkr_transaction_id
        )
        self.lots.append(new_lot)
        self.lots.sort(key=lambda lot: (parse_ibkr_date(lot.acquisition_date) or datetime.min.date(), lot.source_transaction_id))
        if any((parse_ibkr_date(lot.acquisition_date) is None) for lot in self.lots):
             raise ValueError(f"Unparseable acquisition date found in FIFO lots for asset {self.asset_internal_id} after adding lot.")

    def add_short_lot(self, trade_event: TradeEvent):
        if trade_event.event_type != FinancialEventType.TRADE_SELL_SHORT_OPEN: return
        if trade_event.quantity is None or trade_event.quantity >= Decimal(0): return
        if trade_event.net_proceeds_or_cost_basis_eur is None:
            raise DataIntegrityError(f"Cannot add short lot for trade {trade_event.ibkr_transaction_id} - net_proceeds_or_cost_basis_eur is None. Event must be enriched before FIFO processing.")
        if not trade_event.ibkr_transaction_id:
            raise ValueError(f"Missing ibkr_transaction_id for trade {trade_event.event_id} needed for Short FIFO lot creation.")

        total_sale_proceeds_eur = self.ctx.create_decimal(trade_event.net_proceeds_or_cost_basis_eur).copy_abs()
        lot_qty_shorted_contracts_or_units = trade_event.quantity.copy_abs().quantize(global_config.PRECISION_QUANTITY, context=self.ctx)

        if lot_qty_shorted_contracts_or_units == Decimal(0):
            raise DataIntegrityError(f"TradeEvent {trade_event.ibkr_transaction_id} (SELL_SHORT_OPEN) has zero quantity after quantization. Original quantity: {trade_event.quantity}.")
        sale_proceeds_eur_per_unit = self.ctx.divide(total_sale_proceeds_eur, lot_qty_shorted_contracts_or_units)

        new_short_lot = ShortFifoLot(
            opening_date=trade_event.event_date, quantity_shorted=lot_qty_shorted_contracts_or_units,
            unit_sale_proceeds_eur=sale_proceeds_eur_per_unit, # Renamed
            total_sale_proceeds_eur=total_sale_proceeds_eur,
            source_transaction_id=trade_event.ibkr_transaction_id
        )
        self.short_lots.append(new_short_lot)
        self.short_lots.sort(key=lambda lot: (parse_ibkr_date(lot.opening_date) or datetime.min.date(), lot.source_transaction_id))
        if any((parse_ibkr_date(lot.opening_date) is None) for lot in self.short_lots):
             raise ValueError(f"Unparseable opening date found in Short FIFO lots for asset {self.asset_internal_id} after adding lot.")


    def _scaled_vorabpauschale(self, lot: FifoLot, kept_quantity: Decimal,
                               original_quantity: Decimal) -> Decimal:
        """The part of a lot's accumulated Vorabpauschale that `kept_quantity` carries."""
        if lot.vorabpauschale_gross_eur == Decimal(0) or original_quantity <= Decimal(0):
            return Decimal(0)
        return self.ctx.divide(
            self.ctx.multiply(lot.vorabpauschale_gross_eur, kept_quantity),
            original_quantity)

    def _take_vorabpauschale_from_lot(self, lot: FifoLot, consumed_quantity: Decimal,
                                      quantity_before: Decimal) -> Decimal:
        """Remove the consumed units' share of the accumulated Vorabpauschale and return it.

        The § 19 Abs. 1 Satz 3 deduction follows the units disposed of, so a partial
        sale takes the same fraction of the lot's accumulation as of its quantity
        and the remainder stays behind for the next disposal. Called on every
        consumption path, including the historical replay, where the returned figure
        is discarded but the lot must still lose it -- those units are gone.
        """
        taken = self._scaled_vorabpauschale(lot, consumed_quantity, quantity_before)
        if taken != Decimal(0):
            lot.vorabpauschale_gross_eur = self.ctx.subtract(
                lot.vorabpauschale_gross_eur, taken)
        return taken

    def consume_long_lots_for_sale(self, sale_event: TradeEvent, is_historical_simulation: bool = False) -> List[RealizedGainLoss]:
        if sale_event.event_type != FinancialEventType.TRADE_SELL_LONG: return []
        if sale_event.quantity is None or sale_event.quantity >= Decimal(0): return [] 
        if sale_event.net_proceeds_or_cost_basis_eur is None: return []

        quantity_to_realize = sale_event.quantity.copy_abs().quantize(global_config.PRECISION_QUANTITY, context=self.ctx)
        total_sale_proceeds_for_event = self.ctx.create_decimal(sale_event.net_proceeds_or_cost_basis_eur).copy_abs()

        if quantity_to_realize == Decimal(0): return []
        sale_proceeds_eur_per_unit_for_event = self.ctx.divide(total_sale_proceeds_for_event, quantity_to_realize)

        realized_gains_losses: List[RealizedGainLoss] = []
        quantity_remaining_to_realize = quantity_to_realize
        lots_to_remove_indices: List[int] = []
        current_available_qty_in_lots = sum(l.quantity for l in self.lots)


        realization_type_for_rgl: RealizationType
        if self.asset_category == AssetCategory.OPTION:
            realization_type_for_rgl = RealizationType.OPTION_TRADE_CLOSE_LONG
        else:
            realization_type_for_rgl = RealizationType.LONG_POSITION_SALE # Renamed

        for i, current_lot in enumerate(self.lots):
            if quantity_remaining_to_realize <= Decimal(0): break
            quantity_from_this_lot: Decimal
            quantity_in_lot_before_sale = current_lot.quantity
            if current_lot.quantity <= quantity_remaining_to_realize:
                quantity_from_this_lot = current_lot.quantity
                lots_to_remove_indices.append(i)
            else:
                quantity_from_this_lot = quantity_remaining_to_realize
                current_lot.quantity = self.ctx.subtract(current_lot.quantity, quantity_from_this_lot)
                current_lot.total_cost_basis_eur = self.ctx.multiply(current_lot.quantity, current_lot.unit_cost_basis_eur) # Renamed

            quantity_remaining_to_realize = self.ctx.subtract(quantity_remaining_to_realize, quantity_from_this_lot)

            # § 19 Abs. 1 Satz 3: the Vorabpauschalen these units bore. Taken here,
            # before the RGL is built and whether or not one is built, because the
            # units leave the lot either way.
            vorabpauschale_for_portion = self._take_vorabpauschale_from_lot(
                current_lot, quantity_from_this_lot, quantity_in_lot_before_sale)

            if not is_historical_simulation:
                cost_basis_for_portion = self.ctx.multiply(quantity_from_this_lot, current_lot.unit_cost_basis_eur) # Renamed
                realization_value_for_portion = self.ctx.multiply(quantity_from_this_lot, sale_proceeds_eur_per_unit_for_event)
                gross_gain_loss = self.ctx.subtract(realization_value_for_portion, cost_basis_for_portion)

                acq_date_obj = parse_ibkr_date(current_lot.acquisition_date)
                real_date_obj = parse_ibkr_date(sale_event.event_date)
                holding_period_days: Optional[int] = None
                within_speculation_period: Optional[bool] = None
                if acq_date_obj and real_date_obj and real_date_obj >= acq_date_obj :
                    holding_period_days = (real_date_obj - acq_date_obj).days
                    within_speculation_period = is_within_section23_speculation_period(acq_date_obj, real_date_obj)

                tax_cat: Optional[TaxReportingCategory] = None
                is_stillhalter_income_flag = False # Renamed from is_premium_gain
                is_taxable_under_section_23_flag = True # Renamed from is_taxable_under_rules_for_rgl
                
                rgl_fund_type: Optional[InvestmentFundType] = None
                rgl_tf_rate: Optional[Decimal] = None

                if self.asset_category == AssetCategory.STOCK:
                    tax_cat = TaxReportingCategory.ANLAGE_KAP_AKTIEN_GEWINN if gross_gain_loss >= Decimal(0) else TaxReportingCategory.ANLAGE_KAP_AKTIEN_VERLUST
                elif self.asset_category in [AssetCategory.BOND, AssetCategory.SONSTIGE_KAPITALFORDERUNG]:
                    # Both are 20 Abs. 2 Satz 1 Nr. 7 income and share Zeile 19 / Zeile 22.
                    # They stay distinct categories so the report can name them apart.
                    tax_cat = TaxReportingCategory.ANLAGE_KAP_SONSTIGE_KAPITALERTRAEGE if gross_gain_loss >= Decimal(0) else TaxReportingCategory.ANLAGE_KAP_SONSTIGE_VERLUSTE
                elif self.asset_category in [AssetCategory.OPTION, AssetCategory.CFD, AssetCategory.FUTURE]:
                    tax_cat = TaxReportingCategory.ANLAGE_KAP_TERMIN_GEWINN if gross_gain_loss >= Decimal(0) else TaxReportingCategory.ANLAGE_KAP_TERMIN_VERLUST
                elif self.asset_category == AssetCategory.INVESTMENT_FUND:
                    rgl_fund_type = self.fund_type
                    if rgl_fund_type is None: 
                        logger.error(f"CRITICAL: FifoLedger for Investment Fund {self.asset_internal_id} (Event: {sale_event.event_id}) has self.fund_type as None. Defaulting to InvestmentFundType.NONE for RGL.")
                        rgl_fund_type = InvestmentFundType.NONE
                    
                    rgl_tf_rate = get_teilfreistellung_rate_for_fund_type(rgl_fund_type)

                    if rgl_fund_type == InvestmentFundType.AKTIENFONDS:
                        tax_cat = TaxReportingCategory.ANLAGE_KAP_INV_AKTIENFONDS_GEWINN_GROSS
                    elif rgl_fund_type == InvestmentFundType.MISCHFONDS:
                        tax_cat = TaxReportingCategory.ANLAGE_KAP_INV_MISCHFONDS_GEWINN_GROSS
                    elif rgl_fund_type == InvestmentFundType.IMMOBILIENFONDS:
                        tax_cat = TaxReportingCategory.ANLAGE_KAP_INV_IMMOBILIENFONDS_GEWINN_GROSS
                    elif rgl_fund_type == InvestmentFundType.AUSLANDS_IMMOBILIENFONDS:
                        tax_cat = TaxReportingCategory.ANLAGE_KAP_INV_AUSLANDS_IMMOBILIENFONDS_GEWINN_GROSS
                    elif rgl_fund_type in [InvestmentFundType.SONSTIGE_FONDS, InvestmentFundType.NONE]:
                        tax_cat = TaxReportingCategory.ANLAGE_KAP_INV_SONSTIGE_FONDS_GEWINN_GROSS
                    else: 
                        raise ProcessingError(f"Unhandled InvestmentFundType '{rgl_fund_type}' for asset {self.asset_internal_id}, Event {sale_event.event_id}. Tax category mapping must be updated.")

                elif self.asset_category == AssetCategory.PRIVATE_SALE_ASSET: # Renamed
                    # §23 Jahresfrist: anniversary rule (§108 Abs. 1 AO i.V.m. §§187 Abs. 1,
                    # 188 Abs. 2-3 BGB), NOT a 365-day count. See
                    # reference/tax-law/estg-23-private-veraeusserung.md.
                    if within_speculation_period is None:
                        raise ProcessingError(
                            f"Cannot decide §23 taxability for asset {self.asset_internal_id}, "
                            f"Event {sale_event.event_id}: acquisition date "
                            f"'{current_lot.acquisition_date}' / realization date '{sale_event.event_date}' "
                            f"do not yield a usable date pair. An undecidable §23 case is "
                            f"unreported income, not an exempt one."
                        )
                    if within_speculation_period:
                        is_taxable_under_section_23_flag = True # Renamed
                        tax_cat = TaxReportingCategory.SECTION_23_ESTG_TAXABLE_GAIN if gross_gain_loss >= Decimal(0) else TaxReportingCategory.SECTION_23_ESTG_TAXABLE_LOSS
                    else: 
                        is_taxable_under_section_23_flag = False # Renamed
                        tax_cat = TaxReportingCategory.SECTION_23_ESTG_EXEMPT_HOLDING_PERIOD_MET
                
                rgl = RealizedGainLoss(
                    originating_event_id=sale_event.event_id, asset_internal_id=self.asset_internal_id,
                    asset_category_at_realization=self.asset_category, acquisition_date=current_lot.acquisition_date,
                    realization_date=sale_event.event_date,
                    realization_type=realization_type_for_rgl,
                    quantity_realized=quantity_from_this_lot,
                    unit_cost_basis_eur=current_lot.unit_cost_basis_eur, # Renamed kwarg
                    unit_realization_value_eur=sale_proceeds_eur_per_unit_for_event, # Renamed kwarg
                    total_cost_basis_eur=cost_basis_for_portion, # Renamed kwarg
                    total_realization_value_eur=realization_value_for_portion,
                    gross_gain_loss_eur=gross_gain_loss, holding_period_days=holding_period_days,
                    is_within_speculation_period=bool(within_speculation_period),
                    is_taxable_under_section_23=is_taxable_under_section_23_flag, # Renamed kwarg
                    tax_reporting_category=tax_cat,
                    is_stillhalter_income=is_stillhalter_income_flag, # Renamed kwarg
                    fund_type_at_sale=rgl_fund_type if self.asset_category == AssetCategory.INVESTMENT_FUND else None,
                    teilfreistellung_rate_applied=rgl_tf_rate if self.asset_category == AssetCategory.INVESTMENT_FUND else None,
                    vorabpauschale_deduction_eur=(
                        vorabpauschale_for_portion
                        if self.asset_category == AssetCategory.INVESTMENT_FUND else None),
                )
                realized_gains_losses.append(rgl)

        for i in sorted(lots_to_remove_indices, reverse=True): del self.lots[i]

        small_tolerance_qty = Decimal('1e-10') 
        if quantity_remaining_to_realize.copy_abs() > small_tolerance_qty:
            msg = (f"Insufficient long lots for sale event {sale_event.ibkr_transaction_id or sale_event.event_id} "
                   f"for asset {self.asset_internal_id}. Required to sell: {quantity_to_realize}, "
                   f"Total available in lots before this sale: {current_available_qty_in_lots}, " 
                   f"Remaining to sell after processing lots: {quantity_remaining_to_realize}.")
            if is_historical_simulation:
                logger.warning(f"Historical Simulation: {msg}")
                raise UserWarning(msg) 
            else:
                raise ValueError(msg)
        return realized_gains_losses

    def consume_short_lots_for_cover(self, cover_event: TradeEvent, is_historical_simulation: bool = False) -> List[RealizedGainLoss]:
        if cover_event.event_type != FinancialEventType.TRADE_BUY_SHORT_COVER: return []
        if cover_event.quantity is None or cover_event.quantity <= Decimal(0): return [] 
        if cover_event.net_proceeds_or_cost_basis_eur is None: return []

        quantity_to_realize = cover_event.quantity.quantize(global_config.PRECISION_QUANTITY, context=self.ctx) 
        total_cost_for_cover_event = self.ctx.create_decimal(cover_event.net_proceeds_or_cost_basis_eur) 

        if quantity_to_realize == Decimal(0): return []
        cost_eur_per_unit_for_cover_event = self.ctx.divide(total_cost_for_cover_event, quantity_to_realize)

        realized_gains_losses: List[RealizedGainLoss] = []
        quantity_remaining_to_realize = quantity_to_realize
        short_lots_to_remove_indices: List[int] = []
        current_available_qty_in_short_lots = sum(sl.quantity_shorted for sl in self.short_lots)


        realization_type_for_rgl: RealizationType
        if self.asset_category == AssetCategory.OPTION:
            realization_type_for_rgl = RealizationType.OPTION_TRADE_CLOSE_SHORT
        else:
            realization_type_for_rgl = RealizationType.SHORT_POSITION_COVER # Renamed

        for i, current_short_lot in enumerate(self.short_lots):
            if quantity_remaining_to_realize <= Decimal(0): break
            quantity_covered_from_this_lot: Decimal
            if current_short_lot.quantity_shorted <= quantity_remaining_to_realize:
                quantity_covered_from_this_lot = current_short_lot.quantity_shorted
                short_lots_to_remove_indices.append(i)
            else:
                quantity_covered_from_this_lot = quantity_remaining_to_realize
                current_short_lot.quantity_shorted = self.ctx.subtract(current_short_lot.quantity_shorted, quantity_covered_from_this_lot)
                current_short_lot.total_sale_proceeds_eur = self.ctx.multiply(current_short_lot.quantity_shorted, current_short_lot.unit_sale_proceeds_eur) # Renamed

            quantity_remaining_to_realize = self.ctx.subtract(quantity_remaining_to_realize, quantity_covered_from_this_lot)

            if not is_historical_simulation:
                cost_basis_for_portion = self.ctx.multiply(quantity_covered_from_this_lot, cost_eur_per_unit_for_cover_event)
                realization_value_for_portion = self.ctx.multiply(quantity_covered_from_this_lot, current_short_lot.unit_sale_proceeds_eur) # Renamed
                gross_gain_loss = self.ctx.subtract(realization_value_for_portion, cost_basis_for_portion) 

                open_date_obj = parse_ibkr_date(current_short_lot.opening_date)
                cover_date_obj = parse_ibkr_date(cover_event.event_date)
                holding_period_days: Optional[int] = None
                within_speculation_period: Optional[bool] = None
                if open_date_obj and cover_date_obj and cover_date_obj >= open_date_obj:
                    holding_period_days = (cover_date_obj - open_date_obj).days
                    within_speculation_period = is_within_section23_speculation_period(open_date_obj, cover_date_obj)

                tax_cat: Optional[TaxReportingCategory] = None
                is_stillhalter_income_flag = False # Renamed
                is_taxable_under_section_23_flag = True # Renamed

                rgl_fund_type: Optional[InvestmentFundType] = None
                rgl_tf_rate: Optional[Decimal] = None

                if self.asset_category == AssetCategory.STOCK:
                    tax_cat = TaxReportingCategory.ANLAGE_KAP_AKTIEN_GEWINN if gross_gain_loss >= Decimal(0) else TaxReportingCategory.ANLAGE_KAP_AKTIEN_VERLUST
                elif self.asset_category in [AssetCategory.BOND, AssetCategory.SONSTIGE_KAPITALFORDERUNG]:
                    # Both are 20 Abs. 2 Satz 1 Nr. 7 income and share Zeile 19 / Zeile 22.
                    # They stay distinct categories so the report can name them apart.
                    tax_cat = TaxReportingCategory.ANLAGE_KAP_SONSTIGE_KAPITALERTRAEGE if gross_gain_loss >= Decimal(0) else TaxReportingCategory.ANLAGE_KAP_SONSTIGE_VERLUSTE
                elif self.asset_category in [AssetCategory.OPTION, AssetCategory.CFD, AssetCategory.FUTURE]:
                    tax_cat = TaxReportingCategory.ANLAGE_KAP_TERMIN_GEWINN if gross_gain_loss >= Decimal(0) else TaxReportingCategory.ANLAGE_KAP_TERMIN_VERLUST
                    if self.asset_category == AssetCategory.OPTION and gross_gain_loss >= Decimal(0):
                        is_stillhalter_income_flag = True # Renamed
                elif self.asset_category == AssetCategory.INVESTMENT_FUND:
                    rgl_fund_type = self.fund_type
                    if rgl_fund_type is None: 
                        logger.error(f"CRITICAL: FifoLedger for Investment Fund {self.asset_internal_id} (Event: {cover_event.event_id}) has self.fund_type as None. Defaulting to InvestmentFundType.NONE for RGL.")
                        rgl_fund_type = InvestmentFundType.NONE
                    
                    rgl_tf_rate = get_teilfreistellung_rate_for_fund_type(rgl_fund_type)
                    
                    if rgl_fund_type == InvestmentFundType.AKTIENFONDS:
                        tax_cat = TaxReportingCategory.ANLAGE_KAP_INV_AKTIENFONDS_GEWINN_GROSS
                    elif rgl_fund_type == InvestmentFundType.MISCHFONDS:
                        tax_cat = TaxReportingCategory.ANLAGE_KAP_INV_MISCHFONDS_GEWINN_GROSS
                    elif rgl_fund_type == InvestmentFundType.IMMOBILIENFONDS:
                        tax_cat = TaxReportingCategory.ANLAGE_KAP_INV_IMMOBILIENFONDS_GEWINN_GROSS
                    elif rgl_fund_type == InvestmentFundType.AUSLANDS_IMMOBILIENFONDS:
                        tax_cat = TaxReportingCategory.ANLAGE_KAP_INV_AUSLANDS_IMMOBILIENFONDS_GEWINN_GROSS
                    elif rgl_fund_type in [InvestmentFundType.SONSTIGE_FONDS, InvestmentFundType.NONE]:
                        tax_cat = TaxReportingCategory.ANLAGE_KAP_INV_SONSTIGE_FONDS_GEWINN_GROSS
                    else: 
                        raise ProcessingError(f"Unhandled InvestmentFundType '{rgl_fund_type}' for asset {self.asset_internal_id}, Event {cover_event.event_id}. Tax category mapping must be updated.")

                elif self.asset_category == AssetCategory.PRIVATE_SALE_ASSET: # Renamed
                    # §23 Jahresfrist: anniversary rule (§108 Abs. 1 AO i.V.m. §§187 Abs. 1,
                    # 188 Abs. 2-3 BGB), NOT a 365-day count. See
                    # reference/tax-law/estg-23-private-veraeusserung.md.
                    if within_speculation_period is None:
                        raise ProcessingError(
                            f"Cannot decide §23 taxability for asset {self.asset_internal_id}, "
                            f"Event {cover_event.event_id}: acquisition date "
                            f"'{current_short_lot.opening_date}' / realization date '{cover_event.event_date}' "
                            f"do not yield a usable date pair. An undecidable §23 case is "
                            f"unreported income, not an exempt one."
                        )
                    if within_speculation_period:
                        is_taxable_under_section_23_flag = True # Renamed
                        tax_cat = TaxReportingCategory.SECTION_23_ESTG_TAXABLE_GAIN if gross_gain_loss >= Decimal(0) else TaxReportingCategory.SECTION_23_ESTG_TAXABLE_LOSS
                    else: 
                        is_taxable_under_section_23_flag = False # Renamed
                        tax_cat = TaxReportingCategory.SECTION_23_ESTG_EXEMPT_HOLDING_PERIOD_MET
                
                rgl = RealizedGainLoss(
                    originating_event_id=cover_event.event_id, asset_internal_id=self.asset_internal_id,
                    asset_category_at_realization=self.asset_category, 
                    acquisition_date=current_short_lot.opening_date, 
                    realization_date=cover_event.event_date, 
                    realization_type=realization_type_for_rgl,
                    quantity_realized=quantity_covered_from_this_lot, 
                    unit_cost_basis_eur=cost_eur_per_unit_for_cover_event, # Renamed kwarg
                    unit_realization_value_eur=current_short_lot.unit_sale_proceeds_eur, # Renamed kwarg
                    total_cost_basis_eur=cost_basis_for_portion, # Renamed kwarg
                    total_realization_value_eur=realization_value_for_portion,
                    gross_gain_loss_eur=gross_gain_loss, holding_period_days=holding_period_days,
                    is_within_speculation_period=bool(within_speculation_period),
                    is_taxable_under_section_23=is_taxable_under_section_23_flag, # Renamed kwarg
                    tax_reporting_category=tax_cat, 
                    is_stillhalter_income=is_stillhalter_income_flag, # Renamed kwarg
                    fund_type_at_sale=rgl_fund_type if self.asset_category == AssetCategory.INVESTMENT_FUND else None,
                    teilfreistellung_rate_applied=rgl_tf_rate if self.asset_category == AssetCategory.INVESTMENT_FUND else None
                )
                realized_gains_losses.append(rgl)

        for i in sorted(short_lots_to_remove_indices, reverse=True): del self.short_lots[i]

        small_tolerance_qty = Decimal('1e-10')
        if quantity_remaining_to_realize.copy_abs() > small_tolerance_qty:
            msg = (f"Insufficient short lots for cover event {cover_event.ibkr_transaction_id or cover_event.event_id} "
                   f"for asset {self.asset_internal_id}. Required to cover: {quantity_to_realize}, "
                   f"Total available in short lots before this cover: {current_available_qty_in_short_lots}, " 
                   f"Remaining to cover after processing lots: {quantity_remaining_to_realize}.")
            if is_historical_simulation:
                logger.warning(f"Historical Simulation: {msg}")
                raise UserWarning(msg) 
            else:
                raise ValueError(msg)
        return realized_gains_losses


    def adjust_lots_for_split(self, event: CorpActionSplitForward):
        split_ratio = event.new_shares_per_old_share
        if split_ratio <= Decimal(0):
            logger.warning(f"Split event {event.event_id} for asset {self.asset_internal_id} has invalid ratio {split_ratio}. No adjustment made.")
            return

        logger.info(f"Applying split ratio {split_ratio} to lots for asset {self.asset_internal_id} (Category: {self.asset_category.name}) from event {event.event_id}")

        for lot in self.lots:
            original_quantity = lot.quantity
            original_total_cost = lot.total_cost_basis_eur
            new_quantity = self.ctx.multiply(original_quantity, split_ratio).quantize(global_config.PRECISION_QUANTITY, context=self.ctx)
            if new_quantity == Decimal(0) and original_quantity != Decimal(0) : 
                logger.warning(f"Lot (Src: {lot.source_transaction_id}) quantity became zero after split ratio {split_ratio}. Original Qty: {original_quantity}. Setting cost/unit to 0.")
                new_cost_per_unit = Decimal(0)
            elif new_quantity == Decimal(0) and original_quantity == Decimal(0) :
                 new_cost_per_unit = Decimal(0) 
            else:
                new_cost_per_unit = self.ctx.divide(original_total_cost, new_quantity)

            lot.quantity = new_quantity
            lot.unit_cost_basis_eur = new_cost_per_unit # Renamed
            logger.debug(f"  Adjusted Lot (Src: {lot.source_transaction_id}): New Qty={lot.quantity}, New Cost/Unit={lot.unit_cost_basis_eur}, Total Cost (Unchanged)={lot.total_cost_basis_eur}") # Renamed

        for short_lot in self.short_lots:
            original_quantity = short_lot.quantity_shorted
            original_total_proceeds = short_lot.total_sale_proceeds_eur
            new_quantity = self.ctx.multiply(original_quantity, split_ratio).quantize(global_config.PRECISION_QUANTITY, context=self.ctx)
            if new_quantity == Decimal(0) and original_quantity != Decimal(0):
                logger.warning(f"Short Lot (Src: {short_lot.source_transaction_id}) quantity became zero after split ratio {split_ratio}. Original Qty: {original_quantity}. Setting proceeds/unit to 0.")
                new_proceeds_per_unit = Decimal(0)
            elif new_quantity == Decimal(0) and original_quantity == Decimal(0) :
                 new_proceeds_per_unit = Decimal(0)
            else:
                new_proceeds_per_unit = self.ctx.divide(original_total_proceeds, new_quantity)

            short_lot.quantity_shorted = new_quantity
            short_lot.unit_sale_proceeds_eur = new_proceeds_per_unit # Renamed
            logger.debug(f"  Adjusted Short Lot (Src: {short_lot.source_transaction_id}): New Qty={short_lot.quantity_shorted}, New Proceeds/Unit={short_lot.unit_sale_proceeds_eur}, Total Proceeds (Unchanged)={short_lot.total_sale_proceeds_eur}") # Renamed

    def consume_all_lots_for_cash_merger(self, event: CorpActionMergerCash) -> List[RealizedGainLoss]:
        if event.cash_per_share_eur is None:
             logger.error(f"Cash merger event {event.event_id} for asset {self.asset_internal_id} missing cash_per_share_eur. Cannot process.")
             return []
        if not self.lots:
            logger.info(f"Cash merger event {event.event_id} for asset {self.asset_internal_id}, but no long lots to consume.")
            return []

        logger.info(f"Processing cash merger for asset {self.asset_internal_id} from event {event.event_id}, selling all lots at {event.cash_per_share_eur} EUR per {'contract' if self.asset_category == AssetCategory.OPTION else 'unit'}.")

        realized_gains_losses: List[RealizedGainLoss] = []
        realization_value_eur_per_unit_for_event = event.cash_per_share_eur

        for current_lot in list(self.lots):
            quantity_from_this_lot = current_lot.quantity

            # Every unit of the lot goes, so the whole accumulated Vorabpauschale
            # goes with it (§ 19 Abs. 1 Satz 3; a cash merger is a disposal).
            vorabpauschale_for_portion = self._take_vorabpauschale_from_lot(
                current_lot, quantity_from_this_lot, quantity_from_this_lot)

            cost_basis_for_portion = current_lot.total_cost_basis_eur
            realization_value_for_portion = self.ctx.multiply(quantity_from_this_lot, realization_value_eur_per_unit_for_event)
            gross_gain_loss = self.ctx.subtract(realization_value_for_portion, cost_basis_for_portion)

            acq_date_obj = parse_ibkr_date(current_lot.acquisition_date)
            real_date_obj = parse_ibkr_date(event.event_date)
            holding_period_days: Optional[int] = None
            within_speculation_period: Optional[bool] = None
            if acq_date_obj and real_date_obj and real_date_obj >= acq_date_obj :
                holding_period_days = (real_date_obj - acq_date_obj).days
                within_speculation_period = is_within_section23_speculation_period(acq_date_obj, real_date_obj)

            tax_cat: Optional[TaxReportingCategory] = None
            is_stillhalter_income_flag = False # Renamed
            is_taxable_under_section_23_flag = True # Renamed
            
            rgl_fund_type: Optional[InvestmentFundType] = None
            rgl_tf_rate: Optional[Decimal] = None


            if self.asset_category == AssetCategory.STOCK:
                tax_cat = TaxReportingCategory.ANLAGE_KAP_AKTIEN_GEWINN if gross_gain_loss >= Decimal(0) else TaxReportingCategory.ANLAGE_KAP_AKTIEN_VERLUST
            elif self.asset_category in [AssetCategory.BOND, AssetCategory.SONSTIGE_KAPITALFORDERUNG]:
                 # Both are 20 Abs. 2 Satz 1 Nr. 7 income and share Zeile 19 / Zeile 22.
                 tax_cat = TaxReportingCategory.ANLAGE_KAP_SONSTIGE_KAPITALERTRAEGE if gross_gain_loss >= Decimal(0) else TaxReportingCategory.ANLAGE_KAP_SONSTIGE_VERLUSTE
            elif self.asset_category in [AssetCategory.OPTION, AssetCategory.CFD, AssetCategory.FUTURE]:
                 tax_cat = TaxReportingCategory.ANLAGE_KAP_TERMIN_GEWINN if gross_gain_loss >= Decimal(0) else TaxReportingCategory.ANLAGE_KAP_TERMIN_VERLUST
            elif self.asset_category == AssetCategory.INVESTMENT_FUND:
                rgl_fund_type = self.fund_type
                if rgl_fund_type is None:
                    logger.error(f"CRITICAL: FifoLedger for Investment Fund {self.asset_internal_id} (Event: {event.event_id}) has self.fund_type as None. Defaulting to InvestmentFundType.NONE for RGL.")
                    rgl_fund_type = InvestmentFundType.NONE
                
                rgl_tf_rate = get_teilfreistellung_rate_for_fund_type(rgl_fund_type)

                if rgl_fund_type == InvestmentFundType.AKTIENFONDS:
                    tax_cat = TaxReportingCategory.ANLAGE_KAP_INV_AKTIENFONDS_GEWINN_GROSS
                elif rgl_fund_type == InvestmentFundType.MISCHFONDS:
                    tax_cat = TaxReportingCategory.ANLAGE_KAP_INV_MISCHFONDS_GEWINN_GROSS
                elif rgl_fund_type == InvestmentFundType.IMMOBILIENFONDS:
                    tax_cat = TaxReportingCategory.ANLAGE_KAP_INV_IMMOBILIENFONDS_GEWINN_GROSS
                elif rgl_fund_type == InvestmentFundType.AUSLANDS_IMMOBILIENFONDS:
                    tax_cat = TaxReportingCategory.ANLAGE_KAP_INV_AUSLANDS_IMMOBILIENFONDS_GEWINN_GROSS
                elif rgl_fund_type in [InvestmentFundType.SONSTIGE_FONDS, InvestmentFundType.NONE]:
                    tax_cat = TaxReportingCategory.ANLAGE_KAP_INV_SONSTIGE_FONDS_GEWINN_GROSS
                else: 
                    raise ProcessingError(f"Unhandled InvestmentFundType '{rgl_fund_type}' for asset {self.asset_internal_id}, Event {event.event_id}. Tax category mapping must be updated.")

            elif self.asset_category == AssetCategory.PRIVATE_SALE_ASSET: # Renamed
                # §23 Jahresfrist: anniversary rule (§108 Abs. 1 AO i.V.m. §§187 Abs. 1,
                # 188 Abs. 2-3 BGB), NOT a 365-day count. See
                # reference/tax-law/estg-23-private-veraeusserung.md.
                if within_speculation_period is None:
                    raise ProcessingError(
                        f"Cannot decide §23 taxability for asset {self.asset_internal_id}, "
                        f"Event {event.event_id}: acquisition date "
                        f"'{current_lot.acquisition_date}' / realization date '{event.event_date}' "
                        f"do not yield a usable date pair. An undecidable §23 case is "
                        f"unreported income, not an exempt one."
                    )
                if within_speculation_period:
                    is_taxable_under_section_23_flag = True # Renamed
                    tax_cat = TaxReportingCategory.SECTION_23_ESTG_TAXABLE_GAIN if gross_gain_loss >= Decimal(0) else TaxReportingCategory.SECTION_23_ESTG_TAXABLE_LOSS
                else: 
                    is_taxable_under_section_23_flag = False # Renamed
                    tax_cat = TaxReportingCategory.SECTION_23_ESTG_EXEMPT_HOLDING_PERIOD_MET
            
            rgl = RealizedGainLoss(
                originating_event_id=event.event_id, asset_internal_id=self.asset_internal_id,
                asset_category_at_realization=self.asset_category, acquisition_date=current_lot.acquisition_date,
                realization_date=event.event_date,
                realization_type=RealizationType.CASH_MERGER_PROCEEDS, # Renamed
                vorabpauschale_deduction_eur=(
                    vorabpauschale_for_portion
                    if self.asset_category == AssetCategory.INVESTMENT_FUND else None),
                quantity_realized=quantity_from_this_lot,
                unit_cost_basis_eur=current_lot.unit_cost_basis_eur, # Renamed kwarg
                unit_realization_value_eur=realization_value_eur_per_unit_for_event, # Renamed kwarg
                total_cost_basis_eur=cost_basis_for_portion, # Renamed kwarg
                total_realization_value_eur=realization_value_for_portion,
                gross_gain_loss_eur=gross_gain_loss, holding_period_days=holding_period_days,
                is_within_speculation_period=bool(within_speculation_period),
                is_taxable_under_section_23=is_taxable_under_section_23_flag, # Renamed kwarg
                tax_reporting_category=tax_cat, 
                is_stillhalter_income=is_stillhalter_income_flag, # Renamed kwarg
                fund_type_at_sale=rgl_fund_type if self.asset_category == AssetCategory.INVESTMENT_FUND else None,
                teilfreistellung_rate_applied=rgl_tf_rate if self.asset_category == AssetCategory.INVESTMENT_FUND else None
            )
            realized_gains_losses.append(rgl)
            logger.debug(f"  Generated RGL from cash merger for lot (Src: {current_lot.source_transaction_id}): Realized {quantity_from_this_lot}, Gross G/L={gross_gain_loss}")

        self.lots.clear()
        logger.info(f"Cleared all long lots for asset {self.asset_internal_id} due to cash merger.")
        return realized_gains_losses

    def add_lot_for_stock_dividend(self, event: CorpActionStockDividend):
        if event.quantity_new_shares_received <= Decimal(0):
            logger.info(f"Stock dividend event {event.event_id} for asset {self.asset_internal_id} has zero or negative new shares ({event.quantity_new_shares_received}). No lot added.")
            return
        if event.fmv_per_new_share_eur is None:
            logger.error(f"Stock dividend event {event.event_id} for asset {self.asset_internal_id} missing fmv_per_new_share_eur. Cannot create lot.")
            return

        if self.asset_category == AssetCategory.OPTION:
            logger.warning(f"Stock dividend event {event.event_id} received for OPTION asset {self.asset_internal_id}. This is unusual. Treating quantity as contracts with FMV per contract if applicable, but verify CA terms.")
        elif self.asset_category != AssetCategory.STOCK and self.asset_category != AssetCategory.INVESTMENT_FUND : 
            logger.warning(f"Stock dividend event {event.event_id} received for non-STOCK/non-FUND asset {self.asset_internal_id} (Category: {self.asset_category.name}). Adding lot based on shares/FMV, but verify asset classification and CA terms.")

        new_lot_quantity = event.quantity_new_shares_received.quantize(global_config.PRECISION_QUANTITY, context=self.ctx)
        new_lot_cost_per_unit = event.fmv_per_new_share_eur 
        new_lot_total_cost = self.ctx.multiply(new_lot_quantity, new_lot_cost_per_unit)

        source_id = event.ca_action_id_ibkr or event.ibkr_transaction_id or f"STOCKDIV_{event.event_id}"

        new_lot = FifoLot(
            acquisition_date=event.event_date, quantity=new_lot_quantity, 
            unit_cost_basis_eur=new_lot_cost_per_unit, # Renamed
            total_cost_basis_eur=new_lot_total_cost, source_transaction_id=source_id
        )
        self.lots.append(new_lot)
        self.lots.sort(key=lambda lot: (parse_ibkr_date(lot.acquisition_date) or datetime.min.date(), lot.source_transaction_id))
        if any((parse_ibkr_date(lot.acquisition_date) is None) for lot in self.lots):
             raise ValueError(f"Unparseable acquisition date found after adding stock dividend lot for asset {self.asset_internal_id}.")

        logger.info(f"Added new lot for stock dividend event {event.event_id} for asset {self.asset_internal_id}: Qty={new_lot.quantity}, Cost/Unit={new_lot.unit_cost_basis_eur} (FMV)") # Renamed


    def consume_long_option_get_cost(self, quantity_contracts_to_consume: Decimal) -> List[ConsumedLotDetail]:
        if self.asset_category != AssetCategory.OPTION:
            raise TypeError(f"consume_long_option_get_cost called on non-option asset {self.asset_internal_id} (Category: {self.asset_category.name})")

        qty_to_consume = quantity_contracts_to_consume.quantize(global_config.PRECISION_QUANTITY, context=self.ctx)
        if qty_to_consume <= Decimal(0):
            logger.warning(f"Quantity to consume for long option cost must be positive. Got {qty_to_consume}. Asset ID: {self.asset_internal_id}. Returning empty list.")
            return [] 

        consumed_lot_details: List[ConsumedLotDetail] = []
        quantity_remaining_to_consume = qty_to_consume
        lots_to_remove_indices: List[int] = []

        logger.debug(f"Attempting to consume {qty_to_consume} long option contracts for asset {self.asset_internal_id}...")

        for i, current_lot in enumerate(self.lots):
            if quantity_remaining_to_consume <= Decimal(0): break
            qty_available_in_lot = current_lot.quantity

            qty_consumed_from_this_lot: Decimal
            if qty_available_in_lot <= quantity_remaining_to_consume:
                qty_consumed_from_this_lot = qty_available_in_lot
                lots_to_remove_indices.append(i)
                logger.debug(f"  Fully consuming long option lot (Src: {current_lot.source_transaction_id}, Acq: {current_lot.acquisition_date}) Qty Contracts: {qty_consumed_from_this_lot}")
            else:
                qty_consumed_from_this_lot = quantity_remaining_to_consume
                current_lot.quantity = self.ctx.subtract(current_lot.quantity, qty_consumed_from_this_lot)
                current_lot.total_cost_basis_eur = self.ctx.multiply(current_lot.quantity, current_lot.unit_cost_basis_eur) # Renamed
                logger.debug(f"  Partially consuming long option lot (Src: {current_lot.source_transaction_id}, Acq: {current_lot.acquisition_date}) Qty Contracts: {qty_consumed_from_this_lot}. Remaining Qty Contracts: {current_lot.quantity}")

            consumed_lot_details.append(ConsumedLotDetail(
                consumed_quantity=qty_consumed_from_this_lot,
                value_per_unit_eur=current_lot.unit_cost_basis_eur, # Renamed
                original_lot_date=current_lot.acquisition_date,
                original_lot_source_tx_id=current_lot.source_transaction_id
            ))
            quantity_remaining_to_consume = self.ctx.subtract(quantity_remaining_to_consume, qty_consumed_from_this_lot)

        for i in sorted(lots_to_remove_indices, reverse=True):
            logger.debug(f"  Removing fully consumed long option lot index {i} (Src: {self.lots[i].source_transaction_id})")
            del self.lots[i]

        small_tolerance_qty = Decimal('1e-10') 
        if quantity_remaining_to_consume.copy_abs() > small_tolerance_qty: 
            current_total_qty_in_lots = sum(l.quantity for l in self.lots) 
            available_before_this_op = current_total_qty_in_lots + (qty_to_consume - quantity_remaining_to_consume)
            raise ValueError(f"Insufficient long option contracts for asset {self.asset_internal_id}. "
                             f"Required to consume: {qty_to_consume}, "
                             f"Total available before this consumption: {available_before_this_op}, "
                             f"Remaining to consume: {quantity_remaining_to_consume}.")

        logger.debug(f"Successfully consumed {qty_to_consume - quantity_remaining_to_consume} long option contracts. Details: {consumed_lot_details}")
        return consumed_lot_details


    def consume_short_option_get_proceeds(self, quantity_contracts_to_consume: Decimal) -> List[ConsumedLotDetail]:
        if self.asset_category != AssetCategory.OPTION:
             raise TypeError(f"consume_short_option_get_proceeds called on non-option asset {self.asset_internal_id} (Category: {self.asset_category.name})")

        qty_to_consume = quantity_contracts_to_consume.quantize(global_config.PRECISION_QUANTITY, context=self.ctx)
        if qty_to_consume <= Decimal(0):
            logger.warning(f"Quantity to consume for short option proceeds must be positive. Got {qty_to_consume}. Asset ID: {self.asset_internal_id}. Returning empty list.")
            return []

        consumed_lot_details: List[ConsumedLotDetail] = []
        quantity_remaining_to_consume = qty_to_consume
        short_lots_to_remove_indices: List[int] = []

        logger.debug(f"Attempting to consume {qty_to_consume} short option contracts for asset {self.asset_internal_id}...")

        for i, current_short_lot in enumerate(self.short_lots):
            if quantity_remaining_to_consume <= Decimal(0): break
            qty_available_in_lot = current_short_lot.quantity_shorted

            qty_consumed_from_this_lot: Decimal
            if qty_available_in_lot <= quantity_remaining_to_consume:
                qty_consumed_from_this_lot = qty_available_in_lot
                short_lots_to_remove_indices.append(i)
                logger.debug(f"  Fully consuming short option lot (Src: {current_short_lot.source_transaction_id}, Open: {current_short_lot.opening_date}) Qty Contracts: {qty_consumed_from_this_lot}")
            else:
                qty_consumed_from_this_lot = quantity_remaining_to_consume
                current_short_lot.quantity_shorted = self.ctx.subtract(current_short_lot.quantity_shorted, qty_consumed_from_this_lot)
                current_short_lot.total_sale_proceeds_eur = self.ctx.multiply(current_short_lot.quantity_shorted, current_short_lot.unit_sale_proceeds_eur) # Renamed
                logger.debug(f"  Partially consuming short option lot (Src: {current_short_lot.source_transaction_id}, Open: {current_short_lot.opening_date}) Qty Contracts: {qty_consumed_from_this_lot}. Remaining Qty Contracts: {current_short_lot.quantity_shorted}")

            consumed_lot_details.append(ConsumedLotDetail(
                consumed_quantity=qty_consumed_from_this_lot,
                value_per_unit_eur=current_short_lot.unit_sale_proceeds_eur, # Renamed
                original_lot_date=current_short_lot.opening_date,
                original_lot_source_tx_id=current_short_lot.source_transaction_id
            ))
            quantity_remaining_to_consume = self.ctx.subtract(quantity_remaining_to_consume, qty_consumed_from_this_lot)

        for i in sorted(short_lots_to_remove_indices, reverse=True):
            logger.debug(f"  Removing fully consumed short option lot index {i} (Src: {self.short_lots[i].source_transaction_id})")
            del self.short_lots[i]

        small_tolerance_qty = Decimal('1e-10')
        if quantity_remaining_to_consume.copy_abs() > small_tolerance_qty: 
            current_total_qty_in_lots = sum(sl.quantity_shorted for sl in self.short_lots)
            available_before_this_op = current_total_qty_in_lots + (qty_to_consume - quantity_remaining_to_consume)
            raise ValueError(f"Insufficient short option contracts for asset {self.asset_internal_id}. "
                             f"Required to consume: {qty_to_consume}, "
                             f"Total available before this consumption: {available_before_this_op}, " 
                             f"Remaining to consume: {quantity_remaining_to_consume}.") 

        logger.debug(f"Successfully consumed {qty_to_consume - quantity_remaining_to_consume} short option contracts. Details: {consumed_lot_details}")
        return consumed_lot_details


    def get_current_position_quantity(self) -> Decimal:
        current_long_qty = sum(lot.quantity for lot in self.lots) if self.lots else Decimal(0)
        current_short_qty_abs = sum(short_lot.quantity_shorted for short_lot in self.short_lots) if self.short_lots else Decimal(0)

        net_quantity = self.ctx.subtract(current_long_qty, current_short_qty_abs)
        return net_quantity.quantize(global_config.PRECISION_QUANTITY, context=self.ctx)

    def reduce_cost_basis_for_capital_repayment(self, repayment_amount_eur: Decimal) -> Decimal:
        """
        Reduces cost basis of FIFO lots for tax-free capital repayments.
        Returns excess amount that becomes taxable income.
        """
        if repayment_amount_eur <= Decimal('0') or not self.lots:
            return repayment_amount_eur
            
        remaining_repayment = repayment_amount_eur
        
        for lot in self.lots:
            if remaining_repayment <= Decimal('0'):
                break
                
            reduction = min(remaining_repayment, lot.total_cost_basis_eur)
            lot.total_cost_basis_eur = self.ctx.subtract(lot.total_cost_basis_eur, reduction)
            lot.unit_cost_basis_eur = self.ctx.divide(lot.total_cost_basis_eur, lot.quantity) if lot.quantity > Decimal('0') else Decimal('0')
            remaining_repayment = self.ctx.subtract(remaining_repayment, reduction)
        
        return remaining_repayment  # Excess that becomes taxable income
