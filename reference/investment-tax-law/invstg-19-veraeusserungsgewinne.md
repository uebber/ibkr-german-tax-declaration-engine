# InvStG 19 -- Gewinne aus der Veraeusserung von Investmentanteilen

## Source

- **Primary:** [gesetze-im-internet.de -- 19 InvStG](https://www.gesetze-im-internet.de/invstg_2018/__19.html)
- **Form instructions:** `reference/Anltg_KAP_INV_24.md`, `reference/Anltg_KAP_INV_25.md`

> Statutory text retrieved 2026-08-03 from gesetze-im-internet.de/invstg_2018/__19.html. Umlauts
> transliterated per this library's convention. § 19 has **three Absaetze**; Abs. 1 has four
> Saetze. All are accounted for below.

## Relevance to Engine

Defines how gains from the sale of investment fund units are computed, and in particular the
deduction of Vorabpauschalen already taxed during the holding period.

---

## Abs. 1 -- Gain calculation (four Saetze, verbatim)

- **Satz 1:** *"Fuer die Ermittlung des Gewinns aus der Veraeusserung von Investmentanteilen, die
  nicht zu einem Betriebsvermoegen gehoeren, ist § 20 Absatz 4 des Einkommensteuergesetzes
  entsprechend anzuwenden."*
- **Satz 2:** *"§ 20 Absatz 4a des Einkommensteuergesetzes ist nicht anzuwenden."*
- **Satz 3:** *"Der Gewinn ist um die waehrend der Besitzzeit angesetzten Vorabpauschalen zu
  vermindern."*
- **Satz 4:** *"Die angesetzten Vorabpauschalen sind ungeachtet einer moeglichen Teilfreistellung
  nach § 20 in voller Hoehe zu beruecksichtigen."*

```
Gewinn = Veraeusserungserloes
       - Veraeusserungskosten
       - Anschaffungskosten                                    (Satz 1, via 20 Abs. 4 EStG)
       - Summe der waehrend der Besitzzeit angesetzten Vorabpauschalen, BRUTTO   (Saetze 3-4)
```

Two things Satz 3 fixes that are easy to lose:

- **"waehrend der Besitzzeit"** -- the Vorabpauschalen accumulated over the holding period of
  *the units actually disposed of*, across all the years they were held. It is **not** the
  current year's Vorabpauschale total, and it is not a fund-level figure: it follows the lot.
- **"angesetzten"** -- only Vorabpauschalen that were actually brought to tax. The Anleitung
  makes the condition explicit for units without inlaendischer Steuerabzug; see the Zeile 53
  quotation below.

Satz 4 settles the gross/net question at Tier 1: the deduction is the **full, pre-Teilfreistellung**
amount, even though the Vorabpauschale itself was taxed after Teilfreistellung. The Teilfreistellung
is then applied once, to the resulting gain.

Because Satz 2 excludes 20 Abs. 4a EStG, the corporate-action rollover rules for shares do **not**
apply to fund units.

## Abs. 2 -- Deemed disposal when the fund leaves the scope of the InvStG

*"Faellt ein Investmentfonds nicht mehr in den Anwendungsbereich dieses Gesetzes, so gelten seine
Anteile als veraeussert. Als Veraeusserungserloes gilt der gemeine Wert der Investmentanteile zu
dem Zeitpunkt, zu dem der Investmentfonds nicht mehr in den Anwendungsbereich faellt."*

**Not implemented.** The engine has no event for a fund leaving the InvStG's scope and no input
column that would signal it.

## Abs. 3 -- Further deemed disposals (Wegzug and related)

Abs. 3 treats as a disposal at gemeiner Wert: the end of unbeschraenkte Steuerpflicht through
giving up residence (Nr. 1), gratuitous transfer to a person not unbeschraenkt steuerpflichtig
(Nr. 2), and otherwise the exclusion or restriction of Germany's taxing right (Nr. 3) -- but only
where the total gains are positive **and** the investor held at least 1 percent of the issued
units within the last five years, or holds units with acquisition costs of at least EUR 500 000.

**Out of scope and not implemented.** Recorded here because Validation Protocol item 2 requires
stating what else the cited unit contains. The engine assumes a continuously unbeschraenkt
steuerpflichtiger private investor.

---

## Form placement -- Zeile 53, not Zeile 55

**Verified against the official Anleitung for both supported years**
(`reference/Anltg_KAP_INV_24.md` and `reference/Anltg_KAP_INV_25.md`, identical wording;
read 2026-08-03).

| Zeile | Official heading | Content |
|-------|------------------|---------|
| 51 | Anschaffungskosten | acquisition cost (or the fiktive 31.12.2017 value for Alt-Anteile) |
| **53** | **Waehrend der Besitzzeit angesetzte Vorabpauschalen** | **the Satz 3-4 deduction** |
| 54 | -- | Veraeusserungsgewinn / -verlust; transferred to Zeilen 14/17/20/23/26 by fund type |
| 55 | Gewinne aus der Veraeusserung von bestandsgeschuetzten Alt-Anteilen | the 56 Abs. 6 S. 1 Nr. 2 InvStG portion; transferred to Zeilen 15/18/21/24/27 |

Zeile 53, verbatim:

> *"Um eine Doppelbesteuerung auszuschliessen, tragen Sie hier bitte die waehrend der Besitzzeit
> der veraeusserten Investmentanteile angesetzten Vorabpauschalen ein. Sie muessen diese vor
> Teilfreistellung angeben. Die Vorabpauschalen bei Investmentanteilen, die nicht dem
> inlaendischen Steuerabzug unterlegen haben, mindern den Veraeusserungsgewinn nur, soweit Sie
> diese Vorabpauschalen der Besteuerung unterworfen haben (Zeile 9 bis 13). Bitte legen Sie dar,
> dass die Vorabpauschalen in der Steuererklaerung angegeben wurden oder die gesamten
> Kapitaleinkuenfte in den betreffenden Kalenderjahren den Sparer-Pauschbetrag nicht
> ueberschritten haben."*

Two consequences specific to this engine, whose inputs are all from a foreign broker and
therefore **never** subject to inlaendischer Steuerabzug:

1. The condition in sentence three is always the operative one. A Vorabpauschale reduces the
   disposal gain **only** to the extent it was actually declared in the year it flowed (or fell
   under the Sparer-Pauschbetrag). A Vorabpauschale the engine never reported cannot be deducted.
2. The taxpayer must be able to *demonstrate* that. That is a multi-year record, not a
   single-run computation.

**Correction, 2026-08-03:** this file previously stated the deduction is reported on Zeile 55.
It is not; Zeile 55 is the bestandsgeschuetzte-Alt-Anteile line. The error was mirrored in
`tax-forms/anlage-kap-inv-zeilen.md`, `invstg-18-vorabpauschale.md`, `research/coverage-matrix.md`
and in the engine's `TaxReportingCategory` name. All corrected together (Validation Protocol
item 8).

---

## Engine Mapping and known deviation

Gains are reported gross per fund type on Zeilen 14/17/20/23/26 via
`ANLAGE_KAP_INV_*_GEWINN_GROSS`.

**The Zeile 53 deduction is not computed.** The engine has no per-lot Vorabpauschale
accumulation: `RealizedGainLoss` carries no Vorabpauschale field, and the value previously
emitted was the sum of the *current* tax year's gross Vorabpauschalen -- neither
"waehrend der Besitzzeit" nor restricted to the units disposed of, and on the wrong line.
Computing it correctly requires carrying each lot's assessed Vorabpauschalen across years,
together with evidence that they were declared. Until that exists the engine emits no Zeile 53
figure and records a data gap when fund units were disposed of, rather than a plausible wrong
number.
