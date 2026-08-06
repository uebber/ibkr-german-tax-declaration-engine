# InvStG 18 -- Vorabpauschale

## Source

- **Primary:** [gesetze-im-internet.de -- 18 InvStG](https://www.gesetze-im-internet.de/invstg_2018/__18.html)
- **With version history:** [buzer.de -- 18 InvStG](https://www.buzer.de/18_InvStG.htm)
- **Regime start:** 56 Abs. 1 Satz 1 InvStG -- the InvStG 2018 provisions apply from 01.01.2018,
  so the first Vorabpauschale is the one for calendar 2018.
- **Amendment history (checked 2026-08-06, buzer.de version tracking).** The text below is that of
  Artikel 18 des Gesetzes zur Umsetzung der Aenderungen der EU-Amtshilferichtlinie und von
  weiteren Massnahmen gegen Gewinnkuerzungen und -verlagerungen, G. v. 20.12.2016, BGBl. I
  S. 3000, in force from 24.12.2016. § 18 carries exactly **one** earlier version -- the original
  Artikel 1 G. v. 19.07.2016, BGBl. I S. 1730 -- which was superseded on 24.12.2016, before the
  regime began to apply. **§ 18 has therefore been unchanged in every tax year in which it has
  had effect**, 2018 onward, and no year-by-year differentiation of its wording is needed. The
  InvStG as a whole has been amended since, most recently by Artikel 28 G. v. 04.02.2026,
  BGBl. 2026 I Nr. 33, but not in this paragraph.
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

**Abs. 1 is written per Investmentanteil, not per holding.** Every quantity in Saetze 1 to 3 is a
Ruecknahmepreis or a distribution *of one unit*; the number of units enters only through Rz. 18.4
of the BMF-Schreiben, which multiplies at the end and fixes the count as the one held at the close
of 31 December:

```
per Anteil:
  Basisertrag_je_Anteil = Ruecknahmepreis_Jahresbeginn x Basiszins x 0.70          (Satz 2)
  Basisertrag_je_Anteil <= (Ruecknahmepreis_letzt - Ruecknahmepreis_erst)
                             + Ausschuettungen_je_Anteil                           (Satz 3)

per Bestand:
  Basisertrag = Basisertrag_je_Anteil x Anzahl Anteile am 31.12.                   (Rz. 18.4)
  Vorabpauschale = max(0, Basisertrag - Ausschuettungen)                           (Satz 1)
```

The price and the unit count are therefore taken at different moments: the price is the first
Ruecknahmepreis set in the calendar year, the count is the holding at the close of 31 December.
The Satz 3 cap is bounded by the first and last price set in the calendar year, so its lower bound
is the same first price Satz 2 uses.

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

## Administrative guidance (Tier 2)

- **Source:** BMF-Schreiben of 21.05.2019, *Anwendungsfragen zum Investmentsteuergesetz in der ab
  dem 1. Januar 2018 geltenden Fassung*, BStBl I 2019 S. 527. Section 18 runs Rz. 18.1 to 18.11.
- **Amendment chain, each letter naming its predecessor in its BEZUG line:** 21.05.2019
  (BStBl I S. 527) -> ... -> 18.11.2024 (BStBl I S. 1547) -> 17.10.2025
  (GZ IV C 1 - S 1980/00206/032/029) -> 24.11.2025 (GZ IV C 1 - S 1980/00206/032/046). The
  24.11.2025 letter is the current one and **changes nothing in section 18**: its amendments run
  to §§ 2, 17 and others, and section 18 stands as issued in 2019.
- **Retrieved 2026-08-06.** Current letter:
  https://www.bundesfinanzministerium.de/Content/DE/Downloads/BMF_Schreiben/Steuerarten/Investmentsteuer/2025-11-24-anwendungsfragen-InvStG.pdf
  BMF serves only the two most recent letters of a recurring series, so the 2019 base text was
  taken from an Internet Archive snapshot of the original BMF URL
  (`web.archive.org/web/20220324182212if_/` + the 2019-05-21 BMF PDF path).
- **Applicable tax years:** 2018 onward; regime floor as above.

**What else section 18 contains**, beyond the claims recorded below (Validation Protocol item 2):
Rz. 18.1 is introductory; Rz. 18.2 restates Abs. 1 Saetze 1 to 3 without adding to them; Rz. 18.3
is a worked example; Rz. 18.5 governs balance-sheet treatment for
bilanzierende Anleger, which is outside this library's Privatvermoegen scope; Rz. 18.9 and 18.10
concern the Steuerabzug at a depotfuehrende Stelle on custody transfers and foreign-custodian
holdings; Rz. 18.11 restates Abs. 2.

### [GT-INVSTG-017] Rz. 18.4 -- computation precision

*"Fuer die Ermittlung der Vorabpauschale ist ein Rechnungszins mit (mindestens) drei
Nachkommastellen zu verwenden. ... Der Basisertrag ist mit mindestens vier Nachkommastellen
anzusetzen und erst nach der Multiplikation mit der Anzahl der mit Ablauf des 31. Dezember des
Kalenderjahres verwahrten oder verwalteten Anteile an dem Investmentfonds ist eine kaufmaennische
Rundung auf zwei Nachkommastellen vorzunehmen."*

Three requirements: the rate carries at least three decimal places, the Basisertrag at least
four, and rounding to two happens **once, after** multiplying by the unit count -- and the unit
count is the one held at the end of 31 December of the calendar year.

### [GT-INVSTG-018] Rz. 18.6 -- currency conversion of a foreign-currency fund

*"Bei in fremden Waehrungen notierenden Investmentanteilen sind fuer die Umrechnung in Euro die
am jeweiligen Stichtag (Jahresanfang, Ausschuettungstermin, Jahresende) geltenden Referenzkurse
der Europaeischen Zentralbank (EZB) zu Grunde zu legen."*

Each of the three inputs is converted at the ECB reference rate **of its own Stichtag**, not at a
single rate for the year. The three Stichtage named are the start of the year, the distribution
date, and the end of the year.

### [GT-INVSTG-035] Rz. 18.7 -- fund launched during the year

*"Bei unterjaehriger Neuauflage eines Investmentfonds ist der erste festgesetzte Ruecknahmepreis
oder falls dieser nicht vorhanden ist, der erste fuer diesen Investmentfonds ermittelte Boersen-
oder Marktpreis bei der Ermittlung der Vorabpauschale zu Grunde zu legen. Darueber hinaus ist die
Vorabpauschale gemaess § 18 Absatz 2 InvStG zeitanteilig anzusetzen."*

For a fund that did not exist at the start of the year the base is the first price actually set,
and Abs. 2's pro-rata reduction applies on top.

### [GT-INVSTG-036] Rz. 18.8 -- fund without a monthly price

*"Wenn der Investmentfonds nicht mindestens monatlich fortlaufend einen Ruecknahmepreis festsetzt,
ist fuer die Zwecke der Vorabpauschale auf den Boersen- oder Marktpreis abzustellen."*

This is the administration's threshold for Abs. 1 Satz 4: a Ruecknahmepreis set less often than
monthly does not count as one being set, and the market price takes its place.

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
| Ruecknahmepreis at the start of the year (Abs. 1 Satz 2) | first set in `Y-1` |
| Ruecknahmepreis at the end of the year (the Abs. 1 Satz 3 cap) | last set in `Y-1` |
| Ausschuettungen deducted (Abs. 1 Satz 1) | those made during `Y-1` |

Every input is a `Y-1` figure: a price taken from `Y` computes a different year's Vorabpauschale,
against a different Basiszins.

**The day is the first Ruecknahmepreis set in the calendar year.** Rz. 18.3 of the BMF-Schreiben
demonstrates it: the same figure serves as the Satz 2 base and as the Satz 3 cap's lower bound,
which Satz 3 defines as *"dem ersten ... im Kalenderjahr festgesetzten Ruecknahmepreis"*.

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
