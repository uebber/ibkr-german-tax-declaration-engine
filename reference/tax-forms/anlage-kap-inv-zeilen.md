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

Note: Lines 15-16, 18-19, 21-22, 24-25, 27-28 are used for transitional rules (Uebergangsregelungen) for pre-2018 fund units (bestandsgeschuetzte Alt-Anteile under InvStG 56).

---

## Vorabpauschale Deduction on Sale (§19 Abs. 1 S. 3-4)

The deduction of the Vorabpauschalen assessed during the holding period is **Zeile 53**
("Während der Besitzzeit angesetzte Vorabpauschalen"), inside the per-sale Ermittlung
(Z46-54). It is at the **gross** (pre-Teilfreistellung) amount, and **only to the extent the
VP was actually subjected to taxation in the prior years (Z9-13)** — i.e. the *declared* VP.
It is **not** a separate aggregate line: it is subtracted within the worksheet so the gain
transferred to Z14-26 is already **net of VP** (still gross of Teilfreistellung).

> **Z55 is NOT the VP deduction.** Z55 = "Gewinne aus der Veräußerung von bestandsgeschützten
> Alt-Anteilen" (pre-2009 units, §56 Abs. 6). The engine category
> `ANLAGE_KAP_INV_VORABPAUSCHALE_ABZUG_Z55` is a legacy misnomer and is no longer populated.

---

## Detail Lines for Individual Sales — Ermittlung der Veräußerung (Zeilen 46-54)

Per fund, **per acquisition tranche (own column), FIFO** (zuerst angeschaffte Anteile zuerst
veräußert). Filled when the units did not undergo German inländischer Steuerabzug (foreign
custody, e.g. IBKR), unless a broker Aufstellung of the gains is available — then the **net
gain is entered directly on Z14-26**.

| Zeile | Content |
|-------|---------|
| 50 | Veräußerungspreis |
| 51 | Anschaffungskosten |
| 52 | Veräußerungskosten |
| 53 | Während der Besitzzeit angesetzte Vorabpauschalen (gross; deductible only if declared) |
| 54 | Veräußerungsgewinn/-verlust (= Z50 − Z51 − Z52 − Z53) → transferred to Z14/17/20/23/26 |
| 55 | Gewinne aus bestandsgeschützten Alt-Anteilen (pre-2009 units) |
| 56 | Fiktiver Veräußerungsgewinn zum 31.12.2017 (nicht bestandsgeschützte Alt-Anteile) |

The Z54 result (net of VP, gross of Teilfreistellung) is transferred to the aggregate gain
line (Z14/17/20/23/26) by fund type.

### Engine Mapping

The engine emits the **net §19 gain directly on Z14-26** (Aufstellung mode): each fund
`RealizedGainLoss.gross_gain_loss_eur` is reduced at disposal by the per-lot FIFO held-period
VP (`src/processing/vp_disposal_deduction.py`), capped at the user-declared VP per year
(`DeclaredVpProvider`, `cache/declared_vp.json`). The deducted amount is retained as
`RealizedGainLoss.vp_deduction_eur` for the PDF Aufstellung (§3.3 columns: G/V vor VP,
VP-Abzug, G/V brutto n. VP). Teilfreistellung is applied by the Finanzamt afterward.

---

## Gross Reporting Principle

All amounts on Anlage KAP-INV are GROSS (before Teilfreistellung).

**Why:** The Finanzamt applies the Teilfreistellung during assessment. The taxpayer reports the full unreduced amount. This is explicitly stated in the form instructions.

The Teilfreistellung rates (30%/15%/60%/80%/0%) are applied automatically by the tax office based on the fund type indicated.
