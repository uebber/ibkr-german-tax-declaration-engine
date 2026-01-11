# tests/helpers/mock_providers.py
from decimal import Decimal
from datetime import date, timedelta
from typing import Optional, Dict, Set, List, Tuple

# Assuming ExchangeRateProvider is in src.utils.exchange_rate_provider
from src.utils.exchange_rate_provider import ExchangeRateProvider


class MockECBExchangeRateProvider(ExchangeRateProvider):
    """
    A mock exchange rate provider with optional date-based rate schedules.

    Basic Usage (constant rate):
        provider = MockECBExchangeRateProvider(foreign_to_eur_init_value=Decimal("2.0"))
        # All dates return the same rate: 1 USD = 2 EUR

    Advanced Usage (date-based variable rates):
        rate_schedule = [
            (date(2023, 1, 1), Decimal("1.05")),   # 1 USD = 1.05 EUR from Jan 1
            (date(2023, 6, 1), Decimal("1.10")),   # 1 USD = 1.10 EUR from Jun 1
            (date(2023, 9, 1), Decimal("1.08")),   # 1 USD = 1.08 EUR from Sep 1
        ]
        provider = MockECBExchangeRateProvider(rate_schedule=rate_schedule)

    The rate_schedule is a list of (date, foreign_to_eur) tuples, sorted by date.
    For a given conversion date, the provider returns the rate from the most recent
    schedule entry on or before that date. If the date is before all entries,
    the first entry's rate is used.

    Currency-specific rates:
        currency_schedules = {
            "USD": [(date(2023, 1, 1), Decimal("1.05"))],
            "GBP": [(date(2023, 1, 1), Decimal("1.15"))],
        }
        provider = MockECBExchangeRateProvider(currency_schedules=currency_schedules)

    All data is deterministic - the same inputs always produce the same outputs.
    """

    def __init__(
        self,
        foreign_to_eur_init_value: Decimal = Decimal("2.0"),
        rate_schedule: Optional[List[Tuple[date, Decimal]]] = None,
        currency_schedules: Optional[Dict[str, List[Tuple[date, Decimal]]]] = None,
    ):
        """
        Initialize the mock provider.

        Args:
            foreign_to_eur_init_value: Default rate (1 Foreign = X EUR) for all currencies.
                                        Only used if rate_schedule and currency_schedules are None.
            rate_schedule: List of (date, foreign_to_eur) tuples for date-based rates.
                           Applies to all non-EUR currencies. Must be sorted by date.
            currency_schedules: Dict mapping currency codes to their own rate schedules.
                                Takes precedence over rate_schedule for specified currencies.
        """
        self.default_eur_currency_code = "EUR"
        self.default_foreign_to_eur = foreign_to_eur_init_value

        if self.default_foreign_to_eur.is_zero():
            raise ValueError("The EUR value of one foreign currency unit cannot be zero.")

        # Normalize and validate rate schedules
        self._rate_schedule: Optional[List[Tuple[date, Decimal]]] = None
        if rate_schedule is not None:
            self._rate_schedule = sorted(rate_schedule, key=lambda x: x[0])
            self._validate_schedule(self._rate_schedule, "rate_schedule")

        self._currency_schedules: Dict[str, List[Tuple[date, Decimal]]] = {}
        if currency_schedules is not None:
            for currency, schedule in currency_schedules.items():
                sorted_schedule = sorted(schedule, key=lambda x: x[0])
                self._validate_schedule(sorted_schedule, f"currency_schedules[{currency}]")
                self._currency_schedules[currency.upper()] = sorted_schedule

    def _validate_schedule(self, schedule: List[Tuple[date, Decimal]], name: str) -> None:
        """Validate a rate schedule for zero rates."""
        for entry_date, rate in schedule:
            if rate.is_zero():
                raise ValueError(
                    f"Rate schedule '{name}' contains zero rate for date {entry_date}. "
                    "Zero rates are not allowed."
                )

    def _get_rate_from_schedule(
        self, schedule: List[Tuple[date, Decimal]], target_date: date
    ) -> Decimal:
        """
        Get the rate for a target date from a sorted schedule.

        Returns the rate from the most recent entry on or before target_date.
        If target_date is before all entries, returns the first entry's rate.
        """
        if not schedule:
            return self.default_foreign_to_eur

        # Find the most recent entry on or before target_date
        applicable_rate = schedule[0][1]  # Default to first entry
        for entry_date, rate in schedule:
            if entry_date <= target_date:
                applicable_rate = rate
            else:
                break  # Schedule is sorted, no need to continue

        return applicable_rate

    def _get_foreign_to_eur_rate(self, date_of_conversion: date, currency_code: str) -> Decimal:
        """
        Get the foreign-to-EUR rate (1 Foreign = X EUR) for a given date and currency.
        """
        currency_upper = currency_code.upper()

        # Check currency-specific schedule first
        if currency_upper in self._currency_schedules:
            return self._get_rate_from_schedule(
                self._currency_schedules[currency_upper], date_of_conversion
            )

        # Fall back to general rate schedule
        if self._rate_schedule is not None:
            return self._get_rate_from_schedule(self._rate_schedule, date_of_conversion)

        # Fall back to default constant rate
        return self.default_foreign_to_eur

    def get_rate(self, date_of_conversion: date, currency_code: str) -> Optional[Decimal]:
        """
        Get the exchange rate for converting currency_code to EUR on date_of_conversion.

        Returns the rate as "foreign currency units per 1 EUR".
        Example: If 1 USD = 1.10 EUR, this returns 1/1.10 = 0.909...
        """
        currency_to_convert_upper = currency_code.upper()

        if currency_to_convert_upper == self.default_eur_currency_code:
            return Decimal("1.0")

        # Get the foreign-to-EUR rate (1 Foreign = X EUR)
        foreign_to_eur = self._get_foreign_to_eur_rate(date_of_conversion, currency_code)

        # CurrencyConverter expects "Foreign units per 1 EUR"
        # If 1 Foreign = X EUR, then 1 EUR = (1/X) Foreign
        return Decimal("1.0") / foreign_to_eur

    def prefetch_rates(self, start_date: date, end_date: date, currencies: Set[str]):
        # No-op for this mock - all rates are deterministic and in-memory
        pass

    def get_currency_code_mapping(self) -> Dict[str, str]:
        try:
            from src.config import CURRENCY_CODE_MAPPING_ECB
            return CURRENCY_CODE_MAPPING_ECB
        except ImportError:
            return {"CNH": "CNY"}

    def get_max_fallback_days(self) -> int:
        try:
            from src.config import MAX_FALLBACK_DAYS_EXCHANGE_RATES
            return MAX_FALLBACK_DAYS_EXCHANGE_RATES
        except ImportError:
            return 7


# =============================================================================
# Convenience Factory Functions
# =============================================================================

def create_constant_rate_provider(foreign_to_eur: Decimal = Decimal("2.0")) -> MockECBExchangeRateProvider:
    """Create a mock provider with a constant rate for all dates and currencies."""
    return MockECBExchangeRateProvider(foreign_to_eur_init_value=foreign_to_eur)


def create_variable_rate_provider(
    rate_schedule: List[Tuple[date, Decimal]],
) -> MockECBExchangeRateProvider:
    """
    Create a mock provider with date-based variable rates.

    Example:
        provider = create_variable_rate_provider([
            (date(2023, 1, 1), Decimal("1.05")),
            (date(2023, 6, 1), Decimal("1.10")),
        ])
    """
    return MockECBExchangeRateProvider(rate_schedule=rate_schedule)


def create_multi_currency_provider(
    currency_schedules: Dict[str, List[Tuple[date, Decimal]]],
    default_rate: Decimal = Decimal("1.0"),
) -> MockECBExchangeRateProvider:
    """
    Create a mock provider with currency-specific rate schedules.

    Example:
        provider = create_multi_currency_provider({
            "USD": [(date(2023, 1, 1), Decimal("1.10"))],
            "GBP": [(date(2023, 1, 1), Decimal("1.15"))],
        })
    """
    return MockECBExchangeRateProvider(
        foreign_to_eur_init_value=default_rate,
        currency_schedules=currency_schedules,
    )
