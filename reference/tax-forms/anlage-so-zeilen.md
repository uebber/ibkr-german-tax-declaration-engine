# Anlage SO -- Zeilenreferenz (Private Veraeusserungsgeschaefte)

## Source

- **Legal basis (Tier 1):** 22 Nr. 2, 23 Abs. 1 Satz 1 Nr. 2 EStG -- see
  [`../tax-law/estg-23-private-veraeusserung.md`](../tax-law/estg-23-private-veraeusserung.md)
- **ELSTER Help 2024 (Tier 3):** [elster.de -- Anleitung SO](https://www.elster.de/eportal/helpGlobal?themaGlobal=help_est_ufa_12_2024)
- **EStH 2024 -- 23 EStG:** [esth.bundesfinanzministerium.de](https://esth.bundesfinanzministerium.de/esth/2024/A-Einkommensteuergesetz/II-Einkommen-2-24b/8-Die-einzelnen-Einkunftsarten-13-24b/g-Sonstige-Einkuenfte-22-23/Paragraf-23/inhalt.html)
- **EStH 2024 -- Anhang 26 Private Veraeusserungsgeschaefte:** [esth.bundesfinanzministerium.de](https://esth.bundesfinanzministerium.de/esth/2024/C-Anhaenge/Anhang-26/inhalt.html)

> **Sourcing status.** The form download reference is a portal root
> (`https://www.formulare-bfinv.de/`), not a per-year document, and no Anleitung zur Anlage SO
> for a specific assessment year is held in this repository -- unlike Anlage KAP and KAP-INV,
> whose Anleitungen are transcribed here. The line numbers below have therefore **not** been
> verified per year to the standard Validation Protocol item 4 requires. Scheduled for re-audit.

---

## Structure

Anlage SO covers two things, of which only the second is relevant here:

1. **Leistungen** (22 Nr. 3 EStG)
2. **Private Veraeusserungsgeschaefte** (22 Nr. 2, 23 EStG)

Within the second, the form separates:

- Grundstuecke und grundstuecksgleiche Rechte (ten-year period, 23 Abs. 1 Satz 1 Nr. 1)
- Kryptowaehrungen / virtuelle Waehrungen (one-year period, Zeilen 41-47)
- **Andere Wirtschaftsgueter** (one-year period, Zeilen 48-55)

## [GT-FORM-020] Zeilen 48-55 -- Andere Wirtschaftsgueter

| Zeile | Content |
|-------|---------|
| 48 | Art des Wirtschaftsguts |
| 49 | Anschaffungsdatum |
| 50 | Veraeusserungsdatum |
| 51 | Veraeusserungspreis |
| 52 | Anschaffungskosten |
| 53 | Werbungskosten |
| 54 | Gewinn / Verlust |
| 55 | Summe / weitere Angaben |

A disposal outside the Jahresfrist is not reported at all: it is not a
Veraeusserungsgeschaeft under 23 Abs. 1 Satz 1 Nr. 2 and there is no line for it.

---

## Key rules

### [GT-FORM-021] Freigrenze -- 23 Abs. 3 Satz 5 EStG

EUR 1 000 per calendar year from VZ 2024; EUR 600 before. Raised by the **Wachstumschancengesetz
vom 27.03.2024 (BGBl. 2024 I Nr. 108)** -- *not* by the JStG 2024, as this file previously
stated. The statutory wording is *"weniger als 1 000 Euro"*, so a Gesamtgewinn of exactly
EUR 1 000 is **not** exempt. Full text and the amendment provenance:
[`../tax-law/estg-23-private-veraeusserung.md`](../tax-law/estg-23-private-veraeusserung.md).

It applies to the combined gain from **all** private sales in the year, and it is a Freigrenze,
not a Freibetrag: once exceeded, the entire gain is taxable, not just the excess.

### [GT-FORM-022] Loss offsetting

23 EStG losses offset 23 EStG gains only -- no cross-offsetting with 20 EStG capital income.
Carryback to the preceding year and carryforward to subsequent years operate per 10d EStG
analogously (23 Abs. 3 Saetze 7-8).

### [GT-FORM-023] Lot identification for 23 EStG assets -- open, except for currency

**§ 23 EStG contains exactly one lot-identification rule, and it is confined to currency.**
§ 23 Abs. 1 Satz 1 Nr. 2 **Satz 3** EStG fixes FIFO for *gleichartige Fremdwaehrungsbetraege* --
see [GT-ESTG23-013]. For every other "anderes Wirtschaftsgut" — Gold and commodity ETCs, Crypto
ETPs, the instruments this form block is actually used for — **no ordering rule has been located at
Tier 1 or Tier 2.**

The FIFO fiction of 20 Abs. 4 Satz 7 EStG does not fill the gap: it is confined by its own wording
to *vertretbare Wertpapiere in Sammelverwahrung nach § 5 DepotG* and does not reach an "anderes
Wirtschaftsgut" under § 23.

The contrast is the point. The legislature wrote a consumption order into § 23 for one class of
asset and not for the others, which makes the silence harder to read as an implied general FIFO
rather than easier.

> **Correction, 2026-08-03.** Two rounds. This file first asserted that FIFO for § 23 assets
> *"follows the general principle applied by the Finanzverwaltung for fungible assets"*, unsourced;
> that was removed. The replacement then over-corrected to *"§ 23 EStG contains no
> lot-identification rule"* — false as written, since Nr. 2 Satz 3 is one, and the library had
> simply never recorded that Satz. A lot ordering decides which acquisition date is compared
> against the disposal date and therefore whether the gain is taxable at all, so both the false
> positive and the false negative mattered. Recorded as open, with its true scope, in
> [`../research/open-legal-questions.md`](../research/open-legal-questions.md) Q6.
