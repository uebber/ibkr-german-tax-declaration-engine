# src/parsers/domain_event_factory.py
import logging
import re
from decimal import Decimal
from typing import List, Optional, Set, Union, Tuple # Ensure Tuple is here
from datetime import date, datetime

from src.domain.assets import Asset, Option, CashBalance, InvestmentFund, Derivative, Stock, Bond
from src.domain.events import (
    FinancialEvent, TradeEvent, CashFlowEvent, WithholdingTaxEvent,
    CorporateActionEvent, CorpActionSplitForward, CorpActionMergerCash,
    CorpActionMergerStock, CorpActionStockDividend, OptionLifecycleEvent,
    OptionExerciseEvent, OptionAssignmentEvent, OptionExpirationWorthlessEvent,
    CurrencyConversionEvent, FeeEvent
)
from src.domain.enums import FinancialEventType, AssetCategory, InvestmentFundType
from src.identification.asset_resolver import AssetResolver
from src.parsers.raw_models import (
    RawTradeRecord, RawCashTransactionRecord, RawCorporateActionRecord
)
from src.utils.type_utils import parse_ibkr_date, parse_ibkr_datetime, safe_decimal

logger = logging.getLogger(__name__)

class DomainEventFactory:
    def __init__(self, asset_resolver: AssetResolver):
        self.asset_resolver = asset_resolver
        self.processed_ibkr_trade_ids_for_options: Set[str] = set()
        self.wht_on_interest_pattern = re.compile(
            r"WITHHOLDING\s*(?:@\s*\d{1,3}(?:\.\d+)?%)?\s*ON\s*(?:CREDIT\s*)?INT(?:EREST)?.*",
            re.IGNORECASE
        )

    @staticmethod
    def _get_prioritized_date(
        settle_date_str: Optional[str] = None,
        pay_date_str: Optional[str] = None,
        trade_or_event_datetime_str: Optional[str] = None,
        trade_date_str: Optional[str] = None,
        report_date_str: Optional[str] = None,
    ) -> Optional[str]:
        parsed_date_obj: Optional[date] = None
        if settle_date_str:
            parsed_date_obj = parse_ibkr_date(settle_date_str)
            if parsed_date_obj: return parsed_date_obj.isoformat()
        if pay_date_str:
            parsed_date_obj = parse_ibkr_date(pay_date_str)
            if parsed_date_obj: return parsed_date_obj.isoformat()
        if trade_or_event_datetime_str:
            dt_obj = parse_ibkr_datetime(trade_or_event_datetime_str)
            if dt_obj: return dt_obj.date().isoformat()
            else:
                parsed_date_obj = parse_ibkr_date(trade_or_event_datetime_str)
                if parsed_date_obj: return parsed_date_obj.isoformat()
        if trade_date_str:
            parsed_date_obj = parse_ibkr_date(trade_date_str)
            if parsed_date_obj: return parsed_date_obj.isoformat()
        if report_date_str:
            parsed_date_obj = parse_ibkr_date(report_date_str)
            if parsed_date_obj: return parsed_date_obj.isoformat()
        return None


    def _determine_trade_event_type(self, raw_trade: RawTradeRecord) -> FinancialEventType:
        buy_sell = (raw_trade.buy_sell or "").upper()
        open_close_ind = (raw_trade.open_close_indicator or "").upper()
        trade_quantity = safe_decimal(raw_trade.quantity, default=Decimal(0))

        if buy_sell == "BUY":
            if open_close_ind == "O": return FinancialEventType.TRADE_BUY_LONG
            if open_close_ind == "C": return FinancialEventType.TRADE_BUY_SHORT_COVER
            logger.warning(
                f"Trade ID {raw_trade.transaction_id or raw_trade.trade_id} (BUY): "
                f"Missing or unexpected Open/Close Indicator: '{raw_trade.open_close_indicator}'. Notes/Codes was: '{raw_trade.notes_codes}'. "
                f"Assuming TRADE_BUY_LONG as default for BUY based on PRD directive for data inconsistency."
            )
            return FinancialEventType.TRADE_BUY_LONG
        elif buy_sell == "SELL":
            if open_close_ind == "O": return FinancialEventType.TRADE_SELL_SHORT_OPEN
            if open_close_ind == "C": return FinancialEventType.TRADE_SELL_LONG
            logger.warning(
                f"Trade ID {raw_trade.transaction_id or raw_trade.trade_id} (SELL): "
                f"Missing or unexpected Open/Close Indicator: '{raw_trade.open_close_indicator}'. Notes/Codes was: '{raw_trade.notes_codes}'. "
                f"Assuming TRADE_SELL_LONG as default for SELL based on PRD directive for data inconsistency."
            )
            return FinancialEventType.TRADE_SELL_LONG

        if trade_quantity != Decimal(0):
            logger.warning(
                f"Trade ID {raw_trade.transaction_id or raw_trade.trade_id}: Buy/Sell indicator missing. "
                f"Using quantity sign to infer trade direction. Open/CloseIndicator was '{open_close_ind}'."
            )
            if trade_quantity > 0:
                return FinancialEventType.TRADE_BUY_SHORT_COVER if open_close_ind == "C" else FinancialEventType.TRADE_BUY_LONG
            if trade_quantity < 0:
                return FinancialEventType.TRADE_SELL_SHORT_OPEN if open_close_ind == "O" else FinancialEventType.TRADE_SELL_LONG

        err_msg = (
            f"Could not determine trade event type for trade: {raw_trade.transaction_id or raw_trade.trade_id}, "
            f"Symbol: {raw_trade.symbol}, Buy/Sell: '{buy_sell}', Open/CloseIndicator: '{open_close_ind}', "
            f"Quantity: {trade_quantity}, Notes/Codes: '{raw_trade.notes_codes}'. "
            "This indicates critical missing or inconsistent data in the trade record."
        )
        logger.error(err_msg)
        raise ValueError(err_msg)

    def _process_option_trade(self, raw_trade: RawTradeRecord, asset: Asset, event_date_str: str) -> Optional[OptionLifecycleEvent]:
        """
        Creates OptionLifecycleEvents (Assignment, Exercise, Expiration) from specific trade records.
        It no longer attempts to populate a linking map.
        It marks the trade ID as processed to avoid re-processing as a generic TradeEvent for the option.
        """
        if not isinstance(asset, Option):
            logger.warning(f"Attempted to process option trade for non-Option asset: {asset.get_classification_key()} (Type: {type(asset).__name__}), Trade ID: {raw_trade.transaction_id or raw_trade.trade_id}. Skipping.")
            return None

        notes_codes_parts = {part.strip() for part in (raw_trade.notes_codes or "").upper().split(';') if part.strip()}
        option_event_type: Optional[FinancialEventType] = None

        if 'A' in notes_codes_parts: option_event_type = FinancialEventType.OPTION_ASSIGNMENT
        elif 'EX' in notes_codes_parts: option_event_type = FinancialEventType.OPTION_EXERCISE
        elif 'EP' in notes_codes_parts: option_event_type = FinancialEventType.OPTION_EXPIRATION_WORTHLESS

        if option_event_type:
            raw_trade_quantity_val = safe_decimal(raw_trade.quantity, default=Decimal(0))
            qty_contracts = raw_trade_quantity_val.copy_abs()

            tx_id_for_event = raw_trade.transaction_id or raw_trade.trade_id
            if not tx_id_for_event:
                logger.error(f"Option lifecycle event ({option_event_type.name}) for {asset.get_classification_key()} on {event_date_str} lacks a transaction ID. Skipping event.")
                return None

            gross_amount_val = Decimal('0.0')

            common_args = {
                "asset_internal_id": asset.internal_asset_id,
                "event_date": event_date_str,
                "quantity_contracts": qty_contracts,
                "gross_amount_foreign_currency": gross_amount_val,
                "local_currency": raw_trade.currency_primary,
                "ibkr_transaction_id": tx_id_for_event,
                "ibkr_activity_description": raw_trade.description,
                "ibkr_notes_codes": raw_trade.notes_codes
            }

            option_event: Optional[OptionLifecycleEvent] = None
            if option_event_type == FinancialEventType.OPTION_ASSIGNMENT:
                option_event = OptionAssignmentEvent(**common_args)
            elif option_event_type == FinancialEventType.OPTION_EXERCISE:
                option_event = OptionExerciseEvent(**common_args)
            elif option_event_type == FinancialEventType.OPTION_EXPIRATION_WORTHLESS:
                option_event = OptionExpirationWorthlessEvent(**common_args)

            if option_event:
                logger.debug(f"Created {option_event_type.name} for option {asset.get_classification_key()} from trade ID {tx_id_for_event}, Contracts: {qty_contracts}")

                self.processed_ibkr_trade_ids_for_options.add(tx_id_for_event)
                if raw_trade.trade_id and raw_trade.trade_id != raw_trade.transaction_id:
                    self.processed_ibkr_trade_ids_for_options.add(raw_trade.trade_id)

                return option_event
        return None

    def create_events_from_trades(self, raw_trades: List[RawTradeRecord]) -> Tuple[List[FinancialEvent], List[OptionLifecycleEvent], List[TradeEvent]]:
        logger.info(f"Processing {len(raw_trades)} raw trade records into domain events (linking deferred)...")
        all_created_events: List[FinancialEvent] = []
        candidate_option_lifecycle_events: List[OptionLifecycleEvent] = []
        candidate_stock_trades_for_linking: List[TradeEvent] = []

        self.processed_ibkr_trade_ids_for_options.clear()

        for rt in raw_trades:
            tx_id_primary = rt.transaction_id or rt.trade_id
            if not tx_id_primary:
                 logger.error(f"Trade record for Symbol: {rt.symbol}, Date: {rt.trade_date}, Qty: {rt.quantity} lacks both transaction_id and trade_id. Skipping.")
                 continue

            asset = self.asset_resolver.get_or_create_asset(
                raw_isin=rt.isin or rt.security_id if rt.security_id_type == "ISIN" else rt.isin,
                raw_conid=rt.conid, raw_symbol=rt.symbol, raw_currency=rt.currency_primary,
                raw_ibkr_asset_class=rt.asset_class, raw_description=rt.description,
                description_source_type="trade",
                raw_ibkr_sub_category=rt.sub_category, raw_multiplier=rt.multiplier,
                raw_strike=rt.strike, raw_expiry=rt.expiry, raw_put_call=rt.put_call,
                raw_underlying_conid=rt.underlying_conid, raw_underlying_symbol=rt.underlying_symbol
            )

            trade_datetime_str = f"{rt.trade_date} {rt.trade_time or '00:00:00'}" if rt.trade_date else None
            event_date_str_or_none = self._get_prioritized_date(
                settle_date_str=rt.settle_date_target,
                trade_or_event_datetime_str=trade_datetime_str,
                trade_date_str=rt.trade_date,
                report_date_str=rt.report_date
            )
            if not event_date_str_or_none:
                 logger.error(f"Could not determine a valid event date for trade: {tx_id_primary}, Symbol: {rt.symbol}. Skipping event creation.")
                 continue
            event_date_str = event_date_str_or_none

            current_event_processed_as_option_lifecycle = False
            if isinstance(asset, Option):
                option_lifecycle_event = self._process_option_trade(rt, asset, event_date_str)
                if option_lifecycle_event:
                    all_created_events.append(option_lifecycle_event)
                    # Collect Exercise/Assignment events for later linking
                    if isinstance(option_lifecycle_event, (OptionExerciseEvent, OptionAssignmentEvent)):
                        candidate_option_lifecycle_events.append(option_lifecycle_event)
                    current_event_processed_as_option_lifecycle = True

            if not current_event_processed_as_option_lifecycle:
                is_fx_pair_instrument_trade = False
                if asset.ibkr_asset_class_raw == "CASH" and \
                   asset.ibkr_symbol and '.' in asset.ibkr_symbol:
                     parts = asset.ibkr_symbol.split('.')
                     if len(parts) == 2 and len(parts[0]) == 3 and len(parts[1]) == 3:
                        is_fx_pair_instrument_trade = True

                if is_fx_pair_instrument_trade:
                    parts = asset.ibkr_symbol.split('.')
                    curr1, curr2 = parts[0].upper(), parts[1].upper()
                    from_curr, to_curr = "", ""
                    from_amt_val, to_amt_val = Decimal(0), Decimal(0)

                    rate = safe_decimal(rt.trade_price, default=Decimal(0))
                    base_monetary_value_raw = rt.trade_money if rt.trade_money is not None else rt.proceeds
                    base_monetary_value = safe_decimal(base_monetary_value_raw, default=Decimal(0))
                    trade_quantity_val = safe_decimal(rt.quantity, default=Decimal(0))

                    if base_monetary_value == Decimal(0) and trade_quantity_val != Decimal(0) and rate != Decimal(0):
                        calculated_second_leg_amount = trade_quantity_val.copy_abs() * rate
                        logger.warning(
                            f"FX Pair trade {tx_id_primary} ({asset.ibkr_symbol}): "
                            f"TradeMoney/Proceeds was missing or zero (Original base_monetary_value_raw: '{base_monetary_value_raw}'). "
                            f"Calculating the second leg amount from Quantity ({trade_quantity_val} {curr1}) and Rate ({rate} {curr2}/{curr1}). "
                            f"Calculated second leg: {calculated_second_leg_amount:.4f} {curr2}."
                        )
                        base_monetary_value = calculated_second_leg_amount.copy_abs()

                    if trade_quantity_val == Decimal(0):
                        logger.error(f"FX Pair trade {tx_id_primary} of {asset.ibkr_symbol} has zero quantity. Cannot determine direction/amounts.")
                        continue

                    if trade_quantity_val > 0: # Buying curr1 (e.g., EUR in EUR.USD)
                        to_curr = curr1                        # e.g., EUR
                        to_amt_val = trade_quantity_val.copy_abs() # Amount of curr1 bought
                        from_curr = curr2                      # e.g., USD
                        from_amt_val = base_monetary_value.copy_abs() # Amount of curr2 sold
                    else: # Selling curr1 (e.g., EUR in EUR.USD)
                        from_curr = curr1                      # e.g., EUR
                        from_amt_val = trade_quantity_val.copy_abs() # Amount of curr1 sold
                        to_curr = curr2                        # e.g., USD
                        to_amt_val = base_monetary_value.copy_abs() # Amount of curr2 bought

                    calculated_rate = None
                    if to_amt_val != Decimal(0) and from_amt_val != Decimal(0): # Ensure not to divide by zero
                        if trade_quantity_val > 0: # Buying C1. to_curr = C1, from_curr = C2. rate = C2/C1
                            calculated_rate = from_amt_val / to_amt_val
                        else: # Selling C1. from_curr = C1, to_curr = C2. rate = C2/C1
                            calculated_rate = to_amt_val / from_amt_val

                    if rate == Decimal(0) or (calculated_rate is not None and calculated_rate != Decimal(0) and abs(rate - calculated_rate) > (Decimal('0.0001') * rate) ):
                        if calculated_rate is not None and calculated_rate != Decimal(0): # Ensure calculated_rate is usable
                            logger.warning(f"FX Pair trade {tx_id_primary}: Using calculated rate {calculated_rate:.6f} instead of reported rate {rate:.6f} due to discrepancy.")
                            rate = calculated_rate
                        elif rate == Decimal(0): # Both reported and calculable rates are zero/invalid
                            logger.error(f"FX Pair trade {tx_id_primary}: Reported rate is {rate}, and could not calculate a valid rate from amounts (From: {from_amt_val} {from_curr}, To: {to_amt_val} {to_curr}). Cannot determine rate.")
                            continue
                        elif rate != Decimal(0) and (calculated_rate is None or calculated_rate == Decimal(0)):
                             logger.warning(f"FX Pair trade {tx_id_primary}: Could not calculate a valid rate from amounts, but reported rate is {rate:.6f}. Proceeding with reported rate.")

                    if not from_curr or not to_curr or from_amt_val <= Decimal(0) or to_amt_val <= Decimal(0) or (rate is None or rate <= Decimal(0)):
                        logger.error(f"Could not determine valid amounts/currencies/rate for FX Pair trade {tx_id_primary} of {asset.ibkr_symbol}. From: {from_amt_val} {from_curr}, To: {to_amt_val} {to_curr}, Rate: {rate}. Skipping CurrencyConversionEvent.")
                        continue

                    target_cash_balance_asset = self.asset_resolver.get_or_create_asset(
                        raw_isin=None, raw_conid=None, raw_symbol=to_curr,
                        raw_currency=to_curr, raw_ibkr_asset_class="CASH",
                        raw_description=f"Cash Balance {to_curr}",
                        description_source_type="cash_balance_generated"
                    )
                    conv_event = CurrencyConversionEvent(
                        asset_internal_id=target_cash_balance_asset.internal_asset_id,
                        event_date=event_date_str,
                        from_currency=from_curr, from_amount=from_amt_val,
                        to_currency=to_curr, to_amount=to_amt_val,
                        exchange_rate=rate,
                        ibkr_transaction_id=tx_id_primary,
                        ibkr_activity_description=f"FX Pair Trade: {rt.description}",
                        ibkr_notes_codes=rt.notes_codes
                    )
                    all_created_events.append(conv_event)
                    continue

                try:
                    event_type = self._determine_trade_event_type(rt)
                except ValueError as e:
                    logger.error(f"Skipping trade ID {tx_id_primary} due to error determining type: {e}")
                    continue

                trade_quantity_val = safe_decimal(rt.quantity, default=Decimal('0'))
                trade_price = safe_decimal(rt.trade_price, default=Decimal('0.0'))
                calculated_gross_amount_raw_source = rt.trade_money if rt.trade_money is not None else rt.proceeds
                calculated_gross_amount = safe_decimal(calculated_gross_amount_raw_source)

                if calculated_gross_amount is None:
                    asset_multiplier_trade = getattr(asset, 'multiplier', Decimal(1))
                    asset_multiplier_trade = safe_decimal(asset_multiplier_trade, default=Decimal(1))
                    if asset_multiplier_trade == Decimal(0): asset_multiplier_trade = Decimal(1)

                    if trade_price is not None and trade_quantity_val is not None:
                        # Initial calculation: Qty * Price
                        raw_calculated_gross = trade_quantity_val.copy_abs() * trade_price
                        
                        # Apply multiplier if it's significant (not 1 or 0)
                        if asset_multiplier_trade != Decimal(1):
                            raw_calculated_gross *= asset_multiplier_trade
                            logger.debug(f"Trade {tx_id_primary}: Applied multiplier {asset_multiplier_trade}. Intermediate Q*P*M: {raw_calculated_gross}")

                        if isinstance(asset, Bond) or asset.asset_category == AssetCategory.BOND:
                            # Bond prices are typically percentages of nominal value.
                            # Gross value = (Nominal Quantity * Percentage Price / 100) * Multiplier
                            # Since multiplier might already be applied above if it's not 1,
                            # we just need to divide by 100 here.
                            # If multiplier was 1, raw_calculated_gross = Qty * Price. We need (Qty * Price / 100).
                            calculated_gross_amount = raw_calculated_gross / Decimal(100)
                            logger.debug(f"Trade {tx_id_primary} (Bond {asset.get_classification_key()}): "
                                         f"Applied /100 for percentage price. Original Q*P*(M if applicable): {raw_calculated_gross}, "
                                         f"Final Gross amount: {calculated_gross_amount}")
                        else:
                            calculated_gross_amount = raw_calculated_gross
                            logger.debug(f"Trade {tx_id_primary} (Non-Bond {asset.get_classification_key()}): "
                                         f"Calculated gross amount {calculated_gross_amount} from Qty*Price*(Multiplier if applicable).")
                    else:
                        logger.warning(f"Trade {tx_id_primary} for {asset.get_classification_key()} missing proceeds/trade_money and price/quantity for gross amount calculation. Defaulting gross amount to 0.")
                        calculated_gross_amount = Decimal('0.0')
                else:
                    logger.debug(f"Trade {tx_id_primary}: Using provided gross amount from TradeMoney/Proceeds: {calculated_gross_amount} (Source: '{calculated_gross_amount_raw_source}')")


                commission_val = safe_decimal(rt.ib_commission, default=Decimal('0.0')).copy_abs()

                trade_event = TradeEvent(
                    asset_internal_id=asset.internal_asset_id,
                    event_date=event_date_str,
                    event_type=event_type,
                    quantity=trade_quantity_val,
                    price_foreign_currency=trade_price,
                    commission_foreign_currency=commission_val,
                    commission_currency=rt.ib_commission_currency or rt.currency_primary,
                    local_currency=rt.currency_primary,
                    gross_amount_foreign_currency=calculated_gross_amount.copy_abs(),
                    ibkr_transaction_id=tx_id_primary,
                    ibkr_activity_description=rt.description,
                    ibkr_notes_codes=rt.notes_codes
                )

                if isinstance(asset, Stock) and rt.notes_codes:
                    notes_codes_parts_stock = {part.strip() for part in (rt.notes_codes or "").upper().split(';') if part.strip()}
                    if 'A' in notes_codes_parts_stock or 'EX' in notes_codes_parts_stock:
                        candidate_stock_trades_for_linking.append(trade_event)
                        logger.debug(f"Collected stock trade {trade_event.ibkr_transaction_id} (Asset: {asset.get_classification_key()}) for later linking.")

                all_created_events.append(trade_event)
                logger.debug(f"Created TradeEvent: {trade_event.event_type.name} for {asset.get_classification_key()}, Qty: {trade_event.quantity}, Price: {trade_event.price_foreign_currency}, Gross: {trade_event.gross_amount_foreign_currency} {trade_event.local_currency}")

        logger.info(f"Finished initial processing of {len(raw_trades)} raw trade records. Generated {len(all_created_events)} domain events. Linking deferred.")
        logger.info(f"Collected {len(candidate_option_lifecycle_events)} candidate option lifecycle events and {len(candidate_stock_trades_for_linking)} candidate stock trades for linking.")
        return all_created_events, candidate_option_lifecycle_events, candidate_stock_trades_for_linking

    def create_events_from_cash_transactions(self, raw_cash_transactions: List[RawCashTransactionRecord]) -> List[FinancialEvent]:
        logger.info(f"Processing {len(raw_cash_transactions)} raw cash transaction records into domain events...")
        domain_events: List[FinancialEvent] = []
        for rct in raw_cash_transactions:
            tx_id_for_event = rct.transaction_id
            if not tx_id_for_event:
                logger.error(f"Cash transaction (Type: {rct.type}, Desc: {rct.description}, Date: {rct.settle_date or rct.date_time or rct.report_date}) lacks a transaction ID. Skipping event.")
                continue

            is_instrument_specific_ct = bool(
                rct.isin or \
                rct.conid or \
                (rct.symbol and rct.symbol.strip().upper() != (rct.currency_primary or "").strip().upper())
            )
            asset_for_event: Asset
            if is_instrument_specific_ct:
                asset_for_event = self.asset_resolver.get_or_create_asset(
                    raw_isin=rct.isin or rct.security_id if rct.security_id_type == "ISIN" else rct.isin,
                    raw_conid=rct.conid, raw_symbol=rct.symbol, raw_currency=rct.currency_primary,
                    raw_ibkr_asset_class=rct.asset_class, raw_description=rct.description,
                    description_source_type="cash_tx",
                    raw_ibkr_sub_category=rct.sub_category
                )
            else:
                asset_for_event = self.asset_resolver.get_or_create_asset(
                    raw_isin=None, raw_conid=None, raw_symbol=rct.currency_primary,
                    raw_currency=rct.currency_primary, raw_ibkr_asset_class="CASH",
                    raw_description=f"Cash Balance {rct.currency_primary}",
                    description_source_type="cash_balance_generated",
                    raw_ibkr_sub_category=rct.sub_category
                )

            event_date_str_or_none = self._get_prioritized_date(
                settle_date_str=rct.settle_date,
                trade_or_event_datetime_str=rct.date_time,
                report_date_str=rct.report_date
            )
            if not event_date_str_or_none:
                logger.error(f"Could not determine a valid event date for cash transaction: {rct.transaction_id}, Type: {rct.type}, Desc: {rct.description}. Skipping event creation.")
                continue
            event_date_str = event_date_str_or_none

            event_type_str_upper = (rct.type or "").upper()
            desc_upper = (rct.description or "").upper()
            code_upper = (rct.code or "").upper()
            domain_event_instance: Optional[FinancialEvent] = None
            raw_amount = safe_decimal(rct.amount, default=Decimal(0))
            # Gross amount for events should be absolute for income, or represent the cost if it's an expense.
            # For WithholdingTaxEvent and FeeEvent, raw_amount is typically negative.
            # For CashFlowEvents (Dividend, Interest), raw_amount is typically positive.
            # The event processor or downstream logic will interpret the sign.
            # Here, we store the amount as reported by IBKR.
            # The `gross_amount_foreign_currency` in FinancialEvent itself can be positive.
            # For RGLs, this will be handled correctly. For `other_income_gains_gross` etc.,
            # we add `event_gross_eur` which for WHT/Fees will be negative if `raw_amount` was negative.
            # PdfReportGenerator uses `gross_amount_eur.copy_abs()` or `gross_amount_eur` as needed.
            # The issue with WHT in PDF might be if `gross_amount_eur` for WHT became positive.
            # Let's use raw_amount directly for FinancialEvent.gross_amount_foreign_currency
            # (or its absolute if the convention for that field is always positive value + type).
            # For simplicity, and to align with existing TradeEvent creation, let's use absolute amount + type.

            event_amount_for_storage = raw_amount # Keep sign for some events.
            if event_type_str_upper in ["DIVIDEND", "INTEREST", "PAYMENT IN LIEU"] or \
               code_upper in ["DI", "IN", "PO"]: # Types that are generally income
                event_amount_for_storage = raw_amount.copy_abs()

            event_params_kw = {
                "gross_amount_foreign_currency": event_amount_for_storage,
                "local_currency": rct.currency_primary,
                "ibkr_transaction_id": tx_id_for_event,
                "ibkr_activity_description": rct.description,
                "ibkr_notes_codes": rct.code
            }

            if "DIVIDEND" in event_type_str_upper or \
               (code_upper == "DI" and asset_for_event.asset_category != AssetCategory.CASH_BALANCE and "INTEREST" not in desc_upper):
                evt_type = FinancialEventType.DISTRIBUTION_FUND if isinstance(asset_for_event, InvestmentFund) else FinancialEventType.DIVIDEND_CASH
                domain_event_instance = CashFlowEvent(asset_for_event.internal_asset_id, event_date_str, event_type=evt_type, source_country_code=rct.issuer_country_code, **event_params_kw)

            elif "INTEREST" in event_type_str_upper or code_upper == "IN" or desc_upper.startswith("CREDIT INTEREST") or desc_upper.startswith("DEBIT INTEREST"):
                source_country_for_interest = rct.issuer_country_code
                if asset_for_event.asset_category == AssetCategory.CASH_BALANCE and \
                   ("BROKER INTEREST" in desc_upper or "DEPOSIT INTEREST" in desc_upper or desc_upper.startswith("CREDIT INTEREST")):
                    source_country_for_interest = "IE"

                # Stückzinsen (Accrued Interest Paid) are typically costs (negative amount)
                # Interest Received are income (positive amount)
                is_stueckzinsen_paid = (
                    asset_for_event.asset_category == AssetCategory.BOND and
                    ("STÜCKZINSEN" in desc_upper or "ACCRUED INT" in desc_upper) and # Changed "INTEREST" to "INT"
                    raw_amount < Decimal(0) # Explicitly paid
                )
                is_stueckzinsen_received = ( # Added for completeness, though might be part of sell proceeds logic
                    asset_for_event.asset_category == AssetCategory.BOND and
                    ("STÜCKZINSEN" in desc_upper or "ACCRUED INT" in desc_upper) and # Changed "INTEREST" to "INT"
                    raw_amount > Decimal(0) # Explicitly received
                )

                if is_stueckzinsen_paid:
                    evt_type = FinancialEventType.INTEREST_PAID_STUECKZINSEN
                    # For INTERES_PAID_STUECKZINSEN, gross_amount_foreign_currency should represent the cost (positive number)
                    event_params_kw["gross_amount_foreign_currency"] = raw_amount.copy_abs()
                elif is_stueckzinsen_received : # If handled as a separate cash event
                     evt_type = FinancialEventType.INTEREST_RECEIVED # Or a more specific type if needed
                     event_params_kw["gross_amount_foreign_currency"] = raw_amount.copy_abs()
                else: # Regular interest received or paid (e.g. on cash balances, margin loans)
                    evt_type = FinancialEventType.INTEREST_RECEIVED
                    # If raw_amount is negative (e.g., debit interest), it should be stored as such
                    # or handled based on event type. For INTEREST_RECEIVED, expect positive.
                    # Let's assume event_params_kw['gross_amount_foreign_currency'] is already set
                    # (it was raw_amount.copy_abs() if it was income type)
                    # This implies interest received will always be positive in event_params_kw.
                    # If debit interest (negative raw_amount) should be stored as negative, change here.
                    # For now, INTEREST_RECEIVED events will have positive gross_amount_foreign_currency.
                    # If debit interest is common, a new event type like INTEREST_PAID_DEBIT might be better.

                domain_event_instance = CashFlowEvent(
                    asset_for_event.internal_asset_id, event_date_str, event_type=evt_type,
                    source_country_code=source_country_for_interest, **event_params_kw
                )

            elif "WITHHOLDING TAX" in event_type_str_upper or code_upper == "WHT" or self.wht_on_interest_pattern.match(rct.description or ""):
                source_country_for_wht: Optional[str] = rct.issuer_country_code
                if self.wht_on_interest_pattern.match(rct.description or "") and not source_country_for_wht:
                    match_country_in_desc = re.search(r"\b([A-Z]{2})\b\s*\(DETAILS\)", desc_upper) # Example pattern
                    if match_country_in_desc: source_country_for_wht = match_country_in_desc.group(1)
                    elif asset_for_event.asset_category == AssetCategory.CASH_BALANCE: source_country_for_wht = "IE"
                
                # WHT amount should be stored as a positive value representing the tax paid.
                # raw_amount for WHT is typically negative in IBKR reports.
                event_params_kw["gross_amount_foreign_currency"] = raw_amount.copy_abs()

                domain_event_instance = WithholdingTaxEvent(
                    asset_internal_id=asset_for_event.internal_asset_id, event_date=event_date_str,
                    source_country_code=source_country_for_wht, **event_params_kw
                )

            elif "PAYMENT IN LIEU" in event_type_str_upper or code_upper == "PO":
                # PIL typically positive income
                event_params_kw["gross_amount_foreign_currency"] = raw_amount.copy_abs()
                domain_event_instance = CashFlowEvent(asset_for_event.internal_asset_id, event_date_str, event_type=FinancialEventType.PAYMENT_IN_LIEU_DIVIDEND, source_country_code=rct.issuer_country_code, **event_params_kw)

            elif "FEE" in event_type_str_upper or code_upper == "FE" or "FEES" in event_type_str_upper:
                # Fees are costs, raw_amount typically negative. Store as positive cost.
                event_params_kw["gross_amount_foreign_currency"] = raw_amount.copy_abs()
                domain_event_instance = FeeEvent(asset_for_event.internal_asset_id, event_date_str, **event_params_kw)

            if domain_event_instance:
                logger.debug(f"Created {type(domain_event_instance).__name__} (Type: {domain_event_instance.event_type.name}) for asset {asset_for_event.get_classification_key()} from cash tx ID {rct.transaction_id}, Amt: {event_params_kw['gross_amount_foreign_currency']} {event_params_kw['local_currency']}")
                domain_events.append(domain_event_instance)
            else:
                logger.debug(f"Cash transaction type '{rct.type}' (Desc: '{rct.description}') for asset {asset_for_event.get_classification_key()} did not map to a specific domain event. Skipping.")
        return domain_events


    def create_events_from_corporate_actions(self, raw_corporate_actions: List[RawCorporateActionRecord]) -> List[CorporateActionEvent]:
        logger.info(f"Processing {len(raw_corporate_actions)} raw corporate action records into domain events...")
        domain_ca_events: List[CorporateActionEvent] = []

        for idx, rca in enumerate(raw_corporate_actions):
            logger.debug(f"CA Record {idx+1}/{len(raw_corporate_actions)}: Data: Symbol='{rca.symbol}', Desc='{rca.description}', Type='{rca.type_ca}', ActionID='{rca.action_id_ibkr}'")

            if not rca.symbol or not rca.description or not rca.type_ca:
                logger.warning(f"CA Record {idx+1}: Skipping due to missing Symbol, Description, or Type. Data: {rca}")
                continue
            logger.debug(f"CA Record {idx+1}: Passed initial essential field check.")

            affected_asset = self.asset_resolver.get_or_create_asset(
                raw_isin=rca.isin or rca.security_id if rca.security_id_type == "ISIN" else rca.isin,
                raw_conid=rca.conid, raw_symbol=rca.symbol,
                raw_currency=rca.currency_primary, raw_ibkr_asset_class=rca.asset_class,
                raw_description=rca.description,
                description_source_type="corp_act_asset"
            )
            logger.debug(f"CA Record {idx+1}: Resolved/Created asset '{affected_asset.get_classification_key()}' (ID: {affected_asset.internal_asset_id}, Symbol on Asset: '{affected_asset.ibkr_symbol}')")

            if not affected_asset.ibkr_symbol and affected_asset.asset_category != AssetCategory.CASH_BALANCE:
                logger.error(f"CA Record {idx+1}: Corporate action (ActionID: {rca.action_id_ibkr}, Type: {rca.type_ca}, CSV Date: {rca.report_date or rca.pay_date or rca.ex_date}) affects asset {affected_asset.internal_asset_id} which lacks an 'ibkr_symbol'. Skipping event.")
                continue
            logger.debug(f"CA Record {idx+1}: Asset has ibkr_symbol ('{affected_asset.ibkr_symbol}') or is CashBalance.")

            event_date_str_or_none = self._get_prioritized_date(
                pay_date_str=rca.pay_date,
                report_date_str=rca.report_date,
                trade_or_event_datetime_str=rca.ex_date
            )
            logger.debug(f"CA Record {idx+1}: Prioritized date determined: '{event_date_str_or_none}' (Pay: {rca.pay_date}, Report: {rca.report_date}, Ex: {rca.ex_date})")
            if not event_date_str_or_none:
                 logger.error(f"CA Record {idx+1}: Could not determine a valid event date for corporate action: {rca.action_id_ibkr}, Type: {rca.type_ca}, Symbol: {rca.symbol}. Skipping event creation.")
                 continue
            event_date_str = event_date_str_or_none
            logger.debug(f"CA Record {idx+1}: Using event date: {event_date_str}")

            ca_type_from_file = (rca.type_ca or "").upper()
            ca_desc_from_file = (rca.description or "").upper()
            logger.debug(f"CA Record {idx+1}: Parsed CA Type from file: '{ca_type_from_file}', Parsed CA Desc from file (upper): '{ca_desc_from_file[:100]}...'")

            domain_ca_event_instance: Optional[CorporateActionEvent] = None
            quantity_ca = safe_decimal(rca.quantity)
            logger.debug(f"CA Record {idx+1}: Raw Quantity: {rca.quantity}, Parsed Decimal Quantity: {quantity_ca}")

            gross_amount_ca_raw = None
            if ca_type_from_file == "TC" and "CASH" in ca_desc_from_file: # Merger for cash
                gross_amount_ca_raw = rca.proceeds # total cash received
                logger.debug(f"CA Record {idx+1} (TC-Cash): Using 'Proceeds' ({rca.proceeds}) for gross amount.")
            elif ca_type_from_file == "HI": # Stock dividend
                gross_amount_ca_raw = rca.value # Fair market value of shares received
                logger.debug(f"CA Record {idx+1} (HI): Using 'Value' ({rca.value}) for gross amount.")
            elif rca.proceeds is not None:
                gross_amount_ca_raw = rca.proceeds
                logger.debug(f"CA Record {idx+1}: Fallback to 'Proceeds' ({rca.proceeds}) for gross amount.")
            elif rca.value is not None:
                gross_amount_ca_raw = rca.value
                logger.debug(f"CA Record {idx+1}: Fallback to 'Value' ({rca.value}) for gross amount.")
            gross_amount_ca = safe_decimal(gross_amount_ca_raw, default=Decimal('0.0'))
            logger.debug(f"CA Record {idx+1}: Final gross_amount_ca (parsed Decimal): {gross_amount_ca}")

            common_ca_params_kw_base = {
                "ca_action_id_ibkr": rca.action_id_ibkr,
                "ibkr_transaction_id": rca.transaction_id,
                "ibkr_activity_description": rca.action_description or rca.description,
                "local_currency": rca.currency_primary or affected_asset.currency,
                "gross_amount_foreign_currency": None # Will be set by specific CA type if applicable
            }
            logger.debug(f"CA Record {idx+1}: common_ca_params_kw_base (pre-gross): {common_ca_params_kw_base}")

            if ca_type_from_file == "FS" or "FORWARD SPLIT" in ca_type_from_file or \
               ("SPLIT" in ca_desc_from_file and "REVERSE" not in ca_desc_from_file):
                logger.debug(f"CA Record {idx+1}: Identified as potential Forward Split.")
                ratio_match = re.search(r"(\d+(?:\.\d+)?)\s*FOR\s*(\d+(?:\.\d+)?)", ca_desc_from_file)
                new_per_old_ratio = None
                if ratio_match:
                    try:
                        new_val_str, old_val_str = ratio_match.group(1), ratio_match.group(2)
                        new_val, old_val = Decimal(new_val_str), Decimal(old_val_str)
                        if old_val != Decimal(0): new_per_old_ratio = new_val / old_val
                        else: logger.warning(f"CA Record {idx+1}: Old value in split ratio is zero for CA {rca.action_id_ibkr}. Ratio: {new_val_str}-for-{old_val_str}.")
                    except Exception as e:
                        logger.warning(f"CA Record {idx+1}: Could not parse split ratio from '{ca_desc_from_file}' for CA {rca.action_id_ibkr}: {e}.")
                else:
                     logger.warning(f"CA Record {idx+1}: Could not find split ratio pattern in description '{ca_desc_from_file}' for CA {rca.action_id_ibkr}. Cannot create CorpActionSplitForward event.")
                logger.debug(f"CA Record {idx+1} (FS): Parsed new_per_old_ratio: {new_per_old_ratio}")

                if new_per_old_ratio is not None:
                     common_ca_params_kw_base["gross_amount_foreign_currency"] = Decimal('0.0') # Splits typically don't have a gross cash amount
                     common_ca_params_kw = {k: v for k, v in common_ca_params_kw_base.items() if v is not None} # Filter out None values for kwargs
                     domain_ca_event_instance = CorpActionSplitForward(
                        asset_internal_id=affected_asset.internal_asset_id, event_date=event_date_str,
                        new_shares_per_old_share=new_per_old_ratio, **common_ca_params_kw
                    )

            elif ca_type_from_file == "TC": # Merger/Acquisition (can be cash, stock, or mixed)
                logger.debug(f"CA Record {idx+1}: Identified as potential Merger/Acquisition (TC).")
                cash_per_share_match = re.search(r"FOR\s+([A-Z]{3})\s*(\d+(?:\.\d+)?)\s*(?:PER\s*SHARE)?", ca_desc_from_file)
                is_cash_merger = False
                cash_per_share_val = None
                if cash_per_share_match:
                    try:
                        cash_curr = cash_per_share_match.group(1)
                        cash_val_str = cash_per_share_match.group(2)
                        event_curr = common_ca_params_kw_base.get("local_currency") # Already determined
                        if event_curr and cash_curr == event_curr.upper():
                            cash_per_share_val = Decimal(cash_val_str)
                            is_cash_merger = True
                        else:
                            logger.warning(f"CA Record {idx+1} (TC): Cash currency mismatch in description ('{cash_curr}') vs primary ('{event_curr}'). Cannot reliably parse cash per share.")
                    except Exception as e:
                        logger.warning(f"CA Record {idx+1} (TC): Could not parse cash per share from '{ca_desc_from_file}' for CA {rca.action_id_ibkr}: {e}")
                logger.debug(f"CA Record {idx+1} (TC): Cash merger check - is_cash_merger: {is_cash_merger}, cash_per_share_val: {cash_per_share_val}")

                if is_cash_merger and cash_per_share_val is not None:
                    if quantity_ca is None or quantity_ca == Decimal(0): # Quantity here means shares disposed
                        logger.warning(f"CA Record {idx+1} (TC-Cash): Cash Merger CA {rca.action_id_ibkr} has cash per share but missing or zero quantity ({quantity_ca}). Cannot create event.")
                    else:
                        qty_disposed_abs = quantity_ca.copy_abs() # Ensure positive
                        common_ca_params_kw_base["gross_amount_foreign_currency"] = gross_amount_ca.copy_abs() # Total cash received from CSV Proceeds
                        common_ca_params_kw = {k: v for k, v in common_ca_params_kw_base.items() if v is not None}
                        logger.debug(f"CA Record {idx+1} (TC-Cash): Creating CorpActionMergerCash. Qty disposed: {qty_disposed_abs}, Cash/Share: {cash_per_share_val}, Gross: {common_ca_params_kw_base['gross_amount_foreign_currency']}")
                        domain_ca_event_instance = CorpActionMergerCash(
                            asset_internal_id=affected_asset.internal_asset_id, event_date=event_date_str,
                            cash_per_share_foreign_currency=cash_per_share_val,
                            quantity_disposed=qty_disposed_abs,
                            **common_ca_params_kw
                        )
                else:
                    logger.debug(f"CA Record {idx+1} (TC): Not a cash merger or details not parsed. Checking for stock-for-stock.")
                    stock_ratio_match = re.search(r"WITH\s+([A-Z0-9\.\-]+)\s+(\d+(?:\.\d+)?)\s*FOR\s*(\d+(?:\.\d+)?)", ca_desc_from_file)
                    if not stock_ratio_match:
                         stock_ratio_match = re.search(r"([A-Z0-9\.\-]+)\s+(\d+(?:\.\d+)?)\s*FOR\s*(\d+(?:\.\d+)?)", ca_desc_from_file)

                    new_shares_per_old_stock = None
                    new_asset_symbol_from_desc = None
                    if stock_ratio_match:
                        try:
                            new_asset_symbol_from_desc = stock_ratio_match.group(1)
                            new_val_str, old_val_str = stock_ratio_match.group(2), stock_ratio_match.group(3)
                            new_val, old_val = Decimal(new_val_str), Decimal(old_val_str)
                            if old_val != Decimal(0): new_shares_per_old_stock = new_val / old_val
                            else: logger.warning(f"CA Record {idx+1} (TC-Stock): Old value in stock merger ratio is zero for CA {rca.action_id_ibkr}.")
                        except Exception as e:
                             logger.warning(f"CA Record {idx+1} (TC-Stock): Could not parse stock merger ratio from '{ca_desc_from_file}' for CA {rca.action_id_ibkr}: {e}")
                    logger.debug(f"CA Record {idx+1} (TC-Stock): Parsed - new_asset_symbol_from_desc: {new_asset_symbol_from_desc}, new_shares_per_old_stock: {new_shares_per_old_stock}")

                    if new_shares_per_old_stock is not None and new_asset_symbol_from_desc is not None:
                         new_asset = self.asset_resolver.get_or_create_asset(
                             raw_isin=None, raw_conid=None,
                             raw_symbol=new_asset_symbol_from_desc,
                             raw_currency=rca.currency_primary or affected_asset.currency,
                             raw_ibkr_asset_class=rca.asset_class or affected_asset.ibkr_asset_class_raw,
                             raw_description=f"New asset from merger: {new_asset_symbol_from_desc}",
                             description_source_type="corp_act_generated"
                         )
                         logger.debug(f"CA Record {idx+1} (TC-Stock): Attempted to resolve/create new asset by symbol '{new_asset_symbol_from_desc}'. Resulting asset ID: {new_asset.internal_asset_id if new_asset else 'Not Found/Created'}")
                         if new_asset:
                            common_ca_params_kw_base["gross_amount_foreign_currency"] = Decimal('0.0')
                            common_ca_params_kw = {k: v for k, v in common_ca_params_kw_base.items() if v is not None}
                            domain_ca_event_instance = CorpActionMergerStock(
                                asset_internal_id=affected_asset.internal_asset_id, event_date=event_date_str,
                                new_asset_internal_id=new_asset.internal_asset_id,
                                new_shares_received_per_old=new_shares_per_old_stock,
                                **common_ca_params_kw
                            )
                         else:
                              logger.warning(f"CA Record {idx+1} (TC-Stock): Stock Merger CA {rca.action_id_ibkr}: Could not resolve or create new asset with symbol '{new_asset_symbol_from_desc}'. Cannot create event.")
                    elif not stock_ratio_match:
                         logger.warning(f"CA Record {idx+1} (TC): Could not determine if Merger CA {rca.action_id_ibkr} is cash or stock, or parse details from description '{ca_desc_from_file}'. Will fall through to generic.")

            elif ca_type_from_file == "HI" or ca_type_from_file == "SD" or "STOCK DIVIDEND" in ca_type_from_file:
                 logger.debug(f"CA Record {idx+1}: Identified as potential Stock Dividend (HI, SD, or 'STOCK DIVIDEND').")
                 new_shares_qty = quantity_ca
                 total_fmv = gross_amount_ca
                 fmv_per_share = None
                 logger.debug(f"CA Record {idx+1} (SD): new_shares_qty: {new_shares_qty}, total_fmv (from gross_amount_ca): {total_fmv}")

                 if new_shares_qty is not None and new_shares_qty > Decimal(0):
                     if total_fmv is not None and total_fmv >= Decimal(0):
                        fmv_per_share = total_fmv / new_shares_qty if new_shares_qty != Decimal(0) else Decimal(0)
                     else:
                        logger.warning(f"CA Record {idx+1} (SD): Stock Dividend CA {rca.action_id_ibkr}: Missing or invalid total FMV ('Value'={rca.value}, Gross_amount_ca={gross_amount_ca}) for {new_shares_qty} shares. Assuming 0 FMV.")
                        fmv_per_share = Decimal('0.0')
                        total_fmv = Decimal('0.0')
                 else:
                     logger.warning(f"CA Record {idx+1} (SD): Stock Dividend CA {rca.action_id_ibkr}: Invalid or missing quantity ({new_shares_qty}). Cannot create event.")
                 logger.debug(f"CA Record {idx+1} (SD): Calculated fmv_per_share: {fmv_per_share}")

                 # Check if this is a receivable asset that should be skipped for stock dividends
                 is_receivable_asset = (
                     ".REC" in (rca.symbol or "") or 
                     "RECEIVABLE" in (rca.description or "").upper() or
                     "RECEIVABLE" in (affected_asset.description or "").upper()
                 )
                 
                 if new_shares_qty is not None and new_shares_qty > 0 and fmv_per_share is not None:
                    if is_receivable_asset:
                        logger.info(f"CA Record {idx+1} (SD): Skipping stock dividend for receivable asset {affected_asset.get_classification_key()}. Receivables are temporary and should not receive permanent stock dividends.")
                    else:
                        common_ca_params_kw_base["gross_amount_foreign_currency"] = total_fmv
                        common_ca_params_kw = {k: v for k, v in common_ca_params_kw_base.items() if v is not None}
                        logger.debug(f"CA Record {idx+1} (SD): Creating CorpActionStockDividend. New Shares: {new_shares_qty}, FMV/Share: {fmv_per_share}, Gross: {total_fmv}")
                        domain_ca_event_instance = CorpActionStockDividend(
                            asset_internal_id=affected_asset.internal_asset_id, event_date=event_date_str,
                            quantity_new_shares_received=new_shares_qty,
                            fmv_per_new_share_foreign_currency=fmv_per_share,
                            **common_ca_params_kw
                        )

            if domain_ca_event_instance:
                logger.info(f"CA Record {idx+1}: Successfully created {type(domain_ca_event_instance).__name__} (Type: {domain_ca_event_instance.event_type.name}) for asset {affected_asset.get_classification_key()} from CA ID {rca.action_id_ibkr}, Gross Amt: {common_ca_params_kw_base.get('gross_amount_foreign_currency')} {common_ca_params_kw_base.get('local_currency')}")
                domain_ca_events.append(domain_ca_event_instance)
            else:
                 logger.warning(f"CA Record {idx+1}: Corporate action type '{ca_type_from_file}' (Desc: '{ca_desc_from_file}') for asset {affected_asset.get_classification_key()} did not map to a specific domain event type or parsing failed. Creating generic CorporateActionEvent.")
                 common_ca_params_kw_base["gross_amount_foreign_currency"] = gross_amount_ca
                 common_ca_params_kw = {k: v for k, v in common_ca_params_kw_base.items() if v is not None}

                 fallback_event_type = FinancialEventType.CORP_STOCK_DIVIDEND
                 if ca_type_from_file == "RS": fallback_event_type = FinancialEventType.CORP_SPLIT_FORWARD
                 elif ca_type_from_file == "TC": fallback_event_type = FinancialEventType.CORP_MERGER_CASH

                 generic_event = CorporateActionEvent(
                     asset_internal_id=affected_asset.internal_asset_id,
                     event_date=event_date_str,
                     event_type=fallback_event_type,
                     **common_ca_params_kw
                 )
                 domain_ca_events.append(generic_event)
                 logger.info(f"CA Record {idx+1}: Created generic CorporateActionEvent for fallback. Type assigned: {fallback_event_type.name}, Gross: {gross_amount_ca}")
        return domain_ca_events
