# src/tax_law/legal_positions.py
"""
Legal-position register (rework2-plan AR7) — the UNSETTLED legal questions on
which this engine must take a position, as first-class data instead of prose
scattered across reference files. Rendered as report caveats so every
declaration states which contested readings it relies on.

Add an entry whenever the engine implements a position on a question where
statute/BMF guidance is silent or disputed; remove it when the question is
settled (cite the settling source in the commit).
"""
from dataclasses import dataclass
from typing import List, Tuple


@dataclass(frozen=True)
class LegalPosition:
    id: str
    question: str          # the unsettled question
    position_taken: str    # what this engine does
    alternative: str       # the defensible alternative NOT taken
    sources: Tuple[str, ...]  # reference/ files and primary sources


LEGAL_POSITIONS: List[LegalPosition] = [
    LegalPosition(
        id="FX_SHORT_ANALOGY",
        question=("Steuerliche Behandlung von Short-Positionen in Fremdwährung "
                  "(negativer Saldo) im Privatvermögen — von der BMF-Verwaltungs"
                  "auffassung nicht ausdrücklich geregelt."),
        position_taken=("Analog zu Long-Positionen unter §20 Abs. 2 S. 1 Nr. 7 EStG: "
                        "Eröffnung = Veräußerung zum Tageskurs, Eindeckung = Anschaffung; "
                        "FIFO je Währung."),
        alternative=("Nichtsteuerbarkeit mangels ausdrücklicher Regelung; oder §23 EStG "
                     "bei nicht verzinslichen Konten."),
        sources=("reference/bmf-guidance/fremdwaehrung-konten.md",
                 "BMF-Schreiben 19.05.2022, Rz. 131"),
    ),
    LegalPosition(
        id="EINLAGENRUECKGEWAEHR_EXCESS",
        question=("Einlagenrückgewähr (§20 Abs. 1 Nr. 1 S. 3 EStG) übersteigt die "
                  "Anschaffungskosten einzelner FIFO-Lose: Behandlung des Überhangs "
                  "bei Beteiligungen < 1% im Privatvermögen."),
        position_taken=("Minderung der Anschaffungskosten FIFO-sequenziell über die Lose; "
                        "erst ein über ALLE Lose hinausgehender Überhang wird sofort als "
                        "Kapitalertrag erfasst."),
        alternative=("Anteilsbezogene (per-share) Minderung mit negativen Anschaffungs"
                     "kosten (h.M. für <1%-Beteiligungen) — identisches Ergebnis bei "
                     "Vollverkauf, abweichend bei Teilverkäufen."),
        sources=("reference/bmf-guidance/abgeltungsteuer-einzelfragen.md",
                 "legal-review-todo.md (F5)"),
    ),
    LegalPosition(
        id="IMPLICIT_FX_SEPARATION",
        question=("Ob Währungsgewinne, die in Wertpapierkäufen/-verkäufen in Fremd"
                  "währung eingebettet sind, separat als FX-Geschäft zu erfassen sind."),
        position_taken=("Konservative Trennung: jeder Fremdwährungsabfluss/-zufluss aus "
                        "Wertpapiergeschäften ist eine eigenständige Veräußerung/Anschaffung "
                        "der Währung (FIFO), im Einklang mit BMF Rz. 131."),
        alternative=("Keine Separierung (Währungseffekt nur im EUR-Wertpapierergebnis)."),
        sources=("reference/bmf-guidance/fremdwaehrung-konten.md",),
    ),
]


def render_console_section() -> List[str]:
    """Lines for the console tax report's caveat section."""
    lines = ["", "--- VERTRETENE RECHTSAUFFASSUNGEN (ungeklärte Rechtsfragen) ---",
             "  Diese Erklärung beruht auf folgenden Positionen zu ungeklärten Fragen:"]
    for p in LEGAL_POSITIONS:
        lines.append(f"  [{p.id}] {p.position_taken}")
    lines.append("  Details und Alternativen: src/tax_law/legal_positions.py")
    return lines
