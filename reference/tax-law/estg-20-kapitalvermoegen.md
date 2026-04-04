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

**Engine mapping:** Bond sales, FX gains on interest-bearing accounts

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
