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
from src.identification.asset_resolver import AssetResolver
from src.classification.asset_classifier import AssetClassifier
from src.utils.sorting_utils import get_event_sort_key
from src.utils.type_utils import parse_ibkr_date, parse_ibkr_datetime, safe_decimal
import src.config as global_config 

from .raw_models import (
    RawTradeRecord, RawCashTransactionRecord, RawPositionRecord, RawCorporateActionRecord
)
from .trades_parser import parse_trades_csv
from .cash_transactions_parser import parse_cash_transactions_csv
from .positions_parser import parse_positions_csv
from .corporate_actions_parser import parse_corporate_actions_csv
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
        self.raw_corporate_actions: List[RawCorporateActionRecord] = []

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
                           corporate_actions_file: Optional[str] = None):
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
        if corporate_actions_file:
            self.raw_corporate_actions = parse_corporate_actions_csv(corporate_actions_file)
            logger.info(f"Loaded {len(self.raw_corporate_actions)} raw corporate action records.")

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
                        "EXPIRE DIVIDEND RIGHT" in event.ibkr_activity_description.upper()):
                        
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
        
        Example: 'LEG(DE000LEG1110) DIVIDEND RIGHTS ISSUE...' -> 'DE000LEG1110'
        """
        if not description:
            return None
        
        # Look for ISIN pattern in parentheses: (DE000LEG1110)
        import re
        isin_match = re.search(r'\(([A-Z]{2}[A-Z0-9]{10})\)', description)
        return isin_match.group(1) if isin_match else None

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

        # Populate the main list of events
        self.domain_financial_events.clear() # Clear if run multiple times (though not typical)
        self.domain_financial_events.extend(all_trade_events)
        self.domain_financial_events.extend(cash_events)
        self.domain_financial_events.extend(ca_events)

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
                             corporate_actions_file: Optional[str] = None
                             ) -> List[FinancialEvent]:
        logger.info("Starting parsing pipeline...")
        try:
            self.load_all_raw_data(
                trades_file=trades_file,
                cash_transactions_file=cash_transactions_file,
                positions_start_file=positions_start_file,
                positions_end_file=positions_end_file,
                corporate_actions_file=corporate_actions_file
            )
            self.process_positions()
            self.discover_assets_from_transactions()
            self.asset_resolver.link_derivatives()
            self.finalize_asset_classifications()
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
