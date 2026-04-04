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

## Abs. 3 -- Partial Year Acquisition

In the year of acquisition, the Vorabpauschale is reduced by 1/12 for each full month preceding the month of acquisition.

**Engine implementation:** Pro-rata reduction based on acquisition month.

## Abs. 4 -- Basiszins Determination

The Basiszins is derived from the long-term achievable yield of public bonds (oeffentliche Anleihen). The Deutsche Bundesbank calculates this rate from yield curve data (Zinsstrukturdaten) as of the first trading day of the year. The BMF publishes the rate in the Bundessteuerblatt.

### Published Basiszins Values

| Year | Basiszins | Effective Basisertrag Factor (x 0.7) | BMF Publication |
|------|-----------|---------------------------------------|-----------------|
| 2024 | 2.29% | 1.603% | BStBl I, BMF 02.01.2024 |
| 2025 | 2.53% | 1.771% | BStBl I, BMF 10.01.2025 |
| 2026 | 3.20% | 2.240% | BStBl I, BMF 13.01.2026 |

Historical note: In 2021 and 2022, the Basiszins was negative, resulting in zero Vorabpauschale for those years.

## Deemed Receipt Date

The Vorabpauschale is deemed received (zugeflossen) on the **first business day of the following calendar year** (Abs. 1 Satz 3).

Example: 2024 Vorabpauschale is deemed received on 02.01.2025.

---

## Engine Mapping

| Component | Engine Field | Form Line |
|-----------|-------------|-----------|
| Vorabpauschale (gross) | `VorabpauschaleData.gross_vorabpauschale_eur` | Zeile 9-13 (by fund type) |
| VP deduction on sale | `RealizedGainLoss.accumulated_vorabpauschale` | Zeile 55 |

**InvStG 19 Abs. 1 Satz 3:** The sale gain is reduced by accumulated Vorabpauschalen assessed during the holding period. These are deducted at full (gross) amount, irrespective of any Teilfreistellung that may have applied.
