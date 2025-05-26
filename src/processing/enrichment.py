# src/processing/enrichment.py
import logging
from decimal import Decimal, getcontext, Context
from typing import List

from src.domain.events import (
    FinancialEvent, TradeEvent, CorpActionStockDividend, CorpActionMergerCash,
    FinancialEventType
)
from src.utils.currency_converter import CurrencyConverter
from src.utils.type_utils import parse_ibkr_date

logger = logging.getLogger(__name__)

def enrich_financial_events(
    financial_events: List[FinancialEvent],
    currency_converter: CurrencyConverter,
    internal_calculation_precision: int, # Renamed from internal_working_precision
    decimal_rounding_mode: str       # New parameter (e.g., "ROUND_HALF_UP")
) -> List[FinancialEvent]:
    """
    Enriches financial events with EUR amounts by converting foreign currency values.
    Uses a high precision context for calculations and stores results at that precision.
    Modifies the event objects in-place.
    """
    logger.info(f"Starting enrichment for {len(financial_events)} financial events using precision {internal_calculation_precision}.")

    # Create a local decimal context for enrichment calculations
    ctx = Context(prec=internal_calculation_precision, rounding=decimal_rounding_mode)

    events_skipped_date_parsing = 0
    eur_gross_conversions_success = 0
    eur_gross_conversions_failed = 0
    eur_commission_conversions_success = 0
    eur_commission_conversions_failed = 0
    eur_corp_action_detail_conversions_success = 0
    eur_corp_action_detail_conversions_failed = 0

    for event_idx, event in enumerate(financial_events):
        event_date_obj = parse_ibkr_date(event.event_date)
        if not event_date_obj:
            logger.warning(f"Event {event_idx+1}/{len(financial_events)} (ID: {event.event_id}): Could not parse event_date '{event.event_date}'. Skipping EUR conversion for this event.")
            events_skipped_date_parsing += 1
            continue

        # 1. Enrich gross_amount_eur
        if event.gross_amount_foreign_currency is not None and event.gross_amount_eur is None: # Only enrich if not already set
            if event.local_currency and event.local_currency.upper() != "EUR":
                eur_amount = currency_converter.convert_to_eur(
                    event.gross_amount_foreign_currency,
                    event.local_currency,
                    event_date_obj
                )
                if eur_amount is not None:
                    # Store with high precision
                    event.gross_amount_eur = ctx.create_decimal(eur_amount)
                    eur_gross_conversions_success += 1
                else:
                    logger.warning(f"Event {event_idx+1} (ID: {event.event_id}): Could not convert gross_amount ({event.gross_amount_foreign_currency} {event.local_currency}) to EUR.")
                    eur_gross_conversions_failed += 1
            elif event.local_currency and event.local_currency.upper() == "EUR":
                event.gross_amount_eur = ctx.create_decimal(event.gross_amount_foreign_currency)
                eur_gross_conversions_success +=1
            elif not event.local_currency and event.gross_amount_foreign_currency != Decimal(0):
                 logger.warning(f"Event {event_idx+1} (ID: {event.event_id}): gross_amount_foreign_currency ({event.gross_amount_foreign_currency}) exists but local_currency is missing. Cannot convert to EUR.")
                 eur_gross_conversions_failed +=1
            elif event.gross_amount_foreign_currency == Decimal(0):
                # If gross is zero, EUR is also zero
                event.gross_amount_eur = ctx.create_decimal(Decimal(0))
                eur_gross_conversions_success += 1


        # 2. Enrich TradeEvent specific fields
        if isinstance(event, TradeEvent):
            # 2a. Commission
            if event.commission_foreign_currency is not None and event.commission_eur is None: # Only enrich if not already set
                if event.commission_currency and event.commission_currency.upper() != "EUR":
                    eur_commission = currency_converter.convert_to_eur(
                        event.commission_foreign_currency,
                        event.commission_currency,
                        event_date_obj
                    )
                    if eur_commission is not None:
                        event.commission_eur = ctx.create_decimal(eur_commission)
                        eur_commission_conversions_success +=1
                    else:
                        logger.warning(f"Event {event_idx+1} (Trade ID: {event.event_id}): Could not convert commission ({event.commission_foreign_currency} {event.commission_currency}) to EUR.")
                        eur_commission_conversions_failed += 1
                elif event.commission_currency and event.commission_currency.upper() == "EUR":
                    event.commission_eur = ctx.create_decimal(event.commission_foreign_currency)
                    eur_commission_conversions_success += 1
                elif not event.commission_currency and event.commission_foreign_currency != Decimal(0):
                     logger.warning(f"Event {event_idx+1} (Trade ID: {event.event_id}): commission_foreign_currency ({event.commission_foreign_currency}) exists but commission_currency is missing. Cannot convert to EUR.")
                     eur_commission_conversions_failed += 1
                elif event.commission_foreign_currency == Decimal(0):
                     event.commission_eur = ctx.create_decimal(Decimal(0))
                     eur_commission_conversions_success += 1


            # 2b. Calculate gross_amount_eur for trade if not already set by general logic above
            if event.gross_amount_eur is None and event.gross_amount_foreign_currency is None and \
               event.quantity is not None and event.price_foreign_currency is not None and event.local_currency is not None:

                calculated_gross_foreign = ctx.multiply(event.quantity.copy_abs(), event.price_foreign_currency)

                if event.local_currency.upper() != "EUR":
                    calculated_gross_eur = currency_converter.convert_to_eur(
                        calculated_gross_foreign,
                        event.local_currency,
                        event_date_obj
                    )
                    if calculated_gross_eur is not None:
                        event.gross_amount_eur = ctx.create_decimal(calculated_gross_eur)
                    else:
                        logger.warning(f"Event {event_idx+1} (Trade ID: {event.event_id}): Could not convert calculated gross_amount ({calculated_gross_foreign} {event.local_currency}) to EUR.")
                elif event.local_currency.upper() == "EUR":
                    event.gross_amount_eur = ctx.create_decimal(calculated_gross_foreign)

            # 2c. Net proceeds or cost basis in EUR (HIGH PRECISION)
            if event.net_proceeds_or_cost_basis_eur is None: # Only calculate if not already set
                if event.gross_amount_eur is not None and event.commission_eur is not None:
                    if event.event_type in [FinancialEventType.TRADE_BUY_LONG, FinancialEventType.TRADE_BUY_SHORT_COVER]:
                        # Cost basis = gross amount + commission
                        event.net_proceeds_or_cost_basis_eur = ctx.add(event.gross_amount_eur, event.commission_eur.copy_abs()) # Ensure commission added is positive
                    elif event.event_type in [FinancialEventType.TRADE_SELL_LONG, FinancialEventType.TRADE_SELL_SHORT_OPEN]:
                        # Proceeds = gross amount - commission
                        event.net_proceeds_or_cost_basis_eur = ctx.subtract(event.gross_amount_eur, event.commission_eur.copy_abs()) # Ensure commission subtracted is positive
                elif event.gross_amount_eur is not None and event.commission_eur is None and event.commission_foreign_currency == Decimal('0.0'):
                    # If commission is zero, net = gross
                    event.net_proceeds_or_cost_basis_eur = ctx.create_decimal(event.gross_amount_eur) # ensure it's under context
                elif event.gross_amount_eur is None:
                     logger.warning(f"Event {event_idx+1} (Trade ID: {event.event_id}): Cannot calculate net_proceeds_or_cost_basis_eur because gross_amount_eur is None.")
                elif event.commission_eur is None :
                     logger.warning(f"Event {event_idx+1} (Trade ID: {event.event_id}): Cannot calculate net_proceeds_or_cost_basis_eur because commission_eur is None (and original commission was not 0.0).")

        # 3. Enrich CorpActionMergerCash specific fields
        elif isinstance(event, CorpActionMergerCash):
            if event.cash_per_share_foreign_currency is not None and event.cash_per_share_eur is None:
                if event_date_obj and event.local_currency:
                    if event.local_currency.upper() != "EUR":
                        eur_val = currency_converter.convert_to_eur(
                            event.cash_per_share_foreign_currency,
                            event.local_currency,
                            event_date_obj
                        )
                        if eur_val is not None:
                            event.cash_per_share_eur = ctx.create_decimal(eur_val)
                            eur_corp_action_detail_conversions_success += 1
                        else:
                            logger.warning(f"Event {event_idx+1} (CorpActionMergerCash ID: {event.event_id}): Could not convert cash_per_share ({event.cash_per_share_foreign_currency} {event.local_currency}) to EUR.")
                            eur_corp_action_detail_conversions_failed += 1
                    else: # Currency is EUR
                        event.cash_per_share_eur = ctx.create_decimal(event.cash_per_share_foreign_currency)
                        eur_corp_action_detail_conversions_success += 1
                elif not event_date_obj:
                     logger.warning(f"Event {event_idx+1} (CorpActionMergerCash ID: {event.event_id}): Missing valid date. Cannot convert cash_per_share to EUR.")
                     eur_corp_action_detail_conversions_failed += 1
                elif not event.local_currency:
                     logger.warning(f"Event {event_idx+1} (CorpActionMergerCash ID: {event.event_id}): Missing currency. Cannot convert cash_per_share to EUR.")
                     eur_corp_action_detail_conversions_failed += 1

        # 4. Enrich CorpActionStockDividend specific fields
        elif isinstance(event, CorpActionStockDividend):
             if event.fmv_per_new_share_foreign_currency is not None and event.fmv_per_new_share_eur is None:
                if event_date_obj and event.local_currency:
                    if event.local_currency.upper() != "EUR":
                        eur_val = currency_converter.convert_to_eur(
                            event.fmv_per_new_share_foreign_currency,
                            event.local_currency,
                            event_date_obj
                        )
                        if eur_val is not None:
                            event.fmv_per_new_share_eur = ctx.create_decimal(eur_val)
                            eur_corp_action_detail_conversions_success += 1
                        else:
                            logger.warning(f"Event {event_idx+1} (CorpActionStockDividend ID: {event.event_id}): Could not convert fmv_per_new_share ({event.fmv_per_new_share_foreign_currency} {event.local_currency}) to EUR.")
                            eur_corp_action_detail_conversions_failed += 1
                    else: # Currency is EUR
                        event.fmv_per_new_share_eur = ctx.create_decimal(event.fmv_per_new_share_foreign_currency)
                        eur_corp_action_detail_conversions_success += 1
                elif not event_date_obj:
                     logger.warning(f"Event {event_idx+1} (CorpActionStockDividend ID: {event.event_id}): Missing valid date. Cannot convert fmv_per_new_share to EUR.")
                     eur_corp_action_detail_conversions_failed += 1
                elif not event.local_currency:
                     logger.warning(f"Event {event_idx+1} (CorpActionStockDividend ID: {event.event_id}): Missing currency. Cannot convert fmv_per_new_share to EUR.")
                     eur_corp_action_detail_conversions_failed += 1

    logger.info(f"Enrichment summary: Events with date parsing errors: {events_skipped_date_parsing}.")
    logger.info(f"Gross amount to EUR: {eur_gross_conversions_success} succeeded, {eur_gross_conversions_failed} failed/skipped.")
    logger.info(f"Commission to EUR: {eur_commission_conversions_success} succeeded, {eur_commission_conversions_failed} failed/skipped.")
    logger.info(f"CA Detail Conversion to EUR: {eur_corp_action_detail_conversions_success} succeeded, {eur_corp_action_detail_conversions_failed} failed/skipped.")
    logger.info("Data enrichment phase completed.")
    return financial_events
