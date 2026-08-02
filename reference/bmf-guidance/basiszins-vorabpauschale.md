# BMF: Basiszins zur Berechnung der Vorabpauschale

## Source

- **Legal basis:** InvStG 18 Abs. 4; regime start InvStG 56 Abs. 1 Satz 1
- **Basiszins zum 02.01.2025 (2.53%):** [BMF-Schreiben 10.01.2025, GZ IV C 1 - S 1980/00230/009/002 (PDF)](https://www.bundesfinanzministerium.de/Content/DE/Downloads/BMF_Schreiben/Steuerarten/Investmentsteuer/2025-01-10-basiszins-vorabpauschale-zum-2-1-2025.pdf?__blob=publicationFile&v=7)
- **Basiszins zum 02.01.2026 (3.20%):** [BMF-Schreiben 13.01.2026, GZ IV C 1 - S 1980/00230/012/001 (PDF)](https://www.bundesfinanzministerium.de/Content/DE/Downloads/BMF_Schreiben/Steuerarten/Investmentsteuer/2026-01-13-basiszins-berechnung-vorabpauschale.pdf?__blob=publicationFile&v=3)
- **Archive:** the BMF Investmentsteuer download page carries only the two most recent
  Schreiben (checked 2026-08-02). Earlier years must be cited from BStBl I -- see the
  per-year column in the table below.

## Relevance to Engine

The Basiszins is a required input for the Vorabpauschale calculation. It is published
annually by the BMF and lives in the law-as-data registry `src/tax_law/registry.py`
(`BASISZINS_PCT`) -- it is law, not user configuration.

---

## Which year's Basiszins belongs in which return

This is the single most error-prone part of the Vorabpauschale, so it is stated before the
table:

```
Basiszins as of 02.01.X   ->   Vorabpauschale FOR calendar year X
                          ->   deemed to flow on the first working day of X+1 (18 Abs. 3 InvStG)
                          ->   taxable, and declared on Anlage KAP-INV, in VZ X+1
```

Worked example: the Vorabpauschale on the **2025** Anlage KAP-INV is the one computed for
calendar **2024** -- Basiszins 2.29%, Ruecknahmepreis as of 01.01.2024, capped by the 2024
value gain, reduced by 2024 distributions. The 2.53% rate published on 10.01.2025 first
appears on the **2026** return.

See `reference/investment-tax-law/invstg-18-vorabpauschale.md` for the verbatim
18 Abs. 3 InvStG text and the Zuflussprinzip reasoning.

---

## Published Basiszins Values (18 Abs. 4 InvStG)

The series **starts with 2018**. The Vorabpauschale was introduced by the InvStG 2018,
whose provisions *"sind ab dem 1. Januar 2018 anzuwenden"* (**56 Abs. 1 Satz 1 InvStG**,
gesetze-im-internet.de, retrieved 2026-08-02). The first Basiszins notice is the
BMF-Schreiben vom 04.01.2018; the first Vorabpauschale is the one for calendar 2018,
deemed to flow on 02.01.2019 and declared in VZ 2019.

| Calendar Year | Basiszins | Reference Date | Effective Basisertrag Factor | BMF-Schreiben / Fundstelle |
|---------------|-----------|----------------|------------------------------|----------------------------|
| 2018 | 0.87% | 02.01.2018 | 0.609% | BMF 04.01.2018, BStBl I |
| 2019 | 0.52% | 02.01.2019 | 0.364% | BMF 09.01.2019, BStBl I 2019 S. 58 |
| 2020 | 0.07% | 02.01.2020 | 0.049% | BMF 29.01.2020, IV C 1 - S 1980-1/19/10038 :001, BStBl I 2020 S. 218 |
| 2021 | -0.45% | 04.01.2021 | negative -> 0 | BMF 06.01.2021, BStBl I |
| 2022 | -0.05% | 03.01.2022 | negative -> 0 | BMF 07.01.2022, BStBl I |
| 2023 | 2.55% | 02.01.2023 | 1.785% | BMF 04.01.2023, IV C 1 - S 1980-1/19/10038 :007, BStBl I |
| 2024 | 2.29% | 02.01.2024 | 1.603% | BMF 05.01.2024, IV C 1 - S 1980-1/19/10038 :008, BStBl I 2024 S. 154 |
| 2025 | 2.53% | 02.01.2025 | 1.771% | BMF 10.01.2025, IV C 1 - S 1980/00230/009/002, BStBl I |
| 2026 | 3.20% | 02.01.2026 | 2.240% | BMF 13.01.2026, IV C 1 - S 1980/00230/012/001, BStBl I |

**Verification status (2026-08-02).** The 2025 and 2026 rates are read off the BMF PDFs
linked above (Tier 2, primary). The 2018-2024 rates and their Schreiben dates were
recovered from secondary tax-press summaries because the BMF site no longer hosts those
PDFs; the values are mutually consistent across independent summaries, and the 2024 entry
carries a BStBl page cited by the BMF itself. **Gap, recorded deliberately:** for
2018-2023 no Tier 1/2 document was retrieved in full. Before an engine figure for VZ 2019-2024
is filed, confirm the year's rate against BStBl I or the taxpayer's Steuerbescheinigung.

### Not a Basiszins under 18 Abs. 4 InvStG: 2016 and 2017

Earlier revisions of this file listed *2016 = 1.10%* and *2017 = 0.59%*. Those are the
Basiszins values for the **vereinfachtes Ertragswertverfahren nach 203 Abs. 2 BewG**
(1.10% per BMF-Schreiben vom 04.01.2016, IV C 7 - S 3102/07/10001, for Bewertungsstichtage
from 01.01.2016; 0.59% computed on 02.01.2017 and carried in OFD-Verfuegungen) -- a
different statute, a different purpose. They match the BewG series' reference dates
(04.01.2016 / 02.01.2017), which is how the mix-up was found. The Vorabpauschale did not
exist in 2016 or 2017, and no 18 Abs. 4 InvStG Basiszins was ever published for those
years. **Both rows removed; do not restore them.**

---

## Determination Method

Per InvStG 18 Abs. 4:

1. The Deutsche Bundesbank calculates the yield from its yield curve data (Zinsstrukturdaten) for the first trading day of each year
2. The yield used is for Bundeswertpapiere (federal bonds) with annual coupon payment and 15-year residual maturity
3. The BMF publishes this rate in the Bundessteuerblatt Teil I

---

## Engine Configuration

In the law-as-data registry `src/tax_law/registry.py` — the published table 2018-2026,
values in percent as Decimals (`BASISZINS_PCT`). The registry is the single source the
engine AND the tests read.

A year MISSING from the table makes the engine skip the Vorabpauschale (it cannot invent a
rate). The two cases are distinguished, because they mean opposite things:

- year **before 2018** — no Vorabpauschale existed (56 Abs. 1 S. 1 InvStG). Logged at INFO;
  nothing is being missed.
- year **2018 or later** — a rate was published and is not in the table. Logged as a
  WARNING: skipping would understate deemed income.

`tests/test_tax_law_registry.py::TestBasiszinsReferenceConsistency` parses the table in
**this file** and asserts the registry matches it row for row, so the two cannot drift.

**Maintenance:** Add the new rate annually after the BMF publication (typically January),
here AND in `src/tax_law/registry.py`. The test fails until both are updated.
