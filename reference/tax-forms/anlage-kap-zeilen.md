# Anlage KAP -- Zeilenreferenz

## Source

- **2024 Form:** [formulare-bfinv.de -- Anlage KAP](https://www.formulare-bfinv.de/ffw/action/invoke.do?id=034024_17)
- **2024 Instructions:** Already in repository: `reference/Anltg_KAP_24.md`
- **2025 Instructions:** Already in repository: `reference/Anltg_KAP_25.md`
- **EStH 2024 Anhang 19 I:** [esth.bundesfinanzministerium.de](https://esth.bundesfinanzministerium.de/esth/2024/C-Anhaenge/Anhang-19/I/inhalt.html)
- **BMF Steuerbescheinigung:** [BMF-Schreiben 16.05.2025 (PDF)](https://www.bundesfinanzministerium.de/Content/DE/Downloads/BMF_Schreiben/Steuerarten/Abgeltungsteuer/2025-05-16-kapitalertragSt-steuerbescheinigung.pdf?__blob=publicationFile&v=5)

## Relevance to Engine

Maps engine output (TaxReportingCategory) to specific form lines on Anlage KAP.

---

## Key Lines Used by Engine

### 2024 Form Structure

| Zeile | Description | Engine TaxReportingCategory | EStG Basis |
|-------|-------------|----------------------------|------------|
| 7 | Hoehe der Kapitalertraege (von Steuerbescheinigung) | (informational) | 20 |
| 19 | Auslaendische Kapitalertraege (net) | `ANLAGE_KAP_AUSLAENDISCHE_KAPITALERTRAEGE_GESAMT` | 20 Abs. 1+2 |
| 20 | Gewinne aus Aktienveraeusserungen | `ANLAGE_KAP_AKTIEN_GEWINN` | 20 Abs. 2 Nr. 1 |
| 21 | Gewinne aus Termingeschaeften | `ANLAGE_KAP_TERMIN_GEWINN` | 20 Abs. 2 Nr. 3 |
| 22 | Verluste ohne Aktien und Termingeschaefte | `ANLAGE_KAP_SONSTIGE_VERLUSTE` | 20 Abs. 6 |
| 23 | Verluste aus Aktienveraeusserungen | `ANLAGE_KAP_AKTIEN_VERLUST` | 20 Abs. 6 S. 4 |
| 24 | Verluste aus Termingeschaeften | `ANLAGE_KAP_TERMIN_VERLUST` | 20 Abs. 6 S. 5 a.F. |
| 41 | Anrechenbare auslaendische Steuern | `ANLAGE_KAP_FOREIGN_TAX_PAID` | 32d Abs. 5, 34c |

### 2025 Form Structure (Verlustverrechnungsbeschraenkung abolished)

| Zeile | Description | Engine TaxReportingCategory | Change vs 2024 |
|-------|-------------|----------------------------|----------------|
| 19 | Auslaendische Kapitalertraege (net) | `ANLAGE_KAP_AUSLAENDISCHE_KAPITALERTRAEGE_GESAMT` | Now includes derivative gains/losses |
| 20 | Gewinne aus Aktienveraeusserungen | `ANLAGE_KAP_AKTIEN_GEWINN` | Unchanged |
| 21 | (entfaellt / removed) | 0.00 | Derivative gains merged into Z19 |
| 22 | Verluste ohne Aktienveraeusserungen | `ANLAGE_KAP_SONSTIGE_VERLUSTE` | Now includes derivative losses |
| 23 | Verluste aus Aktienveraeusserungen | `ANLAGE_KAP_AKTIEN_VERLUST` | Unchanged |
| 24 | (entfaellt / removed) | 0.00 | Derivative losses merged into Z22 |
| 41 | Anrechenbare auslaendische Steuern | `ANLAGE_KAP_FOREIGN_TAX_PAID` | Unchanged |

---

## Zeile 19 Calculation Logic

### 2024 (separate_derivative_lines = True)
```
Z19 = Stock_Gains
    - Stock_Losses
    + Other_Capital_Income (dividends, interest, bond gains, FX gains, fees)
    - Other_Losses (bond losses, FX losses, non-stock/non-derivative losses)
    + Derivative_Gains
    (derivative losses NOT subtracted)
```

### 2025 (separate_derivative_lines = False)
```
Z19 = Stock_Gains
    - Stock_Losses
    + Other_Capital_Income
    - Other_Losses
    + Derivative_Gains
    - Derivative_Losses
```

---

## What Goes Into Each Category

### Stock Gains/Losses (Z20/Z23)
- Sale of long stock positions
- Covering short stock positions
- Cash merger proceeds (stock)

### Derivative Gains/Losses (Z21/Z24 for 2024; merged for 2025)
- Option trade close (long/short)
- Option expiration worthless (long/short)
- Option cash settlement (long/short)
- CFD gains/losses

### Other Capital Income / Losses (component of Z19, Z22)
- Dividends (cash)
- Interest received
- Bond sale gains/losses
- FX conversion gains/losses (on interest-bearing accounts, per 20 EStG)
- Implicit FX gains/losses from security trades
- Transaction fees (negative)
- Stueckzinsen (paid = negative income at acquisition)

### NOT on Anlage KAP
- Investment fund income -> Anlage KAP-INV
- Private sale assets (Gold ETC, Crypto ETP) -> Anlage SO
- Capital repayments (Einlagenrueckgewaehr) -> not taxable
