# EStG 20 -- Einkuenfte aus Kapitalvermoegen

## Source

- **Primary:** [gesetze-im-internet.de -- 20 EStG](https://www.gesetze-im-internet.de/estg/__20.html)
- **With annotations:** [dejure.org -- 20 EStG](https://dejure.org/gesetze/EStG/20.html)
- **Current version:** As amended by Jahressteuergesetz 2024 (BGBl. I 2024 Nr. 387), effective 01.01.2025

## Scope

The central statute for capital income. It defines what constitutes capital income (Abs. 1),
capital gains (Abs. 2), gain calculation (Abs. 4), corporate action treatment (Abs. 4a), and
loss offsetting (Abs. 6, in its own file).

---

## Abs. 1 -- Income Types (Laufende Einkuenfte)

### [GT-ESTG20-001] Nr. 1 -- Dividends
Dividends and other distributions from corporations (Koerperschaften).

### [GT-ESTG20-002] Nr. 3 -- Investmentertraege
*"Investmentertraege nach § 16 des Investmentsteuergesetzes"*. This is the hook through which all
fund income (Ausschuettungen, Vorabpauschale, Veraeusserungsgewinne) becomes Einkuenfte aus
Kapitalvermoegen, and it is why fund income is declared on Anlage KAP-INV rather than Anlage KAP.
Nr. 3a does the same for Spezial-Investmentertraege nach § 34 InvStG.

### [GT-ESTG20-003] Nr. 7 -- Interest
Interest from capital claims of any kind (Kapitalforderungen jeder Art).

### [GT-ESTG20-004] Nr. 11 -- Stillhalterpraemien (Option Premiums)
Premiums received for granting options (Einraeumung von Optionen).

Statutory text (retrieved 2026-08-03): *"Stillhalterpraemien, die fuer die Einraeumung von
Optionen vereinnahmt werden; schliesst der Stillhalter ein Glattstellungsgeschaeft ab, sind die
im Glattstellungsgeschaeft gezahlten Praemien zum Zeitpunkt der Zahlung als negative Einnahmen zu
beruecksichtigen."*

Key rules:
- Premium is taxable upon receipt under Abs. 1 Nr. 11
- Glattstellungsgeschaeft (closing/buy-back): paid premium is a **negative Einnahme at the time
  of payment**. See the timing caveat below -- the *from when* is not settled here.
- Physical exercise: premium does NOT reduce under Nr. 11; the Stillhalter has a Veraeusserungs-
  geschaeft in the Basiswert under Abs. 2, and *"die vereinnahmte Optionspraemie ... wird bei der
  Ermittlung des Veraeusserungsgewinns nicht beruecksichtigt"* (BMF 14.05.2025 Rz. 26)
- Barausgleich (cash settlement) by Stillhalter: loss from a Termingeschaeft under **Abs. 2 Satz 1
  Nr. 3 Buchstabe a** -- BMF 14.05.2025 Rz. 26 states that pinpoint expressly, citing **BFH-Urteil
  vom 20.10.2016 - VIII R 55/13, BStBl II 2017 S. 264**

> **Correction, 2026-08-03.** The Barausgleich bullet previously cited *"Abs. 2 Satz 1 Nr. 3a"*.
> **There is no Nr. 3a in Abs. 2** -- see [GT-ESTG20-007]. The BFH decision was also cited by file
> number alone, with no date and no Fundstelle, so it could not be checked. Both taken from BMF
> 14.05.2025 Rz. 26, retrieved and read 2026-08-03. Validation Protocol items 1 and 2.

#### Open question -- from which VZ does the "negative Einnahmen" wording apply? (NOT resolved)

The *"zum Zeitpunkt der Zahlung als negative Einnahmen"* wording was put into the statute by the
**JStG 2024**, displacing BFH v. 02.08.2022 - VIII R 27/21, which had held that Glattstellung
costs reduce the Stillhalterpraemien **in the VZ the premium was received** (a rueckwirkendes
Ereignis under 175 Abs. 1 S. 1 Nr. 2 AO), not in the VZ of payment. The two readings put the
same amount in different years, so this changes a declared figure whenever the two legs straddle
a year end.

What is not established:

- buzer.de lists **two** JStG-2024 versions of § 20 EStG -- one effective **06.12.2024**
  (Art. 3) and one effective **01.01.2025** (Art. 4) -- and does not say which carried Nr. 11.
- No application rule in § 52 EStG for Nr. 11 has been located.
- Tier 5 sources disagree openly: Haufe Finance Office states application from 01.01.2024; Haufe
  Steuer Office Excellence states from the day after promulgation.

The administration's practice, even before the amendment, was to book the paid premium at the
payment date (BMF 18.01.2016 Rz. 25 ff., carried into BMF 19.05.2022 and 14.05.2025). That is
the reading the new statutory wording adopts, and it is contrary to BFH VIII R 27/21 for any VZ
before the amendment took effect. **A straddling Stillhalter/Glattstellung pair in VZ 2024 or
earlier should be reviewed by hand.** Registered in `research/open-legal-questions.md`.

> **Correction, 2026-08-03.** This section previously asserted the change was "codified in
> statute effective 01.01.2024" as settled fact. The codification is real; the date was
> unsourced, contradicted this file's own header (JStG 2024, effective 01.01.2025), and is
> disputed. Validation Protocol items 3 and 7.

---

## Abs. 2 -- Capital Gains (Veraeusserungsgewinne)

### [GT-ESTG20-005] Satz 1 Nr. 1 -- Sale of shares in corporations (Aktien)
Gains from sale of shares in any corporation (Koerperschaft, Personenvereinigung, Vermoegensmasse).

### [GT-ESTG20-006] Satz 1 Nr. 2 -- Sale of Dividenden-/Zinsscheine apart from the Stammrecht

**Not bonds.** Nr. 2 covers the sale of *"Dividendenscheinen und sonstigen Anspruechen durch den
Inhaber des Stammrechts, wenn die dazugehoerigen Aktien oder sonstigen Anteile nicht
mitveraeussert werden"* (Buchst. a) and of *"Zinsscheinen und Zinsforderungen durch den Inhaber
oder ehemaligen Inhaber der Schuldverschreibung, wenn die dazugehoerigen Schuldverschreibungen
nicht mitveraeussert werden"* (Buchst. b) -- i.e. a coupon or dividend claim detached from the
security it belongs to.

> Retrieved 2026-08-03 from gesetze-im-internet.de/estg/__20.html.

> **Correction, 2026-08-03.** This entry previously read "Sale of other capital claims -- gains
> from sale of interest-bearing instruments (Anleihen, Zertifikate, etc.)". That is Nr. 7, not
> Nr. 2 -- as this same file states correctly under "Satz 1 Nr. 7" and again in the Satz 2
> section below. The file contradicted itself, and the wrong half was the one being relied on.
> Validation Protocol item 2.

### [GT-ESTG20-007] Satz 1 Nr. 3 -- Termingeschaefte (Derivatives)

**Nr. 3 has two Buchstaben and no Nummer 3a.** Statutory text (retrieved 2026-08-03):

- **Buchst. a:** *"der Gewinn bei Termingeschaeften, durch die der Steuerpflichtige einen
  Differenzausgleich oder einen durch den Wert einer veraenderlichen Bezugsgroesse bestimmten
  Geldbetrag oder Vorteil erlangt"* -- this is the limb that catches **Barausgleich / cash
  settlement**.
- **Buchst. b:** *"der Gewinn aus der Veraeusserung eines als Termingeschaeft ausgestalteten
  Finanzinstruments"* -- the disposal of the instrument itself, as distinct from settling it.

The gain figure for a Termingeschaeft is not computed under Abs. 4 Satz 1 but under **Abs. 4
Satz 5** -- see [GT-ESTG20-023].

> **Correction, 2026-08-03.** This entry previously read *"Sub-section 3a: Gains from Barausgleich
> (cash settlement) of Termingeschaefte"*, and the citation *"Abs. 2 Satz 1 Nr. 3a"* was repeated
> under [GT-ESTG20-004], in `../bmf-guidance/abgeltungsteuer-einzelfragen.md` and in
> `../research/coverage-matrix.md`. **Abs. 2 Satz 1 has no Nummer 3a**; the Nummern run 1-8 and
> Nr. 3 is subdivided by Buchstaben. The confusable neighbour is Abs. **1** Nr. 3a
> (Spezial-Investmentertraege), which does exist and is a different thing entirely. Verified
> against gesetze-im-internet.de/estg/__20.html and against the table of contents and Rz. 26 of
> BMF 14.05.2025, which writes *"§ 20 Absatz 2 Satz 1 Nummer 3 Buchstabe a EStG"* in full.
> Corrected in all four places together (Validation Protocol items 2 and 8). Buchst. b was also
> unstated -- item 2.

### [GT-ESTG20-008] Satz 1 Nr. 7 -- Gains from capital claims
Gains from redemption/sale of capital claims (Kapitalforderungen jeder Art).

Statutory text: *"der Gewinn aus der Veraeusserung von sonstigen Kapitalforderungen jeder Art im Sinne des Absatzes 1 Nummer 7"*

### [GT-ESTG20-009] Satz 2 -- Disposal fiction (Einloesung, Rueckzahlung, Abtretung)

**This is the provision that makes a bond redemption at maturity a taxable disposal.**

Statutory text: *"Als Veraeusserung im Sinne des Satzes 1 gilt auch die Einloesung, Rueckzahlung, Abtretung oder verdeckte Einlage in eine Kapitalgesellschaft; in den Faellen von Satz 1 Nummer 4 gilt auch die Vereinnahmung eines Auseinandersetzungsguthabens als Veraeusserung."*

> Verified 2026-08-02 against two Tier 1 sources: gesetze-im-internet.de/estg/__20.html
> and dejure.org/gesetze/EStG/20.html (wording, semicolon and word order agree).
> Version status: as amended by JStG 2024 (BGBl. I 2024 Nr. 387), effective 01.01.2025.
> Note Abs. 2 continues past Satz 2 -- Saetze 3-5 cover Personengesellschaft interests
> and the separation of Zinsschein/Zinsforderung from the Stammrecht; Satz 2 is not the
> end of the Absatz.

Satz 2 applies to **all** of Satz 1, including Nr. 7. Consequently:

| Event | Mechanism | Gain category |
|-------|-----------|---------------|
| Bond sold before maturity | Veraeusserung (Satz 1 directly) | Satz 1 Nr. 7 |
| Bond redeemed at maturity (Faelligkeit) | **Einloesung, deemed Veraeusserung by Satz 2** | Satz 1 Nr. 7 |
| Bond repaid early (Rueckzahlung) | **deemed Veraeusserung by Satz 2** | Satz 1 Nr. 7 |

Gain is computed under Abs. 4 (Veraeusserungserloes minus Veraeusserungskosten minus
Anschaffungskosten). Bonds are not Aktien, so the Abs. 6 Satz 4 ring-fencing does not apply.

**Correct citation for bond maturity is therefore `Abs. 2 Satz 1 Nr. 7 i.V.m. Satz 2`.**
Citing Satz 1 Nr. 7 alone is incomplete -- it establishes the gain category but not
that a redemption counts as a disposal at all.

#### Form placement (Tier 3 -- verified against the official Anleitung)

Verified against BOTH assessment years held in this repository: Anleitung zur Anlage KAP **2024**
(`reference/Anltg_KAP_24.md`, Zeilen 18/19) and **2025** (`reference/Anltg_KAP_25.md`,
same wording at Zeile 19 and the identical "zusaetzlich" rule). The placement below is
unchanged by JStG 2024 -- that amendment removed Zeilen 21/24 (Termingeschaefte), which
bonds never used.

Anleitung zur Anlage KAP 2024, Zeilen 18/19:

- Zeile 18 takes **inlaendische** Kapitalertraege not yet subject to Steuerabzug by an
  inlaendische Zahlstelle.
- Zeile 19 takes **auslaendische** Ertraege, *"insbesondere Ertraege bei auslaendischen
  Kreditinstituten"*.
- *"Alle Veraeusserungstatbestaende tragen Sie bitte zusaetzlich in die Zeilen 20
  und / oder 22 und / oder 23 ein."*

The Z18/Z19 split turns on the **intermediary** (broker location), NOT on issuer domicile
-- see `reference/research/inlaendisch-auslaendisch-relevance.md`. Income received through a
foreign broker lands in Zeile 19 regardless of where the bond issuer sits. **The placement is
conditional on that fact**; it is not a property of bond maturities as such. A bond redeemed
through a German Zahlstelle would belong in Zeile 18.

Applying the "zusaetzlich" rule: a bond maturity **gain** nets into Zeile 19 only (Zeile 20
is reserved for Aktien). A bond maturity **loss** subtracts within Zeile 19 and is
additionally entered in Zeile 22 as a positive amount (Zeile 23 is reserved for Aktien).

---

## [GT-ESTG20-010] Abs. 3 -- Special Benefits

**Satz 1:** Special benefits or advantages (*besondere Entgelte oder Vorteile*) granted in addition
to, or in place of, the income described in Abs. 1 and 2 are also Einkuenfte aus Kapitalvermoegen.

**Satz 2** (previously unstated -- Validation Protocol item 2): such a benefit also exists *"wenn
Bestandsprovisionen, Verwaltungsentgelte oder sonstige Aufwendungen durch den Schuldner der
Kapitalertraege nach Absatz 1 oder 2 oder durch einen Dritten erstattet werden"* -- a rebate of
trailer fees or management charges is itself taxable capital income.

**Abs. 3a exists and is not Abs. 3.** It directs that corrections within the meaning of § 43a
Abs. 3 Satz 7 are taken into account only at the time named there (Satz 1), and that where the
auszahlende Stelle certifies it has not made and will not make the correction, the taxpayer may
claim it under § 32d Abs. 4 und 6 (Satz 2). Both are addressed to a Steuerabzug that a foreign
broker does not perform. Recorded because the Absatz sits between two that this file does state.

---

## Abs. 4 -- Gain Calculation

### [GT-ESTG20-011] Satz 1 erster Halbsatz -- the gain

**Gain = Sale proceeds - Transaction costs - Acquisition costs (Anschaffungskosten)**

Statutory text: *"Gewinn im Sinne des Absatzes 2 ist der Unterschied zwischen den Einnahmen aus
der Veraeusserung nach Abzug der Aufwendungen, die im unmittelbaren sachlichen Zusammenhang mit
dem Veraeusserungsgeschaeft stehen, und den Anschaffungskosten"*.

Note the deduction is limited to costs standing in an *unmittelbarer sachlicher Zusammenhang* with
the disposal. It is not a general Werbungskostenabzug -- Abs. 9 excludes that.

#### What the other eight Saetze of Abs. 4 contain (Validation Protocol item 2)

Abs. 4 has **nine Saetze**, and three of them carry rules of their own that this library states
separately because a figure turns on each:

| Satz | Content | Where stated |
|---|---|---|
| 1, 1. Hs. | the gain | here, [GT-ESTG20-011] |
| 1, 2. Hs. | **currency conversion, leg by leg** | [GT-ESTG20-022] |
| 2 | verdeckte Einlage: gemeiner Wert replaces the proceeds; gain assessed in the calendar year of the Einlage | -- |
| 3 | asset moved into Privatvermoegen by Entnahme/Betriebsaufgabe: the § 6 Abs. 1 Nr. 4 or § 16 Abs. 3 value replaces the Anschaffungskosten | -- |
| 4 | Abs. 2 Satz 1 Nr. 6 (Versicherungsleistungen): contributions count as Anschaffungskosten | -- |
| 5 | **the gain on a Termingeschaeft** | [GT-ESTG20-023] |
| 6 | unentgeltlicher Erwerb: the predecessor's acquisition is attributed to the Einzelrechtsnachfolger | -- |
| 7 | **FIFO fiction** | [GT-ESTG20-012] |
| 8, 9 | Zinsschein separated from the Stammrecht, and the allocation of that value | -- |

Saetze 2, 3, 4 and 6 do not reach a directly held private portfolio bought for consideration.

### [GT-ESTG20-022] Satz 1 zweiter Halbsatz -- currency conversion, each leg at its own date

Statutory text: *"bei nicht in Euro getaetigten Geschaeften sind die Einnahmen im Zeitpunkt der
Veraeusserung und die Anschaffungskosten im Zeitpunkt der Anschaffung in Euro umzurechnen."*

> Retrieved 2026-08-03 from gesetze-im-internet.de/estg/__20.html.

This is the Tier 1 basis for converting a foreign-currency disposal: **the two legs are translated
at two different dates**, the proceeds at the disposal date and the cost at the acquisition date.
The gain is therefore computed in EUR and necessarily carries the currency movement between the
two dates; it is not a foreign-currency difference translated once.

The provision fixes *that* each leg is converted at its own moment. It does **not** name an
exchange-rate source, and no Tier 1 or Tier 2 source prescribing one for the Veranlagung has been
located -- BMF 14.05.2025 Rz. 247 prescribes the *Devisenbriefkurs* only for the
Kapitalertragsteuerabzug by an inlaendische Zahlstelle, which is a different operation.

> **Added 2026-08-03 (Validation Protocol item 2).** Abs. 4 Satz 1's second Halbsatz was absent
> from this library, which stated only the first. The omission is the load-bearing kind: every
> figure derived from a non-EUR transaction depends on this sentence, and the store carried no
> ground truth for it at all.

### [GT-ESTG20-023] Satz 5 -- the gain on a Termingeschaeft

Statutory text: *"Gewinn bei einem Termingeschaeft ist der Differenzausgleich oder der durch den
Wert einer veraenderlichen Bezugsgroesse bestimmte Geldbetrag oder Vorteil abzueglich der
Aufwendungen, die im unmittelbaren sachlichen Zusammenhang mit dem Termingeschaeft stehen."*

> Retrieved 2026-08-03 from gesetze-im-internet.de/estg/__20.html.

A Termingeschaeft gain is **not** computed by the Satz 1 proceeds-minus-basis formula. The measure
is the Differenzausgleich (or the value-linked amount) less directly related expenses. BMF
14.05.2025 Rz. 27 applies the same Satz to the **expiry of a long option**: *"sind die fuer den
Erwerb der Kaufoption entstandenen Aufwendungen bei der Ermittlung des Gewinns (oder Verlusts) im
Sinne des § 20 Absatz 4 Satz 5 EStG zu beruecksichtigen"* (BFH vom 12.01.2016 - IX R 48/14,
IX R 49/14, IX R 50/14, BStBl II S. 456, 459, 462), including a knock-out expiry.

> **Added 2026-08-03 (Validation Protocol item 2).** The library stated only the Abs. 4 Satz 1
> formula and applied it to derivatives by implication. Satz 5 is the provision that actually
> governs them, and it is the one the administration cites for a worthless expiry.

### [GT-ESTG20-012] Satz 7 -- FIFO fiction (Verbrauchsreihenfolge)

Statutory text: *"Bei vertretbaren Wertpapieren, die einem Verwahrer zur Sammelverwahrung
im Sinne des § 5 des Depotgesetzes [...] anvertraut worden sind, ist zu unterstellen, dass
die zuerst angeschafften Wertpapiere zuerst veraeussert wurden."*

> Verified 2026-08-02 against two Tier 1 sources: gesetze-im-internet.de/estg/__20.html
> (full sentence, extracted from the official HTML) and dejure.org/gesetze/EStG/20.html
> (operative clause and Depotgesetz condition agree).
> Sentence position confirmed by the official numbering: Satz 7 of 9. Satz 8 concerns a
> Zinsschein separated from the Stammrecht, Satz 9 the allocation of that value -- neither
> continues the FIFO rule.
> Umlauts are transliterated per this library's convention. The elision `[...]` is the
> Depotgesetz version citation, verbatim: *"in der Fassung der Bekanntmachung vom
> 11. Januar 1995 (BGBl. I S. 34), das zuletzt durch Artikel 4 des Gesetzes vom
> 5. April 2004 (BGBl. I S. 502) geaendert worden ist, in der jeweils geltenden Fassung"*.

What the statute does and does not say:

- It **is mandatory** -- *"ist zu unterstellen"* is a Fiktion, not a default that the
  taxpayer may rebut.
- It does **not** say "per Depot". The only occurrence of "Depot" in Satz 7 is inside the
  citation *"Depotgesetzes"*. Depot-relatedness comes from Tier 2 (below), not from the
  statute.
- It does **not** offer a specific-identification alternative. Its only condition is the
  form of custody (Sammelverwahrung per § 5 DepotG).

#### [GT-ESTG20-013] Depot-relatedness (Tier 2 -- BMF, this is where "je Depot" comes from)

BMF-Schreiben vom 14. Mai 2025, GZ IV C 1 - S 2252/00075/016/070, *"Einzelfragen zur
Abgeltungsteuer"*, section I.4.b **Rz. 97-99**. Neufassung of BMF 19.05.2022
(BStBl I S. 742). The wording is **identical** in BMF 18.01.2016, so this is stable
administrative practice across both, not a recent change.

Rz. 97: *"Gemaess § 20 Absatz 4 Satz 7 EStG ist bei Wertpapieren bei der Veraeusserung aus
der Girosammelverwahrung (§§ 5 ff. DepotG) zu unterstellen, dass die zuerst angeschafften
Wertpapiere zuerst veraeussert werden (Fifo-Methode). Die Anwendung der Fifo-Methode im
Sinne des § 20 Absatz 4 Satz 7 EStG ist auf das einzelne Depot bezogen anzuwenden. Konkrete
Einzelweisungen des Kunden, welches Wertpapier veraeussert werden soll, sind insoweit
einkommensteuerrechtlich unbeachtlich."*

Rz. 98: *"Als Depot im Sinne dieser Regelung ist auch ein Unterdepot anzusehen. Bei einem
Unterdepot handelt es sich um eine eigenstaendige Untergliederung eines Depots mit einer
laufenden Unterdepot-Nummer. Der Kunde kann hierbei die Zuordnung der einzelnen Wertpapiere
zum jeweiligen Depot bestimmen."*

Rz. 99: *"Die Fifo-Methode gilt auch bei der Streifbandverwahrung."*

| Question | Answer | Source |
|----------|--------|--------|
| Is FIFO mandatory? | Yes -- Fiktion, not a default | Abs. 4 S. 7 (Tier 1) |
| May the taxpayer designate which lot is sold? | **No** -- *einkommensteuerrechtlich unbeachtlich* | Rz. 97 S. 3 (Tier 2) |
| Is FIFO pooled across depots, or per depot? | **Per single depot** | Rz. 97 S. 2 (Tier 2) |
| Does a sub-depot count as a depot? | **Yes**, if an independent subdivision with its own running number | Rz. 98 (Tier 2) |
| May the taxpayer choose which depot a security sits in? | **Yes** | Rz. 98 S. 3 (Tier 2) |
| Does FIFO also apply outside Sammelverwahrung? | Yes, also to Streifbandverwahrung | Rz. 99 (Tier 2) |

The pairing of Rz. 97 S. 3 with Rz. 98 S. 3 is deliberate and is the practically important
point: **lot selection by sale instruction is disregarded; lot allocation by custody
placement is respected.** Holding the same ISIN in two depots is therefore a lawful way to
influence which lots are consumed, whereas instructing the broker which lot to sell is not.

Note also that Sparer-Pauschbetrag and Abs. 6 loss offsetting operate per taxpayer at the
Veranlagung, across all depots. Depot separation changes the consumption order only.

#### Correction of a previous entry in this file

Until 2026-08-02 this section read, without any source:

> *"Key principle: FIFO method applies per asset per depot unless specific identification
> is possible."*

The *"unless specific identification is possible"* clause is **wrong** and is removed.
It is contradicted by Rz. 97 S. 3 (customer instructions on which security to sell are
irrelevant for income tax) and by Rz. 99 (FIFO applies even to Streifbandverwahrung, so
individual custody is not an escape either). Brokers do offer lot-matching methods other
than FIFO, and a realised-P&L figure taken from a broker may reflect one; the deleted
clause would have sanctioned adopting such a figure, contrary to Rz. 97 S. 3. That is why
it was a live hazard rather than a harmless imprecision. The "per depot" half was
substantively correct but unsourced; it is now carried by Rz. 97 S. 2.

#### Open question -- foreign custody (NOT settled, do not cite as resolved)

Satz 7 conditions the fiction on Sammelverwahrung *im Sinne des § 5 DepotG* -- a German
statute -- and Rz. 97-99 are written from the perspective of a German depotfuehrende
Stelle. Securities held through a foreign broker may sit in omnibus custody or in
Wertpapierrechnung, which is not § 5 DepotG Sammelverwahrung. Rz. 99 extending the method
to Streifbandverwahrung shows the administration applies FIFO irrespective of custody
form, which makes FIFO itself safe; what Rz. 97-99 do not squarely address is whether the
*"einzelnes Depot"* boundary transposes to a foreign broker's account/sub-account
structure. No Tier 1 or Tier 2 source located that settles this. Per-account FIFO is the
defensible reading and matches the administration's evident intent, but it is reasoned,
not sourced.

Practical consequence: a declaration prepared from foreign-broker data is a Veranlagungsfall
under § 32d Abs. 3 (no inlaendische Zahlstelle, no Steuerbescheinigung), so no bank has
applied FIFO and the taxpayer both computes and evidences it. § 90 Abs. 2 AO imposes an
erhoehte Mitwirkungspflicht for foreign matters, so a per-depot result must be evidenced
by per-account holdings, not merely asserted.

#### [GT-ESTG20-014] A transfer between the taxpayer's own depots is not a disposal

Moving a holding from one of the taxpayer's own depots to another is **not** a Veraeusserung
under Abs. 2: there is no change of beneficial owner and no consideration. Acquisition date and
acquisition cost carry over to the receiving depot. A per-depot lot computation must therefore
*relocate* lots on such a transfer, not close and reopen them -- reopening would reset the
holding period and the basis.

The § 43 / § 43a Depotuebertrag rules (BMF Rz. 162-173, 184a-193) are Kapitalertragsteuer
provisions addressed to German institutions. They do not apply to a foreign broker and cannot be
cited for the disposal question.

### Abs. 4a -- Corporate Actions (Kapitalmasnahmen)

#### [GT-ESTG20-015] Satz 1-2: Stock-for-stock mergers/exchanges

When shares are exchanged for shares of another corporation due to corporate measures (gesellschaftsrechtliche Massnahmen), the new shares step into the tax position of the old shares. No taxable event occurs.

Conditions:
- German taxation right on gain is not excluded/restricted, OR
- EU Merger Directive (Art. 8, Richtlinie 2009/133/EG) applies

Additional cash consideration (Barzuzahlung) is taxable under Abs. 1 Nr. 1.

#### [GT-ESTG20-016] Satz 5: Zuteilung without consideration (foreign corporations)

Shares allocated without consideration by a corporation with *"weder Geschaeftsleitung noch Sitz
im Inland"*: income and acquisition cost are both set to EUR 0, and the cost basis of the shares
that gave rise to the allocation is unchanged. **Conditional** -- the statute adds *"wenn die
Voraussetzungen der Saetze 3, 4 und 7 nicht vorliegen"*, i.e. Satz 5 is the residual case after
the Wandelanleihe (Satz 3), Bezugsrecht (Satz 4) and Abspaltung (Satz 7) rules.

#### [GT-ESTG20-017] Satz 7: Spin-offs (Abspaltungen)

Asset transfer via Abspaltung: Satz 1 and 2 apply analogously.

#### [GT-ESTG20-018] Satz 6: Timing

*"Soweit es auf die steuerliche Wirksamkeit einer Kapitalmassnahme im Sinne der vorstehenden
Saetze 1 bis 5 ankommt, ist auf den Zeitpunkt der Einbuchung in das Depot des Steuerpflichtigen
abzustellen."*

> **Correction, 2026-08-03.** Previously cited as "Satz 8". **Abs. 4a has seven Saetze; there is
> no Satz 8.** The timing rule is Satz 6 and it is expressly limited to Saetze 1 bis 5 -- it
> does not govern the Abspaltung case in Satz 7. Retrieved 2026-08-03 from
> gesetze-im-internet.de/estg/__20.html. Validation Protocol item 2.

#### [GT-ESTG20-019] Satz 3: Wandel-/Umtauschanleihen

Where the holder or issuer exercises a right to deliver shares instead of cash at maturity, the
cost of the claim becomes the disposal price of the claim *and* the acquisition cost of the
shares received.

#### [GT-ESTG20-020] Satz 4: Bezugsrechte

The portion of the old shares' acquisition cost attributable to the subscription right is set at
EUR 0.

Saetze 3 and 4 are recorded per Validation Protocol item 2: both are inside the cited Absatz, and
neither is a consequence of Satz 5 -- indeed Satz 5 is expressly the residual case *after* them.

---

## Abs. 6 -- Loss Offsetting

See dedicated file: [estg-20-abs6-verlustverrechnung.md](estg-20-abs6-verlustverrechnung.md)

---

## [GT-ESTG20-021] Abs. 8 -- Subsidiarity (Subsidiaritaet)

**Satz 1:** Capital income that belongs to income from agriculture/forestry, trade/business,
self-employment, or rental is attributed to those income types instead. Everything else in this
file assumes the holding is in Privatvermoegen.

**Satz 2:** *"Absatz 4a findet insoweit keine Anwendung."* Where the subsidiarity rule bites, the
corporate-action rollover of Abs. 4a is switched off as well. Recorded per Validation Protocol
item 2.

---

## [GT-ESTG20-024] Abs. 9 -- Sparer-Pauschbetrag, and the exclusion of actual Werbungskosten

**Satz 1:** *"Bei der Ermittlung der Einkuenfte aus Kapitalvermoegen ist als Werbungskosten ein
Betrag von 1 000 Euro abzuziehen (Sparer-Pauschbetrag); der Abzug der tatsaechlichen
Werbungskosten ist ausgeschlossen."*

**Satz 2:** EUR 2 000 jointly for zusammen veranlagte Ehegatten. **Satz 3** splits the joint amount
in half per spouse and shifts the unused part of one spouse's share to the other. **Satz 4:**
neither amount may exceed the Kapitalertraege as offset under Abs. 6.

> Retrieved 2026-08-03 from gesetze-im-internet.de/estg/__20.html. The EUR 1 000 / 2 000 figures
> apply **from 01.01.2023**; before that the Sparer-Pauschbetrag was EUR 801 / 1 602. The date and
> the two amounts are pinned at Tier 1 by **§ 52 Abs. 43 Satz 1 EStG**, which directs that a
> Freistellungsauftrag given *"vor dem 1. Januar 2023 unter Beachtung des § 20 Absatz 9 in der bis
> dahin geltenden Fassung"* be uplifted by **24,844 Prozent** -- and 801 x 1,24844 = 1 000
> exactly, which authenticates the old figure from the new one without a second source.

Two reasons this belongs in the store, both of which the library already depended on without
stating:

1. The **exclusion of actual Werbungskosten** in Satz 1 is why only costs in *unmittelbarem
   sachlichem Zusammenhang* with a disposal reduce a gain ([GT-ESTG20-011]); a custody fee or a
   data subscription does not.
2. The Anlage KAP-INV Zeile 53 instruction quoted at [GT-FORM-033] makes the Vorabpauschale
   deduction available where the year's total Kapitaleinkuenfte *"den Sparer-Pauschbetrag nicht
   ueberschritten haben"* -- so the amount is an input to that condition.

The Pauschbetrag itself is applied by the Finanzamt at the Veranlagung; it is not entered as a
figure on Anlage KAP other than as the portion already used through Freistellungsauftraege
(Zeilen 16/17).

> **Added 2026-08-03 (Validation Protocol item 2).** § 20 Abs. 9 was absent from the library while
> two of its statements leaned on it.
