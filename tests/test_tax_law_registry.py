"""
Law-as-data registry: the engine and the tests read the SAME
tables; entries carry citations; lookups outside validity are loud.

legal_basis: §20 InvStG (Teilfreistellung), §18 Abs. 4 InvStG (Basiszins),
§20 Abs. 6 EStG + JStG 2024 §52 Abs. 28 (form structure, cap repeal) —
mirrored from reference/ (see registry module docstring).
"""
import logging
import re
from decimal import Decimal
from pathlib import Path

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

    def test_missing_year_inside_the_regime_is_loud(self, caplog):
        """A year >= 2018 that the table lacks is a real gap: no rate, no VP,
        and deemed income may be understated. WARNING."""
        with caplog.at_level(logging.INFO):
            assert registry.basiszins_pct(2030) is None
        assert any("No Basiszins" in r.message and r.levelname == "WARNING"
                   for r in caplog.records)

    def test_pre_regime_year_is_not_reported_as_a_gap(self, caplog):
        """Before 2018 there was no Vorabpauschale at all (§56 Abs. 1 S. 1
        InvStG), so the absence is correct and must not read as a missing rate."""
        with caplog.at_level(logging.INFO):
            assert registry.basiszins_pct(2017) is None
        assert not any(r.levelname == "WARNING" for r in caplog.records)
        assert any("InvStG 2018 regime" in r.message for r in caplog.records)

    def test_bewg_basiszins_values_are_not_in_the_table(self):
        """2016/2017 once carried 1.10%/0.59% — the §203 Abs. 2 BewG Basiszins
        for the vereinfachtes Ertragswertverfahren, a different statute. No
        §18 Abs. 4 InvStG rate exists for those years."""
        assert 2016 not in registry.BASISZINS_PCT
        assert 2017 not in registry.BASISZINS_PCT
        assert min(registry.BASISZINS_PCT) == registry.INVSTG_2018_FIRST_BASISZINS_YEAR == 2018


class TestBasiszinsReferenceConsistency:
    """The registry must equal the BMF table in the knowledge store, row for
    row. Parsed from the document — not a third hand-kept copy of the numbers,
    which could not detect the drift it exists to detect.
    Source: reference/bmf-guidance/basiszins-vorabpauschale.md."""

    REFERENCE_DOC = (Path(__file__).resolve().parent.parent
                     / "reference" / "bmf-guidance" / "basiszins-vorabpauschale.md")

    @staticmethod
    def _parse_published_table(text: str) -> dict[int, Decimal]:
        """Rows of the '## Published Basiszins Values' table:
        | 2024 | 2.29% | 02.01.2024 | ... |"""
        rows: dict[int, Decimal] = {}
        in_table = False
        for line in text.splitlines():
            if line.startswith("## Published Basiszins Values"):
                in_table = True
                continue
            if in_table and line.startswith("#"):
                break
            m = re.match(r"^\|\s*(\d{4})\s*\|\s*(-?\d+\.\d+)%\s*\|", line)
            if in_table and m:
                rows[int(m.group(1))] = Decimal(m.group(2))
        return rows

    def test_parser_finds_the_table(self):
        published = self._parse_published_table(self.REFERENCE_DOC.read_text(encoding="utf-8"))
        assert len(published) >= 9, f"table not parsed (got {published})"

    def test_registry_matches_the_reference_document(self):
        published = self._parse_published_table(self.REFERENCE_DOC.read_text(encoding="utf-8"))
        assert registry.BASISZINS_PCT == published, (
            "src/tax_law/registry.py and reference/bmf-guidance/"
            "basiszins-vorabpauschale.md disagree; the reference is authoritative"
        )

    def test_no_gap_inside_the_covered_range(self):
        years = sorted(registry.BASISZINS_PCT)
        assert years == list(range(years[0], years[-1] + 1)), (
            f"missing year(s) between {years[0]} and {years[-1]}: a gap silently "
            "skips that year's Vorabpauschale"
        )
