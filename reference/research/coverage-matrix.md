# Coverage Matrix: Taxable Events & Assets vs. Legal Sources

## Asset Types

| Asset Type | Primary Law | Admin Guidance | Form Reference | Reference File |
|------------|-------------|----------------|----------------|----------------|
| Stocks (Aktien) | EStG 20 Abs. 1 Nr. 1, Abs. 2 Nr. 1 | BMF Abgeltungsteuer | Anlage KAP Z19-23 | tax-law/estg-20-kapitalvermoegen.md |
| Bonds (Anleihen) | EStG 20 Abs. 1 Nr. 7, Abs. 2 Nr. 7 | BMF Abgeltungsteuer | Anlage KAP Z19,22 | tax-law/estg-20-kapitalvermoegen.md |
| Investment Funds | InvStG 16, 18, 19, 20 | BMF InvStG guidance | Anlage KAP-INV Z4-55 | investment-tax-law/*.md |
| Options/Derivatives | EStG 20 Abs. 1 Nr. 11, Abs. 2 Nr. 3 | BMF Abgeltungsteuer | Anlage KAP Z19-24 | tax-law/estg-20-kapitalvermoegen.md |
| CFDs | EStG 20 Abs. 2 Nr. 3 | BMF Abgeltungsteuer | Anlage KAP Z19-24 | tax-law/estg-20-kapitalvermoegen.md |
| Private Sale Assets | EStG 23 Abs. 1 Nr. 2 | EStH Anhang 26 | Anlage SO Z48-55 | tax-law/estg-23-private-veraeusserung.md |
| Foreign Currency | EStG 20/23 (depends) | BMF Abgeltungsteuer | Anlage KAP Z19,22 | bmf-guidance/fremdwaehrung-konten.md |

## Taxable Events

| Event | Primary Law | Paragraph | Form Line | Covered In |
|-------|-------------|-----------|-----------|------------|
| Stock sale (long) | EStG | 20 Abs. 2 Nr. 1 | KAP Z20 | estg-20-kapitalvermoegen.md |
| Stock sale (short cover) | EStG | 20 Abs. 2 Nr. 1 | KAP Z20 | estg-20-kapitalvermoegen.md |
| Dividend (cash) | EStG | 20 Abs. 1 Nr. 1 | KAP Z19 | estg-20-kapitalvermoegen.md |
| Interest received | EStG | 20 Abs. 1 Nr. 7 | KAP Z19 | estg-20-kapitalvermoegen.md |
| Stueckzinsen (paid) | EStG | 20 Abs. 4 | KAP Z19 (neg.) | estg-20-kapitalvermoegen.md |
| Bond sale | EStG | 20 Abs. 2 Nr. 7 | KAP Z19/22 | estg-20-kapitalvermoegen.md |
| Bond maturity (BM) | EStG | 20 Abs. 2 S. 1 Nr. 7 i.V.m. S. 2 (Einlösung) | KAP Z19/22 | estg-20-kapitalvermoegen.md |
| Option premium (Stillhalter) | EStG | 20 Abs. 1 Nr. 11 | KAP Z19 | estg-20-kapitalvermoegen.md |
| Option close (trade) | EStG | 20 Abs. 2 Nr. 3 | KAP Z21/19 | estg-20-kapitalvermoegen.md |
| Option expiration worthless | EStG | 20 Abs. 2 Nr. 3 | KAP Z21/22/19 | estg-20-kapitalvermoegen.md |
| Option exercise/assignment | EStG | 20 Abs. 4a (analog) | (cost basis adj.) | estg-20-kapitalvermoegen.md |
| Option cash settlement | EStG | 20 Abs. 2 Nr. 3a | KAP Z21/19 | estg-20-kapitalvermoegen.md |
| Cash merger | EStG | 20 Abs. 2 Nr. 1 | KAP Z19/20 | estg-20-kapitalvermoegen.md |
| Stock merger | EStG | 20 Abs. 4a | (steuerneutral) | estg-20-kapitalvermoegen.md |
| Stock split | EStG | 20 Abs. 4a | (cost adj.) | estg-20-kapitalvermoegen.md |
| Stock dividend | EStG | 20 Abs. 4a Satz 5 | (varies) | estg-20-kapitalvermoegen.md |
| Foreign WHT | EStG | 32d Abs. 5, 34c | KAP Z41 | estg-32d-abgeltungsteuer.md |
| German KESt on German dividend (foreign depot) | EStG | 43 Abs. 1 S. 1 Nr. 1a i.V.m. 44 Abs. 1 S. 4 Nr. 3 | KAP Z7 + Z37/Z38/Z39 | estg-36-45a-kapitalertragsteuer-anrechnung.md |
| KESt credit / Steuerbescheinigung | EStG | 36 Abs. 2 S. 1 Nr. 2, S. 2; 45a Abs. 2/3 | KAP Z37 | estg-36-45a-kapitalertragsteuer-anrechnung.md |
| Fund distribution | InvStG | 16 Abs. 1 Nr. 1 | KAP-INV Z4-8 | invstg-16-investmentertraege.md |
| Vorabpauschale | InvStG | 18 | KAP-INV Z9-13 | invstg-18-vorabpauschale.md |
| Fund sale gain/loss | InvStG | 19 | KAP-INV Z14-26 | invstg-19-veraeusserungsgewinne.md |
| VP deduction on sale | InvStG | 19 Abs. 1 S. 3-4 | KAP-INV Z55 | invstg-19-veraeusserungsgewinne.md |
| FX gain (explicit) | EStG | 20 Abs. 2 Nr. 7 | KAP Z19/22 | fremdwaehrung-konten.md |
| FX gain (implicit) | EStG | 20 Abs. 2 Nr. 7 | KAP Z19/22 | fremdwaehrung-konten.md |
| Private sale (Gold ETC etc.) | EStG | 23 Abs. 1 Nr. 2 | SO Z54 | estg-23-private-veraeusserung.md |
| Capital repayment | EStG | 20 Abs. 1 Nr. 1 S. 3 | (not taxable) | estg-20-kapitalvermoegen.md |

## Loss Offsetting Rules

| Rule | Primary Law | Form Impact | Covered In |
|------|-------------|-------------|------------|
| No cross-income offsetting | EStG 20 Abs. 6 S. 1 | KAP only | estg-20-abs6-verlustverrechnung.md |
| Stock loss ring-fencing | EStG 20 Abs. 6 S. 4 | Z23 separate | estg-20-abs6-verlustverrechnung.md |
| Derivative loss cap (abolished) | EStG 20 Abs. 6 S. 5 a.F. | Z24 removed 2025 | estg-20-abs6-verlustverrechnung.md |
| Private sale loss rules | EStG 23 Abs. 3 S. 7-8 | SO only | estg-23-private-veraeusserung.md |
| Fund Teilfreistellung | InvStG 20 | KAP-INV gross | invstg-20-teilfreistellung.md |

## Year-Specific Rules

| Rule | 2024 and earlier | 2025 and later | Source |
|------|------------------|----------------|--------|
| Derivative loss cap | 20k EUR cap (S. 5) | Abolished (JStG 2024) | estg-20-abs6-verlustverrechnung.md |
| Separate derivative lines | Z21 gains, Z24 losses | Merged into Z19/Z22 | anlage-kap-zeilen.md |
| SO Freigrenze | EUR 1,000 (since 2024) | EUR 1,000 | estg-23-private-veraeusserung.md |
| Basiszins | 2.29% (2024), 2.53% (2025) | 3.20% (2026) | basiszins-vorabpauschale.md |

## Pending Legal Developments

| Case | Subject | Impact on Engine | Status |
|------|---------|------------------|--------|
| BVerfG 2 BvL 3/21 | Stock loss ring-fencing | Could abolish Z23 separation | Pending |
