# Foreign Currency (Fremdwaehrung) -- Tax Treatment

## Source

- **BMF-Schreiben Abgeltungsteuer (14.05.2025):** [BMF PDF](https://www.bundesfinanzministerium.de/Content/DE/Downloads/BMF_Schreiben/Steuerarten/Abgeltungsteuer/2025-05-14-einzelfragen-zur-abgeltungsteuer.pdf?__blob=publicationFile&v=2)
- **Kleeberg analysis:** [Fremdwaehrungskonten im Privatvermoegen](https://www.kleeberg.de/2025/03/17/fremdwaehrungskonten-im-privatvermoegen/)
- **Haufe commentary:** [Private Fremdwaehrungskonten: Neue steuerliche Regeln seit 2025](https://www.haufe.de/steuern/steuerwissen-tipps/private-fremdwaehrungskonten-neue-steuerliche-regeln-seit-2025_170_671044.html)
- **Flick Gocke Schaumburg:** [New Rules on Taxing Foreign Currency Gains](https://www.fgs.de/en/news-and-insights/blog/detail/new-rules-on-taxing-foreign-currency-gains-in-private-assets)
- **Legal basis:** EStG 20 Abs. 2 Satz 1 Nr. 7 (interest-bearing) / EStG 23 Abs. 1 Nr. 2 (non-interest-bearing)

## Relevance to Engine

The engine tracks FX gains/losses on foreign currency balances. The correct tax classification (20 EStG vs. 23 EStG) depends on account characteristics, which changed with the BMF paradigm shift in 2022.

---

## Classification Rules (since BMF-Schreiben 19.05.2022)

### Interest-Bearing Accounts -> EStG 20 (Abgeltungsteuer)

FX gains/losses on **interest-bearing** foreign currency accounts (Tagesgeld, Festgeld, sonstiges verzinsliches Fremdwaehrungskonto) fall under 20 Abs. 2 Satz 1 Nr. 7 EStG.

**Key implications:**
- No speculation period -- always taxable regardless of holding period
- Flat 25% Abgeltungsteuer
- Loss offsetting within capital income pool (20 Abs. 6)
- Each deposit/credit = acquisition; each withdrawal/debit = disposal
- FIFO applies to determine which "currency lot" is disposed

**Retroactive application:** Applies to all open cases from VZ 2009 onwards.

**Bank obligation (from 01.01.2025):** German banks must withhold Kapitalertragsteuer on FX gains from interest-bearing accounts.

### Non-Interest-Bearing / Payment Accounts -> EStG 23 (Spekulationsgeschaeft)

FX gains/losses on **non-interest-bearing** accounts (Girokonto, Basiskonto, payment accounts) remain under 23 Abs. 1 Nr. 2 EStG.

**Key implications:**
- 1-year speculation period applies
- Tax-free after 1 year holding
- Taxed at individual income tax rate (not Abgeltungsteuer)
- Separate loss pool (23 EStG only)

### Pure Payment Transactions -> Not taxable

FX fluctuations from Zahlungsverkehrskonten, credit cards, and digital payment instruments are generally not taxable due to lack of Einkuenfteerzielungsabsicht (intent to generate income).

---

## Engine Implementation

### IBKR Context

IBKR accounts are typically **margin accounts** that pay/charge interest on currency balances. Therefore, IBKR FX balances generally qualify as interest-bearing and fall under **20 EStG**.

### Engine FX Event Types

| Engine Realization Type | Description | Tax Category |
|------------------------|-------------|--------------|
| `FX_CONVERSION_SALE` | Explicit FX trade, selling long currency | 20 EStG |
| `FX_CONVERSION_SHORT_COVER` | Explicit FX trade, covering short currency | 20 EStG |
| `FX_IMPLICIT_SECURITY_PURCHASE` | Currency consumed to buy security | 20 EStG |
| `FX_IMPLICIT_SECURITY_SALE` | Currency received from security sale | 20 EStG |
| `FX_IMPLICIT_CASHFLOW_EXPENSE` | Currency consumed for fees/WHT | 20 EStG |
| `FX_IMPLICIT_CASHFLOW_INCOME` | Currency received from dividends/interest | 20 EStG |

All FX gains/losses are mapped to `ANLAGE_KAP_SONSTIGE_KAPITALERTRAEGE` (component of Zeile 19) or the corresponding loss category in Zeile 22.

---

## Open Questions

1. **Short currency positions:** The engine tracks short FX positions (negative balances). The BMF guidance does not explicitly address tax treatment of short FX positions in Privatvermoegen. The engine treats them analogously to long positions under 20 EStG.

2. **Implicit FX from security trades:** Whether FX gains/losses embedded in foreign security purchases/sales should be separated and taxed independently is debated. The engine follows the conservative approach of tracking them separately, consistent with BMF Rz. 131 of the Abgeltungsteuer guidance.
