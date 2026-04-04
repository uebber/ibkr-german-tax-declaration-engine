# Research Strategy: Tax & Legal Source Collection

## Objective

Build a curated, high-quality reference library of German tax law sources covering all taxable events and asset types supported by this engine. These references serve as ground truth for validation testing.

## Source Ranking (Tier System)

### Tier 1 -- Primary Law (highest authority)

| Source | URL | Description |
|--------|-----|-------------|
| gesetze-im-internet.de | https://www.gesetze-im-internet.de | Official federal law texts (BMJ) |
| dejure.org | https://dejure.org | Consolidated law with amendment history and court rulings |
| buzer.de | https://www.buzer.de | Law texts with version tracking across amendments |

**Use for:** Exact statutory text, paragraph/section references, effective dates of amendments.

### Tier 2 -- Official Administrative Guidance

| Source | URL | Description |
|--------|-----|-------------|
| BMF-Schreiben | https://www.bundesfinanzministerium.de | Federal Ministry of Finance circulars |
| EStH (Amtliches Einkommensteuer-Handbuch) | https://esth.bundesfinanzministerium.de | Official income tax handbook |
| Bundessteuerblatt (BStBl) | Published via BMF | Official tax gazette |
| BMF Basiszins publications | via BMF Downloads | Annual Vorabpauschale base rate notices |

**Use for:** Administrative interpretation, form line mappings, Basiszins rates, Steuerbescheinigung rules.

### Tier 3 -- Official Forms & Instructions

| Source | URL | Description |
|--------|-----|-------------|
| formulare-bfinv.de | https://www.formulare-bfinv.de | Official tax form downloads |
| ELSTER Help | https://www.elster.de/eportal/helpGlobal | Official electronic filing guidance |

**Use for:** Form structure, line numbers, filing instructions.

### Tier 4 -- Court Decisions

| Source | URL | Description |
|--------|-----|-------------|
| Bundesfinanzhof (BFH) | https://www.bundesfinanzhof.de | Federal Fiscal Court decisions |
| Bundesverfassungsgericht (BVerfG) | https://www.bundesverfassungsgericht.de | Constitutional Court (pending: 2 BvL 3/21) |

**Use for:** Authoritative interpretation, constitutional challenges, binding precedent.

### Tier 5 -- Professional Commentary (use for interpretation only)

| Source | URL | Description |
|--------|-----|-------------|
| Haufe Finance | https://www.haufe.de | Tax professional commentary |
| NWB Datenbank | https://datenbank.nwb.de | Tax professional database |
| Kleeberg | https://www.kleeberg.de | Tax advisory firm publications |

**Use for:** Cross-checking interpretations, identifying edge cases. Never as sole source.

## Validation Protocol

1. **Every claim** must trace back to at least a Tier 1 or Tier 2 source
2. **Year-specific rules** must reference the exact amendment law (e.g., JStG 2024, BGBl. I Nr. 387)
3. **Tax rates/thresholds** must cite the specific paragraph and sentence number
4. **Form line mappings** must be verified against the official form for the specific tax year
5. **Cross-check** any Tier 4/5 interpretation against Tier 1 statute text

## Scope: Supported Taxable Events & Asset Types

### Asset Types
- Stocks (Aktien) -- EStG 20
- Bonds (Anleihen) -- EStG 20
- Investment Funds (Investmentfonds) -- InvStG 2018
- Options/Derivatives (Termingeschaefte) -- EStG 20
- CFDs -- EStG 20
- Private Sale Assets (Gold ETCs, Crypto ETPs) -- EStG 23
- Foreign Currency (Fremdwaehrung) -- EStG 20 / EStG 23

### Taxable Events
- Sale of securities (long/short) -- EStG 20 Abs. 2
- Dividends -- EStG 20 Abs. 1 Nr. 1
- Interest -- EStG 20 Abs. 1 Nr. 7
- Fund distributions -- InvStG 16
- Vorabpauschale -- InvStG 18
- Fund sale gains/losses -- InvStG 19 + 20
- Option premiums (Stillhalterpraemien) -- EStG 20 Abs. 1 Nr. 11
- Option expiration/exercise/assignment -- EStG 20 Abs. 2
- Cash settlement (index options) -- EStG 20 Abs. 2
- Corporate actions (merger, split, stock dividend) -- EStG 20 Abs. 4a
- Foreign withholding tax -- EStG 32d Abs. 5, 34c
- Currency gains/losses -- EStG 20 Abs. 2 / EStG 23
- Private sales within speculation period -- EStG 23 Abs. 1 Nr. 2

### Loss Offsetting Rules
- General capital loss offsetting -- EStG 20 Abs. 6
- Stock loss ring-fencing -- EStG 20 Abs. 6 Satz 4
- Derivative loss restriction (abolished 2025) -- EStG 20 Abs. 6 Satz 5 a.F.
- Private sale loss rules -- EStG 23 Abs. 3 Satz 7-8

## Directory Structure

```
reference/
  tax-law/                  # Primary statute texts and analysis
    estg-20-kapitalvermoegen.md
    estg-23-private-veraeusserung.md
    estg-20-abs6-verlustverrechnung.md
    estg-32d-abgeltungsteuer.md
  investment-tax-law/       # InvStG-specific references
    invstg-16-investmentertraege.md
    invstg-18-vorabpauschale.md
    invstg-19-veraeusserungsgewinne.md
    invstg-20-teilfreistellung.md
  tax-forms/                # Form line mappings by year
    anlage-kap-zeilen.md
    anlage-kap-inv-zeilen.md
    anlage-so-zeilen.md
  bmf-guidance/             # Administrative circulars
    abgeltungsteuer-einzelfragen.md
    basiszins-vorabpauschale.md
    fremdwaehrung-konten.md
  research/                 # Meta-documentation
    research-strategy.md    # This file
    coverage-matrix.md      # Event/asset vs. source mapping
```

## Maintenance

- Review after each Jahressteuergesetz publication
- Update form line references when new tax year forms are released
- Track pending BVerfG decisions (especially 2 BvL 3/21 on stock loss ring-fencing)
- Update Basiszins annually after BMF publication (typically January)
