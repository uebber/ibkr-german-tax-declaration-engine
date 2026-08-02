# EStG 20 -- Einkuenfte aus Kapitalvermoegen

## Source

- **Primary:** [gesetze-im-internet.de -- 20 EStG](https://www.gesetze-im-internet.de/estg/__20.html)
- **With annotations:** [dejure.org -- 20 EStG](https://dejure.org/gesetze/EStG/20.html)
- **Current version:** As amended by Jahressteuergesetz 2024 (BGBl. I 2024 Nr. 387), effective 01.01.2025

## Relevance to Engine

This is the central statute for all capital income taxation. It defines what constitutes capital income (Abs. 1), capital gains (Abs. 2), gain calculation (Abs. 4), corporate action treatment (Abs. 4a), and loss offsetting (Abs. 6).

---

## Abs. 1 -- Income Types (Laufende Einkuenfte)

### Nr. 1 -- Dividends
Dividends and other distributions from corporations (Koerperschaften).

**Engine mapping:** `DIVIDEND_CASH` event -> `ANLAGE_KAP_SONSTIGE_KAPITALERTRAEGE`

### Nr. 7 -- Interest
Interest from capital claims of any kind (Kapitalforderungen jeder Art).

**Engine mapping:** `INTEREST_RECEIVED` event -> `ANLAGE_KAP_SONSTIGE_KAPITALERTRAEGE`

### Nr. 11 -- Stillhalterpraemien (Option Premiums)
Premiums received for granting options (Einraeumung von Optionen).

Key rules:
- Premium is taxable upon receipt under Abs. 1 Nr. 11
- Glattstellungsgeschaeft (closing/buy-back): paid premium is negative income at time of payment (as of JStG 2024, codified in statute effective 01.01.2024)
- Physical exercise: premium does NOT reduce under Nr. 11; instead affects cost basis of underlying trade (Abs. 2)
- Barausgleich (cash settlement) by Stillhalter: loss from Termingeschaeft under Abs. 2 Satz 1 Nr. 3a (per BFH VIII R 55/13)

**Engine mapping:** Short option events, `OPTION_EXPIRED_SHORT`, `OPTION_CASH_SETTLED_SHORT`

---

## Abs. 2 -- Capital Gains (Veraeusserungsgewinne)

### Satz 1 Nr. 1 -- Sale of shares in corporations (Aktien)
Gains from sale of shares in any corporation (Koerperschaft, Personenvereinigung, Vermoegensmasse).

**Engine mapping:** `LONG_POSITION_SALE` / `SHORT_POSITION_COVER` for STOCK category -> `ANLAGE_KAP_AKTIEN_GEWINN`

### Satz 1 Nr. 2 -- Sale of other capital claims
Gains from sale of interest-bearing instruments (Anleihen, Zertifikate, etc.).

**Engine mapping:** `LONG_POSITION_SALE` for BOND category -> `ANLAGE_KAP_SONSTIGE_KAPITALERTRAEGE`

### Satz 1 Nr. 3 -- Termingeschaefte (Derivatives)
Gains from derivatives/forward transactions.

**Sub-section 3a:** Gains from Barausgleich (cash settlement) of Termingeschaefte.

**Engine mapping:** `OPTION_TRADE_CLOSE_LONG/SHORT`, `OPTION_EXPIRED_LONG`, `OPTION_CASH_SETTLED_LONG/SHORT` -> `ANLAGE_KAP_TERMIN_GEWINN` (<=2024) or `ANLAGE_KAP_AUSLAENDISCHE_KAPITALERTRAEGE_GESAMT` (>=2025)

### Satz 1 Nr. 7 -- Gains from capital claims
Gains from redemption/sale of capital claims (Kapitalforderungen jeder Art).

Statutory text: *"der Gewinn aus der Veraeusserung von sonstigen Kapitalforderungen jeder Art im Sinne des Absatzes 1 Nummer 7"*

**Engine mapping:** Bond sales, FX gains on interest-bearing accounts

### Satz 2 -- Disposal fiction (Einloesung, Rueckzahlung, Abtretung)

**This is the provision that makes a bond redemption at maturity a taxable disposal.**

Statutory text: *"Als Veraeusserung im Sinne des Satzes 1 gilt auch die Einloesung, Rueckzahlung, Abtretung oder verdeckte Einlage in eine Kapitalgesellschaft; in den Faellen von Satz 1 Nummer 4 gilt auch die Vereinnahmung eines Auseinandersetzungsguthabens als Veraeusserung."*

> Verified 2026-08-02 against two Tier 1 sources: gesetze-im-internet.de/estg/__20.html
> and dejure.org/gesetze/EStG/20.html (wording, semicolon and word order agree).
> Version status: as amended by JStG 2024 (BGBl. I 2024 Nr. 387), effective 01.01.2025.
> Note Abs. 2 continues past Satz 2 -- Saetze 3-5 cover Personengesellschaft interests
> and the separation of Zinsschein/Zinsforderung from the Stammrecht; Satz 2 is not the
> end of the Absatz.

Satz 2 applies to **all** of Satz 1, including Nr. 7. Consequently:

| Event | Mechanism | Gain category |
|-------|-----------|---------------|
| Bond sold before maturity | Veraeusserung (Satz 1 directly) | Satz 1 Nr. 7 |
| Bond redeemed at maturity (Faelligkeit) | **Einloesung, deemed Veraeusserung by Satz 2** | Satz 1 Nr. 7 |
| Bond repaid early (Rueckzahlung) | **deemed Veraeusserung by Satz 2** | Satz 1 Nr. 7 |

Gain is computed under Abs. 4 (Veraeusserungserloes minus Veraeusserungskosten minus
Anschaffungskosten). Bonds are not Aktien, so the Abs. 6 Satz 4 ring-fencing does not apply.

**Correct citation for bond maturity is therefore `Abs. 2 Satz 1 Nr. 7 i.V.m. Satz 2`.**
Citing Satz 1 Nr. 7 alone is incomplete -- it establishes the gain category but not
that a redemption counts as a disposal at all.

#### Form placement (Tier 3 -- verified against the official Anleitung)

Verified against BOTH tax years the engine supports: Anleitung zur Anlage KAP **2024**
(`reference/Anltg_KAP_24.md`, Zeilen 18/19) and **2025** (`reference/Anltg_KAP_25.md`,
same wording at Zeile 19 and the identical "zusaetzlich" rule). The placement below is
unchanged by JStG 2024 -- that amendment removed Zeilen 21/24 (Termingeschaefte), which
bonds never used.

Anleitung zur Anlage KAP 2024, Zeilen 18/19:

- Zeile 18 takes **inlaendische** Kapitalertraege not yet subject to Steuerabzug by an
  inlaendische Zahlstelle.
- Zeile 19 takes **auslaendische** Ertraege, *"insbesondere Ertraege bei auslaendischen
  Kreditinstituten"*.
- *"Alle Veraeusserungstatbestaende tragen Sie bitte zusaetzlich in die Zeilen 20
  und / oder 22 und / oder 23 ein."*

The Z18/Z19 split turns on the **intermediary** (broker location), NOT on issuer domicile
-- see `reference/research/inlaendisch-auslaendisch-relevance.md`. Because IBKR is an Irish
broker, all income from this engine's inputs lands in Zeile 19 regardless of where the bond
issuer sits. **This mapping is conditional on that fact**; it is not a property of bond
maturities as such. A bond redeemed through a German Zahlstelle would belong in Zeile 18.

Applying the "zusaetzlich" rule: a bond maturity **gain** nets into Zeile 19 only (Zeile 20
is reserved for Aktien). A bond maturity **loss** subtracts within Zeile 19 and is
additionally entered in Zeile 22 as a positive amount (Zeile 23 is reserved for Aktien).

**Engine mapping:** IBKR corporate action `Type="BM"` -> synthetic `TRADE_SELL_LONG` ->
`RealizationType.LONG_POSITION_SALE` -> `ANLAGE_KAP_SONSTIGE_KAPITALERTRAEGE` (Zeile 19)
if positive, `ANLAGE_KAP_SONSTIGE_VERLUSTE` (Zeile 22) if negative. EUR conversion of both
legs follows the engine's general enrichment rule (ECB rate at each event date), not a
provision specific to Satz 2.

---

## Abs. 3 -- Special Benefits
Special benefits or advantages granted in addition to or in place of income under Abs. 1 and 2.

---

## Abs. 4 -- Gain Calculation

**Gain = Sale proceeds - Transaction costs - Acquisition costs (Anschaffungskosten)**

Key principle: FIFO method applies per asset per depot unless specific identification is possible.

**Engine implementation:** `FifoManager` with lot-level tracking.

### Abs. 4a -- Corporate Actions (Kapitalmasnahmen)

**Satz 1-2: Stock-for-stock mergers/exchanges**
When shares are exchanged for shares of another corporation due to corporate measures (gesellschaftsrechtliche Massnahmen), the new shares step into the tax position of the old shares. No taxable event occurs.

Conditions:
- German taxation right on gain is not excluded/restricted, OR
- EU Merger Directive (Art. 8, Richtlinie 2009/133/EG) applies

Additional cash consideration (Barzuzahlung) is taxable under Abs. 1 Nr. 1.

**Satz 5: Zuteilung without consideration (foreign corporations)**
Shares allocated by a foreign corporation without consideration: income and acquisition cost = EUR 0. Original shares' cost basis unchanged.

**Satz 7: Spin-offs (Abspaltungen)**
Asset transfer via Abspaltung: Satz 1 and 2 apply analogously.

**Satz 8: Timing**
Effective date = date of booking into the taxpayer's depot (Einbuchung in das Depot).

**Engine mapping:**
- `CORP_MERGER_STOCK` -> tax-neutral cost basis transfer (FifoManager drain/receive)
- `CORP_MERGER_CASH` -> `CASH_MERGER_PROCEEDS` realization
- `CORP_SPLIT_FORWARD` -> lot quantity/cost adjustment
- `CORP_STOCK_DIVIDEND` -> new shares with EUR 0 cost basis (if foreign)

---

## Abs. 6 -- Loss Offsetting

See dedicated file: [estg-20-abs6-verlustverrechnung.md](estg-20-abs6-verlustverrechnung.md)

---

## Abs. 8 -- Subsidiarity (Subsidiaritaet)

Capital income that belongs to income from agriculture/forestry, trade/business, self-employment, or rental is attributed to those income types instead. This engine assumes all positions are in Privatvermoegen (private assets).
