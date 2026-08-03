# Open Legal Questions

Points that decide a declared figure and that **no Tier 1 or Tier 2 source has been found to
settle**. Each entry states both readings and the authority behind each.

**This file does not record which reading was chosen.** That is an implementation decision and
lives in `docs/legal-implementation-map.md`, against the same claim ID -- Validation Protocol
item 7. The split is deliberate: an unresolved question and a decision taken under uncertainty
are different kinds of statement, and merging them is how the second quietly becomes the first.

An unresolved question recorded is ground truth. An unresolved question silently resolved is not.

| # | Claim | Question | Documented in full |
|---|-------|----------|--------------------|
| Q1 | [GT-ESTG23-004] | Does § 108 Abs. 3 AO extend the § 23 Jahresfrist when the anniversary falls on a Saturday, Sunday or public holiday? | `../tax-law/estg-23-private-veraeusserung.md` |
| Q2 | [GT-ESTG20-013] | Does the *"einzelnes Depot"* boundary of the Fifo rule transpose to a foreign broker's account and sub-account structure? | `../tax-law/estg-20-kapitalvermoegen.md` |
| Q3 | [GT-FORM-005] | Were Zeilen 21, 24 and 25 physically removed from the VZ 2025 Anlage KAP, or retained and left unused? | `../tax-forms/anlage-kap-zeilen.md` |
| Q4 | [GT-ESTG20-004] | From which VZ does the JStG-2024 wording of § 20 Abs. 1 Nr. 11 EStG (Glattstellungspraemien as negative Einnahmen *at the time of payment*) apply? | `../tax-law/estg-20-kapitalvermoegen.md` |
| Q5 | [GT-INVSTG-016] | Is a fund disposed of during the calendar year exempt from that year's Vorabpauschale? | `../investment-tax-law/invstg-18-vorabpauschale.md` |
| Q6 | [GT-FORM-023] | What lot-identification rule applies to an *anderes Wirtschaftsgut* under § 23 EStG? | `../tax-forms/anlage-so-zeilen.md` |
| Q7 | [GT-FX-005] | Are currency gains on an interest-bearing account really § 20 EStG income, or do they remain within § 23 Abs. 1 Satz 1 Nr. 2? | `../bmf-guidance/fremdwaehrung-konten.md` |
| Q8 | [GT-FX-006] | How is a short (negative) currency position taxed in Privatvermoegen? | `../bmf-guidance/fremdwaehrung-konten.md` |
| Q9 | [GT-FX-007] | Is the currency leg embedded in a foreign securities transaction a separate disposal? | `../bmf-guidance/fremdwaehrung-konten.md` |

---

## Q1 -- § 108 Abs. 3 AO and the § 23 Jahresfrist

**Reading A (no extension).** The Frist ends on the anniversary day whatever weekday it is.
Authority: **FG Koeln vom 02.06.1997, EFG 1997, 1187 (rkr.)**, the only § 23-specific decision
located, holding there is no extension when the period ends on a Sunday or public holiday;
followed by Littmann/Bitz/Pust, EStG § 23 Rn. 106 (EL 171, 02/2024). A practical argument
supports it: § 108 Abs. 3 AO's *"gesetzlicher Feiertag"* varies by Land, so the extension reading
makes the Frist depend on a Land-specific calendar.

**Reading B (extension).** § 108 Abs. 3 AO says *"das Ende einer Frist"* without qualification,
and § 108 Abs. 1 AO makes it lex specialis to § 193 BGB. Authority: **BFH vom 14.10.2003 --
IX R 68/98, BStBl II 2003, 898**, which abandoned the distinction between eigentliche and
uneigentliche Fristen for § 108 Abs. 3 AO; extended to the Festsetzungsfrist by **BFH vom
20.01.2016 -- VI R 14/15**. The FG Koeln decision pre-dates IX R 68/98.

**Why it matters:** the two readings differ on exactly the days a taxpayer waiting out the year
is most likely to trade -- the first trading day after a weekend anniversary.

## Q2 -- "einzelnes Depot" at a foreign broker

**Reading A (per account).** BMF Rz. 97 Satz 2 ties FIFO to the einzelnes Depot and Rz. 98 treats
an Unterdepot as a Depot; a foreign broker's account and sub-account structure is the natural
analogue.

**Reading B (pooled).** § 20 Abs. 4 Satz 7 EStG conditions the fiction on Sammelverwahrung *im
Sinne des § 5 DepotG*, a German statute. Foreign custody is often omnibus or Wertpapierrechnung,
which is not § 5 DepotG Sammelverwahrung, so the Depot boundary the Randziffern draw may have no
foreign counterpart.

Rz. 99 (FIFO applies to Streifbandverwahrung too) shows the administration applies FIFO
irrespective of custody form, so *whether* FIFO applies is not in doubt -- only the boundary.

## Q3 -- Zeilen 21/24/25 on the VZ 2025 Anlage KAP

**Reading A (retained but unused).** The Anleitung 2025 keeps the block heading at *"Zeilen 18
bis 26a"* and leaves every later line number unchanged -- Zeile 41 is still the noch nicht
angerechnete auslaendische Steuer in both years. On the VZ 2020 form, Zeilen 21 and 24 were
printed *"frei"*, so the form has precedent for retaining a numbered but unused line.

**Reading B (removed).** A Tier 5 summary claims removal. It also claims a three-line
renumbering, and that half is **refuted** by the official Anleitung, which weakens the source.

Not retrievable as of 2026-08-03: the official VZ 2025 form itself, which would settle it.
Nothing is entered on these lines under either reading.

## Q4 -- application date of the § 20 Abs. 1 Nr. 11 amendment

**Reading A (payment date, from the amendment).** The JStG-2024 wording books the
Glattstellungspraemie as a negative Einnahme *"zum Zeitpunkt der Zahlung"*. This matches
administrative practice before the amendment as well (BMF 18.01.2016 Rz. 25 ff., carried into
19.05.2022 and 14.05.2025).

**Reading B (year of the Stillhalterpraemie, for earlier VZ).** **BFH v. 02.08.2022 --
VIII R 27/21** held that Glattstellung costs reduce the Stillhalterpraemie in the VZ the premium
was *received*, as a rueckwirkendes Ereignis under § 175 Abs. 1 Satz 1 Nr. 2 AO.

**Unestablished:** buzer.de lists two JStG-2024 versions of § 20 EStG -- effective 06.12.2024
(Art. 3) and 01.01.2025 (Art. 4) -- and does not say which carried Nr. 11. No § 52 EStG
application rule for Nr. 11 has been located. Tier 5 sources disagree openly: Haufe Finance
Office states application from 01.01.2024, Haufe Steuer Office Excellence from the day after
promulgation.

**Why it matters:** the same amount falls in different years whenever the two legs straddle a
year end.

## Q5 -- Vorabpauschale in the year of disposal

**Reading A (no Vorabpauschale).** § 18 Abs. 3 InvStG deems the inflow to occur on the first
working day of the following year. By then the units are gone and there is no holder to receive
the deemed income.

**Reading B (Vorabpauschale arises).** § 18 Abs. 1 defines the amount by reference to the
calendar year's prices and distributions and imposes no year-end holding requirement. A
Zuflussfiktion fixes *when* income is received, which is not the same as whether it arises.

No Tier 1 or Tier 2 statement directly on the point has been located.

## Q6 -- lot identification under § 23 EStG

**§ 23 EStG contains no lot-identification rule.** The FIFO fiction of § 20 Abs. 4 Satz 7 EStG is
confined by its own wording to *vertretbare Wertpapiere* in Sammelverwahrung and does not reach
an *anderes Wirtschaftsgut*.

**Reading A (FIFO by analogy).** Administrative practice for fungible assets is said to be FIFO.
No source for this has been located -- it was asserted in this library without one until
2026-08-03, and the assertion is what prompted the entry.

**Reading B (a different ordering, or free designation).** With no statutory fiction, the general
rule that the taxpayer must establish which asset was disposed of would apply, and where lots are
genuinely indistinguishable the choice of convention is unsettled.

**Why it matters:** the ordering decides which acquisition date is compared with the disposal
date, and therefore whether the gain falls inside the Jahresfrist at all.

## Q7, Q8, Q9 -- foreign currency

All three are set out in `../bmf-guidance/fremdwaehrung-konten.md`, which also records why that
file's sourcing is currently the weakest in the library: the controlling BMF circular of
19.05.2022 is cited by Randziffer without a retrieved copy, and Randziffer numbering is not
stable across the 14.05.2025 Neufassung.

---

## Pending legal developments

Not open questions -- these have a settled answer today that a decision may change.

| Case | Subject | Effect if decided against the current rule |
|------|---------|--------------------------------------------|
| BVerfG 2 BvL 3/21 | Stock loss ring-fencing, § 20 Abs. 6 Satz 4 EStG (referred by BFH, Beschluss vom 17.11.2020, VIII R 11/18) | The separate Aktienverlusttopf, and with it the Zeile 20/23 split, would fall away |
| §§ 45b, 45c EStG (AbzStEntModG), from 01.01.2027 | Reporting duties changing Steuerbescheinigung issuance for German dividends | Alters the evidential route in [GT-CREDIT-022]; out of scope for VZ <= 2026 |
