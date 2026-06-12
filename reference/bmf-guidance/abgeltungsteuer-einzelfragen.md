# BMF-Schreiben: Einzelfragen zur Abgeltungsteuer

## Source

- **Current version (14.05.2025):** [BMF-Schreiben Einzelfragen Abgeltungsteuer (PDF)](https://www.bundesfinanzministerium.de/Content/DE/Downloads/BMF_Schreiben/Steuerarten/Abgeltungsteuer/2025-05-14-einzelfragen-zur-abgeltungsteuer.pdf?__blob=publicationFile&v=2)
- **EStH 2024 Anhang 19 II:** [esth.bundesfinanzministerium.de -- Anhang 19 II](https://ao.bundesfinanzministerium.de/esth/2024/C-Anhaenge/Anhang-19/II/anhang-19-II.html)
- **EStH 2025 Anhang 19 II:** [esth.bundesfinanzministerium.de -- Anhang 19 II](https://esth.bundesfinanzministerium.de/esth/2025/B-Anhaenge/Anhang-19/II/inhalt.html)

## Relevance to Engine

This is THE central administrative guidance document for capital income taxation. It contains the BMF's binding interpretation on virtually every edge case the engine handles: option treatment, corporate actions, loss offsetting, FX gains, Stueckzinsen, and more.

---

## Version History

| Date | Reference | Notes |
|------|-----------|-------|
| 22.12.2009 | BStBl I 2010, S. 94 | Original Abgeltungsteuer guidance |
| 19.05.2022 | BStBl I 2022, S. 742 | Major rewrite |
| 20.12.2022 | BStBl I 2023, S. 46 | Amendment |
| 11.07.2023 | (BMF) | Amendment |
| 14.05.2025 | (BMF) | Complete rewrite superseding 19.05.2022 version |

The 14.05.2025 version is the current authoritative document, superseding all prior versions.

---

## Key Topics Covered (relevant to engine)

### I. Kapitalvermoegen (20 EStG)

1. **Dividenden** (20 Abs. 1 Nr. 1) -- treatment of stock dividends, scrip dividends, Einlagenrueckgewaehr
2. **Zinsen** (20 Abs. 1 Nr. 7) -- includes Stueckzinsen treatment
3. **Stillhalterpraemien** (20 Abs. 1 Nr. 11) -- option premium taxation, Glattstellung as negative income
4. **Veraeusserungsgewinne** (20 Abs. 2) -- FIFO principle, partial sales
5. **Termingeschaefte** (20 Abs. 2 Nr. 3) -- derivative taxation, cash settlement, exercise
6. **Gewinnermittlung** (20 Abs. 4) -- acquisition cost determination, transaction costs
7. **Kapitalmasnahmen** (20 Abs. 4a) -- corporate action treatment (mergers, splits, spin-offs)
8. **Verlustverrechnung** (20 Abs. 6) -- loss offsetting rules including stock ring-fencing

### Specific Interpretations Relevant to Engine

#### Options
- Stillhalterpraemie taxable upon receipt (Nr. 11)
- Glattstellung: closing premium = negative income at time of payment
- Exercise (physical delivery): premium becomes cost basis component of underlying
- Expiration worthless (long): loss under 20 Abs. 2 Nr. 3
- Expiration worthless (short): no further tax consequence beyond premium already taxed
- Cash settlement: gain/loss under 20 Abs. 2 Nr. 3a

#### Corporate Actions
- Stock-for-stock merger: steuerneutral, cost basis rollover (20 Abs. 4a)
- Cash merger: taxable disposal
- Stock split: proportional cost basis adjustment, no taxable event
- Stock dividend: treatment depends on whether domestic or foreign corporation

#### Einlagenrueckgewaehr (20 Abs. 1 Nr. 1 S. 3 EStG, 27 KStG)

**Settled (statute + BMF):** a distribution from the steuerliches Einlagekonto is NOT
income; it reduces the Anschaffungskosten of the shares it was paid on. The reduction is
permanent — it must survive into later assessment years (a sale after the distribution
year realises against the REDUCED basis; losing the reduction understates the gain by
the repayment amount).

**Open legal question (excess over acquisition cost, <1% Privatvermoegen holdings):**
neither the statute nor the BMF guidance says what happens once the acquisition cost
reaches zero, and there is no BFH ruling for sub-1% holdings taxed under 20 EStG (for
17-EStG holdings >= 1% the BFH rejects negative Anschaffungskosten — excess immediately
taxable). The literature splits; the prevailing commentary view permits negative
Anschaffungskosten (full deferral to disposal, excess surfaces in the Aktiengewinn pot).

**Position taken by this engine** (legal-position register `EINLAGENRUECKGEWAEHR_EXCESS`,
disclosed on every report):
- allocation across FIFO lots is SEQUENTIAL (lot 1 reduced to zero, remainder spills
  into lot 2, ...) — a gap-filling convention; no source prescribes lot mechanics;
- only the residual exceeding ALL lots' combined basis is taxed, IMMEDIATELY, as
  sonstige Kapitalertraege (Zeile-19 pot), in the DISTRIBUTION year's assessment;
- the alternative (negative AK / deferral, h.M.) is documented in the register; it
  yields identical totals on a same-year full exit but diverges on timing, on the
  loss-offsetting pot (Z19 vs Z20 under the 20 Abs. 6 Aktien ring-fencing), and on
  partial sales.

Covered in tests/test_einlagenrueckgewaehr_excess.py (cross-year basis carry,
FIFO-sequential partial exit, immediate excess income, cross-year excess timing).

#### Foreign Withholding Tax
- Creditable under 32d Abs. 5, subject to treaty limitations
- Report on Zeile 41 Anlage KAP

---

## Applicability

This BMF-Schreiben represents the **Finanzverwaltung's binding interpretation** (Verwaltungsauffassung). While not law itself (Tier 2), tax offices are bound by it. Taxpayers can deviate but may face dispute.

For test validation purposes: this document defines the "expected behavior" of tax administration and is the best source for checking engine correctness against administrative practice.
