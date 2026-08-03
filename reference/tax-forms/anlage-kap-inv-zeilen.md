# Anlage KAP-INV -- Zeilenreferenz

## Source

- **2024 Form:** [formulare-bfinv.de -- Anlage KAP-INV 2024](https://www.formulare-bfinv.de/ffw/action/invoke.do?id=035004_24)
- **2024 Instructions:** Already in repository: `reference/Anltg_KAP_INV_24.md`
- **2025 Instructions:** Already in repository: `reference/Anltg_KAP_INV_25.md`
- **Legal basis:** InvStG 16, 18, 19, 20

## Scope

Which fund event goes on which line of Anlage KAP-INV. All amounts are entered GROSS (brutto,
before Teilfreistellung) -- see [GT-FORM-034].

The form is organised by **fund type**, in the same order in every block: Aktienfonds,
Mischfonds, Immobilienfonds, Auslands-Immobilienfonds, Sonstige Fonds. The type determines the
Teilfreistellung the Finanzamt then applies
([`../investment-tax-law/invstg-20-teilfreistellung.md`](../investment-tax-law/invstg-20-teilfreistellung.md)).

---

## [GT-FORM-030] Zeilen 4-8 -- Ausschuettungen (brutto)

| Zeile | Fund type |
|-------|-----------|
| 4 | Aktienfonds |
| 5 | Mischfonds |
| 6 | Immobilienfonds |
| 7 | Auslands-Immobilienfonds |
| 8 | Sonstige Fonds |

---

## [GT-FORM-031] Zeilen 9-13 -- Vorabpauschale (brutto)

**These take the Vorabpauschale for the *preceding* calendar year.** Zeilen 9-13 of the VZ `Y`
form take *"die Ihnen im Jahr `Y` als zugeflossen geltenden Vorabpauschalen"*, and the
Vorabpauschale for `Y-1` is deemed to flow on the first working day of `Y` (18 Abs. 3 InvStG).
The 2024 Anleitung says it outright: *"Die Vorabpauschale fuer 2023 gilt am 2. Januar 2024 als
zugeflossen."* See `investment-tax-law/invstg-18-vorabpauschale.md`.

| Zeile | Fund type |
|-------|-----------|
| 9 | Aktienfonds |
| 10 | Mischfonds |
| 11 | Immobilienfonds |
| 12 | Auslands-Immobilienfonds |
| 13 | Sonstige Fonds |

---

## [GT-FORM-032] Zeilen 14/17/20/23/26 -- Veraeusserungsgewinn und -verlust (brutto)

| Zeile | Fund type |
|-------|-----------|
| 14 | Aktienfonds |
| 17 | Mischfonds |
| 20 | Immobilienfonds |
| 23 | Auslands-Immobilienfonds |
| 26 | Sonstige Fonds |

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

Both require data from before the InvStG 2018 regime began -- an acquisition date before
01.01.2009 for the bestandsgeschuetzte case, and a 31.12.2017 valuation for the fiktive
Veraeusserung.

---

## [GT-FORM-033] Zeile 53 -- Vorabpauschale deduction on disposal

Per 19 Abs. 1 Saetze 3-4 InvStG the disposal gain is reduced by the gross (pre-Teilfreistellung)
Vorabpauschalen assessed during the holding period **of the units disposed of**.

Anleitung zur Anlage KAP-INV 2024 and 2025, Zeile 53 (identical wording, read 2026-08-03):

> *"Um eine Doppelbesteuerung auszuschliessen, tragen Sie hier bitte die waehrend der Besitzzeit
> der veraeusserten Investmentanteile angesetzten Vorabpauschalen ein. Sie muessen diese vor
> Teilfreistellung angeben. Die Vorabpauschalen bei Investmentanteilen, die nicht dem
> inlaendischen Steuerabzug unterlegen haben, mindern den Veraeusserungsgewinn nur, soweit Sie
> diese Vorabpauschalen der Besteuerung unterworfen haben (Zeile 9 bis 13)."*

**Correction, 2026-08-03 (Validation Protocol items 4 and 8).** This section previously named
**Zeile 55**. That was wrong: Zeile 55 is *"Gewinne aus der Veraeusserung von
bestandsgeschuetzten Alt-Anteilen"*. The file contradicted itself -- the detail-line table below
already listed Zeile 53 correctly. Mirrored corrections in
`../investment-tax-law/invstg-19-veraeusserungsgewinne.md`,
`../investment-tax-law/invstg-18-vorabpauschale.md` and `../research/coverage-matrix.md`.

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

## [GT-FORM-034] Gross reporting principle

Every amount on Anlage KAP-INV is entered **gross**, before Teilfreistellung. The Finanzamt
applies the Teilfreistellung during the assessment, deriving the rate from the fund type the
line itself indicates. This is why the form is organised by fund type at all: the line number
*is* the rate declaration.

The rates are stated once in the library, in
[`../investment-tax-law/invstg-20-teilfreistellung.md`](../investment-tax-law/invstg-20-teilfreistellung.md);
they are deliberately not repeated here.
