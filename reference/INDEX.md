# Reference Library -- German Tax Law Sources

Curated collection of German tax and legal sources. All sources are ranked by authority tier
(see research/research-strategy.md).

**This library states law and nothing else.** It names no module, class, field, test or data
file. Implementation positions -- what is implemented, what deviates, what is out of scope, and
which tests guard each -- are recorded in
[`docs/legal-implementation-map.md`](../docs/legal-implementation-map.md), keyed by the claim IDs
tagged on the headings here. See the Purity Rule in CLAUDE.md.

## Tax Law (EStG)

- [EStG 20 -- Kapitalvermoegen](tax-law/estg-20-kapitalvermoegen.md) -- Central statute for all capital income (dividends, gains, options, corporate actions)
- [EStG 20 Abs. 6 -- Verlustverrechnung](tax-law/estg-20-abs6-verlustverrechnung.md) -- Loss offsetting rules, stock ring-fencing, abolished derivative cap
- [EStG 23 -- Private Veraeusserung](tax-law/estg-23-private-veraeusserung.md) -- Private sales (Gold ETCs, Crypto ETPs), 1-year speculation period
- [EStG 32d -- Abgeltungsteuer](tax-law/estg-32d-abgeltungsteuer.md) -- Flat tax rate (25%), Veranlagungspflicht (Abs. 3), foreign tax credit (Abs. 5), Guenstigerpruefung (Abs. 6)
- [EStG 34d -- Auslaendische Einkuenfte](tax-law/estg-34d-auslaendische-einkuenfte.md) -- Schuldner-domicile test for foreign-source income; distinct from the Z18/Z19 form split
- [EStG 36 / 45a -- Anrechnung inlaendischer KESt](tax-law/estg-36-45a-kapitalertragsteuer-anrechnung.md) -- German KESt on German dividends held via a foreign broker: Zeile 7/37/38/39 (NOT Zeile 41), Steuerbescheinigung requirement

## Investment Tax Law (InvStG)

- [InvStG 16 -- Investmentertraege](investment-tax-law/invstg-16-investmentertraege.md) -- Definition of taxable fund income
- [InvStG 18 -- Vorabpauschale](investment-tax-law/invstg-18-vorabpauschale.md) -- Deemed minimum income, Basiszins, calculation formula
- [InvStG 19 -- Veraeusserungsgewinne](investment-tax-law/invstg-19-veraeusserungsgewinne.md) -- Fund sale gain calculation, VP deduction
- [InvStG 20 -- Teilfreistellung](investment-tax-law/invstg-20-teilfreistellung.md) -- Partial exemption rates by fund type (30%/15%/60%/80%); fund type definitions and their thresholds
- [InvStG 22 -- Aenderung des Teilfreistellungssatzes](investment-tax-law/invstg-22-teilfreistellungssatz-aenderung.md) -- fiktive Veraeusserung when the applicable rate changes or its conditions lapse

## Tax Forms (Zeilen-Referenz)

- [Anlage KAP -- Zeilen](tax-forms/anlage-kap-zeilen.md) -- KAP form line mappings (Z4/5, Z7, Z18-25, Z37-41), the *zusaetzlich* / *ausschliesslich* split, year-specific differences
- [Anlage KAP-INV -- Zeilen](tax-forms/anlage-kap-inv-zeilen.md) -- KAP-INV form lines (Z4-55), gross reporting principle
- [Anlage SO -- Zeilen](tax-forms/anlage-so-zeilen.md) -- SO form lines for private sales (Z48-55)

## BMF Guidance (Administrative Circulars)

- [Einzelfragen Abgeltungsteuer](bmf-guidance/abgeltungsteuer-einzelfragen.md) -- Central BMF guidance (14.05.2025, Rz. 1-325); retrieved in full 2026-08-03. Index into the document, plus its version history and application rule
- [Basiszins Vorabpauschale](bmf-guidance/basiszins-vorabpauschale.md) -- Published rates 2018-2026, one BMF-Schreiben cited per row
- [Fremdwaehrung Konten](bmf-guidance/fremdwaehrung-konten.md) -- FX gain classification (20 vs. 23 EStG); BMF 14.05.2025 Rz. 131 verbatim

## Existing Form Instructions (OCR)

- [Anltg_KAP_24.md](Anltg_KAP_24.md) -- Anlage KAP 2024 instructions (full text)
- [Anltg_KAP_25.md](Anltg_KAP_25.md) -- Anlage KAP 2025 instructions (full text)
- [Anltg_KAP_INV_24.md](Anltg_KAP_INV_24.md) -- Anlage KAP-INV 2024 instructions (full text)
- [Anltg_KAP_INV_25.md](Anltg_KAP_INV_25.md) -- Anlage KAP-INV 2025 instructions (full text)

## Research Meta-Documentation

- [Research Strategy](research/research-strategy.md) -- Source ranking (5 tiers), validation protocol, claim IDs, how the library may be extended
- [Coverage Matrix](research/coverage-matrix.md) -- Event/asset vs. source mapping, completeness check
- [Open Legal Questions](research/open-legal-questions.md) -- points no Tier 1/2 source settles: both readings and both authorities, for each
- [Inlaendisch vs. Auslaendisch: relevance](research/inlaendisch-auslaendisch-relevance.md) -- why the 34d distinction has no expression on the declaration under Abgeltungsteuer
