# InvStG 18 -- Vorabpauschale

## Source

- **Primary:** [gesetze-im-internet.de -- 18 InvStG](https://www.gesetze-im-internet.de/invstg_2018/__18.html)
- **With version history:** [buzer.de -- 18 InvStG](https://www.buzer.de/18_InvStG.htm)
- **Regime start:** 56 Abs. 1 Satz 1 InvStG -- the InvStG 2018 provisions apply from 01.01.2018,
  so the first Vorabpauschale is the one for calendar 2018.
- **Basiszins values and their per-year provenance:** `bmf-guidance/basiszins-vorabpauschale.md`
  is the **single authoritative table**. Do not duplicate it here; an earlier revision of this
  file carried a second copy that drifted from it (Validation Protocol item 5).
- **Form instructions:** `reference/Anltg_KAP_INV_24.md`, `reference/Anltg_KAP_INV_25.md`

> Statutory text below retrieved 2026-08-03 from gesetze-im-internet.de/invstg_2018/__18.html.
> Umlauts transliterated per this library's convention. § 18 has **four Absaetze**; all four are
> reproduced, because the previous revision of this file mis-numbered three of them.

## Relevance to Engine

The Vorabpauschale is an annual deemed minimum income for investment fund units. The engine
computes it from start-of-year position values and the published Basiszins.

---

## Absatz structure (all four, verbatim)

**Careful: the earlier revision of this file labelled Abs. 2 "Basisertrag", Abs. 3 "partial year
acquisition" and cited "Abs. 1 Satz 3" for the Zuflussfiktion. All three were wrong.** The
Basisertrag lives in Abs. 1; Abs. 2 is the pro-rata rule; Abs. 3 is the Zuflussfiktion.

### Abs. 1 -- Definition, Basisertrag and its cap (four Saetze)

- **Satz 1:** *"Die Vorabpauschale ist der Betrag, um den die Ausschuettungen eines
  Investmentfonds innerhalb eines Kalenderjahres den Basisertrag fuer dieses Kalenderjahr
  unterschreiten."*
- **Satz 2:** *"Der Basisertrag wird ermittelt durch Multiplikation des Ruecknahmepreises des
  Investmentanteils zu Beginn des Kalenderjahres mit 70 Prozent des Basiszinses nach Absatz 4."*
- **Satz 3:** *"Der Basisertrag ist auf den Mehrbetrag begrenzt, der sich zwischen dem ersten und
  dem letzten im Kalenderjahr festgesetzten Ruecknahmepreis zuzueglich der Ausschuettungen
  innerhalb des Kalenderjahres ergibt."*
- **Satz 4:** *"Wird kein Ruecknahmepreis festgesetzt, so tritt der Boersen- oder Marktpreis an
  die Stelle des Ruecknahmepreises."*

```
Basisertrag = Ruecknahmepreis_Jahresbeginn x Basiszins x 0.70        (Satz 2)
Basisertrag <= (Ruecknahmepreis_letzt - Ruecknahmepreis_erst) + Ausschuettungen   (Satz 3)
Vorabpauschale = max(0, Basisertrag - Ausschuettungen)               (Satz 1)
```

Note Satz 3 is expressed in **Ruecknahmepreise festgesetzt im Kalenderjahr**, not in calendar
boundaries: the first and last price *set during the year*. Note also Satz 4 -- for an
exchange-traded fund where no Ruecknahmepreis is published, the Boersen- oder Marktpreis takes
its place. The engine uses the broker's position mark price, which is a market price; that is
Satz 4's substitute, and it is only correct where no Ruecknahmepreis was set. **Not verified per
instrument.**

### Abs. 2 -- Reduction in the year of acquisition

*"Im Jahr des Erwerbs der Investmentanteile vermindert sich die Vorabpauschale um ein Zwoelftel
fuer jeden vollen Monat, der dem Monat des Erwerbs vorangeht."*

**Not implemented.** The engine applies no pro-rata reduction. It computes the Vorabpauschale
only for units held at the *start* of the calendar year (it reads the SoY position snapshot), so
units acquired during the year produce no Vorabpauschale at all rather than a reduced one. For
the acquisition year that under-computes to zero where Abs. 2 would give eleven twelfths or less.

### Abs. 3 -- Zuflussfiktion (decides the declaration year)

*"Die Vorabpauschale gilt am ersten Werktag des folgenden Kalenderjahres als zugeflossen."*

This is the provision that decides **which return the figure belongs on**. See the next section.

### Abs. 4 -- Basiszins (three Saetze)

*"Der Basiszins ist aus der langfristig erzielbaren Rendite oeffentlicher Anleihen abzuleiten.
Dabei ist auf den Zinssatz abzustellen, den die Deutsche Bundesbank anhand der Zinsstrukturdaten
jeweils auf den ersten Boersentag des Jahres errechnet. Das Bundesministerium der Finanzen
veroeffentlicht den massgebenden Zinssatz im Bundessteuerblatt."*

Published values, with per-year provenance: `bmf-guidance/basiszins-vorabpauschale.md`.

---

## Which calendar year's Vorabpauschale goes on which return

**This is the most error-prone point in the whole computation and the engine got it wrong.**

```
Basiszins as of 02.01.X  ->  Vorabpauschale FOR calendar year X
                         ->  deemed to flow first working day of X+1  (18 Abs. 3 InvStG)
                         ->  declared on Anlage KAP-INV Zeilen 9-13 in VZ X+1
```

Tier 3 confirmation, `reference/Anltg_KAP_INV_24.md` (Zeilen 9 bis 13), verbatim:

> *"In die Zeilen 9 bis 13 tragen Sie bitte getrennt nach Fondsart die Ihnen im Jahr 2024 als
> zugeflossen geltenden Vorabpauschalen ein, die nicht dem inlaendischen Steuerabzug unterlegen
> haben. Vorabpauschalen gelten am ersten Werktag des folgenden Kalenderjahres als zugeflossen.
> **Die Vorabpauschale fuer 2023 gilt am 2. Januar 2024 als zugeflossen.**"*

So the **VZ 2024** return carries the Vorabpauschale computed **for calendar 2023** -- Basiszins
2.55%, Ruecknahmepreis at the start of 2023, capped by the 2023 value movement, reduced by 2023
distributions. The 2.29% rate published for 02.01.2024 first appears on the **VZ 2025** return.

The same statement appears in every annual BMF Basiszins-Schreiben; see
`bmf-guidance/basiszins-vorabpauschale.md` for the verbatim 05.01.2024 wording.

### Inputs required, and where the engine gets them

For the Vorabpauschale declared in VZ `Y` (i.e. the one for calendar `Y-1`):

| Input | Source | Available today? |
|-------|--------|------------------|
| Basiszins for `Y-1` | `src/tax_law/registry.py` (`BASISZINS_PCT`) | yes -- table starts at 2018 |
| Ruecknahmepreis at start of `Y-1` | `Positions-{Y-1}-SoY.csv` | **no** -- only the selected year's snapshots are loaded |
| Ruecknahmepreis at end of `Y-1` | `Positions-{Y-1}-EoY.csv`, equivalently `Positions-{Y}-SoY.csv` | yes -- this is the currently-loaded SoY snapshot |
| Distributions during `Y-1` | transaction files, concatenated across all years <= `Y` | yes |

Only the first-of-`Y-1` snapshot is missing. Where it cannot be resolved the deemed income
cannot be computed, which is the archetypal `FAIL_FAST` condition named in
`src/processing/data_gaps.py` -- the engine must not substitute the wrong year's figure.

---

## Engine Mapping

| Component | Engine field | Form line |
|-----------|--------------|-----------|
| Vorabpauschale (gross, per fund type) | `VorabpauschaleData.gross_vorabpauschale_eur` | KAP-INV Zeilen 9-13 |
| Vorabpauschale accumulated over the holding period, deducted on disposal | see `invstg-19-veraeusserungsgewinne.md` | KAP-INV **Zeile 53** (not Zeile 55) |

**Correction, 2026-08-03:** this table previously named `RealizedGainLoss.accumulated_vorabpauschale`
and Zeile 55. Both were wrong. No such field exists on `RealizedGainLoss` -- the engine has no
per-lot Vorabpauschale accumulation at all -- and Zeile 55 is *"Gewinne aus der Veraeusserung von
bestandsgeschuetzten Alt-Anteilen"*. The deduction line is Zeile 53. See
`tax-forms/anlage-kap-inv-zeilen.md`.

## Teilfreistellung

The Vorabpauschale is an Investmentertrag under 16 Abs. 1 Nr. 2 InvStG and is subject to the
Teilfreistellung of 20 InvStG. It is nevertheless declared **gross** on Zeilen 9-13; the
Finanzamt applies the Teilfreistellung. See `invstg-20-teilfreistellung.md`.

## Known deviations from the statute

Listed here so they are not rediscovered as surprises. Each changes a declared figure.

1. **Abs. 2 pro-rata not implemented** -- see above.
2. **Abs. 1 Satz 4** -- the engine uses the broker's mark price without establishing that no
   Ruecknahmepreis was set.
3. **Units disposed of during the year** -- the engine skips any fund with no end-of-year
   position. That matches the ordinary result (the Zufluss under Abs. 3 falls after the
   disposal), but it is an inference from Abs. 3, not a rule stated in Abs. 1, and no Tier 1 or
   Tier 2 source has been located that states it directly. Recorded as an open question in
   `research/coverage-matrix.md`.
