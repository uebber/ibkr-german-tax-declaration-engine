# EStG 23 -- Private Veraeusserungsgeschaefte

## Source

- **Primary:** [gesetze-im-internet.de -- 23 EStG](https://www.gesetze-im-internet.de/estg/__23.html)
- **With court rulings:** [dejure.org -- 23 EStG](https://dejure.org/gesetze/EStG/23.html)
- **EStH commentary:** [EStH 2024 -- 23 Private Veraeusserungsgeschaefte](https://esth.bundesfinanzministerium.de/esth/2024/A-Einkommensteuergesetz/II-Einkommen-2-24b/8-Die-einzelnen-Einkunftsarten-13-24b/g-Sonstige-Einkuenfte-22-23/Paragraf-23/inhalt.html)
- **Detailed guidance:** [EStH 2024 -- Anhang 26 Private Veraeusserungsgeschaefte](https://esth.bundesfinanzministerium.de/esth/2024/C-Anhaenge/Anhang-26/inhalt.html)

Period arithmetic pulls in three further Tier 1 provisions, cited verbatim below:

- [gesetze-im-internet.de -- 108 AO](https://www.gesetze-im-internet.de/ao_1977/__108.html) (Fristen und Termine)
- [gesetze-im-internet.de -- 187 BGB](https://www.gesetze-im-internet.de/bgb/__187.html) (Fristbeginn)
- [gesetze-im-internet.de -- 188 BGB](https://www.gesetze-im-internet.de/bgb/__188.html) (Fristende)

## Scope

Taxation of *andere Wirtschaftsgueter* disposed of within the one-year Jahresfrist -- in a
brokerage portfolio typically Gold and commodity ETCs and Crypto ETPs, which are claims on a
physical commodity or a crypto asset rather than securities under 20 EStG.

Also reaches foreign currency gains on non-interest-bearing accounts; see
[`../bmf-guidance/fremdwaehrung-konten.md`](../bmf-guidance/fremdwaehrung-konten.md).

---

## [GT-ESTG23-001] Abs. 1 Satz 1 Nr. 2 -- Other Assets (Andere Wirtschaftsgueter)

Statutory text, **Satz 1 Nr. 2 Satz 1**: *"Veraeusserungsgeschaefte bei anderen
Wirtschaftsguetern, bei denen der Zeitraum zwischen Anschaffung und Veraeusserung nicht mehr
als ein Jahr betraegt."*

**Exclusion (Nr. 2 Satz 2):** *"Ausgenommen sind Veraeusserungen von Gegenstaenden des
taeglichen Gebrauchs."*

> Retrieved 2026-08-02 from the official consolidated text at
> gesetze-im-internet.de/estg/__23.html. Umlauts transliterated per this library's
> convention. Note the citation form: the one-year rule is **Abs. 1 Satz 1 Nr. 2 Satz 1**, not
> "Abs. 1 Nr. 2" -- Abs. 1 has five Saetze of its own and Nr. 2 has four.

### Speculation Period Calculation

Two separate questions, with separate sources: *which dates* enter the calculation, and *how
the one-year period is measured* from them.

#### [GT-ESTG23-002] Which dates -- the obligatorisches Geschaeft (Tier 2)

**H 23 EStH, Stichwort "Veraeusserungsfrist"**: *"Fuer die Berechnung der Veraeusserungsfrist
des § 23 Abs. 1 EStG ist grundsaetzlich das der Anschaffung oder Veraeusserung zu Grunde
liegende obligatorische Geschaeft massgebend"* (BFH vom 15.12.1993 -- BStBl 1994 II S. 687,
und vom 8.4.2014 -- BStBl II S. 826 = IX R 18/13); *"ein ausserhalb der Veraeusserungsfrist
liegender Zeitpunkt des Eintritts einer aufschiebenden Bedingung des Veraeusserungsgeschaefts
ist unmassgeblich"* (BFH vom 10.2.2015 -- BStBl II S. 487 = IX R 23/13).

So the **binding contract date** counts, not the transfer of ownership and not settlement.

> Provenance: the official EStH at esth.bundesfinanzministerium.de is behind a bot filter
> that blocks automated retrieval; the H 23 text above was read off the steuerschroeder.de
> mirror of the official Hinweis on 2026-08-02. The three BFH decisions it cites are Tier 4
> and carry BStBl references, so the claim is checkable independently of the mirror.

The practical consequence for broker data: the **trade date** is the date the contract became
binding on both sides and is therefore the date this rule points at. The settlement date is not.

#### [GT-ESTG23-003] How the year is measured -- anniversary arithmetic (Tier 1)

§ 23 fixes no arithmetic of its own, so the general rule of the Abgabenordnung applies.

**§ 108 Abs. 1 AO:** *"Fuer die Berechnung von Fristen und fuer die Bestimmung von Terminen
gelten die §§ 187 bis 193 des Buergerlichen Gesetzbuchs entsprechend, soweit nicht durch die
Absaetze 2 bis 5 etwas anderes bestimmt ist."*

**§ 187 Abs. 1 BGB:** *"Ist fuer den Anfang einer Frist ein Ereignis oder ein in den Lauf
eines Tages fallender Zeitpunkt massgebend, so wird bei der Berechnung der Frist der Tag
nicht mitgerechnet, in welchen das Ereignis oder der Zeitpunkt faellt."*

**§ 188 Abs. 2 BGB:** *"Eine Frist, die nach Wochen, nach Monaten oder nach einem mehrere
Monate umfassenden Zeitraum - Jahr, halbes Jahr, Vierteljahr - bestimmt ist, endigt im Falle
des § 187 Abs. 1 mit dem Ablauf desjenigen Tages der letzten Woche oder des letzten Monats,
welcher durch seine Benennung oder seine Zahl dem Tage entspricht, in den das Ereignis oder
der Zeitpunkt faellt, [...]"*

**§ 188 Abs. 3 BGB:** *"Fehlt bei einer nach Monaten bestimmten Frist in dem letzten Monat
der fuer ihren Ablauf massgebende Tag, so endigt die Frist mit dem Ablauf des letzten Tages
dieses Monats."*

> All four retrieved verbatim 2026-08-02 from gesetze-im-internet.de (`__108.html` of
> ao_1977, `__187.html` and `__188.html` of bgb). Umlauts transliterated. The elision in
> Abs. 2 is the parallel clause for the § 187 Abs. 2 case, which does not apply here
> (an acquisition is an *Ereignis*, so § 187 Abs. 1 governs).

Applying them to an acquisition on day D:

1. § 187 Abs. 1 -- the acquisition day itself is **not counted**; the period runs from D+1.
2. § 188 Abs. 2 -- it ends with the **expiry of the anniversary day** in the following year:
   the day whose number matches D.
3. Therefore a disposal **on** the anniversary day is still *within* the year and taxable;
   the first exempt day is the day after.

**§ 188 Abs. 3 applies to a Jahresfrist as well**, even though it says *"nach Monaten
bestimmten Frist"*: Abs. 2 treats Monatsfristen and multi-month periods (*"Jahr, halbes Jahr,
Vierteljahr"*) as one case and lets both end on a day *"des letzten Monats"*, so Abs. 3's
correction for a missing day in that month covers both. Consequence: an acquisition on
**29 February** has no anniversary in a non-leap year, and the period ends on **28 February**.

Worked cases -- note that none of these is a 365-day count:

| Acquisition | Period ends | Disposal | Taxable? |
|---|---|---|---|
| 2022-03-15 | 2023-03-15 | 2023-03-15 (365 d) | yes -- anniversary day |
| 2022-03-15 | 2023-03-15 | 2023-03-16 (366 d) | no |
| 2023-07-01 | 2024-07-01 | 2024-07-01 (**366 d**, spans 29.02.2024) | **yes** -- anniversary day |
| 2023-07-01 | 2024-07-01 | 2024-07-02 (367 d) | no |
| 2024-02-29 | 2025-02-28 | 2025-02-28 (365 d) | yes -- § 188 Abs. 3 |
| 2024-02-29 | 2025-02-28 | 2025-03-01 (366 d) | no |
| 2023-02-28 | 2024-02-28 | 2024-02-29 (366 d) | no -- the 28th exists in 2024, Abs. 3 idle |

A `days <= 365` shortcut agrees with the statute except when the holding spans a 29 February,
where it wrongly exempts an anniversary-day disposal -- row three of the table above. Day
counting is not a safe substitute for the anniversary comparison.

#### [GT-ESTG23-004] Open question -- does § 108 Abs. 3 AO extend the Jahresfrist? (NOT resolved at Tier 1/2)

**§ 108 Abs. 3 AO:** *"Faellt das Ende einer Frist auf einen Sonntag, einen gesetzlichen
Feiertag oder einen Sonnabend, so endet die Frist mit dem Ablauf des naechstfolgenden
Werktags."*

If this applied to the Behaltefrist, an anniversary falling on a Saturday or Sunday would push
the end of the period to the following Monday -- and a Monday disposal, the first trading day
available, would still be **taxable**. The two readings differ on exactly the days a taxpayer
waiting out the year is most likely to trade.

Neither reading is settled at Tier 1 or Tier 2:

- **Tier 1 is silent on the boundary.** § 108 Abs. 3 AO says *"das Ende einer Frist"* without
  qualification, and § 108 Abs. 1 makes it a lex specialis to § 193 BGB (which *is* limited
  to periods for making a declaration or rendering performance). So the text does not
  exclude a materiell-rechtliche Frist.
- **Tier 2 does not decide it either.** AEAO zu § 108 Nr. 2 enumerates where the
  administration applies Abs. 3 -- the Bekanntgabe fictions of §§ 122/122a/123 AO, the
  Erklaerungsfrist (§ 149 AO) and the Festsetzungsfrist. § 23 EStG is not among them, but the
  list reads as confirmed applications rather than an exhaustive negative.
- **Tier 4 points both ways.** BFH vom 14.10.2003 -- IX R 68/98, BStBl II 2003, 898 abandoned
  the distinction between *eigentliche* (Handlungs-) and *uneigentliche* Fristen for
  § 108 Abs. 3 AO, holding that the wider civil-law concept of a Frist governs; BFH vom
  20.01.2016 -- VI R 14/15 extended that to the Festsetzungsfrist. Against that, **FG Koeln
  vom 02.06.1997, EFG 1997, 1187 (rkr.)** held there is *no* extension of the § 23 period when
  it ends on a Sunday or public holiday -- but it pre-dates IX R 68/98.
- **Tier 5** follows the FG: Littmann/Bitz/Pust, EStG § 23 Rn. 106 (EL 171, 02/2024) states
  *"Eine Verlaengerung der Frist kommt auch dann nicht in Frage, wenn das Fristende auf einen
  Sonntag oder einen gesetzlichen Feiertag faellt, da § 108 Abs 3 AO in diesem Fall nicht zur
  Anwendung kommt"*, citing that decision, and gives the practical rule that the period should
  be exceeded by at least one day. Never a sole source, and here it rests on the pre-2003 FG
  decision.

> The FG Koeln decision could not be retrieved in full text (no free source; the file number
> is not reported by the commentaries that cite it). It is recorded here as *reported by*
> Littmann/Bitz/Pust, not as read.

A further practical objection to the extension reading, independent of the authorities: § 108
Abs. 3 AO's *"gesetzlicher Feiertag"* is not uniform across the Laender, so applying it would
make the Jahresfrist depend on a Land-specific Feiertagskalender -- itself an unresolved input.

**Both readings are defensible and the difference changes a declared figure.** Where a disposal
falls between a weekend or holiday anniversary and the next working day, the figure should be
reviewed by hand. Registered in
[`../research/open-legal-questions.md`](../research/open-legal-questions.md).

#### [GT-ESTG23-005] Nr. 2 Satz 4 -- the ten-year period

*"Bei Wirtschaftsguetern im Sinne von Satz 1, aus deren Nutzung als Einkunftsquelle zumindest in
einem Kalenderjahr Einkuenfte erzielt werden, erhoeht sich der Zeitraum auf zehn Jahre."*

The one-year period is therefore conditional: an "anderes Wirtschaftsgut" that produced income in
even one calendar year carries a **ten**-year Frist. Gold and commodity ETCs and Crypto ETPs held
through a broker produce no income from the asset itself, so Satz 4 is idle for them -- but that
is a property of those instruments, not of the provision.

#### [GT-ESTG23-006] Nr. 3 -- disposal before acquisition

*"Veraeusserungsgeschaefte, bei denen die Veraeusserung der Wirtschaftsgueter frueher erfolgt als
der Erwerb."*

A short position in an "anderes Wirtschaftsgut" is a privates Veraeusserungsgeschaeft under
Nr. 3, and **Nr. 3 contains no holding period at all**. Applying the Nr. 2 Jahresfrist to a short
cover would exempt a short held longer than a year that Nr. 3 makes taxable.

### [GT-ESTG23-007] Inherited Assets (Unentgeltlicher Erwerb)
For assets acquired without consideration (gift, inheritance), the acquirer inherits the original acquisition date of the predecessor for purposes of this provision.

---

## Abs. 3 -- Gain Calculation and Exemption Threshold

### [GT-ESTG23-008] Gain Calculation
**Gain/Loss = Sale price - Acquisition/production costs - Advertising expenses (Werbungskosten)**

### [GT-ESTG23-009] Exemption Threshold (Freigrenze) -- Abs. 3 Satz 5

Statutory text: *"Gewinne bleiben steuerfrei, wenn der aus den privaten Veraeusserungsgeschaeften
erzielte Gesamtgewinn im Kalenderjahr weniger als 1 000 Euro betragen hat."*

> Retrieved 2026-08-03 from gesetze-im-internet.de/estg/__23.html. Note *"weniger als"* -- a
> Gesamtgewinn of exactly EUR 1 000 is **not** exempt.

**Amendment:** raised from EUR 600 to EUR 1 000 by the **Wachstumschancengesetz vom 27.03.2024
(BGBl. 2024 I Nr. 108)**, first applicable for **VZ 2024**.

> **Correction, 2026-08-03.** This file and `tax-forms/anlage-so-zeilen.md` previously credited
> the increase to the JStG 2024. That is wrong, and wrong in a way that is hard to spot: the
> JStG 2024 *did* amend § 23 (dejure amendment table, effective 06.12.2024), just not this
> figure. Amendment source: dejure.org/gesetze/EStG/23.html amendment table, entry
> "01.01.2024 -- Wachstumschancengesetz, 27.03.2024, BGBl. I Nr. 108". Validation Protocol
> item 3.

**Important:** This is a Freigrenze (exemption threshold), NOT a Freibetrag (allowance). If the
threshold is exceeded, the ENTIRE gain is taxable. It is applied to the Gesamtgewinn from all
private sales in the calendar year, which is a figure only the taxpayer's full return can
produce -- a single portfolio's gains are not necessarily the whole of it.

### [GT-ESTG23-010] Loss Offsetting (Satz 7-8)
- Losses may only be offset against gains from private sales (Abs. 1) in the same calendar year
- Losses may NOT be deducted under 10d EStG
- However, losses reduce private sale income in the immediately preceding assessment period or subsequent periods (per 10d EStG analogously)
- This creates a separate loss carryback/forward pool for 23 EStG

---

## [GT-ESTG23-011] Which instruments fall under 23 EStG rather than 20 EStG

| Instrument | Rationale |
|------------|-----------|
| Gold ETCs (e.g. Xetra-Gold) | A claim to delivery of physical gold, not a security under 20 EStG |
| Commodity ETCs | A claim on a physical commodity |
| Crypto ETPs | Tracks a crypto asset; an "anderes Wirtschaftsgut" |

These represent claims on physical commodities or crypto assets -- neither Kapitalforderungen nor
shares in corporations. The BFH has confirmed that Xetra-Gold is a claim to delivery of physical
gold, so gains and losses fall under 23 EStG rather than 20 EStG (BFH VIII R 4/15, VIII R 7/17,
VIII R 35/14).

The classification is per instrument and cannot be read off an asset class label: an ETC that is
cash-settled rather than physically backed may well be a Kapitalforderung under 20 EStG.

---

## [GT-ESTG23-012] Form placement

| Situation | Form | Line |
|-----------|------|------|
| Gain within the Jahresfrist | Anlage SO | Zeile 54 |
| Loss within the Jahresfrist | Anlage SO | Zeile 54 (negative) |
| Disposal after the Jahresfrist | not reported | outside 23 Abs. 1 Satz 1 Nr. 2 |

Line detail: [`../tax-forms/anlage-so-zeilen.md`](../tax-forms/anlage-so-zeilen.md),
[GT-FORM-020].
