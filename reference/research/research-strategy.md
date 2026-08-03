# Research Strategy: Tax & Legal Source Collection

## Objective

Build a curated, high-quality reference library of German tax law sources covering all taxable events and asset types supported by this engine. These references serve as ground truth for validation testing.

## Source Ranking (Tier System)

### Tier 1 -- Primary Law (highest authority)

| Source | URL | Description |
|--------|-----|-------------|
| gesetze-im-internet.de | https://www.gesetze-im-internet.de | Official federal law texts (BMJ) |
| dejure.org | https://dejure.org | Consolidated law with amendment history and court rulings |
| buzer.de | https://www.buzer.de | Law texts with version tracking across amendments |

**Use for:** Exact statutory text, paragraph/section references, effective dates of amendments.

### Tier 2 -- Official Administrative Guidance

| Source | URL | Description |
|--------|-----|-------------|
| BMF-Schreiben | https://www.bundesfinanzministerium.de | Federal Ministry of Finance circulars |
| EStH (Amtliches Einkommensteuer-Handbuch) | https://esth.bundesfinanzministerium.de | Official income tax handbook |
| Bundessteuerblatt (BStBl) | Published via BMF | Official tax gazette |
| BMF Basiszins publications | via BMF Downloads | Annual Vorabpauschale base rate notices |

**Use for:** Administrative interpretation, form line mappings, Basiszins rates, Steuerbescheinigung rules.

### Tier 3 -- Official Forms & Instructions

| Source | URL | Description |
|--------|-----|-------------|
| formulare-bfinv.de | https://www.formulare-bfinv.de | Official tax form downloads |
| ELSTER Help | https://www.elster.de/eportal/helpGlobal | Official electronic filing guidance |

**Use for:** Form structure, line numbers, filing instructions.

### Tier 4 -- Court Decisions

| Source | URL | Description |
|--------|-----|-------------|
| Bundesfinanzhof (BFH) | https://www.bundesfinanzhof.de | Federal Fiscal Court decisions |
| Bundesverfassungsgericht (BVerfG) | https://www.bundesverfassungsgericht.de | Constitutional Court (pending: 2 BvL 3/21) |

**Use for:** Authoritative interpretation, constitutional challenges, binding precedent.
**Never as sole source.** A decision interprets a provision — cite the provision too, and check
whether a later decision or a BMF-Schreiben has overtaken it.

### Tier 5 -- Professional Commentary (use for interpretation only)

| Source | URL | Description |
|--------|-----|-------------|
| Haufe Finance | https://www.haufe.de | Tax professional commentary |
| NWB Datenbank | https://datenbank.nwb.de | Tax professional database |
| Kleeberg | https://www.kleeberg.de | Tax advisory firm publications |

**Use for:** Cross-checking interpretations, identifying edge cases. Never as sole source.

## Validation Protocol

Every item below exists because its absence let a wrong figure, or a wrong justification for a
right figure, into this engine.

1. **Every claim** traces back to at least a Tier 1 or Tier 2 source. Tier 3 fixes form
   structure; Tier 4 and Tier 5 may support an interpretation but **never stand alone**.
2. **Cite to the sentence, not the section** — every citation, not only rates and thresholds.
   `§ 108 AO` is true of the anniversary rule *and* pulls in `§ 108 Abs. 3 AO`, which is not
   implemented here. **The unstated Absatz is where the unimplemented rule hides.** Having named
   the sentence, state what else the cited unit contains. Whether it is implemented is recorded
   in `docs/legal-implementation-map.md`, against the claim ID — not in this library.
3. **Year-specific rules** name the exact amendment law (e.g. JStG 2024, BGBl. I Nr. 387) and,
   where the amendment says so, the fact that it applies to *all open cases* rather than from a
   given year. A repeal with no first year of application is not the same as a rule that starts
   in a particular year, and the two are easy to conflate.
4. **Form line mappings** are verified against the official form **for that specific tax year**.
   Never project a mapping onto an earlier year that has not been checked: a line that exists
   today may be printed *frei* on an older form. Forward carry-over is sound — a form structure
   holds until a later year changes it — backward projection is not, and the engine should refuse
   years below the earliest verified one.
5. **Each value carries its own provenance.** For a table of rates or thresholds, every row cites
   the individual document it was read off, with date and identifier. **Agreement between copies
   is not verification.** Two rows of a Basiszins table were silently inherited from a different
   statute and survived because three copies of the numbers agreed with one another; a chain of
   annual notices that each name their predecessor is what actually authenticates such a series.
6. **State the applicable tax years** and the regime floor. A provision that did not exist before
   a given year must say so, or the engine will compute a figure for a year in which the concept
   had not been introduced.
7. **Record open questions as open.** Where Tier 1 and Tier 2 do not settle a point that has to be
   answered either way, write **both readings and the authority behind each** into
   `open-legal-questions.md`. Which reading was chosen, and why, is recorded against the same
   claim ID in `docs/legal-implementation-map.md` — this library states what the law is and is
   not settled on, not what was decided about it. An unresolved question recorded is ground
   truth; an unresolved question silently resolved is not.
8. **On correcting a reference, check what cited the old reading.** Grep the code, the tests and
   the docs. A reference that changes while the code keeps its former justification leaves the two
   in conflict, which is the state this rule exists to prevent.
9. **State law, and only law.** No file here names a module, class, field, function, test, CSV
   column or data file, carries a code block, or describes what the engine does. Those belong in
   `docs/legal-implementation-map.md`, keyed by claim ID. Two failures made this a rule rather
   than a preference. A pointer to a field named in an *"Engine Mapping"* table survived long
   after the field was gone, so the store asserted as ground truth something that had never been
   true. And the Teilfreistellung rates were stated once in an authority table and again as code
   literals in the same file, with nothing binding the two — the duplication item 5 forbids,
   reintroduced by the code copy. Enforced by `tests/test_reference_purity.py`.

## Scope: Supported Taxable Events & Asset Types

### Asset Types
- Stocks (Aktien) -- EStG 20
- Bonds (Anleihen) -- EStG 20
- Investment Funds (Investmentfonds) -- InvStG 2018
- Options/Derivatives (Termingeschaefte) -- EStG 20
- CFDs -- EStG 20
- Private Sale Assets (Gold ETCs, Crypto ETPs) -- EStG 23
- Foreign Currency (Fremdwaehrung) -- EStG 20 / EStG 23

### Taxable Events
- Sale of securities (long/short) -- EStG 20 Abs. 2
- Dividends -- EStG 20 Abs. 1 Nr. 1
- Interest -- EStG 20 Abs. 1 Nr. 7
- Fund distributions -- InvStG 16
- Vorabpauschale -- InvStG 18
- Fund sale gains/losses -- InvStG 19 + 20
- Option premiums (Stillhalterpraemien) -- EStG 20 Abs. 1 Nr. 11
- Option expiration/exercise/assignment -- EStG 20 Abs. 2
- Cash settlement (index options) -- EStG 20 Abs. 2
- Corporate actions (merger, split, stock dividend) -- EStG 20 Abs. 4a
- Foreign withholding tax -- EStG 32d Abs. 5, 34c
- Currency gains/losses -- EStG 20 Abs. 2 / EStG 23
- Private sales within speculation period -- EStG 23 Abs. 1 Nr. 2

### Loss Offsetting Rules
- General capital loss offsetting -- EStG 20 Abs. 6
- Stock loss ring-fencing -- EStG 20 Abs. 6 Satz 4
- Derivative loss restriction (repealed for all open cases by JStG 2024; see
  `estg-20-abs6-verlustverrechnung.md` -- not "from 2025", and the separate form lines outlive
  the restriction) -- EStG 20 Abs. 6 Satz 5 a.F.
- Private sale loss rules -- EStG 23 Abs. 3 Satz 7-8

## Directory Structure

```
reference/
  Anltg_KAP_{24,25}.md      # Official form instructions (OCR), with source PDFs
  Anltg_KAP_INV_{24,25}.md
  INDEX.md                  # Library directory
  tax-law/                  # Primary statute texts and analysis
    estg-20-kapitalvermoegen.md
    estg-20-abs6-verlustverrechnung.md
    estg-23-private-veraeusserung.md
    estg-32d-abgeltungsteuer.md
    estg-34d-auslaendische-einkuenfte.md
    estg-36-45a-kapitalertragsteuer-anrechnung.md
  investment-tax-law/       # InvStG-specific references
    invstg-16-investmentertraege.md
    invstg-18-vorabpauschale.md
    invstg-19-veraeusserungsgewinne.md
    invstg-20-teilfreistellung.md
    invstg-22-teilfreistellungssatz-aenderung.md
  tax-forms/                # Form line mappings by year
    anlage-kap-zeilen.md
    anlage-kap-inv-zeilen.md
    anlage-so-zeilen.md
  bmf-guidance/             # Administrative circulars
    abgeltungsteuer-einzelfragen.md
    basiszins-vorabpauschale.md
    fremdwaehrung-konten.md
  research/                 # Meta-documentation
    research-strategy.md    # This file
    coverage-matrix.md      # Event/asset vs. source mapping
    open-legal-questions.md # Points no Tier 1/2 source settles: both readings, both authorities
    inlaendisch-auslaendisch-relevance.md
```

Outside the library, and deliberately so: `docs/legal-implementation-map.md` records what the
engine does about each claim ID and which tests guard it. Nothing in `reference/` may state that.

## Extending the Library (required procedure)

The `reference/` library is the only admissible source of legal requirements for the engine. Application code and tests may not encode a legal rule that is not written here first. When a needed rule is missing, stale, or ambiguous, extend the library before touching code:

1. **State the question** precisely: the event/asset, the tax year, and the figure or form line it affects.
2. **Locate sources** using the tier table above. Prefer Tier 1 (statute) and Tier 2 (BMF/EStH). Tier 4/5 may support interpretation but never stand alone.
3. **Verify against the Validation Protocol above** — all **nine** items, not only the tier check.
4. **Write the reference file** into the matching subdirectory of the structure above. Each file
   records: the statutory text or an accurate summary, the precise citation, the source URL and
   its tier, the retrieval date, applicable tax years, and **a stable claim ID on the heading of
   each normative requirement** (`GT-<AREA>-<NNN>`; see below). It records no implementation
   detail — Validation Protocol item 9.
5. **Update the meta-docs**: add the file to `reference/INDEX.md`, and add or amend the relevant rows in `coverage-matrix.md` (asset type, taxable event, loss offsetting, year-specific rules, as applicable).
6. **Then implement**, citing the reference file in the code comment, test docstring, or commit message.
7. **Record the position in the map.** Every claim ID gets a row in
   `docs/legal-implementation-map.md` saying what the engine does about it — implements,
   deviates, or does not reach — which module, and which tests guard it. A claim with no row is
   a claim nobody has decided about; the purity test fails on one.

### Claim IDs

`GT-<AREA>-<NNN>`, one per statutory unit that already carries a heading. Areas: `GT-ESTG20`,
`GT-ESTG23`, `GT-INVSTG`, `GT-CREDIT` (§ 32d / 34c / 34d / 36 / 45a), `GT-FORM`, `GT-FX`.

IDs exist because the map has to point at a requirement and keep pointing at it. A heading
anchor breaks the moment the heading is reworded, silently — this repo already carries one dead
anchor citation. An ID is greppable, survives rewording, and its disappearance is caught by a
test. Allocate the next free number in the area; **never reuse a retired ID**.

If a question cannot be resolved to Tier 1/2 standard, record what was found, mark the gap explicitly, and raise it with the user. Do not close the gap with general knowledge or an uncited web result.

## Retrieval notes

Hard-won and otherwise rediscovered each time. None of this changes what counts as a source —
only how to get at one.

- **BMF publishes only the two most recent Schreiben** of a recurring series. Older ones come from
  Internet Archive snapshots of the original BMF PDF, or occasionally an industry-body mirror.
- **WebFetch is blocked for `web.archive.org`.** Use `curl` and the CDX API to find and fetch a
  snapshot.
- **WebFetch cannot read PDFs.** Download and use `pdftotext -layout`, which preserves the column
  structure that form and table extraction depends on.
- **A BMF download that returns empty is often a User-Agent block, not a dead link.** The
  Einzelfragen-zur-Abgeltungsteuer circular was recorded here as unretrievable after WebFetch and a
  bare `curl` both returned nothing; `curl -L` with an ordinary browser User-Agent returned all
  137 pages on the first attempt (2026-08-03). Retry with a User-Agent before recording a
  retrieval gap — that gap had stood long enough to be described as the library's weakest point.
- **`esth.bundesfinanzministerium.de` and `ao.bundesfinanzministerium.de` are Radware-blocked** for
  both `curl` and WebFetch, and are not archived. Mirrors of the EStH exist and are usable for
  locating a passage, but the citation must still resolve to the official text.
- **`gesetze-im-internet.de` serves ISO-8859-1.** Decode explicitly or German characters corrupt.
- **A series of annual notices self-authenticates.** Each BMF letter's BEZUG line names its
  predecessor together with that predecessor's BStBl page, so every citation but the newest can be
  confirmed by a second official document. Use this rather than trusting a summary table.
- **Official forms** are retrievable per year from the form portals; the accompanying Anleitung is
  the document that states which line takes which figure.

Record the retrieval date and the URL actually used in the reference file. A source that was
reachable once and is not reachable now is still a source, provided the file says where it came
from.

## Maintenance

- Review after each Jahressteuergesetz publication
- Update form line references when new tax year forms are released
- Track pending BVerfG decisions (especially 2 BvL 3/21 on stock loss ring-fencing)
- Update Basiszins annually after BMF publication (typically January)
- When a reference is corrected, re-check every citation of it in code, tests and docs (Validation
  Protocol item 8)
- Re-check `open-legal-questions.md` after each BFH decision or BMF-Schreiben that touches a
  listed question
