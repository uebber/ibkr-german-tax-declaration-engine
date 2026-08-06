# src/parsers/parsing_orchestrator.py
import uuid
from decimal import Decimal, getcontext
from typing import List, Dict, Optional, Any, Set, Tuple
from datetime import datetime, date
import logging
import sys 

from src.domain.assets import (
    Asset, InvestmentFund, Option, CashBalance, Derivative, Stock, Bond, PrivateSaleAsset, Cfd # Changed Section23EstgAsset to PrivateSaleAsset
)
# FinancialEvent, OptionLifecycleEvent, TradeEvent for type hinting
from src.domain.events import FinancialEvent, OptionLifecycleEvent, TradeEvent
from src.domain.enums import FinancialEventType, AssetCategory, InvestmentFundType
from src.domain.exceptions import DataIntegrityError
from src.identification.asset_resolver import AssetResolver
from src.classification.asset_classifier import AssetClassifier
from src.utils.sorting_utils import get_event_sort_key
from src.utils.type_utils import parse_ibkr_date, parse_ibkr_datetime, safe_decimal
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

class ParsingOrchestrator:
    def __init__(self, asset_resolver: AssetResolver, asset_classifier: AssetClassifier, interactive_classification: bool = True):
        self.asset_resolver = asset_resolver
        self.asset_classifier = asset_classifier
        self.interactive_classification = interactive_classification

        self.raw_trades: List[RawTradeRecord] = []
        self.raw_cash_transactions: List[RawCashTransactionRecord] = []
        self.raw_positions_start: List[RawPositionRecord] = []
        self.raw_positions_end: List[RawPositionRecord] = []
        # Preceding calendar year's snapshots -- Vorabpauschale only. See Asset.prior_year_*.
        self.raw_positions_prior_start: List[RawPositionRecord] = []
        self.raw_positions_prior_end: List[RawPositionRecord] = []
        self.raw_positions_prior_opening: List[RawPositionRecord] = []
        # Which prior-year snapshot fields were read onto which asset, so the pipeline can
        # verify they are still there once classification has run. See
        # _verify_prior_year_snapshot_survived_classification.
        self._prior_year_snapshot_fields: Dict[uuid.UUID, Dict[str, Any]] = {}
        # Funds whose Satz 2 price had to be taken from the wrong day. Drained into the
        # data-gap channel by the pipeline, so it reaches the report rather than the log.
        self.vorabpauschale_price_substitutions: List[Tuple[str, str]] = []
        self.raw_corporate_actions: List[RawCorporateActionRecord] = []
        self.raw_cash_balances: List[RawCashBalanceRecord] = []
        self.raw_options_eae: List[RawOptionsEAERecord] = []

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
                           options_eae_file: Optional[str] = None):
        # ... (implementation is the same)
        if trades_file:
            self.raw_trades = parse_trades_csv(trades_file)
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
            self.raw_options_eae = parse_options_eae_csv(options_eae_file)
            logger.info(f"Loaded {len(self.raw_options_eae)} raw OptionEAE records.")

    def process_positions(self):
        # ... (implementation is the same)
        logger.info("Processing start-of-year positions...")
        for raw_pos in self.raw_positions_start:
            asset = self.asset_resolver.get_or_create_asset(
                raw_isin=raw_pos.isin, raw_conid=raw_pos.conid, raw_symbol=raw_pos.symbol,
                raw_currency=raw_pos.currency_primary, raw_ibkr_asset_class=raw_pos.asset_class,
                raw_description=raw_pos.description,
                description_source_type="position",
                raw_multiplier=raw_pos.multiplier, raw_strike=raw_pos.strike,
                raw_expiry=raw_pos.expiry, raw_put_call=raw_pos.put_call,
                raw_underlying_conid=raw_pos.underlying_conid,
                raw_underlying_symbol=raw_pos.underlying_symbol
            )
            asset.soy_quantity = safe_decimal(raw_pos.position, default=Decimal(0)) # Changed from initial_quantity_soy
            asset.soy_cost_basis_amount = safe_decimal(raw_pos.cost_basis_money) # Changed from initial_cost_basis_money_soy
            asset.soy_cost_basis_currency = raw_pos.currency_primary # Changed from initial_cost_basis_currency_soy
            asset.soy_position_value = safe_decimal(raw_pos.position_value)
            asset.soy_mark_price_currency = raw_pos.currency_primary
            logger.debug(f"Asset {asset.get_classification_key()} SOY: Qty={asset.soy_quantity}, Cost={asset.soy_cost_basis_amount} {asset.soy_cost_basis_currency}")

        logger.info("Processing end-of-year positions...")
        for raw_pos in self.raw_positions_end:
            asset = self.asset_resolver.get_or_create_asset(
                raw_isin=raw_pos.isin, raw_conid=raw_pos.conid, raw_symbol=raw_pos.symbol,
                raw_currency=raw_pos.currency_primary, raw_ibkr_asset_class=raw_pos.asset_class,
                raw_description=raw_pos.description,
                description_source_type="position",
                raw_multiplier=raw_pos.multiplier, raw_strike=raw_pos.strike,
                raw_expiry=raw_pos.expiry, raw_put_call=raw_pos.put_call,
                raw_underlying_conid=raw_pos.underlying_conid,
                raw_underlying_symbol=raw_pos.underlying_symbol
            )
            asset.eoy_quantity = safe_decimal(raw_pos.position, default=Decimal(0))
            asset.eoy_market_price = safe_decimal(raw_pos.mark_price) # Changed from eoy_mark_price
            asset.eoy_position_value = safe_decimal(raw_pos.position_value)
            asset.eoy_mark_price_currency = raw_pos.currency_primary
            logger.debug(f"Asset {asset.get_classification_key()} EOY: Qty={asset.eoy_quantity}, Val={asset.eoy_position_value} {asset.currency}")

        # Preceding calendar year's snapshots. Used ONLY by the Vorabpauschale, which for a VZ Y
        # declaration is the one computed for calendar Y-1 (18 Abs. 3 InvStG). These must not
        # feed cost basis, reconciliation or any other consumer.
        logger.info("Processing prior-year positions (Vorabpauschale reference prices)...")
        for raw_pos in self.raw_positions_prior_start:
            asset = self._resolve_asset_from_position(raw_pos)
            asset.prior_year_soy_quantity = safe_decimal(raw_pos.position, default=Decimal(0))
            asset.prior_year_soy_position_value = safe_decimal(raw_pos.position_value)
            asset.prior_year_soy_mark_price = safe_decimal(raw_pos.mark_price)
            asset.prior_year_soy_mark_price_currency = raw_pos.currency_primary
            self._record_prior_year_snapshot_fields(asset, (
                "prior_year_soy_quantity", "prior_year_soy_position_value",
                "prior_year_soy_mark_price", "prior_year_soy_mark_price_currency",
            ))

        for raw_pos in self.raw_positions_prior_end:
            asset = self._resolve_asset_from_position(raw_pos)
            asset.prior_year_eoy_quantity = safe_decimal(raw_pos.position, default=Decimal(0))
            asset.prior_year_eoy_position_value = safe_decimal(raw_pos.position_value)
            asset.prior_year_eoy_mark_price = safe_decimal(raw_pos.mark_price)
            asset.prior_year_eoy_mark_price_currency = raw_pos.currency_primary
            self._record_prior_year_snapshot_fields(asset, (
                "prior_year_eoy_quantity", "prior_year_eoy_position_value",
                "prior_year_eoy_mark_price", "prior_year_eoy_mark_price_currency",
            ))

        for raw_pos in self.raw_positions_prior_opening:
            asset = self._resolve_asset_from_position(raw_pos)
            asset.prior_year_opening_quantity = safe_decimal(raw_pos.position, default=Decimal(0))
            asset.prior_year_opening_mark_price = safe_decimal(raw_pos.mark_price)
            asset.prior_year_opening_mark_price_currency = raw_pos.currency_primary
            self._record_prior_year_snapshot_fields(asset, (
                "prior_year_opening_quantity", "prior_year_opening_mark_price",
                "prior_year_opening_mark_price_currency",
            ))

        self._compose_vorabpauschale_base_value()

    def _compose_vorabpauschale_base_value(self) -> None:
        """
        Build the Basisertrag's base from a price and a unit count taken at the
        same moment: the start of the Vorabpauschale year.

        For the Vorabpauschale of calendar X, the price is the first one set in
        X (18 Abs. 1 Satz 2 InvStG, resolved by open question Q12), and the unit
        count is the holding at the close of X-1 -- the position that price
        applies to. Where a fund was sold on X's first trading day it is absent
        from that snapshot, and the last price before the year began stands in:
        one trading day early rather than a year late.

        Which unit count the Vorabpauschale should then be multiplied by is a
        separate question about that computation, not about this bookkeeping:
        Rz. 18.4 names the holding at the close of X, and the position taken here
        is recorded against GT-INVSTG-017 in docs/legal-implementation-map.md.

        The composed figure is written into the field the Vorabpauschale already
        consumes, so the calculation itself is untouched.
        """
        for asset in self.asset_resolver.assets_by_internal_id.values():
            units = getattr(asset, "prior_year_opening_quantity", None)
            if units is None or units <= Decimal(0):
                # Nothing held when the year opened: no Basisertrag to scale. Units acquired
                # during the year are Abs. 2's pro-rata case (GT-INVSTG-011, GT-INVSTG-035),
                # which is not implemented -- and inventing a full-year Basisertrag for them
                # would be a plausible wrong number rather than a missing one.
                continue

            price = getattr(asset, "prior_year_soy_mark_price", None)
            if price is None:
                price = getattr(asset, "prior_year_opening_mark_price", None)
                if price is None:
                    continue
                self.vorabpauschale_price_substitutions.append(
                    (asset.get_classification_key(), asset.description or ""))
                logger.warning(
                    "Vorabpauschale for %s: no price on the first trading day of the year "
                    "though the fund was held when it opened; using the last price set "
                    "before the year began.",
                    asset.get_classification_key(),
                )

            composed = price * units
            previous = asset.prior_year_soy_position_value
            asset.prior_year_soy_position_value = composed
            if previous is not None and previous != composed:
                logger.debug(
                    "Vorabpauschale base for %s: price %s x opening units %s = %s "
                    "(the snapshot's own value was %s).",
                    asset.get_classification_key(), price, units, composed, previous,
                )

    def _record_prior_year_snapshot_fields(self, asset: Asset, field_names: Tuple[str, ...]) -> None:
        """Note which prior-year snapshot values this asset now carries.

        An alias is kept alongside the field names because the asset object recorded here need
        not be the one the engine sees. Two later rows whose identifiers overlap are merged, and
        the merge deletes the losing asset and repoints its aliases at the winner. Looking the
        alias up again resolves to whichever asset ends up owning the instrument.
        """
        present = {name for name in field_names if getattr(asset, name, None) is not None}
        if not present:
            return
        record = self._prior_year_snapshot_fields.setdefault(
            asset.internal_asset_id, {"fields": set(), "alias": None})
        record["fields"].update(present)
        if record["alias"] is None and asset.aliases:
            record["alias"] = next(iter(asset.aliases))

    def _verify_prior_year_snapshot_survived_classification(self) -> None:
        """Every prior-year snapshot value read above must still be on its asset.

        Classification replaces an asset's Python type by building a new object and copying
        the old one's fields across (`AssetResolver.replace_asset_type`). A field the copy
        does not list is dropped, and the drop is invisible: the Vorabpauschale then finds no
        year-start Ruecknahmepreis and skips the fund, so its deemed income leaves the
        declaration with nothing recorded anywhere. This checks the values that were read are
        the values the engine will see, and reports every affected asset at once.

        Two conditions bound what it reports, and both are deliberate:

        - **Only investment funds.** 18 InvStG reaches nothing else, so nothing else can lose a
          declared figure this way. The prior-year snapshot is read for every instrument in the
          file, and aborting a run because a share or a bond lost a value it has no use for
          would stop a declaration that is not at risk.
        - **Only where a value was actually read.** A fund bought during the Vorabpauschale year
          has no prior-year snapshot row and is never registered, so a legitimate absence cannot
          trip this.

        The asset is looked up by alias rather than by id, so an instrument that was merged into
        another after its snapshot was read is followed to the asset that now owns it.
        """
        losses: List[str] = []
        checked = 0
        for asset_id, record in self._prior_year_snapshot_fields.items():
            asset = self.asset_resolver.assets_by_internal_id.get(asset_id)
            if asset is None and record["alias"] is not None:
                # Merged into another asset; the surviving one is what the engine will read.
                asset = self.asset_resolver.alias_map.get(record["alias"])
            if not isinstance(asset, InvestmentFund):
                continue
            checked += 1
            lost = sorted(name for name in record["fields"] if getattr(asset, name, None) is None)
            if lost:
                losses.append(f"{asset.get_classification_key()} ({asset.description}): {', '.join(lost)}")

        if losses:
            raise DataIntegrityError(
                "The preceding year's position snapshot was read for "
                f"{checked} investment fund(s) but no longer reaches the calculation for "
                f"{len(losses)} of them. The Vorabpauschale for that year (18 Abs. 1 InvStG) is "
                "computed from these values, so the affected funds would drop out of Anlage "
                "KAP-INV Zeilen 9-13 without a figure and without a warning. This is an engine "
                "defect, not an input problem: the values were read and then lost -- either by a "
                "field missing from AssetResolver._extract_common_asset_fields, or by a merge of "
                "two identifiers that carried the aliases across but not the values. Affected: "
                + "; ".join(losses)
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
            raw_multiplier=raw_pos.multiplier, raw_strike=raw_pos.strike,
            raw_expiry=raw_pos.expiry, raw_put_call=raw_pos.put_call,
            raw_underlying_conid=raw_pos.underlying_conid,
            raw_underlying_symbol=raw_pos.underlying_symbol
        )

    def discover_assets_from_transactions(self):
        # ... (implementation is the same)
        logger.info("Discovering assets from trades, cash transactions, and corporate actions...")
        for rt in self.raw_trades:
            self.asset_resolver.get_or_create_asset(
                raw_isin=rt.isin or rt.security_id if rt.security_id_type == "ISIN" else rt.isin,
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
                    raw_isin=rct.isin or rct.security_id if rct.security_id_type == "ISIN" else rct.isin,
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
                raw_isin=rca.isin or rca.security_id if rca.security_id_type == "ISIN" else rca.isin,
                raw_conid=rca.conid, raw_symbol=rca.symbol, raw_currency=rca.currency_primary,
                raw_ibkr_asset_class=rca.asset_class, raw_description=rca.description,
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

            # Set SOY/EOY quantities (can be negative for short positions)
            cash_asset.soy_quantity = raw_balance.starting_cash
            cash_asset.eoy_quantity = raw_balance.ending_cash

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
                if asset_obj.soy_quantity is None: # Changed from initial_quantity_soy
                    asset_obj.soy_quantity = Decimal(0) # Changed from initial_quantity_soy
                    asset_obj.soy_cost_basis_amount = Decimal(0) # Changed from initial_cost_basis_money_soy
                    asset_obj.soy_cost_basis_currency = None # Changed from initial_cost_basis_currency_soy
                    logger.debug(
                        f"Asset {asset_obj.get_classification_key()} (ID: {asset_id}) was not in SOY report. "
                        f"Set soy_quantity to 0, soy_cost_basis_amount to 0."
                    )
                    assets_updated_count +=1
                elif asset_obj.soy_quantity != Decimal(0) and asset_obj.soy_cost_basis_amount is None: # Changed from initial_quantity_soy and initial_cost_basis_money_soy
                     logger.warning(f"Asset {asset_obj.get_classification_key()} (ID: {asset_id}) had non-zero SOY quantity ({asset_obj.soy_quantity}) but missing cost basis. Setting SOY cost basis to 0.")
                     asset_obj.soy_cost_basis_amount = Decimal(0) # Changed from initial_cost_basis_money_soy
                     asset_obj.soy_cost_basis_currency = None # Changed from initial_cost_basis_currency_soy
                elif not isinstance(asset_obj.soy_quantity, Decimal): # Changed from initial_quantity_soy
                    logger.warning(f"Asset {asset_obj.get_classification_key()} (ID: {asset_id}) had non-Decimal SOY quantity ({asset_obj.soy_quantity}, type {type(asset_obj.soy_quantity)}). Converting to Decimal.")
                    asset_obj.soy_quantity = safe_decimal(asset_obj.soy_quantity, default=Decimal(0)) # Changed from initial_quantity_soy

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

        logger.info(f"DomainEventFactory created {len(self.domain_financial_events)} total financial events initially.")
        logger.info(f"Collected {len(self.candidate_option_lifecycle_events)} candidate option lifecycle events for linking.")
        logger.info(f"Collected {len(self.candidate_stock_trades_for_linking)} candidate stock trades for linking.")


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
                corporate_actions_file=corporate_actions_file,
                cash_balance_file=cash_balance_file,
                options_eae_file=options_eae_file
            )
            self.process_positions()
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
