# EStG 32d -- Gesonderter Steuertarif fuer Einkuenfte aus Kapitalvermoegen

## Source

- **Primary:** [gesetze-im-internet.de -- 32d EStG](https://www.gesetze-im-internet.de/estg/__32d.html)
- **With annotations:** [dejure.org -- 32d EStG](https://dejure.org/gesetze/EStG/32d.html)

## Scope

The flat tax rate (Abgeltungsteuer), the Veranlagungspflicht that makes a declaration necessary
at all, the foreign tax credit, and the Guenstigerpruefung option. Applying the rate is the
Finanzamt's step, not the taxpayer's: the declaration carries gross figures.

---

## [GT-CREDIT-001] Abs. 1 -- Flat Tax Rate

The income tax on capital income that does not fall under 20 Abs. 8 EStG is **25 percent** (Abgeltungsteuer).

Plus Solidaritaetszuschlag (5.5% of tax = effective 1.375%) and optional Kirchensteuer.

**Effective rates:**
- Without Kirchensteuer: 26.375%
- With Kirchensteuer (8%): 27.819%
- With Kirchensteuer (9%): 27.995%

## [GT-CREDIT-002] Abs. 3 -- Veranlagungspflicht (why a declaration is required at all)

Capital income **not subject to inlaendischer Steuerabzug** must be declared in the
Einkommensteuererklaerung; it is then assessed at the Abs. 1 rate. Income received through a
foreign broker is exactly that case: no inlaendische Zahlstelle, no Steuerabzug, no
Steuerbescheinigung. This is also why Abs. 5 is reachable at all -- Abs. 5 Satz 1 opens
*"In den Faellen der Absaetze 3 und 4"*.

## [GT-CREDIT-003] Abs. 4 -- Antrag auf Ueberpruefung des Steuereinbehalts

*Not* the Guenstigerpruefung. Abs. 4 lets a taxpayer whose income **has** borne
Kapitalertragsteuer request an assessment under Abs. 3 Satz 2 -- e.g. to use an unexhausted
Sparer-Pauschbetrag, a loss not yet taken into account under 43a Abs. 3, a Verlustvortrag under
20 Abs. 6, or foreign taxes not yet credited. On Anlage KAP this is the **Zeile 5** request --
*"Ueberpruefung des Steuereinbehalts dem Grunde und der Hoehe nach"* -- not the Zeile 4 one
(`reference/Anltg_KAP_24.md`, Zeile 5; identical in the 2025 Anleitung; read 2026-08-03).

Foreign-broker income cannot reach Abs. 4 on its own: there is no Steuereinbehalt to review. It
matters only for a taxpayer who also holds a German depot.

## [GT-CREDIT-004] Abs. 5 -- Foreign Tax Credit

*"[...] die auf auslaendische Kapitalertraege festgesetzte und gezahlte und um einen entstandenen
Ermaessigungsanspruch gekuerzte auslaendische Steuer, jedoch hoechstens 25 Prozent auslaendische
Steuer auf den einzelnen steuerpflichtigen Kapitalertrag, auf die deutsche Steuer anzurechnen"*
(Satz 1).

This is a **self-standing** credit mechanism, not an application of 34c Abs. 1 -- 34c Abs. 1
Satz 1 *zweiter Halbsatz* expressly excludes income to which 32d Abs. 1 und 3 bis 6 applies
(see `estg-34d-auslaendische-einkuenfte.md` for the verbatim carve-out). Two ceilings, both
often missed:

### [GT-CREDIT-005] Satz 1 -- the per-Kapitalertrag ceiling

At most 25 % foreign tax per *individual* Kapitalertrag. No per-country Anrechnungshoechstbetrag
applies.

### [GT-CREDIT-006] Satz 3 -- the per-VZ ceiling

Across the Veranlagungszeitraum, the credit is limited to the German tax falling on that year's
foreign Kapitalertraege.

The form takes the figure on **Zeile 41**, *"noch nicht angerechnete auslaendische Steuer"*
(verified identical in the 2024 and 2025 Anleitung). The declared amount is the foreign tax
withheld; the Finanzamt applies Satz 1 and Satz 3.

## [GT-CREDIT-007] Abs. 6 -- Guenstigerpruefung (assessment at the individual rate)

*"Auf Antrag des Steuerpflichtigen werden anstelle der Anwendung der Absaetze 1, 3 und 4 die
nach § 20 ermittelten Kapitaleinkuenfte den Einkuenften im Sinne des § 2 hinzugerechnet und der
tariflichen Einkommensteuer unterworfen, wenn dies zu einer niedrigeren Einkommensteuer
einschliesslich Zuschlagsteuern fuehrt (Guenstigerpruefung)."* (Satz 1)

Satz 2 keeps the foreign tax credit under **Abs. 5** even when the Guenstigerpruefung is
elected, so electing it never triggers 34c's per-country Anrechnungshoechstbetrag. Satz 3-4: the
application is only possible uniformly for all Kapitalertraege of the VZ, and for both spouses
jointly. On Anlage KAP this is the **Zeile 4** request -- *"Wenn Sie die Guenstigerpruefung
beantragen moechten, tragen Sie in Zeile 4 eine ,1' ein"* (`reference/Anltg_KAP_24.md`, Zeile 4;
identical in the 2025 Anleitung; read 2026-08-03).

> **Correction, 2026-08-03.** This file previously labelled **Abs. 4** the Guenstigerpruefung.
> It is Abs. 6; Abs. 4 is the Ueberpruefung des Steuereinbehalts. It also stated the Abs. 5
> credit runs *"per 34c Abs. 1 EStG"*, which inverts the relationship. Both were contradicted by
> this library's own `research/inlaendisch-auslaendisch-relevance.md`, which cites Abs. 6 and
> Abs. 6 Satz 2 correctly. Statutory text retrieved 2026-08-03 from
> gesetze-im-internet.de/estg/__32d.html. Validation Protocol items 2 and 8.

---

## What the declaration does not contain

The Abgeltungsteuer amount itself is not a figure the taxpayer enters. It follows from the
declared gross income together with circumstances the declaration does not carry --
Guenstigerpruefung, Sparer-Pauschbetrag, Kirchensteuer -- and is computed by the Finanzamt.
