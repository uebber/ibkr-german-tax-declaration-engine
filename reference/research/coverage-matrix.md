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
| Unallocated spot precious metal | unsettled -- 20 Abs. 2 Nr. 3 / 23 Abs. 1 Nr. 2 / 20 Abs. 2 Nr. 7 | none located | unsettled | **open-legal-questions.md Q11** -- three readings, no Tier 1/2 source chooses |
| CFDs | EStG 20 Abs. 2 S. 1 Nr. 3 | BMF 14.05.2025 **Rz. 9** | Anlage KAP Z19-24 | abgeltungsteuer-einzelfragen.md [GT-ESTG20-038] -- Rz. 9 names CFDs expressly, with Waehrungspaare among the Basiswerte and Edelmetalle among the Bezugsgroessen. No longer an analogy. |
| Optionsscheine (warrants) | EStG 20 Abs. 1 Nr. 7, Abs. 2 S. 1 Nr. 7 | BMF 14.05.2025 **Rn. 8** | Anlage KAP Z19,22 | abgeltungsteuer-einzelfragen.md [GT-ESTG20-038] -- *"Optionsscheine sind Kapitalforderungen im Sinne des § 20 Absatz 1 Nummer 7 EStG"*, and expressly not a Termingeschaeft. Never traded on this account; recorded so Rn. 9's exclusion does not dangle. |
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
| Whose holding is declared | EStG | 2 Abs. 1 S. 1 Nr. 5 i.V.m. 25 Abs. 1, Abs. 3 S. 1 (the person and the Veranlagungszeitraum are the units) | (every figure) | estg-20-kapitalvermoegen.md [GT-ESTG20-061] |
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
| Fund distribution | InvStG | 16 Abs. 1 Nr. 1 (closed list; the payer is named: *"des Investmentfonds"*); definitions at 2 Abs. 10 and Abs. 11 with BMF 21.05.2019 Rz. 2.44 | KAP-INV Z4-8 | invstg-16-investmentertraege.md [GT-INVSTG-001], [GT-INVSTG-057], [GT-INVSTG-058] |
| Securities on loan -- whose they are | AO / BMF | 39 Abs. 1 and Abs. 2 Nr. 1 S. 1 AO; BMF 09.07.2021 Rz. 1-9 (Grundfall, Gesamtschau, five criteria, burden on the borrower), Rz. 11-12 (consequences) | (decides whose income every event on the security is) | bmf-guidance/wertpapierdarlehen-zurechnung.md [GT-ESTG20-042] to [GT-ESTG20-046] |
| Substitute payment on lent fund units | InvStG | 18 Abs. 1 read with 2 Abs. 10, 2 Abs. 11 and 16 Abs. 1 Nr. 1 -- **two branches, decided by the 39 AO attribution** | KAP-INV Z4-8 and Z9-13 (branch A) / neither (branch B) | invstg-18-vorabpauschale.md [GT-INVSTG-059]. No source addresses a Kompensationszahlung on Investmentanteile; both branches are subsumptions, and which applies is a fact about the loan |
| Third-party payment connected with a capital investment | EStG | 20 Abs. 3 S. 1 (*neben* / *an deren Stelle*) and S. 2; BMF 14.05.2025 Rn. 83, 84 -- combined with the Nummer of Abs. 1 it relates to, Nr. 3 for fund units, **with the Teilfreistellung applied** | KAP / KAP-INV per the Nummer | estg-20-kapitalvermoegen.md [GT-ESTG20-010], [GT-ESTG20-048] |
| Wertpapierdarlehen fee received by a private lender | -- | **unresolved**; 20 Abs. 3 / 20 Abs. 1 Nr. 7 / 22 Nr. 3, in that order of enquiry | KAP Z19 or Anlage SO | estg-20-kapitalvermoegen.md [GT-ESTG20-049], open-legal-questions.md **Q14** |
| Whether a Wertpapierdarlehen realises a disposal for a private lender | -- | **no located Tier 1/2 source**; BMF 09.07.2021 Rz. 11 says no Gewinnrealisierung but says it in Buchwert terms, and BMF 14.05.2025 Rn. 170's fiction is 43 Abs. 1 S. 4 (Steuerabzug) | -- | bmf-guidance/wertpapierdarlehen-zurechnung.md [GT-ESTG20-046] -- recorded as a gap, not as a rule |
| Vorabpauschale | InvStG | 18 Abs. 1; pro-rata 18 Abs. 2; Zufluss 18 Abs. 3; Basiszins 18 Abs. 4; BMF 21.05.2019 Rz. 18.3, 18.4, 18.6, 18.7, 18.8, 18.9, 18.11, 18.12, 18.14 | KAP-INV Z9-13 (for calendar year VZ-1) | invstg-18-vorabpauschale.md |
| Vorabpauschale, what the Abs. 2 twelfths multiply | InvStG | 18 Abs. 2 read with 18 Abs. 1 S. 1; BMF 21.05.2019 Rz. 18.3 (0,50 € is the capped Basisertrag *after* the 0,10 € Ausschuettung), continued by Rz. 18.11 | (scales KAP-INV Z9-13) | invstg-18-vorabpauschale.md [GT-INVSTG-056] -- the twelfths multiply `Basisertrag - Ausschuettungen`, not the Basisertrag |
| Vorabpauschale, units disposed of in the year | InvStG | BMF 21.05.2019 Rz. 18.4 (count at the close of 31 December); Rz. 20.4 for a merely deemed disposal | (scales KAP-INV Z9-13) | invstg-18-vorabpauschale.md [GT-INVSTG-016] -- settled 2026-08-07, formerly Q5 |
| Vorabpauschale, holding acquired in several instalments | InvStG | 18 Abs. 2; BMF 21.05.2019 Rz. 18.11 (reduction applied per Anteil), Rz. 18.9; BMF 14.05.2025 Rn. 184a | (scales KAP-INV Z9-13) | invstg-18-vorabpauschale.md [GT-INVSTG-011] -- settled 2026-08-07, formerly Q13; the per-instalment summation is a construction from two quoted rules |
| Vorabpauschale in a Teilfreistellungssatzwechsel year | InvStG | BMF 21.05.2019 Rz. 20.4, as amended 29.04.2021 | (scales KAP-INV Z9-13) | invstg-22-teilfreistellungssatz-aenderung.md [GT-INVSTG-054] |
| Day that fixes Anschaffung and Veraeusserung | EStG | BMF 14.05.2025 Rn. 85 (disposal), Rn. 317 (Erwerb) -- the obligatorisches Rechtsgeschaeft, not settlement | (decides the VZ, the FX rate, and the Abs. 2 month) | abgeltungsteuer-einzelfragen.md [GT-ESTG20-039], [GT-ESTG20-040] |
| Acquisition data of fund units, and a fund merger | EStG | BMF 14.05.2025 Rn. 184a -- per Anschaffungszeitpunkt; a steuerneutrale Fondsverschmelzung restates the count only | (feeds 18 Abs. 2 and 19 Abs. 1) | abgeltungsteuer-einzelfragen.md [GT-ESTG20-041] |
| Fund sale gain/loss | InvStG | 19 Abs. 1 S. 1-2 | KAP-INV Z14-26 | invstg-19-veraeusserungsgewinne.md |
| VP deduction on sale | InvStG | 19 Abs. 1 S. 3-4 | KAP-INV **Z53** (not Z55) | invstg-19-veraeusserungsgewinne.md |
| FX gain (explicit conversion) | EStG | 20 Abs. 2 S. 1 Nr. 7 i.V.m. S. 2 (verzinslich) / 23 Abs. 1 S. 1 Nr. 2 (unverzinslich) | KAP Z19/22 or SO | fremdwaehrung-konten.md |
| FX gain (currency leg of a securities trade) | -- | **unresolved**; Rz. 131 does *not* address it | KAP Z19/22 | fremdwaehrung-konten.md [GT-FX-007], open-legal-questions.md Q9 instance (a) |
| FX gain (currency consumed to settle a cash-flow item) | -- | **unresolved**; Rz. 131 names Veraeusserung and Rueckzahlung, not a payment out of the balance | KAP Z19/22 | fremdwaehrung-konten.md [GT-FX-001], open-legal-questions.md Q9 instance (b) |
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
| Separate derivative lines (a *form* question, independent of the repeal above) | Z21 gains, Z24 losses -- in use | Not used; derivative gains net into Z19, losses into Z22. Nothing is entered on them; whether the numbers are still printed is a form-layout point that decides no figure, noted in anlage-kap-zeilen.md [GT-FORM-005] | anlage-kap-zeilen.md |
| SO Freigrenze | EUR 1,000 from VZ 2024 (Wachstumschancengesetz v. 27.03.2024, BGBl. 2024 I Nr. 108); EUR 600 before | EUR 1,000 | estg-23-private-veraeusserung.md |
| Basiszins (for the VP *of* that calendar year, declared the following VZ) | 2.29% (2024), 2.53% (2025) | 3.20% (2026) | basiszins-vorabpauschale.md |

## Open questions and pending developments

Both now live in [open-legal-questions.md](open-legal-questions.md), which states each question's
two readings and the authority behind each. Which reading was adopted is recorded separately, in
`docs/legal-implementation-map.md` -- Validation Protocol item 7.
