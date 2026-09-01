# src/parsers/parsing_orchestrator.py
import uuid
from dataclasses import replace as dataclasses_replace
from decimal import Decimal, getcontext
from typing import List, Dict, Optional, Any, Set, Tuple
from datetime import datetime, date
import logging
import sys 

from src.domain.assets import (
    Asset, InvestmentFund, Option, CashBalance, Derivative, Stock, Bond, PrivateSaleAsset, Cfd, # Changed Section23EstgAsset to PrivateSaleAsset
    MarkPosition, MarksByAccount, PositionSnapshot, SnapshotsByAccount,
    person_snapshot, snapshots_for_asset,
)
# FinancialEvent, OptionLifecycleEvent, TradeEvent for type hinting
from src.domain.events import (
    FinancialEvent, OptionLifecycleEvent, TradeEvent,
    OptionAssignmentEvent, OptionExerciseEvent, OptionCashSettlementEvent,
)
from src.domain.enums import FinancialEventType, AssetCategory, InvestmentFundType
from src.domain.exceptions import DataIntegrityError, ProcessingError
from src.identification.asset_resolver import AssetResolver
from src.classification.asset_classifier import AssetClassifier
from src.utils.account_utils import DEFAULT_ACCOUNT, account_key
from src.utils.snapshot_dates import (
    first_business_day_of_year, last_business_day_of_year)
from src.utils.sorting_utils import get_event_sort_key
from src.utils.type_utils import parse_ibkr_date
import src.config as global_config 

from .raw_models import (
    RawTradeRecord, RawCashTransactionRecord, RawPositionRecord, RawCorporateActionRecord,
    RawCashBalanceRecord, RawOptionsEAERecord
)
from .trades_parser import parse_trades_csv
from .cash_transactions_parser import parse_cash_transactions_csv
from .positions_parser import parse_positions_csv
from .corporate_actions_parser import parse_corporate_actions_csv
from .cash_balance_parser import parse_cash_balance_csv
from .options_eae_parser import parse_options_eae_csv
from .domain_event_factory import DomainEventFactory
# NEW IMPORTS
from src.processing.option_trade_linker import perform_option_trade_linking
from src.processing.withholding_tax_linker import WithholdingTaxLinker


logger = logging.getLogger(__name__)


def _drop_cancelled_trade_pairs(raw_trades: List[RawTradeRecord]) -> List[RawTradeRecord]:
    """Remove every cancelled booking and the row that cancelled it.

    IBKR books a cancellation as its own row: ``Buy/Sell`` carries the ORIGINAL
    trade's direction word with a ``(Ca.)`` suffix, the quantity is the
    original's negated, ``Notes/Codes`` is ``Ca``, and the transaction id is
    later than the original's. A rebooked row normally follows and stands on its
    own. A cancelled trade did not happen, so the pair is a no-op and neither
    half should reach the ledger.

    Removing the pair is preferred over interpreting the cancellation row,
    because that row carries no ``Open/CloseIndicator``: nothing in it says
    whether the booking it reverses opened a long or closed a short, and the
    rebooked row is not a reliable guide -- on the one instance in this
    repository's input the original was ``oc=C`` and the rebook ``oc=O``.

    Until August 2026 these rows were not recognised at all. ``"BUY (Ca.)"``
    matches neither ``"BUY"`` nor ``"SELL"``, so ``_determine_trade_event_type``
    fell through to inferring direction from the quantity sign and logged
    "Buy/Sell indicator missing" -- which was false, the indicator was present
    and unrecognised. A cancelled BUY became a SELL. In a declared year that
    produces a disposal that never happened, consuming the oldest lots FIFO and
    emitting a realised gain, while the end-of-year quantity still reconciles
    because the rebooked row restores the count.

    An unmatched cancellation raises: it means the input contradicts itself, or
    the booking it reverses lies before the earliest file loaded. Every case is
    collected before raising.
    """
    cancellations = [r for r in raw_trades if "(CA.)" in (r.buy_sell or "").upper()]
    if not cancellations:
        return raw_trades

    def _key(record) -> Tuple[Any, ...]:
        return (record.isin or "", record.conid or "", record.symbol or "",
                record.trade_date or "")

    removed: Set[int] = set()
    unmatched: List[str] = []
    for cancellation in cancellations:
        word = (cancellation.buy_sell or "").upper().replace("(CA.)", "").strip()
        quantity = cancellation.quantity
        candidates = [
            r for r in raw_trades
            if id(r) not in removed
            and r is not cancellation
            and _key(r) == _key(cancellation)
            and (r.buy_sell or "").strip().upper() == word
            and r.quantity == -quantity
            and (r.transaction_id or "") < (cancellation.transaction_id or "")
        ]
        if not candidates:
            unmatched.append(
                f"{cancellation.buy_sell} {cancellation.quantity} of "
                f"{cancellation.isin or cancellation.symbol} on {cancellation.trade_date} "
                f"(transaction {cancellation.transaction_id})")
            continue
        # The nearest preceding booking, where the broker has reused a quantity.
        original = max(candidates, key=lambda r: (r.transaction_id or ""))
        removed.add(id(original))
        removed.add(id(cancellation))
        logger.info(
            "Cancelled trade dropped with its cancellation: %s %s of %s on %s "
            "(original transaction %s, cancellation %s).",
            original.buy_sell, original.quantity,
            original.isin or original.symbol, original.trade_date,
            original.transaction_id, cancellation.transaction_id)

    if unmatched:
        raise DataIntegrityError(
            "Trade cancellation rows with no booking to cancel. A '(Ca.)' row reverses an "
            "earlier trade of the same instrument, date, direction and quantity; without it "
            "the row cannot be applied, and guessing its direction from the quantity sign is "
            "how a cancelled purchase becomes a phantom disposal. "
            f"{len(unmatched)} case(s): " + "; ".join(unmatched))

    return [r for r in raw_trades if id(r) not in removed]


def _sum_snapshot_column(total: Optional[Decimal],
                         addend: Optional[Decimal]) -> Optional[Decimal]:
    """Accumulate one snapshot column across the rows of several accounts.

    A person's holding is the total across their accounts -- [GT-ESTG20-061] --
    and one Flex Query covering several accounts emits one row per account, so a
    quantity or an amount is read by adding rather than by assigning.

    `None` on the left is "nothing recorded yet"; on the right it is "the broker
    left the column blank". A blank is skipped rather than read as zero, so an
    asset whose every row is blank keeps `None` and reaches the guard in
    `_ensure_soy_quantities_are_set`, which refuses a holding reported with no
    cost basis rather than declaring its whole proceeds as gain.

    What that cannot distinguish is one account blank and another filled: the
    total is then the filled one alone, understating the basis. This rests on the
    assumption that every account's row carries the column, which is an assumption
    and not a checked condition. Filling the blank instead is not the answer: a
    substituted cost basis is an invented figure.

    That gap no longer reaches the SoY/EoY reconciliation, which is now per
    account: each ledger reconciles against its own account's record, so an
    account with a blank cost basis is examined on its own -- its reconstruction
    either disagrees with its reported quantity and `_create_fallback_long_lot`
    refuses a holding reported with no basis, or agrees and the reported basis is
    never read. The undetected mixed case is confined to the PERSON-LEVEL view
    this sum still feeds -- `person_snapshot`, i.e. the `prior_year_*` fields and
    the funds-held set -- not to any account's ledger basis.
    """
    if addend is None:
        return total
    if total is None:
        return addend
    return total + addend


def _replace_snapshot_quantity(existing: Optional[PositionSnapshot],
                               quantity: Optional[Decimal]) -> PositionSnapshot:
    """Take the balance from the cash-balance report, keeping the rest of the record.

    Only the quantity: a currency reported in BOTH the Positions snapshot and the
    cash-balance report gets its balance from the second, which is the report written
    for it, while the cost basis and value stay as the Positions row gave them. That
    is the precedence the engine has always had -- the cash-balance pass ran second and
    assigned the two quantities -- and the basis it preserves is what a currency ledger
    that disagrees with its opening balance is reconciled against.
    """
    if existing is None:
        return PositionSnapshot(quantity=quantity)
    return dataclasses_replace(existing, quantity=quantity)


def _one_snapshot_price(existing: Optional[PositionSnapshot],
                        row_price: Optional[Decimal]) -> Optional[Decimal]:
    """The per-unit price the accumulated rows agree on, or `None` where they do not.

    Quantities and amounts belong to the account and are added. A per-unit price is
    not: it describes the instrument, and two rows for one (account, asset) can carry
    two different ones. That happens when the broker reports two contracts the resolver
    treats as one instrument -- the same ISIN listed on two exchanges, both quoted in
    the same currency, so the currency refusal does not catch it. The quantities and
    values still add, because one ISIN is one holding for FIFO ([GT-ESTG20-012]); the
    prices do not, because neither exchange's is the other's.

    Taking one of them would put an arbitrary venue's price on the record, and nothing
    downstream could tell. The end-of-year reconciliation compares quantities, not
    prices, so it would reconcile clean. **The one figure a snapshot price reaches is
    the Vorabpauschale** -- 18 Abs. 1 Satz 2's Ruecknahmepreis where nothing better is
    available, and Satz 3's cap on the Basisertrag. Neither wants a market price from
    one exchange, and no arithmetic turns two of them into the Ruecknahmepreis the
    statute asks for, which is a number the fund sets and not an average of venues.

    So an ambiguous price is recorded as no price, and each consumer already does the
    right thing with that: the diagnostic report prints N/A; `resolve_year_start_prices`
    goes to the stored figure, the issuer's NAV, then the taxpayer, and stops naming the
    fund if nobody can answer; and the Satz 3 cap records `VORABPAUSCHALE_PRICE_UNUSABLE`,
    which stops the run naming the fund rather than capping with a wrong number.

    A row reporting no price adds nothing and leaves the accumulated one standing: a
    blank is the broker omitting a figure, not a second venue disagreeing about it.
    Once dropped the price stays dropped, however many further rows arrive -- which is
    why a price arriving after a blank FIRST row is dropped too, the record having no
    way to tell that state from an earlier disagreement. That needs a blank price to
    exist at all: `MarkPrice` is populated on every row of every Positions export in
    the window, so nothing measurable rests on it, and the direction it errs in is
    towards fetching the Ruecknahmepreis rather than towards guessing it.
    """
    if existing is None:
        return row_price
    if row_price is None:
        return existing.mark_price
    if existing.mark_price is None:
        return None
    return existing.mark_price if existing.mark_price == row_price else None


def _one_snapshot_currency(existing: Optional[str], row_currency: Optional[str],
                           asset: Asset, snapshot_label: str) -> Optional[str]:
    """The single currency the accumulated amounts above are denominated in.

    A currency is a property of the instrument, not of the account holding it,
    so every account's row for one instrument reports the same one and this
    returns what they agree on. Were they ever to disagree, the accumulated
    total would be two currencies added together -- a figure with no meaning
    that no consumer could tell from a real one -- so the disagreement raises
    instead of being resolved by taking one of them.
    """
    if row_currency is None:
        return existing
    if existing is not None and existing != row_currency:
        raise DataIntegrityError(
            f"{snapshot_label} for {asset.get_classification_key()} reports two "
            f"currencies across accounts ({existing} and {row_currency}). The "
            f"person's holding is the total across their accounts, and amounts in "
            f"two currencies cannot be added.")
    return row_currency


class ParsingOrchestrator:
    def __init__(self, asset_resolver: AssetResolver, asset_classifier: AssetClassifier, interactive_classification: bool = True):
        self.asset_resolver = asset_resolver
        self.asset_classifier = asset_classifier
        self.interactive_classification = interactive_classification

        self.raw_trades: List[RawTradeRecord] = []
        self.raw_cash_transactions: List[RawCashTransactionRecord] = []
        self.raw_positions_start: List[RawPositionRecord] = []
        self.raw_positions_end: List[RawPositionRecord] = []
        # Preceding calendar year's snapshots -- Vorabpauschale only.
        self.raw_positions_prior_start: List[RawPositionRecord] = []
        self.raw_positions_prior_end: List[RawPositionRecord] = []
        self.raw_positions_prior_opening: List[RawPositionRecord] = []
        # Checkpoint marks for the historical replay: {year: rows of Positions-{year}-EoY.csv}.
        # Resolved into `mark_positions` once assets exist.
        self.raw_positions_marks: Dict[int, List[RawPositionRecord]] = {}
        self.mark_positions: Dict[int, MarksByAccount] = {}
        # Every snapshot the engine reads, each one record per (account, asset). These
        # registries are the ONLY place any of them is held: FIFO is applied per Depot
        # ([GT-ESTG20-013]) and the person declares the total across their accounts
        # ([GT-ESTG20-061]), and both readings are taken from here -- the second through
        # `person_snapshot`, which derives it rather than storing it.
        self.soy_positions: SnapshotsByAccount = {}
        self.eoy_positions: SnapshotsByAccount = {}
        # The PRECEDING calendar year's snapshots, used ONLY for the Vorabpauschale.
        #
        # The Vorabpauschale declared in VZ Y is the one computed for calendar year Y-1: it is
        # deemed to flow on the first working day of Y (18 Abs. 3 InvStG), and Zeilen 9-13 of
        # the VZ Y Anlage KAP-INV take "die Ihnen im Jahr Y als zugeflossen geltenden
        # Vorabpauschalen". See reference/investment-tax-law/invstg-18-vorabpauschale.md and
        # reference/tax-forms/anlage-kap-inv-zeilen.md. The Basisertrag therefore needs the
        # Ruecknahmepreis at the START of Y-1 and the cap needs the last price set IN Y-1 --
        # neither of which is the tax year's own SoY/EoY snapshot. `prior_opening_positions`
        # is the close of the year BEFORE that: the units the Vorabpauschale year opened
        # with, and the last price set before it began.
        #
        # Abs. 1 is written per Investmentanteil: the prices here are PER UNIT and the unit
        # count enters separately, at the close of 31 December (Rz. 18.4). A single position
        # value carrying both cannot be right for both.
        #
        # Each price carries the day it was set, in `mark_price_date`. Rz. 18.6 converts a
        # foreign-currency figure at the ECB rate of its OWN Stichtag (GT-INVSTG-018), and a
        # Stichtag is a day a price was set -- never a fixed calendar date. Without the day
        # the engine had to assume one, and assumed 2 January: a Saturday in 2021 and a
        # Sunday in 2022. It matters most on the substitution path, where the price comes
        # from the close of the PRECEDING year and a date derived from the Vorabpauschale
        # year would put price and rate in different years.
        self.prior_soy_positions: SnapshotsByAccount = {}
        self.prior_eoy_positions: SnapshotsByAccount = {}
        self.prior_opening_positions: SnapshotsByAccount = {}
        # Which assets a prior-year snapshot was read for, so the pipeline can verify the
        # record still reaches the engine once classification has run. See
        # _verify_prior_year_snapshot_survived_classification.
        self._prior_year_snapshot_assets: Dict[uuid.UUID, Optional[str]] = {}
        # Funds whose Satz 2 price had to be taken from the wrong day. Drained into the
        # data-gap channel by the pipeline, so it reaches the report rather than the log.
        self.vorabpauschale_price_substitutions: List[Tuple[str, str]] = []
        self.raw_corporate_actions: List[RawCorporateActionRecord] = []
        self.raw_cash_balances: List[RawCashBalanceRecord] = []
        self.raw_options_eae: List[RawOptionsEAERecord] = []
        # Whether an OptionEAE file was offered at all, as opposed to offered and empty.
        # Only the wording of _require_option_cash_settlements' error depends on it: the
        # requirement itself comes from the trades, never from the file's presence.
        self.options_eae_file_supplied: bool = False

        self.domain_financial_events: List[FinancialEvent] = []
        # NEW: Store collections for linking
        self.candidate_option_lifecycle_events: List[OptionLifecycleEvent] = []
        self.candidate_stock_trades_for_linking: List[TradeEvent] = []

        self.decimal_sort_key_precision = global_config.PRECISION_QUANTITY


    def load_all_raw_data(self,
                           trades_file: Optional[str] = None,
                           cash_transactions_file: Optional[str] = None,
                           positions_start_file: Optional[str] = None,
                           positions_end_file: Optional[str] = None,
                           positions_prior_start_file: Optional[str] = None,
                           positions_prior_end_file: Optional[str] = None,
                             positions_prior_opening_file: Optional[str] = None,
                           corporate_actions_file: Optional[str] = None,
                           cash_balance_file: Optional[str] = None,
                           options_eae_file: Optional[str] = None,
                           positions_mark_files: Optional[Dict[int, str]] = None):
        # ... (implementation is the same)
        if trades_file:
            self.raw_trades = _drop_cancelled_trade_pairs(parse_trades_csv(trades_file))
            logger.info(f"Loaded {len(self.raw_trades)} raw trade records.")
        if cash_transactions_file:
            self.raw_cash_transactions = parse_cash_transactions_csv(cash_transactions_file)
            logger.info(f"Loaded {len(self.raw_cash_transactions)} raw cash transaction records.")
        if positions_start_file:
            self.raw_positions_start = parse_positions_csv(positions_start_file)
            logger.info(f"Loaded {len(self.raw_positions_start)} raw start-of-year position records.")
        if positions_end_file:
            self.raw_positions_end = parse_positions_csv(positions_end_file)
            logger.info(f"Loaded {len(self.raw_positions_end)} raw end-of-year position records.")
        if positions_prior_start_file:
            self.raw_positions_prior_start = parse_positions_csv(positions_prior_start_file)
            logger.info(f"Loaded {len(self.raw_positions_prior_start)} raw prior-year start-of-year position records (Vorabpauschale).")
        if positions_prior_end_file:
            self.raw_positions_prior_end = parse_positions_csv(positions_prior_end_file)
            logger.info(f"Loaded {len(self.raw_positions_prior_end)} raw prior-year end-of-year position records (Vorabpauschale).")
        if positions_prior_opening_file:
            self.raw_positions_prior_opening = parse_positions_csv(positions_prior_opening_file)
            logger.info(f"Loaded {len(self.raw_positions_prior_opening)} raw opening position records (Vorabpauschale unit count).")
        if corporate_actions_file:
            self.raw_corporate_actions = parse_corporate_actions_csv(corporate_actions_file)
            logger.info(f"Loaded {len(self.raw_corporate_actions)} raw corporate action records.")
        if cash_balance_file:
            self.raw_cash_balances = parse_cash_balance_csv(cash_balance_file)
            logger.info(f"Loaded {len(self.raw_cash_balances)} raw cash balance records.")
        if options_eae_file:
            self.options_eae_file_supplied = True
            self.raw_options_eae = parse_options_eae_csv(options_eae_file)
            logger.info(f"Loaded {len(self.raw_options_eae)} raw OptionEAE records.")
        for mark_year, mark_file in sorted((positions_mark_files or {}).items()):
            self.raw_positions_marks[mark_year] = parse_positions_csv(mark_file)
            logger.info(f"Loaded {len(self.raw_positions_marks[mark_year])} raw position records "
                        f"for the {mark_year}-12-31 checkpoint mark.")

    @staticmethod
    def _record_snapshot_row(snapshots: SnapshotsByAccount, raw_pos: RawPositionRecord,
                             asset: Asset, snapshot_label: str,
                             mark_price_date: Optional[date] = None) -> None:
        """Record one Positions row under the account that reported it.

        A repeat of the same (account, asset) is accumulated rather than overwritten:
        two rows for one instrument in one account are two parts of one holding, and the
        last of them is not the holding. Accumulating across ACCOUNTS is not done here --
        that is `person_snapshot`, and it is the derived view.

        `mark_price_date` is the day the price was set, which the export does not carry:
        it comes from the file the row was read out of, so the caller supplies it. Only
        the preceding year's snapshots need it -- see `prior_soy_positions`.
        """
        key = (account_key(raw_pos.client_account_id), asset.internal_asset_id)
        existing = snapshots.get(key)
        if existing is None:
            snapshots[key] = PositionSnapshot(
                quantity=raw_pos.position,
                cost_basis_amount=raw_pos.cost_basis_money,
                cost_basis_currency=raw_pos.currency_primary,
                position_value=raw_pos.position_value,
                mark_price=raw_pos.mark_price,
                mark_price_currency=raw_pos.currency_primary,
                mark_price_date=mark_price_date,
            )
            return
        snapshots[key] = PositionSnapshot(
            quantity=_sum_snapshot_column(existing.quantity, raw_pos.position),
            cost_basis_amount=_sum_snapshot_column(
                existing.cost_basis_amount, raw_pos.cost_basis_money),
            cost_basis_currency=_one_snapshot_currency(
                existing.cost_basis_currency, raw_pos.currency_primary, asset, snapshot_label),
            position_value=_sum_snapshot_column(
                existing.position_value, raw_pos.position_value),
            # Per unit, so it is not added -- and not simply taken either, since two
            # rows can disagree. See `_one_snapshot_price`.
            mark_price=_one_snapshot_price(existing, raw_pos.mark_price),
            mark_price_currency=_one_snapshot_currency(
                existing.mark_price_currency, raw_pos.currency_primary, asset, snapshot_label),
            mark_price_date=mark_price_date,
        )

    @staticmethod
    def _record_mark_row(marks: MarksByAccount, raw_pos: RawPositionRecord,
                         asset: Asset, mark_label: str) -> None:
        """Record one checkpoint-mark row under the account that reported it.

        The `MarkPosition` counterpart of `_record_snapshot_row`, and it accumulates a
        repeat of the same (account, asset) for the same reason. Quantity and cost basis
        accumulate together: a quantity added up over two rows and a cost basis taken
        from one of them imply a per-unit cost belonging to no holding anybody had, and
        that is the figure a disagreeing reconstruction is replaced by.
        """
        key = (account_key(raw_pos.client_account_id), asset.internal_asset_id)
        existing = marks.get(key)
        quantity = raw_pos.position
        cost_basis = raw_pos.cost_basis_money
        currency = raw_pos.currency_primary
        if existing is not None:
            quantity += existing.quantity
            cost_basis = _sum_snapshot_column(existing.cost_basis_amount, cost_basis)
            currency = _one_snapshot_currency(
                existing.cost_basis_currency, currency, asset, mark_label)
        marks[key] = MarkPosition(
            quantity=quantity,
            cost_basis_amount=cost_basis,
            cost_basis_currency=currency,
        )

    @staticmethod
    def _refuse_mixed_snapshot_currencies(snapshots: Dict[Tuple[str, uuid.UUID], Any],
                                          asset_resolver: AssetResolver,
                                          snapshot_label: str) -> None:
        """One asset, one currency, however many accounts hold it.

        Runs over every snapshot registry -- `PositionSnapshot` and `MarkPosition`
        alike -- because both carry a `cost_basis_currency` and both are summed
        across accounts by their person-level view.

        A currency belongs to the instrument, not to the account holding it, so the rows
        agree. Were they ever to disagree, `person_snapshot` would add two currencies
        together and hand downstream a figure in neither -- one no consumer could tell
        from a real one. Checked here rather than there because this is where the row that
        carried the disagreement can still be named.
        """
        by_asset: Dict[uuid.UUID, Dict[str, str]] = {}
        for (account, asset_id), snap in snapshots.items():
            if snap.cost_basis_currency is None:
                continue
            by_asset.setdefault(asset_id, {})[account] = snap.cost_basis_currency
        offenders = []
        for asset_id, per_account in by_asset.items():
            if len(set(per_account.values())) <= 1:
                continue
            asset = asset_resolver.get_asset_by_id(asset_id)
            key = asset.get_classification_key() if asset else str(asset_id)
            offenders.append(f"{key} ({', '.join(sorted(set(per_account.values())))})")
        if offenders:
            raise DataIntegrityError(
                f"{snapshot_label} reports more than one currency for an instrument across "
                f"accounts. The person's holding is the total across their accounts, and "
                f"amounts in two currencies cannot be added. "
                f"{len(offenders)} instrument(s): " + "; ".join(sorted(offenders)))

    def process_positions(self, tax_year: Optional[int] = None):
        # ... (implementation is the same)
        logger.info("Processing start-of-year positions...")
        for raw_pos in self.raw_positions_start:
            asset = self.asset_resolver.get_or_create_asset(
                raw_isin=raw_pos.isin, raw_conid=raw_pos.conid, raw_symbol=raw_pos.symbol,
                raw_currency=raw_pos.currency_primary, raw_ibkr_asset_class=raw_pos.asset_class,
                raw_description=raw_pos.description,
                description_source_type="position",
                raw_multiplier=raw_pos.multiplier,
                raw_underlying_conid=raw_pos.underlying_conid,
                raw_underlying_symbol=raw_pos.underlying_symbol
            )
            self._record_snapshot_row(self.soy_positions, raw_pos, asset,
                                      "The opening snapshot")

        logger.info("Processing end-of-year positions...")
        for raw_pos in self.raw_positions_end:
            asset = self.asset_resolver.get_or_create_asset(
                raw_isin=raw_pos.isin, raw_conid=raw_pos.conid, raw_symbol=raw_pos.symbol,
                raw_currency=raw_pos.currency_primary, raw_ibkr_asset_class=raw_pos.asset_class,
                raw_description=raw_pos.description,
                description_source_type="position",
                raw_multiplier=raw_pos.multiplier,
                raw_underlying_conid=raw_pos.underlying_conid,
                raw_underlying_symbol=raw_pos.underlying_symbol
            )
            self._record_snapshot_row(self.eoy_positions, raw_pos, asset,
                                      "The closing snapshot")

        self._refuse_mixed_snapshot_currencies(
            self.soy_positions, self.asset_resolver, "The opening snapshot")
        self._refuse_mixed_snapshot_currencies(
            self.eoy_positions, self.asset_resolver, "The closing snapshot")

        # Preceding calendar year's snapshots. Used ONLY by the Vorabpauschale, which for a VZ Y
        # declaration is the one computed for calendar Y-1 (18 Abs. 3 InvStG). These must not
        # feed cost basis, reconciliation or any other consumer.
        logger.info("Processing prior-year positions (Vorabpauschale reference prices)...")
        # The day each snapshot describes. The files carry no date column, so it is the
        # naming convention they were selected by -- Positions-{X}-SoY.csv is X's first
        # trading day, Positions-{X}-EoY.csv the close of X (src/data_preparation.py).
        # Recorded here, next to the price, because Rz. 18.6 converts each price at the
        # ECB rate of the day it was set (GT-INVSTG-018) and by the time the engine sees
        # a price it can no longer tell which file it came from. Issue #59 replaces the
        # convention with a report date the export itself carries.
        # Left unset when no tax year is given: the engine then derives the day from
        # the Vorabpauschale year, which is the same rule. What it cannot derive is
        # the substituted price's day, and that is set explicitly below.
        vorabpauschale_year = tax_year - 1 if tax_year is not None else None
        soy_snapshot_date = (first_business_day_of_year(vorabpauschale_year)
                             if vorabpauschale_year is not None else None)
        eoy_snapshot_date = (last_business_day_of_year(vorabpauschale_year)
                             if vorabpauschale_year is not None else None)

        # Recorded per (account, asset) like every other snapshot. The person's unit
        # count and value are `person_snapshot` over the rows ([GT-ESTG20-061]); each
        # price is per unit and common to every account.
        for raw_pos in self.raw_positions_prior_start:
            asset = self._resolve_asset_from_position(raw_pos)
            self._record_snapshot_row(self.prior_soy_positions, raw_pos, asset,
                                      "The preceding year's opening snapshot",
                                      mark_price_date=soy_snapshot_date)
            self._record_prior_year_snapshot_asset(asset)

        for raw_pos in self.raw_positions_prior_end:
            asset = self._resolve_asset_from_position(raw_pos)
            self._record_snapshot_row(self.prior_eoy_positions, raw_pos, asset,
                                      "The preceding year's closing snapshot",
                                      mark_price_date=eoy_snapshot_date)
            self._record_prior_year_snapshot_asset(asset)

        # Checkpoint marks. Kept in their own registry rather than in `soy_positions`:
        # there is one of these per year in the window, and `soy_positions` is a single
        # opening snapshot for the tax year. Keeping them apart is deliberate --
        # conflating a mark with the opening snapshot is how a mid-window snapshot would
        # end up feeding the tax year's cost basis.
        for mark_year, raw_rows in sorted(self.raw_positions_marks.items()):
            marks: MarksByAccount = {}
            mark_label = f"The {mark_year}-12-31 checkpoint mark"
            for raw_pos in raw_rows:
                asset = self._resolve_asset_from_position(raw_pos)
                self._record_mark_row(marks, raw_pos, asset, mark_label)
            self._refuse_mixed_snapshot_currencies(
                marks, self.asset_resolver, mark_label)
            self.mark_positions[mark_year] = marks
            logger.info("Checkpoint mark %d-12-31: %d (account, instrument) row(s) reported.",
                        mark_year, len(marks))

        for raw_pos in self.raw_positions_prior_opening:
            asset = self._resolve_asset_from_position(raw_pos)
            self._record_snapshot_row(self.prior_opening_positions, raw_pos, asset,
                                      "The snapshot before the Vorabpauschale year")
            self._record_prior_year_snapshot_asset(asset)

        for registry, label in ((self.prior_soy_positions,
                                 "The preceding year's opening snapshot"),
                                (self.prior_eoy_positions,
                                 "The preceding year's closing snapshot"),
                                (self.prior_opening_positions,
                                 "The snapshot before the Vorabpauschale year")):
            self._refuse_mixed_snapshot_currencies(registry, self.asset_resolver, label)

        self._resolve_vorabpauschale_start_price(vorabpauschale_year)

    def _resolve_vorabpauschale_start_price(
            self, vorabpauschale_year: Optional[int] = None) -> None:
        """
        Settle the per-unit price the Vorabpauschale year opens at.

        For calendar X the Ruecknahmepreis is the first one set in X, which is
        what X's own start-of-year report carries (18 Abs. 1 Satz 2 InvStG).
        Where a fund has no price in that report -- it was sold on X's first
        trading day, so the snapshot taken at that day's close does not list it
        -- the last price set before the year began stands in: one trading day
        early rather than a year late. Every substitution is recorded so the
        report can say it happened.

        Only the price is settled here. The unit count is not this layer's
        business: it comes from the lots held at the close of 31 December
        (Rz. 18.4), which only the ledger knows.

        The substituted price carries the day it was set with it, which is in
        the year BEFORE the Vorabpauschale year. Rz. 18.6 converts at the ECB
        rate of that day (GT-INVSTG-018); converting at a day inside the
        Vorabpauschale year would take the price from one year and the rate
        from another.
        """
        opening_price_date = (last_business_day_of_year(vorabpauschale_year - 1)
                              if vorabpauschale_year is not None else None)

        # Whether a price is missing is asked of the person's holding, not of one
        # account's row: the Ruecknahmepreis is a property of the fund, so one account
        # reporting it settles it for all of them. Which accounts the substituted price
        # is then written under is a storage question, answered below.
        # Walked in asset order rather than in registry order so the substitutions are
        # reported in the order the instruments were first seen, which is an order the
        # input fixes; a set of registry keys is not.
        reported_at_open = {asset_id for _account, asset_id in self.prior_opening_positions}
        for asset_id in self.asset_resolver.assets_by_internal_id:
            if asset_id not in reported_at_open:
                continue
            reported = person_snapshot(self.prior_soy_positions, asset_id)
            if reported is not None and reported.mark_price is not None:
                continue

            opening = person_snapshot(self.prior_opening_positions, asset_id)
            if opening is None or opening.mark_price is None:
                continue

            # Only funds held when the year opened can have lost their price
            # this way; anything else never had one to begin with, and
            # inventing one would be a plausible wrong number.
            if opening.quantity is None or opening.quantity <= Decimal(0):
                continue

            # Written under every account that reported the fund at the year's start,
            # or -- where the start-of-year report omits it entirely -- under the
            # accounts that held it when the year opened. Both are accounts the export
            # names; no account is invented to hold the record.
            accounts = [account for account, _snap
                        in snapshots_for_asset(self.prior_soy_positions, asset_id)]
            if not accounts:
                accounts = [account for account, _snap
                            in snapshots_for_asset(self.prior_opening_positions, asset_id)]
            for account in accounts:
                key = (account, asset_id)
                base = self.prior_soy_positions.get(key) or PositionSnapshot(quantity=None)
                self.prior_soy_positions[key] = dataclasses_replace(
                    base,
                    mark_price=opening.mark_price,
                    mark_price_currency=opening.mark_price_currency,
                    mark_price_date=opening_price_date,
                )

            asset = self.asset_resolver.get_asset_by_id(asset_id)
            if asset is None:
                continue
            self.vorabpauschale_price_substitutions.append(
                (asset.get_classification_key(), asset.description or ""))
            logger.warning(
                "Vorabpauschale for %s: no price on the first trading day of the year "
                "though the fund was held when it opened; using the last price set "
                "before the year began.",
                asset.get_classification_key(),
            )

    def _record_prior_year_snapshot_asset(self, asset: Asset) -> None:
        """Note that a prior-year snapshot record was written for this asset.

        An alias is kept alongside the id because the asset object recorded here need not
        be the one the engine sees. Two later rows whose identifiers overlap are merged,
        and the merge deletes the losing asset and repoints its aliases at the winner --
        while the record stays filed under the losing id, where nothing will look for it.
        Looking the alias up again resolves to whichever asset ends up owning the
        instrument, so the loss can be named.
        """
        if asset.internal_asset_id in self._prior_year_snapshot_assets:
            return
        self._prior_year_snapshot_assets[asset.internal_asset_id] = (
            next(iter(asset.aliases)) if asset.aliases else None)

    def _verify_prior_year_snapshot_survived_classification(self) -> None:
        """Every prior-year snapshot read above must still reach the asset that owns it.

        The registries are keyed by `internal_asset_id`, which a reclassification
        preserves, so rebuilding a Stock as an InvestmentFund cannot lose a record --
        that is what moving the snapshot off the Asset bought. A MERGE still can: two
        rows whose identifiers overlap resolve to one asset, the loser is deleted from
        `assets_by_internal_id`, and any record filed under its id becomes unreachable.
        The drop is invisible -- the Vorabpauschale then finds no year-start
        Ruecknahmepreis and skips the fund, so its deemed income leaves the declaration
        with nothing recorded anywhere. This checks every asset a record was written for
        and reports all of them at once.

        Two conditions bound what it reports, and both are deliberate:

        - **Only investment funds.** 18 InvStG reaches nothing else, so nothing else can lose a
          declared figure this way. The prior-year snapshot is read for every instrument in the
          file, and aborting a run because a share or a bond lost a value it has no use for
          would stop a declaration that is not at risk.
        - **Only where a record was actually written.** A fund bought during the Vorabpauschale
          year has no prior-year snapshot row and is never registered, so a legitimate absence
          cannot trip this.

        The owner is looked up by id, falling back to the alias for an id that no longer
        resolves -- which is what a merge leaves behind, the losing asset having been
        deleted. Resolving through the alias first would be equivalent: probed on
        2026-08-31, the two orders agree on every reachable path, because
        `replace_asset_type` re-uses the id and a merge deletes the loser rather than
        leaving a stale entry beside it.
        """
        registries = (self.prior_soy_positions, self.prior_eoy_positions,
                      self.prior_opening_positions)
        losses: List[str] = []
        checked = 0
        for asset_id, alias in self._prior_year_snapshot_assets.items():
            owner = self.asset_resolver.assets_by_internal_id.get(asset_id)
            if owner is None and alias is not None:
                owner = self.asset_resolver.alias_map.get(alias)
            if not isinstance(owner, InvestmentFund):
                continue
            checked += 1
            if owner.internal_asset_id == asset_id:
                continue
            # The instrument changed hands between assets, and the rows are still filed
            # under the id nothing will look up again.
            if any(snapshots_for_asset(reg, asset_id) for reg in registries):
                losses.append(f"{owner.get_classification_key()} ({owner.description})")

        if losses:
            raise DataIntegrityError(
                "The preceding year's position snapshot was read for "
                f"{checked} investment fund(s) but no longer reaches the calculation for "
                f"{len(losses)} of them. The Vorabpauschale for that year (18 Abs. 1 InvStG) is "
                "computed from these snapshots, so the affected funds would drop out of Anlage "
                "KAP-INV Zeilen 9-13 without a figure and without a warning. This is an engine "
                "defect, not an input problem: the snapshot was read and filed under an "
                "internal asset id that no longer owns the instrument -- by a merge of two "
                "identifiers that carried the aliases across but not the records, or by a "
                "reclassification that failed to re-use the id. Affected: " + "; ".join(losses)
            )


    def _resolve_asset_from_position(self, raw_pos):
        """Resolve (or create) the Asset a raw position record refers to.

        Extracted verbatim from the SoY/EoY loops so the prior-year loops resolve identically --
        a fund that resolved to one Asset from the tax year's snapshot must resolve to the same
        Asset from the prior year's, or its Vorabpauschale would attach to a second instrument.
        """
        return self.asset_resolver.get_or_create_asset(
            raw_isin=raw_pos.isin, raw_conid=raw_pos.conid, raw_symbol=raw_pos.symbol,
            raw_currency=raw_pos.currency_primary, raw_ibkr_asset_class=raw_pos.asset_class,
            raw_description=raw_pos.description,
            description_source_type="position",
            raw_multiplier=raw_pos.multiplier,
            raw_underlying_conid=raw_pos.underlying_conid,
            raw_underlying_symbol=raw_pos.underlying_symbol
        )

    def discover_assets_from_transactions(self):
        # ... (implementation is the same)
        logger.info("Discovering assets from trades, cash transactions, and corporate actions...")
        for rt in self.raw_trades:
            self.asset_resolver.get_or_create_asset(
                raw_isin=rt.isin,
                raw_conid=rt.conid, raw_symbol=rt.symbol, raw_currency=rt.currency_primary,
                raw_ibkr_asset_class=rt.asset_class, raw_description=rt.description,
                description_source_type="trade",
                raw_ibkr_sub_category=rt.sub_category, raw_multiplier=rt.multiplier,
                raw_strike=rt.strike, raw_expiry=rt.expiry, raw_put_call=rt.put_call,
                raw_underlying_conid=rt.underlying_conid, raw_underlying_symbol=rt.underlying_symbol
            )

        for rct in self.raw_cash_transactions:
            is_instrument_specific = bool(
                rct.isin or \
                rct.conid or \
                (rct.symbol and rct.symbol.strip().upper() != (rct.currency_primary or "").strip().upper())
            )

            if is_instrument_specific:
                self.asset_resolver.get_or_create_asset(
                    raw_isin=rct.isin,
                    raw_conid=rct.conid, raw_symbol=rct.symbol, raw_currency=rct.currency_primary,
                    raw_ibkr_asset_class=rct.asset_class, raw_description=rct.description,
                    description_source_type="cash_tx",
                    raw_ibkr_sub_category=rct.sub_category
                )
            else:
                self.asset_resolver.get_or_create_asset(
                    raw_isin=None, raw_conid=None, raw_symbol=rct.currency_primary,
                    raw_currency=rct.currency_primary, raw_ibkr_asset_class="CASH",
                    raw_description=f"Cash Balance {rct.currency_primary}",
                    description_source_type="cash_balance_generated",
                    raw_ibkr_sub_category=rct.sub_category
                )

        for rca in self.raw_corporate_actions:
            self.asset_resolver.get_or_create_asset(
                raw_isin=rca.isin,
                raw_conid=rca.conid, raw_symbol=rca.symbol, raw_currency=rca.currency_primary,
                raw_ibkr_asset_class=None,  # AssetClass is not exported for CAs
                raw_description=rca.description,
                description_source_type="corp_act_asset"
            )
        logger.info(f"Asset discovery complete. Total unique assets identified: {len(self.asset_resolver.assets_by_internal_id)}")

    def finalize_asset_classifications(self):
        # ... (implementation is the same)
        logger.info("Finalizing asset classifications...")
        current_assets_to_process = list(self.asset_resolver.assets_by_internal_id.values())

        for asset_obj_snapshot in current_assets_to_process:
            current_asset_in_resolver = self.asset_resolver.assets_by_internal_id.get(asset_obj_snapshot.internal_asset_id)
            if not current_asset_in_resolver:
                logger.warning(f"Asset with ID {asset_obj_snapshot.internal_asset_id} was removed during processing, skipping final classification for it.")
                continue

            asset_to_classify = current_asset_in_resolver

            final_cat, final_fund_type, final_notes, needs_replacement = \
                self.asset_classifier.ensure_final_classification(
                    asset_to_classify,
                    interactive_mode=self.interactive_classification
                )

            asset_after_action: Asset
            if needs_replacement:
                logger.debug(f"Replacing type for asset {asset_to_classify.get_classification_key()} (ID: {asset_to_classify.internal_asset_id}) to {final_cat.name}")
                asset_after_action = self.asset_resolver.replace_asset_type(
                    internal_asset_id=asset_to_classify.internal_asset_id,
                    new_category=final_cat,
                    new_fund_type=final_fund_type,
                    new_user_notes=final_notes
                )
            else:
                asset_to_classify.asset_category = final_cat
                if isinstance(asset_to_classify, InvestmentFund) and final_cat == AssetCategory.INVESTMENT_FUND:
                    asset_to_classify.fund_type = final_fund_type or InvestmentFundType.NONE
                elif not isinstance(asset_to_classify, InvestmentFund) and final_cat == AssetCategory.INVESTMENT_FUND:
                    logger.error(f"CRITICAL ERROR: Mismatch - Asset {asset_to_classify.get_classification_key()} is {type(asset_to_classify)} but classified as InvestmentFund without replacement flag being True.")
                asset_to_classify.user_notes = final_notes
                asset_after_action = asset_to_classify

            asset_key_for_cache = asset_after_action.get_classification_key()
            current_cache_entry = self.asset_classifier.classifications_cache.get(asset_key_for_cache)
            new_fund_type_name_for_cache = InvestmentFundType.NONE.name 
            if isinstance(asset_after_action, InvestmentFund) and asset_after_action.fund_type:
                new_fund_type_name_for_cache = asset_after_action.fund_type.name

            new_cache_tuple = (
                asset_after_action.asset_category.name,
                new_fund_type_name_for_cache,
                asset_after_action.user_notes or ""
            )
            if asset_key_for_cache not in self.asset_classifier.classifications_cache or current_cache_entry != new_cache_tuple:
                logger.debug(f"Updating classification cache for key '{asset_key_for_cache}' to: {new_cache_tuple}")
                self.asset_classifier.classifications_cache[asset_key_for_cache] = new_cache_tuple
                self.asset_classifier.save_classifications()

        self.asset_classifier.save_classifications()
        logger.info("Asset classifications finalized and cache saved.")

    def _process_dividend_rights_matching(self):
        """Post-processing step to handle DI/ED dividend rights matching.
        
        For each ED (Expire Dividend Rights) event:
        1. Find matching DI (Dividend Issue) event and set its shares to 0
        2. Find matching cash dividend event and update its asset ISIN to underlying asset
        """
        from src.domain.events import CorpActionExpireDividendRights, CorpActionStockDividend, CashFlowEvent, CorporateActionEvent
        from src.domain.enums import FinancialEventType
        import re
        
        logger.info("Processing dividend rights matching (DI/ED events)...")
        
        # Debug: Log all corporate action events
        ca_events = [event for event in self.domain_financial_events if isinstance(event, CorporateActionEvent)]
        logger.debug(f"Found {len(ca_events)} corporate action events total:")
        for ca_event in ca_events:
            logger.debug(f"  CA Event: {type(ca_event).__name__}, Type: {ca_event.event_type.name}, Desc: {ca_event.ibkr_activity_description}")
        
        # Debug: Log all cash flow events
        cash_events = [event for event in self.domain_financial_events if isinstance(event, CashFlowEvent)]
        logger.debug(f"Found {len(cash_events)} cash flow events total:")
        for cash_event in cash_events:
            logger.debug(f"  Cash Event: Type: {cash_event.event_type.name}, Desc: {cash_event.ibkr_activity_description}")
        
        # Find all ED events for processing
        ed_events = [
            event for event in self.domain_financial_events 
            if isinstance(event, CorpActionExpireDividendRights)
        ]
        
        if not ed_events:
            logger.info("No ED (Expire Dividend Rights) events found. Skipping dividend rights processing.")
            return
        
        logger.info(f"Found {len(ed_events)} ED events to process.")
        
        for ed_event in ed_events:
            ed_asset = self.asset_resolver.get_asset_by_id(ed_event.asset_internal_id)
            if not ed_asset:
                logger.warning(f"ED Event {ed_event.event_id}: Could not find asset for ED event. Skipping.")
                continue
                
            logger.debug(f"Processing ED event for asset {ed_asset.get_classification_key()} (CONID: {ed_asset.ibkr_conid}, ISIN: {ed_asset.ibkr_isin})")
            
            # 1. Find matching DI event
            matching_di_event = None
            for event in self.domain_financial_events:
                if (isinstance(event, CorpActionStockDividend) and 
                    event.ibkr_activity_description and
                    "DIVIDEND RIGHTS ISSUE" in event.ibkr_activity_description.upper()):
                    
                    di_asset = self.asset_resolver.get_asset_by_id(event.asset_internal_id)
                    if (di_asset and 
                        di_asset.ibkr_conid == ed_asset.ibkr_conid and 
                        di_asset.ibkr_isin == ed_asset.ibkr_isin and
                        di_asset.ibkr_symbol == ed_asset.ibkr_symbol):
                        matching_di_event = event
                        logger.debug(f"Found matching DI event {event.event_id} for ED event {ed_event.event_id}")
                        break
            
            if matching_di_event:
                # Set DI event shares to 0 (rights expired without receiving shares)
                logger.info(f"ED Event {ed_event.event_id}: Setting matching DI event {matching_di_event.event_id} shares from {matching_di_event.quantity_new_shares_received} to 0")
                matching_di_event.quantity_new_shares_received = Decimal('0')
            else:
                logger.warning(f"ED Event {ed_event.event_id}: Could not find matching DI event for asset {ed_asset.get_classification_key()}")
            
            # 2. Find matching cash dividend event and update its asset ISIN
            # Extract underlying ISIN from the matching DI event description (not ED event)
            underlying_isin = None
            if matching_di_event:
                underlying_isin = self._extract_underlying_isin_from_description(matching_di_event.ibkr_activity_description)
            
            if not underlying_isin:
                logger.warning(f"ED Event {ed_event.event_id}: Could not extract underlying ISIN from matching DI event description: {matching_di_event.ibkr_activity_description if matching_di_event else 'No DI event found'}")
                continue
                
            logger.debug(f"ED Event {ed_event.event_id}: Extracted underlying ISIN from DI event: {underlying_isin}")
            
            # Debug: Log what we're looking for in cash events
            logger.debug(f"ED Event {ed_event.event_id}: Looking for cash event with CONID={ed_asset.ibkr_conid}, ISIN={ed_asset.ibkr_isin}")
            
            matching_cash_event = None
            cash_events_checked = 0
            for event in self.domain_financial_events:
                if isinstance(event, CashFlowEvent):
                    cash_events_checked += 1
                    cash_asset = self.asset_resolver.get_asset_by_id(event.asset_internal_id)
                    logger.debug(f"  Checking cash event {event.event_id}: Type={event.event_type.name}, Desc='{event.ibkr_activity_description}', Asset CONID={cash_asset.ibkr_conid if cash_asset else 'None'}, ISIN={cash_asset.ibkr_isin if cash_asset else 'None'}")
                    
                    if ((event.event_type == FinancialEventType.DIVIDEND_CASH or event.event_type == FinancialEventType.CAPITAL_REPAYMENT) and
                        event.ibkr_activity_description and
                        "EXEMPT FROM WITHHOLDING" in event.ibkr_activity_description.upper()):
                        
                        logger.debug(f"    Cash event matches description pattern")
                        if (cash_asset and 
                            cash_asset.ibkr_conid == ed_asset.ibkr_conid and 
                            cash_asset.ibkr_isin == ed_asset.ibkr_isin):
                            matching_cash_event = event
                            logger.debug(f"Found matching cash dividend event {event.event_id} for ED event {ed_event.event_id}")
                            break
                        else:
                            logger.debug(f"    Asset identifiers don't match: Expected CONID={ed_asset.ibkr_conid}/ISIN={ed_asset.ibkr_isin}, Got CONID={cash_asset.ibkr_conid if cash_asset else 'None'}/ISIN={cash_asset.ibkr_isin if cash_asset else 'None'}")
            
            logger.debug(f"ED Event {ed_event.event_id}: Checked {cash_events_checked} cash events, found match: {matching_cash_event is not None}")
            
            if matching_cash_event:
                # Find the LEG stock asset to link the cash event to
                leg_stock_asset = None
                for asset_id, asset in self.asset_resolver.assets_by_internal_id.items():
                    if asset.ibkr_isin == underlying_isin:
                        leg_stock_asset = asset
                        break
                
                if leg_stock_asset:
                    logger.info(f"ED Event {ed_event.event_id}: Updating cash dividend event to point to LEG stock asset {leg_stock_asset.get_classification_key()}")
                    # Update the cash event to point to the LEG stock asset instead of dividend rights asset
                    matching_cash_event.asset_internal_id = leg_stock_asset.internal_asset_id
                else:
                    logger.warning(f"ED Event {ed_event.event_id}: Could not find LEG stock asset with ISIN {underlying_isin}")
            else:
                logger.warning(f"ED Event {ed_event.event_id}: Could not find matching cash dividend event for asset {ed_asset.get_classification_key()}")
        
        logger.info("Dividend rights matching processing completed.")

    def _extract_underlying_isin_from_description(self, description: str) -> Optional[str]:
        """Extract the underlying asset ISIN from corporate action description.
        
        Example: 'ABC(DE0001234567) DIVIDEND RIGHTS ISSUE...' -> 'DE0001234567'
        """
        if not description:
            return None
        
        # Look for ISIN pattern in parentheses: (DE0001234567)
        import re
        isin_match = re.search(r'\(([A-Z]{2}[A-Z0-9]{10})\)', description)
        return isin_match.group(1) if isin_match else None

    def _process_cash_balance_positions(self, tax_year: Optional[int] = None):
        """
        Process cash balance records to set SOY/EOY quantities on CashBalance assets.
        Filters out tiny balances and EUR (base currency).
        Validates that cash balance dates match the configured tax year.

        Supports both positive (long) and negative (short) currency positions.
        Negative positions occur with margin trading.
        """
        MIN_BALANCE_THRESHOLD = Decimal("0.01")  # Filter tiny balances

        logger.info("Processing cash balance positions for SOY/EOY quantities...")
        balances_processed = 0
        balances_skipped = 0

        # Validate cash balance dates against tax year (check first record)
        if tax_year and self.raw_cash_balances:
            first = self.raw_cash_balances[0]
            try:
                from_year = int(first.from_date[:4]) if first.from_date else None
                to_year = int(first.to_date[:4]) if first.to_date else None
                if from_year and to_year:
                    if from_year != tax_year and to_year != tax_year:
                        logger.error(
                            f"CASH BALANCE DATE MISMATCH: Cash balance CSV covers "
                            f"{first.from_date}–{first.to_date} but tax year is {tax_year}. "
                            f"SOY/EOY currency balances will be WRONG. "
                            f"Please provide a cash balance report for tax year {tax_year}."
                        )
                    elif from_year != tax_year:
                        logger.warning(
                            f"Cash balance CSV starts in {from_year} (FromDate={first.from_date}) "
                            f"but tax year is {tax_year}. Verify that StartingCash represents "
                            f"the SOY balance for {tax_year}."
                        )
            except (ValueError, TypeError):
                pass  # malformed date, skip validation

        for raw_balance in self.raw_cash_balances:
            # Skip EUR (base currency) and BASE_SUMMARY (IBKR aggregate row)
            if raw_balance.currency_primary and raw_balance.currency_primary.upper() in ("EUR", "BASE_SUMMARY"):
                logger.debug(f"Skipping cash balance row: {raw_balance.currency_primary}")
                balances_skipped += 1
                continue

            # Skip tiny balances (below threshold)
            if (abs(raw_balance.starting_cash) < MIN_BALANCE_THRESHOLD and
                abs(raw_balance.ending_cash) < MIN_BALANCE_THRESHOLD):
                logger.debug(f"Skipping tiny cash balance {raw_balance.currency_primary}: "
                           f"SOY={raw_balance.starting_cash}, EOY={raw_balance.ending_cash}")
                balances_skipped += 1
                continue

            # Get or create CashBalance asset
            cash_asset = self.asset_resolver.get_or_create_asset(
                raw_isin=None,
                raw_conid=None,
                raw_symbol=raw_balance.currency_primary,
                raw_currency=raw_balance.currency_primary,
                raw_ibkr_asset_class="CASH",
                raw_description=f"Cash Balance {raw_balance.currency_primary}",
                description_source_type="cash_balance_csv"
            )

            # Record the opening and closing balance (can be negative for short positions)
            # under the account that reported it. One currency held in two accounts is
            # reported on two rows and the person's balance is both of them
            # ([GT-ESTG20-061]); `person_snapshot` adds them. The threshold above still
            # applies per row, which is what it was written for: it drops rounding dust,
            # and dust is dust in each account separately.
            #
            # These REPLACE whatever a Positions row said about this currency, which is
            # what they have always done by running second -- a currency reported in both
            # reports is one balance, and the cash-balance report is the one written for
            # it. Keyed by account, so a Positions row for a currency in a DIFFERENT
            # account survives; there is no such row in any export this engine has seen.
            key = (account_key(raw_balance.client_account_id), cash_asset.internal_asset_id)
            self.soy_positions[key] = _replace_snapshot_quantity(
                self.soy_positions.get(key), raw_balance.starting_cash)
            self.eoy_positions[key] = _replace_snapshot_quantity(
                self.eoy_positions.get(key), raw_balance.ending_cash)

            position_type = "LONG" if raw_balance.starting_cash >= Decimal("0") else "SHORT"
            eoy_position_type = "LONG" if raw_balance.ending_cash >= Decimal("0") else "SHORT"

            logger.debug(f"Cash {raw_balance.currency_primary}: "
                        f"SOY={raw_balance.starting_cash} ({position_type}), "
                        f"EOY={raw_balance.ending_cash} ({eoy_position_type})")
            balances_processed += 1

        logger.info(f"Processed {balances_processed} cash balance positions, skipped {balances_skipped}")

    def _ensure_soy_quantities_are_set(self):
        # ... (implementation is the same)
        logger.info("Ensuring all non-cash assets have Start-of-Year (SOY) quantities initialized...")
        assets_updated_count = 0
        for asset_id, asset_obj in self.asset_resolver.assets_by_internal_id.items():
            if asset_obj.asset_category != AssetCategory.CASH_BALANCE:
                opening = person_snapshot(self.soy_positions, asset_id)
                if opening is None or opening.quantity is None:
                    # Absent from the opening report, so the year opened holding none of
                    # it. Recorded under DEFAULT_ACCOUNT because it belongs to no account:
                    # no account reported it, and a zero holding is the same zero in every
                    # one of them.
                    #
                    # Removing this moves no figure -- `reconcile_with_mark` coerces a
                    # `None` reported quantity to zero itself, and every declared figure
                    # is identical either way. What it buys is that the zero is *stated*
                    # rather than inferred two layers down, and that the warning that
                    # coercion emits stays for the cases it was written for. Do not delete
                    # it on the strength of a green suite: the suite is green without it.
                    self.soy_positions[(DEFAULT_ACCOUNT, asset_id)] = PositionSnapshot(
                        quantity=Decimal(0), cost_basis_amount=Decimal(0))
                    logger.debug(
                        f"Asset {asset_obj.get_classification_key()} (ID: {asset_id}) was not in SOY report. "
                        f"Recorded an opening holding of 0 at zero cost."
                    )
                    assets_updated_count +=1
                elif opening.quantity != Decimal(0) and opening.cost_basis_amount is None:
                    # Held at the start of the year with no reported cost basis. This used to
                    # set the basis to zero, which makes the whole of a later disposal a gain.
                    # `CostBasisMoney` is blank in 0 of 87 position rows across 2021-2025, so
                    # nothing was ever floored -- but a zero here is an invented figure, not a
                    # missing one, and the run must not carry it.
                    raise ProcessingError(
                        f"Asset {asset_obj.get_classification_key()}: the start-of-year "
                        f"snapshot reports {opening.quantity} units with no cost basis. "
                        f"Their gain on disposal cannot be computed, and a zero basis would "
                        f"declare the whole proceeds as gain.")

        if assets_updated_count > 0:
            logger.info(f"Initialized SOY quantity to 0 for {assets_updated_count} assets not found in the SOY position report.")
        else:
            logger.info("All non-cash assets already had SOY quantities (or were not applicable).")


    def create_domain_events_and_prepare_for_linking(self, event_factory: DomainEventFactory): # MODIFIED
        """
        Uses the DomainEventFactory to create all financial events from raw data
        and populates collections for later linking.
        """
        logger.info("Creating domain events using DomainEventFactory and preparing for linking...")
        
        # DomainEventFactory.create_events_from_trades now returns a tuple
        trade_events_tuple = event_factory.create_events_from_trades(self.raw_trades)
        all_trade_events: List[FinancialEvent] = trade_events_tuple[0]
        # Store these on self for the linking step
        self.candidate_option_lifecycle_events = trade_events_tuple[1]
        self.candidate_stock_trades_for_linking = trade_events_tuple[2]

        cash_events = event_factory.create_events_from_cash_transactions(self.raw_cash_transactions)
        ca_events = event_factory.create_events_from_corporate_actions(self.raw_corporate_actions)
        options_eae_events = event_factory.create_events_from_options_eae(self.raw_options_eae) if self.raw_options_eae else []

        # Populate the main list of events
        self.domain_financial_events.clear() # Clear if run multiple times (though not typical)
        self.domain_financial_events.extend(all_trade_events)
        self.domain_financial_events.extend(cash_events)
        self.domain_financial_events.extend(ca_events)
        self.domain_financial_events.extend(options_eae_events)

        self._require_option_cash_settlements(all_trade_events, options_eae_events)

        logger.info(f"DomainEventFactory created {len(self.domain_financial_events)} total financial events initially.")
        logger.info(f"Collected {len(self.candidate_option_lifecycle_events)} candidate option lifecycle events for linking.")
        logger.info(f"Collected {len(self.candidate_stock_trades_for_linking)} candidate stock trades for linking.")

    def _require_option_cash_settlements(self,
                                         trade_derived_events: List[FinancialEvent],
                                         options_eae_events: List[FinancialEvent]) -> None:
        """A cash-settled option's assignment/exercise must have its OptionEAE row.

        The OptionEAE export is optional *as a file* -- an account that never traded
        options needs none, and one that only ever took physical delivery needs none
        either, because those rows duplicate the Trades export. What is not optional is
        the `Cash Settlement` row behind a settlement that actually happened: it is the
        sole carrier of the settlement proceeds, and without it the realised gain of an
        index-option position is the premium alone.

        **The requirement is derivable from the Trades export by itself**, which is what
        makes checking it possible at all. `OptionExerciseProcessor` and
        `OptionAssignmentProcessor` both step aside for an option with no underlying
        link -- an index option, whose underlying is not an instrument the account can
        hold -- on the stated ground that `OptionCashSettlementProcessor` handles it.
        That was an assumption with nothing behind it. Here it becomes a contract:
        every A/EX event those two hand on must have a settlement event to be handed to.

        Unmatched cases are collected and reported together, so one run names every
        contract rather than the first.

        Without this the failure is real but reads as something else. The option lot is
        never consumed, so the calculated end-of-year quantity stands against a contract
        the broker no longer reports and EOY validation aborts on a position mismatch --
        whose own message lists missing trades, corporate actions, option exercises and
        double-identified instruments as the causes to go looking for, and not the file.
        Measured 2026-08-08: a VZ 2025 run against the real import with
        `Options_EAE-2025.csv` withheld produced `EOY_RECONCILIATION_FAILED` naming 14
        index-option positions; with this check it stops at parse time naming the same
        14 and the file to export.

        For a settlement in a *prior* year there is no signal at all:
        `reconcile_with_mark` discards a reconstruction that disagrees with the snapshot
        and takes the snapshot, so the phantom lot is absorbed in silence. Hence the
        whole replay window is checked, not only the assessment year.
        """
        settled_keys = {
            (ev.asset_internal_id, ev.event_date)
            for ev in options_eae_events
            if isinstance(ev, OptionCashSettlementEvent)
        }

        unpaired: List[str] = []
        for event in trade_derived_events:
            if not isinstance(event, (OptionAssignmentEvent, OptionExerciseEvent)):
                continue
            option_asset = self.asset_resolver.get_asset_by_id(event.asset_internal_id)
            if not isinstance(option_asset, Option):
                continue
            if option_asset.underlying_asset_internal_id is not None:
                continue  # Physically settled: the delivery leg is in the Trades export.
            if (event.asset_internal_id, event.event_date) in settled_keys:
                continue
            unpaired.append(
                f"{option_asset.description or option_asset.get_classification_key()} "
                f"(Conid: {option_asset.ibkr_conid}) {event.event_type.name} on "
                f"{event.event_date}, {event.quantity_contracts} contract(s)"
            )

        if not unpaired:
            return

        if self.options_eae_file_supplied:
            cause = (
                "An OptionEAE file was read, but it carries no 'Cash Settlement' row for "
                "these contracts on these dates. A row whose Proceeds are exactly zero is "
                "skipped at parse time and counts as absent here."
            )
        else:
            cause = (
                "No OptionEAE file was supplied. Export it as Options_EAE-YYYY.csv into "
                "data_import/ for every year listed below (see input_data_spec.md)."
            )

        raise DataIntegrityError(
            f"{len(unpaired)} cash-settled option assignment(s)/exercise(s) have no "
            f"matching OptionEAE Cash Settlement. The settlement proceeds are the whole "
            f"gain on these positions, so the run cannot produce a figure for them.\n"
            f"  {cause}\n  " + "\n  ".join(unpaired)
        )


    def get_all_financial_events(self) -> List[FinancialEvent]:
        # ... (sorting logic is the same, uses self.domain_financial_events)
        logger.info("Sorting financial events deterministically...")
        sort_key_func = lambda ev: get_event_sort_key(ev, self.asset_resolver)
        try:
            self.domain_financial_events.sort(key=sort_key_func)
        except ValueError as e:
            logger.critical(f"Fatal error during event sorting: {e}. Cannot guarantee deterministic order. Aborting.")
            raise e 

        logger.info("Validating sort key uniqueness and completeness post-sort...")
        errors_found = 0
        
        all_generated_keys: List[Tuple[date, Tuple[Any, ...]]] = []
        for event in self.domain_financial_events:
            try:
                key = get_event_sort_key(event, self.asset_resolver)
                all_generated_keys.append(key)
                if key[0] == date.min and not parse_ibkr_date(event.event_date):
                    logger.error(f"Sort Validation Error: Event {event.event_id} ({type(event).__name__}, Date: '{event.event_date}') resulted in a minimal date sort key component, indicating a potential parsing issue not caught earlier.")
                    errors_found += 1
            except ValueError as e: 
                logger.error(f"Sort Key Generation Error: Event {event.event_id} ({type(event).__name__}) - {e}")
                errors_found += 1
        
        seen_keys = set()
        for i, key_to_check in enumerate(all_generated_keys):
            if key_to_check in seen_keys:
                duplicate_event_details = []
                for j, ev_event in enumerate(self.domain_financial_events):
                    try:
                        current_ev_key = get_event_sort_key(ev_event, self.asset_resolver)
                        if current_ev_key == key_to_check:
                            duplicate_event_details.append(
                                f"(Index {j}, ID: {ev_event.event_id}, Type: {type(ev_event).__name__}, "
                                f"Desc: '{ev_event.ibkr_activity_description}', Amt: {ev_event.gross_amount_foreign_currency} {ev_event.local_currency}, "
                                f"TxID: {ev_event.ibkr_transaction_id})"
                            )
                    except ValueError: 
                        pass

                logger.error(
                    f"Sort Validation Error: Duplicate sort key detected! \n"
                    f"  Duplicate Key: {key_to_check}\n"
                    f"  Events with this key:\n    " + "\n    ".join(duplicate_event_details)
                )
                errors_found += 1
            else:
                seen_keys.add(key_to_check)

        if errors_found > 0:
            msg = f"{errors_found} critical sorting key issues found. Non-deterministic event order or key generation failure detected. Processing cannot continue reliably."
            logger.critical(msg)
            raise ValueError(msg) 
        else:
            logger.info("Event sorting keys validated successfully for uniqueness and completeness.")

        logger.info(f"Total financial domain events generated and sorted: {len(self.domain_financial_events)}")
        return self.domain_financial_events


    def run_parsing_pipeline(self,
                             trades_file: Optional[str] = None,
                             cash_transactions_file: Optional[str] = None,
                             positions_start_file: Optional[str] = None,
                             positions_end_file: Optional[str] = None,
                             positions_prior_start_file: Optional[str] = None,
                             positions_prior_end_file: Optional[str] = None,
                             positions_prior_opening_file: Optional[str] = None,
                             corporate_actions_file: Optional[str] = None,
                             cash_balance_file: Optional[str] = None,
                             options_eae_file: Optional[str] = None,
                             positions_mark_files: Optional[Dict[int, str]] = None,
                             tax_year: Optional[int] = None
                             ) -> List[FinancialEvent]:
        logger.info("Starting parsing pipeline...")
        try:
            self.load_all_raw_data(
                trades_file=trades_file,
                cash_transactions_file=cash_transactions_file,
                positions_start_file=positions_start_file,
                positions_end_file=positions_end_file,
                positions_prior_start_file=positions_prior_start_file,
                positions_prior_end_file=positions_prior_end_file,
                positions_prior_opening_file=positions_prior_opening_file,
                corporate_actions_file=corporate_actions_file,
                cash_balance_file=cash_balance_file,
                options_eae_file=options_eae_file,
                positions_mark_files=positions_mark_files,
            )
            self.process_positions(tax_year=tax_year)
            self._process_cash_balance_positions(tax_year=tax_year)
            self.discover_assets_from_transactions()
            self.asset_resolver.link_derivatives()
            self.finalize_asset_classifications()
            self._verify_prior_year_snapshot_survived_classification()
            self._ensure_soy_quantities_are_set()

            event_factory = DomainEventFactory(asset_resolver=self.asset_resolver)
            # MODIFIED: Call the new method that prepares for linking
            self.create_domain_events_and_prepare_for_linking(event_factory)
            
            # NEW STEP: Perform the linking using the collected candidate events
            logger.info("Performing option trade linking post-event creation...")
            perform_option_trade_linking(
                asset_resolver=self.asset_resolver,
                candidate_option_lifecycle_events=self.candidate_option_lifecycle_events,
                candidate_stock_trades_for_linking=self.candidate_stock_trades_for_linking
            )
            # self.domain_financial_events now contains events with potentially updated related_option_event_id
            
            # NEW STEP: Perform withholding tax linking
            logger.info("Performing withholding tax linking...")
            wht_linker = WithholdingTaxLinker()
            successful_links, unlinked_wht_events = wht_linker.link_withholding_tax_events(self.domain_financial_events)
            
            # Log linking statistics
            logger.info(f"Withholding tax linking completed: {len(successful_links)} successful links, {len(unlinked_wht_events)} unlinked WHT events")
            if unlinked_wht_events:
                logger.warning(f"Unlinked withholding tax events:")
                for wht_event in unlinked_wht_events:
                    logger.warning(f"  - WHT Event {wht_event.event_id}: Date={wht_event.event_date}, Amount={wht_event.gross_amount_foreign_currency} {wht_event.local_currency}, Desc='{wht_event.ibkr_activity_description}'")
            
            # Post-process DI/ED dividend rights matching
            self._process_dividend_rights_matching()
            
            logger.info("Parsing pipeline (including linking) completed.")
            return self.get_all_financial_events() # This will sort all events
        except ValueError as e:
            logger.critical(f"Terminating parsing pipeline due to critical error: {e}")
            raise e 
        except Exception as e:
            logger.critical(f"Terminating parsing pipeline due to unexpected error: {e}", exc_info=True)
            raise e
