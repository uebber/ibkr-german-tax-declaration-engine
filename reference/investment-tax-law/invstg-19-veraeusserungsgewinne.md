# InvStG 19 -- Gewinne aus der Veraeusserung von Investmentanteilen

## Source

- **Primary:** [gesetze-im-internet.de -- 19 InvStG](https://www.gesetze-im-internet.de/invstg_2018/__19.html)
- **Form instructions:** `reference/Anltg_KAP_INV_24.md`, `reference/Anltg_KAP_INV_25.md`

> Statutory text retrieved 2026-08-03 from gesetze-im-internet.de/invstg_2018/__19.html. Umlauts
> transliterated per this library's convention. § 19 has **three Absaetze**; Abs. 1 has four
> Saetze. All are accounted for below.

## Scope

How gains from the sale of investment fund units are computed, and in particular the deduction
of Vorabpauschalen already taxed during the holding period.

---

## [GT-INVSTG-030] Abs. 1 -- Gain calculation (four Saetze, verbatim)

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

## [GT-INVSTG-031] Abs. 2 -- Deemed disposal when the fund leaves the scope of the InvStG

*"Faellt ein Investmentfonds nicht mehr in den Anwendungsbereich dieses Gesetzes, so gelten seine
Anteile als veraeussert. Als Veraeusserungserloes gilt der gemeine Wert der Investmentanteile zu
dem Zeitpunkt, zu dem der Investmentfonds nicht mehr in den Anwendungsbereich faellt."*

A broker statement does not report this event: nothing is bought or sold, and the position is
unchanged. It has to be established from the fund's own disclosures.

## [GT-INVSTG-032] Abs. 3 -- Further deemed disposals (Wegzug and related)

Abs. 3 treats as a disposal at gemeiner Wert: the end of unbeschraenkte Steuerpflicht through
giving up residence (Nr. 1), gratuitous transfer to a person not unbeschraenkt steuerpflichtig
(Nr. 2), and otherwise the exclusion or restriction of Germany's taxing right (Nr. 3) -- but only
where the total gains are positive **and** the investor held at least 1 percent of the issued
units within the last five years, or holds units with acquisition costs of at least EUR 500 000.

All three turn on the investor's circumstances rather than on any transaction, and all three are
gated by the 1 percent / EUR 500 000 threshold. Recorded here because Validation Protocol item 2
requires stating what else the cited unit contains.

---

## [GT-INVSTG-033] Form placement -- Zeile 53, not Zeile 55

**Verified against the official Anleitung for both supported years**
(`reference/Anltg_KAP_INV_24.md` and `reference/Anltg_KAP_INV_25.md`, identical wording;
read 2026-08-03).

| Zeile | Official heading | Content |
|-------|------------------|---------|
| 51 | Anschaffungskosten | acquisition cost (for nicht bestandsgeschuetzte Alt-Anteile, the fiktive value at the close of 31.12.2017) |
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

### [GT-INVSTG-034] Units never subject to inlaendischer Steuerabzug

Units held through a foreign broker never bear inlaendischer Steuerabzug, so the third sentence
of the Zeile 53 instruction is always the operative one, with two consequences:

1. A Vorabpauschale reduces the disposal gain **only** to the extent it was actually brought to
   tax in the year it flowed -- either declared, or covered by the Sparer-Pauschbetrag. A
   Vorabpauschale that was never declared cannot be deducted here.
2. The taxpayer must be able to *demonstrate* that, for every year of the holding period. This
   is a multi-year evidentiary record, not something a single year's figures can establish.

**Correction, 2026-08-03:** this file previously stated the deduction is reported on Zeile 55.
It is not; Zeile 55 is the bestandsgeschuetzte-Alt-Anteile line. The error was mirrored in
`../tax-forms/anlage-kap-inv-zeilen.md`, `invstg-18-vorabpauschale.md` and
`../research/coverage-matrix.md`, and corrected in all of them together (Validation Protocol
item 8).
