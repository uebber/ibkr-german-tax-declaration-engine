# EStG 34d -- Auslaendische Einkuenfte

## Source

- **Primary:** [gesetze-im-internet.de -- 34d EStG](https://www.gesetze-im-internet.de/estg/__34d.html)
- **With annotations:** [dejure.org -- 34d EStG](https://dejure.org/gesetze/EStG/34d.html)

## Relevance to Engine

Defines what constitutes "auslaendische Einkuenfte" (foreign income) for the foreign tax credit mechanism (34c, 32d Abs. 5). Determines whether income has a domestic or foreign source based on the debtor's domicile. Distinct from the Anlage KAP Z18/Z19 form-level distinction which is based on the intermediary (broker), not the issuer.

---

## Introductory Sentence

> Auslaendische Einkuenfte im Sinne des 34c Absatz 1 bis 5 sind [...]

The definition applies specifically in the context of the foreign tax credit under 34c.

---

## Nr. 6 -- Einkuenfte aus Kapitalvermoegen (20 EStG)

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

### Practical examples for IBKR accounts

| Transaction | Issuer | 34d classification | Z18 or Z19? |
|-------------|--------|---------------------|-------------|
| BMW dividend via IBKR | BMW AG, Muenchen | **Inlaendisch** (German Schuldner) | Z19 (foreign broker) |
| Apple dividend via IBKR | Apple Inc, USA | **Auslaendisch** (foreign Schuldner) | Z19 (foreign broker) |
| Gain from selling BMW stock via IBKR | BMW AG, Muenchen | **Inlaendisch** (German issuer) | Z19 (foreign broker) |
| Gain from selling Apple stock via IBKR | Apple Inc, USA | **Auslaendisch** (foreign issuer) | Z19 (foreign broker) |
| Interest on IBKR cash balance | IBKR Ireland | **Auslaendisch** (Irish debtor) | Z19 (foreign broker) |

Note: The 34d classification and the Z18/Z19 form placement are **independent**. All IBKR income goes to Z19 because the broker is foreign (form instructions: "Ertraege bei auslaendischen Kreditinstituten"). The 34d classification is relevant for WHT credit and Guenstigerpruefung.

---

## Relationship to 34c and 32d Abs. 5

### General rule (34c Abs. 1)
Foreign tax credit is computed per 34c Abs. 1 using the Anrechnungshoechstbetrag (maximum credit = German tax attributable to foreign income).

### Exception for Abgeltungsteuer (34c Abs. 1 Satz 4)
34c Abs. 1 explicitly **excludes** capital income subject to 32d Abs. 1 (Abgeltungsteuer):
> "das gilt nicht fuer Einkuenfte aus Kapitalvermoegen, auf die 32d Absatz 1 und 3 bis 6 anzuwenden ist"

### Capital income credit mechanism (32d Abs. 5)
Instead, 32d Abs. 5 provides a direct credit mechanism for foreign WHT on Abgeltungsteuer-subject income. This is simpler than 34c's general Anrechnungshoechstbetrag.

### When 34d classification matters despite Abgeltungsteuer

1. **Guenstigerpruefung** (32d Abs. 4): If the taxpayer elects taxation at regular rates, capital income falls back under 34c Abs. 1 and the per-country Anrechnungshoechstbetrag based on 34d applies.

2. **DBA application**: Double taxation agreements may apply different rules for domestic vs. foreign-source capital income.

3. **Reporting transparency**: Per-country breakdowns aid Finanzamt verification and DBA compliance.

---

## Z18 vs. Z19: Form-Level vs. Substantive Classification

The Anlage KAP form instructions use "inlaendisch" and "auslaendisch" in a **procedural** sense, distinct from 34d:

| | Zeile 18 (Inlaendische) | Zeile 19 (Auslaendische) |
|--|-------------------------|--------------------------|
| **Criterion** | Domestic-source income not subject to German withholding | Income from foreign institutions / foreign sources |
| **Form instruction** | "inlaendische Kapitalertraege, die nicht dem Steuerabzug unterlegen haben (z.B. Zinsen aus Privatdarlehen)" | "Ertraege bei auslaendischen Kreditinstituten (z.B. Dividenden und Zinsen einer auslaendischen Schuldnerin)" |
| **For IBKR accounts** | Not used (IBKR is foreign) | ALL income (because IBKR is a foreign credit institution) |
| **34d alignment** | Partially overlaps -- but Z18 is about missing Steuerabzug, not necessarily inlaendisch per 34d | Partially overlaps -- but captures all foreign-broker income regardless of issuer domicile |

### Engine implication

The engine correctly routes all IBKR capital income to Z19 (`ANLAGE_KAP_AUSLAENDISCHE_KAPITALERTRAEGE_GESAMT`). This is correct per the form instructions. A separate 34d-level per-security classification is only needed if the engine adds Guenstigerpruefung support or per-country credit cap calculations.

---

## Data Sources for 34d Classification

If per-security classification is implemented:

| Data source | Coverage | Accuracy for 34d | Notes |
|-------------|----------|-------------------|-------|
| `issuerCountryCode` (Cash Transactions CSV) | Dividends, interest, WHT | Good -- directly identifies debtor country | Empty in older years (2021-2022); sometimes "XX" |
| ISIN prefix (`Asset.ibkr_isin`, first 2 chars) | All securities with ISIN | Reasonable -- country of registration usually = issuer domicile | Exceptions: Luxembourg-registered funds of US issuers |
| Positions CSV `IssuerCountryCode` | Available in CSV | Not currently parsed into Asset | Could enrich Asset model with issuer country |

Neither source perfectly matches 34d's "Schuldner" concept (Wohnsitz/Geschaeftsleitung/Sitz), but for practical tax declaration purposes both are accepted proxies.
