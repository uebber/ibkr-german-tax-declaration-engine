# BMF-Schreiben: Einzelfragen zur Abgeltungsteuer

## Source

- **Current version (14.05.2025):** [BMF-Schreiben Einzelfragen Abgeltungsteuer (PDF)](https://www.bundesfinanzministerium.de/Content/DE/Downloads/BMF_Schreiben/Steuerarten/Abgeltungsteuer/2025-05-14-einzelfragen-zur-abgeltungsteuer.pdf?__blob=publicationFile&v=2)
- **EStH 2024 Anhang 19 II:** [esth.bundesfinanzministerium.de -- Anhang 19 II](https://ao.bundesfinanzministerium.de/esth/2024/C-Anhaenge/Anhang-19/II/anhang-19-II.html)
- **EStH 2025 Anhang 19 II:** [esth.bundesfinanzministerium.de -- Anhang 19 II](https://esth.bundesfinanzministerium.de/esth/2025/B-Anhaenge/Anhang-19/II/inhalt.html)

## Scope

The central administrative guidance on capital income taxation. It carries the
Finanzverwaltung's interpretation of most of the edge cases § 20 EStG throws up: option
treatment, corporate actions, loss offsetting, currency gains, Stueckzinsen, lot identification.

This file is an **index into that document**, not a substitute for it. Where a Randziffer is
load-bearing, the verbatim text lives in the statute file it interprets, with its own retrieval
record; the pointers below say where to look.

---

## [GT-ESTG20-060] Version History

| Date | Reference | Notes |
|------|-----------|-------|
| 22.12.2009 | BStBl I 2010, S. 94 | Original Abgeltungsteuer guidance |
| 19.05.2022 | BStBl I 2022, S. 742 | Major rewrite |
| 20.12.2022 | BStBl I 2023, S. 46 | Amendment |
| 11.07.2023 | BStBl I 2023, S. 1471 | Amendment |
| 14.05.2025 | GZ IV C 1 - S 2252/00075/016/070 | Neufassung of the 19.05.2022 version; 137 pages, Rz. 1-325 |

The 14.05.2025 version is the current authoritative document. Its own opening line is
*"wird das BMF-Schreiben vom 19. Mai 2022 (BStBl I S. 742) wie folgt neu gefasst"*, and **Rz. 324**
names the three letters it displaces: *"vom 19. Mai 2022 (BStBl I S. 742), 20. Dezember 2022
(BStBl I 2023 S. 46) und vom 11. Juli 2023 (BStBl I S. 1471)"*.

> **Retrieved 2026-08-03.** The document had never been read in the course of building this
> library; both the 11.07.2023 Fundstelle and the supersession list above are taken from it. The
> earlier table marked two rows *"(BMF)"* for want of a citation.

### Application and Nichtbeanstandung

- **Rz. 324:** *"Fuer die Abgeltungsteuer auf Kapitalertraege und Veraeusserungsgewinne sind die
  Grundsaetze dieses Schreibens auf alle offenen Faelle anzuwenden. Im Uebrigen ist dieses
  Schreiben auf Kapitalertraege, die nach dem 31. Dezember 2008 zufliessen, sowie erstmals fuer
  den Veranlagungszeitraum 2009 anzuwenden."*
- **Rz. 325** permits Rz. 8, 8a, 23, 24, 26, 27, 30-32, 34, 36, 38, 42, 43, 46, 47, 59, 60, 61,
  61a, 63, 118, 194, 226, 227, 229a, 233 and 234 to be applied in the 19.05.2022 wording before
  01.01.2026 -- but **only *"Fuer den Kapitalertragsteuerabzug"***, which a foreign broker does not
  perform. It is not a Nichtbeanstandung for the Veranlagung.

### Randziffer numbering is version-specific

The 14.05.2025 text is a Neufassung, so its Randziffern do not necessarily carry the 19.05.2022
numbering. **Every citation into this document must name the document date.** All Randziffern
cited anywhere in this library are from the 14.05.2025 version unless stated otherwise.

---

## Key topics

### I. Kapitalvermoegen (20 EStG)

1. **Dividenden** (20 Abs. 1 Nr. 1) -- treatment of stock dividends, scrip dividends, Einlagenrueckgewaehr
2. **Zinsen** (20 Abs. 1 Nr. 7) -- includes Stueckzinsen treatment
3. **Stillhalterpraemien** (20 Abs. 1 Nr. 11) -- option premium taxation, Glattstellung as negative income
4. **Veraeusserungsgewinne** (20 Abs. 2) -- partial sales
5. **Termingeschaefte** (20 Abs. 2 Nr. 3) -- derivative taxation, cash settlement, exercise
6. **Gewinnermittlung** (20 Abs. 4) -- acquisition cost determination, transaction costs;
   **Fifo-Methode Rz. 97-99** (section I.4.b), see below
7. **Kapitalmasnahmen** (20 Abs. 4a) -- corporate action treatment (mergers, splits, spin-offs)
8. **Verlustverrechnung** (20 Abs. 6) -- loss offsetting rules including stock ring-fencing

### Specific interpretations

#### [GT-ESTG20-038] What counts as a Termingeschaeft (Rz. 9)

Rz. 9 defines the term the statute leaves open. A Termingeschaeft is any financial instrument
structured as an Options- or Festgeschaeft, settled with a time delay, whose price depends
directly or indirectly on one of five listed Bezugsgroessen. Two of the five bear on contracts
over currencies and precious metals:

- *"dem Kurs von **Devisen** oder Rechnungseinheiten"*
- *"dem Boersen- oder Marktpreis von Waren oder **Edelmetallen**"*

The Randziffer then enumerates the forms, and the enumeration is explicit rather than analogical:

> *"Zu den Termingeschaeften gehoeren insbesondere Optionsgeschaefte, Swaps,
> Devisentermingeschaefte und Forwards oder Futures, vgl. Rn. 36 und 37 sowie **Contracts for
> Difference (CFDs)**. CFDs sind Vertraege zwischen zwei Parteien, die auf die Kursentwicklung
> eines bestimmten Basiswerts spekulieren. Basiswerte koennen beispielsweise Aktien, Indizes,
> **Waehrungspaare** oder Zinssaetze sein. Zertifikate und Optionsscheine gehoeren nicht zu den
> Termingeschaeften, vgl. Rn. 8 f."*

**A CFD on a currency pair is therefore a Termingeschaeft twice over** -- once through the Devisen
Bezugsgroesse, once through the named Basiswert. A CFD on a precious metal falls under the
Edelmetalle Bezugsgroesse.

**The negative boundary is stated in the same sentence and matters as much:** Zertifikate and
Optionsscheine are *not* Termingeschaefte (Rn. 8 f.). The enumeration is *"insbesondere"*, so it
is open -- but the two exclusions are closed.

What the cited unit also contains: the remaining three Bezugsgroessen (Boersen-/Marktpreis of
Wertpapiere and of Geldmarktinstrumente, and Zinssaetze oder andere Ertraege), and a
cross-reference to Rn. 36-37 for Forwards and Futures.

Applicable tax years: the 14.05.2025 version applies to all open cases unless a Randziffer says
otherwise; the Termingeschaeft definition is not year-limited. Retrieved 2026-08-05 from
https://www.bundesfinanzministerium.de/Content/DE/Downloads/BMF_Schreiben/Steuerarten/Abgeltungsteuer/2025-05-14-einzelfragen-zur-abgeltungsteuer.pdf
(page 9 of 137).

#### Options (Rz. 9-47; the load-bearing ones are 25-27)
- Stillhalterpraemie taxable upon receipt (Nr. 11) -- Rz. 25
- Glattstellung: premiums paid and their Nebenkosten are negative Kapitalertrag *"zum Zeitpunkt
  der Zahlung"* -- Rz. 25
- Exercise (physical delivery) by the Stillhalter: a disposal of the Basiswert under Abs. 2, and
  the premium *"wird bei der Ermittlung des Veraeusserungsgewinns nicht beruecksichtigt"* -- Rz. 26
- Expiration worthless (long): the acquisition cost is taken into account under **20 Abs. 4
  Satz 5** -- Rz. 27, also for a knock-out expiry
- Expiration worthless (short): no further tax consequence beyond the premium already taxed
- Cash settlement by the Stillhalter: loss from a Termingeschaeft under **20 Abs. 2 Satz 1 Nr. 3
  Buchstabe a** -- Rz. 26, citing BFH vom 20.10.2016 - VIII R 55/13, BStBl II 2017 S. 264

> **Correction, 2026-08-03.** The cash-settlement line read *"20 Abs. 2 Nr. 3a"*. There is no
> Nr. 3a in Abs. 2 -- see [GT-ESTG20-007]. Rz. 26 writes the pinpoint out in full.

#### Lot identification (Fifo-Methode, Rz. 97-99)
- Rz. 97: FIFO under 20 Abs. 4 S. 7 is applied **auf das einzelne Depot bezogen**; a
  customer instruction naming which security to sell is *einkommensteuerrechtlich
  unbeachtlich*
- Rz. 98: an **Unterdepot** counts as a Depot (independent subdivision with its own running
  number); the customer **may** determine which securities are allocated to which depot
- Rz. 99: Fifo applies to **Streifbandverwahrung** as well
- Wording is identical in the 18.01.2016 version -- stable practice, not a 2025 change
- Full verbatim text: [estg-20-kapitalvermoegen.md](../tax-law/estg-20-kapitalvermoegen.md),
  [GT-ESTG20-013]

#### [GT-ESTG20-039] The moment a disposal is measured (Rn. 85)

> *"Der Zeitpunkt, in dem das der Veraeusserung/Einloesung zugrundeliegende obligatorische
> Rechtsgeschaeft abgeschlossen wird, ist der massgebliche Zeitpunkt fuer die Waehrungsumrechnung
> und die Berechnung des steuerlichen Veraeusserungs- bzw. Einloesungsgewinns oder -verlustes
> sowie fuer die Freistellungsauftragsverwaltung und die Verlustverrechnung."*

The **obligatorisches Rechtsgeschaeft** -- the day the contract is struck, not the day it settles
-- fixes four things at once: the currency-conversion rate, the computation of the gain or loss,
the Freistellungsauftrag, and the loss offsetting. Two of the four decide declared figures for a
holder without a domestic withholding agent: the rate and the gain. The remaining two are
Steuerabzug administration.

Because it fixes the day, it also fixes the **assessment year** whenever contract and settlement
straddle a year end.

What the cited unit also contains: nothing further; Rn. 85 is one Satz. The following Rn. 85a is a
separate point on Vorschusszinsen as Veraeusserungskosten. **Rn. 85 addresses only the disposal
side** -- *"Veraeusserung/Einloesung"*; for the acquisition side see [GT-ESTG20-040].

Applicable tax years: all open cases, per Rn. 324. Retrieved 2026-08-07 from the 14.05.2025 PDF,
page 39 of 137.

#### [GT-ESTG20-040] What counts as *Erwerb* (Rn. 317)

> *"§ 23 Absatz 1 Satz 1 Nummer 2 EStG a. F. ist letztmals auf private Veraeusserungsgeschaefte mit
> Wertpapieren anzuwenden, die vor dem 1. Januar 2009 erworben wurden. Der Begriff des Erwerbs
> beinhaltet den Tatbestand des 'rechtswirksam abgeschlossenen obligatorischen Vertrags oder
> gleichstehenden Rechtsaktes'."*

The second Satz defines *Erwerb* for Wertpapiere as the **rechtswirksam abgeschlossener
obligatorischer Vertrag** -- the same criterion Rn. 85 applies to the disposal side, so acquisition
and disposal are measured symmetrically at the contract, not at settlement.

**Weigh the context before leaning on it.** The definition is given inside a § 52 application rule
about which Wertpapiere still fall under § 23 a. F., so it is stated for a transitional purpose
even though the definition itself is general in form. It is the only administrative definition of
*Erwerb* for securities located in this document.

**Tier 4 support, which does not stand alone.** For § 23 EStG it is staendige Rechtsprechung that
both ends of the period are the moments the obligatorische Vertraege were concluded, not the
transfer of wirtschaftliches Eigentum and not Erfuellung: BFH vom 08.04.2014 -- IX R 18/13,
BFHE 245, 323, BStBl II 2014, 826, Rz 29, continuing BFH vom 15.12.1993 -- X R 49/91,
BStBl II 1994, 687 and BFH vom 08.04.2003 -- IX R 1/01. The reasoning given is that the taxpayer
has secured the increase in value with the Verpflichtungsgeschaeft. The located decisions concern
Grundstuecke under Nr. 1; the principle is stated generally.

**No located source puts the acquisition day at settlement**, on any reading.

What the cited unit also contains: the first Satz, the § 52 cut-off itself. The following Rn. 318
is a separate transitional rule on Umtausch- and Aktienanleihen in 2008/2009.

Applicable tax years: all open cases, per Rn. 324. Retrieved 2026-08-07 from the 14.05.2025 PDF,
page 130 of 137.

#### [GT-ESTG20-041] Acquisition data of Investmentanteile are held per acquisition (Rn. 184a)

On a transfer of Investmentanteile between custodians, the data to be passed on is enumerated:

> *"Unter den Begriff der Anschaffungsdaten sind saemtliche bei Anschaffung der Investmentanteile
> vorliegenden Daten zu fassen. Im Einzelnen sind die folgenden Anschaffungsdaten zu uebermitteln:
> - der Anschaffungszeitpunkt,
> - die Anschaffungskosten (Ausgabepreis oder bei einem Erwerb auf dem Sekundaermarkt der
>   Kaufpreis einschliesslich Anschaffungsnebenkosten) der zum jeweiligen Anschaffungszeitpunkt
>   erworbenen Investmentanteile,
> - die Anzahl der zum jeweiligen Anschaffungszeitpunkt erworbenen Investmentanteile (sofern
>   zwischenzeitlich eine steuerneutrale Fondsverschmelzung vorgenommen wurde: die Anzahl der
>   erworbenen Anteile unter Beruecksichtigung des Umtauschverhaeltnisses der
>   Fondsverschmelzung)."*

Two things follow, and both decide figures.

**A holding of one fund is administered as several acquisitions, each with its own date and its
own unit count.** The repeated *"zum jeweiligen Anschaffungszeitpunkt"* presupposes more than one
acquisition point within a single holding. This is the data on which § 18 Abs. 2 InvStG's
reduction operates -- see [GT-INVSTG-011].

**A steuerneutrale Fondsverschmelzung does not create a new acquisition point.** Only the *count*
is restated, *"unter Beruecksichtigung des Umtauschverhaeltnisses"*; the Anschaffungszeitpunkt
carried in the Anschaffungsdaten is the original one. So units received in a fund merger keep the
acquisition date of the units given up.

What the cited unit also contains: a further requirement to notify the Zwischengewinn for
transfers up to 31.12.2017 under the InvStG in its then-applicable version; a Nichtbeanstandung
allowing the receiving institution to determine the Immobiliengewinn from the Anschaffungszeitpunkt
rather than have it transmitted; and correction figures for units acquired in a pre-2018
steuerneutrale Verschmelzung under §§ 14, 17a InvStG a. F. All three are Steuerabzug mechanics
between custodians.

Applicable tax years: all open cases, per Rn. 324. Retrieved 2026-08-07 from the 14.05.2025 PDF,
pages 80-81 of 137.

#### Corporate Actions
- Stock-for-stock merger: steuerneutral, cost basis rollover (20 Abs. 4a)
- Cash merger: taxable disposal
- Stock split: proportional cost basis adjustment, no taxable event
- Stock dividend: treatment depends on whether domestic or foreign corporation

#### Foreign Withholding Tax
- Creditable under 32d Abs. 5, subject to treaty limitations
- Report on Zeile 41 Anlage KAP

---

## Applicability

This BMF-Schreiben represents the **Finanzverwaltung's binding interpretation**
(Verwaltungsauffassung). While not law itself (Tier 2), tax offices are bound by it. Taxpayers can
deviate but may face dispute.

Where it and a statute diverge, the statute governs and the divergence is a point to record, not
to resolve silently.
