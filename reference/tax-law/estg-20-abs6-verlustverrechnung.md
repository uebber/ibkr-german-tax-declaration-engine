# EStG 20 Abs. 6 -- Verlustverrechnung bei Kapitalvermoegen

## Source

- **Primary:** [gesetze-im-internet.de -- 20 EStG](https://www.gesetze-im-internet.de/estg/__20.html)
- **Amendment history:** [buzer.de -- 20 EStG Versionen](https://www.buzer.de/gesetz/4499/v62240.htm)
- **Key amendment:** Jahressteuergesetz 2024 (BGBl. I 2024 Nr. 387), effective retroactively for all open cases

## Relevance to Engine

Loss offsetting rules determine how the engine aggregates gains and losses into the correct tax form lines (Zeilen 19-24 of Anlage KAP). The rules changed significantly between 2024 and 2025.

---

## Current Rules (as of JStG 2024)

### Satz 1 -- No cross-income offsetting
Losses from capital income (Kapitalvermoegen) may NOT be offset against income from other income types. They also may NOT be deducted under 10d EStG (general loss carryforward).

### Satz 2 -- Intra-category carryforward
Capital losses reduce capital income in subsequent assessment periods (Veranlagungszeitraeume).

### Satz 3 -- Spousal pooling
For jointly assessed spouses (Zusammenveranlagung), joint loss offsetting occurs before loss determination (Verlustfeststellung).

### Satz 4 -- Stock loss ring-fencing (STILL IN FORCE)
**Losses from the sale of shares (Aktien) may ONLY be offset against gains from the sale of shares.**

This creates a separate loss pool (Aktienverlusttopf). Carryforward applies under Satz 2 analogously.

- Verfassungsmaessigkeit pending at BVerfG: **Az. 2 BvL 3/21** (referred by BFH, Beschluss vom 17.11.2020, VIII R 11/18)
- BFH considered the restriction likely unconstitutional

**Engine mapping:** `ANLAGE_KAP_AKTIEN_VERLUST` (Zeile 23) kept separate from other losses

### Satz 5 a.F. -- Derivative loss cap (ABOLISHED)
**Former rule (VZ 2021-2024):** Losses from Termingeschaefte could only be offset up to EUR 20,000 per year against gains from Termingeschaefte and Stillhalterpraemien.

**Abolished by:** JStG 2024, Art. 1 Nr. 10 (BGBl. I 2024 Nr. 387, 02.12.2024)
- Retroactive application to all open cases (52 Abs. 28 EStG n.F.)
- Existing loss carryforwards from Termingeschaefte are fully usable
- BFH had signaled unconstitutionality: Beschluss vom 07.06.2024, VIII B 113/23

**Source:** [Bayerisches Landesamt fuer Steuern -- Verlustverrechnungsbeschraenkungen](https://www.lfst.bayern.de/aktuelles/gesetzliche-aenderungen/details?tx_news_pi1%5Baction%5D=detail&tx_news_pi1%5Bcontroller%5D=News&tx_news_pi1%5Bnews%5D=321&cHash=938da14ac42f3754b4f9dc47963cbab2)

### Satz 6 a.F. -- Worthless securities cap (ABOLISHED)
**Former rule:** Losses from total loss (Ausfall/Ausbuchung) of Wirtschaftsguetern capped at EUR 20,000 per year.

**Also abolished** by JStG 2024, same retroactive scope.

---

## Year-Specific Engine Behavior

### Tax Year <= 2024 (form_rules: separate_derivative_lines = True)

| Form Line | Content |
|-----------|---------|
| Zeile 19 | Stock gains - stock losses + other income - other losses + derivative gains |
| Zeile 20 | Stock gains (gross, for Aktienverlusttopf) |
| Zeile 21 | Derivative gains (Termingeschaefte, gross) |
| Zeile 22 | Other (non-stock, non-derivative) losses |
| Zeile 23 | Stock losses (absolute value) |
| Zeile 24 | Derivative losses (absolute value) |

Note: Zeile 21/24 existed for tracking even after abolition of the cap -- the form structure for 2024 still includes these lines.

### Tax Year >= 2025 (form_rules: separate_derivative_lines = False)

| Form Line | Content |
|-----------|---------|
| Zeile 19 | Stock gains - stock losses + other income - other losses + derivative gains - derivative losses |
| Zeile 20 | Stock gains (gross) |
| Zeile 21 | 0.00 (line removed from form) |
| Zeile 22 | All non-stock losses including derivative losses |
| Zeile 23 | Stock losses (absolute value) |
| Zeile 24 | 0.00 (line removed from form) |

**Engine implementation:** `src/reporting/form_rules.py` -- `FormYearRules` dataclass with `get_form_rules(tax_year)`

---

## Loss Offsetting Hierarchy

```
Capital Income
  |
  +-- Aktienverlusttopf (Stock losses <-> Stock gains only)
  |     EStG 20 Abs. 6 Satz 4
  |
  +-- Allgemeiner Verlustverrechnungskreis (all other capital income)
  |     Dividends, interest, bond gains/losses, derivative gains/losses,
  |     FX gains/losses, option premiums, fund gains (via KAP not KAP-INV)
  |
  +-- No cross-income-type offsetting (Satz 1)
```

## Open Constitutional Questions

| Case | Subject | Status |
|------|---------|--------|
| BVerfG 2 BvL 3/21 | Stock loss ring-fencing (Satz 4) | Pending |
