# InvStG 16 -- Investmentertraege

## Source

- **Primary:** [gesetze-im-internet.de -- 16 InvStG](https://www.gesetze-im-internet.de/invstg_2018/__16.html)
- **Full law:** [gesetze-im-internet.de -- InvStG](https://www.gesetze-im-internet.de/invstg_2018/)

## Relevance to Engine

Defines what constitutes taxable investment fund income. The engine processes fund distributions and sale gains under this framework.

---

## Abs. 1 -- Definition of Investmentertraege

Investment income comprises:

1. **Ausschuettungen** (distributions) of an investment fund under 2 Abs. 11 InvStG
2. **Vorabpauschalen** under 18 InvStG
3. **Gewinne aus der Veraeusserung** (gains from sale) of investment units under 19 InvStG

### Key exclusion
20 Abs. 1 Nr. 1, 2, and Nr. 3 EStG do NOT apply to investment fund income. Instead, investment fund distributions are taxed exclusively under InvStG (opaque taxation principle since 2018 reform).

3 Nr. 40 EStG (Teileinkuenfteverfahren) and 8b KStG do NOT apply to Investmentertraege.

---

## Engine Mapping

| InvStG 16 Component | Engine Event Type | Tax Reporting Category |
|----------------------|-------------------|------------------------|
| Ausschuettungen | `DISTRIBUTION_FUND` | `ANLAGE_KAP_INV_*_AUSSCHUETTUNG_GROSS` |
| Vorabpauschale | (calculated) | `ANLAGE_KAP_INV_*_VORABPAUSCHALE_BRUTTO` |
| Veraeusserungsgewinn | `LONG_POSITION_SALE` (for INVESTMENT_FUND) | `ANLAGE_KAP_INV_*_GEWINN_GROSS` |

The asterisk (*) represents the fund type: AKTIENFONDS, MISCHFONDS, IMMOBILIENFONDS, AUSLANDS_IMMOBILIENFONDS, SONSTIGE_FONDS.

---

## Reporting Principle

All amounts are reported as **GROSS** (brutto, before Teilfreistellung) on Anlage KAP-INV. The Teilfreistellung is applied by the Finanzamt during assessment, not by the taxpayer on the form.

**Source for this principle:** Anlage KAP-INV form instructions (see reference/Anltg_KAP_INV_24.md)
