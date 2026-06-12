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

At a fund disposal the engine reduces the realized gain (`RealizedGainLoss.gross_gain_loss_eur`)
by the gross (pre-Teilfreistellung) Vorabpauschalen assessed during the holding period of the
**sold units**, computed **per lot, FIFO**: for each year-end the lot was held, the units' share
of that year's VP is `declared_VP[year] / units_held_at_year_end` (`src/processing/
vp_disposal_deduction.py`). A full exit reduces to `Σ declared_VP[year]`.

**Only-if-declared cap (Z53, form instructions):** the deduction is limited to VP the user
actually subjected to taxation in prior years (Anlage KAP-INV Z9-13). Three years are distinct:
holding year **HY**, assessment year **VZ = HY+1** (where VP(HY) is declared, §18 Abs. 3), and
filing year HY+2. The engine's `--tax-year` is the VZ (= **V**). For a fund disposed in V,
`src/processing/declared_vp_resolution.py`:
- **Holding year V-1** — the engine **computes** this VP itself (it is the figure on Z9-13 of
  *this* return), **auto-enters it** into `cache/declared_vp.json` and the deduction, and never
  prompts. So even a non-interactive run deducts it.
- **Holding years ≤ V-2** — declared on prior returns and not recomputable (no historical NAVs),
  so prompted once (cached) via `DeclaredVpProvider`, labeled by holding year with a pointer to
  *Steuererklärung HY+1*. Years not declared (0) are not deducted (conservative).

The reduced gain is reported **as the net (vor Teilfreistellung) figure on Anlage KAP-INV
Zeilen 14/17/20/23/26** (Aufstellung mode) — there is **no separate deduction line**. The
deducted amount is retained on `RealizedGainLoss.vp_deduction_eur` for the PDF breakdown.

> Note: form **Zeile 55 is NOT the VP deduction** — it is "Gewinne aus bestandsgeschützten
> Alt-Anteilen". The VP deduction lives in the per-sale Ermittlung (Zeile 53), folded into
> the Z14-26 figure.
