"""
Law-as-data registry (rework2 AR2): the engine and the tests read the SAME
tables; entries carry citations; lookups outside validity are loud.

legal_basis: §20 InvStG (Teilfreistellung), §18 Abs. 4 InvStG (Basiszins),
§20 Abs. 6 EStG + JStG 2024 §52 Abs. 28 (form structure, cap repeal) —
mirrored from reference/ (see registry module docstring).
"""
import logging
from decimal import Decimal

from src.domain.enums import InvestmentFundType
from src.tax_law import registry


class TestTeilfreistellung:
    def test_rates_match_invstg_20(self):
        """§20 Abs. 1/2/3 InvStG: 30/15/60/80; Sonstige/None -> 0."""
        r = registry.teilfreistellung_rate
        assert r(InvestmentFundType.AKTIENFONDS) == Decimal("0.30")
        assert r(InvestmentFundType.MISCHFONDS) == Decimal("0.15")
        assert r(InvestmentFundType.IMMOBILIENFONDS) == Decimal("0.60")
        assert r(InvestmentFundType.AUSLANDS_IMMOBILIENFONDS) == Decimal("0.80")
        assert r(InvestmentFundType.SONSTIGE_FONDS) == Decimal("0.00")
        assert r(None) == Decimal("0.00")

    def test_shim_delegates(self):
        from src.utils.tax_utils import get_teilfreistellung_rate_for_fund_type
        assert get_teilfreistellung_rate_for_fund_type(
            InvestmentFundType.AKTIENFONDS) == Decimal("0.30")


class TestFormYearRules:
    def test_cap_repealed_for_every_configured_year(self):
        """JStG 2024 abolished the €20k cap RETROACTIVELY for all open cases
        (§52 Abs. 28 EStG n.F.) — no year may apply it."""
        for year, rules in registry._FORM_RULES_BY_YEAR.items():
            assert rules.derivative_loss_cap_applies is False, year

    def test_2024_vs_2025_form_structure(self):
        r24, r25 = registry.get_form_rules(2024), registry.get_form_rules(2025)
        assert r24.separate_derivative_lines and not r25.separate_derivative_lines
        assert not r24.z19_subtracts_derivative_losses and r25.z19_subtracts_derivative_losses
        assert not r24.z22_includes_derivative_losses and r25.z22_includes_derivative_losses

    def test_pre_2024_years_use_2024_structure(self):
        """VZ 2021-2023 share the <=2024 form structure (earliest fallback)."""
        assert registry.get_form_rules(2023) == registry.get_form_rules(2024)

    def test_reporting_shim_reexports(self):
        from src.reporting.form_rules import get_form_rules, FormYearRules
        assert get_form_rules is registry.get_form_rules
        assert FormYearRules is registry.FormYearRules


class TestBasiszinsLookup:
    def test_known_year(self):
        assert registry.basiszins_pct(2024) == Decimal("2.29")

    def test_negative_years_present_not_gaps(self, caplog):
        """2021/2022 are COMPUTED zero-VP years (negative rate), not config gaps."""
        with caplog.at_level(logging.WARNING):
            assert registry.basiszins_pct(2021) == Decimal("-0.45")
        assert not any("No Basiszins" in r.message for r in caplog.records)

    def test_unknown_year_is_loud(self, caplog):
        with caplog.at_level(logging.WARNING):
            assert registry.basiszins_pct(1999) is None
        assert any("No Basiszins" in r.message and r.levelname == "WARNING"
                   for r in caplog.records)
