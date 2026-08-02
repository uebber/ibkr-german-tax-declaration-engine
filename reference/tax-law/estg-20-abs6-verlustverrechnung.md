# EStG 20 Abs. 6 -- Verlustverrechnung bei Kapitalvermoegen

## Source

- **Primary:** [gesetze-im-internet.de -- 20 EStG](https://www.gesetze-im-internet.de/estg/__20.html)
- **Primary (application rule):** [gesetze-im-internet.de -- 52 EStG](https://www.gesetze-im-internet.de/estg/__52.html), [dejure.org -- 52 EStG](https://dejure.org/gesetze/EStG/52.html)
- **Amendment history:** [buzer.de -- 20 EStG Versionen](https://www.buzer.de/gesetz/4499/v62240.htm)
- **Amendment synopsis (52 EStG, JStG 2024):** [buzer.de](https://www.buzer.de/gesetz/4499/al208581-0.htm)
- **Key amendment:** Jahressteuergesetz 2024 (BGBl. I 2024 Nr. 387), effective retroactively for all open cases -- see "The repeal and its application rule" below for the verbatim provision

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

### Satz 5 (current) -- Bescheinigung requirement

**Careful: the sentence numbering shifted.** After the JStG-2024 repeal, Abs. 6 has **five
Saetze**, and the *current* Satz 5 is the former Satz 7: losses subject to
Kapitalertragsteuer may only be offset or carried forward if a Bescheinigung within the
meaning of 43a Abs. 3 Satz 4 EStG is presented. A bare citation of "20 Abs. 6 Satz 5"
written before 02.12.2024 means the derivative cap; written after, it means this rule.
Always state the Fassung.

### Satz 5 a.F. -- Derivative loss cap (ABOLISHED)
**Former rule (VZ 2021-2024):** Losses from Termingeschaefte could only be offset up to EUR 20,000 per year against gains from Termingeschaefte and Stillhalterpraemien.

### Satz 6 a.F. -- Worthless securities cap (ABOLISHED)
**Former rule (VZ 2020 onwards):** Losses from total loss (Ausfall/Ausbuchung) of Wirtschaftsguetern capped at EUR 20,000 per year.

### The repeal and its application rule (Tier 1, verbatim)

Both caps were struck by **JStG 2024, Art. 1 Nr. 10 (BGBl. I 2024 Nr. 387, 02.12.2024)**;
Abs. 6 Satz 5 und 6 a.F. *"werden aufgehoben"*. The scope of the repeal is decided not by
20 Abs. 6 itself but by the application rule in **52 Abs. 28 EStG**, which the same
Article amended. Absatz 28 has 26 Saetze; the last two are the ones that matter:

- **52 Abs. 28 Satz 25 EStG n.F.** -- *"[20 Absatz 6 Satz 5 in der Fassung des Gesetzes
  vom 21. Dezember 2020 (BGBl. I S. 3096)] ist auf alle offenen Faelle nicht mehr
  anzuwenden."*
- **52 Abs. 28 Satz 26 EStG n.F.** -- identical wording for **20 Absatz 6 Satz 6**.

> Verified 2026-08-02 against Tier 1 sources. Wording and sentence positions (Satz 25 =
> Termingeschaefte, Satz 26 = Forderungsausfaelle, 26 Saetze in Abs. 28) taken from
> dejure.org/gesetze/EStG/52.html; the *change* is read off the buzer.de synopsis of the
> JStG-2024 amendment, which shows the operative clause replaced in both sentences:
> Satz 25 *"ist auf Verluste anzuwenden, die nach dem 31. Dezember 2020 entstehen"* ->
> *"ist auf alle offenen Faelle nicht mehr anzuwenden"*; Satz 26 the same with
> "31. Dezember 2019". The repeal in 20 Abs. 6 was confirmed against the official
> gesetze-im-internet.de text, which now shows **five** Saetze in Abs. 6 with **no** EUR
> 20,000 restriction of either kind. Umlauts transliterated per this library's convention.

**What "alle offenen Faelle" means for this engine:** the legislature did not set a first
year of application -- it ordered the old provisions *not to be applied* to any case still
open. A return being prepared now for VZ 2021, 2022, 2023 or 2024 is such a case. There is
therefore **no assessment year in which this engine should apply the EUR 20,000 cap.**

**Not the same question as the form structure.** The repeal removes the *offsetting
restriction*; it does not restructure the *forms* that were already published. Anlage KAP
for VZ <= 2024 still has its separate Termingeschaefte lines, and figures still belong on
them. See "Year-Specific Engine Behavior" below: `derivative_loss_cap_applies` is False for
every year, `separate_derivative_lines` remains year-specific.

Constitutional background (Tier 4, context only -- the repeal is what binds):
BFH, Beschluss vom 07.06.2024, VIII B 113/23 (AdV), signalled serious doubts about the
Termingeschaeft restriction. Existing Termingeschaeft loss carryforwards are fully usable.

Secondary summary consulted, not relied on: [Bayerisches Landesamt fuer Steuern --
Verlustverrechnungsbeschraenkungen](https://www.lfst.bayern.de/aktuelles/gesetzliche-aenderungen/details?tx_news_pi1%5Baction%5D=detail&tx_news_pi1%5Bcontroller%5D=News&tx_news_pi1%5Bnews%5D=321&cHash=938da14ac42f3754b4f9dc47963cbab2)

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

**Engine implementation:** `src/tax_law/registry.py` -- `FormYearRules` dataclass with
`get_form_rules(tax_year)` (`src/reporting/form_rules.py` is a re-export shim). Entries for
**2021** (covering 2021-2023 by forward carry-over) and **2024**, **2025**.
`derivative_loss_cap_applies` is **False in every entry** (52 Abs. 28 S. 25 EStG, above);
only `separate_derivative_lines`, `z19_subtracts_derivative_losses` and
`z22_includes_derivative_losses` are year-specific.

### Verification of the line numbers, per year (Validation Protocol item 4)

Each assessment year was checked against the official form or Anleitung for that year, not
inferred from a neighbouring year. Retrieved 2026-08-02.

| VZ | Z20 Aktiengewinne | Z21 Stillhalter + Termingewinne | Z22 sonstige Verluste | Z23 Aktienverluste | Z24 Terminverluste | Source checked |
|----|----|----|----|----|----|----|
| 2020 | 232/432 | **frei** | 235/435 | 236/436 | **frei** | Form 2020AnlKAP051 |
| 2021 | 232/432 | 631/831 | 235/435 | 236/436 | 635/835 | Form 2021AnlKAP051 |
| 2022 | 232/432 | 631/831 | 235/435 | 236/436 | 635/835 | Form + Anleitung zur Anlage KAP 2022 |
| 2023 | 232/432 | 631/831 | 235/435 | 236/436 | 635/835 | Form (Anlage KAP 2023) |
| 2024 | -- | Z21 | Z22 | Z23 | Z24 | `reference/Anltg_KAP_24.md` |
| 2025 | -- | removed | Z22 (incl. derivatives) | Z23 | removed | `reference/Anltg_KAP_25.md` |

Numbers in the middle columns are the official Kennzahlen printed on the form; they are
**identical across 2021-2023**, which is the strongest available identity check between
those years.

**VZ 2020 and earlier are outside this engine's form coverage.** On the 2020 form, Zeilen 21
and 24 are printed *"frei"* and the word "Termingeschäfte" does not occur anywhere in the
form. The separate Termingeschäft lines were introduced with the VZ 2021 form, together with
the (since repealed) 20 Abs. 6 Satz 5 restriction that made the split necessary. Carrying the
2021+ projection backwards would put figures on lines that do not exist, so
`get_form_rules` **raises** for a tax year before 2021 rather than falling back. Forward
carry-over (an unpublished future form inherits the latest verified structure) remains a
silent default -- a structure stays in force until a later year changes it.

Sources for the retrieved forms: official Formularstand identifiers as printed
(2020AnlKAP051, 2021AnlKAP051); PDFs mirrored at steuern.de / steuerklassen.com /
helpdesk.stotax.de (Tier 3 copies of the Bundesfinanzverwaltung forms, identified by their
Formularstand string).

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
