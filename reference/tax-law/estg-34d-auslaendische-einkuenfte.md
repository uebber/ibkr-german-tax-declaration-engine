# EStG 34d -- Auslaendische Einkuenfte

## Source

- **Primary:** [gesetze-im-internet.de -- 34d EStG](https://www.gesetze-im-internet.de/estg/__34d.html)
- **With annotations:** [dejure.org -- 34d EStG](https://dejure.org/gesetze/EStG/34d.html)

## Scope

Defines what constitutes *auslaendische Einkuenfte* for the foreign tax credit (34c, 32d Abs. 5):
whether income has a domestic or foreign source, decided by the debtor's domicile. Distinct from
the Anlage KAP Z18/Z19 form split, which turns on the intermediary (broker), not the issuer.

---

## [GT-CREDIT-010] Introductory Sentence

> Auslaendische Einkuenfte im Sinne des 34c Absatz 1 bis 5 sind [...]

The definition applies specifically in the context of the foreign tax credit under 34c.

---

## [GT-CREDIT-011] Nr. 6 -- Einkuenfte aus Kapitalvermoegen (20 EStG)

> Einkuenfte aus Kapitalvermoegen (20), wenn der Schuldner Wohnsitz, Geschaeftsleitung oder Sitz in einem auslaendischen Staat hat oder das Kapitalvermoegen durch auslaendischen Grundbesitz gesichert ist

### Classification criteria

Income from capital assets is "auslaendisch" if:

1. The **Schuldner** (debtor) has Wohnsitz, Geschaeftsleitung, or Sitz in a foreign state, **OR**
2. The capital is secured by **foreign real property** (auslaendischer Grundbesitz)

### Applying "Schuldner" to different income types

| Income type | EStG basis | Who is the "Schuldner"? |
|-------------|------------|-------------------------|
| Dividends | 20 Abs. 1 Nr. 1 | The distributing corporation |
| Interest | 20 Abs. 1 Nr. 7 | The debtor paying interest (bond issuer, bank, etc.) |
| Stillhalterpraemien | 20 Abs. 1 Nr. 11 | The option counterparty (debatable; often the exchange/clearinghouse) |
| Veraeusserungsgewinne (stock sale) | 20 Abs. 2 Nr. 1 | No direct "Schuldner" -- prevailing view: the **issuer** of the sold security |
| Veraeusserungsgewinne (bond) | 20 Abs. 2 Nr. 7 | The bond issuer |
| Termingeschaefte (derivatives) | 20 Abs. 2 Nr. 3 | Debatable; typically the underlying issuer or exchange counterparty |

### Worked examples -- holdings at a foreign broker

| Income | Debtor | 34d classification | Z18 or Z19? |
|--------|--------|---------------------|-------------|
| Dividend of a German AG | German AG | **Inlaendisch** (German Schuldner) | Z19 (foreign broker) |
| Dividend of a US corporation | US corporation | **Auslaendisch** (foreign Schuldner) | Z19 (foreign broker) |
| Gain on selling a German AG's shares | German AG | **Inlaendisch** (German issuer) | Z19 (foreign broker) |
| Gain on selling a US corporation's shares | US corporation | **Auslaendisch** (foreign issuer) | Z19 (foreign broker) |
| Interest on a cash balance at an Irish broker | the Irish broker | **Auslaendisch** (Irish debtor) | Z19 (foreign broker) |

The 34d classification and the Z18/Z19 form placement are **independent**. Every row lands in
Z19 because the intermediary is foreign (*"Ertraege bei auslaendischen Kreditinstituten"*),
whatever the debtor's domicile.

---

## Relationship to 34c and 32d Abs. 5

### [GT-CREDIT-012] 34c Abs. 1 Satz 1 -- the general credit, and the carve-out in its second Halbsatz

Satz 1 grants the credit and then withdraws it for Abgeltungsteuer income in the same sentence:

> *"Bei unbeschraenkt Steuerpflichtigen, die mit auslaendischen Einkuenften in dem Staat, aus dem
> die Einkuenfte stammen, zu einer der deutschen Einkommensteuer entsprechenden Steuer
> herangezogen werden, ist die festgesetzte und gezahlte und um einen entstandenen
> Ermaessigungsanspruch gekuerzte auslaendische Steuer auf die deutsche Einkommensteuer
> anzurechnen, die auf die Einkuenfte aus diesem Staat entfaellt; **das gilt nicht fuer
> Einkuenfte aus Kapitalvermoegen, auf die § 32d Absatz 1 und 3 bis 6 anzuwenden ist.**"*

**Satz 3** completes it: *"Bei der Ermittlung des zu versteuernden Einkommens und der
auslaendischen Einkuenfte sind die Einkuenfte nach Satz 1 zweiter Halbsatz nicht zu
beruecksichtigen"* -- the carved-out income is also excluded from the
Anrechnungshoechstbetrag arithmetic in Satz 2.

> **Correction, 2026-08-03.** This file, and `research/inlaendisch-auslaendisch-relevance.md`,
> both attributed the carve-out to **34c Abs. 1 Satz 4**. Satz 4 is about Betriebsausgaben:
> *"Gehoeren auslaendische Einkuenfte der in § 34d Nummer 3, 4, 6, 7 und 8 Buchstabe c genannten
> Art zum Gewinn eines inlaendischen Betriebes, sind bei ihrer Ermittlung Betriebsausgaben und
> Betriebsvermoegensminderungen abzuziehen ..."*. The conclusion drawn from it was right; the
> pinpoint was wrong, which is precisely what Validation Protocol item 2 exists to catch --
> here the file even quoted the Satz 1 text under a Satz 4 heading. Retrieved 2026-08-03 from
> gesetze-im-internet.de/estg/__34c.html.

### 32d Abs. 5 -- the mechanism that applies instead

32d Abs. 5 provides a direct credit for foreign withholding tax on Abgeltungsteuer income,
capped per individual Kapitalertrag rather than per country. See
[estg-32d-abgeltungsteuer.md](estg-32d-abgeltungsteuer.md).

### [GT-CREDIT-013] Guenstigerpruefung does **not** restore the 34c mechanism

The carve-out in Satz 1 zweiter Halbsatz names *"§ 32d Absatz 1 **und 3 bis 6**"*. Abs. 6 is the
Guenstigerpruefung, so it sits **inside** the carve-out: electing it does not push capital income
back under 34c Abs. 1, and the per-country Anrechnungshoechstbetrag never applies. 32d Abs. 6
Satz 2 says the same thing from the other side by keeping the credit under Abs. 5.

> **Correction, 2026-08-03.** This file previously stated that Guenstigerpruefung is *"32d
> Abs. 4"* and that electing it makes capital income *"fall back under 34c Abs. 1 and the
> per-country Anrechnungshoechstbetrag"*. Both are wrong: the Guenstigerpruefung is Abs. 6
> (Abs. 4 is the Ueberpruefung des Steuereinbehalts), and Abs. 6 is inside the 34c carve-out.
> The library already contradicted itself here -- `estg-32d-abgeltungsteuer.md` and
> `research/inlaendisch-auslaendisch-relevance.md` both state the correct position.
> Validation Protocol item 8.

### Where the classification still matters

1. **DBA application** -- treaties may set different rates by source state, which the credit
   under 32d Abs. 5 is measured against.
2. **Evidential** -- a per-country breakdown supports the Zeile 41 figure if the Finanzamt asks
   for treaty-rate substantiation.

---

## Z18 vs. Z19: Form-Level vs. Substantive Classification

The Anlage KAP form instructions use "inlaendisch" and "auslaendisch" in a **procedural** sense, distinct from 34d:

| | Zeile 18 (Inlaendische) | Zeile 19 (Auslaendische) |
|--|-------------------------|--------------------------|
| **Criterion** | Domestic-source income not subject to German withholding | Income from foreign institutions / foreign sources |
| **Form instruction** | "inlaendische Kapitalertraege, die nicht dem Steuerabzug unterlegen haben (z.B. Zinsen aus Privatdarlehen)" | "Ertraege bei auslaendischen Kreditinstituten (z.B. Dividenden und Zinsen einer auslaendischen Schuldnerin)" |
| **Holdings at a foreign broker** | Not used | ALL income (the intermediary is a foreign credit institution) |
| **34d alignment** | Partially overlaps -- but Z18 is about missing Steuerabzug, not necessarily inlaendisch per 34d | Partially overlaps -- but captures all foreign-broker income regardless of issuer domicile |

Consequence: for a portfolio held wholly at a foreign broker, the 34d classification has no
expression anywhere on the declaration. It would become operative only for a per-country credit
computation, which the Abgeltungsteuer regime does not call for -- see
[GT-CREDIT-013] and `research/inlaendisch-auslaendisch-relevance.md`.

---

## [GT-CREDIT-014] Proxies for the Schuldner test, and what they cost

Where a per-security 34d classification is needed, none of the commonly available identifiers
is the *Schuldner* concept the statute uses (Wohnsitz / Geschaeftsleitung / Sitz):

| Proxy | Coverage | Accuracy against 34d | Failure mode |
|-------|----------|----------------------|--------------|
| Issuer country code reported by the broker | Dividends, interest, withholding tax | Good -- names the debtor's country directly | Absent in older statement years; sometimes reported as "XX" |
| ISIN country prefix | All securities with an ISIN | Reasonable -- country of registration usually equals issuer domicile | Fails for e.g. Luxembourg-registered funds of US issuers |
| Issuer country on the positions statement | Held positions | Same as the first, restricted to holdings | Says nothing about income from a position already closed |

Both are accepted in practice as proxies, but neither is the statutory test, and a declaration
resting on one should say so.
