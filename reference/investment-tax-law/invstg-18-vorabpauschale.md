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

## Scope

An annual deemed minimum income for investment fund units: where a fund distributes less than a
notional base return, the shortfall is taxed as though it had been distributed.

---

## Absatz structure (all four, verbatim)

**Careful: the earlier revision of this file labelled Abs. 2 "Basisertrag", Abs. 3 "partial year
acquisition" and cited "Abs. 1 Satz 3" for the Zuflussfiktion. All three were wrong.** The
Basisertrag lives in Abs. 1; Abs. 2 is the pro-rata rule; Abs. 3 is the Zuflussfiktion.

### [GT-INVSTG-010] Abs. 1 -- Definition, Basisertrag and its cap (four Saetze)

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
boundaries: the first and last price *set during the year*.

Note also the order of precedence in Satz 4. The Ruecknahmepreis is the primary measure; a
Boersen- oder Marktpreis substitutes for it **only where no Ruecknahmepreis was set**. A market
price used in place of an existing Ruecknahmepreis is not Satz 4's substitute, and whether a
Ruecknahmepreis exists is a per-instrument question.

### [GT-INVSTG-011] Abs. 2 -- Reduction in the year of acquisition

*"Im Jahr des Erwerbs der Investmentanteile vermindert sich die Vorabpauschale um ein Zwoelftel
fuer jeden vollen Monat, der dem Monat des Erwerbs vorangeht."*

So units bought during the year carry a **reduced** Vorabpauschale, not none: one twelfth is
dropped for each full month before the month of acquisition. Units bought in December still
attract one twelfth.

### [GT-INVSTG-012] Abs. 3 -- Zuflussfiktion (decides the declaration year)

*"Die Vorabpauschale gilt am ersten Werktag des folgenden Kalenderjahres als zugeflossen."*

This is the provision that decides **which return the figure belongs on**. See the next section.

### [GT-INVSTG-013] Abs. 4 -- Basiszins (three Saetze)

*"Der Basiszins ist aus der langfristig erzielbaren Rendite oeffentlicher Anleihen abzuleiten.
Dabei ist auf den Zinssatz abzustellen, den die Deutsche Bundesbank anhand der Zinsstrukturdaten
jeweils auf den ersten Boersentag des Jahres errechnet. Das Bundesministerium der Finanzen
veroeffentlicht den massgebenden Zinssatz im Bundessteuerblatt."*

Published values, with per-year provenance: `bmf-guidance/basiszins-vorabpauschale.md`.

---

## Which calendar year's Vorabpauschale goes on which return

**This is the most error-prone point in the whole computation.** The Basiszins year, the price
year and the declaration year are three different things, and only two of them coincide.

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

### [GT-INVSTG-014] Which year each input is taken from

For the Vorabpauschale declared in VZ `Y` -- that is, the one computed for calendar `Y-1`:

| Input | Which year it is taken from |
|-------|------------------------------|
| Basiszins | `Y-1` (the rate published for 02.01. of `Y-1`) |
| Ruecknahmepreis at the start of the year (Abs. 1 Satz 2) | first of `Y-1` |
| Ruecknahmepreis at the end of the year (the Abs. 1 Satz 3 cap) | last set in `Y-1` |
| Ausschuettungen deducted (Abs. 1 Satz 1) | those made during `Y-1` |

Every input is a `Y-1` figure. The one that is easy to get wrong is the first: the start-of-`Y-1`
price is *not* the start-of-`Y` position snapshot, and using the latter computes a different
year's Vorabpauschale with a different Basiszins.

---

## [GT-INVSTG-015] Teilfreistellung

The Vorabpauschale is an Investmentertrag under 16 Abs. 1 Nr. 2 InvStG and is subject to the
Teilfreistellung of 20 InvStG. It is nevertheless declared **gross** on Zeilen 9-13; the
Finanzamt applies the Teilfreistellung. See `invstg-20-teilfreistellung.md`.

## [GT-INVSTG-016] Disposal during the calendar year -- unresolved

Whether a fund disposed of during calendar `X`, and therefore not held on the first working day
of `X+1`, gives rise to a Vorabpauschale for `X` at all.

- **For "no Vorabpauschale":** Abs. 3 deems the inflow to occur on the first working day of the
  following year. On that date the units are gone, so there is no holder to whom the deemed
  income can flow.
- **Against:** Abs. 1 defines the Vorabpauschale by reference to the calendar year's prices and
  distributions, and states no holding requirement at the year's end. The Zuflussfiktion fixes
  *when* income is received, which is not obviously the same as whether it arises.

No Tier 1 or Tier 2 source stating the point directly has been located. Registered in
`../research/open-legal-questions.md`.
