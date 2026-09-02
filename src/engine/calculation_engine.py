# src/engine/calculation_engine.py
import logging
from typing import Callable, List, Tuple, Dict, DefaultDict, Optional, Set, Any
import uuid
from decimal import Decimal, getcontext, Context
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, date

from src.utils.account_utils import account_key, DEFAULT_ACCOUNT
from src.processing.data_gaps import DataGapCollector, DataGapError, GapSeverity
from src.domain.events import (
    FinancialEvent, TradeEvent, CorpActionSplitForward, CorpActionMergerCash,
    CorpActionStockDividend, CorpActionMergerStock, CorporateActionEvent,
    CorpActionExpireDividendRights, OptionExerciseEvent, OptionAssignmentEvent,
    OptionExpirationWorthlessEvent, OptionCashSettlementEvent,
    OptionLifecycleEvent, CashFlowEvent, FeeEvent,
    WithholdingTaxEvent, CurrencyConversionEvent, InternalTransferEvent,
    InternalCashTransferEvent
)
from src.domain.assets import (
    Asset, Stock, Bond, AssetCategory, Option, InvestmentFund, CashBalance,
    MarksByAccount, PositionSnapshot, SnapshotsByAccount, person_snapshot,
)
from src.identification.asset_resolver import AssetResolver
from src.domain.results import RealizedGainLoss, VorabpauschaleData
from src.domain.enums import FinancialEventType, InvestmentFundType 
from src.utils.snapshot_dates import (
    first_business_day_of_year, last_business_day_of_year)
from src.utils.sorting_utils import get_event_sort_key
from src.domain.exceptions import ProcessingError
from src.utils.type_utils import parse_ibkr_date

from .fifo_manager import FifoLedger, FifoLot
from .ledger_views import aggregate_lots
from .vorabpauschale_attribution import (
    abs2_retained_twelfths, apply_weighted_share, distribute_declared_vorabpauschale,
    weigh_tranches)
from src.processing.vorabpauschale_declarations import (
    DECLARATION_UNKNOWN_CODE, DIVERGES_CODE, NOT_ATTRIBUTABLE_CODE,
    NOT_DECLARED_CODE, VorabpauschaleDeclarationStore)
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
from .event_processors.transfer_processor import (
    InternalTransferProcessor, InternalCashTransferProcessor, apply_internal_transfer)


logger = logging.getLogger(__name__)


def _initialize_currency_soy_ledger(ledger: FifoLedger, asset: CashBalance, tax_year: int,
                                     exchange_rate_provider: ECBExchangeRateProvider,
                                     ctx: Context,
                                     reported: Optional[PositionSnapshot] = None) -> None:
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

    reported_soy_qty = reported.quantity if reported else None
    reported_soy_cost = reported.cost_basis_amount if reported else None
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
        if reported_soy_cost and reported_soy_cost > Decimal("0"):
            total_cost_basis_eur = reported_soy_cost
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

def _grade_mark_outcomes(mark_outcomes, data_gap_collector) -> None:
    """Report every checkpoint mark where the reconstruction was discarded.

    The severity turns on what the interval *started* from, not on which mark it
    ended at:

    * **Started at a confirmed snapshot** — ground truth at both ends, and the
      replay in between is the engine's own work over events the input actually
      contains. A disagreement is a defect in the engine or in the input, and it
      stops the run.
    * **Started unconfirmed** — in practice the earliest interval, before any
      snapshot exists. Its ledger begins empty while the real holding did not,
      so it is *expected* to disagree by whatever was held before the input
      window opened. That is the ordinary condition of a partial history, it is
      recorded, and the run continues from the snapshot.

    Both kinds discard real acquisition dates and cost bases for the asset
    concerned, so neither is silent. Every case is collected before anything
    raises, so one run names the whole problem.
    """
    if not mark_outcomes:
        return

    discarded = [(asset, outcome) for asset, outcome in mark_outcomes if not outcome.kept]
    if not discarded:
        logger.info("Every ledger agreed with the reported snapshot at every checkpoint mark.")
        return

    def _describe(asset, outcome) -> str:
        return (f"{asset.get_classification_key()} @ {outcome.mark_label}: "
                f"reconstructed {outcome.reconstructed_quantity}, "
                f"broker reported {outcome.reported_quantity}"
                + (" (an event could not be applied during the interval)"
                   if outcome.oversell_observed else "")
                + (" (the reconstruction holds a long AND a short position in the same "
                   "instrument, which is not a holding: the input's open/close indicators "
                   "contradict each other)"
                   if outcome.offsetting_long_and_short else ""))

    expected = [(a, o) for a, o in discarded if not o.started_confirmed]
    defects = [(a, o) for a, o in discarded if o.started_confirmed]

    for asset, outcome in expected:
        cause = (
            "The broker's own open/close indicators disagree with each other here, so the "
            "reconstruction is not short of history -- it is contradictory. "
            if outcome.offsetting_long_and_short else
            "This interval did not start from a reported snapshot, so the reconstruction is "
            "missing whatever was held before the input window opened. ")
        detail = (
            f"{_describe(asset, outcome)}. {cause}The broker's figure has been taken and the "
            f"replay continues from it. The quantity carried forward is the broker's; the acquisition date and cost "
            f"basis of those units were never observed, so the lot is flagged as undated and "
            f"consumers that need a real date must refuse it."
        )
        if data_gap_collector is not None:
            data_gap_collector.record(
                code="REPLAY_MARK_UNCONFIRMED_START",
                subject=f"{asset.get_classification_key()} @ {outcome.mark_label}",
                detail=detail,
                severity=GapSeverity.WARNING,
            )
        else:
            logger.warning("[REPLAY_MARK_UNCONFIRMED_START] %s", detail)

    if not defects:
        return

    named = "; ".join(_describe(asset, outcome) for asset, outcome in defects)
    detail = (
        f"The historical replay disagrees with the broker over an interval that began at a "
        f"reported snapshot and ended at one. Both ends are ground truth and every event in "
        f"between is present in the input, so the disagreement is in the engine's handling of "
        f"those events or in the input itself — it is not a consequence of a short trade "
        f"history. Real acquisition dates and cost bases would be discarded and replaced by a "
        f"synthesised lot, which no downstream consumer can tell from a measured one. "
        f"{len(defects)} case(s): {named}"
    )
    if data_gap_collector is not None:
        data_gap_collector.record(
            code="REPLAY_MARK_MISMATCH",
            subject=f"{len(defects)} ledger(s) disagree with a confirmed interval",
            detail=detail,
            severity=GapSeverity.FAIL_FAST,
        )  # records, logs CRITICAL and raises DataGapError
    else:
        raise DataGapError(f"[REPLAY_MARK_MISMATCH] {detail}")


def _replay_historical_merger(merger_event, fifo_ledgers) -> None:
    """Apply ONE historical stock-for-stock merger — the per-event unit the
    unified replayer streams chronologically in Phase.LEDGER_EVENTS, at the
    merger's own date. Tax-neutral under §20 Abs. 4a Satz 1-2 EStG (the new
    shares step into the tax position of the old ones), so the lots transfer
    with their acquisition date and cost basis, and Satz 6 places the transfer
    at the Einbuchung date so that day's disposals can consume it:
    reference/tax-law/estg-20-kapitalvermoegen.md, "Abs. 4a"
    (GT-ESTG20-015, GT-ESTG20-018)."""
    # The delivered shares arrive in the same account the old ones left ([GT-ESTG20-013]:
    # per-Depot). Both ledgers are that account's.
    merger_account = account_key(merger_event.account_id)
    source_ledger = fifo_ledgers.get((merger_account, merger_event.asset_internal_id))
    target_ledger = fifo_ledgers.get((merger_account, merger_event.new_asset_internal_id))

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


MULTI_ACCOUNT_LIMITATIONS = "MULTI_ACCOUNT_LIMITATIONS"


def _report_multi_account_limitations(accounts, data_gap_collector,
                                      transfers_file_supplied: bool = False) -> None:
    """Warn when several accounts are held and no Transfers export was offered at all.

    **One limitation, and it is the only one left.** Lot selection is per Depot
    ([GT-ESTG20-013]), a securities move between the taxpayer's own accounts is read and
    relocates its lots ([GT-ESTG20-014]), and each account's currency balance is its own
    Kapitalforderung whose Umbuchung is measured ([GT-FX-009], [GT-FX-010]). What remains
    is not a limitation of the engine but a gap in the input: with no Transfers export a
    move that happened is invisible. The receiving account then holds units it never
    bought and the sending one still shows units it never sold, the reconciliation rebuilds
    both from the broker's snapshot, and the acquisition dates it substitutes are invented
    -- which reaches the holding period (§ 23 EStG), the FIFO order and the currency gains,
    in the year of the move and every year after it.

    **So this fires only when the export is absent.** When it was read there is nothing to
    warn about, and warning anyway would be the defect this function used to be: its text
    said currency was held per person long after the store settled that it is not, and a
    caveat nobody can act on teaches the reader to skip the section. The currency clause is
    gone with the change that keys currency ledgers by account; the securities clause is
    gone when the export is read.

    A WARNING rather than a refusal, because an absent export is the ordinary state of
    anyone holding one account or having never moved anything. The other shape -- an export
    covering some years and not others -- is refused by `_require_a_complete_transfers_window`
    before this runs, since the person plainly has the report and a missing year costs one
    export to fix.

    Defaults to not-read: a caller that has not been updated says the cautious thing.
    """
    named = sorted(a for a in accounts if a != DEFAULT_ACCOUNT)
    if len(named) < 2 or transfers_file_supplied:
        return
    detail = (
        "ES WURDE KEIN TRANSFERS-BERICHT EINGELESEN. "
        "Wurde eine Position oder ein Fremdwährungsbetrag zwischen Ihren Konten "
        "übertragen, kann die Engine den Übertrag nicht sehen: sie rekonstruiert den "
        "Bestand aus dem Positionsbericht -- die Stückzahl ist die des Brokers, das "
        "Anschaffungsdatum ist erfunden. Betroffen sind die Haltefrist (§ 23 EStG), die "
        "FIFO-Reihenfolge und die Fremdwährungsgewinne, im Jahr des Übertrags UND in "
        "allen Folgejahren. Exportieren Sie den Transfers-Bericht für jedes Jahr (siehe "
        "README), dann entfällt dieser Hinweis. "
        "Wurde nie etwas zwischen Ihren Konten übertragen, ist er für Sie ohne "
        "Bedeutung. Andernfalls sind die Zahlen dieses Berichts NICHT BELASTBAR -- "
        "prüfen Sie sie, bevor Sie sie übernehmen."
    )
    subject = f"{len(named)} Konten im Export"
    if data_gap_collector is not None:
        data_gap_collector.record(
            code=MULTI_ACCOUNT_LIMITATIONS, subject=subject, detail=detail,
            severity=GapSeverity.WARNING)
    else:
        logger.warning("[%s] %s: %s", MULTI_ACCOUNT_LIMITATIONS, subject, detail)


TRANSFERS_WINDOW_INCOMPLETE = "TRANSFERS_WINDOW_INCOMPLETE"


def _require_a_complete_transfers_window(accounts, transfers_file_supplied: bool,
                                         transfers_missing_years: str,
                                         data_gap_collector) -> None:
    """A Transfers export that covers some years and not others stops the run.

    **A hole is not the same as an absence, and only the hole is refused.** A person who
    has never created the query has no Transfers file at all, and that has to stay a
    warning -- it is the ordinary state of everyone who holds one account or has never
    moved anything, and refusing would stop them for nothing. A person whose export
    covers 2022 to 2024 but not 2025 plainly HAS the query: a year of it is simply
    missing, and a move made in that year is invisible, silently, in that year and every
    year after it. There is nothing to weigh there -- exporting the year is cheap and the
    figure it protects is not recoverable afterwards.

    Only for a run that sees more than one account, which is the same condition the
    warning uses: a move between the taxpayer's own accounts needs two of them, so with
    one account there is no per-Depot placement for a missing year to get wrong.

    The years are named because the reader's next action is to export exactly those.
    """
    named = sorted(a for a in accounts if a != DEFAULT_ACCOUNT)
    missing = (transfers_missing_years or "").strip()
    if len(named) < 2 or not transfers_file_supplied or not missing:
        return

    subject = f"Transfers export missing for: {missing}"
    detail = (
        f"The Transfers export covers some years of the replayed window and not "
        f"{missing}. A move between your own accounts in an uncovered year cannot be "
        f"seen: the receiving account holds units it never bought and the sending one "
        f"still shows units it never sold, so the reconstruction is discarded and "
        f"rebuilt from the position snapshot -- the broker's quantity with an invented "
        f"acquisition date. That date decides the holding period (§ 23 EStG) and which "
        f"units a later sale consumes, in the year of the move AND in every year after "
        f"it. Because the export exists for other years, the query exists too: export "
        f"{missing} as well (see README) and this stops. An export absent for every "
        f"year is a different case and is reported as a warning, not a refusal."
    )
    if data_gap_collector is not None:
        data_gap_collector.record(
            code=TRANSFERS_WINDOW_INCOMPLETE, subject=subject, detail=detail,
            severity=GapSeverity.FAIL_FAST,
        )  # records, logs CRITICAL and raises DataGapError
    else:
        raise DataGapError(f"[{TRANSFERS_WINDOW_INCOMPLETE}] {subject}: {detail}")


TRANSFER_COUNTERPARTY_UNKNOWN = "TRANSFER_COUNTERPARTY_UNKNOWN"


def _require_transfer_counterparties_are_the_persons_own(
        transfer_events, own_accounts, asset_resolver, data_gap_collector) -> None:
    """Every account a move names must be one the taxpayer's own exports name too.

    [GT-ESTG20-014] covers a move between *the taxpayer's own depots*, and that is what
    the engine does with one: relocate the lots, realise nothing. The export's `Type` is
    not that test. `INTERNAL` is IBKR's word for "between IBKR accounts", which says
    nothing about who owns the other one -- a gift, a spousal transfer or any move to a
    third party is `INTERNAL` too, and each of those may well be a disposal that no claim
    in `reference/` decides.

    So the ownership test is made from the input instead: an account the person holds is
    an account their own exports report -- it trades, it is snapshotted, or it is marked.
    An account named only by a transfer is either not theirs or was never exported, and
    the run must not compute through either. Without this, a move OUT to such an account
    before the tax year completes in silence: the units leave the person's holdings with
    no disposal anywhere, and the opening snapshot never lists the account, so nothing
    disagrees with anything. (A move inside the tax year is caught by the per-account
    end-of-year check, which is a narrower guard than it looks.)

    Every offender is collected before raising, so one run names the whole problem.
    """
    unknown = []
    for event in transfer_events:
        for account, role in ((event.account_id, "sending"),
                              (event.to_account_id, "receiving")):
            if account_key(account) in own_accounts:
                continue
            asset = asset_resolver.get_asset_by_id(event.asset_internal_id)
            name = asset.get_classification_key() if asset else str(event.asset_internal_id)
            unknown.append(
                f"{name} on {event.event_date}: the {role} account {account} appears "
                f"nowhere else in the input")
    if not unknown:
        return

    subject = f"{len(unknown)} transfer side(s) name an account the input does not report"
    detail = (
        "A move is treated as tax-neutral because it stays within the taxpayer's own "
        "depots ([GT-ESTG20-014]). The export's Type of INTERNAL does not establish "
        "that -- it means the counterparty is an IBKR account, not that it is yours. "
        "Every account named here is absent from the trades, the snapshots and the "
        "checkpoint marks, so either it is not yours, in which case the move may be a "
        "disposal and no rule here decides which, or it is yours and was not exported, "
        "in which case its own holdings are missing too. Export every account you hold "
        "in every query, or the move needs a rule this engine does not have. "
        + "; ".join(unknown)
    )
    if data_gap_collector is not None:
        data_gap_collector.record(
            code=TRANSFER_COUNTERPARTY_UNKNOWN, subject=subject, detail=detail,
            severity=GapSeverity.FAIL_FAST,
        )  # records, logs CRITICAL and raises DataGapError
    else:
        raise DataGapError(f"[{TRANSFER_COUNTERPARTY_UNKNOWN}] {subject}: {detail}")


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
    prior_year_positions_available: bool = False,
    # Checkpoint marks: {year: {(account_key, asset_id): MarkPosition}} from
    # Positions-{year}-EoY.csv, for every year strictly below the opening snapshot. Empty
    # means the historical window is replayed as one uninterrupted interval — the
    # behaviour before checkpointing. Each account's ledger is graded against its OWN mark
    # row (`mark_positions[year][(account, asset)]`); a missing row is a reported zero.
    mark_positions: Optional[Dict[int, "MarksByAccount"]] = None,
    # The tax year's opening and closing snapshots, {(account_key, asset_id):
    # PositionSnapshot}. A ledger reconciles against its OWN account's record; the
    # person's total, which is what the return declares ([GT-ESTG20-061]), is
    # `person_snapshot` over them. Empty means no snapshot was supplied at all, which
    # `_ensure_soy_quantities_are_set` has already turned into an explicit zero holding
    # for every non-cash asset, so an empty registry here means an empty portfolio.
    soy_positions: Optional["SnapshotsByAccount"] = None,
    eoy_positions: Optional["SnapshotsByAccount"] = None,
    # The PRECEDING calendar year's snapshots, read only by the Vorabpauschale: the close
    # of that year (the Rz. 18.4 unit count and the Satz 3 cap price) and the close of the
    # year before it (the units the year opened with). Recorded per (account, asset) like
    # every other snapshot; the Vorabpauschale reads the person's figure over them.
    prior_eoy_positions: Optional["SnapshotsByAccount"] = None,
    prior_opening_positions: Optional["SnapshotsByAccount"] = None,
    # The year-start Ruecknahmepreis 18 Abs. 1 Satz 2 asks for, settled a layer up by
    # `resolve_year_start_prices` and written back into the preceding year's opening
    # snapshot. Passed in as that registry.
    prior_soy_positions: Optional["SnapshotsByAccount"] = None,
    # What was DECLARED as Vorabpauschale on earlier returns, per fund and calendar year.
    # Feeds the Anlage KAP-INV Zeile 53 deduction (19 Abs. 1 Satz 3 InvStG), which may only
    # rest on declared amounts. None means no record is available: the deduction then covers
    # the preceding calendar year alone — the one this return itself declares — and every
    # other holding-period year is reported as undeducted rather than recomputed.
    declaration_store: Optional["VorabpauschaleDeclarationStore"] = None,
    # Asked once per fund and EARLIER holding-period year with nothing on record:
    # "what did your return for that year declare?". None — which is what a
    # --no-interactive run passes — means nobody can be asked, so nothing is assumed
    # and the year is reported unanswered. The year this return itself declares is
    # never asked about; its figures are on the form being produced.
    ask_for_declared_vorabpauschale: Optional[Callable] = None,
    # Whether a Transfers export was offered at all, as opposed to offered and empty. Only
    # the difference between "no report" (a warning) and "report present but a year is
    # missing" (a refusal) turns on it -- see `_require_a_complete_transfers_window` and
    # `_report_multi_account_limitations`.
    transfers_file_supplied: bool = False,
    # Years in the replayed window for which no Transfers file was offered, comma-joined
    # and in order. Only meaningful when a report WAS supplied (a hole, not an absence).
    transfers_missing_years: str = "",
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
    mark_positions = mark_positions or {}
    soy_positions = soy_positions if soy_positions is not None else {}
    eoy_positions = eoy_positions if eoy_positions is not None else {}
    prior_soy_positions = prior_soy_positions if prior_soy_positions is not None else {}
    prior_eoy_positions = prior_eoy_positions if prior_eoy_positions is not None else {}
    prior_opening_positions = (prior_opening_positions
                               if prior_opening_positions is not None else {})

    def person_soy(asset_id: uuid.UUID) -> Optional["PositionSnapshot"]:
        return person_snapshot(soy_positions, asset_id)
    ctx = Context(prec=internal_calculation_precision, rounding=decimal_rounding_mode) # Renamed internal_working_precision

    realized_gains_losses: List[RealizedGainLoss] = []
    vorabpauschale_data_items: List[VorabpauschaleData] = []
    # Every (fund, calendar year) of a holding period whose Vorabpauschale reached no
    # lot. Reported once at the end, filtered to funds actually disposed of.
    unattributed_fund_years: List[UnattributedFundYear] = []

    historical_events_by_asset: DefaultDict[uuid.UUID, List[FinancialEvent]] = defaultdict(list)
    historical_merger_events: List[CorpActionMergerStock] = []
    historical_transfer_events: List[InternalTransferEvent] = []
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
            elif isinstance(event, InternalTransferEvent):
                # A move made before the tax year is replayed as a stream item at its own
                # sort position, exactly like a historical merger (both touch two ledgers).
                historical_transfer_events.append(event)
            elif isinstance(event, (TradeEvent, CorpActionSplitForward, CorpActionStockDividend,
                                    OptionLifecycleEvent, CorpActionMergerCash,
                                    CorpActionExpireDividendRights)):
                # OptionLifecycleEvent joined this bucket when checkpointing exposed what its
                # absence cost: an option opened and closed inside the historical window kept
                # its lots forever, because nothing removed them. Nine option ledgers on the
                # maintainer's 2022 data carried a phantom holding into every later year. The
                # ledger effect is applied by FifoLedger._close_option_lots_historically; no
                # realised gain is produced, because the historical replay declares nothing.
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

    # Funds the tax year opens holding, from the reported opening snapshot. Only
    # these can reach this year's Zeile 53, so only these are attributed to — and,
    # for an earlier year, only these are worth asking a person about.
    funds_held_at_tax_year_opening: Set[uuid.UUID] = {
        asset_id
        for asset_id, asset_obj in asset_resolver.assets_by_internal_id.items()
        if isinstance(asset_obj, InvestmentFund)
        and ((person_soy(asset_id) or PositionSnapshot(quantity=None)).quantity
             or Decimal(0)) > Decimal(0)
    }

    fifo_ledgers: Dict[Tuple[str, uuid.UUID], FifoLedger] = {}  # one per (account_key, asset_id): a disposal consumes its own account's lots ([GT-ESTG20-013])
    # Separate dict for currency ledgers, same (account_key, asset_id) key shape and now the
    # real account in it. Each account's balance in a currency is its own Kapitalforderung
    # (BMF 14.05.2025 Rz. 131 ¶2, [GT-FX-009]), so a disposal out of one account consumes the
    # amounts paid into that account and is measured against their cost. The route is
    # Rz. 131, never Rz. 97: Rz. 97 draws the Depot boundary for § 20 Abs. 4 Satz 7, which by
    # its own wording reaches only Wertpapiere in Sammelverwahrung (the [GT-FX-008]
    # correction). Same shape, different provision.
    currency_fifo_ledgers: Dict[Tuple[str, uuid.UUID], FifoLedger] = {}

    # === Unified historical replay (AR5) ===
    # ONE ordered stream rebuilds all pre-tax-year ledger state — securities
    # AND currencies — under the documented phase contract (see engine/replay.py):
    # LEDGER_EVENTS (chronological, mergers included) -> RECONCILE.
    from src.engine.replay import ReplayStream, Phase

    # Ledger-event work is COLLECTED first, not streamed straight away: the historical window is
    # cut into intervals at the checkpoint marks, and each interval is replayed and reconciled
    # before the next one begins. Items keep their (phase, sort_key) and their insertion order,
    # so within an interval the ordering contract is exactly what a single stream would give.
    deferred_items: List[Tuple[Any, Any, Any, str]] = []

    def _defer(phase, sort_key, apply_fn, label: str = "") -> None:
        deferred_items.append((phase, sort_key, apply_fn, label))

    # Which accounts hold each asset -- one FIFO ledger per (account, asset). A disposal
    # consumes the lots of the account it was made from (BMF Rz. 97 Satz 2, [GT-ESTG20-013]).
    # Four sources, each a place an account can first appear:
    #   * the historical events and the tax year's events -- any account that ever traded it;
    #   * the opening snapshot -- an account holding it from before the import window, with no
    #     event of its own (guarded by
    #     test_an_account_that_only_appears_in_the_snapshot_still_gets_a_ledger);
    #   * the checkpoint marks -- defensive; an account seen only at a mid-window mark is
    #     reconciled away again at the opening snapshot, which does not list it.
    # The CLOSING snapshot is deliberately NOT a source: an account reporting units it never
    # acquired is a reconciliation failure, and a ledger for it would not make it one -- the
    # end-of-year check reads that file directly.
    ledger_accounts: DefaultDict[uuid.UUID, Set[str]] = defaultdict(set)

    def _register_event_accounts(event, asset_id) -> None:
        account = account_key(event.account_id)
        ledger_accounts[asset_id].add(account)
        # A stock-for-stock merger names a second asset, and the delivered lots arrive in the
        # account they left, so the target needs a ledger there too or the transfer is refused.
        new_asset_id = getattr(event, "new_asset_internal_id", None)
        if new_asset_id:
            ledger_accounts[new_asset_id].add(account)
        # A move between accounts names a second ACCOUNT rather than a second asset, and needs
        # the mirror of the line above: without a ledger on the receiving side the move is
        # refused, and the account the units arrive in may appear nowhere else -- a holding
        # moved in and still held at year end sits only in the closing snapshot, which is
        # deliberately not a ledger source.
        to_account_id = getattr(event, "to_account_id", None)
        if to_account_id:
            ledger_accounts[asset_id].add(account_key(to_account_id))

    for _asset_id, _events in historical_events_by_asset.items():
        for _event in _events:
            _register_event_accounts(_event, _asset_id)
    for _event in current_year_events:
        _register_event_accounts(_event, _event.asset_internal_id)
    for _merger in historical_merger_events:
        _register_event_accounts(_merger, _merger.asset_internal_id)
    for _transfer in historical_transfer_events:
        _register_event_accounts(_transfer, _transfer.asset_internal_id)
    # The opening snapshot. A zero holding contributes no ledger: it is the record
    # `_ensure_soy_quantities_are_set` writes under DEFAULT_ACCOUNT for an asset absent from
    # the opening report, and treating it as a source would build a ledger for an account
    # nobody holds beside the asset's real ones. A real holding (quantity != 0) is a source --
    # an account can hold an instrument from before the import window and have no event of
    # its own.
    for (_account, _asset_id), _snap in soy_positions.items():
        if _snap.quantity:
            ledger_accounts[_asset_id].add(_account)
    for _year_marks in mark_positions.values():
        for (_account, _asset_id) in _year_marks:
            ledger_accounts[_asset_id].add(_account)

    # A move may only be treated as tax-neutral if BOTH accounts it names are the person's
    # own -- decided from the input, not from the export's `Type=INTERNAL`. Own accounts are
    # those the person's own exports report (trades, snapshots, marks), never one named only
    # by a transfer.
    _require_transfer_counterparties_are_the_persons_own(
        historical_transfer_events
        + [e for events in historical_currency_events.values() for e in events
           if isinstance(e, InternalCashTransferEvent)]
        + [e for e in current_year_events
           if isinstance(e, (InternalTransferEvent, InternalCashTransferEvent))],
        # An account is the taxpayer's own if their OWN exports report it -- a trade, a
        # snapshot, a mark, a cash balance. A transfer event must NOT self-certify: its own
        # account_id is the sending account, and the whole question is whether that account
        # is the taxpayer's, so both kinds of internal-transfer event are excluded from this
        # set -- the current-year ones here and the historical ones (securities in
        # historical_transfer_events, currency in historical_currency_events, neither in
        # historical_events_by_asset).
        own_accounts=(
            {account_key(e.account_id) for e in current_year_events
             if not isinstance(e, (InternalTransferEvent, InternalCashTransferEvent))}
            | {account_key(e.account_id)
               for events in historical_events_by_asset.values() for e in events}
            | {account for account, _ in soy_positions}
            | {account for account, _ in eoy_positions}
            | {account for marks in mark_positions.values() for account, _ in marks}
        ),
        asset_resolver=asset_resolver,
        data_gap_collector=data_gap_collector,
    )

    _known_accounts = (
        {account for accounts in ledger_accounts.values() for account in accounts}
        | {account for account, _ in eoy_positions}
    )
    # A Transfers export that covers some years and not others stops the run before any
    # figure rests on a move it could not see; an export absent for every year is the
    # ordinary case and only warns.
    _require_a_complete_transfers_window(
        _known_accounts, transfers_file_supplied, transfers_missing_years,
        data_gap_collector)
    _report_multi_account_limitations(
        _known_accounts, data_gap_collector, transfers_file_supplied)

    logger.info("Building unified historical replay stream (securities, mergers, currencies)...")
    for asset_id, asset_obj in asset_resolver.assets_by_internal_id.items():
        if asset_obj.asset_category != AssetCategory.CASH_BALANCE:
            asset_multiplier_val: Optional[Decimal] = None
            asset_fund_type: Optional[InvestmentFundType] = None

            if isinstance(asset_obj, Option):
                asset_multiplier_val = asset_obj.multiplier
            elif isinstance(asset_obj, InvestmentFund):
                asset_fund_type = asset_obj.fund_type

            # One ledger per account that holds this asset. An asset that appears nowhere with
            # an account still gets its single DEFAULT ledger, so a caller building assets
            # directly, and every single-account export, behave exactly as before.
            for ledger_account in sorted(ledger_accounts.get(asset_id) or {DEFAULT_ACCOUNT}):
                ledger = FifoLedger(
                    asset_internal_id=asset_id, asset_category=asset_obj.asset_category,
                    asset_multiplier_from_asset=asset_multiplier_val,
                    currency_converter=currency_converter, exchange_rate_provider=exchange_rate_provider,
                    internal_working_precision=internal_calculation_precision,
                    decimal_rounding_mode=decimal_rounding_mode,
                    fund_type=asset_fund_type
                )

                # This account's own events only -- the disposal consumes its own lots.
                # Key each event ONCE and carry the key into the stream. Computing it
                # again at stream.add() would repeat every warning get_event_sort_key
                # emits (e.g. a historical trade with no ibkr_transaction_id).
                sorted_hist_keys_and_events: List[Tuple[Any, FinancialEvent]] = []
                if asset_id in historical_events_by_asset:
                    try:
                        sorted_hist_keys_and_events = sorted(
                            ((get_event_sort_key(e, asset_resolver), e)
                             for e in historical_events_by_asset[asset_id]
                             if account_key(e.account_id) == ledger_account),
                            key=lambda keyed: keyed[0],
                        )
                    except ValueError as e:
                        logger.critical(f"Fatal error sorting historical events for asset {asset_obj.get_classification_key()} (ID: {asset_id}): {e}. Cannot guarantee deterministic order for FIFO init. Aborting.")
                        raise e

                ledger.begin_historical_simulation(asset_obj)
                ledger.announce_historical_simulation(asset_obj, len(sorted_hist_keys_and_events))
                for hist_key, hist_event in sorted_hist_keys_and_events:
                    _defer(
                        Phase.LEDGER_EVENTS, hist_key,
                        (lambda l=ledger, a=asset_obj, e=hist_event:
                            l.apply_historical_event(a, e, tax_year)),
                        label=f"sec:{asset_obj.get_classification_key()}",
                    )

                fifo_ledgers[(ledger_account, asset_id)] = ledger
    securities_ledger_count = len(fifo_ledgers)

    # Mergers join the chronological stream at their own date, not a phase of
    # their own: §20 Abs. 4a Satz 6 EStG fixes the moment a Kapitalmassnahme
    # takes effect at the Einbuchung into the depot (GT-ESTG20-018), so the
    # transferred lots must exist for that day's disposals. Ordering them after
    # the whole window instead was issue #56.
    if historical_merger_events:
        logger.info(f"Streaming {len(historical_merger_events)} historical stock merger(s) chronologically...")
        for merger_event in historical_merger_events:
            try:
                merger_key = get_event_sort_key(merger_event, asset_resolver)
            except ValueError as e:
                logger.critical(f"Fatal error sorting historical merger events: {e}. Aborting.")
                raise e
            _defer(
                Phase.LEDGER_EVENTS, merger_key,
                (lambda m=merger_event: _replay_historical_merger(m, fifo_ledgers)),
                label="merger",
            )
    else:
        logger.info("No historical stock mergers to replay.")

    # Internal transfers made before the tax year join the same chronological stream, at
    # their own sort position -- the merger's precedent, on the account axis instead of the
    # asset axis. The handover relocates the moved lots between the two accounts' ledgers;
    # its sort position (the corp-action band, so before that day's trades) is what places
    # the arriving lots before a same-day sale out of the receiving account.
    if historical_transfer_events:
        logger.info(f"Streaming {len(historical_transfer_events)} historical internal "
                    f"transfer(s) chronologically...")
        for transfer_event in historical_transfer_events:
            try:
                transfer_key = get_event_sort_key(transfer_event, asset_resolver)
            except ValueError as e:
                logger.critical(f"Fatal error sorting historical transfer events: {e}. Aborting.")
                raise e
            _defer(
                Phase.LEDGER_EVENTS, transfer_key,
                (lambda t=transfer_event: apply_internal_transfer(
                    t, fifo_ledgers, asset_resolver, data_gap_collector)),
                label="transfer",
            )
    else:
        logger.info("No historical internal transfers to replay.")

    # Reconcile: securities ledgers against the reported snapshot at each mark, after every
    # ledger event of that interval (mergers included) has been applied. Currency ledgers
    # reconcile against cash balances at the final mark only — see below.
    mark_outcomes: List[Tuple[Asset, "MarkReconciliation"]] = []
    currency_reconcilers: List[Any] = []

    def _reconcile_security_soy(ledger, asset_obj, reported):
        try:
            # This account's OWN opening record, not the person's total: each ledger holds one
            # account's lots and reconciles against the row that account reported. A missing
            # row is a reported zero -- the snapshot says so by not listing the account.
            mark_outcomes.append((asset_obj, ledger.reconcile_with_soy_position(
                asset_obj, tax_year, reported)))
        except ValueError as e:
            logger.critical(f"Fatal error reconciling SOY for asset {asset_obj.get_classification_key()} (ID: {asset_obj.internal_asset_id}): {e}. Aborting.")
            raise e

    def _reconcile_security_mark(ledger, asset_obj, mark_year: int, reported):
        try:
            mark_outcomes.append((asset_obj, ledger.reconcile_with_mark(
                asset_obj,
                reported_quantity=reported.quantity if reported else Decimal(0),
                reported_cost_basis=reported.cost_basis_amount if reported else None,
                reported_cost_basis_currency=reported.cost_basis_currency if reported else None,
                mark_label=f"{mark_year}-12-31",
                fallback_acquisition_date=f"{mark_year}-12-31",
                # Same rule the final mark uses: the first day after the mark.
                fx_conversion_date=date(mark_year + 1, 1, 1),
            )))
        except ValueError as e:
            logger.critical(f"Fatal error reconciling the {mark_year}-12-31 mark for asset "
                            f"{asset_obj.get_classification_key()}: {e}. Aborting.")
            raise e

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

    # Which accounts hold which currency, and therefore which currency ledgers exist -- the
    # mirror of `ledger_accounts` for securities, and needed for the same reason: a disposal
    # consumes the balance of the account it was made from ([GT-FX-009]), so every account
    # that touches a currency needs its own queue of lots.
    #
    # Three sources. The CLOSING balances are deliberately NOT one, exactly as the closing
    # snapshot is not a source for securities: an account reporting a balance it never
    # acquired is a divergence to report, and giving it a ledger would not make it one. The
    # end-of-year check reads the report directly.
    #   * the cash report's OPENING balances, recorded per (account, currency) in
    #     soy_positions ([GT-ESTG20-061]). An account holding a currency from before the
    #     input window has no event anywhere, and without a ledger its balance would
    #     silently vanish.
    #   * the historical events, by the account that made them.
    #   * the tax year's own events, likewise.
    currency_ledger_accounts: DefaultDict[uuid.UUID, Set[str]] = defaultdict(set)
    for (_account, _asset_id), _snap in soy_positions.items():
        _cash_obj = asset_resolver.get_asset_by_id(_asset_id)
        if (isinstance(_cash_obj, CashBalance) and (_cash_obj.currency or "").upper() != "EUR"
                and _snap.quantity is not None):
            currency_ledger_accounts[_asset_id].add(_account)

    def _register_currency_event_account(event) -> None:
        for ccy in _currencies_of_event(event):
            ccy_asset = asset_resolver.get_cash_balance_asset(ccy)
            if ccy_asset is None:
                continue
            currency_ledger_accounts[ccy_asset.internal_asset_id].add(
                account_key(event.account_id))
            # A cash move names a second ACCOUNT: the balance arrives there and is acquired
            # there ([GT-FX-009]), so the receiving side needs a ledger even when it appears
            # nowhere else in the input.
            to_account_id = getattr(event, "to_account_id", None)
            if to_account_id:
                currency_ledger_accounts[ccy_asset.internal_asset_id].add(
                    account_key(to_account_id))

    for _events in historical_currency_events.values():
        for _event in _events:
            _register_currency_event_account(_event)
    for _event in current_year_events:
        _register_currency_event_account(_event)

    currency_replay_counts: Dict[str, list] = {}
    for currency_code in sorted(currencies_to_init):
        currency_asset = asset_resolver.get_cash_balance_asset(currency_code)
        if not currency_asset:
            continue

        # An asset that appears nowhere with an account still gets its one DEFAULT ledger,
        # so a caller building assets directly, and every single-account run, behave as
        # before. Same rule as the securities loop above.
        accounts_for_currency = sorted(
            currency_ledger_accounts.get(currency_asset.internal_asset_id) or {DEFAULT_ACCOUNT})

        for ledger_account in accounts_for_currency:
            # Ensure CashBalance asset and ledger exist (creation is unordered setup, not
            # stream work — the stream replays EVENTS).
            _ensure_currency_ledger_exists(
                currency_code, ledger_account, asset_resolver, currency_fifo_ledgers,
                fifo_ledgers, currency_converter, exchange_rate_provider,
                internal_calculation_precision, decimal_rounding_mode,
                f"Currency init {currency_code}"
            )

            currency_ledger = currency_fifo_ledgers.get(
                (ledger_account, currency_asset.internal_asset_id))
            if not currency_ledger:
                continue

            # Stream every historical event with a currency impact THIS ACCOUNT made;
            # per-currency relative order = get_event_sort_key (ties: insertion seq).
            # Events of different currencies commute, and so now do events of different
            # accounts — one ledger each.
            hist_events = [e for e in historical_currency_events.get(currency_code, [])
                           if _currency_event_touches_account(e, ledger_account)]
            if hist_events:
                counter_key = f"{currency_code}@{ledger_account}"
                currency_replay_counts[counter_key] = [0, len(hist_events)]

                def _apply_ccy_event(event, led=currency_ledger, ccy=currency_code,
                                     acct=ledger_account, ck=counter_key):
                    currency_replay_counts[ck][0] += _apply_historical_currency_event(
                        event, led, ccy, currency_converter, ctx, ledger_account=acct,
                    )

                for hist_event in hist_events:
                    try:
                        hist_key = get_event_sort_key(hist_event, asset_resolver)
                    except ValueError as e:
                        # Fatal, like the securities branch above and the merger branch
                        # between them: an event that cannot be placed in the chronology
                        # cannot be replayed, and the replay order fixes the EUR cost basis
                        # of every currency lot it touches. Unreachable as things stand --
                        # the event separation loop at the top of this function already
                        # builds a sort key for every event and drops the ones that raise.
                        logger.critical(f"Fatal error sorting historical currency event {hist_event.event_id} "
                                        f"for {currency_code}: {e}. Cannot guarantee deterministic order "
                                        f"for FIFO init. Aborting.")
                        raise
                    _defer(
                        Phase.LEDGER_EVENTS, hist_key,
                        (lambda e=hist_event, f=_apply_ccy_event: f(e)),
                        label=f"ccy:{currency_code}",
                    )

            # SOY quantity is authoritative - always reconcile to match it -- of THIS
            # account, because that account's balance is the Kapitalforderung ([GT-FX-009]).
            # An account with no row in the cash report has no reported balance
            # (soy_positions.get returns None) and is left alone by the reconciler, which is
            # not the same as reconciling it to zero.
            # Currencies reconcile at the FINAL mark only: the intermediate marks come from
            # the Positions files, which report securities, and no per-year cash-balance
            # snapshot is loaded. Currency events still replay in strict chronological order
            # across the whole window, because the intervals are contiguous and ordered.
            if isinstance(currency_asset, CashBalance):
                reported_snapshot = soy_positions.get(
                    (ledger_account, currency_asset.internal_asset_id))
                currency_reconcilers.append(
                    (lambda l=currency_ledger, a=currency_asset, c=currency_code,
                            acct=ledger_account, snap=reported_snapshot:
                        (f"reconcile-ccy:{c}@{acct}",
                         _reconcile_currency_soy(l, a, tax_year, exchange_rate_provider,
                                                 ctx, snap)))
                )

    # === Run the historical replay, one interval per checkpoint mark ===
    #
    # A partial ledger is the normal starting condition, not a defect: the transaction files
    # reach back only so far. The position snapshots are the ground truth to recover from, and
    # there is one at the close of every year. So the window is cut at each mark; the interval
    # is replayed; the reconstruction is compared and either kept or replaced by the snapshot;
    # and the next interval starts from a state the broker vouches for.
    #
    # The consequence that matters: a defect can no longer propagate past the next mark. Before
    # this, one oversell in 2021 offset a ledger for every year that followed.
    mark_years = sorted(y for y in mark_positions if y < tax_year - 1)
    interval_ends = [date(y, 12, 31) for y in mark_years] + [date(tax_year - 1, 12, 31)]

    def _interval_of(event_date) -> int:
        for index, end in enumerate(interval_ends):
            if event_date <= end:
                return index
        # Unreachable: every deferred item is a historical event, so it predates the tax year
        # and therefore the final interval's end. Kept so a future caller cannot drop work.
        return len(interval_ends) - 1

    buckets: List[List[Tuple[Any, Any, Any, str]]] = [[] for _ in interval_ends]
    for phase, sort_key, apply_fn, label in deferred_items:
        buckets[_interval_of(sort_key[0])].append((phase, sort_key, apply_fn, label))

    logger.info("Historical replay in %d interval(s), marks at %s.",
                len(interval_ends), ", ".join(str(e) for e in interval_ends))

    for index, interval_end in enumerate(interval_ends):
        is_final_mark = index == len(interval_ends) - 1
        stream = ReplayStream()
        for phase, sort_key, apply_fn, label in buckets[index]:
            stream.add(phase, sort_key, apply_fn, label=label)

        for (ledger_account, asset_id), ledger in fifo_ledgers.items():
            asset_obj = asset_resolver.get_asset_by_id(asset_id)
            if not asset_obj:
                continue
            # `_ensure_currency_ledger_exists` registers each currency ledger in BOTH
            # `currency_fifo_ledgers` and `fifo_ledgers`. Currencies reconcile against cash
            # balances through `_reconcile_currency_soy`, never against a Positions snapshot,
            # so they must be excluded here. Before checkpointing this held only because the
            # securities reconcile items were built before the currency ledgers existed —
            # an ordering accident, and one the interval loop would otherwise have inherited.
            if asset_obj.asset_category == AssetCategory.CASH_BALANCE:
                continue
            if is_final_mark:
                reported = soy_positions.get((ledger_account, asset_id))
                stream.add(
                    Phase.RECONCILE, (0,),
                    (lambda l=ledger, a=asset_obj, r=reported: _reconcile_security_soy(l, a, r)),
                    label=f"reconcile-sec:{asset_obj.get_classification_key()}",
                )
            else:
                mark_year = mark_years[index]
                reported = mark_positions.get(mark_year, {}).get((ledger_account, asset_id))
                stream.add(
                    Phase.RECONCILE, (0,),
                    (lambda l=ledger, a=asset_obj, y=mark_year, r=reported:
                        _reconcile_security_mark(l, a, y, r)),
                    label=f"reconcile-mark{mark_year}:{asset_obj.get_classification_key()}",
                )

        if is_final_mark:
            for reconciler in currency_reconcilers:
                stream.add(Phase.RECONCILE, (0,), reconciler, label="reconcile-ccy")

        logger.info("Interval %d/%d (through %s): %d stream item(s).",
                    index + 1, len(interval_ends), interval_end, len(stream))
        stream.run()

        # The interval has been replayed AND reconciled, so the ledgers now describe
        # the holding at the close of this calendar year — the count Rz. 18.4
        # multiplies by, and the only moment that year's declared Vorabpauschale can
        # be spread over the lots that bore it. The final mark is handled below,
        # after this run's own figure for that year has been computed.
        # The amount an EARLIER year declared is looked up or asked for right here,
        # and applied to the lots while they are live.
        #
        # Deferring it to one batch after the replay reads better — the questions
        # would arrive in a block instead of sprinkled through the replay's log —
        # and it is wrong. A merger rebuilds the lots it transfers, and `_take_newest`
        # rebuilt them at a mark until this change; a deferred amount would arrive
        # holding a reference to a lot the ledger no longer has, and the year's
        # deduction would vanish without a word. Applied here, every later
        # transformation carries or scales the figure with the units.
        if not is_final_mark and _year_can_bear_a_vorabpauschale(mark_years[index]):
            _attribute_declared_vorabpauschale(
                fifo_ledgers=fifo_ledgers, asset_resolver=asset_resolver,
                calendar_year=mark_years[index],
                declaration_store=declaration_store,
                ask=ask_for_declared_vorabpauschale,
                held_at_tax_year_opening=funds_held_at_tax_year_opening,
                ctx=ctx, unattributed=unattributed_fund_years)

    _grade_mark_outcomes(mark_outcomes, data_gap_collector)

    # Placing the merger ahead of its day's trades (see engine/replay.py) is
    # right for the target — the delivered shares exist before that day's
    # disposals — and is the wrong end of the day for the source: a purchase of
    # the old instrument booked on the merger date lands in the source ledger
    # *after* the drain and can never transfer. The source then reconciles
    # against a reported zero and the lots are dropped, cost basis and all,
    # with nothing in the output to say so.
    #
    # It is a narrow case (a trade in an instrument on the day its ISIN is
    # replaced) and no input here exhibits it, but it is the price of a single
    # intra-day slot and it must not be silent. Every offender is collected
    # before raising, so one run names the whole problem.
    if historical_merger_events:
        orphaned: List[str] = []
        for merger_event in historical_merger_events:
            source_ledger = fifo_ledgers.get(
                (account_key(merger_event.account_id), merger_event.asset_internal_id))
            if source_ledger is None:
                continue
            leftover = (sum(lot.quantity for lot in source_ledger.lots)
                        + sum(lot.quantity_shorted for lot in source_ledger.short_lots))
            if leftover:
                source_asset = asset_resolver.get_asset_by_id(merger_event.asset_internal_id)
                name = (source_asset.get_classification_key() if source_asset
                        else str(merger_event.asset_internal_id))
                orphaned.append(
                    f"{name}: {leftover} unit(s) remain after the merger on "
                    f"{merger_event.event_date} transferred its holding away")
        if orphaned:
            raise ProcessingError(
                "Historical replay: a merged-away instrument still holds lots after the "
                "replay. The merger is applied before that day's trades, so an acquisition "
                "of the old instrument booked on or after the merger date cannot transfer "
                "and would be discarded silently at reconciliation. "
                + "; ".join(orphaned))

    # The lots as they stand right here are the holding at the close of the
    # preceding calendar year: the historical replay has run and been reconciled
    # against the opening snapshot, and not one event of the tax year has been
    # applied yet. That is precisely the count Rz. 18.4 multiplies by for the
    # Vorabpauschale of calendar `tax_year - 1`, and each lot carries the
    # acquisition date § 18 Abs. 2 reduces by.
    #
    # It has to be taken now. Once the tax year's own trades have consumed and
    # created lots the ledgers describe the end of the tax year and the moment is
    # gone.
    vorabpauschale_opening_lots = _snapshot_fund_lots(fifo_ledgers, asset_resolver)

    # --- Vorabpauschale for calendar `tax_year - 1`, and its attribution to lots ---
    #
    # Computed HERE, not after the tax year's events, for the same reason the
    # snapshot above is taken here: this run's own figure is what this return
    # declares on Zeilen 9-13, and § 19 Abs. 1 Satz 3 deducts it from a disposal of
    # the very units it was computed on. It therefore has to reach those lots
    # before the tax year's first sale consumes them. Until #63 it was computed
    # some 400 lines below, which was harmless only because nothing downstream of
    # it touched a lot.
    vorabpauschale_year = tax_year - 1
    vorabpauschale_data_items = _compute_vorabpauschale_for_prior_year(
        financial_events=financial_events,
        asset_resolver=asset_resolver,
        currency_converter=currency_converter,
        tax_year=tax_year,
        opening_lots_by_asset=vorabpauschale_opening_lots,
        prior_year_positions_available=prior_year_positions_available,
        prior_soy_positions=prior_soy_positions,
        prior_eoy_positions=prior_eoy_positions,
        prior_opening_positions=prior_opening_positions,
        ctx=ctx,
        data_gap_collector=data_gap_collector,
    )

    if _year_can_bear_a_vorabpauschale(vorabpauschale_year):
        _attribute_declared_vorabpauschale(
            fifo_ledgers=fifo_ledgers, asset_resolver=asset_resolver,
            calendar_year=vorabpauschale_year,
            declared_by_asset=_declared_for_the_preceding_year(
                asset_resolver=asset_resolver,
                vorabpauschale_items=vorabpauschale_data_items,
                vorabpauschale_year=vorabpauschale_year,
                declaration_store=declaration_store,
                tax_year=tax_year,
                data_gap_collector=data_gap_collector,
            ),
            # This return declares the preceding calendar year, so every fund is
            # in the mapping above and nothing is asked.
            held_at_tax_year_opening=funds_held_at_tax_year_opening,
            ctx=ctx, unattributed=unattributed_fund_years)

    # A holding-period year whose close is not a checkpoint mark has no reported
    # holding to distribute that year's declared total over, so the deduction
    # cannot reach the lots however the year was declared. Scanned from the lots
    # that survive into the tax year, because those are the ones a disposal can
    # consume.
    _scan_for_unattributable_years(
        opening_lots_by_asset=vorabpauschale_opening_lots,
        asset_resolver=asset_resolver,
        attributable_years=set(mark_years) | {vorabpauschale_year},
        tax_year=tax_year,
        unattributed=unattributed_fund_years,
    )

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
    internal_transfer_processor = InternalTransferProcessor()
    internal_cash_transfer_processor = InternalCashTransferProcessor()

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
        FinancialEventType.INTERNAL_TRANSFER: internal_transfer_processor,
        FinancialEventType.INTERNAL_CASH_TRANSFER: internal_cash_transfer_processor,
    }

    logger.info(f"Processing {len(current_year_events)} current tax year events using dispatch table...")
    for event_idx, event in enumerate(current_year_events):
        asset_object = asset_resolver.get_asset_by_id(event.asset_internal_id)
        if not asset_object:
            raise ProcessingError(f"Event {event.event_id} ({event.event_type.name}) references unknown asset {event.asset_internal_id}. Asset resolution failure.")

        # The disposal consumes the lots of the account it was made from -- Rz. 97 Satz 2,
        # [GT-ESTG20-013]. Every account this asset's events name has a ledger
        # (`ledger_accounts` was built from those same events), so a miss here is a cash
        # balance or an option, both handled in the branches below.
        ledger = fifo_ledgers.get((account_key(event.account_id), asset_object.internal_asset_id))
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
                    # An internal transfer that cannot be resolved (a sub-day split) is
                    # routed to the report through this, at FAIL_FAST -- see transfer_processor.
                    'data_gap_collector': data_gap_collector,
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
                        fx_currency_code, account_key(event.account_id), asset_resolver,
                        currency_fifo_ledgers, fifo_ledgers,
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


    logger.info("Performing End-of-Year (EOY) quantity validation per account...")
    eoy_mismatch_errors = 0
    # Every (account, asset) that has either a ledger or a reported closing row. Checking each
    # account on its own is the point of per-Depot tracking: a misplacement that nets to the
    # person's correct total -- 90 held where 100 was, 110 where 100 was -- passes a
    # person-level check and fails here. Currency (cash balance) is validated separately below.
    for (ledger_account, asset_id) in sorted(set(fifo_ledgers) | set(eoy_positions)):
        asset_obj = asset_resolver.get_asset_by_id(asset_id)
        if not asset_obj or asset_obj.asset_category == AssetCategory.CASH_BALANCE:
            continue

        subject = asset_obj.description or asset_obj.get_classification_key()
        if ledger_account != DEFAULT_ACCOUNT:
            subject = f"{subject} [Konto {ledger_account}]"

        ledger = fifo_ledgers.get((ledger_account, asset_id))
        calculated_eoy_qty: Decimal

        if ledger:
            calculated_eoy_qty = ledger.get_current_position_quantity()
        else:
            calculated_eoy_qty = Decimal(0)
            opening = soy_positions.get((ledger_account, asset_id))
            if opening is not None and opening.quantity not in (None, Decimal(0)):
                logger.warning(f"EOY Validation: {subject} had SOY qty {opening.quantity} but no ledger found at EOY. Calculated EOY assumed 0.")

        closing = eoy_positions.get((ledger_account, asset_id))
        reported_eoy_qty = closing.quantity if closing else None
        try:
            tolerance_exponent = -(ctx.prec // 2)
            comparison_tolerance = Decimal('1e' + str(tolerance_exponent))
        except Exception:
            logger.warning(f"Could not calculate dynamic tolerance from precision {ctx.prec}. Using fixed tolerance 1e-8.")
            comparison_tolerance = Decimal('1e-8')

        if reported_eoy_qty is not None:
            if abs(calculated_eoy_qty - reported_eoy_qty) > comparison_tolerance:
                logger.error(
                    f"CRITICAL EOY MISMATCH for {subject} (ID: {asset_id}): "
                    f"Calculated EOY Qty: {calculated_eoy_qty}, Reported EOY Qty (from file): {reported_eoy_qty}. "
                    f"Difference: {calculated_eoy_qty - reported_eoy_qty}"
                )
                eoy_mismatch_errors += 1
                if data_gap_collector is not None:
                    data_gap_collector.record(
                        code="EOY_QTY_MISMATCH",
                        subject=subject,
                        detail=(f"Berechnete EoY-Stückzahl {calculated_eoy_qty} weicht von der im "
                                f"Broker-Report gemeldeten ({reported_eoy_qty}) ab."),
                    )
        elif abs(calculated_eoy_qty) > comparison_tolerance:
            logger.error(
                f"EOY MISMATCH for {subject} (ID: {asset_id}): "
                f"Calculated EOY Qty: {calculated_eoy_qty}, but asset NOT found in EOY positions report (implying reported EOY Qty is 0)."
            )
            eoy_mismatch_errors += 1
            if data_gap_collector is not None:
                data_gap_collector.record(
                    code="EOY_QTY_MISMATCH",
                    subject=subject,
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

    # Currency EOY validation: each account's ledger against THAT ACCOUNT's reported closing
    # balance. Run per (account, currency) for the same reason the securities check is: a
    # ledger too high in one account and too low in another agrees with the broker on the
    # person's total, and every disposal in both has been matched against the wrong lots.
    #
    # The pairs checked are every currency ledger there is, plus every pair the cash report
    # states (in eoy_positions). **The second half is defensive and is NOT demonstrated to
    # matter** -- probed by deleting it, which leaves the suite green. It cannot matter for a
    # real export, because the cash report states an opening and a closing balance on the
    # same row and an opening balance is one of the sources that creates a ledger, so every
    # reported pair already has one. Kept for a caller that supplies balances directly with
    # only a closing figure, where the ledger set would miss an account reporting a balance
    # it never acquired. The securities check above unions the closing snapshot for a reason
    # that *is* demonstrated; this is the same shape without the same evidence, and saying so
    # is cheaper than implying otherwise.
    logger.info("Performing currency EOY quantity validation per account...")
    currency_eoy_mismatches = 0
    currency_pairs = sorted(
        {(acct, aid) for (acct, aid) in currency_fifo_ledgers}
        | {(acct, aid) for (acct, aid) in eoy_positions},
        key=lambda pair: (str(pair[1]), pair[0]),
    )
    for ledger_account, asset_id in currency_pairs:
        asset_obj = asset_resolver.get_asset_by_id(asset_id)
        if not isinstance(asset_obj, CashBalance):
            continue
        if asset_obj.currency and asset_obj.currency.upper() == "EUR":
            continue

        closing = eoy_positions.get((ledger_account, asset_id))
        reported_eoy = closing.quantity if closing else None
        if reported_eoy is None:
            continue

        ledger = currency_fifo_ledgers.get((ledger_account, asset_id))
        if ledger:
            long_qty = sum(lot.quantity for lot in ledger.lots)
            short_qty = sum(lot.quantity_shorted for lot in ledger.short_lots)
            calculated_eoy = long_qty - short_qty
        else:
            calculated_eoy = Decimal("0")

        # Named only when there is an account to name, so a run over one account reports
        # exactly what it reported before.
        subject = str(asset_obj.currency)
        if ledger_account != DEFAULT_ACCOUNT:
            subject = f"{subject} (Konto {ledger_account})"

        currency_tolerance = Decimal("0.01")
        diff = calculated_eoy - reported_eoy
        if abs(diff) > currency_tolerance:
            logger.warning(
                f"CURRENCY EOY MISMATCH {subject}: "
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
            # §20 Abs. 2 Satz 1 Nr. 7 gains computed from it.
            if data_gap_collector is not None:
                data_gap_collector.record(
                    code="CURRENCY_EOY_MISMATCH",
                    subject=subject,
                    detail=(f"FIFO-Bestand {calculated_eoy:.2f} weicht vom gemeldeten "
                            f"Kontostand {reported_eoy:.2f} ab (Differenz {diff:.2f}). "
                            f"Mögliche Ursachen: Zeitraum der Cash-Balance-Datei, oder "
                            f"nicht erfasste Ein-/Auszahlungen, Margin-Zinsen oder Gebühren."),
                )
        else:
            logger.debug(f"Currency EOY OK {subject}: FIFO={calculated_eoy:.2f}, Reported={reported_eoy:.2f}")

    if currency_eoy_mismatches > 0:
        logger.warning(f"Currency EOY validation: {currency_eoy_mismatches} mismatches found. "
                      f"Common causes: cash balance CSV dates don't match tax year, "
                      f"or untracked currency-impacting events (deposits, withdrawals, "
                      f"margin interest, broker fees not in cash transactions CSV).")
    else:
        logger.info("Currency EOY validation passed.")

    # The Vorabpauschale itself was computed before the tax year's events, at the
    # moment the ledgers described the close of `tax_year - 1`, and attributed to
    # the lots there. What remains here is the report of the holding-period years
    # that never reached a lot, which needs the disposals to be known.
    _record_unattributed_vorabpauschale(
        unattributed_fund_years, realized_gains_losses, tax_year, data_gap_collector)

    processed_income_events_for_output: List[FinancialEvent] = list(current_year_events)

    logger.info(f"Calculation engine finished. Produced {len(realized_gains_losses)} RealizedGainLoss records.")
    logger.info(f"Calculation engine produced {len(vorabpauschale_data_items)} VorabpauschaleData records.")

    return realized_gains_losses, vorabpauschale_data_items, processed_income_events_for_output, eoy_mismatch_errors


def _compute_vorabpauschale_for_prior_year(
    *,
    financial_events: List[FinancialEvent],
    asset_resolver: AssetResolver,
    currency_converter: CurrencyConverter,
    tax_year: int,
    opening_lots_by_asset: Dict[uuid.UUID, List["FundUnitTranche"]],
    prior_year_positions_available: bool,
    prior_soy_positions: "SnapshotsByAccount",
    prior_eoy_positions: "SnapshotsByAccount",
    prior_opening_positions: "SnapshotsByAccount",
    ctx: Context,
    data_gap_collector: Optional[DataGapCollector],
) -> List[VorabpauschaleData]:
    """The Vorabpauschale this return declares: the one FOR calendar `tax_year - 1`.

    It is deemed to flow on the first working day of `tax_year` (18 Abs. 3 InvStG),
    and Zeilen 9-13 take "die Ihnen im Jahr <tax_year> als zugeflossen geltenden
    Vorabpauschalen". Until 2026-08-03 the engine computed the VP for the tax year
    itself and declared it in that same year -- one year early, with the wrong
    Basiszins and the wrong reference prices.
    See reference/investment-tax-law/invstg-18-vorabpauschale.md.
    """
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
        opening_lots_by_asset=opening_lots_by_asset,
        prior_soy_positions=prior_soy_positions,
        prior_eoy_positions=prior_eoy_positions,
        prior_opening_positions=prior_opening_positions,
        ctx=ctx,
        data_gap_collector=data_gap_collector,
    )
    logger.info(
        f"Vorabpauschale calculation produced {len(vorabpauschale_data_items)} records "
        f"for calendar {vorabpauschale_year} (declared in VZ {tax_year})."
    )
    return vorabpauschale_data_items


def _declared_for_the_preceding_year(
    *,
    asset_resolver: AssetResolver,
    vorabpauschale_items: List[VorabpauschaleData],
    vorabpauschale_year: int,
    declaration_store: Optional["VorabpauschaleDeclarationStore"],
    tax_year: int,
    data_gap_collector: Optional[DataGapCollector],
) -> Dict[uuid.UUID, Decimal]:
    """What counts as declared for calendar `tax_year - 1`, per fund.

    **This return is the declaration.** The Anleitung to Zeile 53 admits the
    deduction *"nur, soweit Sie diese Vorabpauschalen der Besteuerung unterworfen
    haben (Zeile 9 bis 13)"* ([GT-INVSTG-034]), and for the preceding calendar
    year Zeilen 9-13 are on this very form, carrying exactly the figures computed
    above. So the run's own figure is the declared amount -- not a recomputation
    standing in for a record, which is what it would be for any earlier year.

    Where the year has already been committed -- the return was filed and the run
    is being repeated -- the **declared** figure governs instead, because that is
    what was brought to tax, and any difference is reported so it can be dealt
    with while the return is still amendable.
    """
    computed_by_asset = {
        item.asset_internal_id: item.gross_vorabpauschale_eur
        for item in vorabpauschale_items
        if item.vorabpauschale_year == vorabpauschale_year
    }

    declared: Dict[uuid.UUID, Decimal] = {}
    for asset_id, asset_obj in asset_resolver.assets_by_internal_id.items():
        if not isinstance(asset_obj, InvestmentFund):
            continue
        computed = computed_by_asset.get(asset_id, Decimal("0.00"))
        entry = (declaration_store.get(asset_obj.get_classification_key(), vorabpauschale_year)
                 if declaration_store is not None else None)
        if entry is None:
            declared[asset_id] = computed
            continue

        declared[asset_id] = entry.gross_eur
        if entry.gross_eur != computed:
            detail = (
                f"Fuer das Kalenderjahr {vorabpauschale_year} sind EUR {entry.gross_eur} "
                f"als erklaert erfasst ({entry.source}, erfasst am "
                f"{entry.declared_on.isoformat()}); dieser Lauf berechnet EUR {computed}. "
                f"Der Abzug nach § 19 Abs. 1 Satz 3 InvStG bleibt auf den erklaerten "
                f"Betrag begrenzt. Weicht die Berechnung ab, weil die Engine "
                f"zwischenzeitlich korrigiert wurde, ist die Erklaerung fuer VZ "
                f"{tax_year} zu pruefen, solange sie noch aenderbar ist."
            )
            if data_gap_collector is not None:
                data_gap_collector.record(
                    code=DIVERGES_CODE,
                    subject=f"{asset_obj.get_classification_key()} "
                            f"({asset_obj.description or ''}) {vorabpauschale_year}",
                    detail=detail, severity=GapSeverity.WARNING,
                )
            else:
                logger.warning("[%s] %s: %s", DIVERGES_CODE,
                               asset_obj.get_classification_key(), detail)
    return declared


def _scan_for_unattributable_years(
    *,
    opening_lots_by_asset: Dict[uuid.UUID, List["FundUnitTranche"]],
    asset_resolver: AssetResolver,
    attributable_years: set,
    tax_year: int,
    unattributed: List["UnattributedFundYear"],
) -> None:
    """Name the holding-period years the replay never stopped at.

    Distributing a fund-year's declared total over its tranches needs the holding
    as it stood at that year's close, and the replay only has one where
    `Positions-{Y}-EoY.csv` supplied a checkpoint mark. Without it the year cannot
    reach a lot however faithfully it was declared -- a different failure from an
    undeclared year, and reported under its own code.

    Scanned over the lots that survive into the tax year: a lot present when the
    tax year opens was held at the close of every year from its acquisition
    onwards, because nothing but a disposal removes it.
    """
    for asset_id, tranches in opening_lots_by_asset.items():
        asset_obj = asset_resolver.get_asset_by_id(asset_id)
        if asset_obj is None:
            continue

        # Units whose acquisition date reconciliation invented have no knowable
        # holding period, so no year of one can be established for them -- not the
        # earliest, and not the § 18 Abs. 2 weight of any single year. The
        # reconstruction being discarded is already reported by the mark grading;
        # this names what it costs on Zeile 53, which is a deduction of zero
        # against a gain the disposal declares in full.
        undated = [t for t in tranches if not t.acquisition_date_is_known]
        if undated:
            unattributed.append(UnattributedFundYear(
                asset_internal_id=asset_id,
                classification_key=asset_obj.get_classification_key(),
                description=asset_obj.description or "",
                calendar_year=tax_year - 1,
                code=NOT_ATTRIBUTABLE_CODE,
                reason=(f"{sum((t.quantity for t in undated), Decimal(0))} Anteile "
                        f"tragen ein bei der Abstimmung gesetztes Ersatz-"
                        f"Anschaffungsdatum; ihr Besitzzeitraum ist damit unbekannt "
                        f"und es laesst sich keine Vorabpauschale auf sie aufteilen"),
            ))

        dated = [t for t in tranches if t.acquisition_date_is_known]
        if not dated:
            continue
        first_year = min(t.acquisition_date.year for t in dated)
        for year in range(first_year, tax_year):
            if year in attributable_years:
                continue
            if not _year_can_bear_a_vorabpauschale(year):
                continue
            unattributed.append(UnattributedFundYear(
                asset_internal_id=asset_id,
                classification_key=asset_obj.get_classification_key(),
                description=asset_obj.description or "",
                calendar_year=year,
                code=NOT_ATTRIBUTABLE_CODE,
                reason=(f"zum Ende des Kalenderjahres {year} liegt kein gemeldeter "
                        f"Bestand vor (Positions-{year}-EoY.csv fehlt), auf den sich "
                        f"eine erklaerte Vorabpauschale aufteilen liesse"),
            ))


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


@dataclass(frozen=True)
class FundUnitTranche:
    """
    Units of one fund held at a moment, and when they were acquired.

    `acquisition_date_is_known` is False where the historical replay could not
    reconstruct the lot and the opening snapshot supplied only the quantity.
    The date is then a placeholder, and § 18 Abs. 2 must not be applied to it.
    """
    quantity: Decimal
    acquisition_date: date
    acquisition_date_is_known: bool = True

    def abs2_retained_twelfths(self, calendar_year: int) -> int:
        """
        Twelfths of the Vorabpauschale these units keep, per § 18 Abs. 2.

        The rule itself lives in `engine/vorabpauschale_attribution.py`, because
        the Zeile 53 distribution key is the same rule and the two must not be
        able to drift apart. All this adds is the refusal below.
        """
        if not self.acquisition_date_is_known:
            raise ProcessingError(
                "Vorabpauschale: § 18 Abs. 2 was asked for the acquisition month "
                "of units whose acquisition date the engine invented. The caller "
                "must drop the fund before reaching here.")
        return abs2_retained_twelfths(self.acquisition_date, calendar_year)


def _snapshot_fund_lots(fifo_ledgers, asset_resolver) -> Dict[uuid.UUID, List[FundUnitTranche]]:
    """
    Take the investment-fund lots as they stand, with their acquisition dates.

    Called once, at the only moment the ledgers describe the close of the
    preceding calendar year. Short lots are ignored: a short fund position is
    not a holding of Investmentanteile and Rz. 18.4 counts units *verwahrt oder
    verwaltet*.
    """
    snapshot: Dict[uuid.UUID, List[FundUnitTranche]] = {}
    for (_account, asset_id), ledger in fifo_ledgers.items():
        asset_obj = asset_resolver.get_asset_by_id(asset_id)
        if not isinstance(asset_obj, InvestmentFund):
            continue
        for lot in ledger.lots:
            try:
                acquired = date.fromisoformat(lot.acquisition_date)
            except (TypeError, ValueError) as e:
                raise ProcessingError(
                    f"Vorabpauschale: lot of {asset_obj.get_classification_key()} "
                    f"carries an unreadable acquisition date {lot.acquisition_date!r}. "
                    "§ 18 Abs. 2 reduces by the month of acquisition, so it cannot "
                    "be guessed.") from e
            snapshot.setdefault(asset_id, []).append(
                FundUnitTranche(
                    quantity=lot.quantity, acquisition_date=acquired,
                    acquisition_date_is_known=getattr(
                        lot, "acquisition_date_is_known", True)))
    return snapshot


def _year_can_bear_a_vorabpauschale(calendar_year: int) -> bool:
    """Could ANY fund have owed a Vorabpauschale for this calendar year?

    § 18 Abs. 1 Satz 2 multiplies the year-start price by the Basiszins, so a year
    whose Basiszins is not positive yields a non-positive Basisertrag for every
    fund and no Vorabpauschale for any of them ([GT-INVSTG-010], [GT-INVSTG-050]).
    2021 and 2022 are such years. Nothing could have been declared for them, so a
    Zeile 53 deduction covering them is not missing -- it does not exist -- and
    demanding a declaration record would be noise.

    This is a derivation from the law as the registry holds it, not an assumption
    about the data.
    """
    from src.tax_law.registry import basiszins_pct
    basiszins = basiszins_pct(calendar_year)
    return basiszins is not None and basiszins > Decimal(0)


@dataclass(frozen=True)
class UnattributedFundYear:
    """One (fund, calendar year) whose Vorabpauschale never reached a lot.

    Collected rather than recorded on the spot for two reasons. It is only a gap
    where units of that fund were actually disposed of in the tax year -- which is
    not known until the tax year has been processed -- and one report naming every
    fund and year is worth more than a gap per line.
    """
    asset_internal_id: uuid.UUID
    classification_key: str
    description: str
    calendar_year: int
    code: str
    reason: str


def _attribute_declared_vorabpauschale(
    *,
    fifo_ledgers: Dict[Tuple[str, uuid.UUID], FifoLedger],
    asset_resolver: AssetResolver,
    calendar_year: int,
    ctx: Context,
    unattributed: List[UnattributedFundYear],
    held_at_tax_year_opening: Set[uuid.UUID],
    declared_by_asset: Optional[Dict[uuid.UUID, Decimal]] = None,
    declaration_store: Optional["VorabpauschaleDeclarationStore"] = None,
    ask: Optional[Callable] = None,
) -> None:
    """Spread one calendar year's declared Vorabpauschalen over the lots holding them.

    Called at the close of each calendar year of the replay -- the one moment the
    ledgers describe the holding Rz. 18.4 counts ([GT-INVSTG-017]) -- so that when
    units are disposed of later, § 19 Abs. 1 Satz 3 has a per-lot figure to deduct.

    Two ways the amount arrives, and they are not interchangeable:

    - `declared_by_asset` -- used for the calendar year THIS return declares. The
      figures are on the form being produced, so there is nothing to ask about.
    - otherwise the **declaration store**, and where it has no answer, `ask`. This
      is a year on a return already filed. What it declared is not something this
      engine can compute, and its own recomputation is not a substitute: the
      Anleitung to Zeile 53 admits the deduction only so far as the amount was
      brought to tax ([GT-INVSTG-034]).

    **The question is worth asking even when the expected answer is "nothing".**
    Anyone whose earlier returns were filed before this engine could compute a
    Vorabpauschale declared nothing for those years, and will never find out that
    it costs them a deduction unless something asks. A `--no-interactive` run
    cannot ask -- and therefore must not assume: it records the year as unanswered
    and deducts nothing.

    **Only funds still held when the tax year opens are considered.** A fund sold
    before then cannot reach this return's Zeile 53: no disposal this year can
    consume lots it no longer has. Without this the run asked about years that
    could not move a figure -- measured on VZ 2025, all three questions it put
    were about funds whose opening position was zero, and each belonged to the
    VZ 2024 return, not this one. Asking a person to look up a filed return for
    nothing is how a prompt that matters gets dismissed.

    The test is the reported opening position rather than the ledger, because at
    an intermediate mark the ledger does not yet describe the tax year's opening.
    The two agree by construction: reconciliation pins the final ledger to exactly
    that snapshot.

    Anything that cannot be attributed is collected, never approximated.
    """
    from src.processing.vorabpauschale_declarations import DeclarationStatus

    for asset_id, asset_obj in asset_resolver.assets_by_internal_id.items():
        if not isinstance(asset_obj, InvestmentFund):
            continue
        if asset_id not in held_at_tax_year_opening:
            continue
        lots = aggregate_lots(fifo_ledgers, asset_id)
        if not lots:
            continue

        def _unattributed(code: str, reason: str) -> None:
            unattributed.append(UnattributedFundYear(
                asset_internal_id=asset_id,
                classification_key=asset_obj.get_classification_key(),
                description=asset_obj.description or "",
                calendar_year=calendar_year, code=code, reason=reason))

        if declared_by_asset is not None:
            declared = declared_by_asset.get(asset_id)
        else:
            key = asset_obj.get_classification_key()
            entry = (declaration_store.get(key, calendar_year)
                     if declaration_store is not None else None)
            if entry is None and ask is not None:
                entry = ask(asset_obj, calendar_year)
                if entry is not None and declaration_store is not None:
                    declaration_store.commit(key, calendar_year, entry)
                    declaration_store.save()
            if entry is None:
                _unattributed(
                    DECLARATION_UNKNOWN_CODE,
                    f"fuer das Kalenderjahr {calendar_year} liegt keine Angabe vor, "
                    f"ob und in welcher Hoehe eine Vorabpauschale erklaert wurde")
                continue
            if entry.status is DeclarationStatus.NOT_DECLARED:
                _unattributed(
                    NOT_DECLARED_CODE,
                    f"fuer das Kalenderjahr {calendar_year} wurde nach eigener "
                    f"Angabe nichts erklaert ({entry.source})")
                continue
            declared = entry.gross_eur

        if declared is None:
            _unattributed(
                DECLARATION_UNKNOWN_CODE,
                f"fuer das Kalenderjahr {calendar_year} liegt keine Angabe vor, "
                f"ob und in welcher Hoehe eine Vorabpauschale erklaert wurde")
            continue
        if declared <= Decimal(0):
            continue

        try:
            distribute_declared_vorabpauschale(
                lots, calendar_year=calendar_year, declared_gross_eur=declared, ctx=ctx)
        except ProcessingError as e:
            _unattributed(
                NOT_ATTRIBUTABLE_CODE,
                f"die erklaerten EUR {declared} fuer {calendar_year} lassen sich "
                f"nicht auf die Tranchen aufteilen: {e}")


def _record_unattributed_vorabpauschale(
    unattributed: List[UnattributedFundYear],
    realized_gains_losses: List[RealizedGainLoss],
    tax_year: int,
    data_gap_collector: Optional[DataGapCollector],
) -> None:
    """Report the holding-period years that reached no lot, for funds actually sold.

    Three conditions, reported apart because the reader has to do a different
    thing about each: a year the taxpayer says was never declared (recoverable, by
    correcting that year's declaration), a year nobody has been asked about
    (answerable, by running interactively), and a year that cannot be split over
    the tranches at all. Rolling them into one message was the first version, and
    it left the most actionable of the three — a lost deduction the taxpayer can
    still recover — indistinguishable from a missing input file.

    Severity is WARNING for all three, and the direction is what makes that
    honest: a year left out means the deduction is smaller and the declared gain
    therefore **larger**, so the figures are conservative rather than
    income-understating. What the taxpayer loses is money, which is why the fund
    and the year are named instead of the condition being logged and forgotten.

    Nothing is reported for a fund whose units were not disposed of: Zeile 53 does
    not arise for it, and an undeclared year costs nothing until units are sold.
    """
    disposed = {
        rgl.asset_internal_id for rgl in realized_gains_losses
        if rgl.asset_category_at_realization == AssetCategory.INVESTMENT_FUND
    }
    relevant = [u for u in unattributed if u.asset_internal_id in disposed]
    if not relevant or data_gap_collector is None:
        for entry in relevant:
            logger.warning("[%s] %s @ %d: %s", entry.code, entry.classification_key,
                           entry.calendar_year, entry.reason)
        return

    # One report per condition, because the three call for different things. What
    # they share is the direction: a year left out makes the deduction smaller and
    # the declared gain LARGER, so the figures are conservative — and the taxpayer
    # is out of pocket, which is why each says what to do about it.
    remedies = {
        NOT_DECLARED_CODE: (
            "Fuer diese Jahre wurde nach eigener Angabe keine Vorabpauschale "
            "erklaert. Nach der Anleitung zu Zeile 53 mindert eine Vorabpauschale "
            "den Veraeusserungsgewinn nur, soweit sie der Besteuerung unterworfen "
            "wurde (Zeilen 9-13) — der Abzug entfaellt also, solange die Erklaerung "
            "des betreffenden Jahres unveraendert bleibt, und der Gewinn wird "
            "insoweit doppelt erfasst. Den Betrag, der dort anzusetzen gewesen "
            "waere, zeigt ein Lauf mit --tax-year <Jahr+1>. Wird die Erklaerung "
            "berichtigt, tragen Sie den erklaerten Betrag hier ein (der Lauf fragt "
            "danach) — der Abzug steht dann ab dem naechsten Lauf zur Verfuegung. "
            "Ob eine bereits eingereichte Erklaerung noch geaendert werden kann, "
            "entscheidet dieses Programm nicht."),
        DECLARATION_UNKNOWN_CODE: (
            "Fuer diese Jahre ist nicht bekannt, ob eine Vorabpauschale erklaert "
            "wurde, und es wird deshalb nichts abgezogen — angenommen wird nichts. "
            "Starten Sie den Lauf interaktiv (ohne --no-interactive); er fragt je "
            "Fonds und Jahr danach und merkt sich die Antwort."),
        NOT_ATTRIBUTABLE_CODE: (
            "Fuer diese Jahre laesst sich ein erklaerter Betrag nicht auf die "
            "veraeusserten Anteile aufteilen — es fehlt der gemeldete Bestand zum "
            "Jahresende, oder Anschaffungsdaten wurden bei der Abstimmung ersetzt. "
            "Ohne diese Zuordnung waere jeder Abzug geraten."),
    }

    for code in (NOT_DECLARED_CODE, DECLARATION_UNKNOWN_CODE, NOT_ATTRIBUTABLE_CODE):
        entries = sorted((u for u in relevant if u.code == code),
                         key=lambda u: (u.classification_key, u.calendar_year))
        if not entries:
            continue
        named = "; ".join(
            f"{u.classification_key} ({u.description}) {u.calendar_year}: {u.reason}"
            for u in entries)
        years = sorted({u.calendar_year for u in entries})
        data_gap_collector.record(
            code=code,
            subject=f"Anlage KAP-INV Zeile 53 ({tax_year}), "
                    f"{len(entries)} Fonds-Jahr(e): "
                    + ", ".join(str(y) for y in years),
            detail=(
                f"Fuer {len(entries)} Fonds-Jahr(e) im Besitzzeitraum veraeusserter "
                f"Anteile wird keine Vorabpauschale nach § 19 Abs. 1 Satz 3 InvStG "
                f"abgezogen. {named}. {remedies[code]}"
            ),
            severity=GapSeverity.WARNING,
        )


def _price_stichtag(recorded: Optional[date], by_convention: date) -> date:
    """The day a price was set: the one recorded with it, else the convention.

    `recorded` is set by the parsing layer wherever it knows the day -- always
    for a price read from a snapshot, and in particular for a price substituted
    from the close of the preceding year, which is the case no rule keyed on the
    Vorabpauschale year can derive.

    Falling back is not a substituted *value*: `by_convention` is the same
    naming rule the file was selected by (`Positions-{X}-SoY.csv` is X's first
    trading day; see src/data_preparation.py and src/utils/snapshot_dates.py),
    so it restates an assumption already made rather than inventing a new one.
    Issue #59 replaces the convention with a report date the export carries, at
    which point the fallback becomes unreachable on real input.
    """
    return recorded if recorded is not None else by_convention


def _calculate_vorabpauschale(
    asset_resolver: AssetResolver,
    distributions_by_asset: Dict[uuid.UUID, Decimal],
    currency_converter: CurrencyConverter,
    vorabpauschale_year: int,
    opening_lots_by_asset: Dict[uuid.UUID, List[FundUnitTranche]],
    prior_soy_positions: "SnapshotsByAccount",
    prior_eoy_positions: "SnapshotsByAccount",
    prior_opening_positions: "SnapshotsByAccount",
    ctx: Context,
    data_gap_collector: Optional[DataGapCollector] = None,
) -> List[VorabpauschaleData]:
    """
    Calculate the Vorabpauschale FOR calendar year `vorabpauschale_year`.

    **`vorabpauschale_year` is not the Veranlagungszeitraum.** The VP for calendar X is deemed
    to flow on the first working day of X+1 (18 Abs. 3 InvStG) and is declared on Zeilen 9-13
    of the *X+1* Anlage KAP-INV. Callers preparing a VZ Y return must pass Y-1. All position
    values and distributions read here are therefore those of `vorabpauschale_year`, taken from
    the `prior_*_positions` registries, not the tax year's own SoY/EoY snapshot. Each is
    recorded per (account, asset); what 18 reads is the person's figure over them
    ([GT-ESTG20-061]), and it is the same figure whichever accounts the units sit in
    because Abs. 1 is written per unit.

    **Everything up to the last step is per Investmentanteil**, because that is how Abs. 1 is
    written -- every quantity in Saetze 1 to 3 is a Ruecknahmepreis or a distribution *of one
    unit*. The unit count enters once, at the end, through Rz. 18.4. Working in position values
    instead conflated a price change with a quantity change in the Satz 3 cap, whose two sides
    were measured over different holdings.

      Abs. 1 S. 2  basisertrag_je_anteil = preis_jahresbeginn * basiszins * 0.7
      Abs. 1 S. 3  basisertrag_je_anteil <= (preis_letzt - preis_erst) + ausschuettung_je_anteil
      Abs. 1 S. 1  vp_je_anteil = max(0, basisertrag_je_anteil - ausschuettung_je_anteil)
      Abs. 2       vp_je_anteil * k/12, k = 12 less one per full month before the
                   month of acquisition
      Rz. 18.4     VP = SUM over tranches of vp_je_anteil * k/12 * units
      Abs. 4       basiszins from the published BMF table for `vorabpauschale_year`

    **Satz 1 comes before Abs. 2 and the order is load-bearing.** Abs. 2 reduces *"die
    Vorabpauschale"*, which Satz 1 defines as the shortfall against the Basisertrag, so the
    twelfths multiply what the distributions left. Rz. 18.3 works it in that order --
    [GT-INVSTG-056]. The two orders differ by ausschuettungen * (12 - k)/12, and the reversed
    one can drive the figure below zero and drop a fund that owes something.

    The unit count is the holding at the close of 31 December of the Vorabpauschale year
    (Rz. 18.4), taken from `opening_lots_by_asset` -- the ledger's own lots at that moment,
    which is also where each tranche's acquisition date comes from. § 18 Abs. 2 then reduces
    each tranche by one twelfth for every full month before its month of acquisition.

    Applying Abs. 2 per tranche is what Rz. 18.11 does: its worked example reduces the
    *per-Anteil* Vorabpauschale, at a point before any unit count has entered, so the factor
    belongs to the units acquired rather than to the position. Settled 2026-08-07 and recorded
    against GT-INVSTG-011 in docs/legal-implementation-map.md; it is no longer a choice under
    uncertainty. The one part no source works through is summing the factor tranche by tranche
    for a holding acquired in several instalments.

    Teilfreistellung (20 InvStG) is applied to derive the net figure; the gross figure is what
    goes on the form.

    Still not implemented, rather than silently approximated: Abs. 1 S. 4 (Boersen- oder
    Marktpreis only where no Ruecknahmepreis was set) -- GT-INVSTG-036.

    **A fund whose Satz 2 or Satz 3 price cannot be used is not skipped.** It is
    collected and reported as one `VORABPAUSCHALE_PRICE_UNUSABLE` FAIL_FAST gap naming
    every affected fund, at the foot of this function -- see the comment there for the
    two boundaries on that. Four separate `continue`s did it silently until 2026-08-09
    (issue #55). Passing no `data_gap_collector` restores the silent skip, which is why
    the pipeline always passes one.
    """
    from src.utils.tax_utils import get_teilfreistellung_rate_for_fund_type

    from src.tax_law.registry import basiszins_pct
    basiszins = basiszins_pct(vorabpauschale_year)  # None -> loud warning inside the registry
    if basiszins is None:
        return []

    base_return_rate = ctx.multiply(basiszins, Decimal("0.01"))  # Convert percentage to factor
    factor_70 = Decimal("0.7")

    # Rz. 18.6 converts each input at the ECB reference rate of its OWN Stichtag
    # (GT-INVSTG-018), and a Stichtag is the day a price was set -- never a fixed
    # calendar date. These were hardcoded to 2 January and 31 December until
    # 2026-08-08. Measured against the first/last-business-day convention, 2 January
    # is the year's first trading day in only two of 2021-2025, and in 2021 and 2022
    # it is a Saturday and a Sunday -- days the ECB publishes no rate for, so the
    # converter's fallback quietly supplied one from another day. 31 December falls
    # on a weekend in 2022 and 2023 and had the same defect, unrecorded until then.
    #
    # The day travels with the price, in the snapshot's `mark_price_date`, because
    # the substitution path takes its price from the close of the PRECEDING year and
    # no rule keyed on `vorabpauschale_year` can know that.
    eoy_conversion_date_default = last_business_day_of_year(vorabpauschale_year)

    results: List[VorabpauschaleData] = []
    funds_without_acquisition_dates: List[Tuple[str, str]] = []
    # Every fund dropped for want of a usable Satz 2 or Satz 3 price, with the
    # reason. Collected rather than recorded on the spot for the same reason as
    # the list above: the gap is FAIL_FAST and raises as it is recorded, so one
    # entry per fund would stop at the first and hide the rest.
    funds_without_a_usable_price: List[Tuple[str, str, str]] = []

    for asset_id, asset_obj in asset_resolver.assets_by_internal_id.items():
        if not isinstance(asset_obj, InvestmentFund):
            continue
        # Rz. 18.4: the units held at the close of 31 December of the Vorabpauschale
        # year. Nothing held then means no Vorabpauschale -- which is also how a fund
        # disposed of during the year drops out (GT-INVSTG-016). That follows from this
        # count alone: the statute has no disposal counterpart to Abs. 2, so units gone
        # by 31 December are simply not multiplied. Do not reason it from the Abs. 3
        # Zuflussfiktion, which fixes when income is received, not whether it arises.
        tranches = opening_lots_by_asset.get(asset_id, [])

        # § 18 Abs. 2 turns on the month each tranche was acquired. Where the
        # historical replay could not reconstruct a lot, the opening snapshot
        # gave the quantity and the engine invented the date. No Vorabpauschale
        # is computed from an invented date -- not reduced by it, and not
        # quietly treated as though the units had always been held.
        undated = [t for t in tranches if not t.acquisition_date_is_known]
        if undated:
            # Abs. 2 asks one thing of a tranche: was it acquired *during* this
            # calendar year? A date is one way to answer that and not the only
            # one. Units the reconstruction could not place, but which the
            # broker already reported at the close of the year before, were
            # demonstrably acquired before this year began -- the snapshot is
            # the evidence, and no reduction applies to them. That is a
            # derivation from a report actually held, not a guess at a date.
            opened_with = person_snapshot(prior_opening_positions, asset_id)
            held_before_the_year = (
                (opened_with.quantity if opened_with is not None else None) or Decimal(0))
            undated_units = sum((t.quantity for t in undated), Decimal(0))
            if undated_units > held_before_the_year:
                funds_without_acquisition_dates.append(
                    (asset_obj.get_classification_key(), asset_obj.description or "",
                     undated_units, held_before_the_year))
                logger.warning(
                    "Fund %s: %s units held at the close of %d cannot be placed in "
                    "time -- the reconstruction has no date for them and the close "
                    "of %d accounts for only %s. No Vorabpauschale computed.",
                    asset_obj.get_classification_key(), undated_units,
                    vorabpauschale_year, vorabpauschale_year - 1, held_before_the_year)
                continue

            logger.info(
                "Fund %s: %s undated units were already held at the close of %d, "
                "so 18 Abs. 2 does not reduce them.",
                asset_obj.get_classification_key(), undated_units,
                vorabpauschale_year - 1)

        units_at_year_end = sum((t.quantity for t in tranches), Decimal(0))
        if units_at_year_end <= Decimal('0'):
            logger.debug(f"Fund {asset_obj.description}: nothing held at the close of "
                         f"{vorabpauschale_year}. No VP.")
            continue

        # Abs. 1 S. 2: the Ruecknahmepreis at the start of the year, PER UNIT.
        prior_soy = person_snapshot(prior_soy_positions, asset_id)
        soy_conversion_date = _price_stichtag(
            prior_soy.mark_price_date if prior_soy is not None else None,
            first_business_day_of_year(vorabpauschale_year))
        soy_price_foreign = prior_soy.mark_price if prior_soy is not None else None
        soy_currency = ((prior_soy.mark_price_currency if prior_soy is not None else None)
                        or asset_obj.currency)
        if soy_price_foreign is None or soy_currency is None:
            logger.warning(f"Fund {asset_obj.description} (ID: {asset_id}): No start-of-{vorabpauschale_year} price. No VP; collected for the gap report.")
            funds_without_a_usable_price.append((
                asset_obj.get_classification_key(), asset_obj.description or "",
                f"kein Ruecknahmepreis zum Jahresbeginn {vorabpauschale_year} "
                "(§ 18 Abs. 1 Satz 2 InvStG)"))
            continue

        soy_price_eur = currency_converter.convert_to_eur(soy_price_foreign, soy_currency, soy_conversion_date)
        if soy_price_eur is None:
            logger.warning(f"Fund {asset_obj.description} (ID: {asset_id}): Failed to convert start-of-{vorabpauschale_year} price to EUR. No VP; collected for the gap report.")
            funds_without_a_usable_price.append((
                asset_obj.get_classification_key(), asset_obj.description or "",
                f"der Preis zum Jahresbeginn ({soy_price_foreign} {soy_currency} zum "
                f"{soy_conversion_date.isoformat()}) konnte nicht in EUR umgerechnet "
                "werden -- kein EZB-Referenzkurs fuer diesen Stichtag (Rz. 18.6)"))
            continue

        # Abs. 1 S. 3: the last Ruecknahmepreis set in the year, PER UNIT.
        prior_eoy = person_snapshot(prior_eoy_positions, asset_id)
        eoy_conversion_date = _price_stichtag(
            prior_eoy.mark_price_date if prior_eoy is not None else None,
            eoy_conversion_date_default)
        eoy_price_foreign = prior_eoy.mark_price if prior_eoy is not None else None
        eoy_currency = ((prior_eoy.mark_price_currency if prior_eoy is not None else None)
                        or asset_obj.currency)
        if eoy_price_foreign is None or eoy_currency is None:
            logger.warning(f"Fund {asset_obj.description} (ID: {asset_id}): No end-of-{vorabpauschale_year} price though units were held at the close. No VP; collected for the gap report.")
            funds_without_a_usable_price.append((
                asset_obj.get_classification_key(), asset_obj.description or "",
                f"kein Ruecknahmepreis zum Jahresende {vorabpauschale_year}, obwohl "
                "zum 31.12. Anteile gehalten wurden -- die Deckelung nach § 18 "
                "Abs. 1 Satz 3 InvStG ist damit nicht berechenbar"))
            continue

        eoy_price_eur = currency_converter.convert_to_eur(eoy_price_foreign, eoy_currency, eoy_conversion_date)
        if eoy_price_eur is None:
            logger.warning(f"Fund {asset_obj.description} (ID: {asset_id}): Failed to convert end-of-{vorabpauschale_year} price to EUR. No VP; collected for the gap report.")
            funds_without_a_usable_price.append((
                asset_obj.get_classification_key(), asset_obj.description or "",
                f"der Preis zum Jahresende ({eoy_price_foreign} {eoy_currency} zum "
                f"{eoy_conversion_date.isoformat()}) konnte nicht in EUR umgerechnet "
                "werden -- kein EZB-Referenzkurs fuer diesen Stichtag (Rz. 18.6)"))
            continue

        distributions_eur = distributions_by_asset.get(asset_id, Decimal('0'))
        distribution_per_unit = ctx.divide(distributions_eur, units_at_year_end)

        # Abs. 1 S. 2, per unit.
        basisertrag_per_unit = ctx.multiply(
            ctx.multiply(soy_price_eur, base_return_rate), factor_70)

        # Abs. 1 S. 3, per unit: capped at the year's price gain plus what was
        # distributed on one unit. The cap is a ceiling, and a fund that lost value
        # has a negative one, so the floor at zero is the cap's own doing.
        cap_per_unit = ctx.add(
            ctx.subtract(eoy_price_eur, soy_price_eur), distribution_per_unit)
        basisertrag_per_unit = min(basisertrag_per_unit, cap_per_unit)
        if basisertrag_per_unit <= Decimal('0'):
            logger.debug(f"Fund {asset_obj.description}: per-unit Basisertrag "
                         f"{basisertrag_per_unit} <= 0 after the Satz 3 cap. VP=0.")
            continue

        # Abs. 1 S. 1, per unit: the Vorabpauschale is what the distributions
        # fell short of. It is subtracted HERE, before the Abs. 2 twelfths,
        # because Abs. 2 reduces "die Vorabpauschale" -- the amount Satz 1
        # defines -- and not the Basisertrag. Rz. 18.3 computes in exactly this
        # order and Rz. 18.11 then takes the twelfths of what remains
        # ([GT-INVSTG-056]). The other order was this engine's until 2026-08-09
        # and understated by distributions * (12 - k)/12.
        vp_per_unit = ctx.subtract(basisertrag_per_unit, distribution_per_unit)
        if vp_per_unit <= Decimal('0'):
            logger.debug(f"Fund {asset_obj.description}: distributions per unit "
                         f"({distribution_per_unit}) >= per-unit Basisertrag "
                         f"({basisertrag_per_unit}). VP=0.")
            continue

        # Rz. 18.4 with Abs. 2: multiply by the units, tranche by tranche, each
        # reduced by a twelfth for every full month before its month of acquisition.
        gross_vp = Decimal(0)
        for tranche in tranches:
            if tranche.acquisition_date_is_known:
                twelfths = tranche.abs2_retained_twelfths(vorabpauschale_year)
            else:
                # An undated tranche only reaches here past the check above, which
                # established from the report that these units were already held
                # when the year opened. They are therefore not in their year of
                # acquisition and keep twelve twelfths -- [GT-INVSTG-011],
                # reference/investment-tax-law/invstg-18-vorabpauschale.md:131-135.
                # Answered without a date because none was observed and none may be
                # invented: every date before the year gives this same answer, so
                # the question Abs. 2 asks has been settled without one.
                twelfths = 12
            tranche_vp = ctx.multiply(vp_per_unit, tranche.quantity)
            if twelfths != 12:
                tranche_vp = ctx.divide(
                    ctx.multiply(tranche_vp, Decimal(twelfths)), Decimal(12))
                logger.debug(
                    "Fund %s: tranche of %s acquired %s keeps %d/12 (18 Abs. 2).",
                    asset_obj.description, tranche.quantity,
                    tranche.acquisition_date, twelfths)
            gross_vp = ctx.add(gross_vp, tranche_vp)

        # Abs. 1 S. 2 and S. 3 over the whole holding, kept for the report.
        # **Abs. 2 does not enter here.** It reduces the Vorabpauschale, so the
        # Basisertrag is the plain Rz. 18.4 product and a fund bought in
        # December has the same one as a fund held all year. This field carried
        # the twelfths-reduced amount until 2026-08-09, which is a quantity no
        # provision defines.
        basisertrag = ctx.multiply(basisertrag_per_unit, units_at_year_end)

        # Kept for the report: the holding's value at each end of the year, on the
        # Rz. 18.4 count, so both sides describe the same units.
        fund_value_soy_eur = ctx.multiply(soy_price_eur, units_at_year_end)
        fund_value_eoy_eur = ctx.multiply(eoy_price_eur, units_at_year_end)

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

    # One report naming every fund. A FAIL_FAST gap raises as it is recorded, so
    # recording them one by one would stop at the first and hide the rest.
    if funds_without_acquisition_dates and data_gap_collector is not None:
        named = "; ".join(
            f"{key} ({description}): {undated} Anteile ohne Datum, "
            f"Bestand zum Vorjahresende {held}"
            for key, description, undated, held in funds_without_acquisition_dates)
        data_gap_collector.record(
            code="VORABPAUSCHALE_ACQUISITION_DATE_UNKNOWN",
            subject=f"{len(funds_without_acquisition_dates)} Fonds: {named}",
            detail=(
                f"Fuer Anteile, die zum Ende des Kalenderjahres {vorabpauschale_year} "
                "gehalten wurden, konnte die historische Wiedergabe kein "
                "Anschaffungsdatum rekonstruieren; die Menge stammt aus dem "
                "Positions-Snapshot. § 18 Abs. 2 InvStG mindert die Vorabpauschale um "
                "ein Zwoelftel je vollem Monat vor dem Anschaffungsmonat; ob diese "
                "Anteile ueberhaupt unterjaehrig erworben wurden, ist nicht "
                "feststellbar, weil sie auch im Bestand zum Ende des Vorjahres nicht "
                "enthalten sind. Es wurde daher KEINE Vorabpauschale angesetzt, was "
                "die Einkuenfte untererfasst. Die historische Rekonstruktion "
                "widerspricht hier dem Positionsbericht des Brokers -- die Ursache "
                "liegt in den Transaktionsdateien, nicht in fehlenden Preisen."
            ),
            severity=GapSeverity.FAIL_FAST,
        )

    # The same report for a fund whose Satz 2 or Satz 3 price could not be used.
    # Until 2026-08-08 each of these four conditions was a log line and a
    # `continue`, so a fund the engine had itself classified as an investment
    # fund contributed no deemed income and nothing said so -- measured live on
    # 2026-08-07, four funds across VZ 2024 and VZ 2025, with Zeilen 9-13 at
    # 0.00 and an empty gap section (issue #55).
    #
    # FAIL_FAST, for the reason `VORABPAUSCHALE_PRIOR_YEAR_SNAPSHOT_MISSING`
    # already is at whole-year scale: the figure is not zero, it is
    # un-computable, and a zero on Zeile 9 is indistinguishable from a real one.
    #
    # Recorded after the block above so that a tree missing both keeps aborting
    # on the acquisition dates, as it did before this existed -- a FAIL_FAST
    # raises where it is recorded, so only the first of the two is ever seen.
    #
    # One code for all four, with the reason per fund in the detail. #55 asked
    # for the year-start path to be split so that a fund *not held* when the
    # year opened would not abort next to one whose price is genuinely missing;
    # that split now exists a layer up, in `resolve_year_start_prices()`, which
    # prices every fund owing a Vorabpauschale before the engine runs. A second
    # code here would separate nothing and would cost the single report.
    #
    # Guarded on the Basiszins: a year whose rate is not positive yields no
    # Vorabpauschale for any fund, because Abs. 1 Satz 2 multiplies by it, so a
    # price nobody could obtain removed nothing from the declaration. Calendar
    # 2021 and 2022 are such years -- without this, VZ 2023 would start aborting
    # over a zero that is lawful. Same reasoning as the early return in
    # `src/processing/fund_prices.py`.
    if (funds_without_a_usable_price and basiszins > Decimal(0)
            and data_gap_collector is not None):
        named = "; ".join(
            f"{key} ({description}): {reason}"
            for key, description, reason in funds_without_a_usable_price)
        data_gap_collector.record(
            code="VORABPAUSCHALE_PRICE_UNUSABLE",
            subject=f"{len(funds_without_a_usable_price)} Fonds: {named}",
            detail=(
                f"Fuer diese Fonds wurden zum Ende des Kalenderjahres "
                f"{vorabpauschale_year} Anteile gehalten, sodass nach § 18 Abs. 1 "
                "InvStG eine -- gegebenenfalls nach Abs. 2 zeitanteilig geminderte "
                "-- Vorabpauschale anzusetzen waere. Der dafuer benoetigte "
                "Ruecknahmepreis liess sich nicht verwenden; der Grund steht je "
                "Fonds oben. Es wurde daher KEINE Vorabpauschale angesetzt, was die "
                "Einkuenfte untererfasst. Eine Null in den Zeilen 9-13 der Anlage "
                "KAP-INV waere von einer zutreffenden Null nicht zu unterscheiden, "
                "deshalb bricht der Lauf ab."
            ),
            severity=GapSeverity.FAIL_FAST,
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
        account_id=original_event.account_id,
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
    ledger_account: str,
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
    Ensure a CashBalance asset and FIFO ledger exist for the given currency, in the
    account whose balance it is. Creates both on-the-fly if they don't exist yet.
    This makes event processing robust against any CSV/event ordering.

    One ledger per (account, currency), because each account's balance is its own
    Kapitalforderung ([GT-FX-009]). A caller that names no account passes
    DEFAULT_ACCOUNT, which is what a one-account run is.
    """
    if currency_code.upper() == "EUR":
        return

    existing_asset = asset_resolver.get_cash_balance_asset(currency_code.upper())
    if existing_asset:
        # Asset exists; ensure ledger also exists
        if (ledger_account, existing_asset.internal_asset_id) not in fifo_ledgers:
            new_ledger = FifoLedger(
                asset_internal_id=existing_asset.internal_asset_id,
                asset_category=AssetCategory.CASH_BALANCE,
                asset_multiplier_from_asset=None,
                currency_converter=currency_converter,
                exchange_rate_provider=exchange_rate_provider,
                internal_working_precision=internal_calculation_precision,
                decimal_rounding_mode=decimal_rounding_mode,
            )
            currency_fifo_ledgers[(ledger_account, existing_asset.internal_asset_id)] = new_ledger
            fifo_ledgers[(ledger_account, existing_asset.internal_asset_id)] = new_ledger
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
        currency_fifo_ledgers[(ledger_account, new_asset.internal_asset_id)] = new_ledger
        fifo_ledgers[(ledger_account, new_asset.internal_asset_id)] = new_ledger
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

    # The account that made the cash flow: it is that account's balance the dividend lands
    # in or the fee is taken from ([GT-FX-009]).
    cashflow_account = account_key(event.account_id)
    currency_ledger = currency_fifo_ledgers.get((cashflow_account, currency_asset.internal_asset_id))
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
        currency_fifo_ledgers[(cashflow_account, currency_asset.internal_asset_id)] = currency_ledger
        if fifo_ledgers is not None:
            fifo_ledgers[(cashflow_account, currency_asset.internal_asset_id)] = currency_ledger
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


# Cash-flow events that move a currency balance: income creates lots, expense consumes
# them. Named once, because the selection is made in three places -- collecting the
# historical stream, deciding which accounts need a ledger, and applying the impact.
_CURRENCY_MOVING_CASHFLOW_TYPES = (
    FinancialEventType.DIVIDEND_CASH,
    FinancialEventType.DISTRIBUTION_FUND,
    FinancialEventType.INTEREST_RECEIVED,
    FinancialEventType.INTEREST_PAID_STUECKZINSEN,
    FinancialEventType.WITHHOLDING_TAX,
    FinancialEventType.FEE_TRANSACTION,
    FinancialEventType.CAPITAL_REPAYMENT,
)


def _currencies_of_event(event: FinancialEvent) -> List[str]:
    """The non-EUR currencies whose balance this event moves.

    The same selection `_collect_historical_currency_event` makes, expressed as a question
    rather than as a side effect, because the tax year's events have to answer it too: they
    decide which accounts hold which currency, and therefore which currency ledgers exist.
    Keeping one function per phase let the two drift, which is how an account whose only
    currency activity is inside the tax year would get no ledger.
    """
    if isinstance(event, CurrencyConversionEvent):
        return [c.upper() for c in (event.from_currency, event.to_currency)
                if c and c.upper() != "EUR"]

    if isinstance(event, InternalCashTransferEvent):
        ccy = (event.local_currency or "").upper()
        return [ccy] if ccy and ccy != "EUR" else []

    if isinstance(event, TradeEvent):
        ccy = (event.local_currency or "").upper()
        return [ccy] if ccy and ccy != "EUR" else []

    if isinstance(event, CorpActionMergerCash):
        ccy = (event.local_currency or "").upper()
        if ccy and ccy != "EUR" and event.gross_amount_foreign_currency:
            return [ccy]
        return []

    ccy = (getattr(event, 'local_currency', None) or "").upper()
    if ccy and ccy != "EUR" and event.event_type in _CURRENCY_MOVING_CASHFLOW_TYPES:
        return [ccy]
    return []


def _currency_event_touches_account(event: FinancialEvent, ledger_account: str) -> bool:
    """Whether this event moves the balance held in `ledger_account`.

    Every event names the account that made it. A move between the taxpayer's own accounts
    names two, and touches both: the balance leaves one and is acquired in the other
    ([GT-FX-009]). It is replayed once per side, each side applying only its own half, so
    neither ledger has to reach into the other.
    """
    if account_key(event.account_id) == ledger_account:
        return True
    to_account_id = getattr(event, "to_account_id", None)
    return bool(to_account_id) and account_key(to_account_id) == ledger_account


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
    - Moves of a balance between the taxpayer's own accounts

    The selection itself is `_currencies_of_event`, which the tax year's events are put
    through as well. Restating it here is what let the two drift apart.
    """
    for ccy in _currencies_of_event(event):
        historical_currency_events[ccy].append(event)


def _apply_historical_currency_event(
    event: FinancialEvent,
    ledger: 'FifoLedger',
    currency_code: str,
    currency_converter: CurrencyConverter,
    ctx: Context,
    ledger_account: str = DEFAULT_ACCOUNT,
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
    - InternalCashTransferEvent: a balance moved between the taxpayer's own accounts,
      which touches TWO ledgers. `ledger_account` says which side this call is applying.
    """
    replayed = 0
    # Single-iteration loop: the body is kept VERBATIM from the previous batch
    # loop (its `continue` statements mean "this event does not affect this
    # currency" and skip to the return).
    for _ in (0,):
        try:
            if isinstance(event, InternalCashTransferEvent):
                # A disposal of the sending account's Kapitalforderung and an acquisition
                # of the receiving account's, both at the gemeiner Wert of the amount moved
                # ([GT-FX-009], [GT-FX-010]). Replayed once per side; each call applies
                # only the half belonging to `ledger_account`, so neither ledger reaches
                # into the other.
                #
                # No RealizedGainLoss here: this is the historical replay, which rebuilds
                # lot state for years already declared. The gain of a move inside the tax
                # year is produced by `InternalCashTransferProcessor`. Enrichment converted
                # the amount at the day of the move -- the same figure the tax-year
                # processor uses, so the two paths cannot disagree about what a move is
                # worth.
                eur_value = event.gross_amount_eur
                if eur_value is None:
                    # No rate, no figure -- and no skipping either. Skipping leaves the
                    # sending account holding a balance it no longer has and the receiving
                    # one short of what it received; the opening reconciliation then repairs
                    # the QUANTITY against the cash report and synthesises the lots, so the
                    # run continues with acquisition dates nobody measured. Raised rather
                    # than swallowed like the neighbouring branches (issue #49): this one is
                    # new, and the handler below is told to let it through.
                    raise ProcessingError(
                        f"Internal cash transfer of {currency_code} on "
                        f"{event.event_date}: no exchange rate for that day, so the "
                        f"disposal and the acquisition cannot be valued ([GT-FX-010]).")
                if event.quantity <= Decimal("0"):
                    continue
                eur_per_unit = ctx.divide(eur_value.copy_abs(), event.quantity)
                if account_key(event.account_id) == ledger_account:
                    _consume_lots_historical(
                        ledger, event.quantity, eur_per_unit, event.event_date, ctx)
                    replayed += 1
                if account_key(event.to_account_id) == ledger_account:
                    _create_lot_historical(
                        ledger, event.quantity, eur_per_unit, event.event_date,
                        event.ibkr_transaction_id, ctx)
                    replayed += 1

            elif isinstance(event, CurrencyConversionEvent):
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

        except ProcessingError:
            # Deliberately ahead of the catch-all below. That handler is issue #49 --
            # every failure in this function is swallowed at DEBUG, so a condition the
            # engine decided was fatal would be downgraded to a log line nobody reads. A
            # branch that means to stop the run says so by raising this type.
            raise
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
    exchange_rate_provider, ctx: Context,
    reported_snapshot: Optional[PositionSnapshot] = None,
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

    reported_soy = reported_snapshot.quantity if reported_snapshot else None
    reported_soy_cost = reported_snapshot.cost_basis_amount if reported_snapshot else None
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
        if (reported_soy_cost and reported_soy_cost > Decimal("0")
                and abs(diff - reported_soy) <= Decimal("0.01")):
            # Full SOY amount missing - use the provided total cost basis
            total_cost = reported_soy_cost
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
