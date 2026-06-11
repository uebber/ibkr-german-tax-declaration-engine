"""
AR7 (rework2): legal-position register — contested readings as data.

legal_basis: register of positions on UNSETTLED questions (short-FX analogy,
Einlagenrückgewähr excess, implicit-FX separation); each entry carries the
alternative and its sources, and the console report renders the caveats.
"""
from src.tax_law.legal_positions import LEGAL_POSITIONS, render_console_section


def test_register_entries_are_complete():
    assert {p.id for p in LEGAL_POSITIONS} >= {
        "FX_SHORT_ANALOGY", "EINLAGENRUECKGEWAEHR_EXCESS", "IMPLICIT_FX_SEPARATION",
    }
    for p in LEGAL_POSITIONS:
        # every position must state what was taken, what was not, and why
        assert p.question and p.position_taken and p.alternative and p.sources


def test_console_section_lists_every_position():
    text = "\n".join(render_console_section())
    for p in LEGAL_POSITIONS:
        assert p.id in text
