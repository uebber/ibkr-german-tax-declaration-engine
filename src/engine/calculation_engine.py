# src/engine/calculation_engine.py
import logging
from typing import List, Tuple, Dict, DefaultDict, Optional, Any
import uuid
from decimal import Decimal, getcontext, Context
from collections import defaultdict
from datetime import datetime, date

from src.engine.ledger_views import aggregate_lots, ledgers_for_asset
from src.utils.account_utils import account_key, DEFAULT_ACCOUNT
from src.processing.data_gaps import DataGapCollector, GapSeverity
from src.domain.events import (
    FinancialEvent, TradeEvent, CorpActionSplitForward, CorpActionMergerCash,
    CorpActionStockDividend, CorpActionMergerStock, CorporateActionEvent,
    CorpActionExpireDividendRights, OptionExerciseEvent, OptionAssignmentEvent,
    OptionExpirationWorthlessEvent, OptionCashSettlementEvent,
    OptionLifecycleEvent, CashFlowEvent, FeeEvent,
    WithholdingTaxEvent, CurrencyConversionEvent, InternalTransferEvent
)
from src.domain.assets import Asset, Stock, Bond, AssetCategory, Option, InvestmentFund, CashBalance
from src.identification.asset_resolver import AssetResolver
from src.domain.results import RealizedGainLoss, VorabpauschaleData
from src.domain.enums import FinancialEventType, InvestmentFundType 
from src.utils.sorting_utils import get_event_sort_key
from src.domain.exceptions import ProcessingError
from src.utils.type_utils import parse_ibkr_date
from src.processing.vp_disposal_deduction import year_end_quantities

from .fifo_manager import FifoLedger
from src.utils.currency_converter import CurrencyConverter
from src.utils.exchange_rate_provider import ECBExchangeRateProvider
import src.config as config

# Import the event processors
from .event_processors.base_processor import EventProcessor
from .event_processors.trade_processor import TradeProcessor
from .event_processors.corporate_action_processor import (
    SplitProcessor, MergerCashProcessor, StockDividendProcessor, MergerStockProcessor,
    GenericCorporateActionProcessor, ExpireDividendRightsProcessor
)
from .event_processors.option_processor import (
    OptionExerciseProcessor, OptionAssignmentProcessor, OptionExpirationWorthlessProcessor,
    OptionCashSettlementProcessor
)
from .event_processors.currency_conversion_processor import CurrencyConversionProcessor


logger = logging.getLogger(__name__)



class _AccountAssetView:
    """
    Per-(account, asset) read view over an Asset, overriding only the SoY/EoY position fields
    with this account's recorded values (asset_resolver.positions_by_account / cash_by_account).
    Lets FifoLedger.reconcile_with_soy_position (which reads asset.soy_*/eoy_*) operate per
    Depot without copying or mutating the shared Asset.
    """
    _OVERRIDES = (
        "soy_quantity", "soy_cost_basis_amount", "soy_cost_basis_currency",
        "soy_market_price", "soy_position_value", "soy_mark_price_currency",
        "eoy_quantity", "eoy_market_price", "eoy_position_value", "eoy_mark_price_currency",
    )

    def __init__(self, asset, pos: Optional[Dict[str, Any]]):
        object.__setattr__(self, "_asset", asset)
        pos = pos or {}
        ccy = pos.get("soy_currency") or asset.currency
        eoy_ccy = pos.get("eoy_currency") or asset.currency
        vals = {
            # No per-account position row for this (account, asset) means the account simply did
            # not hold it at SoY -> 0 (the account-agnostic baseline set the aggregate SoY to 0 the
            # same way). Passing 0 rather than None avoids a spurious "SOY quantity is None" warning
            # for every account that doesn't hold a given security; behaviour is identical.
            "soy_quantity": pos.get("soy_quantity") if pos.get("soy_quantity") is not None else Decimal("0"),
            "soy_cost_basis_amount": pos.get("soy_cost_basis_amount"),
            "soy_cost_basis_currency": ccy,
            "soy_market_price": pos.get("soy_market_price"),
            "soy_position_value": pos.get("soy_position_value"),
            "soy_mark_price_currency": ccy,
            "eoy_quantity": pos.get("eoy_quantity"),
            "eoy_market_price": pos.get("eoy_market_price"),
            "eoy_position_value": pos.get("eoy_position_value"),
            "eoy_mark_price_currency": eoy_ccy,
        }
        object.__setattr__(self, "_overrides", vals)

    @property
    def __class__(self):
        # Make isinstance(view, Stock/InvestmentFund/CashBalance/...) reflect the real asset.
        return type(object.__getattribute__(self, "_asset"))

    def __getattr__(self, name):
        ov = object.__getattribute__(self, "_overrides")
        if name in ov:
            return ov[name]
        return getattr(object.__getattribute__(self, "_asset"), name)

    def __setattr__(self, name, value):
        if name in _AccountAssetView._OVERRIDES:
            object.__getattribute__(self, "_overrides")[name] = value
        else:
            setattr(object.__getattribute__(self, "_asset"), name, value)


def _initialize_currency_soy_ledger(ledger: FifoLedger, asset: CashBalance, tax_year: int,
                                     exchange_rate_provider: ECBExchangeRateProvider,
                                     ctx: Context) -> None:
    """
    Initialize currency FIFO ledger using SOY position with fallback cost basis.

    Supports both positive (long) and negative (short) SOY positions.

    Process:
    1. Get SOY quantity from CashBalance asset
    2. If positive: Create long lot with cost basis from ECB rate at SOY date
    3. If negative: Create short lot with proceeds from ECB rate at SOY date
    """
    from src.engine.fifo_manager import FifoLot, ShortFifoLot
    from datetime import date as date_obj

    reported_soy_qty = asset.soy_quantity
    if reported_soy_qty is None or reported_soy_qty == Decimal("0"):
        logger.debug(f"Currency {asset.currency}: SOY quantity is zero or None, no lots to create")
        return

    # Fallback date is last day of previous year
    fallback_date = date_obj(tax_year - 1, 12, 31)
    fallback_date_str = fallback_date.isoformat()

    # Get ECB rate at fallback date for cost basis calculation
    ecb_rate = exchange_rate_provider.get_rate(fallback_date, asset.currency)
    if ecb_rate is None or ecb_rate == Decimal("0"):
        raise ValueError(
            f"Currency {asset.currency}: No ECB rate available for SOY date {fallback_date_str}. "
            f"Cannot initialize currency FIFO ledger without a valid exchange rate. "
            f"Ensure ECB rate cache covers this date."
        )

    if reported_soy_qty > Decimal("0"):
        # Positive SOY = long position
        # Use provided cost basis if available, otherwise calculate from ECB rate
        if asset.soy_cost_basis_amount and asset.soy_cost_basis_amount > Decimal("0"):
            total_cost_basis_eur = asset.soy_cost_basis_amount
            unit_cost_basis_eur = ctx.divide(total_cost_basis_eur, reported_soy_qty)
            logger.debug(f"Currency {asset.currency}: Using provided SOY cost basis: {total_cost_basis_eur:.2f} EUR")
        else:
            # EUR value = foreign amount / rate
            total_cost_basis_eur = ctx.divide(reported_soy_qty, ecb_rate)
            unit_cost_basis_eur = ctx.divide(total_cost_basis_eur, reported_soy_qty)

        lot = FifoLot(
            acquisition_date=fallback_date_str,
            quantity=reported_soy_qty,
            unit_cost_basis_eur=unit_cost_basis_eur,
            total_cost_basis_eur=total_cost_basis_eur,
            source_transaction_id=f"SOY_CURRENCY_FALLBACK_{asset.currency}"
        )
        ledger.lots.append(lot)
        logger.info(f"Currency {asset.currency}: Created SOY LONG lot - Qty: {reported_soy_qty}, "
                   f"Cost Basis: {total_cost_basis_eur:.2f} EUR (rate: {ecb_rate})")

    else:
        # Negative SOY = short position
        soy_qty_abs = reported_soy_qty.copy_abs()
        # EUR proceeds = foreign amount / rate
        total_proceeds_eur = ctx.divide(soy_qty_abs, ecb_rate)
        unit_proceeds_eur = ctx.divide(total_proceeds_eur, soy_qty_abs)

        short_lot = ShortFifoLot(
            opening_date=fallback_date_str,
            quantity_shorted=soy_qty_abs,
            unit_sale_proceeds_eur=unit_proceeds_eur,
            total_sale_proceeds_eur=total_proceeds_eur,
            source_transaction_id=f"SOY_CURRENCY_FALLBACK_SHORT_{asset.currency}"
        )
        ledger.short_lots.append(short_lot)
        logger.info(f"Currency {asset.currency}: Created SOY SHORT lot - Qty: {soy_qty_abs}, "
                   f"Proceeds: {total_proceeds_eur:.2f} EUR (rate: {ecb_rate})")


def _format_asset_info(asset_obj) -> str:
    """Helper to format asset information for logging."""
    if not asset_obj:
        return "Unknown Asset"
    desc = asset_obj.description or asset_obj.get_classification_key()
    symbol = asset_obj.ibkr_symbol or "N/A"
    return f"'{desc}' (Symbol: {symbol})"

def _replay_historical_merger(merger_event, fifo_ledgers, asset_resolver) -> None:
    """Apply ONE historical stock-for-stock merger (§20 Abs. 4a EStG,
    tax-neutral lot transfer) — the per-event unit the unified replayer
    streams in the MERGERS phase."""
    acct_m = account_key(merger_event.account_id)
    source_ledger = fifo_ledgers.get((acct_m, merger_event.asset_internal_id))
    target_ledger = fifo_ledgers.get((acct_m, merger_event.new_asset_internal_id))

    if source_ledger is None:
        logger.warning(f"Historical merger {merger_event.event_id}: No source ledger for {merger_event.asset_internal_id} acct {acct_m}. Skipping.")
        return
    if target_ledger is None:
        logger.error(f"Historical merger {merger_event.event_id}: No target ledger for {merger_event.new_asset_internal_id} acct {acct_m}. Cannot transfer lots.")
        raise ValueError(f"Target ledger missing for historical merger {merger_event.event_id}")

    source_long_lots = source_ledger.drain_all_long_lots()
    source_short_lots = source_ledger.drain_all_short_lots()
    if not source_long_lots and not source_short_lots:
        logger.debug(f"Historical merger {merger_event.event_id}: Source ledger {merger_event.asset_internal_id} has no lots. Skipping.")
        return

    try:
        target_ledger.receive_all_lots_from_merger(
            source_long_lots, source_short_lots,
            merger_event.new_shares_received_per_old, merger_event
        )
    except Exception as e:
        # Rollback source
        source_ledger.lots.extend(source_long_lots)
        source_ledger.lots.sort(key=lambda lot: (parse_ibkr_date(lot.acquisition_date) or datetime.min.date(), lot.source_transaction_id))
        source_ledger.short_lots.extend(source_short_lots)
        source_ledger.short_lots.sort(key=lambda lot: (parse_ibkr_date(lot.opening_date) or datetime.min.date(), lot.source_transaction_id))
        logger.error(f"Historical merger {merger_event.event_id}: Failed to transfer lots. Rolled back. Error: {e}")
        raise

    assert len(source_ledger.lots) == 0, f"Source ledger {merger_event.asset_internal_id} must have no long lots after historical merger"
    assert len(source_ledger.short_lots) == 0, f"Source ledger {merger_event.asset_internal_id} must have no short lots after historical merger"

    logger.info(f"Historical merger: Transferred {len(source_long_lots)} long + {len(source_short_lots)} "
                 f"short lots from {merger_event.asset_internal_id} to {merger_event.new_asset_internal_id} "
                 f"(ratio: {merger_event.new_shares_received_per_old})")


def _order_current_year_events_for_merger_deps(events: List[FinancialEvent]) -> List[FinancialEvent]:
    """Resolve a same-day ordering dependency between an internal transfer and a stock merger.

    A merger event carries the account it happens in. If a security is transferred A->B and then
    merges in B on the SAME day, the merger consumes the just-transferred lots, so the transfer MUST
    run before the merger. The default intra-day sort places corporate actions (mergers) before
    trades/transfers, which would run the merger against an empty target ledger. Because the merger's
    account unambiguously identifies where the merge happens, detect a transfer whose
    (target account, source asset) matches the merger's (account, source asset) on the same date and
    move it to immediately before that merger. Other cases (e.g. transferring the merger OUTPUT) are
    unaffected — the merger correctly precedes them.
    """
    if not (any(isinstance(e, CorpActionMergerStock) for e in events)
            and any(isinstance(e, InternalTransferEvent) for e in events)):
        return events
    ordered = list(events)
    for _ in range(len(ordered)):  # bounded passes; handles multiple dependencies
        moved = False
        for mi, m in enumerate(ordered):
            if not isinstance(m, CorpActionMergerStock):
                continue
            m_acct = account_key(m.account_id)
            for ti in range(mi + 1, len(ordered)):
                t = ordered[ti]
                if (isinstance(t, InternalTransferEvent)
                        and t.event_date == m.event_date
                        and t.asset_internal_id == m.asset_internal_id
                        and account_key(t.target_account_id) == m_acct):
                    ordered.insert(mi, ordered.pop(ti))  # move transfer to just before its merger
                    logger.info(f"Ordering: moved same-day internal transfer {t.event_id} before "
                                f"dependent merger {m.event_id} (transfer delivers the merged asset "
                                f"into account {m_acct}).")
                    moved = True
                    break
            if moved:
                break
        if not moved:
            break
    return ordered



def _apply_historical_option_event(option_event, ledger, asset_resolver,
                                   hist_pending_adjustments) -> None:
    """Replay ONE historical option lifecycle event: consume the option ledger's
    contract lots exactly like the current-year processors do, and for
    exercise/assignment register the premium adjustment for the linked stock
    trade (consumed by _adjust_historical_stock_trade). Emits NO RGLs — any
    gain/loss belonged to the event's own assessment year."""
    option_asset = asset_resolver.get_asset_by_id(option_event.asset_internal_id)
    qty = option_event.quantity_contracts
    try:
        if isinstance(option_event, OptionExerciseEvent):
            consumed = ledger.consume_long_option_get_cost(qty)
            premium = sum((ledger.ctx.multiply(d.consumed_quantity, d.value_per_unit_eur)
                           for d in consumed), ledger.ctx.create_decimal(0))
            if isinstance(option_asset, Option) and option_asset.underlying_asset_internal_id is not None:
                hist_pending_adjustments[option_event.event_id] = (
                    premium, option_event.asset_internal_id, option_asset.option_type)
        elif isinstance(option_event, OptionAssignmentEvent):
            consumed = ledger.consume_short_option_get_proceeds(qty)
            premium = sum((ledger.ctx.multiply(d.consumed_quantity, d.value_per_unit_eur)
                           for d in consumed), ledger.ctx.create_decimal(0))
            if isinstance(option_asset, Option) and option_asset.underlying_asset_internal_id is not None:
                hist_pending_adjustments[option_event.event_id] = (
                    premium, option_event.asset_internal_id, option_asset.option_type)
        elif isinstance(option_event, OptionExpirationWorthlessEvent):
            available_long = sum((l.quantity for l in ledger.lots), Decimal(0))
            if available_long >= qty:
                ledger.consume_long_option_get_cost(qty)
            else:
                ledger.consume_short_option_get_proceeds(qty)
    except (ValueError, UserWarning) as e:
        logger.warning(f"Historical option event {option_event.event_id} "
                       f"({option_event.event_type.name}) could not be fully replayed: {e}")
        ledger._historical_simulation_inconsistent = True


def _adjust_historical_stock_trade(trade_event, asset_resolver,
                                   hist_pending_adjustments) -> None:
    """Apply a pending option-premium adjustment to a historical stock trade
    BEFORE it is replayed into the ledger — the same mutation of
    net_proceeds_or_cost_basis_eur the TradeProcessor performs for
    current-year trades (PRD 2.4): long-call exercise premium increases the
    buy cost, short-put assignment premium reduces it (sell-side adjustments
    only affect that year's own proceeds and are applied for consistency)."""
    adjustment_data = hist_pending_adjustments.pop(trade_event.related_option_event_id, None)
    if adjustment_data is None:
        logger.warning(f"Historical stock trade {trade_event.event_id} is linked to option "
                       f"event {trade_event.related_option_event_id}, but no pending "
                       f"adjustment was produced by the replay; basis left unadjusted.")
        return
    premium_eur, _option_asset_id, option_type = adjustment_data
    if trade_event.net_proceeds_or_cost_basis_eur is None:
        logger.warning(f"Historical stock trade {trade_event.event_id}: no EUR value to adjust.")
        return
    if trade_event.event_type in (FinancialEventType.TRADE_BUY_LONG, FinancialEventType.TRADE_BUY_SHORT_COVER):
        delta = premium_eur if option_type == 'C' else -premium_eur
    else:
        delta = premium_eur if option_type == 'C' else -premium_eur
    trade_event.net_proceeds_or_cost_basis_eur = trade_event.net_proceeds_or_cost_basis_eur + delta
    logger.info(f"Historical stock trade {trade_event.event_id}: applied option-premium "
                f"adjustment {delta:+.2f} EUR (option type {option_type}) to the replayed basis.")


def run_main_calculations(
    financial_events: List[FinancialEvent],
    asset_resolver: AssetResolver,
    currency_converter: CurrencyConverter,
    exchange_rate_provider: ECBExchangeRateProvider,
    tax_year: int,
    internal_calculation_precision: int, # Renamed from internal_working_precision
    decimal_rounding_mode: str,
    data_gap_collector: Optional["DataGapCollector"] = None
) -> Tuple[List[RealizedGainLoss], List[VorabpauschaleData], List[FinancialEvent], int]: 
    """
    Runs the main calculation logic:
    1. Separates historical and current year events.
    2. Initializes FIFO ledgers based on SOY positions and historical trades.
    3. Processes current year events chronologically using dedicated processors.
    4. Performs EOY quantity validation (logs errors but does not halt).
    5. Calculates Vorabpauschale (currently placeholder).
    6. Returns calculated results (Realized G/L, Vorabpauschale), processed events, and EOY mismatch count.
    """
    logger.info(f"Starting main calculation engine for tax year {tax_year} with {len(financial_events)} events.")
    ctx = Context(prec=internal_calculation_precision, rounding=decimal_rounding_mode) # Renamed internal_working_precision

    realized_gains_losses: List[RealizedGainLoss] = []
    vorabpauschale_data_items: List[VorabpauschaleData] = []

    # Per-Depot FIFO: historical events grouped by (account_key, asset_id);
    # currency events by (account_key, currency_code).
    historical_events_by_asset: DefaultDict[Any, List[FinancialEvent]] = defaultdict(list)
    historical_merger_events: List[CorpActionMergerStock] = []
    historical_currency_events: DefaultDict[Any, List[FinancialEvent]] = defaultdict(list)
    historical_transfer_events: List[InternalTransferEvent] = []
    all_transfer_events: List[InternalTransferEvent] = []  # historical + current (for ledger combos)
    current_year_events: List[FinancialEvent] = []

    pending_option_adjustments: Dict[uuid.UUID, Tuple[Decimal, uuid.UUID, str]] = {}

    tax_year_start_date_str = f"{tax_year}-01-01"
    tax_year_end_date_str = f"{tax_year}-12-31"
    tax_year_start_date_obj = parse_ibkr_date(tax_year_start_date_str)
    tax_year_end_date_obj = parse_ibkr_date(tax_year_end_date_str)
    
    if not tax_year_start_date_obj:
        logger.error(f"Could not parse tax year start date: {tax_year_start_date_str}. Aborting calculations.")
        return [], [], financial_events, 0 
    if not tax_year_end_date_obj:
        logger.error(f"Could not parse tax year end date: {tax_year_end_date_str}. Aborting calculations.")
        return [], [], financial_events, 0 

    logger.info("Separating historical and current year events...")
    filtered_events_count = 0
    for event in financial_events:
        try:
            event_sort_key = get_event_sort_key(event, asset_resolver)
            event_date_obj = event_sort_key[0] 
        except ValueError as e:
            logger.error(f"Event {event.event_id} has invalid date or identifier ({e}). Cannot process.")
            continue 

        if isinstance(event, InternalTransferEvent):
            # Internal Depotübertragung: tax-neutral lot move. Historical ones are replayed inside
            # the unified historical stream (securities AND non-EUR cash share the one handler);
            # current-year ones in the main loop. Either way they define (account, asset) ledger
            # combos that must exist on both sides.
            all_transfer_events.append(event)
            if event_date_obj < tax_year_start_date_obj:
                historical_transfer_events.append(event)
            elif event_date_obj <= tax_year_end_date_obj:
                current_year_events.append(event)
            else:
                filtered_events_count += 1
            continue

        if event_date_obj < tax_year_start_date_obj:
            if isinstance(event, CorpActionMergerStock):
                historical_merger_events.append(event)
            elif isinstance(event, (TradeEvent, CorpActionSplitForward, CorpActionStockDividend)):
                historical_events_by_asset[(account_key(event.account_id), event.asset_internal_id)].append(event)
            elif isinstance(event, CashFlowEvent) and event.event_type == FinancialEventType.CAPITAL_REPAYMENT:
                # Einlagenrückgewähr: permanent basis reduction — must be part of
                # the securities ledger reconstruction (its currency impact is
                # additionally collected below like every cash flow).
                historical_events_by_asset[(account_key(event.account_id), event.asset_internal_id)].append(event)
            elif isinstance(event, (OptionExerciseEvent, OptionAssignmentEvent, OptionExpirationWorthlessEvent)):
                # Option lifecycle events mutate ledger state across years: they
                # consume the option's contract lots AND (exercise/assignment)
                # produce the premium adjustment that becomes part of the linked
                # stock trade's PERMANENT acquisition cost — a stock acquired
                # via exercise in year X-1 and sold in year X must realise
                # against the premium-adjusted basis.
                historical_events_by_asset[(account_key(event.account_id), event.asset_internal_id)].append(event)
            elif isinstance(event, CurrencyConversionEvent):
                # CurrencyConversionEvents need to be associated with the non-EUR currency's asset ID
                # (or both currencies for cross-currency trades like USD→GBP), per account.
                acct = account_key(event.account_id)
                from_is_non_eur = event.from_currency.upper() != "EUR"
                to_is_non_eur = event.to_currency.upper() != "EUR"

                if from_is_non_eur:
                    from_asset = asset_resolver.get_cash_balance_asset(event.from_currency)
                    if from_asset:
                        historical_events_by_asset[(acct, from_asset.internal_asset_id)].append(event)

                if to_is_non_eur:
                    to_asset = asset_resolver.get_cash_balance_asset(event.to_currency)
                    if to_asset:
                        historical_events_by_asset[(acct, to_asset.internal_asset_id)].append(event)
            # Collect ALL currency-impacting historical events for comprehensive FIFO replay
            _collect_historical_currency_event(event, historical_currency_events)
        elif event_date_obj <= tax_year_end_date_obj:
            current_year_events.append(event)
        else:
            filtered_events_count += 1
            logger.debug(f"Filtered out event {event.event_id} with date {event_date_obj} (after tax year {tax_year})")
    
    if filtered_events_count > 0:
        logger.info(f"Filtered out {filtered_events_count} events occurring after tax year {tax_year}")

    logger.info(f"Separated events: {sum(len(v) for v in historical_events_by_asset.values())} relevant historical events for SOY FIFO reconstruction, "
                f"{len(current_year_events)} current tax year events.")

    fifo_ledgers: Dict[Tuple[str, uuid.UUID], FifoLedger] = {}  # keyed by (account_key, asset_id); seam: all DEFAULT_ACCOUNT until the per-Depot flip
    currency_fifo_ledgers: Dict[Tuple[str, uuid.UUID], FifoLedger] = {}  # keyed by (account_key, asset_id); seam: all DEFAULT_ACCOUNT until the per-Depot flip  # Separate dict for currency ledgers

    # === Unified historical replay (AR5) ===
    # ONE ordered stream rebuilds all pre-tax-year ledger state — securities
    # AND currencies — under the documented phase contract (see engine/replay.py):
    # LEDGER_EVENTS (chronological) -> MERGERS (chronological) -> RECONCILE.
    from src.engine.replay import ReplayStream, Phase
    stream = ReplayStream()

    logger.info("Building unified historical replay stream (securities, mergers, currencies)...")

    positions_by_account: Dict[Any, Dict[str, Any]] = getattr(asset_resolver, "positions_by_account", {}) or {}

    def _build_security_ledger(asset_obj):
        mult = asset_obj.multiplier if isinstance(asset_obj, Option) else None
        ftype = asset_obj.fund_type if isinstance(asset_obj, InvestmentFund) else None
        return FifoLedger(
            asset_internal_id=asset_obj.internal_asset_id, asset_category=asset_obj.asset_category,
            asset_multiplier_from_asset=mult,
            currency_converter=currency_converter, exchange_rate_provider=exchange_rate_provider,
            internal_working_precision=internal_calculation_precision,
            decimal_rounding_mode=decimal_rounding_mode, fund_type=ftype,
        )

    def _apply_internal_transfer(event: InternalTransferEvent) -> None:
        """Move FIFO lots from the source account ledger to the target account ledger for an
        internal Depotübertragung — tax-neutral, basis and acquisition date preserved. Used for
        both historical (SoY reconstruction) and current-year transfers."""
        src = account_key(event.account_id)
        tgt = account_key(event.target_account_id)
        asset_id = event.asset_internal_id
        asset_obj = asset_resolver.get_asset_by_id(asset_id)

        src_ledger = fifo_ledgers.get((src, asset_id))
        src_long = sum((l.quantity for l in src_ledger.lots), Decimal(0)) if src_ledger else Decimal(0)
        src_short = sum((l.quantity_shorted for l in src_ledger.short_lots), Decimal(0)) if src_ledger else Decimal(0)
        if src_ledger is None or (src_long <= Decimal("1e-9") and src_short <= Decimal("1e-9")):
            logger.warning(f"Internal transfer {event.event_id}: source ledger ({src}) for "
                           f"{asset_obj.get_classification_key() if asset_obj else asset_id} is "
                           f"empty/missing; nothing to move.")
            return

        # A position is either net long or net short. Move whichever the source holds (a transferred
        # short position carries its open-short proceeds + opening date, same Fußstapfentheorie).
        try:
            if src_short > Decimal("1e-9") and src_long <= Decimal("1e-9"):
                is_short = True
                drained = src_ledger.transfer_out_short_lots(event.quantity, str(event.event_id))
            else:
                is_short = False
                drained = src_ledger.transfer_out_long_lots(event.quantity, str(event.event_id))
        except ValueError as e:
            logger.error(f"Internal transfer {event.event_id}: {e}")
            return
        if not drained:
            return

        tgt_ledger = fifo_ledgers.get((tgt, asset_id))
        if tgt_ledger is None:
            if isinstance(asset_obj, CashBalance) and asset_obj.currency:
                _ensure_currency_ledger_exists(
                    asset_obj.currency, asset_resolver, currency_fifo_ledgers, fifo_ledgers,
                    currency_converter, exchange_rate_provider,
                    internal_calculation_precision, decimal_rounding_mode,
                    f"Transfer target {event.event_id}", account=tgt)
                tgt_ledger = fifo_ledgers.get((tgt, asset_id))
            elif asset_obj is not None:
                tgt_ledger = _build_security_ledger(asset_obj)
                fifo_ledgers[(tgt, asset_id)] = tgt_ledger
        if tgt_ledger is None:
            logger.error(f"Internal transfer {event.event_id}: could not obtain target ledger "
                         f"({tgt}); transferred lots dropped.")
            return

        if is_short:
            tgt_ledger.receive_transferred_short_lots(drained)
            moved = sum((l.quantity_shorted for l in drained), Decimal(0))
        else:
            tgt_ledger.receive_transferred_lots(drained)
            moved = sum((l.quantity for l in drained), Decimal(0))
        logger.info(f"Internal transfer {event.event_id}: moved {moved} {'SHORT' if is_short else 'long'} of "
                    f"{asset_obj.get_classification_key() if asset_obj else asset_id} from {src} "
                    f"to {tgt} (proceeds/cost basis and date preserved, tax-neutral).")

    # The (account, asset) combos needing a security ledger: any with a recorded position, with
    # historical security events, touched by a current-year event, or a merger source/target.
    combos: set = set()
    for combo in positions_by_account.keys():
        combos.add(combo)
    for combo in historical_events_by_asset.keys():
        combos.add(combo)
    for event in current_year_events:
        combos.add((account_key(event.account_id), event.asset_internal_id))
    for merger_event in historical_merger_events + [e for e in current_year_events if isinstance(e, CorpActionMergerStock)]:
        acct_m = account_key(merger_event.account_id)
        combos.add((acct_m, merger_event.asset_internal_id))
        combos.add((acct_m, merger_event.new_asset_internal_id))
    # Internal transfers: both the source and target account need a ledger for the moved asset.
    for transfer_event in all_transfer_events:
        combos.add((account_key(transfer_event.account_id), transfer_event.asset_internal_id))
        combos.add((account_key(transfer_event.target_account_id), transfer_event.asset_internal_id))

    # Pass A: create the per-(account, asset) ledgers, then stream ALL historical (pre-tax-year)
    # trade / split / stock-dividend events chronologically (Phase.LEDGER_EVENTS). Per-Depot:
    # each account's events apply to that account's own ledger (§20 Abs. 4 S. 7 EStG).
    logger.info("Pass A: Creating per-(account, asset) FIFO ledgers...")
    for (acct, asset_id) in combos:
        asset_obj = asset_resolver.get_asset_by_id(asset_id)
        if asset_obj is None or asset_obj.asset_category == AssetCategory.CASH_BALANCE:
            continue
        ledger = _build_security_ledger(asset_obj)
        # Resolve fund type / clear lot state / reset the inconsistency flag before replay.
        ledger.begin_historical_simulation(asset_obj)
        fifo_ledgers[(acct, asset_id)] = ledger

    logger.info("Pass A: Replaying historical trade/transfer events chronologically...")
    # Option-premium adjustments produced by historical exercises/assignments,
    # consumed by the linked historical stock trades (chronological order of
    # the stream guarantees the option event runs before its stock leg, the
    # same ordering contract the current-year loop relies on).
    hist_pending_adjustments: Dict[uuid.UUID, Tuple[Decimal, uuid.UUID, str]] = {}
    for (acct, asset_id), evlist in historical_events_by_asset.items():
        ledger = fifo_ledgers.get((acct, asset_id))
        if ledger is None:
            continue  # cash-balance assets: their events replay in the currency stream below
        asset_obj = asset_resolver.get_asset_by_id(asset_id)
        for hist_event in evlist:
            try:
                hist_key = get_event_sort_key(hist_event, asset_resolver)
            except ValueError as e:
                logger.critical(f"Fatal error sorting historical events for asset {asset_obj.get_classification_key()} (ID: {asset_id}): {e}. Cannot guarantee deterministic order for FIFO init. Aborting.")
                raise e
            if isinstance(hist_event, (OptionExerciseEvent, OptionAssignmentEvent, OptionExpirationWorthlessEvent)):
                apply_fn = (lambda l=ledger, e=hist_event:
                            _apply_historical_option_event(e, l, asset_resolver, hist_pending_adjustments))
            elif (isinstance(hist_event, TradeEvent) and hist_event.related_option_event_id
                  and asset_obj.asset_category == AssetCategory.STOCK):
                apply_fn = (lambda l=ledger, a=asset_obj, e=hist_event:
                            (_adjust_historical_stock_trade(e, asset_resolver, hist_pending_adjustments),
                             l.apply_historical_event(a, e, tax_year)))
            else:
                apply_fn = (lambda l=ledger, a=asset_obj, e=hist_event:
                            l.apply_historical_event(a, e, tax_year))
            stream.add(
                Phase.LEDGER_EVENTS, hist_key, apply_fn,
                label=f"sec:{asset_obj.get_classification_key()}",
            )
    # Historical internal transfers: registered ONCE in the unified stream
    # (Phase.LEDGER_EVENTS) — securities and non-EUR cash share the same
    # handler; the chronological interleave with trades reconstructs a
    # bought-transferred-sold history lot-exactly (carried basis + date).
    for transfer_event in historical_transfer_events:
        try:
            t_key = get_event_sort_key(transfer_event, asset_resolver)
        except ValueError as e:
            logger.critical(f"Fatal error sorting historical transfer {transfer_event.event_id}: {e}. Aborting.")
            raise
        stream.add(
            Phase.LEDGER_EVENTS, t_key,
            (lambda t=transfer_event: _apply_internal_transfer(t)),
            label="transfer",
        )
    securities_ledger_count = len(fifo_ledgers)

    if historical_merger_events:
        logger.info(f"Pass 2: Replaying {len(historical_merger_events)} historical stock merger(s)...")
        for merger_event in historical_merger_events:
            try:
                merger_key = get_event_sort_key(merger_event, asset_resolver)
            except ValueError as e:
                logger.critical(f"Fatal error sorting historical merger events: {e}. Aborting.")
                raise e
            stream.add(
                Phase.MERGERS, merger_key,
                (lambda m=merger_event: _replay_historical_merger(m, fifo_ledgers, asset_resolver)),
                label="merger",
            )
    else:
        logger.info("Pass 2: No historical stock mergers to replay.")

    # Reconcile phase: securities ledgers against SoY positions (after merger
    # lots are in place). Items are added for the SECURITIES ledgers existing
    # now — currency ledgers reconcile against cash balances separately below.
    logger.info("Pass 3: Reconciling per-(account, asset) ledgers with SoY positions...")
    def _reconcile_security_soy(ledger, view, asset_obj, acct):
        try:
            ledger.reconcile_with_soy_position(view, tax_year)
        except ValueError as e:
            logger.critical(f"Fatal error reconciling SOY for {asset_obj.get_classification_key()} acct {acct}: {e}. Aborting.")
            raise e
    for (ledger_account, asset_id), ledger in fifo_ledgers.items():
        asset_obj = asset_resolver.get_asset_by_id(asset_id)
        if asset_obj:
            view = _AccountAssetView(asset_obj, positions_by_account.get((ledger_account, asset_id)))
            stream.add(
                Phase.RECONCILE, (0,),
                (lambda l=ledger, v=view, a=asset_obj, ac=ledger_account: _reconcile_security_soy(l, v, a, ac)),
                label=f"reconcile-sec:{asset_obj.get_classification_key()}",
            )

    # §19 Abs. 1 S. 3 InvStG: hand each fund ledger the VP-deduction context (declared VP
    # per year — resolved by the pre-pass and attached to the asset — and the year-end
    # quantities used as the per-unit denominator), so fund disposals reduce the gain.
    for (_ledger_account, asset_id), ledger in fifo_ledgers.items():
        if ledger.asset_category != AssetCategory.INVESTMENT_FUND:
            continue
        asset_obj = asset_resolver.get_asset_by_id(asset_id)
        declared = getattr(asset_obj, "vp_declared_by_year", None) if asset_obj else None
        if declared:
            ledger.vp_declared_by_year = declared
            ledger.vp_qty_eoy_by_year = year_end_quantities(financial_events, asset_id, tax_year)

    # Initialize currency FIFO ledgers with comprehensive historical replay, per (account, currency).
    logger.info("Initializing currency FIFO ledgers for foreign currency positions...")

    # Per-account SoY/EoY cash balances (from the parsing orchestrator). Keyed by
    # (account_key, currency_asset_id) -> {"soy","eoy","currency"}. Absent for older
    # single-account exports, in which case currencies collapse to the DEFAULT account.
    cash_by_account: Dict[Any, Dict[str, Any]] = getattr(asset_resolver, "cash_by_account", {}) or {}

    # How many distinct accounts hold each currency asset (used to decide whether the aggregated
    # SoY cost basis on the CashBalance asset may be attributed to a single account's ledger).
    accounts_per_currency: DefaultDict[Any, int] = defaultdict(int)
    for (cba_acct, cba_cur_asset_id) in cash_by_account.keys():
        accounts_per_currency[cba_cur_asset_id] += 1

    # (account, currency_code) combos needing a currency ledger. Seed from KNOWN cash balances
    # (per-account rows, or — for single-account/older exports — the CashBalance assets). A currency
    # is "tracked" once it has a per-account cash balance; for such currencies we ALSO create a
    # ledger in every account that merely TOUCHES the currency via a trade/conversion/cashflow, so a
    # disposal from an account that had no opening balance still realises per Depot (instead of the
    # processor finding no ledger and silently skipping the FX event). We do NOT create tracking for
    # currencies that have no cash balance at all (avoids spurious FX when no cash CSV was provided).
    currency_combos: set = set()
    for (cba_acct, cba_cur_asset_id), cba_state in cash_by_account.items():
        ccy = (cba_state.get("currency") or "").upper()
        if ccy and ccy != "EUR":
            currency_combos.add((cba_acct, ccy))
    # Fallback: if no per-account cash data is available, init each known CashBalance asset's
    # currency on the DEFAULT account (preserves single-account behaviour).
    if not cash_by_account:
        for asset_id, asset_obj in asset_resolver.assets_by_internal_id.items():
            if isinstance(asset_obj, CashBalance) and asset_obj.currency:
                ccy = asset_obj.currency.upper()
                if ccy != "EUR":
                    currency_combos.add((DEFAULT_ACCOUNT, ccy))
    else:
        # Real multi-account path: create a per-account ledger for every (account, currency) that
        # appears in ANY currency-affecting event, so FX consumption realises against that account's
        # own lots (a currency disposed from an account that had no opening balance — e.g. CHF/HKD
        # acquired and spent intra-year — must still be tracked per Depot, not silently skipped).
        # This is gated on cash_by_account being present, so the single-account path (no cash CSV)
        # is unaffected and does not spuriously start tracking currencies.
        current_currency_events: DefaultDict[Any, List[FinancialEvent]] = defaultdict(list)
        for ev in current_year_events:
            _collect_historical_currency_event(ev, current_currency_events)
        for (cc_acct, cc_ccy) in list(historical_currency_events.keys()) + list(current_currency_events.keys()):
            if cc_ccy and cc_ccy.upper() != "EUR":
                currency_combos.add((cc_acct, cc_ccy.upper()))

    # Cash internal transfers: ensure both source and target accounts have a currency ledger.
    for transfer_event in all_transfer_events:
        t_asset = asset_resolver.get_asset_by_id(transfer_event.asset_internal_id)
        if isinstance(t_asset, CashBalance) and t_asset.currency and t_asset.currency.upper() != "EUR":
            ccy = t_asset.currency.upper()
            currency_combos.add((account_key(transfer_event.account_id), ccy))
            currency_combos.add((account_key(transfer_event.target_account_id), ccy))

    # Phase 1: ensure every (account, currency) ledger exists (creation is unordered
    # setup, not stream work — the stream replays EVENTS).
    for (acct, currency_code) in sorted(currency_combos):
        _ensure_currency_ledger_exists(
            currency_code, asset_resolver, currency_fifo_ledgers, fifo_ledgers,
            currency_converter, exchange_rate_provider,
            internal_calculation_precision, decimal_rounding_mode,
            f"Currency init {currency_code} acct {acct}", account=acct,
        )

    # Phase 2: stream each account's historical currency events; per-(account, currency)
    # relative order = get_event_sort_key (ties: insertion seq). Events of different
    # (account, currency) ledgers commute (one ledger each).
    currency_replay_counts: Dict[Any, list] = {}
    for (acct, currency_code) in sorted(currency_combos):
        currency_asset = asset_resolver.get_cash_balance_asset(currency_code)
        if not currency_asset:
            continue
        currency_ledger = currency_fifo_ledgers.get((acct, currency_asset.internal_asset_id))
        if not currency_ledger:
            continue

        hist_events = historical_currency_events.get((acct, currency_code), [])
        if hist_events:
            currency_replay_counts[(acct, currency_code)] = [0, len(hist_events)]

            def _apply_ccy_event(event, led=currency_ledger, ck=(acct, currency_code)):
                currency_replay_counts[ck][0] += _apply_historical_currency_event(
                    event, led, ck[1], currency_converter, ctx
                )

            for hist_event in hist_events:
                try:
                    hist_key = get_event_sort_key(hist_event, asset_resolver)
                except ValueError as e:
                    logger.error(f"Could not sort historical events for {currency_code}: {e}")
                    hist_key = (date.min, ())  # keep insertion order via seq
                stream.add(
                    Phase.LEDGER_EVENTS, hist_key,
                    (lambda e=hist_event, f=_apply_ccy_event: f(e)),
                    label=f"ccy:{currency_code}",
                )

        # Phase 3 (streamed RECONCILE): SOY quantity is authoritative — reconcile each
        # (account, currency) ledger to its OWN account's SoY balance. An account that only
        # TOUCHES the currency via events (no opening balance) must NOT be reconciled to the
        # aggregate — that would create a spurious full-balance lot in every such account
        # (double counting); leave it empty so its lots are built purely from its own events.
        cash_state = cash_by_account.get((acct, currency_asset.internal_asset_id))
        recon_asset = None
        if cash_state is not None:
            # When this currency is held in a single account, the per-account SoY equals the
            # aggregate, so the aggregated SoY cost basis (if any) legitimately belongs to this
            # ledger. With multiple accounts we have no per-account cost basis (the cash-balance
            # export carries none), so null it and let the ECB-rate fallback apply per account.
            single_account = accounts_per_currency.get(currency_asset.internal_asset_id, 0) <= 1
            recon_asset = _AccountAssetView(currency_asset, {
                "soy_quantity": cash_state.get("soy"),
                "soy_currency": currency_code,
                "soy_cost_basis_amount": currency_asset.soy_cost_basis_amount if single_account else None,
                "eoy_quantity": cash_state.get("eoy"),
                "eoy_currency": currency_code,
            })
        elif not cash_by_account:
            # Single-account / older export fallback: the DEFAULT ledger reconciles to the aggregate.
            recon_asset = currency_asset
        if recon_asset is not None and isinstance(recon_asset, CashBalance):
            stream.add(
                Phase.RECONCILE, (0,),
                (lambda l=currency_ledger, a=recon_asset:
                    _reconcile_currency_soy(l, a, tax_year, exchange_rate_provider, ctx)),
                label=f"reconcile-ccy:{currency_code}",
            )

    # === Run the unified historical replay ===
    stream.run()

    logger.info(f"Initialized {securities_ledger_count} FIFO ledgers (unified replay).")
    for (rc_acct, rc_ccy), (done, total) in currency_replay_counts.items():
        logger.info(f"Currency {rc_ccy}: Replayed {done}/{total} historical events")
    logger.info(f"Initialized {len(currency_fifo_ledgers)} currency FIFO ledgers.")

    logger.info("Initializing event processors...")
    trade_processor = TradeProcessor()
    split_processor = SplitProcessor()
    merger_cash_processor = MergerCashProcessor()
    stock_dividend_processor = StockDividendProcessor()
    merger_stock_processor = MergerStockProcessor()
    generic_ca_processor = GenericCorporateActionProcessor()
    expire_dividend_rights_processor = ExpireDividendRightsProcessor()
    option_exercise_processor = OptionExerciseProcessor()
    option_assignment_processor = OptionAssignmentProcessor()
    option_expiration_processor = OptionExpirationWorthlessProcessor()
    option_cash_settlement_processor = OptionCashSettlementProcessor()

    # Currency conversion processor for FX trades
    currency_conversion_processor = CurrencyConversionProcessor(
        currency_converter=currency_converter,
        internal_calculation_precision=internal_calculation_precision,
        decimal_rounding_mode=decimal_rounding_mode
    )

    event_processor_map: Dict[FinancialEventType, EventProcessor] = {
        FinancialEventType.TRADE_BUY_LONG: trade_processor,
        FinancialEventType.TRADE_SELL_LONG: trade_processor,
        FinancialEventType.TRADE_SELL_SHORT_OPEN: trade_processor,
        FinancialEventType.TRADE_BUY_SHORT_COVER: trade_processor,
        FinancialEventType.CORP_SPLIT_FORWARD: split_processor, # Renamed
        FinancialEventType.CORP_MERGER_CASH: merger_cash_processor, # Renamed
        FinancialEventType.CORP_STOCK_DIVIDEND: stock_dividend_processor, # Renamed
        FinancialEventType.CORP_MERGER_STOCK: merger_stock_processor, # Renamed
        FinancialEventType.CORP_EXPIRE_DIVIDEND_RIGHTS: expire_dividend_rights_processor,
        FinancialEventType.OPTION_EXERCISE: option_exercise_processor,
        FinancialEventType.OPTION_ASSIGNMENT: option_assignment_processor,
        FinancialEventType.OPTION_EXPIRATION_WORTHLESS: option_expiration_processor,
        FinancialEventType.OPTION_CASH_SETTLEMENT: option_cash_settlement_processor,
    }

    # Resolve the same-day transfer->merger dependency (a transfer that delivers a security into the
    # account where it then merges must precede that merger; the merger's account disambiguates).
    current_year_events = _order_current_year_events_for_merger_deps(current_year_events)

    logger.info(f"Processing {len(current_year_events)} current tax year events using dispatch table...")
    for event_idx, event in enumerate(current_year_events):
        # Internal Depotübertragung: tax-neutral lot move between the person's own accounts.
        # Handled directly (no processor, no RGL) — drain source ledger, receive into target.
        if isinstance(event, InternalTransferEvent):
            _apply_internal_transfer(event)
            continue

        asset_object = asset_resolver.get_asset_by_id(event.asset_internal_id)
        if not asset_object:
            raise ProcessingError(f"Event {event.event_id} ({event.event_type.name}) references unknown asset {event.asset_internal_id}. Asset resolution failure.")

        event_acct = account_key(event.account_id)
        ledger = fifo_ledgers.get((event_acct, asset_object.internal_asset_id))
        processor = event_processor_map.get(event.event_type)

        if not processor and isinstance(event, CorporateActionEvent):
            logger.warning(f"Event {event.event_id} is CorporateActionEvent type {event.event_type.name} for asset {_format_asset_info(asset_object)} but not in specific map. Using GenericCorporateActionProcessor.")
            processor = generic_ca_processor
        elif processor and isinstance(event, CorporateActionEvent) and not isinstance(event, (CorpActionSplitForward, CorpActionMergerCash, CorpActionStockDividend, CorpActionMergerStock, CorpActionExpireDividendRights)):
            logger.warning(f"Event {event.event_id} is generic CorporateActionEvent with type {event.event_type.name} for asset {_format_asset_info(asset_object)} but specific processor expects subclass. Using GenericCorporateActionProcessor.")
            processor = generic_ca_processor

        if processor and (ledger or event.event_type in [FinancialEventType.OPTION_EXERCISE, FinancialEventType.OPTION_ASSIGNMENT, FinancialEventType.OPTION_EXPIRATION_WORTHLESS, FinancialEventType.OPTION_CASH_SETTLEMENT]):
            if not ledger and asset_object.asset_category == AssetCategory.OPTION:
                logger.warning(f"Option event {event.event_id} ({event.event_type.name}) occurred, but no FIFO ledger exists. Processor will handle.")
            elif not ledger and asset_object.asset_category != AssetCategory.CASH_BALANCE:
                raise ProcessingError(f"Event {event.event_id} ({event.event_type.name}) for asset {asset_object.get_classification_key()} requires a FIFO ledger but none was found.")

            try:
                context: Dict[str, Any] = {
                    'asset_resolver': asset_resolver,
                    'fifo_ledgers': fifo_ledgers,
                    'pending_option_adjustments': pending_option_adjustments,
                    'currency_converter': currency_converter,
                    # Phase 5a: Pass currency infrastructure for implicit FX from security trades
                    'currency_fifo_ledgers': currency_fifo_ledgers,
                    'currency_processor': currency_conversion_processor,
                }
                current_ledger = ledger if ledger else None

                # Split position flip events (C;O / O;C) into close + open sub-events
                if isinstance(event, TradeEvent) and event.is_position_flip and current_ledger:
                    from .fifo_manager import split_position_flip_event
                    avail_long = sum(lot.quantity for lot in current_ledger.lots) if current_ledger.lots else Decimal(0)
                    avail_short = sum(lot.quantity_shorted for lot in current_ledger.short_lots) if current_ledger.short_lots else Decimal(0)
                    sub_events = split_position_flip_event(event, avail_long, avail_short)
                else:
                    sub_events = [event]

                for dispatch_event in sub_events:
                    sub_processor = event_processor_map.get(dispatch_event.event_type, processor)
                    logger.debug(f"Dispatching event {dispatch_event.event_id} ({dispatch_event.event_type.name}) to {type(sub_processor).__name__}")
                    new_rgls = sub_processor.process(dispatch_event, current_ledger, context)
                    if new_rgls:
                        realized_gains_losses.extend(new_rgls)
                        logger.debug(f"  Processor generated {len(new_rgls)} RGL records.")

            except ValueError as e:
                logger.critical(f"Fatal error processing event {event.event_id} ({event.event_type.name}) for asset {asset_object.get_classification_key()} via {type(processor).__name__}: {e}. Aborting.")
                raise e
            except TypeError as e:
                raise ProcessingError(
                    f"Type error processing event {event.event_id} ({event.event_type.name}) with {type(processor).__name__}: {e}"
                ) from e
            except NotImplementedError:
                raise ProcessingError(
                    f"Processor {type(processor).__name__} does not implement handling for event type {event.event_type.name} (ID: {event.event_id})."
                )

        elif not ledger and asset_object.asset_category != AssetCategory.CASH_BALANCE:
            # No security FIFO ledger, but cash flow events still affect currency ledgers
            if event.event_type in [
                FinancialEventType.DIVIDEND_CASH, FinancialEventType.DISTRIBUTION_FUND,
                FinancialEventType.INTEREST_RECEIVED, FinancialEventType.INTEREST_PAID_STUECKZINSEN,
                FinancialEventType.WITHHOLDING_TAX, FinancialEventType.FEE_TRANSACTION
            ]:
                logger.debug(f"Event {event.event_id} ({event.event_type.name}) for {asset_object.get_classification_key()} has no security ledger, but processing currency impact.")
                if currency_conversion_processor is not None:
                    cashflow_fx_rgls = _process_cashflow_currency_impact(
                        event, asset_resolver, currency_fifo_ledgers,
                        currency_conversion_processor, fifo_ledgers,
                        currency_converter, exchange_rate_provider,
                        internal_calculation_precision, decimal_rounding_mode
                    )
                    if cashflow_fx_rgls:
                        realized_gains_losses.extend(cashflow_fx_rgls)
            else:
                logger.warning(f"Event {event.event_id} ({event.event_type.name}) for non-cash asset {asset_object.get_classification_key()} occurred, but no FIFO ledger exists. Skipping processing for this event.")

        # Handle capital repayments directly
        elif event.event_type == FinancialEventType.CAPITAL_REPAYMENT and ledger:
            try:
                repayment_amount_eur = event.gross_amount_eur or Decimal('0')
                logger.info(f"Processing capital repayment for {asset_object.get_classification_key()}: {repayment_amount_eur} EUR")
                excess = ledger.reduce_cost_basis_for_capital_repayment(repayment_amount_eur)
                if excess > Decimal('0'):
                    logger.info(f"Capital repayment excess {excess} EUR becomes taxable dividend income")

                    # Create new DIVIDEND_CASH event for excess amount
                    _create_excess_dividend_event(event, excess, asset_object, current_year_events)

                    # Reduce original capital repayment event to only the cost basis portion
                    cost_basis_portion = repayment_amount_eur - excess
                    event.gross_amount_eur = cost_basis_portion
                    event.gross_amount_foreign_currency = cost_basis_portion
                    logger.info(f"Reduced capital repayment event to cost basis portion: {cost_basis_portion} EUR")

                # Capital repayment = you receive cash in the security's currency.
                # If non-EUR, this creates a currency FIFO lot (same as dividend income).
                if currency_conversion_processor is not None:
                    cashflow_fx_rgls = _process_cashflow_currency_impact(
                        event, asset_resolver, currency_fifo_ledgers,
                        currency_conversion_processor, fifo_ledgers,
                        currency_converter, exchange_rate_provider,
                        internal_calculation_precision, decimal_rounding_mode
                    )
                    if cashflow_fx_rgls:
                        realized_gains_losses.extend(cashflow_fx_rgls)

            except Exception as e:
                logger.error(f"Error processing capital repayment {event.event_id}: {e}", exc_info=True)

        # Handle currency conversion events
        elif isinstance(event, CurrencyConversionEvent):
            try:
                logger.debug(f"Processing currency conversion event {event.event_id}: "
                           f"{event.from_amount} {event.from_currency} -> {event.to_amount} {event.to_currency}")
                # Ensure CashBalance assets and ledgers exist for involved currencies
                # (may not exist yet if this FX trade is the first event for a currency)
                for fx_currency_code in [event.from_currency, event.to_currency]:
                    _ensure_currency_ledger_exists(
                        fx_currency_code, asset_resolver, currency_fifo_ledgers, fifo_ledgers,
                        currency_converter, exchange_rate_provider,
                        internal_calculation_precision, decimal_rounding_mode,
                        f"FX trade {event.event_id}", account=event_acct,
                    )
                fx_rgls = currency_conversion_processor.process(event, fifo_ledgers, asset_resolver)
                if fx_rgls:
                    realized_gains_losses.extend(fx_rgls)
                    logger.debug(f"  Currency conversion generated {len(fx_rgls)} RGL records.")
            except Exception as e:
                logger.error(f"Error processing currency conversion {event.event_id}: {e}", exc_info=True)

        elif not processor:
            if event.event_type not in [
                FinancialEventType.DIVIDEND_CASH, FinancialEventType.CAPITAL_REPAYMENT, FinancialEventType.DISTRIBUTION_FUND,
                FinancialEventType.INTEREST_RECEIVED, FinancialEventType.INTEREST_PAID_STUECKZINSEN,
                FinancialEventType.WITHHOLDING_TAX, FinancialEventType.FEE_TRANSACTION
            ]:
                logger.warning(f"No processor mapped and no ledger interaction expected for event type: {event.event_type.name} (ID: {event.event_id}).")
            else:
                logger.debug(f"Event type {event.event_type.name} (ID: {event.event_id}) does not require FIFO ledger processing. Skipping processor dispatch.")

                # Phase 5c: Process implicit currency impact from cash flows
                if currency_conversion_processor is not None:
                    cashflow_fx_rgls = _process_cashflow_currency_impact(
                        event, asset_resolver, currency_fifo_ledgers,
                        currency_conversion_processor, fifo_ledgers,
                        currency_converter, exchange_rate_provider,
                        internal_calculation_precision, decimal_rounding_mode
                    )
                    if cashflow_fx_rgls:
                        realized_gains_losses.extend(cashflow_fx_rgls)
                        logger.debug(f"  Cashflow currency impact generated {len(cashflow_fx_rgls)} RGL records.")


    logger.info("Finished processing current year events.")
    logger.info(f"Pending option adjustments stored: {len(pending_option_adjustments)}")


    logger.info("Performing End-of-Year (EOY) quantity validation...")
    # Per-Depot: a security can have one ledger per account; the reported EoY quantity on the
    # Asset is aggregated across accounts, so compare against the sum of the per-account ledgers
    # (per-person view, see src/engine/ledger_views.py).
    eoy_mismatch_errors = 0 
    for asset_id, asset_obj in asset_resolver.assets_by_internal_id.items():
        if asset_obj.asset_category == AssetCategory.CASH_BALANCE:
            continue

        asset_ledgers = ledgers_for_asset(fifo_ledgers, asset_id)
        calculated_eoy_qty: Decimal

        if asset_ledgers:
            calculated_eoy_qty = sum((l.get_current_position_quantity() for l in asset_ledgers), Decimal(0))
        else:
            calculated_eoy_qty = Decimal(0)
            if asset_obj.soy_quantity is not None and asset_obj.soy_quantity != Decimal(0): # Renamed
                logger.warning(f"EOY Validation: Asset {asset_obj.get_classification_key()} had SOY qty {asset_obj.soy_quantity} but no ledger found at EOY. Calculated EOY assumed 0.") # Renamed

        reported_eoy_qty = asset_obj.eoy_quantity
        try:
            tolerance_exponent = -(ctx.prec // 2)
            comparison_tolerance = Decimal('1e' + str(tolerance_exponent))
        except Exception:
            logger.warning(f"Could not calculate dynamic tolerance from precision {ctx.prec}. Using fixed tolerance 1e-8.")
            comparison_tolerance = Decimal('1e-8')

        if reported_eoy_qty is not None:
            if abs(calculated_eoy_qty - reported_eoy_qty) > comparison_tolerance:
                logger.error(
                    f"CRITICAL EOY MISMATCH for {asset_obj.description or asset_obj.get_classification_key()} (ID: {asset_id}): "
                    f"Calculated EOY Qty: {calculated_eoy_qty}, Reported EOY Qty (from file): {reported_eoy_qty}. "
                    f"Difference: {calculated_eoy_qty - reported_eoy_qty}"
                )
                eoy_mismatch_errors += 1
                if data_gap_collector is not None:
                    data_gap_collector.record(
                        code="EOY_QTY_MISMATCH",
                        subject=asset_obj.description or asset_obj.get_classification_key(),
                        detail=(f"Berechnete EoY-Stückzahl {calculated_eoy_qty} weicht von der im "
                                f"Broker-Report gemeldeten ({reported_eoy_qty}) ab."),
                    )
        elif abs(calculated_eoy_qty) > comparison_tolerance: 
            logger.error( 
                f"EOY MISMATCH for {asset_obj.description or asset_obj.get_classification_key()} (ID: {asset_id}): "
                f"Calculated EOY Qty: {calculated_eoy_qty}, but asset NOT found in EOY positions report (implying reported EOY Qty is 0)."
            )
            eoy_mismatch_errors += 1 
            if data_gap_collector is not None:
                data_gap_collector.record(
                    code="EOY_QTY_MISMATCH",
                    subject=asset_obj.description or asset_obj.get_classification_key(),
                    detail=(f"Berechnete EoY-Stückzahl {calculated_eoy_qty}, aber das Asset fehlt "
                            f"im EoY-Positionsreport (impliziert 0)."),
                )

    if eoy_mismatch_errors > 0:
        logger.error(f"EOY Quantity Validation FAILED with {eoy_mismatch_errors} critical mismatches. Processing will continue, but results may be inaccurate.")
    else:
        logger.info("EOY Quantity Validation passed or no critical mismatches found against reported EOY positions.")

    # Currency EOY validation: compare FIFO ledger quantities against reported cash balances
    logger.info("Performing currency EOY quantity validation...")
    currency_eoy_mismatches = 0
    for asset_id, asset_obj in asset_resolver.assets_by_internal_id.items():
        if asset_obj.asset_category != AssetCategory.CASH_BALANCE:
            continue
        if not isinstance(asset_obj, CashBalance):
            continue
        if asset_obj.currency and asset_obj.currency.upper() == "EUR":
            continue

        reported_eoy = asset_obj.eoy_quantity
        if reported_eoy is None:
            continue

        # Sum this currency's per-account ledgers against the aggregated reported balance.
        currency_ledgers = ledgers_for_asset(currency_fifo_ledgers, asset_id)
        if currency_ledgers:
            long_qty = sum((lot.quantity for l in currency_ledgers for lot in l.lots), Decimal("0"))
            short_qty = sum((lot.quantity_shorted for l in currency_ledgers for lot in l.short_lots), Decimal("0"))
            calculated_eoy = long_qty - short_qty
        else:
            calculated_eoy = Decimal("0")

        currency_tolerance = Decimal("0.01")
        diff = calculated_eoy - reported_eoy
        if abs(diff) > currency_tolerance:
            logger.warning(
                f"CURRENCY EOY MISMATCH {asset_obj.currency}: "
                f"FIFO ledger={calculated_eoy:.2f}, Reported={reported_eoy:.2f}, "
                f"Diff={diff:.2f}"
            )
            currency_eoy_mismatches += 1
        else:
            logger.debug(f"Currency EOY OK {asset_obj.currency}: FIFO={calculated_eoy:.2f}, Reported={reported_eoy:.2f}")

    if currency_eoy_mismatches > 0:
        logger.warning(f"Currency EOY validation: {currency_eoy_mismatches} mismatches found. "
                      f"Common causes: cash balance CSV dates don't match tax year, "
                      f"or untracked currency-impacting events (deposits, withdrawals, "
                      f"margin interest, broker fees not in cash transactions CSV).")
    else:
        logger.info("Currency EOY validation passed.")

    # Vorabpauschale calculation
    vorabpauschale_data_items = _calculate_vorabpauschale(
        asset_resolver=asset_resolver,
        current_year_events=current_year_events,
        currency_converter=currency_converter,
        tax_year=tax_year,
        ctx=ctx,
        fifo_ledgers=fifo_ledgers,
        all_financial_events=financial_events,
    )
    logger.info(f"Vorabpauschale calculation produced {len(vorabpauschale_data_items)} records.")

    processed_income_events_for_output: List[FinancialEvent] = list(current_year_events)

    logger.info(f"Calculation engine finished. Produced {len(realized_gains_losses)} RealizedGainLoss records.")
    logger.info(f"Calculation engine produced {len(vorabpauschale_data_items)} VorabpauschaleData records.")

    return realized_gains_losses, vorabpauschale_data_items, processed_income_events_for_output, eoy_mismatch_errors


def _get_vp_reporting_category(fund_type: InvestmentFundType) -> Optional['TaxReportingCategory']:
    """Map InvestmentFundType to the corresponding VORABPAUSCHALE_BRUTTO TaxReportingCategory."""
    from src.domain.enums import TaxReportingCategory
    mapping = {
        InvestmentFundType.AKTIENFONDS: TaxReportingCategory.ANLAGE_KAP_INV_AKTIENFONDS_VORABPAUSCHALE_BRUTTO,
        InvestmentFundType.MISCHFONDS: TaxReportingCategory.ANLAGE_KAP_INV_MISCHFONDS_VORABPAUSCHALE_BRUTTO,
        InvestmentFundType.IMMOBILIENFONDS: TaxReportingCategory.ANLAGE_KAP_INV_IMMOBILIENFONDS_VORABPAUSCHALE_BRUTTO,
        InvestmentFundType.AUSLANDS_IMMOBILIENFONDS: TaxReportingCategory.ANLAGE_KAP_INV_AUSLANDS_IMMOBILIENFONDS_VORABPAUSCHALE_BRUTTO,
        InvestmentFundType.SONSTIGE_FONDS: TaxReportingCategory.ANLAGE_KAP_INV_SONSTIGE_FONDS_VORABPAUSCHALE_BRUTTO,
        InvestmentFundType.NONE: TaxReportingCategory.ANLAGE_KAP_INV_SONSTIGE_FONDS_VORABPAUSCHALE_BRUTTO,
    }
    return mapping.get(fund_type)


def _vp_partial_year_factor(
    asset_obj: "InvestmentFund",
    fifo_ledgers: Optional[Dict[Tuple[str, uuid.UUID], FifoLedger]],
    target_year: int,
    ctx: Context,
    acquisition_month: Optional[int],
    use_ledger: bool,
) -> Decimal:
    """
    Units-weighted §18 Abs. 2 retained fraction for the units held at the end of
    `target_year`.

    Each lot acquired in a year before `target_year` keeps the full factor 1; a lot
    acquired in month M of `target_year` keeps (13 - M)/12. Because every unit shares
    the same year-start NAV, applying this units-weighted factor to the fund-level gross
    Vorabpauschale equals the per-lot sum.

    For the current year, per-lot acquisition dates are read from the FIFO ledger
    (which reflects the year-end holdings). For a prior year the ledger no longer
    reflects that year's holdings, so the single earliest-acquisition month is used.
    """
    twelve = Decimal("12")
    if use_ledger:
        # Per-PERSON holdings across all accounts (AR4 aggregate view): the
        # §18 Abs. 2 factor depends on when the person acquired the units,
        # not in which Depot they sit.
        lots = aggregate_lots(fifo_ledgers, asset_obj.internal_asset_id) if fifo_ledgers else []
        if lots:
            total_q = Decimal("0")
            weighted = Decimal("0")
            for lot in lots:
                acq = parse_ibkr_date(lot.acquisition_date)
                if acq is not None and acq.year == target_year:
                    factor = ctx.divide(Decimal(13 - acq.month), twelve)
                else:
                    factor = Decimal("1")
                total_q = ctx.add(total_q, lot.quantity)
                weighted = ctx.add(weighted, ctx.multiply(lot.quantity, factor))
            if total_q > Decimal("0"):
                return ctx.divide(weighted, total_q)

    if acquisition_month:
        return ctx.divide(Decimal(13 - int(acquisition_month)), twelve)
    return Decimal("1")


def _build_fund_vp_record(
    asset_obj: "InvestmentFund",
    asset_id: uuid.UUID,
    target_year: int,
    basiszins: Decimal,
    base_return_rate: Decimal,
    fund_value_soy_eur: Decimal,
    fund_value_eoy_eur: Decimal,
    distributions_eur: Decimal,
    partial_year_factor: Decimal,
    soy_nav_eur: Decimal,
    ctx: Context,
) -> Optional[VorabpauschaleData]:
    """Per-fund §18 InvStG computation from EUR snapshot values. Returns None if VP is 0."""
    from src.utils.tax_utils import get_teilfreistellung_rate_for_fund_type

    factor_70 = Decimal("0.7")
    basisertrag = ctx.multiply(ctx.multiply(fund_value_soy_eur, base_return_rate), factor_70)
    if basisertrag <= Decimal('0'):
        return None
    vp_after_dist = ctx.subtract(basisertrag, distributions_eur)
    if vp_after_dist <= Decimal('0'):
        return None
    cap = max(Decimal('0'), ctx.subtract(fund_value_eoy_eur, fund_value_soy_eur))
    gross_vp_full = min(vp_after_dist, cap)
    if gross_vp_full <= Decimal('0'):
        return None
    gross_vp = ctx.multiply(gross_vp_full, partial_year_factor)
    if gross_vp <= Decimal('0'):
        return None

    fund_type = asset_obj.fund_type or InvestmentFundType.NONE
    tf_rate = get_teilfreistellung_rate_for_fund_type(fund_type)
    tf_amount = ctx.multiply(gross_vp, tf_rate)
    net_vp = ctx.subtract(gross_vp, tf_amount)

    TWO_PLACES = config.OUTPUT_PRECISION_AMOUNTS
    return VorabpauschaleData(
        asset_internal_id=asset_id,
        tax_year=target_year,
        fund_value_start_year_eur=fund_value_soy_eur.quantize(TWO_PLACES, context=ctx),
        fund_value_end_year_eur=fund_value_eoy_eur.quantize(TWO_PLACES, context=ctx),
        distributions_during_year_eur=distributions_eur.quantize(TWO_PLACES, context=ctx),
        base_return_rate=base_return_rate,
        basiszins=basiszins,
        calculated_base_return_eur=basisertrag.quantize(TWO_PLACES, context=ctx),
        gross_vorabpauschale_eur=gross_vp.quantize(TWO_PLACES, context=ctx),
        fund_type=fund_type,
        teilfreistellung_rate_applied=tf_rate,
        teilfreistellung_amount_eur=tf_amount.quantize(TWO_PLACES, context=ctx),
        net_taxable_vorabpauschale_eur=net_vp.quantize(TWO_PLACES, context=ctx),
        tax_reporting_category_gross=_get_vp_reporting_category(fund_type),
        partial_year_factor=partial_year_factor.quantize(Decimal("0.0001"), context=ctx),
        soy_nav_per_unit_eur=soy_nav_eur.quantize(TWO_PLACES, context=ctx),
        deemed_inflow_year=target_year + 1,
    )


def _vp_for_calendar_year(
    asset_resolver: AssetResolver,
    events: List[FinancialEvent],
    currency_converter: CurrencyConverter,
    target_year: int,
    run_tax_year: int,
    ctx: Context,
    fifo_ledgers: Optional[Dict[Tuple[str, uuid.UUID], FifoLedger]],
    results: List[VorabpauschaleData],
) -> None:
    """
    Compute the Vorabpauschale for calendar year `target_year` (deemed to flow on the
    first business day of target_year+1, §18 Abs. 3) for all funds held at the end of
    target_year, appending records to `results`.

    Current year (target_year == run_tax_year): end-of-year holdings/NAVs come from the
    eoy_* position fields; the year-start NAV from soy_market_price (held on 1 Jan) or the
    user-supplied vp_soy_nav_per_unit (acquired mid-year). Prior year
    (target_year == run_tax_year - 1): end-of-year holdings/NAVs come from the soy_* fields
    (which are the prior year's EoY = this run's SoY) and the year-start NAV from
    vp_prior_soy_nav_per_unit (prior-year SoY positions export, or interactive input).
    """
    # Basiszins via the law-as-data registry (AR2): None -> loud warning there.
    from src.tax_law.registry import basiszins_pct
    basiszins = basiszins_pct(target_year)
    if basiszins is None:
        return

    base_return_rate = ctx.multiply(basiszins, Decimal("0.01"))
    is_current = target_year == run_tax_year
    soy_conversion_date = date(target_year, 1, 2)
    eoy_conversion_date = date(target_year, 12, 31)

    # Distributions during target_year (events span all years; filter by date).
    distributions_by_asset: DefaultDict[uuid.UUID, Decimal] = defaultdict(lambda: ctx.create_decimal(Decimal('0')))
    for event in events:
        if isinstance(event, CashFlowEvent) and event.event_type == FinancialEventType.DISTRIBUTION_FUND:
            ev_date = parse_ibkr_date(event.event_date)
            if ev_date is None or ev_date.year != target_year:
                continue
            gross_eur = event.gross_amount_eur if event.gross_amount_eur is not None else Decimal('0')
            if gross_eur > Decimal('0'):
                distributions_by_asset[event.asset_internal_id] = ctx.add(
                    distributions_by_asset[event.asset_internal_id], gross_eur
                )

    for asset_id, asset_obj in asset_resolver.assets_by_internal_id.items():
        if not isinstance(asset_obj, InvestmentFund):
            continue

        if is_current:
            units = asset_obj.eoy_quantity
            if units is None or units <= Decimal('0'):
                continue
            if asset_obj.soy_quantity is not None and asset_obj.soy_quantity > Decimal('0'):
                soy_nav_foreign = asset_obj.soy_market_price
                soy_currency = asset_obj.soy_mark_price_currency or asset_obj.currency
            elif asset_obj.vp_soy_nav_per_unit is not None:
                soy_nav_foreign = asset_obj.vp_soy_nav_per_unit
                soy_currency = asset_obj.vp_soy_nav_currency or asset_obj.currency
            else:
                logger.debug(f"Fund {asset_obj.description}: no {target_year} start-of-year NAV; skipping its VP.")
                continue
            eoy_nav_foreign = asset_obj.eoy_market_price
            eoy_currency = asset_obj.eoy_mark_price_currency or asset_obj.currency
            if eoy_nav_foreign is None and asset_obj.eoy_position_value is not None:
                eoy_nav_foreign = ctx.divide(asset_obj.eoy_position_value, units)
            acquisition_month = asset_obj.vp_acquisition_month
            use_ledger = True
        else:
            # Prior year: held at end of target_year == held at this run's SoY.
            units = asset_obj.soy_quantity
            if units is None or units <= Decimal('0'):
                continue
            if asset_obj.vp_prior_soy_nav_per_unit is None:
                logger.debug(f"Fund {asset_obj.description}: no {target_year} (prior-year) start-of-year NAV; skipping its VP.")
                continue
            soy_nav_foreign = asset_obj.vp_prior_soy_nav_per_unit
            soy_currency = asset_obj.vp_prior_soy_nav_currency or asset_obj.currency
            eoy_nav_foreign = asset_obj.soy_market_price
            eoy_currency = asset_obj.soy_mark_price_currency or asset_obj.currency
            if eoy_nav_foreign is None and asset_obj.soy_position_value is not None:
                eoy_nav_foreign = ctx.divide(asset_obj.soy_position_value, units)
            acquisition_month = asset_obj.vp_prior_acquisition_month
            use_ledger = False

        if soy_nav_foreign is None or soy_currency is None or eoy_nav_foreign is None or eoy_currency is None:
            logger.debug(f"Fund {asset_obj.description}: missing NAV/currency for {target_year}; skipping its VP.")
            continue

        soy_nav_eur = currency_converter.convert_to_eur(soy_nav_foreign, soy_currency, soy_conversion_date)
        eoy_nav_eur = currency_converter.convert_to_eur(eoy_nav_foreign, eoy_currency, eoy_conversion_date)
        if soy_nav_eur is None or eoy_nav_eur is None:
            logger.warning(f"Fund {asset_obj.description}: failed EUR conversion for {target_year}; skipping its VP.")
            continue

        fund_value_soy_eur = ctx.multiply(soy_nav_eur, units)
        fund_value_eoy_eur = ctx.multiply(eoy_nav_eur, units)
        distributions_eur = distributions_by_asset.get(asset_id, Decimal('0'))
        partial_year_factor = _vp_partial_year_factor(
            asset_obj, fifo_ledgers, target_year, ctx, acquisition_month, use_ledger
        )

        vp_data = _build_fund_vp_record(
            asset_obj, asset_id, target_year, basiszins, base_return_rate,
            fund_value_soy_eur, fund_value_eoy_eur, distributions_eur,
            partial_year_factor, soy_nav_eur, ctx,
        )
        if vp_data is None:
            continue
        results.append(vp_data)
        logger.info(
            f"Fund {asset_obj.description}: VP({target_year}) gross={vp_data.gross_vorabpauschale_eur} "
            f"(factor={vp_data.partial_year_factor}, deemed inflow {vp_data.deemed_inflow_year}), "
            f"net={vp_data.net_taxable_vorabpauschale_eur}"
        )


def _calculate_vorabpauschale(
    asset_resolver: AssetResolver,
    current_year_events: List[FinancialEvent],
    currency_converter: CurrencyConverter,
    tax_year: int,
    ctx: Context,
    fifo_ledgers: Optional[Dict[Tuple[str, uuid.UUID], FifoLedger]] = None,
    all_financial_events: Optional[List[FinancialEvent]] = None,
) -> List[VorabpauschaleData]:
    """
    Calculate Vorabpauschale (§18 InvStG) for the current calendar year (deemed to flow
    next year — a preview of the X+1 return) and for the prior calendar year (deemed to
    flow this year — what belongs on the X return's KAP-INV lines). Each record carries
    deemed_inflow_year = its calendar year + 1; downstream selects by deemed_inflow_year.
    """
    results: List[VorabpauschaleData] = []

    # Current calendar year X (deemed inflow X+1; preview of next year's return).
    _vp_for_calendar_year(
        asset_resolver, current_year_events, currency_converter,
        tax_year, tax_year, ctx, fifo_ledgers, results,
    )

    # Prior calendar year X-1 (deemed inflow X; feeds this year's return lines).
    # No availability guard needed: _vp_for_calendar_year returns early (loudly,
    # via the AR2 registry) when the prior year has no published Basiszins.
    prior_year = tax_year - 1
    prior_events = all_financial_events if all_financial_events is not None else current_year_events
    _vp_for_calendar_year(
        asset_resolver, prior_events, currency_converter,
        prior_year, tax_year, ctx, fifo_ledgers, results,
    )

    return results


def _create_excess_dividend_event(original_event, excess_amount, asset_object, current_year_events):
    """Create a new DIVIDEND_CASH event for excess capital repayment amount.
    
    Args:
        original_event: The original CAPITAL_REPAYMENT event
        excess_amount: The excess amount that becomes taxable dividend
        asset_object: The asset for which the dividend is being created
        current_year_events: The current year events list to add the new event to
    """
    from src.domain.events import CashFlowEvent
    from src.domain.enums import FinancialEventType
    
    # Create new DIVIDEND_CASH event for excess amount
    excess_dividend_event = CashFlowEvent(
        asset_internal_id=asset_object.internal_asset_id,
        event_date=original_event.event_date,
        event_type=FinancialEventType.DIVIDEND_CASH,
        gross_amount_foreign_currency=excess_amount,
        local_currency=original_event.local_currency,
        source_country_code=getattr(original_event, 'source_country_code', None),
        ibkr_transaction_id=f"{original_event.ibkr_transaction_id}_EXCESS",
        ibkr_activity_description=f"{original_event.ibkr_activity_description} [EXCESS TAXABLE DIVIDEND]",
        ibkr_notes_codes=getattr(original_event, 'ibkr_notes_codes', None)
    )
    
    # Set the EUR amount 
    excess_dividend_event.gross_amount_eur = excess_amount
    excess_dividend_event.event_id = uuid.uuid4()
    
    # Add to the current year events list for processing
    current_year_events.append(excess_dividend_event)
    
    logger.info(f"Created excess dividend event {excess_dividend_event.event_id} for {excess_amount} EUR from capital repayment excess")

    return excess_dividend_event


def _ensure_currency_ledger_exists(
    currency_code: str,
    asset_resolver: AssetResolver,
    currency_fifo_ledgers: Dict[Any, 'FifoLedger'],
    fifo_ledgers: Dict[Any, 'FifoLedger'],
    currency_converter: CurrencyConverter,
    exchange_rate_provider: ECBExchangeRateProvider,
    internal_calculation_precision: int,
    decimal_rounding_mode: str,
    context_label: str = "",
    account: str = DEFAULT_ACCOUNT,
) -> None:
    """
    Ensure a CashBalance asset and a per-(account, currency) FIFO ledger exist.
    Creates both on-the-fly if they don't exist yet, so event processing is robust against
    any CSV/event ordering.
    """
    if currency_code.upper() == "EUR":
        return

    asset = asset_resolver.get_cash_balance_asset(currency_code.upper())
    if asset is None:
        asset = asset_resolver.get_or_create_asset(
            raw_isin=None, raw_conid=None, raw_symbol=currency_code.upper(),
            raw_currency=currency_code.upper(), raw_ibkr_asset_class="CASH",
            raw_description=f"Cash Balance {currency_code.upper()}",
            description_source_type="on_the_fly"
        )
    if asset is None:
        return

    key = (account, asset.internal_asset_id)
    if key not in currency_fifo_ledgers:
        new_ledger = FifoLedger(
            asset_internal_id=asset.internal_asset_id,
            asset_category=AssetCategory.CASH_BALANCE,
            asset_multiplier_from_asset=None,
            currency_converter=currency_converter,
            exchange_rate_provider=exchange_rate_provider,
            internal_working_precision=internal_calculation_precision,
            decimal_rounding_mode=decimal_rounding_mode,
        )
        currency_fifo_ledgers[key] = new_ledger
        fifo_ledgers[key] = new_ledger
        logger.info(f"{context_label}: Created currency ledger for {currency_code} acct {account}")


def _process_cashflow_currency_impact(
    event: FinancialEvent,
    asset_resolver: AssetResolver,
    currency_fifo_ledgers: Dict[uuid.UUID, 'FifoLedger'],
    currency_processor: 'CurrencyConversionProcessor',
    fifo_ledgers: Optional[Dict[uuid.UUID, 'FifoLedger']] = None,
    currency_converter: Optional[CurrencyConverter] = None,
    exchange_rate_provider: Optional[ECBExchangeRateProvider] = None,
    internal_calculation_precision: int = 28,
    decimal_rounding_mode: str = "ROUND_HALF_EVEN",
) -> List[RealizedGainLoss]:
    """
    Phase 5c: Handle implicit currency acquisition/consumption from cash flows.

    Income events (dividends, interest, distributions) in foreign currency:
      - You receive foreign currency → create new FIFO lot
      - If short lots exist, cover them first (realizes FX gain/loss)

    Expense events (WHT, fees, Stückzinsen paid) in foreign currency:
      - You pay foreign currency → consume from FIFO ledger (realizes FX gain/loss)
      - If insufficient balance, opens short currency position

    Returns:
        List of RealizedGainLoss records for any FX gains/losses
    """
    results: List[RealizedGainLoss] = []

    # Determine currency from the event
    cash_currency = event.local_currency
    if not cash_currency or cash_currency.upper() == "EUR":
        return results

    # Get amounts
    foreign_amount = event.gross_amount_foreign_currency
    eur_amount = event.gross_amount_eur

    if foreign_amount is None or eur_amount is None:
        return results

    # Ensure positive amounts for FIFO operations
    foreign_amount = foreign_amount.copy_abs()
    eur_amount = eur_amount.copy_abs()

    if foreign_amount <= Decimal("0") or eur_amount <= Decimal("0"):
        return results

    # Get currency asset and ledger
    currency_asset = asset_resolver.get_cash_balance_asset(cash_currency.upper())
    if not currency_asset:
        # Create CashBalance asset on-the-fly (e.g., first-ever USD dividend with no prior balance)
        currency_asset = asset_resolver.get_or_create_asset(
            raw_isin=None, raw_conid=None, raw_symbol=cash_currency.upper(),
            raw_currency=cash_currency.upper(), raw_ibkr_asset_class="CASH",
            raw_description=f"Cash Balance {cash_currency.upper()}",
            description_source_type="cashflow_implicit"
        )
        if not currency_asset:
            logger.debug(f"Cashflow {event.event_id}: Could not create CashBalance asset for {cash_currency}")
            return results

    acct = account_key(event.account_id)
    ckey = (acct, currency_asset.internal_asset_id)
    currency_ledger = currency_fifo_ledgers.get(ckey)
    if not currency_ledger:
        # Create ledger on-the-fly (no prior balance, first cash flow in this currency/account)
        ledger_kwargs = dict(
            asset_internal_id=currency_asset.internal_asset_id,
            asset_category=AssetCategory.CASH_BALANCE,
            asset_multiplier_from_asset=None,
            currency_converter=currency_converter,
            exchange_rate_provider=exchange_rate_provider,
            internal_working_precision=internal_calculation_precision,
            decimal_rounding_mode=decimal_rounding_mode,
        )
        currency_ledger = FifoLedger(**ledger_kwargs)
        currency_fifo_ledgers[ckey] = currency_ledger
        if fifo_ledgers is not None:
            fifo_ledgers[ckey] = currency_ledger
        logger.info(f"Cashflow {event.event_id}: Created currency ledger for {cash_currency} acct {acct} (first cash flow)")

    eur_per_unit = eur_amount / foreign_amount

    # Classify: income (creates lots) vs expense (consumes lots)
    if event.event_type in [
        FinancialEventType.DIVIDEND_CASH,
        FinancialEventType.DISTRIBUTION_FUND,
        FinancialEventType.INTEREST_RECEIVED,
        FinancialEventType.CAPITAL_REPAYMENT,
    ]:
        # INCOME: You receive foreign currency
        quantity_to_acquire = foreign_amount

        # Cover short positions first if they exist
        available_short_qty = sum(lot.quantity_shorted for lot in currency_ledger.short_lots)
        if available_short_qty > Decimal("0"):
            qty_to_cover = min(quantity_to_acquire, available_short_qty)
            short_cover_results = currency_processor.cover_short_lots_for_cashflow_income(
                currency_ledger, currency_asset.internal_asset_id,
                event.event_date, event.event_id, event.ibkr_transaction_id,
                qty_to_cover, eur_per_unit
            )
            results.extend(short_cover_results)
            if short_cover_results:
                total_fx_gl = sum(rgl.gross_gain_loss_eur for rgl in short_cover_results)
                logger.info(
                    f"Cashflow {event.event_id} ({event.event_type.name}): Covered {qty_to_cover:.2f} "
                    f"{cash_currency} short with income. FX gain/loss: {total_fx_gl:.2f} EUR"
                )
            quantity_to_acquire -= qty_to_cover

        # Create new lot for remaining
        if quantity_to_acquire > Decimal("1e-10"):
            currency_processor.create_long_lot_for_cashflow_income(
                currency_ledger, event.event_date, event.ibkr_transaction_id,
                quantity_to_acquire, eur_per_unit
            )
            logger.debug(
                f"Cashflow {event.event_id} ({event.event_type.name}): Created {cash_currency} lot: "
                f"{quantity_to_acquire:.2f} @ {eur_per_unit:.6f} EUR per unit"
            )

    elif event.event_type in [
        FinancialEventType.WITHHOLDING_TAX,
        FinancialEventType.FEE_TRANSACTION,
        FinancialEventType.INTEREST_PAID_STUECKZINSEN,
    ]:
        # EXPENSE: You pay foreign currency
        quantity_to_consume = foreign_amount

        # Consume from long lots
        available_long_qty = sum(lot.quantity for lot in currency_ledger.lots)
        if available_long_qty > Decimal("0"):
            qty_to_consume_from_longs = min(quantity_to_consume, available_long_qty)
            long_results = currency_processor.realize_long_lots_for_cashflow_expense(
                currency_ledger, currency_asset.internal_asset_id,
                event.event_date, event.event_id, event.ibkr_transaction_id,
                qty_to_consume_from_longs, eur_per_unit
            )
            results.extend(long_results)
            if long_results:
                total_fx_gl = sum(rgl.gross_gain_loss_eur for rgl in long_results)
                logger.info(
                    f"Cashflow {event.event_id} ({event.event_type.name}): Consumed {qty_to_consume_from_longs:.2f} "
                    f"{cash_currency} for expense. FX gain/loss: {total_fx_gl:.2f} EUR"
                )
            quantity_to_consume -= qty_to_consume_from_longs

        # Open short if insufficient
        if quantity_to_consume > Decimal("1e-10"):
            logger.info(
                f"Cashflow {event.event_id} ({event.event_type.name}): Opening implicit SHORT "
                f"{cash_currency} position: {quantity_to_consume:.2f} (expense exceeds currency balance)"
            )
            currency_processor.open_short_position_for_cashflow_expense(
                currency_ledger, event.event_date, event.ibkr_transaction_id,
                quantity_to_consume, eur_per_unit
            )

    return results


def _collect_historical_currency_event(
    event: FinancialEvent,
    historical_currency_events: DefaultDict[Any, List[FinancialEvent]]
) -> None:
    """
    Collect a historical event into per-(account, currency) lists for FIFO replay.

    Captures ALL events that affect foreign currency cash balances:
    - Trades (buy/sell securities in foreign currency, plus commissions)
    - Currency conversions (explicit FX trades)
    - Cash flows (dividends, interest, distributions)
    - Expenses (WHT, fees, Stueckzinsen)
    """
    acct = account_key(event.account_id)
    if isinstance(event, CurrencyConversionEvent):
        if event.from_currency.upper() != "EUR":
            historical_currency_events[(acct, event.from_currency.upper())].append(event)
        if event.to_currency.upper() != "EUR":
            historical_currency_events[(acct, event.to_currency.upper())].append(event)
        return

    if isinstance(event, TradeEvent):
        ccy = (event.local_currency or "").upper()
        if ccy and ccy != "EUR":
            historical_currency_events[(acct, ccy)].append(event)
        return

    # Cash merger: acquisition proceeds create foreign currency cash
    if isinstance(event, CorpActionMergerCash):
        ccy = (event.local_currency or "").upper()
        if ccy and ccy != "EUR" and event.gross_amount_foreign_currency:
            historical_currency_events[(acct, ccy)].append(event)
        return

    # Cash flow events: dividends, interest, WHT, fees, etc.
    ccy = getattr(event, 'local_currency', None)
    if ccy:
        ccy = ccy.upper()
        if ccy != "EUR" and event.event_type in [
            FinancialEventType.DIVIDEND_CASH,
            FinancialEventType.DISTRIBUTION_FUND,
            FinancialEventType.INTEREST_RECEIVED,
            FinancialEventType.INTEREST_PAID_STUECKZINSEN,
            FinancialEventType.WITHHOLDING_TAX,
            FinancialEventType.FEE_TRANSACTION,
            FinancialEventType.CAPITAL_REPAYMENT,
        ]:
            historical_currency_events[(acct, ccy)].append(event)


def _apply_historical_currency_event(
    event: FinancialEvent,
    ledger: 'FifoLedger',
    currency_code: str,
    currency_converter: CurrencyConverter,
    ctx: Context,
) -> int:
    """Apply ONE historical event's currency impact to a currency ledger —
    the per-event unit the unified replayer streams (AR5). Mutates lot state
    only (no current-year RGLs). Returns 1 if the event affected the ledger.

    Handles every event type that moves currency:
    - CurrencyConversionEvent: explicit FX trades (only the side matching our currency)
    - TradeEvent: security buys consume currency, sells produce currency, commissions consume
    - CorpActionMergerCash: cash proceeds create a currency lot
    - Income cashflows: dividends, interest, distributions create currency lots
    - Expense cashflows: WHT, fees, Stueckzinsen consume currency lots
    """
    replayed = 0
    # Single-iteration loop: the body is kept VERBATIM from the previous batch
    # loop (its `continue` statements mean "this event does not affect this
    # currency" and skip to the return).
    for _ in (0,):
        try:
            if isinstance(event, CurrencyConversionEvent):
                # Handle only the side affecting our currency
                if event.from_currency.upper() == currency_code:
                    # Selling this currency
                    eur_value = _get_historical_eur_value(
                        event.to_amount, event.to_currency, event.event_date,
                        currency_converter
                    )
                    if eur_value and event.from_amount > Decimal("0"):
                        eur_per_unit = ctx.divide(eur_value, event.from_amount)
                        _consume_lots_historical(ledger, event.from_amount, eur_per_unit, event.event_date, ctx)
                        replayed += 1

                if event.to_currency.upper() == currency_code:
                    # Buying this currency
                    eur_value = _get_historical_eur_value(
                        event.from_amount, event.from_currency, event.event_date,
                        currency_converter
                    )
                    if eur_value and event.to_amount > Decimal("0"):
                        eur_per_unit = ctx.divide(eur_value, event.to_amount)
                        _create_lot_historical(
                            ledger, event.to_amount, eur_per_unit, event.event_date,
                            event.ibkr_transaction_id, ctx
                        )
                        replayed += 1

            elif isinstance(event, CorpActionMergerCash):
                # Cash merger: acquisition proceeds create currency lot
                ccy = (event.local_currency or "").upper()
                if ccy != currency_code:
                    continue

                foreign_amount = event.gross_amount_foreign_currency
                eur_amount = event.gross_amount_eur

                if foreign_amount and eur_amount and foreign_amount > Decimal("0") and eur_amount > Decimal("0"):
                    eur_per_unit = ctx.divide(eur_amount, foreign_amount)
                    _create_lot_historical(
                        ledger, foreign_amount, eur_per_unit, event.event_date,
                        event.ibkr_transaction_id, ctx
                    )
                    replayed += 1

            elif isinstance(event, TradeEvent):
                trade_ccy = (event.local_currency or "").upper()
                if trade_ccy != currency_code:
                    continue

                foreign_amount = event.gross_amount_foreign_currency
                eur_amount = event.gross_amount_eur

                if foreign_amount and eur_amount and foreign_amount > Decimal("0") and eur_amount > Decimal("0"):
                    eur_per_unit = ctx.divide(eur_amount, foreign_amount)

                    if event.event_type in [FinancialEventType.TRADE_BUY_LONG, FinancialEventType.TRADE_BUY_SHORT_COVER]:
                        # Buying security = spending currency
                        _consume_lots_historical(ledger, foreign_amount, eur_per_unit, event.event_date, ctx)
                        replayed += 1
                    elif event.event_type in [FinancialEventType.TRADE_SELL_LONG, FinancialEventType.TRADE_SELL_SHORT_OPEN]:
                        # Selling security = receiving currency
                        _create_lot_historical(
                            ledger, foreign_amount, eur_per_unit, event.event_date,
                            event.ibkr_transaction_id, ctx
                        )
                        replayed += 1
                elif foreign_amount is not None and foreign_amount < Decimal("0"):
                    logger.warning(
                        f"Historical currency replay: Trade {event.event_id} has negative "
                        f"gross_amount_foreign_currency ({foreign_amount}). Skipping currency impact."
                    )

                # Commission: negative = fee (outflow), positive = rebate (inflow)
                comm = event.commission_foreign_currency
                comm_ccy = (event.commission_currency or "").upper()
                comm_eur = event.commission_eur
                if comm and comm_ccy == currency_code and comm_eur:
                    comm_abs = comm.copy_abs()
                    comm_eur_abs = comm_eur.copy_abs()
                    if comm_abs > Decimal("0") and comm_eur_abs > Decimal("0"):
                        comm_eur_per_unit = ctx.divide(comm_eur_abs, comm_abs)
                        if comm > Decimal("0"):
                            # Rebate: creates currency inflow
                            _create_lot_historical(ledger, comm_abs, comm_eur_per_unit, event.event_date, event.ibkr_transaction_id, ctx)
                        else:
                            # Normal fee: consumes currency
                            _consume_lots_historical(ledger, comm_abs, comm_eur_per_unit, event.event_date, ctx)

            else:
                # Cash flow event
                ccy = (getattr(event, 'local_currency', None) or "").upper()
                if ccy != currency_code:
                    continue

                foreign_amount = getattr(event, 'gross_amount_foreign_currency', None)
                eur_amount = getattr(event, 'gross_amount_eur', None)

                if foreign_amount is None or eur_amount is None:
                    continue

                if foreign_amount < Decimal("0"):
                    logger.warning(
                        f"Historical currency replay: CashFlow {event.event_id} has negative "
                        f"gross_amount_foreign_currency ({foreign_amount}). Using absolute value."
                    )

                fa_abs = foreign_amount.copy_abs()
                ea_abs = eur_amount.copy_abs()

                if fa_abs <= Decimal("0") or ea_abs <= Decimal("0"):
                    continue

                eur_per_unit = ctx.divide(ea_abs, fa_abs)

                if event.event_type in [
                    FinancialEventType.DIVIDEND_CASH, FinancialEventType.DISTRIBUTION_FUND,
                    FinancialEventType.INTEREST_RECEIVED, FinancialEventType.CAPITAL_REPAYMENT,
                ]:
                    # Income: receive currency
                    _create_lot_historical(
                        ledger, fa_abs, eur_per_unit, event.event_date,
                        getattr(event, 'ibkr_transaction_id', None), ctx
                    )
                    replayed += 1
                elif event.event_type in [
                    FinancialEventType.WITHHOLDING_TAX, FinancialEventType.FEE_TRANSACTION,
                    FinancialEventType.INTEREST_PAID_STUECKZINSEN,
                ]:
                    # Expense: consume currency
                    _consume_lots_historical(ledger, fa_abs, eur_per_unit, event.event_date, ctx)
                    replayed += 1

        except Exception as e:
            logger.debug(f"Historical currency replay: skipped event {event.event_id}: {e}")

    return replayed


def _replay_historical_currency_events(
    events: List[FinancialEvent],
    ledger: 'FifoLedger',
    currency_code: str,
    currency_converter: CurrencyConverter,
    ctx: Context,
) -> int:
    """Batch wrapper over _apply_historical_currency_event (kept for direct
    callers/tests; the engine streams per event). Returns events replayed."""
    return sum(
        _apply_historical_currency_event(event, ledger, currency_code, currency_converter, ctx)
        for event in events
    )


def _get_historical_eur_value(
    amount: Decimal, currency: str, event_date: str,
    currency_converter: CurrencyConverter
) -> Optional[Decimal]:
    """Convert amount to EUR for historical replay. Returns None if conversion fails."""
    if currency.upper() == "EUR":
        return amount
    date_obj = parse_ibkr_date(event_date)
    if date_obj is None:
        return None
    return currency_converter.convert_to_eur(amount, currency, date_obj)


def _consume_lots_historical(
    ledger: 'FifoLedger', quantity: Decimal, eur_per_unit: Decimal,
    event_date: str, ctx: Context
) -> None:
    """Consume currency lots during historical replay (no RGL generation)."""
    from .fifo_manager import ShortFifoLot

    remaining = quantity
    lots_to_remove: List[int] = []

    for i, lot in enumerate(ledger.lots):
        if remaining <= Decimal("0"):
            break
        qty_from_lot = min(lot.quantity, remaining)
        if lot.quantity <= remaining:
            lots_to_remove.append(i)
        else:
            lot.quantity = ctx.subtract(lot.quantity, qty_from_lot)
            lot.total_cost_basis_eur = ctx.multiply(lot.quantity, lot.unit_cost_basis_eur)
        remaining = ctx.subtract(remaining, qty_from_lot)

    for i in reversed(lots_to_remove):
        del ledger.lots[i]

    # If more consumed than available, open short position
    if remaining > Decimal("1e-10"):
        total_proceeds = ctx.multiply(remaining, eur_per_unit)
        short_lot = ShortFifoLot(
            opening_date=event_date,
            quantity_shorted=remaining,
            unit_sale_proceeds_eur=eur_per_unit,
            total_sale_proceeds_eur=total_proceeds,
            source_transaction_id=f"HIST_{event_date}"
        )
        ledger.short_lots.append(short_lot)
        ledger.short_lots.sort(key=lambda l: l.opening_date)


def _create_lot_historical(
    ledger: 'FifoLedger', quantity: Decimal, eur_per_unit: Decimal,
    event_date: str, transaction_id: Optional[str], ctx: Context
) -> None:
    """Create currency lot during historical replay. Covers short lots first."""
    from .fifo_manager import FifoLot

    remaining = quantity
    lots_to_remove: List[int] = []

    # Cover short lots first
    for i, short_lot in enumerate(ledger.short_lots):
        if remaining <= Decimal("0"):
            break
        qty = min(short_lot.quantity_shorted, remaining)
        if short_lot.quantity_shorted <= remaining:
            lots_to_remove.append(i)
        else:
            short_lot.quantity_shorted = ctx.subtract(short_lot.quantity_shorted, qty)
            short_lot.total_sale_proceeds_eur = ctx.multiply(
                short_lot.quantity_shorted, short_lot.unit_sale_proceeds_eur
            )
        remaining = ctx.subtract(remaining, qty)

    for i in reversed(lots_to_remove):
        del ledger.short_lots[i]

    # Create long lot for remaining
    if remaining > Decimal("1e-10"):
        total_cost = ctx.multiply(remaining, eur_per_unit)
        lot = FifoLot(
            acquisition_date=event_date,
            quantity=remaining,
            unit_cost_basis_eur=eur_per_unit,
            total_cost_basis_eur=total_cost,
            source_transaction_id=f"HIST_{transaction_id or event_date}"
        )
        ledger.lots.append(lot)
        ledger.lots.sort(key=lambda l: l.acquisition_date)


def _reconcile_currency_soy(
    ledger: 'FifoLedger', asset: CashBalance, tax_year: int,
    exchange_rate_provider, ctx: Context
) -> None:
    """
    Reconcile currency FIFO ledger against SOY reported balance.

    When used as SOY fallback (no historical events), creates initial lots
    using the provided cost basis from CashBalance asset if available,
    otherwise falls back to ECB rate at SOY date.

    Supports both positive (long) and negative (short) SOY positions.
    """
    from .fifo_manager import FifoLot, ShortFifoLot
    from datetime import date as date_type

    reported_soy = asset.soy_quantity
    if reported_soy is None or reported_soy == Decimal("0"):
        return

    long_qty = sum(lot.quantity for lot in ledger.lots)
    short_qty = sum(lot.quantity_shorted for lot in ledger.short_lots)
    fifo_qty = long_qty - short_qty

    diff = reported_soy - fifo_qty

    if abs(diff) <= Decimal("0.01"):
        return

    fallback_date = date_type(tax_year - 1, 12, 31)
    fallback_date_str = fallback_date.isoformat()

    ecb_rate = exchange_rate_provider.get_rate(fallback_date, asset.currency)
    if ecb_rate is None or ecb_rate == Decimal("0"):
        raise ValueError(
            f"Currency {asset.currency}: No ECB rate available for SOY reconciliation date {fallback_date_str}. "
            f"Cannot reconcile currency FIFO ledger without a valid exchange rate. "
            f"Ensure ECB rate cache covers this date."
        )

    # Default EUR per unit from ECB rate
    default_unit_eur = ctx.divide(Decimal("1"), ecb_rate)

    if diff > Decimal("0"):
        # FIFO < SOY: need more currency, create adjustment long lot
        # Use provided cost basis if available and this is the full SOY amount
        if (asset.soy_cost_basis_amount and asset.soy_cost_basis_amount > Decimal("0")
                and abs(diff - reported_soy) <= Decimal("0.01")):
            # Full SOY amount missing - use the provided total cost basis
            total_cost = asset.soy_cost_basis_amount
            unit_eur = ctx.divide(total_cost, diff)
            logger.debug(f"Currency {asset.currency}: Using provided SOY cost basis: {total_cost:.2f} EUR")
        else:
            unit_eur = default_unit_eur
            total_cost = ctx.multiply(diff, unit_eur)

        lot = FifoLot(
            acquisition_date=fallback_date_str,
            quantity=diff,
            unit_cost_basis_eur=unit_eur,
            total_cost_basis_eur=total_cost,
            source_transaction_id=f"SOY_RECONCILIATION_{asset.currency}"
        )
        ledger.lots.append(lot)
        ledger.lots.sort(key=lambda l: l.acquisition_date)
        logger.info(f"Currency {asset.currency}: SOY reconciliation +{diff:.2f} "
                    f"(FIFO={fifo_qty:.2f}, SOY={reported_soy:.2f})")
    else:
        # FIFO > SOY: too much currency, consume excess from long lots
        excess = diff.copy_abs()

        # For negative SOY (short position) with no historical lots at all, create full SOY short lot
        if reported_soy < Decimal("0") and long_qty <= Decimal("0.01") and short_qty <= Decimal("0.01"):
            # Pure short position from SOY — no historical lots exist
            soy_abs = reported_soy.copy_abs()
            if hasattr(asset, 'soy_short_proceeds_eur') and asset.soy_short_proceeds_eur:
                total_proceeds = asset.soy_short_proceeds_eur
                unit_proceeds = ctx.divide(total_proceeds, soy_abs)
            else:
                unit_proceeds = default_unit_eur
                total_proceeds = ctx.multiply(soy_abs, unit_proceeds)

            short_lot = ShortFifoLot(
                opening_date=fallback_date_str,
                quantity_shorted=soy_abs,
                unit_sale_proceeds_eur=unit_proceeds,
                total_sale_proceeds_eur=total_proceeds,
                source_transaction_id=f"SOY_RECONCILIATION_SHORT_{asset.currency}"
            )
            ledger.short_lots.append(short_lot)
            ledger.short_lots.sort(key=lambda l: l.opening_date)
            logger.info(f"Currency {asset.currency}: SOY reconciliation SHORT {soy_abs:.2f} "
                        f"(FIFO={fifo_qty:.2f}, SOY={reported_soy:.2f})")
            return

        remaining = excess
        lots_to_remove: List[int] = []

        for i, lot in enumerate(ledger.lots):
            if remaining <= Decimal("0"):
                break
            qty = min(lot.quantity, remaining)
            if lot.quantity <= remaining:
                lots_to_remove.append(i)
            else:
                lot.quantity = ctx.subtract(lot.quantity, qty)
                lot.total_cost_basis_eur = ctx.multiply(lot.quantity, lot.unit_cost_basis_eur)
            remaining = ctx.subtract(remaining, qty)

        for i in reversed(lots_to_remove):
            del ledger.lots[i]

        # If still excess after consuming all longs, create short lot
        if remaining > Decimal("1e-10"):
            total_proceeds = ctx.multiply(remaining, default_unit_eur)
            short_lot = ShortFifoLot(
                opening_date=fallback_date_str,
                quantity_shorted=remaining,
                unit_sale_proceeds_eur=default_unit_eur,
                total_sale_proceeds_eur=total_proceeds,
                source_transaction_id=f"SOY_RECONCILIATION_SHORT_{asset.currency}"
            )
            ledger.short_lots.append(short_lot)
            ledger.short_lots.sort(key=lambda l: l.opening_date)

        logger.info(f"Currency {asset.currency}: SOY reconciliation -{excess:.2f} "
                    f"(FIFO={fifo_qty:.2f}, SOY={reported_soy:.2f})")
