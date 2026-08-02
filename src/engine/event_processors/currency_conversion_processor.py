# src/engine/event_processors/currency_conversion_processor.py
"""
CurrencyConversionProcessor - Processes CurrencyConversionEvents as FIFO trades on currency ledgers.

All FX gains/losses are taxable under Section 20 EStG (interest-bearing accounts) and go to
kap_other_income_positive / kap_other_losses_abs (Anlage KAP Zeile 19).

Per BMF circular May 2022 (para. 131): IBKR FX reserves are interest-bearing, meaning:
- Currency gains fall under Section 20 EStG (capital income), NOT Section 23 EStG (private sales)
- No 1-year holding period applies - gains are always taxable
- Report on Anlage KAP Zeile 19
"""
import logging
from decimal import Decimal, Context
from typing import List, Dict, Any, Optional, Tuple
import uuid

from src.utils.account_utils import account_key, DEFAULT_ACCOUNT
from src.domain.events import CurrencyConversionEvent
from src.domain.results import RealizedGainLoss
from src.domain.enums import AssetCategory, TaxReportingCategory, RealizationType
from src.engine.fifo_manager import FifoLedger, FifoLot, ShortFifoLot
from src.identification.asset_resolver import AssetResolver
from src.utils.currency_converter import CurrencyConverter
import src.config as global_config

logger = logging.getLogger(__name__)


class CurrencyConversionProcessor:
    """
    Processes CurrencyConversionEvents as FIFO trades on currency ledgers.

    Example: EUR.USD trade converting 1000 USD -> 920 EUR
    - from_currency=USD, from_amount=1000
    - to_currency=EUR, to_amount=920

    Supports both long and short currency positions:
    - LONG positions: You own the currency, selling realizes gain/loss
    - SHORT positions: You borrowed/owe the currency, buying back covers the short

    Processing Logic:
    - Selling non-EUR (from_currency != EUR):
      - If long lots available: Consume via FIFO, realize gain/loss
      - If insufficient long lots: Open short position for remainder
    - Buying non-EUR (to_currency != EUR):
      - If short lots exist: Cover short via FIFO, realize gain/loss
      - Remaining quantity: Create new long lot
    """

    def __init__(self, currency_converter: CurrencyConverter,
                 internal_calculation_precision: int,
                 decimal_rounding_mode: str):
        self.currency_converter = currency_converter
        self.ctx = Context(prec=internal_calculation_precision, rounding=decimal_rounding_mode)

    def process(self, event: CurrencyConversionEvent,
                fifo_ledgers: Dict[Tuple[str, uuid.UUID], FifoLedger],
                asset_resolver: AssetResolver) -> List[RealizedGainLoss]:
        """
        Process a CurrencyConversionEvent, updating currency FIFO ledgers and returning any realized FX gains/losses.

        Phase 5b: Cross-currency FX trades (e.g., USD→GBP where neither is EUR)
        are fully supported. Both sides are processed independently:
        - Selling non-EUR currency: Consume from source currency ledger (realize FX gain/loss)
        - Buying non-EUR currency: Add to target currency ledger (or cover short)
        EUR bridge valuation is used for both sides via _get_eur_value().
        """
        results: List[RealizedGainLoss] = []

        # Phase 5b: Cross-currency conversions (e.g., USD→GBP).
        # Each side is valued independently via ECB reference rate to EUR.
        # The EUR values may not sum to zero — this is correct per German tax law.
        # ECB rates are independent reference rates; cross-rate consistency is not required.
        # Each currency position's cost basis / proceeds must use its own ECB rate.
        from_is_non_eur = event.from_currency.upper() != "EUR"
        to_is_non_eur = event.to_currency.upper() != "EUR"
        if from_is_non_eur and to_is_non_eur:
            logger.info(
                f"FX {event.event_id}: Cross-currency conversion {event.from_currency}→{event.to_currency} "
                f"(neither is EUR). Processing both sides with EUR bridge valuation."
            )

        # Selling non-EUR currency
        if event.from_currency.upper() != "EUR":
            from_asset = asset_resolver.get_cash_balance_asset(event.from_currency)
            if from_asset:
                ledger = fifo_ledgers.get((DEFAULT_ACCOUNT, from_asset.internal_asset_id))
                if not ledger:
                    logger.warning(f"No ledger for currency {event.from_currency}, skipping FX event {event.event_id}")
                else:
                    sell_results = self._process_currency_sale(
                        event, ledger, from_asset.internal_asset_id
                    )
                    results.extend(sell_results)
            else:
                logger.warning(f"No CashBalance asset found for {event.from_currency}, skipping FX event {event.event_id}")

        # Buying non-EUR currency
        if event.to_currency.upper() != "EUR":
            to_asset = asset_resolver.get_cash_balance_asset(event.to_currency)
            if to_asset:
                ledger = fifo_ledgers.get((DEFAULT_ACCOUNT, to_asset.internal_asset_id))
                if not ledger:
                    logger.warning(f"No ledger for currency {event.to_currency}, skipping FX event {event.event_id}")
                else:
                    buy_results = self._process_currency_purchase(
                        event, ledger, to_asset.internal_asset_id
                    )
                    results.extend(buy_results)
            else:
                logger.warning(f"No CashBalance asset found for {event.to_currency}, skipping FX event {event.event_id}")

        return results

    def _get_eur_value(self, amount: Decimal, currency: str, event_date: str) -> Optional[Decimal]:
        """Convert amount to EUR. Returns amount as-is if already EUR. Returns None on failure."""
        if currency.upper() == "EUR":
            return amount
        from src.utils.type_utils import parse_ibkr_date
        date_obj = parse_ibkr_date(event_date)
        if date_obj is None:
            logger.warning(f"Failed to parse date '{event_date}' for EUR conversion of {amount} {currency}")
            return None
        converted = self.currency_converter.convert_to_eur(amount, currency, date_obj)
        if converted is None:
            logger.warning(f"Failed to convert {amount} {currency} to EUR on {event_date} - missing exchange rate")
            return None
        return converted

    def _process_currency_sale(self, event: CurrencyConversionEvent,
                               ledger: FifoLedger,
                               asset_internal_id: uuid.UUID) -> List[RealizedGainLoss]:
        """
        Process selling non-EUR currency.

        1. First consume available long lots (realize gain/loss)
        2. If selling more than available, open short position for remainder
        """
        results: List[RealizedGainLoss] = []
        quantity_to_sell = event.from_amount
        proceeds_eur = self._get_eur_value(event.to_amount, event.to_currency, event.event_date)

        if quantity_to_sell <= Decimal("0"):
            return results

        if proceeds_eur is None:
            logger.warning(
                f"FX {event.event_id}: Skipping currency sale of {quantity_to_sell} {event.from_currency} "
                f"- could not determine EUR proceeds"
            )
            return results

        proceeds_per_unit = self.ctx.divide(proceeds_eur, quantity_to_sell)

        # Check available long quantity
        available_long_qty = sum(lot.quantity for lot in ledger.lots)

        if available_long_qty > Decimal("0"):
            # Consume long lots first
            qty_to_consume_from_longs = min(quantity_to_sell, available_long_qty)
            long_results = self._realize_long_lots(
                ledger, event, asset_internal_id, qty_to_consume_from_longs, proceeds_per_unit
            )
            results.extend(long_results)
            quantity_to_sell = self.ctx.subtract(quantity_to_sell, qty_to_consume_from_longs)

        # If still quantity remaining, open short position
        if quantity_to_sell > Decimal("1e-10"):
            logger.info(f"Opening SHORT currency position: {quantity_to_sell} {event.from_currency} "
                       f"(proceeds: {self.ctx.multiply(quantity_to_sell, proceeds_per_unit)} EUR)")
            self._open_short_position(ledger, event, quantity_to_sell, proceeds_per_unit)

        return results

    def _process_currency_purchase(self, event: CurrencyConversionEvent,
                                   ledger: FifoLedger,
                                   asset_internal_id: uuid.UUID) -> List[RealizedGainLoss]:
        """
        Process buying non-EUR currency.

        1. First cover any existing short lots (realize gain/loss)
        2. Remaining quantity becomes new long lot
        """
        results: List[RealizedGainLoss] = []
        quantity_to_buy = event.to_amount
        cost_basis_eur = self._get_eur_value(event.from_amount, event.from_currency, event.event_date)

        if quantity_to_buy <= Decimal("0"):
            return results

        if cost_basis_eur is None:
            logger.warning(
                f"FX {event.event_id}: Skipping currency purchase of {quantity_to_buy} {event.to_currency} "
                f"- could not determine EUR cost basis"
            )
            return results

        cost_per_unit = self.ctx.divide(cost_basis_eur, quantity_to_buy)

        # Check available short quantity
        available_short_qty = sum(lot.quantity_shorted for lot in ledger.short_lots)

        if available_short_qty > Decimal("0"):
            # Cover short lots first
            qty_to_cover = min(quantity_to_buy, available_short_qty)
            short_results = self._cover_short_lots(
                ledger, event, asset_internal_id, qty_to_cover, cost_per_unit
            )
            results.extend(short_results)
            quantity_to_buy = self.ctx.subtract(quantity_to_buy, qty_to_cover)

        # If still quantity remaining, create long lot
        if quantity_to_buy > Decimal("1e-10"):
            self._create_long_lot(ledger, event, quantity_to_buy, cost_per_unit)

        return results

    def _realize_long_lots(self, ledger: FifoLedger, event: CurrencyConversionEvent,
                           asset_internal_id: uuid.UUID,
                           quantity: Decimal, proceeds_per_unit: Decimal) -> List[RealizedGainLoss]:
        """Consume long lots FIFO-style, generating RealizedGainLoss records."""
        results: List[RealizedGainLoss] = []
        remaining_qty = quantity
        lots_to_remove: List[int] = []

        for i, lot in enumerate(ledger.lots):
            if remaining_qty <= Decimal("0"):
                break

            qty_from_lot = min(lot.quantity, remaining_qty)

            # Calculate gain/loss for this portion
            cost_basis_portion = self.ctx.multiply(qty_from_lot, lot.unit_cost_basis_eur)
            proceeds_portion = self.ctx.multiply(qty_from_lot, proceeds_per_unit)
            gain_loss = self.ctx.subtract(proceeds_portion, cost_basis_portion)

            # Determine tax category based on gain/loss
            tax_cat = (TaxReportingCategory.ANLAGE_KAP_SONSTIGE_KAPITALERTRAEGE
                      if gain_loss >= Decimal("0")
                      else TaxReportingCategory.ANLAGE_KAP_SONSTIGE_VERLUSTE)

            rgl = RealizedGainLoss(
                originating_event_id=event.event_id,
                asset_internal_id=asset_internal_id,
                asset_category_at_realization=AssetCategory.CASH_BALANCE,
                acquisition_date=lot.acquisition_date,
                realization_date=event.event_date,
                realization_type=RealizationType.FX_CONVERSION_SALE,
                quantity_realized=qty_from_lot,
                unit_cost_basis_eur=lot.unit_cost_basis_eur,
                unit_realization_value_eur=proceeds_per_unit,
                total_cost_basis_eur=cost_basis_portion,
                total_realization_value_eur=proceeds_portion,
                gross_gain_loss_eur=gain_loss,
                tax_reporting_category=tax_cat
            )
            results.append(rgl)

            # Update or mark lot for removal
            if lot.quantity <= remaining_qty:
                lots_to_remove.append(i)
            else:
                lot.quantity = self.ctx.subtract(lot.quantity, qty_from_lot)
                lot.total_cost_basis_eur = self.ctx.multiply(lot.quantity, lot.unit_cost_basis_eur)

            remaining_qty = self.ctx.subtract(remaining_qty, qty_from_lot)

        # Remove fully consumed lots
        for i in reversed(lots_to_remove):
            del ledger.lots[i]

        return results

    def _cover_short_lots(self, ledger: FifoLedger, event: CurrencyConversionEvent,
                          asset_internal_id: uuid.UUID,
                          quantity: Decimal, cost_per_unit: Decimal) -> List[RealizedGainLoss]:
        """Cover short lots FIFO-style, generating RealizedGainLoss records."""
        results: List[RealizedGainLoss] = []
        remaining_qty = quantity
        lots_to_remove: List[int] = []

        for i, short_lot in enumerate(ledger.short_lots):
            if remaining_qty <= Decimal("0"):
                break

            qty_from_lot = min(short_lot.quantity_shorted, remaining_qty)

            # For shorts: Gain = Original Proceeds - Cover Cost
            original_proceeds_portion = self.ctx.multiply(qty_from_lot, short_lot.unit_sale_proceeds_eur)
            cover_cost_portion = self.ctx.multiply(qty_from_lot, cost_per_unit)
            gain_loss = self.ctx.subtract(original_proceeds_portion, cover_cost_portion)

            # Determine tax category based on gain/loss
            tax_cat = (TaxReportingCategory.ANLAGE_KAP_SONSTIGE_KAPITALERTRAEGE
                      if gain_loss >= Decimal("0")
                      else TaxReportingCategory.ANLAGE_KAP_SONSTIGE_VERLUSTE)

            rgl = RealizedGainLoss(
                originating_event_id=event.event_id,
                asset_internal_id=asset_internal_id,
                asset_category_at_realization=AssetCategory.CASH_BALANCE,
                acquisition_date=short_lot.opening_date,  # When short was opened
                realization_date=event.event_date,        # When covered
                realization_type=RealizationType.FX_CONVERSION_SHORT_COVER,
                quantity_realized=qty_from_lot,
                unit_cost_basis_eur=cost_per_unit,        # Cover cost
                unit_realization_value_eur=short_lot.unit_sale_proceeds_eur,  # Original sale
                total_cost_basis_eur=cover_cost_portion,
                total_realization_value_eur=original_proceeds_portion,
                gross_gain_loss_eur=gain_loss,
                tax_reporting_category=tax_cat
            )
            results.append(rgl)

            # Update or mark lot for removal
            if short_lot.quantity_shorted <= remaining_qty:
                lots_to_remove.append(i)
            else:
                short_lot.quantity_shorted = self.ctx.subtract(short_lot.quantity_shorted, qty_from_lot)
                short_lot.total_sale_proceeds_eur = self.ctx.multiply(
                    short_lot.quantity_shorted, short_lot.unit_sale_proceeds_eur
                )

            remaining_qty = self.ctx.subtract(remaining_qty, qty_from_lot)

        # Remove fully covered short lots
        for i in reversed(lots_to_remove):
            del ledger.short_lots[i]

        return results

    def _open_short_position(self, ledger: FifoLedger, event: CurrencyConversionEvent,
                             quantity: Decimal, proceeds_per_unit: Decimal):
        """Create a new ShortFifoLot for the short currency position."""
        total_proceeds = self.ctx.multiply(quantity, proceeds_per_unit)
        short_lot = ShortFifoLot(
            opening_date=event.event_date,
            quantity_shorted=quantity,
            unit_sale_proceeds_eur=proceeds_per_unit,
            total_sale_proceeds_eur=total_proceeds,
            source_transaction_id=event.ibkr_transaction_id or f"FX_{event.event_id}"
        )
        ledger.short_lots.append(short_lot)
        ledger.short_lots.sort(key=lambda l: l.opening_date)

    def _create_long_lot(self, ledger: FifoLedger, event: CurrencyConversionEvent,
                         quantity: Decimal, cost_per_unit: Decimal):
        """Create a new FifoLot for the long currency position."""
        total_cost = self.ctx.multiply(quantity, cost_per_unit)
        lot = FifoLot(
            acquisition_date=event.event_date,
            quantity=quantity,
            unit_cost_basis_eur=cost_per_unit,
            total_cost_basis_eur=total_cost,
            source_transaction_id=event.ibkr_transaction_id or f"FX_{event.event_id}"
        )
        ledger.lots.append(lot)
        ledger.lots.sort(key=lambda l: l.acquisition_date)

    # =========================================================================
    # Phase 5a: Helper methods for implicit currency consumption from security trades
    # =========================================================================

    def realize_long_lots_for_security_trade(
        self,
        ledger: FifoLedger,
        asset_internal_id: uuid.UUID,
        event_date: str,
        event_id: uuid.UUID,
        ibkr_transaction_id: Optional[str],
        quantity: Decimal,
        proceeds_per_unit: Decimal
    ) -> List[RealizedGainLoss]:
        """
        Consume long currency lots due to security purchase.
        Similar to _realize_long_lots but with different realization type.

        Args:
            ledger: The currency FIFO ledger
            asset_internal_id: The currency asset's internal ID
            event_date: Date of the security trade
            event_id: ID of the security trade event (for linking)
            ibkr_transaction_id: IBKR transaction ID of the security trade
            quantity: Amount of currency to consume
            proceeds_per_unit: EUR value per unit of foreign currency at trade time

        Returns:
            List of RealizedGainLoss records for the FX gains/losses
        """
        results: List[RealizedGainLoss] = []
        remaining_qty = quantity
        lots_to_remove: List[int] = []

        for i, lot in enumerate(ledger.lots):
            if remaining_qty <= Decimal("0"):
                break

            qty_from_lot = min(lot.quantity, remaining_qty)

            cost_basis_portion = self.ctx.multiply(qty_from_lot, lot.unit_cost_basis_eur)
            proceeds_portion = self.ctx.multiply(qty_from_lot, proceeds_per_unit)
            gain_loss = self.ctx.subtract(proceeds_portion, cost_basis_portion)

            # Determine tax category based on gain/loss
            tax_cat = (TaxReportingCategory.ANLAGE_KAP_SONSTIGE_KAPITALERTRAEGE
                      if gain_loss >= Decimal("0")
                      else TaxReportingCategory.ANLAGE_KAP_SONSTIGE_VERLUSTE)

            rgl = RealizedGainLoss(
                originating_event_id=event_id,
                asset_internal_id=asset_internal_id,
                asset_category_at_realization=AssetCategory.CASH_BALANCE,
                acquisition_date=lot.acquisition_date,
                realization_date=event_date,
                realization_type=RealizationType.FX_IMPLICIT_SECURITY_PURCHASE,
                quantity_realized=qty_from_lot,
                unit_cost_basis_eur=lot.unit_cost_basis_eur,
                unit_realization_value_eur=proceeds_per_unit,
                total_cost_basis_eur=cost_basis_portion,
                total_realization_value_eur=proceeds_portion,
                gross_gain_loss_eur=gain_loss,
                tax_reporting_category=tax_cat
            )
            results.append(rgl)

            if lot.quantity <= remaining_qty:
                lots_to_remove.append(i)
            else:
                lot.quantity = self.ctx.subtract(lot.quantity, qty_from_lot)
                lot.total_cost_basis_eur = self.ctx.multiply(lot.quantity, lot.unit_cost_basis_eur)

            remaining_qty = self.ctx.subtract(remaining_qty, qty_from_lot)

        # Remove fully consumed lots
        for i in reversed(lots_to_remove):
            del ledger.lots[i]

        return results

    def cover_short_lots_for_security_trade(
        self,
        ledger: FifoLedger,
        asset_internal_id: uuid.UUID,
        event_date: str,
        event_id: uuid.UUID,
        ibkr_transaction_id: Optional[str],
        quantity: Decimal,
        cost_per_unit: Decimal
    ) -> List[RealizedGainLoss]:
        """
        Cover short currency lots when receiving currency from security sale.

        Args:
            ledger: The currency FIFO ledger
            asset_internal_id: The currency asset's internal ID
            event_date: Date of the security trade
            event_id: ID of the security trade event (for linking)
            ibkr_transaction_id: IBKR transaction ID of the security trade
            quantity: Amount of currency received
            cost_per_unit: EUR value per unit of foreign currency at trade time

        Returns:
            List of RealizedGainLoss records for the FX gains/losses from covering shorts
        """
        results: List[RealizedGainLoss] = []
        remaining_qty = quantity
        lots_to_remove: List[int] = []

        for i, short_lot in enumerate(ledger.short_lots):
            if remaining_qty <= Decimal("0"):
                break

            qty_from_lot = min(short_lot.quantity_shorted, remaining_qty)

            # For shorts: Gain = Original Proceeds - Cover Cost
            original_proceeds_portion = self.ctx.multiply(qty_from_lot, short_lot.unit_sale_proceeds_eur)
            cover_cost_portion = self.ctx.multiply(qty_from_lot, cost_per_unit)
            gain_loss = self.ctx.subtract(original_proceeds_portion, cover_cost_portion)

            tax_cat = (TaxReportingCategory.ANLAGE_KAP_SONSTIGE_KAPITALERTRAEGE
                      if gain_loss >= Decimal("0")
                      else TaxReportingCategory.ANLAGE_KAP_SONSTIGE_VERLUSTE)

            rgl = RealizedGainLoss(
                originating_event_id=event_id,
                asset_internal_id=asset_internal_id,
                asset_category_at_realization=AssetCategory.CASH_BALANCE,
                acquisition_date=short_lot.opening_date,
                realization_date=event_date,
                realization_type=RealizationType.FX_IMPLICIT_SECURITY_SALE,
                quantity_realized=qty_from_lot,
                unit_cost_basis_eur=cost_per_unit,
                unit_realization_value_eur=short_lot.unit_sale_proceeds_eur,
                total_cost_basis_eur=cover_cost_portion,
                total_realization_value_eur=original_proceeds_portion,
                gross_gain_loss_eur=gain_loss,
                tax_reporting_category=tax_cat
            )
            results.append(rgl)

            if short_lot.quantity_shorted <= remaining_qty:
                lots_to_remove.append(i)
            else:
                short_lot.quantity_shorted = self.ctx.subtract(short_lot.quantity_shorted, qty_from_lot)
                short_lot.total_sale_proceeds_eur = self.ctx.multiply(
                    short_lot.quantity_shorted, short_lot.unit_sale_proceeds_eur
                )

            remaining_qty = self.ctx.subtract(remaining_qty, qty_from_lot)

        # Remove fully covered short lots
        for i in reversed(lots_to_remove):
            del ledger.short_lots[i]

        return results

    def create_long_lot_for_security_trade(
        self,
        ledger: FifoLedger,
        event_date: str,
        ibkr_transaction_id: Optional[str],
        quantity: Decimal,
        cost_per_unit: Decimal
    ) -> None:
        """Create a new currency lot from security sale proceeds."""
        total_cost = self.ctx.multiply(quantity, cost_per_unit)
        lot = FifoLot(
            acquisition_date=event_date,
            quantity=quantity,
            unit_cost_basis_eur=cost_per_unit,
            total_cost_basis_eur=total_cost,
            source_transaction_id=f"SEC_SALE_{ibkr_transaction_id or 'UNKNOWN'}"
        )
        ledger.lots.append(lot)
        ledger.lots.sort(key=lambda l: l.acquisition_date)

    def open_short_position_for_security_trade(
        self,
        ledger: FifoLedger,
        event_date: str,
        ibkr_transaction_id: Optional[str],
        quantity: Decimal,
        proceeds_per_unit: Decimal
    ) -> None:
        """Open short currency position when purchase exceeds available balance."""
        total_proceeds = self.ctx.multiply(quantity, proceeds_per_unit)
        short_lot = ShortFifoLot(
            opening_date=event_date,
            quantity_shorted=quantity,
            unit_sale_proceeds_eur=proceeds_per_unit,
            total_sale_proceeds_eur=total_proceeds,
            source_transaction_id=f"SEC_BUY_{ibkr_transaction_id or 'UNKNOWN'}"
        )
        ledger.short_lots.append(short_lot)
        ledger.short_lots.sort(key=lambda l: l.opening_date)

    # =========================================================================
    # Phase 5c: Helper methods for implicit currency from cash flows
    # (dividends, interest, fees, withholding tax)
    # =========================================================================

    def realize_long_lots_for_cashflow_expense(
        self,
        ledger: FifoLedger,
        asset_internal_id: uuid.UUID,
        event_date: str,
        event_id: uuid.UUID,
        ibkr_transaction_id: Optional[str],
        quantity: Decimal,
        proceeds_per_unit: Decimal
    ) -> List[RealizedGainLoss]:
        """
        Consume long currency lots due to expense cash flow (fees, WHT, Stückzinsen).
        Realizes FX gain/loss on the consumed currency.
        """
        results: List[RealizedGainLoss] = []
        remaining_qty = quantity
        lots_to_remove: List[int] = []

        for i, lot in enumerate(ledger.lots):
            if remaining_qty <= Decimal("0"):
                break

            qty_from_lot = min(lot.quantity, remaining_qty)

            cost_basis_portion = self.ctx.multiply(qty_from_lot, lot.unit_cost_basis_eur)
            proceeds_portion = self.ctx.multiply(qty_from_lot, proceeds_per_unit)
            gain_loss = self.ctx.subtract(proceeds_portion, cost_basis_portion)

            tax_cat = (TaxReportingCategory.ANLAGE_KAP_SONSTIGE_KAPITALERTRAEGE
                      if gain_loss >= Decimal("0")
                      else TaxReportingCategory.ANLAGE_KAP_SONSTIGE_VERLUSTE)

            rgl = RealizedGainLoss(
                originating_event_id=event_id,
                asset_internal_id=asset_internal_id,
                asset_category_at_realization=AssetCategory.CASH_BALANCE,
                acquisition_date=lot.acquisition_date,
                realization_date=event_date,
                realization_type=RealizationType.FX_IMPLICIT_CASHFLOW_EXPENSE,
                quantity_realized=qty_from_lot,
                unit_cost_basis_eur=lot.unit_cost_basis_eur,
                unit_realization_value_eur=proceeds_per_unit,
                total_cost_basis_eur=cost_basis_portion,
                total_realization_value_eur=proceeds_portion,
                gross_gain_loss_eur=gain_loss,
                tax_reporting_category=tax_cat
            )
            results.append(rgl)

            if lot.quantity <= remaining_qty:
                lots_to_remove.append(i)
            else:
                lot.quantity = self.ctx.subtract(lot.quantity, qty_from_lot)
                lot.total_cost_basis_eur = self.ctx.multiply(lot.quantity, lot.unit_cost_basis_eur)

            remaining_qty = self.ctx.subtract(remaining_qty, qty_from_lot)

        for i in reversed(lots_to_remove):
            del ledger.lots[i]

        return results

    def cover_short_lots_for_cashflow_income(
        self,
        ledger: FifoLedger,
        asset_internal_id: uuid.UUID,
        event_date: str,
        event_id: uuid.UUID,
        ibkr_transaction_id: Optional[str],
        quantity: Decimal,
        cost_per_unit: Decimal
    ) -> List[RealizedGainLoss]:
        """
        Cover short currency lots when receiving currency from income cash flows
        (dividends, interest).
        """
        results: List[RealizedGainLoss] = []
        remaining_qty = quantity
        lots_to_remove: List[int] = []

        for i, short_lot in enumerate(ledger.short_lots):
            if remaining_qty <= Decimal("0"):
                break

            qty_from_lot = min(short_lot.quantity_shorted, remaining_qty)

            original_proceeds_portion = self.ctx.multiply(qty_from_lot, short_lot.unit_sale_proceeds_eur)
            cover_cost_portion = self.ctx.multiply(qty_from_lot, cost_per_unit)
            gain_loss = self.ctx.subtract(original_proceeds_portion, cover_cost_portion)

            tax_cat = (TaxReportingCategory.ANLAGE_KAP_SONSTIGE_KAPITALERTRAEGE
                      if gain_loss >= Decimal("0")
                      else TaxReportingCategory.ANLAGE_KAP_SONSTIGE_VERLUSTE)

            rgl = RealizedGainLoss(
                originating_event_id=event_id,
                asset_internal_id=asset_internal_id,
                asset_category_at_realization=AssetCategory.CASH_BALANCE,
                acquisition_date=short_lot.opening_date,
                realization_date=event_date,
                realization_type=RealizationType.FX_IMPLICIT_CASHFLOW_INCOME,
                quantity_realized=qty_from_lot,
                unit_cost_basis_eur=cost_per_unit,
                unit_realization_value_eur=short_lot.unit_sale_proceeds_eur,
                total_cost_basis_eur=cover_cost_portion,
                total_realization_value_eur=original_proceeds_portion,
                gross_gain_loss_eur=gain_loss,
                tax_reporting_category=tax_cat
            )
            results.append(rgl)

            if short_lot.quantity_shorted <= remaining_qty:
                lots_to_remove.append(i)
            else:
                short_lot.quantity_shorted = self.ctx.subtract(short_lot.quantity_shorted, qty_from_lot)
                short_lot.total_sale_proceeds_eur = self.ctx.multiply(
                    short_lot.quantity_shorted, short_lot.unit_sale_proceeds_eur
                )

            remaining_qty = self.ctx.subtract(remaining_qty, qty_from_lot)

        for i in reversed(lots_to_remove):
            del ledger.short_lots[i]

        return results

    def create_long_lot_for_cashflow_income(
        self,
        ledger: FifoLedger,
        event_date: str,
        ibkr_transaction_id: Optional[str],
        quantity: Decimal,
        cost_per_unit: Decimal
    ) -> None:
        """Create a new currency lot from income cash flow (dividend, interest)."""
        total_cost = self.ctx.multiply(quantity, cost_per_unit)
        lot = FifoLot(
            acquisition_date=event_date,
            quantity=quantity,
            unit_cost_basis_eur=cost_per_unit,
            total_cost_basis_eur=total_cost,
            source_transaction_id=f"CASHFLOW_{ibkr_transaction_id or 'UNKNOWN'}"
        )
        ledger.lots.append(lot)
        ledger.lots.sort(key=lambda l: l.acquisition_date)

    def open_short_position_for_cashflow_expense(
        self,
        ledger: FifoLedger,
        event_date: str,
        ibkr_transaction_id: Optional[str],
        quantity: Decimal,
        proceeds_per_unit: Decimal
    ) -> None:
        """Open short currency position when expense exceeds available balance."""
        total_proceeds = self.ctx.multiply(quantity, proceeds_per_unit)
        short_lot = ShortFifoLot(
            opening_date=event_date,
            quantity_shorted=quantity,
            unit_sale_proceeds_eur=proceeds_per_unit,
            total_sale_proceeds_eur=total_proceeds,
            source_transaction_id=f"CASHFLOW_EXP_{ibkr_transaction_id or 'UNKNOWN'}"
        )
        ledger.short_lots.append(short_lot)
        ledger.short_lots.sort(key=lambda l: l.opening_date)
