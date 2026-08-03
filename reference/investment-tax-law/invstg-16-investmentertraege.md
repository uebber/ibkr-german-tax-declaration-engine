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

### How Investmentertraege enter the EStG

**Via 20 Abs. 1 Nr. 3 EStG**, which reads in full: *"Investmentertraege nach § 16 des
Investmentsteuergesetzes"*. Fund income is therefore Einkuenfte aus Kapitalvermoegen, and the
Abgeltungsteuer machinery of 32d and the loss offsetting of 20 Abs. 6 apply to it. (20 Abs. 1
Nr. 3a is the parallel hook for Spezial-Investmentertraege nach § 34 InvStG -- out of scope.)

> **Correction, 2026-08-03.** This section previously claimed *"20 Abs. 1 Nr. 1, 2, and Nr. 3
> EStG do NOT apply to investment fund income"*. That is backwards for Nr. 3, which is precisely
> the provision that makes fund income taxable as capital income, and § 16 InvStG contains no
> such exclusion at all. Both texts retrieved 2026-08-03 from gesetze-im-internet.de
> (`estg/__20.html`, `invstg_2018/__16.html`).

### Abs. 3 -- Genuine exclusion

*"Auf Investmentertraege aus Investmentfonds sind § 3 Nummer 40 des Einkommensteuergesetzes und
§ 8b des Koerperschaftsteuergesetzes nicht anzuwenden."* So no Teileinkuenfteverfahren and no
8b KStG relief; the Teilfreistellung of 20 InvStG takes their place.

### Abs. 2 and Abs. 4 -- present, out of scope

Abs. 2 disapplies Investmentertraege for certified Altersvorsorge-/Basisrentenvertraege, and
Vorabpauschalen for units held in betriebliche Altersvorsorge, by insurers under certain
20 Abs. 1 Nr. 6 contracts, and for Alterungsrueckstellungen. Abs. 4 conditions DBA-Freistellung
of a foreign fund's distribution on the fund bearing general income taxation and on more than
50 percent of the distribution resting on non-exempt income. Neither is reachable from this
engine's inputs. Recorded per Validation Protocol item 2.

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
