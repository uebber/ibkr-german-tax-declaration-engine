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
