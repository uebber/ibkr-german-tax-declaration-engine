# InvStG 20 -- Teilfreistellung

## Source

- **Primary (Tier 1):** [gesetze-im-internet.de -- 20 InvStG](https://www.gesetze-im-internet.de/invstg_2018/__20.html),
  retrieved 2026-08-03
- **Fund type definitions (Tier 1):** [gesetze-im-internet.de -- 2 InvStG](https://www.gesetze-im-internet.de/invstg_2018/__2.html),
  retrieved 2026-08-03
- **Change of the applicable rate:** 22 InvStG -- see
  [invstg-22-teilfreistellungssatz-aenderung.md](invstg-22-teilfreistellungssatz-aenderung.md)
- **Tier 3 cross-check:** `reference/Anltg_KAP_INV_24.md`, Zeilen 4 bis 8 (fund type definitions)

> Umlauts transliterated per this library's convention. Quoted German is verbatim from the
> retrieved statute text.

---

## Rates -- Privatvermoegen

This is the **only statement of the Teilfreistellung rates in this library.** Do not restate them
elsewhere; Validation Protocol item 5 exists because agreeing copies are not verification.

| Fund type | Claim | Citation | Steuerfrei | Taxable portion |
|-----------|-------|----------|------------|-----------------|
| Aktienfonds | GT-INVSTG-020 | 20 Abs. 1 Satz 1 | 30 % | 70 % |
| Mischfonds | GT-INVSTG-021 | 20 Abs. 2 | 15 % | 85 % |
| Immobilienfonds | GT-INVSTG-022 | 20 Abs. 3 Satz 1 | 60 % | 40 % |
| Auslands-Immobilienfonds | GT-INVSTG-023 | 20 Abs. 3 Satz 2 | 80 % | 20 % |
| Sonstiger Fonds | GT-INVSTG-024 | no provision | 0 % | 100 % |

### [GT-INVSTG-020] Abs. 1 Satz 1 -- Aktienteilfreistellung

*"Steuerfrei sind bei Aktienfonds 30 Prozent der Ertraege (Aktienteilfreistellung)."*

### [GT-INVSTG-021] Abs. 2 -- Mischfonds

*"Bei Mischfonds ist die Haelfte der fuer Aktienfonds geltenden Aktienteilfreistellung
anzusetzen."*

Note the statute states a **fraction of the Aktienteilfreistellung**, not a fixed rate. 15 % is
the result for Privatvermoegen only; in Betriebsvermoegen it is half of 60 % or of 80 %.

### [GT-INVSTG-022] [GT-INVSTG-023] Abs. 3 Saetze 1-3 -- Immobilien

*"Bei Immobilienfonds sind 60 Prozent der Ertraege steuerfrei (Immobilienteilfreistellung). Bei
Auslands-Immobilienfonds sind 80 Prozent der Ertraege steuerfrei
(Auslands-Immobilienteilfreistellung). Die Anwendung der Immobilienteilfreistellung oder der
Auslands-Immobilienteilfreistellung schliesst die Anwendung der Aktienteilfreistellung aus."*

**Satz 3 is a rule in its own right:** the two exemptions are mutually exclusive. A fund meeting
both an Immobilienfondsquote and an Aktienfonds-Kapitalbeteiligungsquote takes the Immobilien
rate, not both.

> **Correction, 2026-08-03 (Validation Protocol item 2).** Earlier revisions cited these as
> *"Abs. 3 Satz 1 Nr. 1"* and *"Abs. 3 Satz 1 Nr. 2"*. **Abs. 3 has no Nummern**; it has three
> Saetze, and the Auslands rate is in Satz 2. Retrieved 2026-08-03 from
> gesetze-im-internet.de/invstg_2018/__20.html.

### [GT-INVSTG-024] Sonstige Fonds

A fund meeting none of the quotas has no Teilfreistellung provision, so 100 % of its
Investmentertraege is taxable. This is the absence of a rule, not a rule; it is given a claim ID
because a figure depends on it.

---

## [GT-INVSTG-025] Rates in Betriebsvermoegen -- out of scope, recorded per Validation Protocol item 2

| Fund type | Natural person (BV) | Subject to KStG |
|-----------|---------------------|-----------------|
| Aktienfonds | 60 % (Abs. 1 Satz 2) | 80 % (Abs. 1 Satz 3) |
| Mischfonds | 30 % (Abs. 2) | 40 % (Abs. 2) |
| Immobilienfonds | 60 % (Abs. 3 Satz 1) | 60 % (Abs. 3 Satz 1) |
| Auslands-Immobilienfonds | 80 % (Abs. 3 Satz 2) | 80 % (Abs. 3 Satz 2) |

Abs. 1 Satz 4 disapplies Saetze 2 and 3 for Lebens-/Krankenversicherungsunternehmen (Nr. 1) and
for Institute/Unternehmen nach 3 Nr. 40 Satz 3 EStG or 8b Abs. 7 KStG holding the units in the
Handelsbestand (Nr. 2); Satz 5 extends Nr. 1 to Pensionsfonds. Abs. 3a extends Abs. 1 bis 3 to
units held indirectly through a Personengesellschaft, except one that has opted into
Koerperschaftsbesteuerung under 1a KStG.

---

## Fund type definitions (2 InvStG)

### [GT-INVSTG-026] Abs. 6 Satz 1 -- Aktienfonds: *mehr als 50 Prozent*

*"Aktienfonds sind Investmentfonds, die gemaess den Anlagebedingungen fortlaufend **mehr als 50
Prozent** ihres Aktivvermoegens in Kapitalbeteiligungen anlegen
(Aktienfonds-Kapitalbeteiligungsquote)."*

> **Correction, 2026-08-03 (figure-changing).** Earlier revisions of this file stated the
> threshold as **">= 51 %"**, twice. That is wrong, and it is wrong in the direction that costs
> the taxpayer money: a fund holding a continuous 50.5 % Kapitalbeteiligungsquote **is** an
> Aktienfonds and carries the 30 % Teilfreistellung, but under the old wording it would have been
> classified Sonstiger Fonds at 0 %.
>
> The 51 % figure is real but belongs to a different rule — the **look-through attribution** in
> Abs. 8 Satz 1 Nr. 3 (below). Confusing a qualification threshold with an attribution rate is
> the exact failure Validation Protocol item 2 targets. The repo's own Tier 3 transcript already
> said *"mehr als 50 %"* (`Anltg_KAP_INV_24.md`); the statute was not checked against it.

Abs. 6 Satz 2 extends the definition to a Dach-Investmentfonds bound by its Anlagebedingungen to
invest so as to maintain the quota through its Ziel-Investmentfonds; Satz 3 limits that extension
to Ziel-Investmentfonds valued at least weekly.

**Satz 4 ends the status, and it is a trigger for the § 22 fiction:** *"In dem Zeitpunkt, in dem
der Investmentfonds wesentlich gegen die Anlagebedingungen verstoesst und dabei die
Aktienfonds-Kapitalbeteiligungsquote unterschreitet, endet die Eigenschaft als Aktienfonds."* Abs. 7
Satz 4 applies it to Mischfonds. So the fund type can lapse without any amendment to the
Anlagebedingungen — a material breach plus a shortfall is enough — and that lapse is a case of
*"fallen die Voraussetzungen der Teilfreistellung weg"* under
[22 Abs. 1 Satz 1](invstg-22-teilfreistellungssatz-aenderung.md), [GT-INVSTG-040].

> **Added 2026-08-03 (Validation Protocol item 2).** Satz 4 was unstated, and its absence made the
> neighbouring statement in the § 22 file — that quota drift alone does not trigger the fiction —
> read as broader than it is.

### [GT-INVSTG-027] Abs. 7 Satz 1 -- Mischfonds: *mindestens 25 Prozent*

*"Mischfonds sind Investmentfonds, die gemaess den Anlagebedingungen fortlaufend **mindestens 25
Prozent** ihres Aktivvermoegens in Kapitalbeteiligungen anlegen
(Mischfonds-Kapitalbeteiligungsquote)."*

Note the asymmetry with Abs. 6, which is deliberate and easy to normalise away by accident:
Aktienfonds is *mehr als 50* (exclusive), Mischfonds is *mindestens 25* (inclusive). A fund at
exactly 25 % is a Mischfonds; a fund at exactly 50 % is not an Aktienfonds.

### [GT-INVSTG-028] Abs. 8 -- Kapitalbeteiligungen, and the 51 % look-through

Satz 1 defines Kapitalbeteiligungen as: exchange-listed or organised-market shares in a
Kapitalgesellschaft (Nr. 1); shares in a Kapitalgesellschaft that is not an Immobilien-Gesellschaft
and is resident and subject to non-exempt corporate income taxation in the EU/EEA (Nr. 2a) or in
a third country at a rate of at least 15 % (Nr. 2b); *"Investmentanteile an Aktienfonds in Hoehe
von **51 Prozent** des Wertes des Investmentanteils"* (Nr. 3); and Investmentanteile an Mischfonds
in Hoehe von 25 Prozent (Nr. 4).

**This is the only place 51 % appears in the Aktienfonds chain.** It governs how much of a
*fund-of-funds holding* counts towards the holder's own quota — not whether a fund qualifies.
Saetze 2 and 3 raise the attributed percentage where the target fund's Anlagebedingungen commit
to a higher minimum.

### [GT-INVSTG-029] Abs. 9 -- Immobilienfonds and Auslands-Immobilienfonds

- **Satz 1:** *"Immobilienfonds sind Investmentfonds, die gemaess den Anlagebedingungen fortlaufend
  mehr als 50 Prozent ihres Aktivvermoegens in Immobilien und Immobilien-Gesellschaften anlegen
  (Immobilienfondsquote)."*
- **Satz 2:** the same *mehr als 50 Prozent* test against **auslaendische** Immobilien and
  Auslands-Immobiliengesellschaften.
- **Satz 3:** Auslands-Immobiliengesellschaften are those investing *"ausschliesslich"* in
  auslaendische Immobilien.
- **Satz 4:** the parallel look-through — units in an Immobilienfonds or Auslands-Immobilienfonds
  count as Immobilien in Hoehe von 51 Prozent of their value.
- **Satz 5:** where the target fund's Anlagebedingungen commit to a higher minimum than 51 percent,
  that higher percentage applies instead.
- **Satz 6:** shares in Koerperschaften, Personenvereinigungen or Vermoegensmassen whose
  Bruttovermoegen consists of at least 65 percent immovable property count as Immobilien **in Hoehe
  von 65 Prozent** of their value, subject to a 15 percent Ertragsbesteuerung condition.

> Saetze 5 and 6 added 2026-08-03 per Validation Protocol item 2; Abs. 9 does not stop at Satz 4.

> **Correction, 2026-08-03.** Earlier revisions cited *"Abs. 9 Nr. 1"* and *"Abs. 9 Nr. 2"*.
> **Abs. 9 has no Nummern**; the distinction is Satz 1 versus Satz 2. The old text also described
> Satz 2 as requiring the properties to be *"predominantly foreign"*, which understates it: the
> quota is measured against foreign properties specifically, and a qualifying
> Auslands-Immobiliengesellschaft must invest *exclusively* abroad.

---

## [GT-INVSTG-019] Abs. 4 -- Teilfreistellung on proof of the actual quota

*"Weist der Anleger nach, dass der Investmentfonds die Aktienfonds- oder
Mischfonds-Kapitalbeteiligungsquote oder Immobilienfonds- oder Auslands-Immobilienfondsquote
waehrend des Kalenderjahres tatsaechlich durchgehend ueberschritten hat, so ist die
Teilfreistellung auf Antrag des Anlegers in der Veranlagung anzuwenden."*

So the Anlagebedingungen are the primary test, and actual continuous compliance is a fallback the
investor may invoke **by application in the assessment**. Satz 2 attaches a documentation
obligation for the whole holding period where the investor later claims disposal losses above
EUR 500 or Wertminderungen on units for which this proof was given.

---

## Applicable years

InvStG 2018 applies from 01.01.2018 (56 Abs. 1 Satz 1 InvStG). There is no Teilfreistellung
before that year; the pre-2018 Investmentsteuerrecht is a different regime and is outside this
library's coverage.
