# InvStG 20 -- Teilfreistellung

## Source

- **Primary:** [gesetze-im-internet.de -- 20 InvStG](https://www.gesetze-im-internet.de/invstg_2018/__20.html)
- **Fund type definitions:** [gesetze-im-internet.de -- 2 InvStG](https://www.gesetze-im-internet.de/invstg_2018/__2.html)

## Relevance to Engine

Teilfreistellung rates determine what fraction of fund income is tax-exempt. The engine applies these rates when calculating net taxable amounts for loss offsetting.

---

## Teilfreistellung Rates (Privatvermoegen)

| Fund Type | InvStG 20 Abs. | Rate | Taxable Portion | Min. Capital Participation |
|-----------|----------------|------|-----------------|---------------------------|
| Aktienfonds | Abs. 1 Satz 1 | 30% | 70% | >= 51% (InvStG 2 Abs. 6) |
| Mischfonds | Abs. 2 | 15% | 85% | >= 25% (InvStG 2 Abs. 7) |
| Immobilienfonds | Abs. 3 Satz 1 Nr. 1 | 60% | 40% | > 50% Immobilien (InvStG 2 Abs. 9 Nr. 1) |
| Auslands-Immobilienfonds | Abs. 3 Satz 1 Nr. 2 | 80% | 20% | > 50% auslaendische Immobilien (InvStG 2 Abs. 9 Nr. 2) |
| Sonstige Fonds | (no provision) | 0% | 100% | Does not qualify for any of the above |

### Rates for Business Assets (Not used by engine, for reference)

| Fund Type | Natural Person (BV) | Corporation (KStG) |
|-----------|---------------------|---------------------|
| Aktienfonds | 60% | 80% |
| Mischfonds | 30% | 40% |
| Immobilienfonds | 60% | 60% |
| Auslands-Immobilienfonds | 80% | 80% |

---

## Fund Type Definitions (InvStG 2)

### Abs. 6 -- Aktienfonds
Investment funds that, per their investment conditions (Anlagebedingungen), invest at least **51 percent** of their active assets continuously in equity participations (Kapitalbeteiligungen).

### Abs. 7 -- Mischfonds
Investment funds that invest at least **25 percent** of their active assets continuously in equity participations.

### Abs. 8 -- Kapitalbeteiligungen
Equity participations include:
- Listed shares (boersennotierte Aktien)
- Holdings in corporations
- Certain REIT shares
- Other equity-like instruments

### Abs. 9 -- Immobilienfonds
Nr. 1: Funds investing more than **50 percent** in real estate (Immobilien) and real estate companies (Immobilien-Gesellschaften).
Nr. 2: Auslands-Immobilienfonds additionally require that the real estate/companies are predominantly foreign.

---

## Application Rules

### Abs. 4 -- Proof of Actual Quota
If the investor proves that the fund actually exceeded the required quota continuously throughout the calendar year, Teilfreistellung applies upon request (Antrag) in the assessment.

### Change of Fund Type
If the applicable Teilfreistellung rate changes or the prerequisites lapse, the investment units are **deemed sold and reacquired** on the following day (fiktive Veraeusserung). This creates a tax event.

---

## Engine Implementation

File: `src/utils/tax_utils.py`

```python
TEILFREISTELLUNG_RATES = {
    InvestmentFundType.AKTIENFONDS: Decimal("0.30"),
    InvestmentFundType.MISCHFONDS: Decimal("0.15"),
    InvestmentFundType.IMMOBILIENFONDS: Decimal("0.60"),
    InvestmentFundType.AUSLANDS_IMMOBILIENFONDS: Decimal("0.80"),
    InvestmentFundType.SONSTIGE_FONDS: Decimal("0"),
    InvestmentFundType.NONE: Decimal("0"),
}
```

Applied in loss offsetting to determine net taxable amounts from gross reported figures.
