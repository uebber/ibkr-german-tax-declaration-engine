# EStG 23 -- Private Veraeusserungsgeschaefte

## Source

- **Primary:** [gesetze-im-internet.de -- 23 EStG](https://www.gesetze-im-internet.de/estg/__23.html)
- **With court rulings:** [dejure.org -- 23 EStG](https://dejure.org/gesetze/EStG/23.html)
- **EStH commentary:** [EStH 2024 -- 23 Private Veraeusserungsgeschaefte](https://esth.bundesfinanzministerium.de/esth/2024/A-Einkommensteuergesetz/II-Einkommen-2-24b/8-Die-einzelnen-Einkunftsarten-13-24b/g-Sonstige-Einkuenfte-22-23/Paragraf-23/inhalt.html)
- **Detailed guidance:** [EStH 2024 -- Anhang 26 Private Veraeusserungsgeschaefte](https://esth.bundesfinanzministerium.de/esth/2024/C-Anhaenge/Anhang-26/inhalt.html)

## Relevance to Engine

Governs taxation of "other assets" (andere Wirtschaftsguetern) sold within the 1-year speculation period. In this engine: Gold ETCs, Crypto ETPs, and similar assets classified as `PRIVATE_SALE_ASSET`.

Also applies to foreign currency gains on non-interest-bearing accounts (see bmf-guidance/fremdwaehrung-konten.md).

---

## Abs. 1 Nr. 2 -- Other Assets (Andere Wirtschaftsgueter)

**Rule:** Sales of other assets where the period between acquisition and sale does not exceed **one year** are taxable.

**Exclusion:** Assets used for everyday private purposes (Gegenstaende des taeglichen Gebrauchs) are excluded.

### Speculation Period Calculation
- Period runs from acquisition date to sale date
- Per BFH case law: the dates of the binding contracts (obligatorische Vertraege) are decisive
- **Engine implementation:** 365-day threshold in `FifoManager` (holding_period_days <= 365)

### Inherited Assets (Unentgeltlicher Erwerb)
For assets acquired without consideration (gift, inheritance), the acquirer inherits the original acquisition date of the predecessor for purposes of this provision.

---

## Abs. 3 -- Gain Calculation and Exemption Threshold

### Gain Calculation
**Gain/Loss = Sale price - Acquisition/production costs - Advertising expenses (Werbungskosten)**

### Exemption Threshold (Freigrenze)
Gains remain **tax-free** if the total gain from private sales in the calendar year is less than **EUR 1,000** (changed from EUR 600 by JStG 2024 for VZ 2024 onwards).

**Important:** This is a Freigrenze (exemption threshold), NOT a Freibetrag (allowance). If the threshold is exceeded, the ENTIRE gain is taxable.

**Engine note:** The engine currently does not apply the Freigrenze automatically -- it reports the full gain/loss for Anlage SO, and the taxpayer/tax office handles the threshold.

### Loss Offsetting (Satz 7-8)
- Losses may only be offset against gains from private sales (Abs. 1) in the same calendar year
- Losses may NOT be deducted under 10d EStG
- However, losses reduce private sale income in the immediately preceding assessment period or subsequent periods (per 10d EStG analogously)
- This creates a separate loss carryback/forward pool for 23 EStG

**Engine mapping:** `SECTION_23_ESTG_TAXABLE_GAIN` / `SECTION_23_ESTG_TAXABLE_LOSS` -> Anlage SO

---

## Assets Covered by This Engine Under 23 EStG

| Asset | IBKR Type | Rationale |
|-------|-----------|-----------|
| Gold ETCs (e.g., Xetra-Gold) | Commodity ETC | Physical gold claim, not a security under 20 EStG |
| Crypto ETPs | Crypto ETP | Tracks crypto, treated as "other asset" |
| Commodity ETCs | Commodity ETC | Physical commodity claim |

### Why not 20 EStG?
These instruments represent claims on physical commodities or crypto assets, not capital claims (Kapitalforderungen) or shares in corporations. The BFH has confirmed that Xetra-Gold constitutes a claim on physical gold delivery, making gains/losses subject to 23 EStG rather than 20 EStG (BFH VIII R 4/15, VIII R 7/17, VIII R 35/14).

---

## Form Mapping

| Situation | Form | Line |
|-----------|------|------|
| Gain within speculation period | Anlage SO | Zeile 54 (other assets) |
| Loss within speculation period | Anlage SO | Zeile 54 (negative) |
| Holding period > 1 year | Not reported | Tax-exempt |

**Engine mapping:**
- `is_within_speculation_period = True` -> `SECTION_23_ESTG_TAXABLE_GAIN` or `SECTION_23_ESTG_TAXABLE_LOSS`
- `is_within_speculation_period = False` -> `SECTION_23_ESTG_EXEMPT_HOLDING_PERIOD_MET` (record-keeping only)
