"""
Test Group: Precision and Rounding Tests

This module tests that the calculation engine handles numerical precision correctly,
particularly in edge cases involving:
- FifoLot dataclass with fractional quantities
- Decimal precision maintenance
- Cost basis calculations

PRD Coverage: Numerical precision requirements (28 decimal places internal)
"""

import pytest
from decimal import Decimal, ROUND_HALF_UP
from datetime import date

from src.engine.fifo_manager import FifoLot, ShortFifoLot
from src import config as global_config


# =============================================================================
# FifoLot Creation and Validation Tests
# =============================================================================

class TestFifoLotPrecision:
    """Tests for FifoLot numerical precision."""

    def test_simple_lot_creation(self):
        """Test basic lot creation with integer values."""
        qty = Decimal("10")
        unit_cost = Decimal("100.00")
        total_cost = qty * unit_cost

        lot = FifoLot(
            acquisition_date="2023-01-15",
            quantity=qty,
            unit_cost_basis_eur=unit_cost,
            total_cost_basis_eur=total_cost,
            source_transaction_id="T001",
        )

        assert lot.quantity == qty
        assert lot.unit_cost_basis_eur == unit_cost
        assert lot.total_cost_basis_eur == total_cost

    def test_fractional_quantity(self):
        """Test lot with fractional share quantity."""
        qty = Decimal("0.333333")
        unit_cost = Decimal("100.00")
        total_cost = qty * unit_cost

        lot = FifoLot(
            acquisition_date="2023-01-15",
            quantity=qty,
            unit_cost_basis_eur=unit_cost,
            total_cost_basis_eur=total_cost,
            source_transaction_id="T001",
        )

        assert lot.quantity == qty
        # Verify total is correctly calculated
        assert lot.total_cost_basis_eur == Decimal("33.333300")

    def test_repeating_decimal_cost(self):
        """Test lot with repeating decimal cost basis."""
        qty = Decimal("3")
        total_cost = Decimal("100.00")
        # 100/3 = 33.333... repeating - infinite decimal, can't be exact
        unit_cost = total_cost / qty

        lot = FifoLot(
            acquisition_date="2023-01-15",
            quantity=qty,
            unit_cost_basis_eur=unit_cost,
            total_cost_basis_eur=total_cost,
            source_transaction_id="T001",
        )

        assert lot.quantity == qty
        # Total cost is the authoritative value stored independently
        assert lot.total_cost_basis_eur == total_cost
        # Unit cost * qty will have small precision difference due to repeating decimal
        # The important invariant is that total_cost_basis_eur is preserved exactly
        recalculated = lot.unit_cost_basis_eur * qty
        assert abs(recalculated - total_cost) < Decimal("0.0000001")

    def test_very_small_quantity(self):
        """Test lot with very small fractional quantity."""
        qty = Decimal("0.000001")
        unit_cost = Decimal("1000000.00")
        total_cost = qty * unit_cost  # = 1.00

        lot = FifoLot(
            acquisition_date="2023-01-15",
            quantity=qty,
            unit_cost_basis_eur=unit_cost,
            total_cost_basis_eur=total_cost,
            source_transaction_id="T001",
        )

        assert lot.quantity == qty
        assert lot.total_cost_basis_eur == Decimal("1.00")

    def test_very_large_quantity(self):
        """Test lot with very large quantity."""
        qty = Decimal("1000000000")  # 1 billion
        unit_cost = Decimal("0.01")
        total_cost = qty * unit_cost  # = 10,000,000

        lot = FifoLot(
            acquisition_date="2023-01-15",
            quantity=qty,
            unit_cost_basis_eur=unit_cost,
            total_cost_basis_eur=total_cost,
            source_transaction_id="T001",
        )

        assert lot.quantity == qty
        assert lot.total_cost_basis_eur == Decimal("10000000")

    def test_zero_quantity_raises_error(self):
        """Test that zero quantity raises ValueError."""
        with pytest.raises(ValueError, match="positive finite Decimal"):
            FifoLot(
                acquisition_date="2023-01-15",
                quantity=Decimal("0"),
                unit_cost_basis_eur=Decimal("100"),
                total_cost_basis_eur=Decimal("0"),
                source_transaction_id="T001",
            )

    def test_negative_quantity_raises_error(self):
        """Test that negative quantity raises ValueError."""
        with pytest.raises(ValueError, match="positive finite Decimal"):
            FifoLot(
                acquisition_date="2023-01-15",
                quantity=Decimal("-10"),
                unit_cost_basis_eur=Decimal("100"),
                total_cost_basis_eur=Decimal("-1000"),
                source_transaction_id="T001",
            )

    def test_negative_cost_raises_error(self):
        """Test that negative cost basis raises ValueError."""
        with pytest.raises(ValueError, match="non-negative finite Decimal"):
            FifoLot(
                acquisition_date="2023-01-15",
                quantity=Decimal("10"),
                unit_cost_basis_eur=Decimal("-100"),
                total_cost_basis_eur=Decimal("-1000"),
                source_transaction_id="T001",
            )


# =============================================================================
# ShortFifoLot Tests
# =============================================================================

class TestShortFifoLotPrecision:
    """Tests for ShortFifoLot numerical precision."""

    def test_simple_short_lot_creation(self):
        """Test basic short lot creation."""
        qty = Decimal("10")
        unit_proceeds = Decimal("100.00")
        total_proceeds = qty * unit_proceeds

        lot = ShortFifoLot(
            opening_date="2023-01-15",
            quantity_shorted=qty,
            unit_sale_proceeds_eur=unit_proceeds,
            total_sale_proceeds_eur=total_proceeds,
            source_transaction_id="T001",
        )

        assert lot.quantity_shorted == qty
        assert lot.unit_sale_proceeds_eur == unit_proceeds
        assert lot.total_sale_proceeds_eur == total_proceeds

    def test_fractional_short_quantity(self):
        """Test short lot with fractional quantity."""
        qty = Decimal("0.5")
        unit_proceeds = Decimal("200.00")
        total_proceeds = qty * unit_proceeds

        lot = ShortFifoLot(
            opening_date="2023-01-15",
            quantity_shorted=qty,
            unit_sale_proceeds_eur=unit_proceeds,
            total_sale_proceeds_eur=total_proceeds,
            source_transaction_id="T001",
        )

        assert lot.quantity_shorted == qty
        assert lot.total_sale_proceeds_eur == Decimal("100.00")


# =============================================================================
# Decimal Precision Tests
# =============================================================================

class TestDecimalPrecision:
    """Tests for Decimal precision in calculations."""

    def test_internal_precision_is_high(self):
        """Verify that internal calculation precision is high."""
        # Check config has high precision
        assert global_config.INTERNAL_CALCULATION_PRECISION >= 28

    def test_decimal_addition_precision(self):
        """Test that Decimal addition maintains precision."""
        values = [Decimal("0.1"), Decimal("0.2"), Decimal("0.3")]
        total = sum(values)
        expected = Decimal("0.6")
        assert total == expected

    def test_decimal_multiplication_precision(self):
        """Test that Decimal multiplication maintains high precision.

        Note: Repeating decimals like 1/3 can't be exactly represented.
        Unlike floats where 0.1+0.2 != 0.3, Decimals maintain consistent
        behavior with configurable precision. The result is very close to 1
        but not exactly 1 due to the infinite nature of 1/3.
        """
        a = Decimal("1") / Decimal("3")
        b = Decimal("3")
        result = a * b
        # Very close to 1, but not exact due to repeating decimal
        assert abs(result - Decimal("1")) < Decimal("1e-27")
        # Contrast with floats: 0.1 + 0.2 != 0.3 due to binary representation
        # Decimals are much better behaved for financial calculations

    def test_many_small_additions_no_drift(self):
        """Test that many small additions don't accumulate errors."""
        value = Decimal("0.01")
        count = 10000
        total = sum([value] * count)
        expected = value * count
        assert total == expected
        assert total == Decimal("100.00")

    def test_division_with_rounding(self):
        """Test division with explicit rounding."""
        qty = Decimal("7")
        total = Decimal("100.00")
        per_share = total / qty

        # Recalculating should give back exact total
        recalc = per_share * qty
        # This may have precision differences, but should be close
        assert abs(recalc - total) < Decimal("0.0000000001")

    def test_commission_allocation_precision(self):
        """Test that commission allocation maintains precision."""
        total_cost = Decimal("1000.00")
        commission = Decimal("1.00")
        qty = Decimal("33")

        total_with_commission = total_cost + commission
        cost_per_share = total_with_commission / qty

        # Verify consistency
        recalc = cost_per_share * qty
        # Should be very close to original
        assert abs(recalc - total_with_commission) < Decimal("0.0000000001")


# =============================================================================
# Multiple Lots Accumulation Tests
# =============================================================================

class TestManyLotsAccumulation:
    """Tests for precision when working with many lots."""

    def test_twelve_monthly_lots(self):
        """Test creating 12 monthly lots and summing."""
        monthly_qty = Decimal("0.333")
        monthly_cost_per_unit = Decimal("100.10")

        lots = []
        for month in range(1, 13):
            total_cost = monthly_qty * monthly_cost_per_unit
            lot = FifoLot(
                acquisition_date=f"2023-{month:02d}-15",
                quantity=monthly_qty,
                unit_cost_basis_eur=monthly_cost_per_unit,
                total_cost_basis_eur=total_cost,
                source_transaction_id=f"T{month:02d}",
            )
            lots.append(lot)

        # Sum all quantities
        total_qty = sum(lot.quantity for lot in lots)
        expected_qty = monthly_qty * 12
        assert total_qty == expected_qty

        # Sum all costs
        total_cost = sum(lot.total_cost_basis_eur for lot in lots)
        expected_cost = monthly_qty * monthly_cost_per_unit * 12
        assert total_cost == expected_cost

    def test_hundred_lots(self):
        """Test creating 100 lots and summing."""
        qty = Decimal("1.01")
        unit_cost = Decimal("10.10")

        lots = []
        for i in range(100):
            total_cost = qty * unit_cost
            lot = FifoLot(
                acquisition_date="2023-01-01",
                quantity=qty,
                unit_cost_basis_eur=unit_cost,
                total_cost_basis_eur=total_cost,
                source_transaction_id=f"T{i:03d}",
            )
            lots.append(lot)

        # Sum all quantities
        total_qty = sum(lot.quantity for lot in lots)
        expected_qty = qty * 100
        assert total_qty == expected_qty

        # Sum all costs
        total_cost = sum(lot.total_cost_basis_eur for lot in lots)
        expected_cost = qty * unit_cost * 100
        assert total_cost == expected_cost


# =============================================================================
# Gain/Loss Calculation Precision
# =============================================================================

class TestGainLossCalculationPrecision:
    """Tests for precision in gain/loss calculations."""

    def test_small_profit_calculation(self):
        """Test calculating small profit on large position."""
        qty = Decimal("10000")
        cost_per_share = Decimal("100.00")
        proceeds_per_share = Decimal("100.01")  # 0.01% profit

        total_cost = qty * cost_per_share
        total_proceeds = qty * proceeds_per_share
        gain = total_proceeds - total_cost

        # Should be exactly 100.00
        assert gain == Decimal("100.00")

    def test_breakeven_is_zero(self):
        """Test that breakeven results in exactly zero gain."""
        qty = Decimal("7")
        cost_per_share = Decimal("100.00")

        total_cost = qty * cost_per_share
        total_proceeds = qty * cost_per_share

        gain = total_proceeds - total_cost
        assert gain == Decimal("0")

    def test_loss_calculation(self):
        """Test loss calculation precision."""
        qty = Decimal("100")
        cost = Decimal("10000.00")
        proceeds = Decimal("9500.00")

        loss = proceeds - cost
        assert loss == Decimal("-500.00")

    def test_gain_with_commission(self):
        """Test gain calculation with commission."""
        qty = Decimal("10")
        buy_price = Decimal("100.00")
        sell_price = Decimal("110.00")
        commission = Decimal("1.00")

        # Buy: (qty * price) + commission
        cost = qty * buy_price + commission  # 1001.00

        # Sell: (qty * price) - commission
        proceeds = qty * sell_price - commission  # 1099.00

        gain = proceeds - cost  # 1099 - 1001 = 98.00
        assert gain == Decimal("98.00")


# =============================================================================
# Edge Cases
# =============================================================================

class TestEdgeCases:
    """Edge case precision tests."""

    def test_very_high_precision_decimal(self):
        """Test handling of very high precision decimals."""
        # 28 decimal places
        high_precision = Decimal("0.1234567890123456789012345678")
        qty = Decimal("100")

        total = high_precision * qty
        # Should maintain precision
        back = total / qty
        assert back == high_precision

    def test_penny_stock_precision(self):
        """Test precision with penny stock prices."""
        qty = Decimal("10000")
        price = Decimal("0.0001")  # 0.01 cents

        total = qty * price
        assert total == Decimal("1.0000")

    def test_crypto_satoshi_precision(self):
        """Test precision with satoshi-level crypto amounts."""
        # 1 satoshi = 0.00000001 BTC
        qty = Decimal("0.00000001")
        price = Decimal("100000.00")  # $100k per BTC

        total = qty * price
        assert total == Decimal("0.00100000")  # $0.001
