# tests/helpers/mock_providers.py
from decimal import Decimal
from datetime import date
from typing import Optional, Dict, Set

# Assuming ExchangeRateProvider is in src.utils.exchange_rate_provider
from src.utils.exchange_rate_provider import ExchangeRateProvider


class MockECBExchangeRateProvider(ExchangeRateProvider):
    """
    A mock exchange rate provider.
    The `foreign_to_eur_init_value` parameter at initialization defines the direct relationship:
    1 unit of Foreign Currency = `foreign_to_eur_init_value` EUR.
    Example: if foreign_to_eur_init_value = Decimal("2.0"), then 1 USD = 2 EUR.
    """
    def __init__(self, foreign_to_eur_init_value: Decimal = Decimal("2.0")):
        self.one_foreign_unit_in_eur = foreign_to_eur_init_value
        if self.one_foreign_unit_in_eur.is_zero(): # type: ignore
            raise ValueError("The EUR value of one foreign currency unit cannot be zero.")
        # Rate: Foreign Currency units per 1 EUR.
        # If 1 Foreign = X EUR, then 1 EUR = (1/X) Foreign.
        self.foreign_per_eur_rate = Decimal("1.0") / self.one_foreign_unit_in_eur # type: ignore
        self.default_eur_currency_code = "EUR"

    def get_rate(self, date_of_conversion: date, currency_code: str) -> Optional[Decimal]: # Method signature matches base class
        """
        Mocked get_rate method.
        The CurrencyConverter calls this with:
        - date_of_conversion: the date of conversion.
        - currency_code: the currency code of the amount being converted TO EUR.

        This mock should return the rate as "foreign currency units per 1 EUR".
        """
        currency_to_convert_upper = currency_code.upper()

        if currency_to_convert_upper == self.default_eur_currency_code:
            # If asked for rate of EUR to EUR, it's 1. (Though CurrencyConverter handles this before calling)
            # However, if CurrencyConverter asks for rate for "EUR" (meaning it wants EUR per 1 EUR), it should be 1.
            return Decimal("1.0")

        # For any other currency, apply the mock rate
        # The request is for converting a foreign currency TO EUR.
        # The rate required by CurrencyConverter's division logic is "Foreign units per 1 EUR".
        # Example: self.one_foreign_unit_in_eur = 2.0 (1 Foreign = 2 EUR)
        # Then 1 EUR = 0.5 Foreign. The rate returned should be 0.5.
        # This is self.foreign_per_eur_rate.
        return self.foreign_per_eur_rate
        
        # This case should ideally not be hit if original_currency_from_converter is always a valid foreign currency
        # or "EUR" (which should be handled before this or by the above if).
        # print(f"MockECBExchangeRateProvider: Unexpected scenario in get_rate for date {date_of_conversion}, currency '{currency_code}'. Returning None.")
        # return None # Covered by returning self.foreign_per_eur_rate for any non-EUR

    def prefetch_rates(self, start_date: date, end_date: date, currencies: Set[str]):
        # No-op for this simple mock.
        pass
        
    def get_currency_code_mapping(self) -> Dict[str, str]:
        try:
            # CURRENCY_CODE_MAPPING_ECB name is unchanged in config.py
            from src.config import CURRENCY_CODE_MAPPING_ECB 
            return CURRENCY_CODE_MAPPING_ECB
        except ImportError:
            return {"CNH": "CNY"} 

    def get_max_fallback_days(self) -> int:
        try:
            # MAX_FALLBACK_DAYS_EXCHANGE_RATES name is unchanged in config.py
            from src.config import MAX_FALLBACK_DAYS_EXCHANGE_RATES
            return MAX_FALLBACK_DAYS_EXCHANGE_RATES
        except ImportError:
            return 7
