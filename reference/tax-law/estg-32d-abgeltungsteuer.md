# EStG 32d -- Gesonderter Steuertarif fuer Einkuenfte aus Kapitalvermoegen

## Source

- **Primary:** [gesetze-im-internet.de -- 32d EStG](https://www.gesetze-im-internet.de/estg/__32d.html)
- **With annotations:** [dejure.org -- 32d EStG](https://dejure.org/gesetze/EStG/32d.html)

## Relevance to Engine

Defines the flat tax rate (Abgeltungsteuer) and the Guenstigerpruefung option. The engine calculates gross figures; the actual tax rate application is handled by the Finanzamt.

---

## Abs. 1 -- Flat Tax Rate

The income tax on capital income that does not fall under 20 Abs. 8 EStG is **25 percent** (Abgeltungsteuer).

Plus Solidaritaetszuschlag (5.5% of tax = effective 1.375%) and optional Kirchensteuer.

**Effective rates:**
- Without Kirchensteuer: 26.375%
- With Kirchensteuer (8%): 27.819%
- With Kirchensteuer (9%): 27.995%

## Abs. 4 -- Guenstigerpruefung (Assessment at individual rate)

Upon request, capital income can be taxed at the individual income tax rate instead of the flat rate, if this results in lower tax. The tax office checks this automatically when the taxpayer files Anlage KAP.

## Abs. 5 -- Foreign Tax Credit

Foreign withholding tax can be credited against the German Abgeltungsteuer per 34c Abs. 1 EStG.

**Engine mapping:** `ANLAGE_KAP_FOREIGN_TAX_PAID` (Zeile 41) -- sum of all `WithholdingTaxEvent` amounts

---

## Not Directly Implemented

The engine computes pre-tax figures for the Steuererklaerung. It does not calculate the actual Abgeltungsteuer amount, as this depends on individual circumstances (Guenstigerpruefung, Sparerpauschbetrag, Kirchensteuer).
