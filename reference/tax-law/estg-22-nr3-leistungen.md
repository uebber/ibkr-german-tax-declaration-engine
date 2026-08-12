# § 22 Nr. 3 EStG -- Einkuenfte aus Leistungen

## Scope of this file

The residual income type reached when a payment is neither one of the six Einkunftsarten of
§ 2 Abs. 1 Satz 1 Nr. 1 bis 6 nor one of the other Nummern of § 22. It is where the order of
enquiry in [GT-ESTG20-049] ends, and it decides the treatment of a benefit a bank or broker grants
for placing capital with it.

**Claim ID area.** The area table in the knowledge store defines no `GT-ESTG22`, and the boundary
against § 22 Nr. 3 is already carried under `GT-ESTG20` at [GT-ESTG20-049]. The claims below
therefore continue the `GT-ESTG20` sequence. Introducing a dedicated area would be a change to the
area table itself and is left to a `ks-maint`.

## Sources

- **Tier 1 -- § 22 Nr. 3 EStG**, retrieved 2026-08-13 from
  [gesetze-im-internet.de/estg/__22.html](https://www.gesetze-im-internet.de/estg/__22.html)
- **Tier 1 -- § 11 Abs. 1 EStG**, retrieved 2026-08-13 from
  [gesetze-im-internet.de/estg/__11.html](https://www.gesetze-im-internet.de/estg/__11.html)
- **Tier 1 -- § 8 Abs. 1, Abs. 2 EStG**, retrieved 2026-08-13 from
  [gesetze-im-internet.de/estg/__8.html](https://www.gesetze-im-internet.de/estg/__8.html)

Applicable tax years: unrestricted within the Abgeltungsteuer regime. None of the three provisions
carries a first year of application relevant here, and the 256-Euro figure in Nr. 3 Satz 2 is not
year-parameterised.

---

## [GT-ESTG20-062] Nr. 3 Satz 1 -- the subsidiarity gate, and Satz 2 to 4

**Satz 1**, verbatim:

> *"Einkuenfte aus Leistungen, soweit sie weder zu anderen Einkunftsarten (§ 2 Absatz 1 Satz 1
> Nummer 1 bis 6) noch zu den Einkuenften im Sinne der Nummern 1, 1a, 2 oder 4 gehoeren, z. B.
> Einkuenfte aus gelegentlichen Vermittlungen und aus der Vermietung beweglicher Gegenstaende."*

The clause is **subsidiary by its own wording**: it is reached only once the six Einkunftsarten and
the other Nummern of § 22 are exhausted, never alongside them. The two named examples are
illustrative (*"z. B."*), not exhaustive -- a *Leistung* is any conduct, including a Dulden or
Unterlassen, done for consideration.

**Satz 2**, verbatim:

> *"Solche Einkuenfte sind nicht einkommensteuerpflichtig, wenn sie weniger als 256 Euro im
> Kalenderjahr betragen haben."*

A **Freigrenze, not a Freibetrag**: below 256 Euro the income is not taxable at all; at 256 Euro or
above the whole amount is taxable, not merely the excess. It is measured **per Kalenderjahr and
across all Leistungen of that year taken together**, not per single receipt.

**What the cited unit also contains.** Satz 3 bars a loss from Leistungen from being offset against
other income or carried under § 10d. Satz 4 lets such a loss reduce Leistungen income of the
immediately preceding and the following assessment periods, § 10d Abs. 4 applying accordingly.
Neither is reached by a benefit received, which cannot be negative.

---

## [GT-ESTG20-063] A benefit granted for placing capital is a Leistung, not Kapitalertrag

Where a bank or broker grants a benefit **in return for the customer transferring or leaving funds
with it**, the order of enquiry fixed by [GT-ESTG20-049] and [GT-ESTG20-050] runs as follows.

**Step 1 -- § 20 Abs. 3 fails.** Abs. 3 requires the benefit to be granted *neben* or *an deren
Stelle* of Einnahmen under Abs. 1 or Abs. 2. A benefit owed for the act of transferring funds is
owed **whether or not the funds go on to yield anything**, so there is no Einnahme of a particular
Kapitalanlage for it to stand alongside or replace. That is precisely the test [GT-ESTG20-050]
states, and the reason it gives -- both worked Randziffern of the administration combine Abs. 3
with a Nummer of Abs. 1 -- applies unchanged.

**Step 2 -- § 20 Abs. 1 Nr. 7 fails.** Nr. 7 taxes *Ertraege aus sonstigen Kapitalforderungen*. A
credit balance is a Kapitalforderung, so the gate that stopped the Wertpapierdarlehen fee (a
Sachforderung, [GT-ESTG20-046]) is passed here. Nr. 7 nonetheless fails on a different element:
what it taxes is a **yield on** the claim -- the consideration for the capital being left
outstanding, measured by amount and time. A benefit fixed by the act of depositing, and neither
measured by the balance over time nor forfeited if the balance yields nothing, is not an *Ertrag
aus* the Kapitalforderung but the price of a distinct transaction.

**Step 3 -- § 22 Nr. 3 applies.** Its subsidiarity clause is satisfied once § 20 is exhausted. The
customer's conduct -- transferring funds and leaving them in place -- is a *Leistung*, and the
benefit is its consideration.

**This is the same three-step result the store already reached for the Wertpapierdarlehen fee**
(open-legal-questions.md Q14, retired 2026-08-09, at [GT-ESTG20-049]); the fee failed Step 2 on the
gate, this benefit fails it on the element. Both land in Nr. 3.

**Consequence for Kapitalertragsteuer.** § 22 Nr. 3 income is not Kapitalertrag, so no domestic
Kapitalertragsteuer arises on it and it does not enter the Sparer-Pauschbetrag or the § 20 Abs. 6
loss pots. It is declared on Anlage SO, not Anlage KAP.

---

## [GT-ESTG20-064] Valuation and Zufluss of a benefit granted in kind

**Valuation -- § 8 Abs. 1 Satz 1 and Abs. 2 Satz 1 EStG.**

> *"Einnahmen sind alle Gueter, die in Geld oder Geldeswert bestehen und dem Steuerpflichtigen im
> Rahmen einer der Einkunftsarten des § 2 Absatz 1 Satz 1 Nummer 4 bis 7 zufliessen."*

> *"Einnahmen, die nicht in Geld bestehen (Wohnung, Kost, Waren, Dienstleistungen und sonstige
> Sachbezuege), sind mit den um uebliche Preisnachlaesse geminderten ueblichen Endpreisen am
> Abgabeort anzusetzen."*

§ 22 Nr. 3 income falls under § 2 Abs. 1 Satz 1 Nr. 7, so § 8 reaches it. A benefit granted in
securities rather than money is a *sonstiger Sachbezug* and is valued at the **ueblicher Endpreis
am Abgabeort** -- for an exchange-traded share, its market price.

**Zufluss -- § 11 Abs. 1 Satz 1 EStG.**

> *"Einnahmen sind innerhalb des Kalenderjahres bezogen, in dem sie dem Steuerpflichtigen
> zugeflossen sind."*

Zufluss requires the recipient to obtain **wirtschaftliche Verfuegungsmacht**. Where a benefit is
booked into the recipient's custody account but remains **subject to a condition under which the
grantor may take it back**, the recipient does not yet hold it unconditionally, and Zufluss falls
on the date the condition lapses rather than the date of the booking. The valuation under § 8
Abs. 2 is then taken at that same date, because § 8 values what is *zugeflossen*.

**What the cited unit also contains.** § 11 Abs. 1 has five sentences: Satz 2 on regularly
recurring income falling either side of the year end, Satz 3 on spreading income from a
Nutzungsueberlassung over the advance period, Satz 4 cross-referring provisions for
non-employment income, and Satz 5 preserving the profit-determination rules. None is reached by a
one-off benefit in kind.

---

## [GT-ESTG20-065] The amount taxed on receipt becomes the Anschaffungskosten

Where the benefit consists of securities, the value brought to tax under [GT-ESTG20-064] is the
recipient's **Anschaffungskosten** for those securities on a later disposal under § 20 Abs. 2
Satz 1 Nr. 1 EStG. Taxing the receipt and then taxing the whole disposal proceeds again would tax
the same accretion twice; the acquisition is entgeltlich to the extent it has been taxed, and
§ 20 Abs. 4 Satz 1 measures the gain against the Anschaffungskosten.

**This claim does not depend on the benefit having actually been declared.** The Anschaffungskosten
follow from the value that fell to be taxed under § 11 and § 8, not from what appeared on a return.

**Where the sources run out.** Whether a receipt left untaxed by the Freigrenze of Nr. 3 Satz 2
nonetheless supplies Anschaffungskosten at its full value is **not settled** by any Tier 1 or
Tier 2 source located. Recorded in `../research/open-legal-questions.md`.
