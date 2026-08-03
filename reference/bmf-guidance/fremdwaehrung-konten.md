# Foreign Currency (Fremdwaehrung) -- Tax Treatment

## Source

- **Legal basis (Tier 1):** 20 Abs. 2 Satz 1 Nr. 7 EStG (interest-bearing) /
  23 Abs. 1 Satz 1 Nr. 2 EStG (non-interest-bearing)
- **BMF-Schreiben Einzelfragen zur Abgeltungsteuer, 19.05.2022, BStBl I 2022 S. 742** -- the
  administrative source the classification below rests on. **See the provenance gap recorded
  under "Sourcing status" before relying on a Randziffer from it.**
- **BMF-Schreiben Einzelfragen zur Abgeltungsteuer, 14.05.2025:**
  [BMF PDF](https://www.bundesfinanzministerium.de/Content/DE/Downloads/BMF_Schreiben/Steuerarten/Abgeltungsteuer/2025-05-14-einzelfragen-zur-abgeltungsteuer.pdf?__blob=publicationFile&v=2)
  -- a complete rewrite superseding the 19.05.2022 version. See
  [abgeltungsteuer-einzelfragen.md](abgeltungsteuer-einzelfragen.md) for the version history.
- **Tier 5, consulted, not relied on:**
  [Kleeberg -- Fremdwaehrungskonten im Privatvermoegen](https://www.kleeberg.de/2025/03/17/fremdwaehrungskonten-im-privatvermoegen/),
  [Haufe -- Private Fremdwaehrungskonten](https://www.haufe.de/steuern/steuerwissen-tipps/private-fremdwaehrungskonten-neue-steuerliche-regeln-seit-2025_170_671044.html),
  [Flick Gocke Schaumburg -- New Rules on Taxing Foreign Currency Gains](https://www.fgs.de/en/news-and-insights/blog/detail/new-rules-on-taxing-foreign-currency-gains-in-private-assets)

---

## Sourcing status -- read this before citing a Randziffer

**This file is the weakest-sourced in the library and is scheduled for re-audit.** Two specific
gaps, recorded rather than papered over:

1. **The controlling document is cited by Randziffer without a retrievable copy.** The BMF
   circular of 19.05.2022 carried the paradigm shift set out below, and Rz. 131 is cited here for
   the treatment of currency embedded in securities transactions. Neither the Randziffer text nor
   the document itself has been read in the course of building this library. The BStBl citation
   above is taken from the version history in
   [abgeltungsteuer-einzelfragen.md](abgeltungsteuer-einzelfragen.md), not from the document.
   Retrieval of the BMF PDF was attempted again on 2026-08-03 and returned an empty response.
2. **"Rz. 131" is ambiguous across versions.** The 14.05.2025 circular is a *Neufassung*, not an
   amendment, so its Randziffern do not necessarily carry the numbering of the 19.05.2022 text.
   A citation to "Rz. 131" that does not name its version is not checkable. Any use of it should
   name the document date.

Until both are closed, the classification below should be treated as Tier 5-supported
administrative practice with a Tier 1 statutory basis, not as verified Tier 2.

---

## Classification

### [GT-FX-001] Interest-bearing accounts -> 20 Abs. 2 Satz 1 Nr. 7 EStG

Currency gains and losses on an **interest-bearing** foreign currency balance (Tagesgeld,
Festgeld, sonstiges verzinsliches Fremdwaehrungskonto) are Einkuenfte aus Kapitalvermoegen: the
balance is a Kapitalforderung, and its disposal falls under Abs. 2 Satz 1 Nr. 7.

Consequences:

- **No speculation period.** Taxable regardless of how long the balance was held.
- Abgeltungsteuer at the 32d Abs. 1 rate.
- Loss offsetting inside the capital income pool (20 Abs. 6).
- Each credit is an acquisition; each debit is a disposal.
- Lot identification follows the general Abs. 4 Satz 7 rule -- see
  [GT-ESTG20-012] in `../tax-law/estg-20-kapitalvermoegen.md`.

### [GT-FX-002] Non-interest-bearing / payment accounts -> 23 Abs. 1 Satz 1 Nr. 2 EStG

A **non-interest-bearing** account (Girokonto, Basiskonto, payment account) is not a
Kapitalforderung yielding Ertrag, so its currency movements remain a privates
Veraeusserungsgeschaeft:

- One-year Jahresfrist; tax-free once exceeded.
- Taxed at the individual tarifliche rate, not the Abgeltungsteuer rate.
- Separate loss pool (23 EStG only).

### [GT-FX-003] Pure payment transactions -> not taxable

Currency movements on Zahlungsverkehrskonten, credit cards and digital payment instruments are
generally outside both, for want of Einkuenfteerzielungsabsicht.

### [GT-FX-004] Temporal reach

The 20 EStG classification is stated to apply to **all open cases from VZ 2009 onwards**, not
from the date of the circular. Separately, from **01.01.2025** German banks must withhold
Kapitalertragsteuer on currency gains from interest-bearing accounts -- which affects a German
depot, not a foreign one, where no Steuerabzug occurs (32d Abs. 3; see
`../tax-law/estg-32d-abgeltungsteuer.md`).

---

## Open questions (NOT settled -- do not cite as resolved)

### [GT-FX-005] Is the 20 EStG classification itself right?

Recorded per Validation Protocol item 7, because the store had carried only one side.

- **For 20 EStG:** the administrative position above; an interest-bearing balance is a
  Kapitalforderung and Abs. 2 Satz 1 Nr. 7 catches its disposal.
- **Against:** 23 Abs. 1 Satz 1 Nr. 2 EStG has long been *the* provision for currency gains, and
  the literature notes that the historical understanding of "andere Wirtschaftsgueter" expressly
  encompassed Fremdwaehrungsbetraege. On that reading, bearing interest changes the taxation of
  the *interest* without converting the currency holding itself into a different asset, and the
  Jahresfrist would continue to apply.

The two readings differ on whether a currency gain realised more than a year after the balance
arose is taxable at all. No Tier 1 or Tier 4 authority resolving the point has been located.

### [GT-FX-006] Short currency positions

A negative currency balance -- borrowing in a foreign currency -- is not addressed by the
guidance located. Whether a short currency position in Privatvermoegen is taxed symmetrically
with a long one under 20 Abs. 2 Satz 1 Nr. 7 is unresolved.

### [GT-FX-007] Currency embedded in a securities transaction

Buying a foreign security consumes foreign currency and selling one produces it. Whether the
currency leg is a separate disposal to be measured on its own, or is absorbed into the security's
acquisition cost and disposal proceeds, is contested. Separate measurement is the conservative
reading and is what BMF Rz. 131 is cited for -- subject to gap 2 in "Sourcing status" above,
which is exactly the ambiguity that citation carries.
