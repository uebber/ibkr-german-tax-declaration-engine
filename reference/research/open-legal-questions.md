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
| Q4 | [GT-ESTG20-004] | Does a Glattstellung cost fall in the year it was paid (§ 20 Abs. 1 Nr. 11 EStG and administrative practice) or in the year the Stillhalterpraemie was received (BFH VIII R 27/21, as a rueckwirkendes Ereignis)? | `../tax-law/estg-20-kapitalvermoegen.md` |
| Q6 | [GT-FORM-023] | What lot-identification rule applies to an *anderes Wirtschaftsgut* under § 23 EStG? | `../tax-forms/anlage-so-zeilen.md` |
| Q7 | [GT-FX-005] | Are currency gains on an interest-bearing account really § 20 EStG income, or do they remain within § 23 Abs. 1 Satz 1 Nr. 2? | `../bmf-guidance/fremdwaehrung-konten.md` |
| Q8 | [GT-FX-006] | How is a short (negative) currency position taxed in Privatvermoegen? | `../bmf-guidance/fremdwaehrung-konten.md` |
| Q9 | [GT-FX-007], [GT-FX-001] | Is a currency movement embedded in another transaction a separate disposal, measured in EUR? Two instances: the leg of a securities trade, and a balance spent on a fee or withholding. | `../bmf-guidance/fremdwaehrung-konten.md` |
| Q11 | [GT-ESTG20-038] | How is unallocated spot precious metal held at a broker taxed -- Termingeschaeft, privates Veraeusserungsgeschaeft, or sonstige Kapitalforderung? | this file |

**Retired on the same terms, and for the same reason -- a source that settles the point was found,
or the point was never one.** Numbers are never reused. Each line says what answered it; the
reasoning lives once, against the claim, which is where a reader acts on it.

| # | Question | What answered it | Recorded at |
|---|----------|------------------|-------------|
| Q5 | Vorabpauschale in the year of disposal | Rz. 18.4 -- the multiplier is the units held *"mit Ablauf des 31. Dezember des Kalenderjahres"*, so a holding disposed of in full is multiplied by nothing. Rz. 20.4 confirms it from the other side. Retired 2026-08-07 | [GT-INVSTG-016] |
| Q12 | The day whose Ruecknahmepreis begins the Vorabpauschale year | Rz. 18.3 -- the same figure serves as the Satz 2 base and the Satz 3 cap's lower bound. Retired 2026-08-06 | [GT-INVSTG-010] |
| Q13 | The Abs. 2 reduction on a holding acquired in several instalments | Rz. 18.11's worked example applies the reduction to the *per-Anteil* amount, before any unit count enters -- which was the whole of the opposing reading. Retired 2026-08-07 | [GT-INVSTG-011] |

Two were retired without being answered, which is a different act and is recorded as such:

| # | Question | Why it left | Recorded at |
|---|----------|-------------|-------------|
| Q3 | Were Zeilen 21/24/25 physically removed from the VZ 2025 Anlage KAP, or retained and left unused? | **It decides no figure under either reading**, and this file admits only points that do. Nothing is entered on those lines either way, so the answer cannot change a declaration. It was filed as a legal question because the VZ 2025 form itself could not be retrieved; the evidence is now a note in `../tax-forms/anlage-kap-zeilen.md`. Retired 2026-08-07 | [GT-FORM-005] |
| Q10 | Is a balance spent on a cash-flow item a separate disposal? | **Not answered -- merged.** It is one instance of Q9, turns on the same finding, and was accumulating the same reasoning twice. Retired into Q9 on 2026-08-07 | [GT-FX-001] |

**Two things Q13's closure does not settle**, recorded so they are not read into it. Which units
remain at the close of 31 December after a *partial* disposal is a lot-identification question, and
the boundary of the pool FIFO runs over at a foreign broker is **Q2**, still open. And the day that
fixes the *Monat des Erwerbs* is not a § 18 question at all: it is the obligatorisches
Rechtsgeschaeft, [GT-ESTG20-040], which no located source puts at settlement.

**Closed 2026-08-03, and recorded here so it is not reopened by habit:** lot identification for
foreign-currency amounts. It is FIFO under both classifications -- § 23 Abs. 1 Satz 1 Nr. 2 Satz 3
EStG at Tier 1 for the § 23 branch ([GT-ESTG23-013]), BMF 14.05.2025 Rz. 131 at Tier 2 for the
§ 20 branch ([GT-FX-008]). The library had grounded it in § 20 Abs. 4 Satz 7, which by its own
wording cannot reach a currency balance.

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

## Q4 -- which year a Glattstellung cost falls in

**Reading A (payment date).** The Glattstellungspraemie is a negative Einnahme *"zum Zeitpunkt der
Zahlung"*. This is the JStG-2024 wording of § 20 Abs. 1 Nr. 11 EStG **and** administrative practice
before it -- BMF 18.01.2016 Rz. 25 ff., carried unchanged into 19.05.2022 and 14.05.2025.

**Reading B (the year the Stillhalterpraemie was received).** **BFH v. 02.08.2022 -- VIII R 27/21**
held that Glattstellung costs reduce the Stillhalterpraemie in the VZ the premium was *received*,
as a rueckwirkendes Ereignis under § 175 Abs. 1 Satz 1 Nr. 2 AO -- which reopens the earlier
assessment rather than booking the cost where it was paid.

**Why it matters:** the same amount falls in different years whenever the two legs straddle a year
end, and Reading B can be the better outcome or the worse one depending on which year has losses
to absorb. It is therefore an election to be taken case by case, not a rule that can be settled
once for every pair.

> **Rescoped 2026-08-07.** This entry was headed *"application date of the amendment"* and turned
> on which JStG-2024 article carried Nr. 11 -- buzer.de lists versions effective 06.12.2024 and
> 01.01.2025 without saying which, no § 52 EStG application rule was located, and Tier 5 sources
> disagreed openly. **That strand decides nothing and has been dropped.** The administration books
> the cost at payment both before and after the amendment, so the amendment's first year cannot
> change the outcome. What was actually open, and remains open, is the divergence between the
> administrative position and VIII R 27/21 -- which is a question about *which year*, not about
> *from when*.

## Q6 -- lot identification under § 23 EStG, for assets other than currency

**Scope correction, 2026-08-03.** This question was previously framed on the premise that *"§ 23
EStG contains no lot-identification rule"*. **It contains one**: § 23 Abs. 1 Satz 1 Nr. 2 **Satz 3**
fixes FIFO for *gleichartige Fremdwaehrungsbetraege* ([GT-ESTG23-013]), inserted by Art. 2 des
Gesetzes vom 25.07.2014 (BGBl. I S. 1266). The library had never recorded that Satz. **Currency is
therefore settled at Tier 1 and is out of this question.** What remains open is every *other*
"anderes Wirtschaftsgut" -- Gold and commodity ETCs, Crypto ETPs.

The FIFO fiction of § 20 Abs. 4 Satz 7 EStG does not reach them either: it is confined by its own
wording to *vertretbare Wertpapiere* in Sammelverwahrung.

**Reading A (FIFO by analogy).** Administrative practice for fungible assets is said to be FIFO.
No source for this has been located -- it was asserted in this library without one until
2026-08-03, and the assertion is what prompted the entry. Nr. 2 Satz 3 could be read as evidence
that FIFO is the ordering the legislature regards as natural for fungibles.

**Reading B (a different ordering, or free designation).** With no statutory fiction, the general
rule that the taxpayer must establish which asset was disposed of would apply, and where lots are
genuinely indistinguishable the choice of convention is unsettled. **Nr. 2 Satz 3 cuts this way
too, and arguably harder:** the legislature legislated a consumption order for one class of § 23
asset and not for the others, which is an argument against reading a general one into the silence.

**Why it matters:** the ordering decides which acquisition date is compared with the disposal
date, and therefore whether the gain falls inside the Jahresfrist at all.

## Q7, Q8, Q9 -- foreign currency

All three are set out in `../bmf-guidance/fremdwaehrung-konten.md`.

**Updated 2026-08-03: the sourcing gap these three rested on is closed.** BMF 14.05.2025 was
retrieved and Rz. 131 read in full. The consequences differ per question and are not uniform:

- **Q7 (is the § 20 classification right?)** -- the *administrative* position is now verified
  Tier 2, verbatim, drawn on the verzinslich/unverzinslich line. The question survives as a
  question about whether that position is correct, and it gains a Tier 1 datum on the § 23 side
  that the library had missed: § 23 Abs. 1 Satz 1 Nr. 2 Satz 3 EStG legislates a FIFO order for
  Fremdwaehrungsbetraege *inside* the privates Veraeusserungsgeschaeft ([GT-ESTG23-013]).
- **Q8 (short currency positions)** -- unchanged. Rz. 131 addresses Guthaben throughout and says
  nothing about a negative balance.
- **Q9 (a currency movement embedded in another transaction)** -- **sharper, not softer.** Rz. 131
  was the citation the library gave for separate measurement, and reading it shows it does not
  address the point at all. Q9 has no administrative source on either side, in either of its two
  instances.
A related point that is **no longer open**: lot identification for currency. It is FIFO under both
classifications -- Rz. 131 for the § 20 branch, § 23 Abs. 1 Satz 1 Nr. 2 Satz 3 for the § 23
branch. The library previously grounded it in § 20 Abs. 4 Satz 7, which cannot reach a currency
balance.

## Q9 in full -- a currency movement inside another transaction

**One question, two instances**, merged 2026-08-07 because they turn on the same finding and were
being reasoned about twice:

- **(a) the leg of a securities trade** -- USD is spent to buy a US share, or received on selling
  one ([GT-FX-007]);
- **(b) a balance spent on a cash-flow item** -- withholding tax, a fee, interest ([GT-FX-001]).

In both, is the currency movement a disposal of the currency, measured separately in EUR against
the acquisition cost of the amount consumed?

**Reading A (a separately measured disposal).** Rz. 131 states the trigger generally before it
names cases: *"Waehrungsgewinne/-verluste aus der **Veraeusserung oder Rueckzahlung** einer ...
verzinslichen Kapitalforderung oder eines verzinslichen Fremdwaehrungsguthabens ... sind gemaess
§ 20 Absatz 2 Satz 1 Nummer 7 und Absatz 4 Satz 1 EStG zu beruecksichtigen."* Spending the balance
extinguishes part of the Kapitalforderung and so realises the difference between its EUR value at
acquisition and at extinction, on the same footing as the cases the Randziffer then lists. Reading
it otherwise lets a currency gain escape measurement whenever the balance is spent rather than
converted back.

**Reading B (not a separate disposal).** Rz. 131's enumeration is of Rueckzahlung, re-investment
and transfer to another interest-bearing account. Neither instance is among them, and the
transaction being settled is itself the taxable event, measured at the rate of its own day. On this
reading the currency movement is a means of settlement, not a second transaction.

**No Tier 1 or Tier 2 statement on either instance has been located.** BMF 14.05.2025 was retrieved
and Rz. 131 read in full on 2026-08-03; it does not reach the question either way, and it was the
only citation the library had for Reading A. The choice is not neutral in amount: Reading A
produces gain and loss lines that Reading B does not.

> **Q10 is retired into this entry, 2026-08-07, and its number is not reused.** It held instance
> (b) as a separate question. Both instances had accumulated the same reasoning and the same
> correction -- that Rz. 131 does not carry separate measurement -- in two places.

---

## Pending legal developments

Not open questions -- these have a settled answer today that a decision may change.

| Case | Subject | Effect if decided against the current rule |
|------|---------|--------------------------------------------|
| BVerfG 2 BvL 3/21 | Stock loss ring-fencing, § 20 Abs. 6 Satz 4 EStG (referred by BFH, Beschluss vom 17.11.2020, VIII R 11/18) | The separate Aktienverlusttopf, and with it the Zeile 20/23 split, would fall away |
| §§ 45b, 45c EStG (AbzStEntModG), from 01.01.2027 | Reporting duties changing Steuerbescheinigung issuance for German dividends | Alters the evidential route in [GT-CREDIT-022]; out of scope for VZ <= 2026 |

---

## Q11 -- unallocated spot precious metal held at a broker

**The instrument.** A long position in gold against a currency, carried on a broker's books with
no maturity and no delivery claim, charged a monthly carrying fee. It is not a dated contract and
it is not allocated metal.

**Why it is not settled.** Three readings are each defensible and no Tier 1 or Tier 2 source
located so far chooses between them.

**Reading A -- Termingeschaeft, 20 Abs. 2 Satz 1 Nr. 3.** The Bezugsgroesse fits: BMF 14.05.2025
Rz. 9 lists *"dem Boersen- oder Marktpreis von Waren oder Edelmetallen"* ([GT-ESTG20-038]).
**Against it:** the same Randziffer opens by requiring an Options- or Festgeschaeft *"die zeitlich
verzoegert zu erfuellen sind"*. A rolling spot position with no maturity does not obviously satisfy
that, and the Bezugsgroesse list qualifies instruments that already meet the definition rather than
substituting for it.

**Reading B -- private sale under 23 Abs. 1 Satz 1 Nr. 2.** The BFH treats gold-backed paper as if
it were physical gold where the holder has a *schuldrechtlicher Anspruch auf Lieferung* (VIII R
35/14, VIII R 19/14, VIII R 4/15, all 12.05.2015; IX R 33/17 of 06.02.2018 on physical
fulfilment). **Against it:** VIII R 15/18 of 12.04.2021 draws the boundary -- a Gold-ETF is *not*
treated as physical gold where no delivery claim exists, and *"dass die Gelder ausschliesslich in
physisches Gold investiert wurden, ist insoweit unerheblich."* An unallocated broker position
carries no such claim.

**Reading C -- sonstige Kapitalforderung, 20 Abs. 2 Satz 1 Nr. 7.** If the position is a
cash-settled claim against the broker rather than metal, this is where it would sit.
**Against it:** the 2015 BFH line holds that a claim directed at delivery of a Sache is not a
Kapitalforderung -- but that reasoning presupposes a delivery claim, which is the very thing
absent here, so it neither supports nor excludes this reading.

**What turns on the answer.** Reading A puts the gain on Anlage KAP as a Termingeschaeft. Reading
B puts it on Anlage SO and makes it tax-free after a year. Reading C puts it on Anlage KAP under a
different Nummer with different loss-offsetting. The three do not converge.

**Status.** No Tier 1/2 source has been located that addresses unallocated spot metal at a broker
specifically. Tier 4 constrains the question from both sides without closing it. **Do not resolve
this from the shape of the product or from what a broker's asset class happens to be called.**
