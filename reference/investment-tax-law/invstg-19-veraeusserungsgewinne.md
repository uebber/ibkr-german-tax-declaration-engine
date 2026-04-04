# InvStG 19 -- Gewinne aus der Veraeusserung von Investmentanteilen

## Source

- **Primary:** [gesetze-im-internet.de -- 19 InvStG](https://www.gesetze-im-internet.de/invstg_2018/__19.html)

## Relevance to Engine

Defines how gains from the sale of investment fund units are calculated, particularly the deduction of previously assessed Vorabpauschalen.

---

## Abs. 1 -- Gain Calculation

For investment units NOT held in business assets (Betriebsvermoegen), 20 Abs. 4 EStG applies analogously.

**Key rule (Satz 3):** The gain is reduced by the Vorabpauschalen assessed during the holding period.

**Critical detail (Satz 4):** The Vorabpauschalen are deducted at their **full (gross) amount**, regardless of any Teilfreistellung that may have been applied under 20 InvStG.

```
Gain = Sale proceeds
     - Acquisition costs
     - Transaction costs
     - Sum of ALL gross Vorabpauschalen during holding period
```

**20 Abs. 4a EStG does NOT apply** (Satz 2) -- corporate action rollover rules for shares do not apply to investment fund units.

---

## Abs. 2 -- Deemed Sale

If an investment fund no longer falls within the scope of InvStG, its units are deemed sold. The deemed sale price is the fair market value (gemeiner Wert) at the point the fund exits the scope.

---

## Engine Mapping

The engine tracks accumulated Vorabpauschalen per fund position lot and deducts them from the sale gain at the gross (pre-Teilfreistellung) amount. The result is reported on Anlage KAP-INV as a gross figure (Zeilen 14/17/20/23/26 by fund type).

The accumulated Vorabpauschale deduction itself is reported on **Zeile 55** of Anlage KAP-INV.
