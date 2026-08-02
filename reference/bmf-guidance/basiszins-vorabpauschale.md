# BMF: Basiszins zur Berechnung der Vorabpauschale

## Source

- **Legal basis:** InvStG 18 Abs. 4; regime start InvStG 56 Abs. 1 Satz 1
- **Basiszins zum 02.01.2025 (2.53%):** [BMF-Schreiben 10.01.2025, GZ IV C 1 - S 1980/00230/009/002 (PDF)](https://www.bundesfinanzministerium.de/Content/DE/Downloads/BMF_Schreiben/Steuerarten/Investmentsteuer/2025-01-10-basiszins-vorabpauschale-zum-2-1-2025.pdf?__blob=publicationFile&v=7)
- **Basiszins zum 02.01.2026 (3.20%):** [BMF-Schreiben 13.01.2026, GZ IV C 1 - S 1980/00230/012/001 (PDF)](https://www.bundesfinanzministerium.de/Content/DE/Downloads/BMF_Schreiben/Steuerarten/Investmentsteuer/2026-01-13-basiszins-berechnung-vorabpauschale.pdf?__blob=publicationFile&v=3)
- **2018-2024:** the BMF Investmentsteuer download page carries only the two most recent
  Schreiben (checked 2026-08-02). The earlier Schreiben were retrieved as archived copies of
  the original BMF PDFs (Internet Archive snapshots of
  `bundesfinanzministerium.de/Content/DE/Downloads/BMF_Schreiben/Steuerarten/Investmentsteuer/`),
  plus the 2019 letter from the BVL mirror. Each was read in full; their GZ, date, value and
  BStBl citation are in the table below.

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

The BMF states this in every annual Schreiben. Verbatim from the 05.01.2024 letter
(GZ IV C 1 - S 1980-1/19/10038 :008):

> *"Die Vorabpauschale fuer 2024 gilt gemaess § 18 Absatz 3 InvStG beim Anleger als am
> ersten Werktag des folgenden Kalenderjahres - also am 2. Januar 2025 - zugeflossen. Die
> Vorabpauschale fuer 2024 ist unter Anwendung des Basiszinses vom 2. Januar 2024 zu
> ermitteln."*

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

| Calendar Year | Basiszins | Reference Date | Effective Basisertrag Factor | BMF-Schreiben | GZ | Fundstelle |
|------|--------|------------|------------|------------|------------|------------|
| 2018 | 0.87% | 02.01.2018 | 0.609% | 04.01.2018 | IV C 1 - S 1980-1/14/10001 :038 | BStBl I 2018 S. 249 |
| 2019 | 0.52% | 02.01.2019 | 0.364% | 09.01.2019 | IV C 1 - S 1980-1/14/10001 :038 | BStBl I 2019 S. 58 |
| 2020 | 0.07% | 02.01.2020 | 0.049% | 29.01.2020 | IV C 1 - S 1980-1/19/10038 :001 | BStBl I 2020 S. 218 |
| 2021 | -0.45% | 04.01.2021 | negative -> 0 | 06.01.2021 | IV C 1 - S 1980-1/19/10038 :004 | BStBl I 2021 S. 56 |
| 2022 | -0.05% | 03.01.2022 | negative -> 0 | 07.01.2022 | IV C 1 - S 1980-1/19/10038 :005 | BStBl I 2022 S. 122 |
| 2023 | 2.55% | 02.01.2023 | 1.785% | 04.01.2023 | IV C 1 - S 1980-1/19/10038 :007 | BStBl I 2023 S. 178 |
| 2024 | 2.29% | 02.01.2024 | 1.603% | 05.01.2024 | IV C 1 - S 1980-1/19/10038 :008 | BStBl I 2024 S. 154 |
| 2025 | 2.53% | 02.01.2025 | 1.771% | 10.01.2025 | IV C 1 - S 1980/00230/009/002 | BStBl I |
| 2026 | 3.20% | 02.01.2026 | 2.240% | 13.01.2026 | IV C 1 - S 1980/00230/012/001 | BStBl I |

**Verification status (2026-08-02): complete, every row read off the BMF-Schreiben itself.**
Date, GZ and percentage come from the document; the reference date is the Boersentag the
Bundesbank computed on, as named in the letter (note 04.01.2021 and 03.01.2022 -- 2 January
was not a trading day in those years). The letters authenticate each other: every Schreiben
carries a BEZUG line naming its predecessor **with the BStBl page**, so 2018 S. 249 is
confirmed by the 2019 letter, 2019 S. 58 by the 2020 letter, 2020 S. 218 by the 2021 letter,
2021 S. 56 by the 2022 letter, 2022 S. 122 by the 2023 letter and 2023 S. 178 by the 2024
letter. The 2024 letter closes with *"Dieses Schreiben wird im Bundessteuerblatt Teil I
veroeffentlicht"*; its own page (S. 154) is cited by the BMF elsewhere and is the one entry
in the chain not confirmed by a successor letter.

**On the negative years, the BMF is explicit** -- 06.01.2021: *"Aufgrund des negativen
Basiszins wird keine Vorabpauschale erhoben."* 07.01.2022 says the same for 2022. That is
the same result the engine reaches by computing a non-positive Basisertrag, so the two rows
are values, not gaps.

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
