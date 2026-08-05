# src/engine/calculation_engine.py
import logging
from typing import List, Tuple, Dict, DefaultDict, Optional, Any
import uuid
from decimal import Decimal, getcontext, Context
from collections import defaultdict
from datetime import datetime, date

from src.utils.account_utils import account_key, DEFAULT_ACCOUNT
from src.processing.data_gaps import DataGapCollector, DataGapError, GapSeverity
from src.domain.events import (
    FinancialEvent, TradeEvent, CorpActionSplitForward, CorpActionMergerCash,
    CorpActionStockDividend, CorpActionMergerStock, CorporateActionEvent,
    CorpActionExpireDividendRights, OptionExerciseEvent, OptionAssignmentEvent,
    OptionExpirationWorthlessEvent, OptionCashSettlementEvent,
    OptionLifecycleEvent, CashFlowEvent, FeeEvent,
    WithholdingTaxEvent, CurrencyConversionEvent
)
from src.domain.assets import Asset, Stock, Bond, AssetCategory, Option, InvestmentFund, CashBalance
from src.identification.asset_resolver import AssetResolver
from src.domain.results import RealizedGainLoss, VorabpauschaleData
from src.domain.enums import FinancialEventType, InvestmentFundType 
from src.utils.sorting_utils import get_event_sort_key
from src.domain.exceptions import ProcessingError
from src.utils.type_utils import parse_ibkr_date

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

def _replay_historical_merger(merger_event, fifo_ledgers) -> None:
    """Apply ONE historical stock-for-stock merger — the per-event unit the
    unified replayer streams in the MERGERS phase. Tax-neutral under §20
    Abs. 4a Satz 1-2 EStG (the new shares step into the tax position of the
    old ones), so the lots transfer with their acquisition date and cost
    basis: reference/tax-law/estg-20-kapitalvermoegen.md, "Abs. 4a"."""
    source_ledger = fifo_ledgers.get((DEFAULT_ACCOUNT, merger_event.asset_internal_id))
    target_ledger = fifo_ledgers.get((DEFAULT_ACCOUNT, merger_event.new_asset_internal_id))

    if source_ledger is None:
        logger.warning(f"Historical merger {merger_event.event_id}: No source ledger for {merger_event.asset_internal_id}. Skipping.")
        return
    if target_ledger is None:
        logger.error(f"Historical merger {merger_event.event_id}: No target ledger for {merger_event.new_asset_internal_id}. Cannot transfer lots.")
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


def run_main_calculations(
    financial_events: List[FinancialEvent],
    asset_resolver: AssetResolver,
    currency_converter: CurrencyConverter,
    exchange_rate_provider: ECBExchangeRateProvider,
    tax_year: int,
    internal_calculation_precision: int, # Renamed from internal_working_precision
    decimal_rounding_mode: str,
    data_gap_collector: Optional["DataGapCollector"] = None,
    # Whether the PRECEDING year's position snapshots were supplied. The Vorabpauschale
    # declared in VZ `tax_year` is the one for calendar `tax_year - 1` (18 Abs. 3 InvStG), so
    # their absence is a gap rather than an empty portfolio. Defaults False so a caller that
    # has not been updated fails loudly instead of silently dropping deemed income.
    prior_year_positions_available: bool = False
) -> Tuple[List[RealizedGainLoss], List[VorabpauschaleData], List[FinancialEvent], int]: 
    """
    Runs the main calculation logic:
    1. Separates historical and current year events.
    2. Initializes FIFO ledgers based on SOY positions and historical trades.
    3. Processes current year events chronologically using dedicated processors.
    4. Performs EOY quantity validation. A securities mismatch is FATAL (PRD 2.4): every
       asset is checked, then the run raises DataGapError naming all of them. A currency
       (cash balance) divergence is recorded as a WARNING data gap and does not halt.
    5. Calculates the Vorabpauschale FOR calendar `tax_year - 1` (18 Abs. 3 InvStG).
    6. Returns calculated results (Realized G/L, Vorabpauschale), processed events, and EOY
       mismatch count. The count is retained in the signature and in ProcessingOutput as a
       backstop for the reporting layer, but on a successful return it is now always 0 —
       any other value would have raised.
    """
    logger.info(f"Starting main calculation engine for tax year {tax_year} with {len(financial_events)} events.")
    ctx = Context(prec=internal_calculation_precision, rounding=decimal_rounding_mode) # Renamed internal_working_precision

    realized_gains_losses: List[RealizedGainLoss] = []
    vorabpauschale_data_items: List[VorabpauschaleData] = []

    historical_events_by_asset: DefaultDict[uuid.UUID, List[FinancialEvent]] = defaultdict(list)
    historical_merger_events: List[CorpActionMergerStock] = []
    historical_currency_events: DefaultDict[str, List[FinancialEvent]] = defaultdict(list)
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

        if event_date_obj < tax_year_start_date_obj:
            if isinstance(event, CorpActionMergerStock):
                historical_merger_events.append(event)
            elif isinstance(event, (TradeEvent, CorpActionSplitForward, CorpActionStockDividend)):
                historical_events_by_asset[event.asset_internal_id].append(event)
            elif isinstance(event, CurrencyConversionEvent):
                # CurrencyConversionEvents need to be associated with the non-EUR currency's asset ID
                # (or both currencies for cross-currency trades like USD→GBP)
                from_is_non_eur = event.from_currency.upper() != "EUR"
                to_is_non_eur = event.to_currency.upper() != "EUR"

                if from_is_non_eur:
                    from_asset = asset_resolver.get_cash_balance_asset(event.from_currency)
                    if from_asset:
                        historical_events_by_asset[from_asset.internal_asset_id].append(event)

                if to_is_non_eur:
                    to_asset = asset_resolver.get_cash_balance_asset(event.to_currency)
                    if to_asset:
                        historical_events_by_asset[to_asset.internal_asset_id].append(event)
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
    # Separate dict for currency ledgers; same (account_key, asset_id) key shape.
    currency_fifo_ledgers: Dict[Tuple[str, uuid.UUID], FifoLedger] = {}

    # === Unified historical replay (AR5) ===
    # ONE ordered stream rebuilds all pre-tax-year ledger state — securities
    # AND currencies — under the documented phase contract (see engine/replay.py):
    # LEDGER_EVENTS (chronological) -> MERGERS (chronological) -> RECONCILE.
    from src.engine.replay import ReplayStream, Phase
    stream = ReplayStream()

    logger.info("Building unified historical replay stream (securities, mergers, currencies)...")
    for asset_id, asset_obj in asset_resolver.assets_by_internal_id.items():
        if asset_obj.asset_category != AssetCategory.CASH_BALANCE:
            asset_multiplier_val: Optional[Decimal] = None
            asset_fund_type: Optional[InvestmentFundType] = None

            if isinstance(asset_obj, Option):
                asset_multiplier_val = asset_obj.multiplier
            elif isinstance(asset_obj, InvestmentFund):
                asset_fund_type = asset_obj.fund_type

            ledger = FifoLedger(
                asset_internal_id=asset_id, asset_category=asset_obj.asset_category,
                asset_multiplier_from_asset=asset_multiplier_val,
                currency_converter=currency_converter, exchange_rate_provider=exchange_rate_provider,
                internal_working_precision=internal_calculation_precision,
                decimal_rounding_mode=decimal_rounding_mode,
                fund_type=asset_fund_type
            )

            # Key each event ONCE and carry the key into the stream. Computing it
            # again at stream.add() would repeat every warning get_event_sort_key
            # emits (e.g. a historical trade with no ibkr_transaction_id).
            sorted_hist_keys_and_events: List[Tuple[Any, FinancialEvent]] = []
            if asset_id in historical_events_by_asset:
                try:
                    sorted_hist_keys_and_events = sorted(
                        ((get_event_sort_key(e, asset_resolver), e)
                         for e in historical_events_by_asset[asset_id]),
                        key=lambda keyed: keyed[0],
                    )
                except ValueError as e:
                    logger.critical(f"Fatal error sorting historical events for asset {asset_obj.get_classification_key()} (ID: {asset_id}): {e}. Cannot guarantee deterministic order for FIFO init. Aborting.")
                    raise e

            ledger.begin_historical_simulation(asset_obj)
            ledger.announce_historical_simulation(asset_obj, len(sorted_hist_keys_and_events))
            for hist_key, hist_event in sorted_hist_keys_and_events:
                stream.add(
                    Phase.LEDGER_EVENTS, hist_key,
                    (lambda l=ledger, a=asset_obj, e=hist_event:
                        l.apply_historical_event(a, e, tax_year)),
                    label=f"sec:{asset_obj.get_classification_key()}",
                )

            fifo_ledgers[(DEFAULT_ACCOUNT, asset_id)] = ledger
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
                (lambda m=merger_event: _replay_historical_merger(m, fifo_ledgers)),
                label="merger",
            )
    else:
        logger.info("Pass 2: No historical stock mergers to replay.")

    # Reconcile phase: securities ledgers against SoY positions (after merger
    # lots are in place). Items are added for the SECURITIES ledgers existing
    # now — currency ledgers reconcile against cash balances separately below.
    logger.info("Pass 3: Reconciling ledgers with SoY positions...")
    def _reconcile_security_soy(ledger, asset_obj):
        try:
            ledger.reconcile_with_soy_position(asset_obj, tax_year)
        except ValueError as e:
            logger.critical(f"Fatal error reconciling SOY for asset {asset_obj.get_classification_key()} (ID: {asset_obj.internal_asset_id}): {e}. Aborting.")
            raise e
    for (ledger_account, asset_id), ledger in fifo_ledgers.items():
        asset_obj = asset_resolver.get_asset_by_id(asset_id)
        if asset_obj:
            stream.add(
                Phase.RECONCILE, (0,),
                (lambda l=ledger, a=asset_obj: _reconcile_security_soy(l, a)),
                label=f"reconcile-sec:{asset_obj.get_classification_key()}",
            )

    # Initialize currency FIFO ledgers with comprehensive historical replay
    logger.info("Initializing currency FIFO ledgers for foreign currency positions...")

    # Collect currencies that need FIFO ledgers (only from known CashBalance assets,
    # not from historical events alone - avoids creating spurious currency tracking
    # when no cash_balance CSV was provided)
    currencies_to_init: set = set()
    for asset_id, asset_obj in asset_resolver.assets_by_internal_id.items():
        if isinstance(asset_obj, CashBalance) and asset_obj.currency:
            ccy = asset_obj.currency.upper()
            if ccy != "EUR":
                currencies_to_init.add(ccy)

    currency_replay_counts: Dict[str, list] = {}
    for currency_code in sorted(currencies_to_init):
        # Ensure CashBalance asset and ledger exist (creation is unordered
        # setup, not stream work — the stream replays EVENTS).
        _ensure_currency_ledger_exists(
            currency_code, asset_resolver, currency_fifo_ledgers, fifo_ledgers,
            currency_converter, exchange_rate_provider,
            internal_calculation_precision, decimal_rounding_mode,
            f"Currency init {currency_code}"
        )

        currency_asset = asset_resolver.get_cash_balance_asset(currency_code)
        if not currency_asset:
            continue

        currency_ledger = currency_fifo_ledgers.get((DEFAULT_ACCOUNT, currency_asset.internal_asset_id))
        if not currency_ledger:
            continue

        # Stream every historical event with a currency impact; per-currency
        # relative order = get_event_sort_key (ties: insertion seq), exactly
        # the previous per-currency sorted replay. Events of different
        # currencies commute (one ledger each).
        hist_events = historical_currency_events.get(currency_code, [])
        if hist_events:
            currency_replay_counts[currency_code] = [0, len(hist_events)]

            def _apply_ccy_event(event, led=currency_ledger, ccy=currency_code):
                currency_replay_counts[ccy][0] += _apply_historical_currency_event(
                    event, led, ccy, currency_converter, ctx
                )

            for hist_event in hist_events:
                try:
                    hist_key = get_event_sort_key(hist_event, asset_resolver)
                except ValueError as e:
                    # Fatal, like the securities branch above and the merger branch
                    # between them: an event that cannot be placed in the chronology
                    # cannot be replayed, and the replay order fixes the EUR cost
                    # basis of every currency lot it touches. Unreachable as things
                    # stand -- the event separation loop at the top of this function
                    # already builds a sort key for every event and drops the ones
                    # that raise -- but the previous fallback was worse than dead: it
                    # sorted the event to (date.min, ()), which is ahead of every
                    # other item in the phase, not "insertion order" as its comment
                    # claimed.
                    logger.critical(f"Fatal error sorting historical currency event {hist_event.event_id} "
                                    f"for {currency_code}: {e}. Cannot guarantee deterministic order "
                                    f"for FIFO init. Aborting.")
                    raise
                stream.add(
                    Phase.LEDGER_EVENTS, hist_key,
                    (lambda e=hist_event, f=_apply_ccy_event: f(e)),
                    label=f"ccy:{currency_code}",
                )

        # SOY quantity is authoritative - always reconcile to match it.
        # Historical replay provides accurate lot-level cost basis,
        # but the total quantity MUST match the reported SOY balance.
        if isinstance(currency_asset, CashBalance):
            stream.add(
                Phase.RECONCILE, (0,),
                (lambda l=currency_ledger, a=currency_asset:
                    _reconcile_currency_soy(l, a, tax_year, exchange_rate_provider, ctx)),
                label=f"reconcile-ccy:{currency_code}",
            )

    # === Run the unified historical replay ===
    stream.run()

    logger.info(f"Initialized {securities_ledger_count} FIFO ledgers (unified replay).")
    for ccy, (done, total) in currency_replay_counts.items():
        logger.info(f"Currency {ccy}: Replayed {done}/{total} historical events")
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

    logger.info(f"Processing {len(current_year_events)} current tax year events using dispatch table...")
    for event_idx, event in enumerate(current_year_events):
        asset_object = asset_resolver.get_asset_by_id(event.asset_internal_id)
        if not asset_object:
            raise ProcessingError(f"Event {event.event_id} ({event.event_type.name}) references unknown asset {event.asset_internal_id}. Asset resolution failure.")

        ledger = fifo_ledgers.get((DEFAULT_ACCOUNT, asset_object.internal_asset_id))
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
                        f"FX trade {event.event_id}"
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
    eoy_mismatch_errors = 0 
    for asset_id, asset_obj in asset_resolver.assets_by_internal_id.items():
        if asset_obj.asset_category == AssetCategory.CASH_BALANCE:
            continue

        ledger = fifo_ledgers.get((DEFAULT_ACCOUNT, asset_id))
        calculated_eoy_qty: Decimal

        if ledger:
            calculated_eoy_qty = ledger.get_current_position_quantity()
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
        # The EoY quantity is fully determined by this year's input alone.
        # reconcile_with_soy_position pins the ledger to the quantity in the SoY positions
        # report — in the reconstruction branch, the fallback branch and the reported-zero
        # case alike — so the previous year's trade history can influence cost basis and
        # acquisition dates but never the running quantity. Reported SoY plus this year's
        # events therefore has exactly one correct answer, and a residual means an event is
        # missing or was processed wrongly: an absent trade or corporate action, an option
        # exercise not linked, or one instrument resolved to two assets. At least one
        # disposal is then matched against the wrong lots, so the gains computed from this
        # ledger are wrong too — not merely the quantity.
        #
        # PRD.md 2.4 already required the quantities to be identical and the discrepancy to
        # be a critical error; only the engine's own "processing will continue" softened it
        # into a warning. CLAUDE.md's fail-fast rule settles which of the two wins: a wrong
        # number that looks plausible is worse than a crash.
        #
        # Reported as a batch, after the loop, so one run names every affected position
        # instead of stopping at the first.
        subjects = "; ".join(
            g.subject for g in (data_gap_collector.gaps if data_gap_collector else [])
            if g.code == "EOY_QTY_MISMATCH"
        )
        detail = (
            f"Die EoY-Abstimmung schlägt für {eoy_mismatch_errors} Position(en) fehl: der aus "
            f"dem gemeldeten SoY-Bestand und den Ereignissen des Steuerjahres berechnete "
            f"Endbestand weicht vom Broker-Report ab. Betroffen: {subjects or 'siehe Log'}. "
            f"Der SoY-Bestand wird aus dem Positionsbericht übernommen, nicht aus der "
            f"Vorjahreshistorie — die Stückzahl ist damit allein durch die Ereignisse dieses "
            f"Jahres bestimmt, und eine Abweichung bedeutet, dass ein Ereignis fehlt oder "
            f"falsch verarbeitet wurde (fehlende Trades, Kapitalmaßnahmen, Options-Ausübungen, "
            f"oder ein Instrument, das unter zwei Kennungen geführt wird). Solange die "
            f"Abweichung besteht, ist mindestens eine Veräußerung falsch zugeordnet und die "
            f"daraus berechneten Gewinne sind unzutreffend."
        )
        if data_gap_collector is not None:
            # Records, logs CRITICAL, and raises DataGapError (a ProcessingError).
            data_gap_collector.record(
                code="EOY_RECONCILIATION_FAILED",
                subject=f"Steuerjahr {tax_year}",
                detail=detail,
                severity=GapSeverity.FAIL_FAST,
            )
        # Reached only when no collector was supplied (direct callers). The abort must not
        # be contingent on an optional argument.
        logger.critical(f"EOY Quantity Validation FAILED with {eoy_mismatch_errors} critical mismatches.")
        raise DataGapError(f"[EOY_RECONCILIATION_FAILED] Steuerjahr {tax_year}: {detail}")
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

        ledger = currency_fifo_ledgers.get((DEFAULT_ACCOUNT, asset_id))
        if ledger:
            long_qty = sum(lot.quantity for lot in ledger.lots)
            short_qty = sum(lot.quantity_shorted for lot in ledger.short_lots)
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
            # WARNING, not FAIL_FAST, and deliberately unlike the securities check
            # above: the listed causes are input-completeness problems (cash-balance
            # export date range, deposits/withdrawals/margin interest absent from the
            # cash-transactions file) rather than a ledger that disagrees with the
            # broker about a holding. Recorded so it reaches the report instead of
            # living only in the log — an FX ledger that is short still moves the
            # §20 Abs. 2 Nr. 3 gains computed from it.
            if data_gap_collector is not None:
                data_gap_collector.record(
                    code="CURRENCY_EOY_MISMATCH",
                    subject=str(asset_obj.currency),
                    detail=(f"FIFO-Bestand {calculated_eoy:.2f} weicht vom gemeldeten "
                            f"Kontostand {reported_eoy:.2f} ab (Differenz {diff:.2f}). "
                            f"Mögliche Ursachen: Zeitraum der Cash-Balance-Datei, oder "
                            f"nicht erfasste Ein-/Auszahlungen, Margin-Zinsen oder Gebühren."),
                )
        else:
            logger.debug(f"Currency EOY OK {asset_obj.currency}: FIFO={calculated_eoy:.2f}, Reported={reported_eoy:.2f}")

    if currency_eoy_mismatches > 0:
        logger.warning(f"Currency EOY validation: {currency_eoy_mismatches} mismatches found. "
                      f"Common causes: cash balance CSV dates don't match tax year, "
                      f"or untracked currency-impacting events (deposits, withdrawals, "
                      f"margin interest, broker fees not in cash transactions CSV).")
    else:
        logger.info("Currency EOY validation passed.")

    # --- Vorabpauschale ---
    # The VP declared in VZ `tax_year` is the one computed FOR calendar `tax_year - 1`: it is
    # deemed to flow on the first working day of `tax_year` (18 Abs. 3 InvStG), and Zeilen 9-13
    # take "die Ihnen im Jahr <tax_year> als zugeflossen geltenden Vorabpauschalen". Until
    # 2026-08-03 the engine computed the VP for the tax year itself and declared it in that same
    # year -- one year early, with the wrong Basiszins and the wrong reference prices.
    # See reference/investment-tax-law/invstg-18-vorabpauschale.md.
    vorabpauschale_year = tax_year - 1

    funds_held = any(
        isinstance(a, InvestmentFund) for a in asset_resolver.assets_by_internal_id.values()
    )
    if funds_held and not prior_year_positions_available:
        # Cannot compute deemed income that is certainly due. Substituting the tax year's own
        # snapshot is what produced the wrong figure; emitting nothing would understate income.
        detail = (
            f"Vorabpauschale for calendar {vorabpauschale_year} cannot be computed: "
            f"Positions-{vorabpauschale_year}-SoY.csv and/or Positions-{vorabpauschale_year}-EoY.csv "
            f"is not present in data_import/. The VZ {tax_year} declaration must report the "
            f"Vorabpauschale for {vorabpauschale_year} (18 Abs. 3 InvStG; Anlage KAP-INV "
            f"Zeilen 9-13 take the amounts deemed to flow in {tax_year}), and that needs "
            f"{vorabpauschale_year}'s start and end position snapshots. Add those files, or "
            f"establish by hand that no investment fund was held during {vorabpauschale_year}."
        )
        if data_gap_collector is not None:
            data_gap_collector.record(
                code="VORABPAUSCHALE_PRIOR_YEAR_SNAPSHOT_MISSING",
                subject=f"Vorabpauschale {vorabpauschale_year}",
                detail=detail,
                severity=GapSeverity.FAIL_FAST,
            )  # records, logs CRITICAL and raises DataGapError
        else:
            # No collector wired: a FAIL_FAST condition must still stop the run rather than
            # fall through to an absent Vorabpauschale.
            raise DataGapError(
                f"[VORABPAUSCHALE_PRIOR_YEAR_SNAPSHOT_MISSING] "
                f"Vorabpauschale {vorabpauschale_year}: {detail}"
            )

    prior_year_distributions_by_asset: Dict[uuid.UUID, Decimal] = _collect_fund_distributions_for_year(
        financial_events, vorabpauschale_year, asset_resolver, ctx
    )

    vorabpauschale_data_items = _calculate_vorabpauschale(
        asset_resolver=asset_resolver,
        distributions_by_asset=prior_year_distributions_by_asset,
        currency_converter=currency_converter,
        vorabpauschale_year=vorabpauschale_year,
        ctx=ctx,
    )
    logger.info(
        f"Vorabpauschale calculation produced {len(vorabpauschale_data_items)} records "
        f"for calendar {vorabpauschale_year} (declared in VZ {tax_year})."
    )

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


def _collect_fund_distributions_for_year(
    financial_events: List[FinancialEvent],
    calendar_year: int,
    asset_resolver: AssetResolver,
    ctx: Context,
) -> Dict[uuid.UUID, Decimal]:
    """Sum gross EUR fund distributions per asset within one calendar year.

    Separate from the engine's historical/current-year split, which buckets only the event
    kinds the FIFO replay needs and drops `DISTRIBUTION_FUND` before the tax year. The
    Vorabpauschale for calendar `calendar_year` is reduced by that year's distributions
    (18 Abs. 1 S. 1 InvStG), which for a VZ Y run are *prior-year* events.

    Only positive distributions reduce the Basisertrag; a negative amount is a correction
    booking, not a distribution, and must not inflate the deemed income.
    """
    totals: DefaultDict[uuid.UUID, Decimal] = defaultdict(lambda: ctx.create_decimal(Decimal('0')))
    for event in financial_events:
        if not isinstance(event, CashFlowEvent):
            continue
        if event.event_type != FinancialEventType.DISTRIBUTION_FUND:
            continue
        try:
            event_date_obj = get_event_sort_key(event, asset_resolver)[0]
        except ValueError as e:
            logger.error(
                f"Fund distribution {event.event_id} has an invalid date or identifier ({e}); "
                f"it cannot be attributed to a Vorabpauschale year."
            )
            continue
        if event_date_obj.year != calendar_year:
            continue
        gross_eur = event.gross_amount_eur if event.gross_amount_eur is not None else Decimal('0')
        if gross_eur > Decimal('0'):
            totals[event.asset_internal_id] = ctx.add(totals[event.asset_internal_id], gross_eur)
    return dict(totals)


def _calculate_vorabpauschale(
    asset_resolver: AssetResolver,
    distributions_by_asset: Dict[uuid.UUID, Decimal],
    currency_converter: CurrencyConverter,
    vorabpauschale_year: int,
    ctx: Context,
) -> List[VorabpauschaleData]:
    """
    Calculate the Vorabpauschale FOR calendar year `vorabpauschale_year`.

    **`vorabpauschale_year` is not the Veranlagungszeitraum.** The VP for calendar X is deemed
    to flow on the first working day of X+1 (18 Abs. 3 InvStG) and is declared on Zeilen 9-13
    of the *X+1* Anlage KAP-INV. Callers preparing a VZ Y return must pass Y-1. All position
    values and distributions read here are therefore those of `vorabpauschale_year`, taken from
    the `Asset.prior_year_*` fields, not the tax year's own SoY/EoY snapshot.

    Formula per 18 InvStG, sentence by sentence:
      Abs. 1 S. 2  Basisertrag = Ruecknahmepreis_Jahresbeginn * basiszins * 0.7
      Abs. 1 S. 3  Basisertrag capped at (last price of year - first price) + distributions
      Abs. 1 S. 1  VP = max(0, Basisertrag - distributions)
      Abs. 4       basiszins from the published BMF table for `vorabpauschale_year`
    Teilfreistellung (20 InvStG) is applied to derive the net figure; the gross figure is what
    goes on the form.

    Not implemented, and deliberately so rather than silently approximated -- see
    reference/investment-tax-law/invstg-18-vorabpauschale.md, "Known deviations":
    Abs. 2 (pro-rata reduction in the acquisition year) and Abs. 1 S. 4 (Boersen- oder
    Marktpreis only where no Ruecknahmepreis was set).
    """
    from src.utils.tax_utils import get_teilfreistellung_rate_for_fund_type

    from src.tax_law.registry import basiszins_pct
    basiszins = basiszins_pct(vorabpauschale_year)  # None -> loud warning inside the registry
    if basiszins is None:
        return []

    base_return_rate = ctx.multiply(basiszins, Decimal("0.01"))  # Convert percentage to factor
    factor_70 = Decimal("0.7")

    # Conversion dates within the Vorabpauschale year: Jan 2 for the year-start price
    # (Jan 1 is never a business day), Dec 31 for the last price set in the year.
    soy_conversion_date = date(vorabpauschale_year, 1, 2)
    eoy_conversion_date = date(vorabpauschale_year, 12, 31)

    results: List[VorabpauschaleData] = []

    for asset_id, asset_obj in asset_resolver.assets_by_internal_id.items():
        if not isinstance(asset_obj, InvestmentFund):
            continue
        # Held at the start of the Vorabpauschale year? Units acquired later get no VP here;
        # Abs. 2's pro-rata reduction is not implemented (see the docstring).
        if asset_obj.prior_year_soy_quantity is None or asset_obj.prior_year_soy_quantity <= Decimal('0'):
            continue

        # Ruecknahmepreis at the start of the Vorabpauschale year (Abs. 1 S. 2)
        soy_value_foreign = asset_obj.prior_year_soy_position_value
        soy_currency = asset_obj.prior_year_soy_mark_price_currency or asset_obj.currency
        if soy_value_foreign is None or soy_currency is None:
            logger.warning(f"Fund {asset_obj.description} (ID: {asset_id}): Missing start-of-{vorabpauschale_year} position value or currency. Skipping VP.")
            continue

        fund_value_soy_eur = currency_converter.convert_to_eur(soy_value_foreign, soy_currency, soy_conversion_date)
        if fund_value_soy_eur is None:
            logger.warning(f"Fund {asset_obj.description} (ID: {asset_id}): Failed to convert start-of-{vorabpauschale_year} value to EUR. Skipping VP.")
            continue

        # Last Ruecknahmepreis set in the Vorabpauschale year (Abs. 1 S. 3 cap)
        eoy_value_foreign = asset_obj.prior_year_eoy_position_value
        eoy_currency = asset_obj.prior_year_eoy_mark_price_currency or asset_obj.currency
        if eoy_value_foreign is None or eoy_currency is None:
            # Fund fully disposed of during the year. The Abs. 3 Zufluss then falls after the
            # disposal, so no VP arises. This is inferred from Abs. 3, not stated by a located
            # Tier 1/2 source: see reference/research/open-legal-questions.md Q5 for both
            # readings, and docs/legal-implementation-map.md GT-INVSTG-016 for this choice.
            logger.debug(f"Fund {asset_obj.description} (ID: {asset_id}): No end-of-{vorabpauschale_year} position value. Skipping VP.")
            continue

        fund_value_eoy_eur = currency_converter.convert_to_eur(eoy_value_foreign, eoy_currency, eoy_conversion_date)
        if fund_value_eoy_eur is None:
            logger.warning(f"Fund {asset_obj.description} (ID: {asset_id}): Failed to convert EoY value to EUR. Skipping VP.")
            continue

        # 1. Basisertrag = fund_value_soy_eur * basiszins_rate * 0.7
        basisertrag = ctx.multiply(ctx.multiply(fund_value_soy_eur, base_return_rate), factor_70)

        # 2. If Basisertrag <= 0, VP = 0
        if basisertrag <= Decimal('0'):
            logger.debug(f"Fund {asset_obj.description}: Basisertrag={basisertrag} <= 0, VP=0.")
            continue

        # 3. VP = Basisertrag - distributions (but not below 0)
        distributions_eur = distributions_by_asset.get(asset_id, Decimal('0'))
        vp_after_dist = ctx.subtract(basisertrag, distributions_eur)
        if vp_after_dist <= Decimal('0'):
            logger.debug(f"Fund {asset_obj.description}: Distributions ({distributions_eur}) >= Basisertrag ({basisertrag}), VP=0.")
            continue

        # 4. Cap: VP <= max(0, fund_value_eoy_eur - fund_value_soy_eur)
        value_gain = ctx.subtract(fund_value_eoy_eur, fund_value_soy_eur)
        cap = max(Decimal('0'), value_gain)
        gross_vp = min(vp_after_dist, cap)

        if gross_vp <= Decimal('0'):
            logger.debug(f"Fund {asset_obj.description}: Value gain cap applied, VP=0.")
            continue

        # 5. Apply Teilfreistellung
        fund_type = asset_obj.fund_type or InvestmentFundType.NONE
        tf_rate = get_teilfreistellung_rate_for_fund_type(fund_type)
        tf_amount = ctx.multiply(gross_vp, tf_rate)
        net_vp = ctx.subtract(gross_vp, tf_amount)

        TWO_PLACES = config.OUTPUT_PRECISION_AMOUNTS
        vp_data = VorabpauschaleData(
            asset_internal_id=asset_id,
            vorabpauschale_year=vorabpauschale_year,
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
        )
        results.append(vp_data)
        logger.info(
            f"Fund {asset_obj.description}: VP gross={gross_vp.quantize(TWO_PLACES, context=ctx)}, "
            f"TF={tf_amount.quantize(TWO_PLACES, context=ctx)}, net={net_vp.quantize(TWO_PLACES, context=ctx)}"
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
    currency_fifo_ledgers: Dict[Tuple[str, uuid.UUID], 'FifoLedger'],
    fifo_ledgers: Dict[Tuple[str, uuid.UUID], 'FifoLedger'],
    currency_converter: CurrencyConverter,
    exchange_rate_provider: ECBExchangeRateProvider,
    internal_calculation_precision: int,
    decimal_rounding_mode: str,
    context_label: str = "",
) -> None:
    """
    Ensure a CashBalance asset and FIFO ledger exist for the given currency.
    Creates both on-the-fly if they don't exist yet.
    This makes event processing robust against any CSV/event ordering.
    """
    if currency_code.upper() == "EUR":
        return

    existing_asset = asset_resolver.get_cash_balance_asset(currency_code.upper())
    if existing_asset:
        # Asset exists; ensure ledger also exists
        if (DEFAULT_ACCOUNT, existing_asset.internal_asset_id) not in fifo_ledgers:
            new_ledger = FifoLedger(
                asset_internal_id=existing_asset.internal_asset_id,
                asset_category=AssetCategory.CASH_BALANCE,
                asset_multiplier_from_asset=None,
                currency_converter=currency_converter,
                exchange_rate_provider=exchange_rate_provider,
                internal_working_precision=internal_calculation_precision,
                decimal_rounding_mode=decimal_rounding_mode,
            )
            currency_fifo_ledgers[(DEFAULT_ACCOUNT, existing_asset.internal_asset_id)] = new_ledger
            fifo_ledgers[(DEFAULT_ACCOUNT, existing_asset.internal_asset_id)] = new_ledger
            logger.info(f"{context_label}: Created currency ledger for existing {currency_code} asset")
        return

    # Create CashBalance asset on-the-fly
    new_asset = asset_resolver.get_or_create_asset(
        raw_isin=None, raw_conid=None, raw_symbol=currency_code.upper(),
        raw_currency=currency_code.upper(), raw_ibkr_asset_class="CASH",
        raw_description=f"Cash Balance {currency_code.upper()}",
        description_source_type="on_the_fly"
    )
    if new_asset:
        new_ledger = FifoLedger(
            asset_internal_id=new_asset.internal_asset_id,
            asset_category=AssetCategory.CASH_BALANCE,
            asset_multiplier_from_asset=None,
            currency_converter=currency_converter,
            exchange_rate_provider=exchange_rate_provider,
            internal_working_precision=internal_calculation_precision,
            decimal_rounding_mode=decimal_rounding_mode,
        )
        currency_fifo_ledgers[(DEFAULT_ACCOUNT, new_asset.internal_asset_id)] = new_ledger
        fifo_ledgers[(DEFAULT_ACCOUNT, new_asset.internal_asset_id)] = new_ledger
        logger.info(f"{context_label}: Created CashBalance asset and ledger for {currency_code}")


def _process_cashflow_currency_impact(
    event: FinancialEvent,
    asset_resolver: AssetResolver,
    currency_fifo_ledgers: Dict[Tuple[str, uuid.UUID], 'FifoLedger'],
    currency_processor: 'CurrencyConversionProcessor',
    fifo_ledgers: Optional[Dict[Tuple[str, uuid.UUID], 'FifoLedger']] = None,
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

    currency_ledger = currency_fifo_ledgers.get((DEFAULT_ACCOUNT, currency_asset.internal_asset_id))
    if not currency_ledger:
        # Create ledger on-the-fly (no prior balance, first cash flow in this currency)
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
        currency_fifo_ledgers[(DEFAULT_ACCOUNT, currency_asset.internal_asset_id)] = currency_ledger
        if fifo_ledgers is not None:
            fifo_ledgers[(DEFAULT_ACCOUNT, currency_asset.internal_asset_id)] = currency_ledger
        logger.info(f"Cashflow {event.event_id}: Created currency ledger for {cash_currency} (first cash flow)")

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
    historical_currency_events: DefaultDict[str, List[FinancialEvent]]
) -> None:
    """
    Collect a historical event into currency-specific lists for FIFO replay.

    Captures ALL events that affect foreign currency cash balances:
    - Trades (buy/sell securities in foreign currency, plus commissions)
    - Currency conversions (explicit FX trades)
    - Cash flows (dividends, interest, distributions)
    - Expenses (WHT, fees, Stueckzinsen)
    """
    if isinstance(event, CurrencyConversionEvent):
        if event.from_currency.upper() != "EUR":
            historical_currency_events[event.from_currency.upper()].append(event)
        if event.to_currency.upper() != "EUR":
            historical_currency_events[event.to_currency.upper()].append(event)
        return

    if isinstance(event, TradeEvent):
        ccy = (event.local_currency or "").upper()
        if ccy and ccy != "EUR":
            historical_currency_events[ccy].append(event)
        return

    # Cash merger: acquisition proceeds create foreign currency cash
    if isinstance(event, CorpActionMergerCash):
        ccy = (event.local_currency or "").upper()
        if ccy and ccy != "EUR" and event.gross_amount_foreign_currency:
            historical_currency_events[ccy].append(event)
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
            historical_currency_events[ccy].append(event)


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
