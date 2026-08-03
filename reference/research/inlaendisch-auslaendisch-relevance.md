# Inländische vs. Ausländische Einkünfte: Relevance for the Declaration

## Summary

For the standard IBKR use case (Abgeltungsteuer), the Inländisch/Ausländisch distinction is **irrelevant at every level of the declaration**. There is no form line, no loss pool, and no credit mechanism that requires separating domestic from foreign income.

---

## Level-by-Level Analysis

### 1. Form Placement (Z18 vs Z19) — Resolved, No Split Needed

The Z18/Z19 distinction is by **intermediary** (broker location), not by issuer domicile. Income
received through a foreign broker goes to Z19 whether the underlying security is German or
foreign. Z18 is for the niche case of domestic-source income that bore no Steuerabzug — a private
loan between German parties, for instance. See [GT-FORM-001].

### 2. Gain/Loss Lines (Z20–Z24) — No Domestic/Foreign Split

The form instructions explicitly state that Z20–Z24 reference "Zeilen 18 und 19" collectively. There is **no further subdivision by source country**. Stock gains from BMW and Apple are pooled together in Z20; losses pooled in Z23.

### 3. Loss Offsetting — No Domestic/Foreign Split

The Aktienverlusttopf (stock loss ring-fence) and Sonstiger Verlusttopf pool all gains/losses within each category without regard to issuer domicile. German law does not require per-country loss tracking.

### 4. Z41 (Foreign WHT Credit) — Single Aggregate, No Per-Country Limitation

This is where the §34d question is most interesting. Under the Abgeltungsteuer regime:

- [§32d Abs. 5 EStG](https://www.gesetze-im-internet.de/estg/__32d.html) provides a **direct credit** mechanism (lex specialis to §34c)
- [§34c Abs. 1 **Satz 1 zweiter Halbsatz** EStG](https://www.gesetze-im-internet.de/estg/__34c.html)
  **explicitly excludes** Abgeltungsteuer-subject capital income from the general
  Anrechnungshöchstbetrag, and Satz 3 keeps it out of the Höchstbetrag arithmetic as well
- The per-country limitation of §34c **does not apply** — instead, §32d Abs. 5 caps credit at 25% per individual capital income item
- Z41 takes a **single aggregate** amount on the form

> **Correction, 2026-08-03.** This file cited **§34c Abs. 1 Satz 4** for the carve-out. Satz 4 is
> about Betriebsausgaben on foreign income belonging to a domestic business; the carve-out is in
> Satz 1 zweiter Halbsatz, completed by Satz 3. The conclusion was right and the pinpoint was
> wrong — the failure Validation Protocol item 2 exists to catch, and the more awkward because
> `../tax-law/estg-32d-abgeltungsteuer.md` cites *this* file as the authority that corrected its
> own Abs. 4 / Abs. 6 mix-up. Verbatim text and provenance:
> [GT-CREDIT-012] in `../tax-law/estg-34d-auslaendische-einkuenfte.md`.

### 5. Anlage AUS — Not Required

Capital income under Abgeltungsteuer is systematically excluded from [Anlage AUS](https://www.steuern.de/steuererklaerung-anlage-aus). This holds even when Günstigerprüfung (§32d Abs. 6) is elected.

### 6. Günstigerprüfung — Still No Impact

Even when the taxpayer elects Günstigerprüfung under §32d Abs. 6, the WHT credit mechanism **remains §32d Abs. 5** (per §32d Abs. 6 Satz 2). The §34c per-country Anrechnungshöchstbetrag never kicks in. So even in this scenario, the domestic/foreign split is not needed.

### 7. Anlage KAP-INV — No Split (Except Immobilienfonds)

No domestic/foreign distinction for Aktienfonds, Mischfonds, or Sonstige Fonds. The only geographic split is Immobilienfonds vs. Auslands-Immobilienfonds (Z6/Z7, Z11/Z12) — which is about the fund's real property location, not relevant to typical IBKR holdings.

---

## When Would the Distinction Matter?

Only where the Abgeltungsteuer regime is displaced:

- **Teileinkünfteverfahren** (§32d Abs. 2 Nr. 3): ≥25% participation in a corporation — triggers
  tarifliche ESt, Anlage AUS, and the §34c per-country limitation. Note this is Abs. 2, which the
  §34c carve-out does **not** name: the carve-out reaches Abs. 1 and Abs. 3 bis 6 only.
- **DBA compliance audits**: The Finanzamt may request per-country supporting documentation for
  Z41 to verify DBA treaty rates. A per-country breakdown of withholding tax is what satisfies
  that request; it is evidential, not a figure on the form.

---

## Conclusion

The [§34d EStG](https://www.gesetze-im-internet.de/estg/__34d.html) classification (Schuldner domicile) is a **substantive tax law concept** that has **no expression on the declaration forms** for Abgeltungsteuer-subject income. Even Günstigerprüfung does not trigger §34c's per-country mechanism because §32d Abs. 6 Satz 2 keeps the credit under §32d Abs. 5.

**Nothing on the declaration turns on the Inländisch/Ausländisch distinction** for a portfolio
held at a foreign broker under the Abgeltungsteuer regime. A per-country withholding-tax
breakdown has evidential value if the Finanzamt asks about treaty rates, but it is not a
declared figure.

One case does turn on issuer domicile, and it is not this one: German Kapitalertragsteuer
withheld upstream on a German issuer's dividend is not auslaendische Steuer and takes a
different credit route entirely — see
[`../tax-law/estg-36-45a-kapitalertragsteuer-anrechnung.md`](../tax-law/estg-36-45a-kapitalertragsteuer-anrechnung.md),
[GT-CREDIT-025].

---

## Sources

### Primary Law

- [§32d EStG — Gesonderter Steuertarif für Einkünfte aus Kapitalvermögen](https://www.gesetze-im-internet.de/estg/__32d.html)
- [§34c EStG — Steuerermäßigung bei ausländischen Einkünften](https://www.gesetze-im-internet.de/estg/__34c.html)
- [§34d EStG — Ausländische Einkünfte](https://www.gesetze-im-internet.de/estg/__34d.html)
- [§34d EStG (dejure.org, with annotations)](https://dejure.org/gesetze/EStG/34d.html)

### Form Instructions and Guidance

- [Haufe: Einkünfte aus Kapitalvermögen — Zeilen 18–26a](https://www.haufe.de/id/beitrag/einkuenfte-aus-kapitalvermoegen-1225-zeilen-1826a-HI9285903.html)
- [Haufe: Einkünfte aus Kapitalvermögen — Zeilen 37–42 (ausländische Steuern)](https://www.haufe.de/id/beitrag/einkuenfte-aus-kapitalvermoegen-1228-zeilen-37-42-HI9285906.html)
- [Haufe: Auslandskonten/-depots](https://www.haufe.de/id/beitrag/einkuenfte-aus-kapitalvermoegen-1233-auslandskonten-depots-HI9285916.html)
- [Haufe: Anlage KAP 2024 — Zeile 19 (ausländische Kapitalerträge ohne Steuerabzug)](https://www.haufe.de/id/beitrag/14-anlage-kap-2024-fuer-einkuenfte-aus-kapitalvermoegen-1472-auslaendische-kapitalertraege-ohne-steuerabzug-HI16276376.html)
- [Haufe: Anrechenbare ausländische Quellensteuer](https://www.haufe.de/steuern/finanzverwaltung/auslaendische-kapitaleinkuenfte-versteuern_164_313500.html)
- [Haufe: Kapitalertragsteuer — Anrechnung ausländischer Steuern in der Veranlagung](https://www.haufe.de/finance/haufe-finance-office-premium/kapitalertragsteuer-103-anrechnung-auslaendischer-steuern-in-der-veranlagung_idesk_PI20354_HI9286020.html)
- [Haufe: Anrechnung weiterer ausländischer Steuern](https://www.haufe.de/id/beitrag/einkuenfte-aus-kapitalvermoegen-12425-anrechnung-weiterer-auslaendischer-steuern-HI9285927.html)
- [steuern.de: Anlage KAP Ausfüllhilfe](https://www.steuern.de/steuererklaerung-anlage-kap)
- [steuern.de: Anlage AUS Ausfüllhilfe](https://www.steuern.de/steuererklaerung-anlage-aus)
- [steuern.de: Tipps zur Anlage AUS](https://www.steuern.de/steuererklaerung-gestaltungshinweise-anlage-aus)
- [smartsteuer: Anlage KAP Ausfüllhilfe](https://www.smartsteuer.de/online/ausfuellhilfen/anlage-kap-ausfuellhilfe/)
- [smartsteuer: Ausländische Steuer — Lexikon](https://www.smartsteuer.de/online/lexikon/a/auslaendische-steuer/)
- [Finanztip: Anlage KAP](https://www.finanztip.de/steuererklaerung-anlage-kap/)
- [Finanztip: Anlage AUS](https://www.finanztip.de/steuererklaerung-anlage-aus/)

### BMF and Commentary

- [BMF: Amtliches ESt-Handbuch §34d](https://esth.bundesfinanzministerium.de/esth/2016/A-Einkommensteuergesetz/V-Steuerermaessigungen/1-Steuerermaessigung-bei-auslaendischen-Einkuenften/Paragraf-34d/inhalt.html)
- [NWB: Steuerermäßigung bei ausländischen Einkünften §34c EStG](https://datenbank.nwb.de/Dokument/113983/)
- [NWB: Anrechnungshöchstbetrag i.S.d. §34c Abs. 1 Satz 2 EStG](https://datenbank.nwb.de/Dokument/773494/)
- [NWB: §34d EStG — Ausländische Einkünfte](https://datenbank.nwb.de/Dokument/78742_34d/)
- [IWW: Vermeidung der Doppelbesteuerung durch die Anrechnungsmethode — Teil 1](https://www.iww.de/pistb/schwerpunktthema/auslaendische-einkuenfte-vermeidung-der-doppelbesteuerung-durch-die-anrechnungsmethode-teil-1-f136244)
- [steuerrecht.com: Anrechnung nach dem EStG](https://steuerrecht.com/a-anrechnung-nach-dem-estg/)
- [Steuertipps: §32d EStG](https://www.steuertipps.de/gesetze/estg/32d-gesonderter-steuertarif-fuer-einkuenfte-aus-kapitalvermoegen)

### Tax Software Help and Forums

- [lohnsteuer-kompakt: Anrechenbare ausländische Steuern (Zeile 41)](https://www.lohnsteuer-kompakt.de/feldhilfe/2024/593/2789/anrechenbare_auslaendische_steuern_zeile_41_der_anlage_kap)
- [lohnsteuer-kompakt: Zeilen 40–42 erfassen](https://www.lohnsteuer-kompakt.de/feldhilfe/2024/404/1191/zeilen_40_bis_42_erfassen_angerechnete_auslaendische_steuern)
- [ELSTER Forum: Ausländische Kapitalerträge — Wo genau eintragen?](https://forum.elster.de/anwenderforum/forum/elster-webanwendungen/mein-elster/454373-ausl%C3%A4ndische-kapitalertr%C3%A4ge-%E2%80%93-wo-genau-eintragen)
- [ELSTER Forum: Anlage KAP — Inländische und Ausländische Kapitalerträge](https://forum.elster.de/anwenderforum/forum/elster-webanwendungen/mein-elster/444660-anlage-kap-inl%C3%A4ndische-und-ausl%C3%A4ndische-kapitalertr%C3%A4ge)
- [ELSTER Forum: Anlage KAP — Anrechenbare noch nicht angerechnete ausländische Steuern](https://forum.elster.de/anwenderforum/forum/elster-webanwendungen/mein-elster/372570-anlage-kap-anrechenbare-noch-nicht-angerechnete-ausl%C3%A4ndische-steuern)

### Official Forms

- [Stotax: Anleitung zur Anlage KAP 2024 (PDF)](https://helpdesk.stotax.de/filesystem/est_2024/17_Anleitung_Anlage_KAP_2024.pdf)
- [Stotax: Anleitung zur Anlage KAP 2023 (PDF)](https://helpdesk.stotax.de/filesystem/est_2023/17_Anleitung_Anlage_KAP_2023.pdf)
- [BZST: BMF-Schreiben 23.05.2022 (PDF)](https://www.bzst.de/SharedDocs/BMF/EN/Downloads/bmf_schreiben_23_05_2022.pdf?__blob=publicationFile&v=3)

### Internal Reference Files

- [`reference/tax-law/estg-34d-auslaendische-einkuenfte.md`](../tax-law/estg-34d-auslaendische-einkuenfte.md)
- [`reference/tax-law/estg-32d-abgeltungsteuer.md`](../tax-law/estg-32d-abgeltungsteuer.md)
- [`reference/tax-forms/anlage-kap-zeilen.md`](../tax-forms/anlage-kap-zeilen.md)
