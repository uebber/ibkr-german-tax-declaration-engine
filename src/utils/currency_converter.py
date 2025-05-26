# src/utils/currency_converter.py
import logging
from datetime import date # Changed from datetime to date for consistency with event_date_obj
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from .exchange_rate_provider import ECBExchangeRateProvider # Relative import

logger = logging.getLogger(__name__)

class CurrencyConverter:
    def __init__(self, rate_provider: ECBExchangeRateProvider):
        self.rate_provider = rate_provider

    def convert_to_eur(self, original_amount: Decimal, original_currency: str, date_of_conversion: date) -> Optional[Decimal]:
        """
        Converts an amount from its original currency to EUR using the rate
        for the given date.
        Rate from ECB is foreign currency units per 1 EUR.
        So, EUR amount = original_amount / rate.
        Returns the EUR amount (Decimal) or None if conversion fails.
        """
        original_currency_upper = original_currency.upper()
        if not original_currency_upper:
            logger.warning(f"Cannot convert to EUR: original currency is missing for amount {original_amount} on {date_of_conversion}")
            return None

        if original_amount == Decimal("0"):
            return Decimal("0.00") # Standardize zero to two decimal places

        if original_currency_upper == "EUR":
            return original_amount # Already in EUR

        rate = self.rate_provider.get_rate(date_of_conversion, original_currency_upper)

        if rate is None:
            # rate_provider already logs warnings/errors
            logger.error(f"Failed to convert {original_amount} {original_currency_upper} to EUR: No exchange rate provided by provider for {date_of_conversion}.")
            return None
        
        if rate <= Decimal("0"): # Rate must be positive
             logger.error(f"Failed to convert {original_amount} {original_currency_upper} to EUR: Exchange rate from provider is zero or negative ({rate}) for {date_of_conversion}.")
             return None # Avoid division by zero or incorrect results

        try:
            # ECB Rate is Foreign Currency per 1 EUR.
            # EUR = Foreign Amount / Rate
            eur_amount = original_amount / rate
            # PRD suggests final outputs are often to 2 decimal places.
            # Calculations might need more, but for storing on event, 2 might be okay
            # unless it's a per-share value.
            # The enrichment function will handle specific quantization.
            return eur_amount # Return with full precision from division for now. Quantization at enrichment step.
        except Exception as e: # Catch any other unexpected errors during division
            logger.error(f"Error during currency division for {original_amount} {original_currency_upper} with rate {rate} on {date_of_conversion}: {e}")
            return None
