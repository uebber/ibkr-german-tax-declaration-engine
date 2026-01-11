"""
Tests for Mock Providers

This module tests the mock providers used in testing, particularly the
enhanced MockECBExchangeRateProvider with variable FX rate support.
"""

import pytest
from decimal import Decimal
from datetime import date

from tests.support.mock_providers import (
    MockECBExchangeRateProvider,
    create_constant_rate_provider,
    create_variable_rate_provider,
    create_multi_currency_provider,
)


# =============================================================================
# Constant Rate Tests (Backward Compatibility)
# =============================================================================

class TestConstantRateProvider:
    """Tests for the constant rate provider (original behavior)."""

    def test_default_rate(self):
        """Test that default rate is 2.0."""
        provider = MockECBExchangeRateProvider()
        # 1 USD = 2 EUR means 1 EUR = 0.5 USD
        rate = provider.get_rate(date(2023, 6, 15), "USD")
        assert rate == Decimal("0.5")

    def test_custom_constant_rate(self):
        """Test custom constant rate."""
        provider = MockECBExchangeRateProvider(foreign_to_eur_init_value=Decimal("1.10"))
        # 1 USD = 1.10 EUR means 1 EUR = 1/1.10 USD
        rate = provider.get_rate(date(2023, 6, 15), "USD")
        expected = Decimal("1.0") / Decimal("1.10")
        assert rate == expected

    def test_eur_to_eur_is_one(self):
        """Test that EUR to EUR rate is always 1."""
        provider = MockECBExchangeRateProvider(foreign_to_eur_init_value=Decimal("1.50"))
        rate = provider.get_rate(date(2023, 6, 15), "EUR")
        assert rate == Decimal("1.0")

    def test_case_insensitive_currency(self):
        """Test that currency codes are case-insensitive."""
        provider = MockECBExchangeRateProvider(foreign_to_eur_init_value=Decimal("1.20"))
        rate_upper = provider.get_rate(date(2023, 6, 15), "USD")
        rate_lower = provider.get_rate(date(2023, 6, 15), "usd")
        rate_mixed = provider.get_rate(date(2023, 6, 15), "Usd")
        assert rate_upper == rate_lower == rate_mixed

    def test_zero_rate_raises_error(self):
        """Test that zero rate raises ValueError."""
        with pytest.raises(ValueError, match="cannot be zero"):
            MockECBExchangeRateProvider(foreign_to_eur_init_value=Decimal("0"))

    def test_factory_function(self):
        """Test create_constant_rate_provider factory."""
        provider = create_constant_rate_provider(Decimal("1.50"))
        rate = provider.get_rate(date(2023, 6, 15), "USD")
        expected = Decimal("1.0") / Decimal("1.50")
        assert rate == expected


# =============================================================================
# Variable Rate Schedule Tests
# =============================================================================

class TestVariableRateProvider:
    """Tests for date-based variable rate schedules."""

    def test_single_rate_period(self):
        """Test with single rate in schedule."""
        provider = create_variable_rate_provider([
            (date(2023, 1, 1), Decimal("1.10")),
        ])

        # Any date should return the single rate
        rate_jan = provider.get_rate(date(2023, 1, 15), "USD")
        rate_jun = provider.get_rate(date(2023, 6, 15), "USD")
        rate_dec = provider.get_rate(date(2023, 12, 31), "USD")

        expected = Decimal("1.0") / Decimal("1.10")
        assert rate_jan == expected
        assert rate_jun == expected
        assert rate_dec == expected

    def test_multiple_rate_periods(self):
        """Test with multiple rate periods."""
        provider = create_variable_rate_provider([
            (date(2023, 1, 1), Decimal("1.05")),
            (date(2023, 6, 1), Decimal("1.10")),
            (date(2023, 9, 1), Decimal("1.08")),
        ])

        # January: 1.05
        rate_jan = provider.get_rate(date(2023, 1, 15), "USD")
        assert rate_jan == Decimal("1.0") / Decimal("1.05")

        # May: still 1.05 (before June change)
        rate_may = provider.get_rate(date(2023, 5, 31), "USD")
        assert rate_may == Decimal("1.0") / Decimal("1.05")

        # June 1: exactly on boundary, should be 1.10
        rate_jun1 = provider.get_rate(date(2023, 6, 1), "USD")
        assert rate_jun1 == Decimal("1.0") / Decimal("1.10")

        # July: 1.10
        rate_jul = provider.get_rate(date(2023, 7, 15), "USD")
        assert rate_jul == Decimal("1.0") / Decimal("1.10")

        # September: 1.08
        rate_sep = provider.get_rate(date(2023, 9, 15), "USD")
        assert rate_sep == Decimal("1.0") / Decimal("1.08")

        # December: still 1.08
        rate_dec = provider.get_rate(date(2023, 12, 31), "USD")
        assert rate_dec == Decimal("1.0") / Decimal("1.08")

    def test_date_before_schedule(self):
        """Test date before first schedule entry uses first rate."""
        provider = create_variable_rate_provider([
            (date(2023, 6, 1), Decimal("1.10")),
        ])

        # January is before June - should still use 1.10 (first available)
        rate = provider.get_rate(date(2023, 1, 15), "USD")
        assert rate == Decimal("1.0") / Decimal("1.10")

    def test_unsorted_schedule_is_sorted(self):
        """Test that unsorted schedule is auto-sorted."""
        # Provide schedule in reverse order
        provider = create_variable_rate_provider([
            (date(2023, 9, 1), Decimal("1.08")),
            (date(2023, 1, 1), Decimal("1.05")),
            (date(2023, 6, 1), Decimal("1.10")),
        ])

        # Should still work correctly
        rate_jan = provider.get_rate(date(2023, 3, 15), "USD")
        rate_jul = provider.get_rate(date(2023, 7, 15), "USD")
        rate_oct = provider.get_rate(date(2023, 10, 15), "USD")

        assert rate_jan == Decimal("1.0") / Decimal("1.05")
        assert rate_jul == Decimal("1.0") / Decimal("1.10")
        assert rate_oct == Decimal("1.0") / Decimal("1.08")

    def test_schedule_with_zero_rate_raises_error(self):
        """Test that zero rate in schedule raises ValueError."""
        with pytest.raises(ValueError, match="zero rate"):
            create_variable_rate_provider([
                (date(2023, 1, 1), Decimal("1.05")),
                (date(2023, 6, 1), Decimal("0")),
            ])

    def test_determinism(self):
        """Test that same inputs always produce same outputs."""
        schedule = [
            (date(2023, 1, 1), Decimal("1.05")),
            (date(2023, 6, 1), Decimal("1.10")),
        ]

        provider1 = create_variable_rate_provider(schedule)
        provider2 = create_variable_rate_provider(schedule)

        test_date = date(2023, 7, 15)
        rate1 = provider1.get_rate(test_date, "USD")
        rate2 = provider2.get_rate(test_date, "USD")

        assert rate1 == rate2


# =============================================================================
# Multi-Currency Schedule Tests
# =============================================================================

class TestMultiCurrencyProvider:
    """Tests for currency-specific rate schedules."""

    def test_different_currencies_different_rates(self):
        """Test that different currencies have different rates."""
        provider = create_multi_currency_provider({
            "USD": [(date(2023, 1, 1), Decimal("1.10"))],
            "GBP": [(date(2023, 1, 1), Decimal("1.15"))],
        })

        rate_usd = provider.get_rate(date(2023, 6, 15), "USD")
        rate_gbp = provider.get_rate(date(2023, 6, 15), "GBP")

        assert rate_usd == Decimal("1.0") / Decimal("1.10")
        assert rate_gbp == Decimal("1.0") / Decimal("1.15")
        assert rate_usd != rate_gbp

    def test_currency_specific_schedule_overrides_general(self):
        """Test that currency-specific schedule takes precedence."""
        provider = MockECBExchangeRateProvider(
            rate_schedule=[(date(2023, 1, 1), Decimal("1.00"))],  # General rate
            currency_schedules={
                "USD": [(date(2023, 1, 1), Decimal("1.10"))],  # USD-specific rate
            },
        )

        # USD should use its specific rate
        rate_usd = provider.get_rate(date(2023, 6, 15), "USD")
        assert rate_usd == Decimal("1.0") / Decimal("1.10")

        # GBP should fall back to general schedule
        rate_gbp = provider.get_rate(date(2023, 6, 15), "GBP")
        assert rate_gbp == Decimal("1.0") / Decimal("1.00")

    def test_currency_with_own_date_progression(self):
        """Test that each currency can have its own rate changes."""
        provider = create_multi_currency_provider({
            "USD": [
                (date(2023, 1, 1), Decimal("1.05")),
                (date(2023, 7, 1), Decimal("1.10")),
            ],
            "GBP": [
                (date(2023, 1, 1), Decimal("1.15")),
                (date(2023, 4, 1), Decimal("1.18")),
            ],
        })

        # Check USD progression
        rate_usd_mar = provider.get_rate(date(2023, 3, 15), "USD")
        rate_usd_aug = provider.get_rate(date(2023, 8, 15), "USD")
        assert rate_usd_mar == Decimal("1.0") / Decimal("1.05")
        assert rate_usd_aug == Decimal("1.0") / Decimal("1.10")

        # Check GBP progression (changes at different time)
        rate_gbp_mar = provider.get_rate(date(2023, 3, 15), "GBP")
        rate_gbp_aug = provider.get_rate(date(2023, 8, 15), "GBP")
        assert rate_gbp_mar == Decimal("1.0") / Decimal("1.15")
        assert rate_gbp_aug == Decimal("1.0") / Decimal("1.18")

    def test_unlisted_currency_uses_default(self):
        """Test that currencies not in schedules use default rate."""
        provider = MockECBExchangeRateProvider(
            foreign_to_eur_init_value=Decimal("2.0"),
            currency_schedules={
                "USD": [(date(2023, 1, 1), Decimal("1.10"))],
            },
        )

        # CHF is not in schedules - should use default
        rate_chf = provider.get_rate(date(2023, 6, 15), "CHF")
        assert rate_chf == Decimal("0.5")  # 1/2.0

    def test_case_insensitive_currency_in_schedules(self):
        """Test currency codes in schedules are case-insensitive."""
        provider = create_multi_currency_provider({
            "usd": [(date(2023, 1, 1), Decimal("1.10"))],  # lowercase
        })

        rate = provider.get_rate(date(2023, 6, 15), "USD")  # uppercase query
        assert rate == Decimal("1.0") / Decimal("1.10")


# =============================================================================
# Edge Cases and Integration
# =============================================================================

class TestEdgeCases:
    """Edge case tests."""

    def test_same_day_rate_change(self):
        """Test rate lookup on exact day of change."""
        provider = create_variable_rate_provider([
            (date(2023, 6, 15), Decimal("1.05")),
            (date(2023, 6, 16), Decimal("1.10")),
        ])

        rate_15 = provider.get_rate(date(2023, 6, 15), "USD")
        rate_16 = provider.get_rate(date(2023, 6, 16), "USD")

        assert rate_15 == Decimal("1.0") / Decimal("1.05")
        assert rate_16 == Decimal("1.0") / Decimal("1.10")

    def test_very_old_date(self):
        """Test with date before any schedule entries."""
        provider = create_variable_rate_provider([
            (date(2023, 1, 1), Decimal("1.10")),
        ])

        # 2020 is before 2023 schedule
        rate = provider.get_rate(date(2020, 6, 15), "USD")
        assert rate == Decimal("1.0") / Decimal("1.10")

    def test_very_future_date(self):
        """Test with date far after last schedule entry."""
        provider = create_variable_rate_provider([
            (date(2023, 1, 1), Decimal("1.10")),
        ])

        # 2030 is after 2023 schedule
        rate = provider.get_rate(date(2030, 6, 15), "USD")
        assert rate == Decimal("1.0") / Decimal("1.10")

    def test_prefetch_is_noop(self):
        """Test that prefetch doesn't raise errors."""
        provider = create_variable_rate_provider([
            (date(2023, 1, 1), Decimal("1.10")),
        ])

        # Should not raise
        provider.prefetch_rates(
            date(2023, 1, 1),
            date(2023, 12, 31),
            {"USD", "EUR", "GBP"},
        )

    def test_many_rate_changes(self):
        """Test schedule with many rate changes."""
        # Monthly rate changes throughout the year
        schedule = [
            (date(2023, month, 1), Decimal(f"1.{month:02d}"))
            for month in range(1, 13)
        ]
        provider = create_variable_rate_provider(schedule)

        # Check mid-month for each period
        for month in range(1, 12):
            expected_rate = Decimal(f"1.{month:02d}")
            actual = provider.get_rate(date(2023, month, 15), "USD")
            assert actual == Decimal("1.0") / expected_rate, f"Failed for month {month}"
