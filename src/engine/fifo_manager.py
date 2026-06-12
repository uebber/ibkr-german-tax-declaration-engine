import logging
from dataclasses import dataclass
from decimal import Decimal, Context, getcontext as get_global_context
from typing import List, Optional, Tuple, Dict
import uuid
from datetime import date as date_obj, datetime

from src.domain.assets import Asset, Option 
from src.domain.events import FinancialEvent, TradeEvent, CorpActionSplitForward, CorpActionMergerCash, CorpActionStockDividend, CorpActionMergerStock
from src.domain.results import RealizedGainLoss
from src.domain.enums import AssetCategory, FinancialEventType, TaxReportingCategory, RealizationType, InvestmentFundType
from src.domain.exceptions import DataIntegrityError, ProcessingError
from src.utils.currency_converter import CurrencyConverter
from src.utils.exchange_rate_provider import ECBExchangeRateProvider
from src.utils.type_utils import parse_ibkr_date, safe_decimal
from src.utils.tax_utils import get_teilfreistellung_rate_for_fund_type
from src.tax_law.holding_period import is_within_section23_speculation_period
from src.processing.vp_disposal_deduction import vp_deduction_for_lot
import src.config as global_config

logger = logging.getLogger(__name__)

@dataclass
class FifoLot:
    acquisition_date: str  # YYYY-MM-DD
    quantity: Decimal # Represents shares/units OR contracts for options
    unit_cost_basis_eur: Decimal # Renamed from cost_basis_eur_per_unit
    total_cost_basis_eur: Decimal # Stored with high precision
    source_transaction_id: str # IBKR Transaction ID (or fallback string like "SOY_FALLBACK")

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

        # §19 Abs. 1 S. 3 InvStG VP-deduction context for fund disposals, populated by the
        # engine after ledger setup. Empty -> no deduction (default; preserves prior behaviour).
        self.vp_declared_by_year: Dict[int, Decimal] = {}
        self.vp_qty_eoy_by_year: Dict[int, Decimal] = {}


    def initialize_lots_from_soy(self,
                                 asset: Asset,
                                 all_historical_events_for_asset: List[FinancialEvent],
                                 tax_year: int):
        """Convenience method: simulate + reconcile in one call (used when no mergers)."""
        self.simulate_historical_events(asset, all_historical_events_for_asset, tax_year)
        self.reconcile_with_soy_position(asset, tax_year)

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
        reconstructed) set the flag consumed by reconcile_with_soy_position."""
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
        except UserWarning as uw:
            logger.warning(f"Historical simulation warning for asset {asset.internal_asset_id} processing event {hist_event.event_id}: {uw}")
            self._historical_simulation_inconsistent = True

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

    def reconcile_with_soy_position(self, asset: Asset, tax_year: int):
        """Pass 3: Compare reconstructed lots against SoY position and apply fallback if needed."""
        historical_simulation_inconsistent = getattr(self, '_historical_simulation_inconsistent', False)

        reconstructed_long_lots_snapshot = list(self.lots)
        reconstructed_short_lots_snapshot = list(self.short_lots)
        self.lots.clear()
        self.short_lots.clear()

        reconstructed_total_long_qty = sum(lot.quantity for lot in reconstructed_long_lots_snapshot)
        reconstructed_total_short_qty_abs = sum(lot.quantity_shorted for lot in reconstructed_short_lots_snapshot)
        reconstructed_net_qty = self.ctx.subtract(reconstructed_total_long_qty, reconstructed_total_short_qty_abs)

        reported_soy_qty = asset.soy_quantity
        if reported_soy_qty is None:
            logger.warning(f"Asset {asset.get_classification_key()}: SOY quantity from positions report is None. Assuming 0 for ledger initialization.")
            reported_soy_qty = Decimal(0)
        else:
            reported_soy_qty = reported_soy_qty.quantize(global_config.PRECISION_QUANTITY, context=self.ctx)

        logger.info(f"Asset {asset.get_classification_key()}: Reconstructed SOY Qty: {reconstructed_net_qty}. Reported SOY Qty: {reported_soy_qty}. Historical Sim Inconsistent: {historical_simulation_inconsistent}")

        if reported_soy_qty == Decimal(0):
            logger.info(f"Asset {asset.get_classification_key()}: Reported SOY quantity is 0. Initializing with no lots.")
            return

        use_fallback = historical_simulation_inconsistent

        if not use_fallback:
            if reported_soy_qty > Decimal(0):
                if reconstructed_total_long_qty >= reported_soy_qty and reconstructed_total_short_qty_abs == Decimal(0):
                    logger.info(f"Asset {asset.get_classification_key()}: Using reconstructed FIFO long lots and costs.")
                    qty_to_assign = reported_soy_qty
                    for lot in reconstructed_long_lots_snapshot:
                        if qty_to_assign <= Decimal(0): break
                        qty_from_this_lot = min(lot.quantity, qty_to_assign)
                        final_lot = FifoLot(
                            acquisition_date=lot.acquisition_date, quantity=qty_from_this_lot,
                            unit_cost_basis_eur=lot.unit_cost_basis_eur,
                            total_cost_basis_eur=self.ctx.multiply(qty_from_this_lot, lot.unit_cost_basis_eur),
                            source_transaction_id=lot.source_transaction_id
                        )
                        self.lots.append(final_lot)
                        qty_to_assign -= qty_from_this_lot
                    if qty_to_assign.copy_abs() > Decimal('1e-8'):
                         logger.error(f"Asset {asset.get_classification_key()}: Mismatch after assigning sufficient long lots. Rem: {qty_to_assign}")
                         use_fallback = True
                else:
                    use_fallback = True

            elif reported_soy_qty < Decimal(0):
                reported_soy_qty_abs = reported_soy_qty.copy_abs()
                if reconstructed_total_short_qty_abs >= reported_soy_qty_abs and reconstructed_total_long_qty == Decimal(0):
                    logger.info(f"Asset {asset.get_classification_key()}: Using reconstructed FIFO short lots and proceeds.")
                    qty_to_assign = reported_soy_qty_abs
                    for lot in reconstructed_short_lots_snapshot:
                        if qty_to_assign <= Decimal(0): break
                        qty_from_this_lot = min(lot.quantity_shorted, qty_to_assign)
                        final_short_lot = ShortFifoLot(
                            opening_date=lot.opening_date, quantity_shorted=qty_from_this_lot,
                            unit_sale_proceeds_eur=lot.unit_sale_proceeds_eur,
                            total_sale_proceeds_eur=self.ctx.multiply(qty_from_this_lot, lot.unit_sale_proceeds_eur),
                            source_transaction_id=lot.source_transaction_id
                        )
                        self.short_lots.append(final_short_lot)
                        qty_to_assign -= qty_from_this_lot
                    if qty_to_assign.copy_abs() > Decimal('1e-8'):
                         logger.error(f"Asset {asset.get_classification_key()}: Mismatch after assigning sufficient short lots. Rem: {qty_to_assign}")
                         use_fallback = True
                else:
                    use_fallback = True
            else:
                 use_fallback = True

        # Surface ANY divergence between the reconstruction and the reported SoY snapshot. The
        # fallback path below already warns for under-reconstruction / inconsistency; this covers the
        # remaining case — OVER-reconstruction, where the replay built more than the snapshot reports
        # (a disposal is evidently missing from the input trades). We keep the more-accurate historical
        # lots (trimmed to the reported quantity, figures unchanged) but no longer do so silently.
        if not use_fallback and abs(reconstructed_net_qty - reported_soy_qty) > Decimal('1e-8'):
            soy_qty_diff = self.ctx.subtract(reconstructed_net_qty, reported_soy_qty)
            logger.warning(
                f"Asset {asset.get_classification_key()}: Historical FIFO reconstruction (net "
                f"{reconstructed_net_qty}) does not match reported SOY Qty ({reported_soy_qty}) "
                f"(reconstructed - reported = {soy_qty_diff}); a disposal is likely missing from the "
                f"input trades. Keeping the reconstructed FIFO lots trimmed to the reported quantity."
            )

        if use_fallback:
            self.lots.clear()
            self.short_lots.clear()
            logger.warning(f"Asset {asset.get_classification_key()}: Historical FIFO reconstruction "
                           f"(Long: {reconstructed_total_long_qty}, Short: {reconstructed_total_short_qty_abs}, Inconsistent: {historical_simulation_inconsistent}) "
                           f"is insufficient or mismatched for reported SOY Qty ({reported_soy_qty}). Using SOY fallback cost/proceeds for entire quantity.")
            if reported_soy_qty > Decimal(0):
                self._create_fallback_long_lot(asset, reported_soy_qty, tax_year)
            elif reported_soy_qty < Decimal(0):
                self._create_fallback_short_lot(asset, reported_soy_qty.copy_abs(), tax_year)

        if self.lots:
            self.lots.sort(key=lambda lot: (parse_ibkr_date(lot.acquisition_date) or datetime.min.date(), lot.source_transaction_id))
            if any((parse_ibkr_date(lot.acquisition_date) is None) for lot in self.lots):
                 raise ValueError(f"Unparseable acquisition date found in final SOY lots for asset {self.asset_internal_id}.")
        if self.short_lots:
            self.short_lots.sort(key=lambda lot: (parse_ibkr_date(lot.opening_date) or datetime.min.date(), lot.source_transaction_id))
            if any((parse_ibkr_date(lot.opening_date) is None) for lot in self.short_lots):
                 raise ValueError(f"Unparseable opening date found in final SOY short lots for asset {self.asset_internal_id}.")

    def _create_fallback_long_lot(self, asset: Asset, quantity: Decimal, tax_year: int):
        if quantity <= Decimal(0): return
        total_cost_basis_eur: Decimal
        if asset.soy_cost_basis_amount is None or asset.soy_cost_basis_currency is None: # Renamed
            logger.error(f"Asset {asset.get_classification_key()} fallback SOY: Missing SOY cost basis. Creating zero-cost lot for Qty {quantity}.")
            total_cost_basis_eur = self.ctx.create_decimal(Decimal(0))
        else:
            total_cost_basis_soy_curr = self.ctx.create_decimal(asset.soy_cost_basis_amount) # Renamed
            cost_basis_currency = asset.soy_cost_basis_currency # Renamed
            if cost_basis_currency.upper() == "EUR":
                total_cost_basis_eur = total_cost_basis_soy_curr
            else:
                conversion_date_obj = date_obj(tax_year, 1, 1) 
                converted_eur = self.currency_converter.convert_to_eur(
                    original_amount=total_cost_basis_soy_curr, original_currency=cost_basis_currency, date_of_conversion=conversion_date_obj
                )
                if converted_eur is None:
                    logger.error(f"Asset {asset.get_classification_key()} fallback SOY: Failed to convert SOY cost basis. Creating zero-cost lot for Qty {quantity}.")
                    total_cost_basis_eur = self.ctx.create_decimal(Decimal(0))
                else:
                    total_cost_basis_eur = self.ctx.create_decimal(converted_eur)
            if total_cost_basis_eur < Decimal(0):
                logger.warning(f"Asset {asset.get_classification_key()} fallback SOY: Reported total cost basis {total_cost_basis_eur} EUR is negative. Using 0 for Qty {quantity}.")
                total_cost_basis_eur = self.ctx.create_decimal(Decimal(0))
        cost_per_unit = self.ctx.divide(total_cost_basis_eur, quantity) if quantity != Decimal(0) else Decimal(0)
        acquisition_date_str = f"{tax_year-1}-12-31" 
        fallback_lot = FifoLot(
            acquisition_date=acquisition_date_str, quantity=quantity,
            unit_cost_basis_eur=cost_per_unit, total_cost_basis_eur=total_cost_basis_eur, # Renamed
            source_transaction_id=self.soy_fallback_lot_source_tx_id
        )
        self.lots.append(fallback_lot)
        logger.info(
            f"Asset {asset.get_classification_key()}: Created fallback SOY long lot: "
            f"Qty: {fallback_lot.quantity}, Cost/Unit EUR: {fallback_lot.unit_cost_basis_eur}, Acq. Date: {fallback_lot.acquisition_date}" # Renamed
        )

    def _create_fallback_short_lot(self, asset: Asset, quantity_abs: Decimal, tax_year: int):
        if quantity_abs <= Decimal(0): return
        total_proceeds_eur: Decimal
        if asset.soy_cost_basis_amount is None or asset.soy_cost_basis_currency is None: # Renamed (using cost basis field for proceeds as per IBKR convention for short SOY)
            logger.error(f"Asset {asset.get_classification_key()} fallback SOY SHORT: Missing SOY proceeds. Creating zero-proceeds lot for Qty {quantity_abs}.")
            total_proceeds_eur = self.ctx.create_decimal(Decimal(0))
        else:
            total_proceeds_soy_curr = self.ctx.create_decimal(asset.soy_cost_basis_amount).copy_abs() # Renamed
            proceeds_currency = asset.soy_cost_basis_currency # Renamed
            if proceeds_currency.upper() == "EUR":
                total_proceeds_eur = total_proceeds_soy_curr
            else:
                conversion_date_obj = date_obj(tax_year, 1, 1) 
                converted_eur = self.currency_converter.convert_to_eur(
                    original_amount=total_proceeds_soy_curr, original_currency=proceeds_currency, date_of_conversion=conversion_date_obj
                )
                if converted_eur is None:
                    logger.error(f"Asset {asset.get_classification_key()} fallback SOY SHORT: Failed to convert SOY proceeds. Creating zero-proceeds lot for Qty {quantity_abs}.")
                    total_proceeds_eur = self.ctx.create_decimal(Decimal(0))
                else:
                    total_proceeds_eur = self.ctx.create_decimal(converted_eur)
        proceeds_per_unit = self.ctx.divide(total_proceeds_eur, quantity_abs) if quantity_abs != Decimal(0) else Decimal(0)
        opening_date_str = f"{tax_year-1}-12-31" 
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
            if current_lot.quantity <= quantity_remaining_to_realize:
                quantity_from_this_lot = current_lot.quantity
                lots_to_remove_indices.append(i)
            else:
                quantity_from_this_lot = quantity_remaining_to_realize
                current_lot.quantity = self.ctx.subtract(current_lot.quantity, quantity_from_this_lot)
                current_lot.total_cost_basis_eur = self.ctx.multiply(current_lot.quantity, current_lot.unit_cost_basis_eur) # Renamed

            quantity_remaining_to_realize = self.ctx.subtract(quantity_remaining_to_realize, quantity_from_this_lot)
            
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

                # §19 Abs. 1 S. 3-4 InvStG: reduce a fund disposal's gain by the gross
                # Vorabpauschalen declared during the holding period of the sold units
                # (FIFO, per lot). The reduced value flows to the RGL as gross_gain_loss
                # (still vor Teilfreistellung); the deducted amount is kept for reporting.
                vp_deduction_for_lot_eur: Optional[Decimal] = None
                if self.asset_category == AssetCategory.INVESTMENT_FUND and self.vp_declared_by_year:
                    raw_vp_deduction = vp_deduction_for_lot(
                        acquisition_year=int(current_lot.acquisition_date[:4]),
                        sale_year=int(sale_event.event_date[:4]),
                        units_sold=quantity_from_this_lot,
                        declared_vp_by_year=self.vp_declared_by_year,
                        qty_eoy_by_year=self.vp_qty_eoy_by_year,
                    )
                    if raw_vp_deduction > Decimal(0):
                        vp_deduction_for_lot_eur = raw_vp_deduction
                        gross_gain_loss = self.ctx.subtract(gross_gain_loss, raw_vp_deduction)

                tax_cat: Optional[TaxReportingCategory] = None
                is_stillhalter_income_flag = False # Renamed from is_premium_gain
                is_taxable_under_section_23_flag = True # Renamed from is_taxable_under_rules_for_rgl
                
                rgl_fund_type: Optional[InvestmentFundType] = None
                rgl_tf_rate: Optional[Decimal] = None

                if self.asset_category == AssetCategory.STOCK:
                    tax_cat = TaxReportingCategory.ANLAGE_KAP_AKTIEN_GEWINN if gross_gain_loss >= Decimal(0) else TaxReportingCategory.ANLAGE_KAP_AKTIEN_VERLUST
                elif self.asset_category == AssetCategory.BOND:
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
                    if within_speculation_period:  # §23 Jahresfrist: anniversary rule (§§187 f. BGB), NOT a 365-day count; None (unparseable dates) falls through to exempt as before
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
                    is_taxable_under_section_23=is_taxable_under_section_23_flag, # Renamed kwarg
                    tax_reporting_category=tax_cat,
                    is_stillhalter_income=is_stillhalter_income_flag, # Renamed kwarg
                    fund_type_at_sale=rgl_fund_type if self.asset_category == AssetCategory.INVESTMENT_FUND else None,
                    teilfreistellung_rate_applied=rgl_tf_rate if self.asset_category == AssetCategory.INVESTMENT_FUND else None,
                    vp_deduction_eur=vp_deduction_for_lot_eur
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
                elif self.asset_category == AssetCategory.BOND:
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
                    if within_speculation_period:  # §23 Jahresfrist: anniversary rule (§§187 f. BGB), NOT a 365-day count; None (unparseable dates) falls through to exempt as before
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
            elif self.asset_category == AssetCategory.BOND:
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
                if within_speculation_period:  # §23 Jahresfrist: anniversary rule (§§187 f. BGB), NOT a 365-day count; None (unparseable dates) falls through to exempt as before
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
                quantity_realized=quantity_from_this_lot,
                unit_cost_basis_eur=current_lot.unit_cost_basis_eur, # Renamed kwarg
                unit_realization_value_eur=realization_value_eur_per_unit_for_event, # Renamed kwarg
                total_cost_basis_eur=cost_basis_for_portion, # Renamed kwarg
                total_realization_value_eur=realization_value_for_portion,
                gross_gain_loss_eur=gross_gain_loss, holding_period_days=holding_period_days,
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
