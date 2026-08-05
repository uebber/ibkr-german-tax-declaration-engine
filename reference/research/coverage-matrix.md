# Coverage Matrix: Taxable Events & Assets vs. Legal Sources

## Asset Types

"Covered in" names a file that **states the rule**, not merely one that mentions the asset. Where
the library has no substantive entry, the row says so — a matrix that claims coverage it does not
have is worse than one with a visible hole.

| Asset Type | Primary Law | Admin Guidance | Form Reference | Reference File |
|------------|-------------|----------------|----------------|----------------|
| Stocks (Aktien) | EStG 20 Abs. 1 Nr. 1, Abs. 2 S. 1 Nr. 1 | BMF 14.05.2025 | Anlage KAP Z19-23 | tax-law/estg-20-kapitalvermoegen.md |
| Bonds (Anleihen) | EStG 20 Abs. 1 Nr. 7, Abs. 2 S. 1 Nr. 7 i.V.m. S. 2 | BMF 14.05.2025 | Anlage KAP Z19,22 | tax-law/estg-20-kapitalvermoegen.md |
| Investment Funds | InvStG 16, 18, 19, 20, 22 | BMF InvStG guidance | Anlage KAP-INV Z4-55 | investment-tax-law/*.md |
| Options/Derivatives | EStG 20 Abs. 1 Nr. 11, Abs. 2 S. 1 Nr. 3 Buchst. a/b, Abs. 4 S. 5 | BMF 14.05.2025 Rz. 9-47 | Anlage KAP Z19-24 | tax-law/estg-20-kapitalvermoegen.md |
| CFDs | EStG 20 Abs. 2 S. 1 Nr. 3 | BMF 14.05.2025 **Rz. 9** | Anlage KAP Z19-24 | abgeltungsteuer-einzelfragen.md [GT-ESTG20-038] -- Rz. 9 names CFDs expressly, with Waehrungspaare among the Basiswerte and Edelmetalle among the Bezugsgroessen. No longer an analogy. |
| Private Sale Assets | EStG 23 Abs. 1 S. 1 Nr. 2 | BMF 14.05.2025 Rz. 57; EStH Anhang 26, H 23 EStH | Anlage SO Z48-55 | tax-law/estg-23-private-veraeusserung.md |
| Foreign Currency | EStG 20 Abs. 2 S. 1 Nr. 7 / 23 Abs. 1 S. 1 Nr. 2 (depends on verzinslich) | BMF 14.05.2025 Rz. 131 | Anlage KAP Z19,22 or Anlage SO | bmf-guidance/fremdwaehrung-konten.md |

## Taxable Events

| Event | Primary Law | Paragraph | Form Line | Covered In |
|-------|-------------|-----------|-----------|------------|
| Stock sale (long) | EStG | 20 Abs. 2 Nr. 1 | KAP Z20 | estg-20-kapitalvermoegen.md |
| Stock sale (short cover) | EStG | 20 Abs. 2 Nr. 1 | KAP Z20 | estg-20-kapitalvermoegen.md |
| Dividend (cash) | EStG | 20 Abs. 1 Nr. 1 | KAP Z19 | estg-20-kapitalvermoegen.md |
| Interest received | EStG | 20 Abs. 1 Nr. 7 | KAP Z19 | estg-20-kapitalvermoegen.md |
| Stueckzinsen (paid) | EStG | 20 Abs. 4 | KAP Z19 (neg.) | **no substantive entry** -- listed as a topic in `bmf-guidance/abgeltungsteuer-einzelfragen.md`, stated nowhere |
| Currency conversion of a non-EUR transaction | EStG | 20 Abs. 4 S. 1 Hs. 2 (each leg at its own date) | (every non-EUR figure) | estg-20-kapitalvermoegen.md [GT-ESTG20-022] |
| Gain on a Termingeschaeft | EStG | 20 Abs. 4 S. 5 (Differenzausgleich less direct costs) | KAP Z21/19 | estg-20-kapitalvermoegen.md [GT-ESTG20-023] |
| Sparer-Pauschbetrag; no actual Werbungskosten | EStG | 20 Abs. 9 | KAP Z16/17 (portion already used) | estg-20-kapitalvermoegen.md [GT-ESTG20-024] |
| Lot identification (Fifo), securities | EStG | 20 Abs. 4 S. 7 + BMF 14.05.2025 Rz. 97-99 (je Depot) | (all disposals) | estg-20-kapitalvermoegen.md |
| Lot identification (Fifo), currency | EStG / BMF | 23 Abs. 1 S. 1 Nr. 2 S. 3 (Tier 1) for the 23 branch; BMF 14.05.2025 Rz. 131 for the 20 branch | (all currency disposals) | estg-23-private-veraeusserung.md [GT-ESTG23-013], fremdwaehrung-konten.md [GT-FX-008] |
| Bond sale | EStG | 20 Abs. 2 Nr. 7 | KAP Z19/22 | estg-20-kapitalvermoegen.md |
| Bond maturity (BM) | EStG | 20 Abs. 2 S. 1 Nr. 7 i.V.m. S. 2 (Einlösung) | KAP Z19/22 | estg-20-kapitalvermoegen.md |
| Option premium (Stillhalter) | EStG | 20 Abs. 1 Nr. 11 | KAP Z19 | estg-20-kapitalvermoegen.md |
| Option close (trade) | EStG | 20 Abs. 2 Nr. 3 | KAP Z21/19 | estg-20-kapitalvermoegen.md |
| Option expiration worthless | EStG | 20 Abs. 2 Nr. 3 | KAP Z21/22/19 | estg-20-kapitalvermoegen.md |
| Option exercise/assignment | EStG | 20 Abs. 2 (disposal of the Basiswert); premium stays under Abs. 1 Nr. 11 and does **not** enter the Veraeusserungsgewinn -- BMF 14.05.2025 Rz. 26 | (cost basis adj.) | estg-20-kapitalvermoegen.md [GT-ESTG20-004] |
| Option cash settlement (Barausgleich) | EStG | 20 Abs. 2 S. 1 Nr. 3 **Buchst. a** (not "Nr. 3a") | KAP Z21/19 | estg-20-kapitalvermoegen.md [GT-ESTG20-007] |
| Cash merger | EStG | 20 Abs. 2 Nr. 1 | KAP Z19/20 | estg-20-kapitalvermoegen.md |
| Stock merger | EStG | 20 Abs. 4a | (steuerneutral) | estg-20-kapitalvermoegen.md |
| Stock split | EStG | 20 Abs. 4a | (cost adj.) | estg-20-kapitalvermoegen.md |
| Stock dividend | EStG | 20 Abs. 4a Satz 5 | (varies) | estg-20-kapitalvermoegen.md |
| Foreign WHT | EStG | 32d Abs. 5 **only** -- 34c Abs. 1 is carved out for Abgeltungsteuer income by its own Satz 1 zweiter Halbsatz | KAP Z41 | estg-32d-abgeltungsteuer.md, estg-34d-auslaendische-einkuenfte.md [GT-CREDIT-012] |
| German KESt on German dividend (foreign depot) | EStG | 43 Abs. 1 S. 1 Nr. 1a i.V.m. 44 Abs. 1 S. 4 Nr. 3 | KAP Z7 + Z37/Z38/Z39 | estg-36-45a-kapitalertragsteuer-anrechnung.md |
| KESt credit / Steuerbescheinigung | EStG | 36 Abs. 2 S. 1 Nr. 2, S. 2; 45a Abs. 2/3 | KAP Z37 | estg-36-45a-kapitalertragsteuer-anrechnung.md |
| Fund distribution | InvStG | 16 Abs. 1 Nr. 1 | KAP-INV Z4-8 | invstg-16-investmentertraege.md |
| Vorabpauschale | InvStG | 18 Abs. 1; Zufluss 18 Abs. 3 | KAP-INV Z9-13 (for calendar year VZ-1) | invstg-18-vorabpauschale.md |
| Fund sale gain/loss | InvStG | 19 Abs. 1 S. 1-2 | KAP-INV Z14-26 | invstg-19-veraeusserungsgewinne.md |
| VP deduction on sale | InvStG | 19 Abs. 1 S. 3-4 | KAP-INV **Z53** (not Z55) | invstg-19-veraeusserungsgewinne.md |
| FX gain (explicit conversion) | EStG | 20 Abs. 2 S. 1 Nr. 7 i.V.m. S. 2 (verzinslich) / 23 Abs. 1 S. 1 Nr. 2 (unverzinslich) | KAP Z19/22 or SO | fremdwaehrung-konten.md |
| FX gain (currency leg of a securities trade) | -- | **unresolved**; Rz. 131 does *not* address it | KAP Z19/22 | fremdwaehrung-konten.md [GT-FX-007], open-legal-questions.md Q9 |
| FX gain (currency consumed to settle a cash-flow item) | -- | **unresolved**; Rz. 131 names Veraeusserung and Rueckzahlung, not a payment out of the balance | KAP Z19/22 | fremdwaehrung-konten.md [GT-FX-001], open-legal-questions.md Q10 |
| Private sale (Gold ETC etc.) | EStG | 23 Abs. 1 S. 1 Nr. 2 S. 1 | SO Z54 | estg-23-private-veraeusserung.md |
| Jahresfrist arithmetic | AO / BGB | 108 Abs. 1 AO, 187 Abs. 1 / 188 Abs. 2-3 BGB | (decides SO Z54 vs. exempt) | estg-23-private-veraeusserung.md |
| Jahresfrist, currency lot order | EStG | 23 Abs. 1 S. 1 Nr. 2 S. 3 | (decides which acquisition date is compared) | estg-23-private-veraeusserung.md |
| Capital repayment (Einlagenrueckgewaehr) | EStG | 20 Abs. 1 Nr. 1 S. 3 | (not taxable) | **no substantive entry** -- named only in `tax-forms/anlage-kap-zeilen.md` [GT-FORM-009]; 20 Abs. 1 Nr. 1 Satz 3 is not stated anywhere |

## Loss Offsetting Rules

| Rule | Primary Law | Form Impact | Covered In |
|------|-------------|-------------|------------|
| No cross-income offsetting | EStG 20 Abs. 6 S. 1 | KAP only | estg-20-abs6-verlustverrechnung.md |
| Stock loss ring-fencing | EStG 20 Abs. 6 S. 4 | Z23 separate | estg-20-abs6-verlustverrechnung.md |
| Derivative loss cap (repealed, all open cases) | EStG 20 Abs. 6 S. 5 a.F.; repeal per 52 Abs. 28 S. 25 | Never applied in any VZ; Z21/Z24 still used <= 2024 | estg-20-abs6-verlustverrechnung.md |
| Private sale loss rules | EStG 23 Abs. 3 S. 7-8 | SO only | estg-23-private-veraeusserung.md |
| Fund Teilfreistellung | InvStG 20 | KAP-INV gross | invstg-20-teilfreistellung.md |
| Change of Teilfreistellungssatz -> fiktive Veraeusserung | InvStG 22 Abs. 1 S. 1 | (deemed disposal + reacquisition) | invstg-22-teilfreistellungssatz-aenderung.md |
| Deferral of the fiktive-Veraeusserung gain to the actual disposal | InvStG 22 Abs. 3 S. 1 | decides the VZ; nothing is declared in the year of the fiction | invstg-22-teilfreistellungssatz-aenderung.md [GT-INVSTG-043] |

## Year-Specific Rules

| Rule | 2024 and earlier | 2025 and later | Source |
|------|------------------|----------------|--------|
| Derivative loss cap | **Not applied in any year.** The repeal is addressed to *alle offenen Faelle* (52 Abs. 28 S. 25/26 EStG), not to a first year of application -- a return prepared now for VZ 2021-2024 is such a case | Not applied | estg-20-abs6-verlustverrechnung.md |
| Separate derivative lines (a *form* question, independent of the repeal above) | Z21 gains, Z24 losses -- in use | Not used; derivative gains net into Z19, losses into Z22. Whether the lines were physically removed from the form is **unresolved**, see [open-legal-questions.md](open-legal-questions.md) Q3 | anlage-kap-zeilen.md |
| SO Freigrenze | EUR 1,000 from VZ 2024 (Wachstumschancengesetz v. 27.03.2024, BGBl. 2024 I Nr. 108); EUR 600 before | EUR 1,000 | estg-23-private-veraeusserung.md |
| Basiszins (for the VP *of* that calendar year, declared the following VZ) | 2.29% (2024), 2.53% (2025) | 3.20% (2026) | basiszins-vorabpauschale.md |

## Open questions and pending developments

Both now live in [open-legal-questions.md](open-legal-questions.md), which states each question's
two readings and the authority behind each. Which reading was adopted is recorded separately, in
`docs/legal-implementation-map.md` -- Validation Protocol item 7.
