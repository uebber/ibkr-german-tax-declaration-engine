# Anlage KAP -- Zeilenreferenz

## Source

- **2024 Anleitung (Tier 3):** in this repository, `reference/Anltg_KAP_24.md` (with the source
  PDF alongside it)
- **2025 Anleitung (Tier 3):** in this repository, `reference/Anltg_KAP_25.md`
- **2024 form:** [formulare-bfinv.de -- Anlage KAP](https://www.formulare-bfinv.de/ffw/action/invoke.do?id=034024_17)
- **Per-year Kennzahlen, verified form by form:**
  [`../tax-law/estg-20-abs6-verlustverrechnung.md`](../tax-law/estg-20-abs6-verlustverrechnung.md),
  section "Verification of the line numbers, per year". **That table is authoritative for which
  line existed in which VZ**; this file does not restate it.
- **BMF Steuerbescheinigung:** [BMF-Schreiben 16.05.2025 (PDF)](https://www.bundesfinanzministerium.de/Content/DE/Downloads/BMF_Schreiben/Steuerarten/Abgeltungsteuer/2025-05-16-kapitalertragSt-steuerbescheinigung.pdf?__blob=publicationFile&v=5)

---

## The income lines

### [GT-FORM-001] Zeilen 18 and 19 -- where income enters, split by intermediary

Zeile 18 takes **inlaendische** Kapitalertraege that have not borne Steuerabzug by an
inlaendische Zahlstelle. Zeile 19 takes **auslaendische** Ertraege, *"insbesondere Ertraege bei
auslaendischen Kreditinstituten"*.

The split turns on the **intermediary**, not on the debtor's domicile: income received through a
foreign broker belongs in Zeile 19 even where the issuer is German. The substantive
domestic/foreign concept of 34d EStG is a different question with no expression here -- see
[`../research/inlaendisch-auslaendisch-relevance.md`](../research/inlaendisch-auslaendisch-relevance.md)
and [GT-CREDIT-011].

### [GT-FORM-002] "zusaetzlich" and "ausschliesslich" are two different instructions (VZ 2024)

The Anleitung uses both words, and the difference decides whether a figure appears **twice** on the
form or **only once**. All four sentences below are verbatim from `Anltg_KAP_24.md`, in the block
on Zeilen 18 und 19, read 2026-08-03:

| Instruction | Verbatim | Effect |
|---|---|---|
| **zusaetzlich** | *"Alle Veraeusserungstatbestaende tragen Sie bitte zusaetzlich in die Zeilen 20 und / oder 22 und / oder 23 ein."* | also inside Zeile 18/19 |
| **zusaetzlich** | *"Einkuenfte aus Stillhalterpraemien und Gewinne aus Termingeschaeften tragen Sie bitte zusaetzlich in Zeile 21 ein."* | also inside Zeile 18/19 |
| **ausschliesslich** | *"Verluste aus Termingeschaeften erklaeren Sie bitte ausschliesslich in Zeile 24."* | **not** in Zeile 18/19 |
| **ausschliesslich** | *"Verluste aus der ganzen oder teilweisen Uneinbringlichkeit einer Kapitalforderung, aus der Ausbuchung oder Uebertragung wertloser Wirtschaftsgueter i. S. d. § 20 Abs. 1 EStG auf einen Dritten oder aus einem sonstigen Ausfall solcher Wirtschaftsgueter erklaeren Sie bitte ausschliesslich in Zeile 25."* | **not** in Zeile 18/19, and **not** in Zeile 22 |

So Zeilen 20, 21, 22 and 23 break out what is already inside Zeilen 18/19 -- a figure appears twice
by design. **Zeilen 24 and 25 do not.** They are the sole home of the two loss kinds routed to
them, and those losses are excluded from the Zeile 19 net figure.

| Zeile | Content | EStG basis | Also in 18/19? |
|-------|---------|------------|----------------|
| 20 | Gewinne aus der Veraeusserung von Aktien | 20 Abs. 2 Satz 1 Nr. 1 | yes |
| 21 | Stillhalterpraemien und Gewinne aus Termingeschaeften | 20 Abs. 1 Nr. 11, Abs. 2 Satz 1 Nr. 3 | yes |
| 22 | Verluste ohne Aktien, ohne Termingeschaefte und ohne die Zeile-25-Faelle | 20 Abs. 6 | yes |
| 23 | Verluste aus der Veraeusserung von Aktien | 20 Abs. 6 Satz 4 | yes |
| 24 | Verluste aus Termingeschaeften | 20 Abs. 2 Satz 1 Nr. 3 | **no -- ausschliesslich** |
| 25 | Verluste aus Kapitalforderungsausfall und wertloser Ausbuchung | 20 Abs. 2 Satz 1 Nr. 7, Abs. 4 | **no -- ausschliesslich** |

Which of these lines exists in which assessment year is **not** uniform -- see the per-year
Kennzahlen table cited under Source, and [GT-FORM-005] below.

> **Correction, 2026-08-03.** This section was headed *"Zeilen 20 to 25 restate part of 18/19"* and
> stated flatly that *"Zeilen 20-25 are therefore not separate income; they break out what is
> already inside Zeilen 18/19"*. That is false for Zeilen 24 and 25, both of which the Anleitung
> marks *ausschliesslich* in the very block the section quotes -- the quoted sentence names only
> Zeilen 20, 22 and 23, and the section generalised it to a range it does not cover. It also
> omitted the Zeile 21 sentence entirely. The Zeile 22 row additionally read *"Verluste ohne Aktien
> und ohne Termingeschaefte"*, which would route the Zeile-25 losses into Zeile 22 -- exactly what
> [GT-FORM-003] says the Anleitung forbids, so the file contradicted itself one section later.
> The same over-broad reading is corrected in
> [`../tax-law/estg-20-abs6-verlustverrechnung.md`](../tax-law/estg-20-abs6-verlustverrechnung.md)
> [GT-FORM-010] (Validation Protocol items 2 and 8).

### [GT-FORM-003] Zeile 25 -- Forderungsausfall and wertlose Ausbuchung (VZ 2024)

`Anltg_KAP_24.md`, in the block on Zeilen 18/19, verbatim:

> *"Verluste aus der ganzen oder teilweisen Uneinbringlichkeit einer Kapitalforderung, aus der
> Ausbuchung oder Uebertragung wertloser Wirtschaftsgueter i. S. d. § 20 Abs. 1 EStG auf einen
> Dritten oder aus einem sonstigen Ausfall solcher Wirtschaftsgueter erklaeren Sie bitte
> **ausschliesslich in Zeile 25**."*

*Ausschliesslich* is doing real work. A loss of this kind does **not** go to Zeile 22 with other
non-share losses; Zeile 25 is its only home. Three distinct events are routed here:

- Uneinbringlichkeit of a Kapitalforderung, whole or partial;
- Ausbuchung or Uebertragung of a wertloses Wirtschaftsgut i. S. d. 20 Abs. 1 EStG to a third
  party;
- any other Ausfall of such a Wirtschaftsgut.

> **Added 2026-08-03.** Zeile 25 was absent from this file entirely, while the file described
> Zeile 22 with no carve-out -- i.e. it directed exactly the losses the Anleitung reserves for
> Zeile 25 into the wrong line.

### [GT-FORM-004] Zeile 23 also takes wertlose Ausbuchung of shares (VZ 2025)

`Anltg_KAP_25.md`, in the corresponding block, verbatim:

> *"Tragen Sie die Ihnen entstandenen Verluste dann in die Zeilen 18 und / oder 19 und
> zusaetzlich in Zeile 22 ein. Wenn es sich um Verluste aus der wertlosen Ausbuchung von Aktien
> handelt, tragen Sie die Verluste nicht in Zeile 22, sondern zusaetzlich in Zeile 23 ein."*

So a **share** written off as worthless follows the Aktienverlust route (Zeile 23), not the
general one. Note this is stated in the 2025 Anleitung; **"Zeile 25" does not occur anywhere in
`Anltg_KAP_25.md`**, which bears on the open question below.

### [GT-FORM-005] Which lines exist in VZ 2025 -- unresolved

For VZ 2025 the Verlustverrechnungsbeschraenkung for Termingeschaefte is gone, so nothing is
entered on the separate derivative lines. **Whether Zeilen 21, 24 and 25 were physically removed
from the 2025 form, or retained and left unused, is not established.** Both readings and the
authorities are in
[`../research/open-legal-questions.md`](../research/open-legal-questions.md).

> **Correction, 2026-08-03.** This file previously stated *"21 | (entfaellt / removed)"* and
> *"24 | (entfaellt / removed)"* as fact, while the library's own register recorded the same
> question as unresolved. A reference file must not settle by assertion a question the store
> elsewhere holds open. Validation Protocol item 7.

---

## [GT-FORM-006] Zeile 41 -- anrechenbare auslaendische Steuern

*"Noch nicht angerechnete auslaendische Steuern"* -- one aggregate figure, not per country. The
line number and wording are identical in the 2024 and 2025 Anleitung. The credit itself is
governed by 32d Abs. 5, not by 34c Abs. 1: see
[`../tax-law/estg-32d-abgeltungsteuer.md`](../tax-law/estg-32d-abgeltungsteuer.md),
[GT-CREDIT-004].

## [GT-FORM-007] Zeilen 7 and 37-39 -- German KESt via a foreign depot

German Kapitalertragsteuer withheld on a German issuer's dividend is **not** an auslaendische
Steuer and does not belong in Zeile 41. It is credited through Zeile 7 (certified gross income)
with Zeilen 37/38/39 (KESt, SolZ, KiSt), and the credit requires a Steuerbescheinigung. See
[`../tax-law/estg-36-45a-kapitalertragsteuer-anrechnung.md`](../tax-law/estg-36-45a-kapitalertragsteuer-anrechnung.md).

## [GT-FORM-008] Zeilen 4 and 5 -- the two applications

- **Zeile 4** -- Guenstigerpruefung under 32d Abs. 6: *"Wenn Sie die Guenstigerpruefung
  beantragen moechten, tragen Sie in Zeile 4 eine ,1' ein"*.
- **Zeile 5** -- Ueberpruefung des Steuereinbehalts under 32d Abs. 4, *"dem Grunde und der Hoehe
  nach"*.

The two are routinely conflated; they are different provisions with different preconditions.

---

## [GT-FORM-009] What does not belong on Anlage KAP

- Investment fund income -> Anlage KAP-INV
  ([anlage-kap-inv-zeilen.md](anlage-kap-inv-zeilen.md))
- Private sale assets under 23 EStG -> Anlage SO ([anlage-so-zeilen.md](anlage-so-zeilen.md))
- Einlagenrueckgewaehr -> not taxable income at all (20 Abs. 1 Nr. 1 Satz 3)
