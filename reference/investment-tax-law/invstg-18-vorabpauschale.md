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
  Vorabpauschale_je_Anteil = max(0, Basisertrag_je_Anteil
                                    - Ausschuettungen_je_Anteil)                   (Satz 1)
  Vorabpauschale_je_Anteil x k/12, k = 12 - volle Monate vor dem Erwerbsmonat      (Abs. 2)

per Bestand:
  Vorabpauschale = SUM je Erwerb of Vorabpauschale_je_Anteil x k/12                (Rz. 18.4,
                                     x Anteile am 31.12.                            Rz. 18.11)
```

**The last two per-Anteil lines are in that order and not the other one.** Abs. 2 reduces *"die
Vorabpauschale"*, and Satz 1 defines the Vorabpauschale as the amount by which the distributions
fall short of the Basisertrag. So the twelfths multiply `Basisertrag - Ausschuettungen`; they never
multiply the Basisertrag with the distributions taken off afterwards. The two orders differ by
`Ausschuettungen x (12 - k)/12` on any fund that both was acquired during the year and distributed
in it. [GT-INVSTG-056] is the worked example that shows the administration reading it this way.

> **Correction, 2026-08-09.** This block set out Satz 2, Satz 3, Rz. 18.4 and Satz 1 in that
> sequence and **omitted Abs. 2 entirely**, so the one ordering question the section turns on was
> the one thing the summary did not state. Abs. 2 was recorded in full below throughout; what was
> missing was its place in the sequence.

The price and the unit count are therefore taken at different moments: the price is the first
Ruecknahmepreis set in the calendar year, the count is the holding at the close of 31 December.
The Satz 3 cap is bounded by the first and last price set in the calendar year, so its lower bound
is the same first price Satz 2 uses.

Note Satz 3 is expressed in **Ruecknahmepreise festgesetzt im Kalenderjahr**, not in calendar
boundaries: the first and last price *set during the year*.

**Satz 1 and Satz 3 use one term and it must be read one way.** *Ausschuettungen* appears twice in
Abs. 1 -- inside the Satz 3 cap, where it raises the ceiling, and in the Satz 1 subtraction, where
it lowers the result. It is the same word in the same Absatz, and it carries the single legal
definition of 2 Abs. 11 InvStG, [GT-INVSTG-057]. Rz. 18.3 works both places with the same 0,10 €
([GT-INVSTG-056]). So an amount that is an Ausschuettung is an Ausschuettung for both purposes,
and one that is not is neither. **The two sides cannot answer differently**, and no separate
enquiry is owed for the cap.

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

**Rz. 18.11 restates the Absatz and works it, and the example fixes what the reduction operates
on:**

> *"Abwandlung des Beispiels aus Rz. 18.3: Anleger A hat den Investmentanteil erst am 10.7.01
> erworben. Die fuer das gesamte Jahr 01 berechnete Vorabpauschale i. H. v. 0,50 € mindert sich um
> 6/12 auf 0,25 €."*

That 0,50 € is the figure Rz. 18.3 derives **per Anteil**, and Rz. 18.3 is explicit that it is what
remains *after* the year's Ausschuettung of 0,10 € has been taken off the capped Basisertrag of
0,60 € — the quotation is at [GT-INVSTG-056]. Two things follow, and they are separate:

- **What the twelfths multiply.** The 6/12 is applied to a figure that is already net of the
  distributions, which is the ordering the statute gives in Abs. 2 read with Satz 1.
- **Where in the computation they apply.** The reduction reaches the per-unit amount at a point
  where no unit count has yet entered — Rz. 18.4 multiplies by the count only afterwards. The
  factor is therefore an attribute of the units acquired, not of the position.

**The reduction applies per acquisition.** Units of one fund held at the close of 31 December that
were acquired at different times each carry their own factor: units already held when the year
opened are not in their year of acquisition and keep twelve twelfths; units acquired in the year
keep twelve less one for each full month preceding their month of acquisition. The Vorabpauschale
for the holding is the sum over those groups.

Three further administrative statements support this and none contradicts it: the reduction turns
on *Anschaffungsdaten* attaching to units ([GT-INVSTG-055], Rz. 18.9); the Anschaffungsdaten of a
fund holding are recorded per acquisition point, *"die Anzahl der zum jeweiligen
Anschaffungszeitpunkt erworbenen Investmentanteile"* ([GT-ESTG20-041]); and *"Erwerb"* in Abs. 2
means an actual acquisition, since a deemed one leaves the full year in place ([GT-INVSTG-054],
Rz. 20.4).

**The limit of what is quoted.** No located source works an example on a holding acquired in more
than one instalment. Summing the per-unit factor group by group joins two quoted rules — the
per-unit reduction here and the 31 December count in [GT-INVSTG-017] — rather than quoting a
third. Recorded because the step is a construction, not because a competing reading survives:
the rival reading, that *"die Vorabpauschale"* denotes one amount for the whole position, is
contradicted by the Rz. 18.11 example above and leaves *"der Monat des Erwerbs"* without a
referent for a holding bought in two months of the same year.

> **Closed 2026-08-07, formerly open question Q13.** See the retirement note in
> `../research/open-legal-questions.md`.

### [GT-INVSTG-012] Abs. 3 -- Zuflussfiktion (decides the declaration year)

*"Die Vorabpauschale gilt am ersten Werktag des folgenden Kalenderjahres als zugeflossen."*

This is the provision that decides **which return the figure belongs on**. See the next section.

Rz. 18.12 restates it and gives the reason: *"Nach § 18 Absatz 3 InvStG fliesst die Vorabpauschale
nicht in dem Kalenderjahr zu, fuer das sie berechnet wird, sondern sie gilt am ersten Werktag des
folgenden Kalenderjahres als zugeflossen. Hierdurch soll das Steuerabzugsverfahren erleichtert
werden, da in vielen Faellen noch ein voller Sparer-Pauschbetrag zur Verfuegung steht, mit dem die
Vorabpauschale verrechnet werden kann."*

The stated purpose is a Steuerabzug convenience. It is **not** a holding test: what the amount is
computed on is fixed by Abs. 1 and by the unit count in [GT-INVSTG-017], not by who holds the
units on the Zufluss date — see [GT-INVSTG-016].

### [GT-INVSTG-013] Abs. 4 -- Basiszins (three Saetze)

*"Der Basiszins ist aus der langfristig erzielbaren Rendite oeffentlicher Anleihen abzuleiten.
Dabei ist auf den Zinssatz abzustellen, den die Deutsche Bundesbank anhand der Zinsstrukturdaten
jeweils auf den ersten Boersentag des Jahres errechnet. Das Bundesministerium der Finanzen
veroeffentlicht den massgebenden Zinssatz im Bundessteuerblatt."*

Rz. 18.13 names the underlying series -- *"die Zinsstruktur der Renditen fuer Bundeswertpapiere mit
jaehrlicher Kuponzahlung und 15-jaehriger Restlaufzeit"*, computed by the Bundesbank
*"boersentaeglich"*. Rz. 18.14 fixes **which day's value is the Basiszins**:

> *"Als Basiszins fuer die Ermittlung der Vorabpauschale ist auf den Wert abzustellen, der fuer den
> ersten Boersentag eines Kalenderjahres ermittelt wird (§ 18 Absatz 4 Satz 2 InvStG). Dieser Wert
> wird vom BMF im Bundessteuerblatt (§ 18 Absatz 4 Satz 3 InvStG) und - fuer einen
> voruebergehenden Zeitraum - auch auf der Internetseite des BMF veroeffentlicht."*

The day is the **erster Boersentag** of the calendar year, which is 2 January only in years whose
first exchange day falls on it. Note this is the Basiszins day and is a different question from
the Stichtag at which a foreign-currency figure is converted, which is [GT-INVSTG-018].

Published values, with per-year provenance: `bmf-guidance/basiszins-vorabpauschale.md`.

---

## Administrative guidance (Tier 2)

- **Source:** BMF-Schreiben of 21.05.2019, *Anwendungsfragen zum Investmentsteuergesetz in der ab
  dem 1. Januar 2018 geltenden Fassung*, BStBl I 2019 S. 527. **Section 18 runs Rz. 18.1 to
  18.14.**
- **Amendment chain.** The current letter of 24.11.2025 (GZ IV C 1 - S 1980/00206/032/046) states
  its own chain: *"wird das BMF-Schreiben vom 21. Mai 2019, BStBl I S. 527, zuletzt geaendert
  durch BMF-Schreiben vom 18. November 2024, BStBl I S. 1547, wie folgt geaendert"*. The letter of
  17.10.2025 (GZ IV C 1 - S 1980/00206/032/029) appears **only in its BEZUG line** and is not
  named as an amending letter, so it is not a link in the chain.
- **Which letters were checked for a change to section 18, and how.** Retrieved and read in full
  on 2026-08-07: 29.10.2020, 18.01.2021, 29.04.2021, 18.06.2021, 15.03.2022 and 24.11.2025.
  **None amends any Randziffer of section 18**; their amendments run to §§ 2, 6, 9, 16, 17, 19,
  20, 31, 33, 48 and others. Section 18 therefore stands as issued in 2019. Not individually
  retrieved: 06.09.2022, 30.12.2022, 18.11.2024 — BMF serves only the two most recent letters of
  a recurring series and no official mirror of these three was located; each is described by
  Tier 5 summaries as touching Rz. 31.x only, which is **not** verification and is recorded here
  as the residual gap.
  **One amendment outside section 18 does reach the Vorabpauschale:** 29.04.2021 appended three
  Saetze to Rz. 20.4 — see [GT-INVSTG-054] in `invstg-22-teilfreistellungssatz-aenderung.md`.
- **Retrieved 2026-08-07**, base letter of 21.05.2019, full text, from the industry-body mirror
  `https://www.bvl-verband.de/fileadmin/steuerpolitik/bmf-schreiben/2019/2019-05-21-anwendungsfragen-zum-investmentsteuergesetz-in-der-am-1-januar-2018-geltenden-fassung-InvStG-2018.pdf`
  — PDF metadata `Author: BMF`, `Title: Anwendungsfragen zum Investmentsteuergesetz in der ab dem
  1. Januar 2018 geltenden Fassung (InvStG)`, created 28.05.2019.
- **Re-retrieved 2026-08-09, from an official source, because that mirror now 404s.**
  https://www.bzst.de/SharedDocs/BMF/DE/Downloads/bmf_schreiben_20190521_InvStG_18_anwendungsfragen.pdf?__blob=publicationFile&v=1
  — 152 pp, PDF created 21.05.2019, letterhead *Bundesministerium der Finanzen*, GZ
  `IV C 1 - S 1980-1/16/10010 :001`, DOK `2019/0415199`, dated 21. Mai 2019, addressed to the
  Oberste Finanzbehoerden der Laender. Section 18 runs pp. 91-93. This is the copy Rz. 18.3 at
  [GT-INVSTG-056] is quoted from. Amendment letters of 29.10.2020,
  18.01.2021, 29.04.2021 and 15.03.2022 from the official BZSt mirror
  (`https://www.bzst.de/SharedDocs/BMF/DE/Downloads/bmf_schreiben_<YYYYMMDD>_InvStG_18_anwendung.pdf`);
  18.06.2021 from the BVL mirror; 24.11.2025 from
  https://www.bundesfinanzministerium.de/Content/DE/Downloads/BMF_Schreiben/Steuerarten/Investmentsteuer/2025-11-24-anwendungsfragen-InvStG.pdf
- **Applicable tax years:** 2018 onward; regime floor as above.

**What else section 18 contains**, beyond the claims recorded below (Validation Protocol item 2):
Rz. 18.1 is introductory; Rz. 18.2 restates Abs. 1 Saetze 1 to 3 without adding to them; Rz. 18.5
governs balance-sheet treatment for bilanzierende Anleger, which is outside this library's
Privatvermoegen scope; Rz. 18.10 provides that no Vorabpauschale is set on units a domestic
depotfuehrende Stelle holds for a foreign credit institution. Rz. 18.3 was in this list, as *"a
worked example"*, until 2026-08-09; it is recorded in full at [GT-INVSTG-056] because the order it
computes in decides a figure.

> **Correction, 2026-08-07.** The previous revision of this file gave the range as *"Rz. 18.1 to
> 18.11"* and described Rz. 18.11 as restating Abs. 2 and nothing more. Both are wrong. The
> section has three further Randziffern — 18.12 (Zuflussfiktion), 18.13 and 18.14 (Basiszins) —
> and Rz. 18.11 carries a worked example that decides how Abs. 2 is applied, together with a
> cross-reference to Rz. 20.4. All four are now recorded below. The range was stated without the
> document open; the missing Randziffern are exactly the *"unstated unit"* Validation Protocol
> item 2 exists to catch.

### [GT-INVSTG-056] Rz. 18.3 -- the worked example, and the order it computes in

> *"Beispiel: Der Basiszins nach § 18 Absatz 4 InvStG betraegt 1,0 %. Da nur 70 % davon anzusetzen
> sind, betraegt der massgebende Zinssatz 0,7 %. Ruecknahmepreis des Investmentanteils am
> Jahresanfang 01: 100 €. Ruecknahmepreis des Investmentanteils am Jahresende 01: 100,50 €.
> Ausschuettung waehrend des Jahres 01: 0,10 € pro Anteil. Fuer die Vorabpauschale koennte maximal
> der Basisertrag i. H. v. 0,70 € pro Anteil angesetzt werden (100 € x 0,7 % = 0,70 €). Die
> Wertsteigerung waehrend des Kalenderjahres (Mehrbetrag) betraegt 0,50 € + 0,10 € Ausschuettung =
> 0,60 €. Die Wertsteigerung von 0,60 € bildet die Obergrenze fuer die Vorabpauschale. Von dieser
> Obergrenze sind die Ausschuettungen des Jahres 01 i. H. v. 0,10 € abzuziehen, so dass eine
> Vorabpauschale von 0,50 € verbleibt."*

Everything in it is per Anteil, and it runs the three Saetze in one fixed order:

1. Satz 2 gives an uncapped Basisertrag of 0,70 €.
2. Satz 3 caps it at the Mehrbetrag, 0,50 € of price movement plus the 0,10 € distribution = 0,60 €.
   Note the distribution appears **inside** the cap, which is what Satz 3 says and is not the Satz 1
   subtraction.
3. Satz 1 then subtracts the same 0,10 € from the capped 0,60 €, leaving **0,50 €**.

So the *"Vorabpauschale i. H. v. 0,50 €"* that Rz. 18.11 reduces by 6/12 is already net of the
year's distributions. That is the administration applying Abs. 2 to `Basisertrag -
Ausschuettungen`, and it is the corroboration for the order in [GT-INVSTG-010] above.

The example also demonstrates that the Satz 3 cap can bind while a Vorabpauschale still remains: it
is a ceiling on the Basisertrag, not on the Vorabpauschale.

**What the cited unit also contains:** nothing further. Rz. 18.3 is the example and no other text.
Rz. 18.5 continues its figures for bilanzierende Anleger, which is outside this library's
Privatvermoegen scope; Rz. 18.11 continues them for Abs. 2.

### [GT-INVSTG-017] Rz. 18.4 -- computation precision

*"Fuer die Ermittlung der Vorabpauschale ist ein Rechnungszins mit (mindestens) drei
Nachkommastellen zu verwenden. ... Der Basisertrag ist mit mindestens vier Nachkommastellen
anzusetzen und erst nach der Multiplikation mit der Anzahl der mit Ablauf des 31. Dezember des
Kalenderjahres verwahrten oder verwalteten Anteile an dem Investmentfonds ist eine kaufmaennische
Rundung auf zwei Nachkommastellen vorzunehmen."*

Three requirements: the rate carries at least three decimal places, the Basisertrag at least
four, and rounding to two happens **once, after** multiplying by the unit count -- and the unit
count is the one held at the end of 31 December of the calendar year.

**The count is the general rule, not a Steuerabzug convention.** Rz. 18.4 sits in Textziffer 18.1
*"Ermittlung der Vorabpauschale"* and is unqualified; where a Randziffer of this section is
confined to the withholding procedure it says so, as Rz. 18.9 and Rz. 18.10 do
(*"im Steuerabzugsverfahren"*). The count therefore governs the amount itself, which is what
decides [GT-INVSTG-016].

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

### [GT-INVSTG-055] Rz. 18.9 -- a transfer arriving without acquisition data

*"Bei einem Depotuebertrag aus dem In- oder Ausland, bei dem keine Anschaffungsdaten mitgeteilt
wurden, ist im Steuerabzugsverfahren die Vorabpauschale fuer das gesamte Kalenderjahr anzusetzen.
Wenn der Anleger im Veranlagungsverfahren einen unterjaehrigen Anschaffungszeitpunkt nachweist,
ist die zu viel erhobene Kapitalertragsteuer zu erstatten."*

Two statements, and the second is the one that reaches an assessment. The Abs. 2 reduction is a
function of *Anschaffungsdaten*; where those are unknown the withholding agent sets the **full**
year, and the full year is therefore the administration's fallback for missing data, not its
answer for units acquired in an earlier year. What restores the reduction is the holder proving
*"einen unterjaehrigen Anschaffungszeitpunkt"* -- an acquisition date attaching to units.

The first sentence is confined to the Steuerabzugsverfahren, which a foreign custodian does not
perform. What the cited unit also contains: nothing further; Rz. 18.9 is two Saetze.

---

## Which calendar year's Vorabpauschale goes on which return

**This is the most error-prone point in the whole computation.** The Basiszins year, the price
year and the declaration year are three different things, and only two of them coincide.

```
Basiszins of the first Boersentag of X  ->  Vorabpauschale FOR calendar year X   (Rz. 18.14)
                                        ->  deemed to flow first working day of X+1  (18 Abs. 3)
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
| Basiszins | `Y-1` (the rate determined for the first Boersentag of `Y-1`; Rz. 18.14) |
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

## [GT-INVSTG-059] A substitute payment on units that were out on loan

Where units are lent under a Wertpapierdarlehen across a distribution date, the fund pays the
person the units are attributed to, and the lender receives a contractual **Kompensationszahlung**
from the counterparty instead. Whether that amount is an Ausschuettung for Abs. 1 does not turn on
what it is called. It turns on the attribution question that 2 Abs. 10 InvStG puts before it,
[GT-INVSTG-058], and the sources answer it in two branches.

**Branch A -- attribution stayed with the lender** (39 Abs. 2 Nr. 1 AO; the Gesamtschau of
[GT-ESTG20-044]). The lender remained the Anleger throughout, and *"die Dividende ist
wirtschaftlich dem Darlehensgeber zuzurechnen und bei diesem zu besteuern"* ([GT-ESTG20-045]).
Both conditions of [GT-INVSTG-057] are met: the amount is the fund's and it reaches the Anleger.
It is an Ausschuettung, it is an Investmentertrag under 16 Abs. 1 Nr. 1, and under Abs. 1 it both
raises the Satz 3 cap and is subtracted under Satz 1.

**Branch B -- attribution passed to the borrower** (39 Abs. 1 AO; the Grundfall of
[GT-ESTG20-043]). The borrower was the Anleger over the distribution date, so the fund distributed
nothing *to the lender*, and what the lender received came from the counterparty and not from the
fund. Neither condition of [GT-INVSTG-057] is met. It is not an Ausschuettung, it is none of the
three items of the closed list in 16 Abs. 1 ([GT-INVSTG-001]), and it enters Abs. 1 on **neither**
side -- the Satz 3 cap is then the price movement alone and Satz 1 subtracts nothing.

**What branch B does not decide is what the payment *is*.** That is a question of 20 EStG and is
recorded at [GT-ESTG20-010]; the only located administrative statement on a consideration paid
under such a transaction addresses a different payment entirely, [GT-ESTG20-047].

**What is not quoted, and is the honest limit of this section.** No located Tier 1 or Tier 2 source
addresses a Kompensationszahlung on **Investmentanteile**. Both branches are subsumptions under
quoted rules -- the definitions in 2 Abs. 10 and Abs. 11, the payer named in 16 Abs. 1 Nr. 1, and
the attribution rules of the 09.07.2021 letter -- and not a fourth quotation stating the result.
The InvStG contains no provision on the lending of Investmentanteile by an investor; the only
Wertpapierdarlehen rules it carries, 6 Abs. 3 Satz 1 Nr. 2 InvStG with Rz. 6.7 to 6.9, are about a
**fund** as the lender and reach the investor level not at all. They do supply the administration's
definition of the term, Rz. 6.8: a Kompensationszahlung is *"der Ausgleich fuer die dem Darlehens-
oder Pensionsgeber entgangenen Dividenden oder sonstigen Beteiligungseinnahmen"*, and 6 Abs. 3
Satz 1 puts it in a different Nummer from the Beteiligungseinnahme itself -- which is the same
separation branch B draws, one level up.

**Which branch applies is a question of fact about the loan, not of law.** Rz. 4 of the 09.07.2021
letter puts the burden of showing attribution to the borrower on the borrower, and its criteria --
duration across the record date, pricing, liquidity, voting, and how easily the position can be
withdrawn -- are terms of the lending arrangement.

## [GT-INVSTG-016] Units disposed of during the calendar year

**The question is decided by the multiplier, not by the disposal.** Rz. 18.4 ([GT-INVSTG-017])
states what the per-unit Basisertrag is multiplied by: *"die Anzahl der mit Ablauf des
31. Dezember des Kalenderjahres verwahrten oder verwalteten Anteile an dem Investmentfonds"*.
Units disposed of before that moment are not in the count. So:

- a holding disposed of in full during calendar `X` is multiplied by nothing and produces **no**
  Vorabpauschale for `X`;
- a **partial** disposal drops the units sold out of the count entirely, with no time
  apportionment for the months they were held -- Abs. 2 apportions on acquisition, and the statute
  has no counterpart on disposal;
- a disposal that is only **deemed** leaves the units in the count, and the full year stands. Rz.
  20.4 says so in terms for a § 22 Abs. 1 Anschaffungs- und Veraeusserungsfiktion
  ([GT-INVSTG-054]), and distinguishes it from *"einer tatsaechlichen Veraeusserung der
  Investmentanteile"*.

The test is therefore what is held at the close of 31 December, not whether a disposal occurred.

**Two further provisions point the same way and neither is the ground of the rule.** Abs. 3
defers the Zufluss to the first working day of the following year, by which time disposed units
are gone ([GT-INVSTG-012]). And § 19 Abs. 1 Satz 3 InvStG deducts from a disposal gain only the
Vorabpauschalen *"waehrend der Besitzzeit angesetzten"*, which Rz. 19.4 explains as *"Um eine
doppelte Besteuerung auszuschliessen"* -- a Vorabpauschale arising for the year of disposal would
be deemed to flow after the Besitzzeit ended and so could never be deducted, defeating that
purpose.

**What is not quoted.** No located source states *"im Jahr der Veraeusserung faellt keine
Vorabpauschale an"* in those words; the answer follows from the computation rule. No Tier 4
decision on the point has been located.

> **Closed 2026-08-07, formerly open question Q5.** The library had grounded this in the
> Zuflussfiktion alone and recorded it as unresolved, because a fiction about *when* income is
> received does not settle whether it arises. Rz. 18.4 settles it on the other side of the
> equation and was already in this file. See the retirement note in
> `../research/open-legal-questions.md`.
