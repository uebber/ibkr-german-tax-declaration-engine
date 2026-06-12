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
Gains from redemption/sale of capital claims (Kapitalforderungen jeder Art). Redemption at maturity (Einlösung) is explicitly treated as a disposal (Veräußerung) per Abs. 2 Satz 2.

**Engine mapping:** Bond sales; bond maturities (IBKR corporate action `Type="BM"`, mapped to a synthetic `TRADE_SELL_LONG` so it reuses the bond FIFO/FX path); FX gains on interest-bearing accounts. Positive G/L -> Anlage KAP Zeile 19, negative -> Zeile 22.

---

## Abs. 3 -- Special Benefits
Special benefits or advantages granted in addition to or in place of income under Abs. 1 and 2.

---

## Abs. 4 -- Gain Calculation

**Gain = Sale proceeds - Transaction costs - Acquisition costs (Anschaffungskosten)**

Key principle: FIFO method applies per asset per depot unless specific identification is possible.

**Engine implementation:** `FifoManager` with lot-level tracking.

**Per-Depot FIFO.** The engine runs a **separate FIFO ledger per (custody account, asset)** — both
for securities and for foreign currency (FX) — matching §20 Abs. 4 S. 7 (FIFO per Depot). Events
carry their IBKR `ClientAccountID`; a disposal from one account consumes only that account's lots,
so a security or currency co-held in two accounts and sold from one yields the correct per-Depot
gain. Per-account SoY/EoY positions and cash balances drive the reconstruction; the aggregate
across accounts is still used for VP (per person), EoY validation, and the tax-return totals.
Events/exports without an account id collapse to a single default ledger (unchanged single-account
behaviour).

**Internal transfers (Depotübertragung).** An internal move of a security or non-EUR cash between
two of the same person's accounts is parsed from the IBKR *Transfers* export and modelled as a
tax-neutral `InternalTransferEvent` (§43 Abs. 1 S. 5 / Fußstapfentheorie): no gain is realised, and
the FIFO lots carry over unchanged — for a **long** position the acquisition date and EUR cost
basis, for a transferred **short** position the opening date and EUR sale proceeds (so the later
cover in the receiving Depot realises the correct gain). The historical (pre-tax-year) SoY
reconstruction replays each account's trades AND the inter-account transfers in a single
chronological stream, so a security bought, transferred between Depots, and (partly) sold all within
the historical window is rebuilt lot-exactly (the carried basis/date survive); current-year
transfers are applied in event order. Where the trade history predates the available files the
ledger still reconciles to the reported SoY position. **Non-EUR cash transfers are treated the same
way**: an internal move of foreign currency between the person's own accounts is not a Veräußerung
(no change of ownership), so it is tax-neutral and the moved currency keeps the sender's acquisition
date and EUR cost basis. The currency SoY reconstruction replays each account's currency-affecting
events AND the inter-account cash transfers in their own chronological stream, so the receiving
Depot's FX gain on later spending that currency is measured from the original acquisition rate — not
reset to the start-of-year rate. (EUR is the base currency and is not FIFO-tracked.)

Note on FX per-Depot: the per-account-vs-aggregated question for foreign-currency gains
(§23/§20, Fremdwährungskonten) is itself legally unsettled; the engine now tracks FX per Depot for
consistency with securities, but the aggregate result is what flows to Anlage KAP.

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
