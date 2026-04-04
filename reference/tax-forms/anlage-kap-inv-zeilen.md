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

## Vorabpauschale Deduction on Sale

| Zeile | Description | Engine TaxReportingCategory |
|-------|-------------|----------------------------|
| 55 | Vorabpauschale deduction (accumulated during holding period) | `ANLAGE_KAP_INV_VORABPAUSCHALE_ABZUG_Z55` |

Per InvStG 19 Abs. 1 Satz 3-4: The sale gain is reduced by the gross (not TF-adjusted) accumulated Vorabpauschalen.

---

## Detail Lines for Individual Sales (Zeilen 49-56)

For each individual investment fund sale, the form requires:

| Zeile | Content |
|-------|---------|
| 49 | Anzahl der veraeusserten Anteile |
| 50 | Veraeusserungspreis |
| 51 | Anschaffungskosten |
| 52 | Veraeusserungskosten |
| 53 | Waehrend der Besitzzeit angesetzte Vorabpauschalen |
| 54 | Veraeusserungsgewinn/-verlust |
| 55 | Gain from pre-2018 units (if applicable) |
| 56 | Fiktiver Veraeusserungsgewinn zum 31.12.2017 (if applicable) |

The sum of Z54 entries is transferred to the appropriate gain line (Z14/17/20/23/26) by fund type.

---

## Gross Reporting Principle

All amounts on Anlage KAP-INV are GROSS (before Teilfreistellung).

**Why:** The Finanzamt applies the Teilfreistellung during assessment. The taxpayer reports the full unreduced amount. This is explicitly stated in the form instructions.

The Teilfreistellung rates (30%/15%/60%/80%/0%) are applied automatically by the tax office based on the fund type indicated.
