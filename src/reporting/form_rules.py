# src/reporting/form_rules.py
"""Compatibility shim (rework2 AR2): the year-specific Anlage KAP form rules
live in the law-as-data registry. Import from src.tax_law.registry directly
in new code; this module keeps existing import paths working."""
from src.tax_law.registry import FormYearRules, get_form_rules  # noqa: F401
