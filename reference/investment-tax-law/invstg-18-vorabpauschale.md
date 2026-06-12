# InvStG 18 -- Vorabpauschale

## Source

- **Primary:** [gesetze-im-internet.de -- 18 InvStG](https://www.gesetze-im-internet.de/invstg_2018/__18.html)
- **With version history:** [buzer.de -- 18 InvStG](https://www.buzer.de/18_InvStG.htm)
- **Basiszins 2024:** [BMF-Schreiben 10.01.2025 (PDF)](https://www.bundesfinanzministerium.de/Content/DE/Downloads/BMF_Schreiben/Steuerarten/Investmentsteuer/2025-01-10-basiszins-vorabpauschale-zum-2-1-2025.pdf?__blob=publicationFile&v=7)
- **Basiszins 2025:** Same BMF source (published January 2025)
- **Basiszins 2026:** [BMF-Schreiben 13.01.2026 (PDF)](https://www.bundesfinanzministerium.de/Content/DE/Downloads/BMF_Schreiben/Steuerarten/Investmentsteuer/2026-01-13-basiszins-berechnung-vorabpauschale.pdf?__blob=publicationFile&v=3)

## Relevance to Engine

The Vorabpauschale is an annual deemed minimum income for investment fund units. The engine calculates this based on start-of-year (SoY) position values and the published Basiszins.

---

## Abs. 1 -- Definition

The Vorabpauschale is the amount by which the distributions of an investment fund in a calendar year fall short of the Basisertrag (base return) for that year.

**Formula:**
```
Vorabpauschale = max(0, Basisertrag - Ausschuettungen)
```

If distributions exceed the Basisertrag, the Vorabpauschale is zero.

## Abs. 2 -- Basisertrag (Base Return)

```
Basisertrag = Ruecknahmepreis_SoY x Basiszins x 0.70
```

The Basisertrag is capped at the actual value increase plus distributions:
```
Basisertrag <= (Ruecknahmepreis_EoY - Ruecknahmepreis_SoY) + Ausschuettungen
```

If the fund lost value and distributions don't compensate, the Basisertrag can be zero.

**Engine note:** `Ruecknahmepreis_SoY` = start-of-year NAV per unit, stored as SoY position data.

## Abs. 2 Satz 2 -- Partial Year Acquisition

In the year of acquisition, the Vorabpauschale is reduced by 1/12 for each full month preceding the month of acquisition (acquisition in month M -> retained fraction (13 - M)/12). The Basisertrag is computed on the **year-start** redemption price for *all* units, regardless of when they were bought; only the 1/12 reduction reflects the partial holding.

**Engine implementation:** Implemented (multi-tranche). The units held at year-end are read from the FIFO ledger; each lot acquired in a prior year keeps factor 1, each lot acquired in month M of the tax year keeps (13 - M)/12, and the units-weighted factor is applied to the fund-level gross Vorabpauschale (equivalent to the per-lot sum, since all units share the year-start NAV). The year-start NAV per unit comes from the SoY position (`soy_market_price`) when the fund was held on 1 Jan, otherwise from a user-supplied value resolved interactively and cached (`processing/vp_nav_resolution.py`, `identification/fund_soy_nav_provider.py`); in non-interactive runs a missing NAV aborts the run (fail-fast). **Known limitation:** distributions and the value-gain cap are applied at fund level, so apportioning distributions across lots acquired before vs. after a distribution date is not modelled (a rare edge case).

## Abs. 4 -- Basiszins Determination

The Basiszins is derived from the long-term achievable yield of public bonds (oeffentliche Anleihen). The Deutsche Bundesbank calculates this rate from yield curve data (Zinsstrukturdaten) as of the first trading day of the year. The BMF publishes the rate in the Bundessteuerblatt.

### Published Basiszins Values

| Year | Basiszins | Effective Basisertrag Factor (x 0.7) | BMF Publication |
|------|-----------|---------------------------------------|-----------------|
| 2024 | 2.29% | 1.603% | BStBl I, BMF 02.01.2024 |
| 2025 | 2.53% | 1.771% | BStBl I, BMF 10.01.2025 |
| 2026 | 3.20% | 2.240% | BStBl I, BMF 13.01.2026 |

Historical note: In 2021 and 2022, the Basiszins was negative, resulting in zero Vorabpauschale for those years.

## Deemed Receipt Date and Assessment Year (Abs. 3)

**§18 Abs. 3 InvStG (verbatim):** „Die Vorabpauschale gilt am ersten Werktag des folgenden Kalenderjahres als zugeflossen."

The Vorabpauschale computed *for* calendar year X is deemed received (zugeflossen) on the **first business day of year X+1**. By the §11 EStG Zuflussprinzip (income is taxed in the year it flows), it is therefore income of year **X+1** and is declared on the **X+1** Anlage KAP-INV — not the year-X return.

Example: the **2024** Vorabpauschale is deemed received on **02.01.2025**, taxed in VZ 2025, and appears on the **2025** Anlage KAP-INV (and the 2025 Steuerbescheinigung). Equivalently, the **2025** Vorabpauschale (computed from 2025 NAVs/Basiszins) flows **02.01.2026** and belongs on the **2026** return.

**Engine mapping:** a Vorabpauschale computed from tax-year-X data carries `deemed_inflow_year = X+1` and is reported as income of the X+1 assessment; the year-X Anlage KAP-INV lines carry the year-(X-1) Vorabpauschale (the amount that flowed on the first business day of year X).

---

## Engine Mapping

| Component | Engine Field | Form Line |
|-----------|-------------|-----------|
| Vorabpauschale (gross) | `VorabpauschaleData.gross_vorabpauschale_eur` | Zeile 9-13 (by fund type) |
| VP deduction on sale | `RealizedGainLoss.vp_deduction_eur` (folded into the gain) | Z53 worksheet → net Z14-26 |

**InvStG 19 Abs. 1 Satz 3:** The sale gain is reduced by the gross (pre-Teilfreistellung)
Vorabpauschalen assessed during the holding period. The engine subtracts this from the disposal
gain so the **net figure is reported on Z14-26** (Aufstellung; the per-sale Z53 line) — it is **not**
a separate "Z55" line (Z55 = bestandsgeschützte Alt-Anteile). See
`invstg-19-veraeusserungsgewinne.md` for the full mechanism (FIFO per-unit, only-if-declared cap,
auto-computed current holding year).
