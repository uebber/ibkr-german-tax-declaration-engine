# Anlage KAP-INV -- Zeilenreferenz

## Source

- **2024 Form:** [formulare-bfinv.de -- Anlage KAP-INV 2024](https://www.formulare-bfinv.de/ffw/action/invoke.do?id=035004_24)
- **2024 Instructions:** Already in repository: `reference/Anltg_KAP_INV_24.md`
- **2025 Instructions:** Already in repository: `reference/Anltg_KAP_INV_25.md`
- **Legal basis:** InvStG 16, 18, 19, 20

## Relevance to Engine

Maps investment fund events to form lines. All amounts are reported as GROSS (brutto, before Teilfreistellung).

---

## Distribution Lines (Ausschuettungen brutto)

| Zeile | Fund Type | Engine TaxReportingCategory |
|-------|-----------|----------------------------|
| 4 | Aktienfonds | `ANLAGE_KAP_INV_AKTIENFONDS_AUSSCHUETTUNG_GROSS` |
| 5 | Mischfonds | `ANLAGE_KAP_INV_MISCHFONDS_AUSSCHUETTUNG_GROSS` |
| 6 | Immobilienfonds | `ANLAGE_KAP_INV_IMMOBILIENFONDS_AUSSCHUETTUNG_GROSS` |
| 7 | Auslands-Immobilienfonds | `ANLAGE_KAP_INV_AUSLANDS_IMMOBILIENFONDS_AUSSCHUETTUNG_GROSS` |
| 8 | Sonstige Fonds | `ANLAGE_KAP_INV_SONSTIGE_FONDS_AUSSCHUETTUNG_GROSS` |

---

## Vorabpauschale Lines (brutto)

**These take the Vorabpauschale for the *preceding* calendar year.** Zeilen 9-13 of the VZ `Y`
form take *"die Ihnen im Jahr `Y` als zugeflossen geltenden Vorabpauschalen"*, and the
Vorabpauschale for `Y-1` is deemed to flow on the first working day of `Y` (18 Abs. 3 InvStG).
The 2024 Anleitung says it outright: *"Die Vorabpauschale fuer 2023 gilt am 2. Januar 2024 als
zugeflossen."* See `investment-tax-law/invstg-18-vorabpauschale.md`.

| Zeile | Fund Type | Engine TaxReportingCategory |
|-------|-----------|----------------------------|
| 9 | Aktienfonds | `ANLAGE_KAP_INV_AKTIENFONDS_VORABPAUSCHALE_BRUTTO` |
| 10 | Mischfonds | `ANLAGE_KAP_INV_MISCHFONDS_VORABPAUSCHALE_BRUTTO` |
| 11 | Immobilienfonds | `ANLAGE_KAP_INV_IMMOBILIENFONDS_VORABPAUSCHALE_BRUTTO` |
| 12 | Auslands-Immobilienfonds | `ANLAGE_KAP_INV_AUSLANDS_IMMOBILIENFONDS_VORABPAUSCHALE_BRUTTO` |
| 13 | Sonstige Fonds | `ANLAGE_KAP_INV_SONSTIGE_FONDS_VORABPAUSCHALE_BRUTTO` |

---

## Sale Gain/Loss Lines (Veraeusserungsgewinn/-verlust brutto)

| Zeile | Fund Type | Engine TaxReportingCategory |
|-------|-----------|----------------------------|
| 14 | Aktienfonds | `ANLAGE_KAP_INV_AKTIENFONDS_GEWINN_GROSS` |
| 17 | Mischfonds | `ANLAGE_KAP_INV_MISCHFONDS_GEWINN_GROSS` |
| 20 | Immobilienfonds | `ANLAGE_KAP_INV_IMMOBILIENFONDS_GEWINN_GROSS` |
| 23 | Auslands-Immobilienfonds | `ANLAGE_KAP_INV_AUSLANDS_IMMOBILIENFONDS_GEWINN_GROSS` |
| 26 | Sonstige Fonds | `ANLAGE_KAP_INV_SONSTIGE_FONDS_GEWINN_GROSS` |

The two interleaved line sets are distinct transitional rules for pre-2018 units, not one
(Anleitung headings, read 2026-08-03):

- **Zeilen 15, 18, 21, 24, 27** -- *"Gewinne aus der Veraeusserung von bestandsgeschuetzten
  Alt-Anteilen"* i. S. d. 56 Abs. 6 Satz 1 Nr. 2 InvStG (acquired before 01.01.2009 and held in
  Privatvermoegen since). Gains **only**; losses are not netted here. Carried over from Zeile 55.
  These amounts are *already included* in the Zeilen 14/17/20/23/26 figures; the separate entry
  exists so the Finanzamt can apply the EUR 100 000 Freibetrag.
- **Zeilen 16, 19, 22, 25, 28** -- gains and losses from the **fiktive Veraeusserung** of
  *nicht* bestandsgeschuetzte Alt-Anteile i. S. d. 56 Abs. 2 i. V. m. Abs. 3 Satz 1 InvStG,
  deemed sold at the close of 31.12.2017. Carried over from Zeile 56.

Neither is produced by this engine: it has no pre-2018 acquisition data and no
Alt-Anteil classification. A taxpayer holding such units must complete these lines by hand.

---

## Vorabpauschale Deduction on Sale -- Zeile 53

| Zeile | Description | Engine TaxReportingCategory |
|-------|-------------|----------------------------|
| 53 | Waehrend der Besitzzeit angesetzte Vorabpauschalen (brutto) | none -- **not computed**, see below |

Per InvStG 19 Abs. 1 Satz 3-4 the sale gain is reduced by the gross (not TF-adjusted)
Vorabpauschalen assessed during the holding period **of the units disposed of**.

Anleitung zur Anlage KAP-INV 2024 and 2025, Zeile 53 (identical wording, read 2026-08-03):

> *"Um eine Doppelbesteuerung auszuschliessen, tragen Sie hier bitte die waehrend der Besitzzeit
> der veraeusserten Investmentanteile angesetzten Vorabpauschalen ein. Sie muessen diese vor
> Teilfreistellung angeben. Die Vorabpauschalen bei Investmentanteilen, die nicht dem
> inlaendischen Steuerabzug unterlegen haben, mindern den Veraeusserungsgewinn nur, soweit Sie
> diese Vorabpauschalen der Besteuerung unterworfen haben (Zeile 9 bis 13)."*

**Correction, 2026-08-03 (Validation Protocol items 4 and 8).** This section previously named
**Zeile 55** and an engine category `ANLAGE_KAP_INV_VORABPAUSCHALE_ABZUG_Z55`. That was wrong:
Zeile 55 is *"Gewinne aus der Veraeusserung von bestandsgeschuetzten Alt-Anteilen"*. The file
contradicted itself -- the detail-line table below already listed Zeile 53 correctly -- and the
engine implemented the wrong branch. The figure it emitted was additionally the wrong quantity:
the sum of the current tax year's gross Vorabpauschalen, rather than those accumulated over the
holding period of the units actually sold. The engine now emits no Zeile 53 figure and records a
data gap where fund units were disposed of. Mirrored corrections in
`investment-tax-law/invstg-19-veraeusserungsgewinne.md`,
`investment-tax-law/invstg-18-vorabpauschale.md` and `research/coverage-matrix.md`.

---

## Detail Lines for Individual Sales (Zeilen 46-56)

The Anleitung heads this block *"Zeile 46 bis 56 -- Ermittlung der Gewinne und Verluste aus der
Veraeusserung von Investmentanteilen"*. It is filled per individual sale.

| Zeile | Content |
|-------|---------|
| 49 | Anzahl der veraeusserten Anteile |
| 50 | Veraeusserungspreis |
| 51 | Anschaffungskosten (or the fiktive value at 01.01.2018 for Alt-Anteile) |
| 52 | Veraeusserungskosten |
| **53** | **Waehrend der Besitzzeit angesetzte Vorabpauschalen** (vor Teilfreistellung) |
| 54 | Veraeusserungsgewinn / -verlust |
| 55 | Gewinne aus der Veraeusserung von bestandsgeschuetzten Alt-Anteilen |
| 56 | Fiktiver Veraeusserungsgewinn / -verlust zum 31.12.2017 (nicht bestandsgeschuetzte Alt-Anteile) |

Z54 is transferred to the gain line (Z14/17/20/23/26) by fund type; Z55 is transferred to
Z15/18/21/24/27; Z56 to Z16/19/22/25/28.

---

## Gross Reporting Principle

All amounts on Anlage KAP-INV are GROSS (before Teilfreistellung).

**Why:** The Finanzamt applies the Teilfreistellung during assessment. The taxpayer reports the full unreduced amount. This is explicitly stated in the form instructions.

The Teilfreistellung rates (30%/15%/60%/80%/0%) are applied automatically by the tax office based on the fund type indicated.
