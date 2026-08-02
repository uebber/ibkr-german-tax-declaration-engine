# EStG 36 / 45a -- Anrechnung inlaendischer Kapitalertragsteuer (KESt)

## Scope

German **inlaendische Kapitalertragsteuer** (KESt) plus Solidaritaetszuschlag withheld on
**German-issuer dividends** even when the shares are held through a **foreign broker**.

This is NOT `auslaendische Quellensteuer`. It is German tax, prepaid. It belongs on
different Anlage KAP lines and follows a different credit mechanism. Conflating the two
is the failure mode this file exists to prevent.

## Source

- **Primary (Tier 1):**
  [gesetze-im-internet.de -- 36 EStG](https://www.gesetze-im-internet.de/estg/__36.html),
  [45a EStG](https://www.gesetze-im-internet.de/estg/__45a.html),
  [44 EStG](https://www.gesetze-im-internet.de/estg/__44.html)
- **Administrative (Tier 2):** BMF-Schreiben vom **16.05.2025**, *"Kapitalertragsteuer:
  Ausstellung von Steuerbescheinigungen nach § 45a Absatz 2 und 3 EStG"*,
  **GZ IV C 1 - S 2401/00008/014/051** (50 pages). Replaces BMF 23.05.2022 (BStBl I S. 860),
  19.09.2023 (BStBl I S. 1673) and 13.02.2024 (BStBl I 2024 S. 223).
  Referenced therein: BMF 16.09.2013 (BStBl I S. 1168) on auslaendische Zwischenverwahrung.
- **Form (Tier 3):** `reference/Anltg_KAP_24.md`, `reference/Anltg_KAP_25.md`
- Verified 2026-08-02. Statutory text quoted with original umlauts.

---

## 1. The withholding happens upstream, not at the broker

A foreign broker cannot be required to withhold German KESt -- only an **inlaendisches**
institution can be an auszahlende Stelle (44 Abs. 1 Satz 4 Nr. 1 lit. a EStG; lit. bb
expressly carves out payment to an *auslaendisches* institute).

But for **German** dividends the deduction occurs one level up the custody chain.
BMF 16.05.2025 (section on Zahlstellensteuerprinzip, 43 Abs. 1 Satz 1 Nr. 1a):

> *"Fuehrt ein inlaendisches Kreditinstitut ein Wertpapierdepot, das auf den Namen eines
> auslaendischen Kreditinstituts lautet, liegt fuer Ertraege im Sinne des § 43 Absatz 1
> Satz 1 Nummer 1a und Nummer 2 Satz 4 EStG regelmaessig ein Fall des § 44 Absatz 1 Satz 4
> Nummer 3 EStG vor. Das depotfuehrende inlaendische Kreditinstitut ist zum Einbehalt von
> Kapitalertragsteuer in seiner Funktion als auszahlende Stelle im Sinne des § 44 Absatz 1
> Satz 3 EStG verpflichtet."*

**Consequence:** holding German shares at a foreign broker does not avoid German KESt. The
investor receives the dividend net of 25% KESt + 5.5% SolZ = **26.375%**, and must declare
the **gross** dividend.

**Detection rule (engine-relevant):** a withholding entry at exactly 26.375% of the gross
dividend on a German-issuer security is German KESt+SolZ, not foreign WHT.

---

## 2. Form placement -- verified against the official Anleitung, 2024 AND 2025

Both years carry identical wording.

| Line | Content | Source |
|------|---------|--------|
| Zeile 7-15 | Kapitalertraege **die dem inlaendischen Steuerabzug unterlegen haben** -- taken from *"der Steuerbescheinigung der inlaendischen auszahlenden Stelle (z. B. Kreditinstitut)"* | Anltg_KAP_24 / _25 |
| **Zeile 37** | *"Die von den Ertraegen der Zeilen 7 bis 11 einbehaltene Kapitalertragsteuer"* | Anltg_KAP_24 / _25 |
| **Zeile 38** | einbehaltener Solidaritaetszuschlag | idem |
| **Zeile 39** | einbehaltene Kirchensteuer | idem |
| Zeile 40 | *bereits durch das Kreditinstitut angerechnete* **auslaendische** Steuer | idem |
| Zeile 41 | *noch nicht angerechnete* **auslaendische** Steuer | idem |
| Zeile 42 | fiktive Quellensteuer | idem |

The BMF Steuerbescheinigung template itself annotates its income field with
*"Hoehe der Kapitalertraege ... Zeile 7 Anlage KAP"*, confirming the Zeile 7 -> Zeile 37 pairing.

**Zeilen 40/41 are for auslaendische Steuern only.** German KESt entered there is on the
wrong line and claims the wrong credit mechanism.

Note the interaction with Zeile 18/19: those are for income that has **NOT** been subject to
inlaendischer Steuerabzug. A German dividend that suffered KESt upstream belongs in
**Zeile 7**, not Zeile 19 -- unlike every other income type in this engine's inputs.
See `reference/research/inlaendisch-auslaendisch-relevance.md`, which resolves the Z18/Z19
question by intermediary but does not cover the certified-withholding case.

---

## 3. Credit requires a Steuerbescheinigung -- statutory bar

**36 Abs. 2 Satz 1 Nr. 2 EStG** credits *"die durch Steuerabzug erhobene Einkommensteuer"*
to the extent it falls on *"die bei der Veranlagung erfassten Einkuenfte"*, provided
*"keine Erstattung beantragt oder durchgefuehrt worden ist"*.

**36 Abs. 2 Satz 2 EStG** is the hard gate:

> *"... wird nicht angerechnet, wenn die in § 45a Absatz 2 oder Absatz 3 bezeichnete
> Bescheinigung nicht vorgelegt worden ist"* (or the 45a Abs. 2a data were not transmitted).

**Satz 3** relaxes only the *timing* for applications under 32d Abs. 4 or Abs. 6 --
production *auf Verlangen des Finanzamts* suffices there. It does not dispense with the
certificate's existence.

Under **45a Abs. 2 Satz 1**, for 43 Abs. 1 Satz 1 Nr. 1a the issuer is *die auszahlende
Stelle*; Abs. 3 shifts the duty to the **inlaendisches** Kreditinstitut in the relevant
constellations. A foreign broker is not an eligible issuer.

---

## 4. The certificate IS obtainable -- BMF 16.05.2025

This is the part that resolves the apparent deadlock, and it is **settled administrative
guidance, not interpretation**:

> *"Bei im Inland endverwahrten Bestaenden, soweit keine Sammel-Steuerbescheinigung
> beantragt wurde, sowie **bei im Ausland endverwahrten Bestaenden** ist fuer die bei
> inlaendischen Kreditinstituten verwahrten Wertpapierbestaende auslaendischer
> Kreditinstitute bis zur Hoehe der auf die Kapitalertraege abgefuehrten Kapitalertragsteuer
> **auf Antrag des auslaendischen Kreditinstitutes in Vertretung des Anteilseigners eine
> Einzelsteuerbescheinigung durch das inlaendische Kreditinstitut auszustellen.**"*

Two routes:
1. **Einzelsteuerbescheinigung** -- the foreign broker applies *in representation of the
   shareholder* to the German custodian, which must then issue it in the shareholder's name.
   The certificate must show which foreign institution received the credit.
2. **Sammel-Steuerbescheinigung** -- for auslaendische Zwischenverwahrung, issuable by the
   inlaendisches Kreditinstitut acting as *letzte inlaendische Stelle* under 44 Abs. 1 Satz 4
   Nr. 3 EStG, per BMF 16.09.2013 (BStBl I S. 1168).

The taxpayer must initiate this via the broker; it is not automatic. Fees may apply.

---

## 5. 36a EStG (Cum/Cum) -- generally not binding for retail

36a can disallow **3/5** of the KESt credit where the Mindesthaltedauer / Mindestwert-
aenderungsrisiko conditions are unmet (Anlage KAP Zeile 46). **36a Abs. 5 Nr. 1** provides a
**EUR 20,000** Bagatellgrenze; below it the full credit stands. Retail dividend volumes in
this engine's typical scope are far below that threshold.

---

## 6. Engine status -- KNOWN DEFECT (not yet fixed)

`src/engine/loss_offsetting.py` sums **every** `WithholdingTaxEvent` into
`ANLAGE_KAP_FOREIGN_TAX_PAID` (Zeile 41) with **no country filter**, and the engine has no
representation of Zeile 7 / 37 / 38 / 39 at all.

Observed in real data (German issuers held at IBKR Ireland): Aurubis, BASF and BMW dividends
carry `Withholding Tax` rows described `... - DE TAX`. The 2024 BMW row is
EUR 317.56 on EUR 1,204.00 gross = **exactly 26.375%**, i.e. 25% KESt + 5.5% SolZ.

Effect: German KESt is declared as anrechenbare **auslaendische** Steuer in Zeile 41.

Required to fix:
1. Classify `WithholdingTaxEvent` by issuer country / German-KESt signature rather than
   treating all withholding as foreign.
2. Add Zeile 7 (certified gross income), Zeile 37 (KESt), Zeile 38 (SolZ), Zeile 39 (KiSt).
3. Surface the Steuerbescheinigung requirement to the user -- without it the credit is
   barred by 36 Abs. 2 Satz 2, so the report should tell them to request one via the broker.

---

## Open questions (NOT settled -- do not treat as fact)

- Whether IBKR in practice obtains Einzelsteuerbescheinigungen on client request. This is a
  **factual question about the broker**, unanswerable from Tier 1/2 sources, and must be
  established from IBKR documentation or by asking them.
- Whether a German Finanzamt accepts a broker statement in lieu of a 45a certificate. The
  statutory wording says no; no BFH decision on the retail Auslandsdepot constellation was
  located (the cases found concern Cum/Ex and Cum/Cum).
- From 01.01.2027, 45b / 45c EStG reporting duties (AbzStEntModG) change certificate
  issuance for German dividends. Out of scope for VZ <= 2026; revisit before VZ 2027.
