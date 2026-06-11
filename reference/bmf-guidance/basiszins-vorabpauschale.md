# BMF: Basiszins zur Berechnung der Vorabpauschale

## Source

- **2024 Basiszins:** [BMF-Schreiben 10.01.2025 (PDF)](https://www.bundesfinanzministerium.de/Content/DE/Downloads/BMF_Schreiben/Steuerarten/Investmentsteuer/2025-01-10-basiszins-vorabpauschale-zum-2-1-2025.pdf?__blob=publicationFile&v=7)
- **2026 Basiszins:** [BMF-Schreiben 13.01.2026 (PDF)](https://www.bundesfinanzministerium.de/Content/DE/Downloads/BMF_Schreiben/Steuerarten/Investmentsteuer/2026-01-13-basiszins-berechnung-vorabpauschale.pdf?__blob=publicationFile&v=3)
- **Legal basis:** InvStG 18 Abs. 4

## Relevance to Engine

The Basiszins is a required input for the Vorabpauschale calculation. It is published annually by BMF and stored in `src/config.py` as `BASISZINS_BY_YEAR`.

---

## Published Basiszins Values

| Calendar Year | Basiszins | Reference Date | Effective Basisertrag Factor | Publication |
|---------------|-----------|----------------|------------------------------|-------------|
| 2016 | 1.10% | 04.01.2016 | 0.770% | BStBl I |
| 2017 | 0.59% | 02.01.2017 | 0.413% | BStBl I |
| 2018 | 0.87% | 02.01.2018 | 0.609% | BStBl I |
| 2019 | 0.52% | 02.01.2019 | 0.364% | BStBl I |
| 2020 | 0.07% | 02.01.2020 | 0.049% | BStBl I |
| 2021 | -0.45% | 04.01.2021 | negative -> 0 | BStBl I |
| 2022 | -0.05% | 03.01.2022 | negative -> 0 | BStBl I |
| 2023 | 2.55% | 02.01.2023 | 1.785% | BStBl I |
| 2024 | 2.29% | 02.01.2024 | 1.603% | BStBl I |
| 2025 | 2.53% | 02.01.2025 | 1.771% | BStBl I |
| 2026 | 3.20% | 02.01.2026 | 2.240% | BStBl I |

---

## Determination Method

Per InvStG 18 Abs. 4:

1. The Deutsche Bundesbank calculates the yield from its yield curve data (Zinsstrukturdaten) for the first trading day of each year
2. The yield used is for Bundeswertpapiere (federal bonds) with annual coupon payment and 15-year residual maturity
3. The BMF publishes this rate in the Bundessteuerblatt Teil I

---

## Engine Configuration

In the law-as-data registry `src/tax_law/registry.py` — the COMPLETE published
table 2016-2026, values in percent as Decimals (`BASISZINS_PCT`). The registry
is the single source the engine AND the tests read; it is law, not user
configuration (it no longer lives in `src/config.py`).

A tax year MISSING from the table makes the engine skip the Vorabpauschale with
a WARNING (it cannot invent a rate); for a year with a positive published
Basiszins that skip would understate deemed income — keep the table complete.
`tests/test_vorabpauschale.py::TestBasiszinsTable` and
`tests/test_tax_law_registry.py` assert the registry matches this document.

**Maintenance:** Add the new rate annually after the BMF publication (typically
January), here AND in `src/tax_law/registry.py`.
