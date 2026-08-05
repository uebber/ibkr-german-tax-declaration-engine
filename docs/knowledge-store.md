# The knowledge store

`reference/` is the single source of truth for every legal requirement this engine implements.
This document governs it: **how it is managed, how it may evolve, and how the code links to it.**

Nothing else may serve as a legal source. Not web search, not a linked PDF, not your own
knowledge of German tax law, not what the existing code appears to assume.

- `reference/INDEX.md` — the library's directory
- `reference/research/coverage-matrix.md` — every supported event and asset against its legal source
- `reference/research/open-legal-questions.md` — points no Tier 1/2 source settles, both readings
- `docs/legal-implementation-map.md` — what the engine does about each requirement, and which tests guard it

---

## The two rules

### The Ground Truth Rule — stated in CLAUDE.md

The rule barring legally relevant behaviour from any source outside `reference/` is stated in
CLAUDE.md, not here. It lives there because nothing enforces it, and an agent that has not read it
will not know to open this document at all.

**What it reaches**, since this is the rule that most often sends a change back: form-line
mappings, Teilfreistellung rates, loss-offsetting and ring-fencing, holding periods, thresholds,
caps, Basiszins values, withholding-tax treatment, event classification with a tax consequence,
and the expected values in any test asserting one of those.

What it delegates here is step 3: when the store does not cover a point, or covers it stalely or
ambiguously, **extend the store first** — by the procedure in *Evolving the store* below, and by
no other route. Research done in conversation and not written into `reference/` is not ground
truth.

### The Purity Rule

**`reference/` states law and contains no implementation state.** It names no module, class,
field, function, test, CSV column or data file, carries no code block, and does not describe what
the engine does.

The rule is reciprocal: CLAUDE.md states how the project is built and carries no tax content —
no form line numbers, rates, thresholds or year rules. A legal fact stated there is a defect, and
an identifier stated here is a defect.

**The reason is not tidiness.** A code pointer inside the store rots silently and becomes a false
statement in the one document you are supposed to be able to trust. Two failures made this a rule
rather than a preference:

- An *"Engine Mapping"* row asserted for months that the Vorabpauschale deduction lived in
  `RealizedGainLoss.accumulated_vorabpauschale` — a field that does not exist and never did. The
  store went on presenting it as ground truth. A legal fact cannot go stale from a refactor; an
  identifier can.
- The Teilfreistellung rates were stated once in an authority table and again as code literals in
  the same file, with nothing binding the two — the duplication Validation Protocol item 5
  forbids, reintroduced by the code copy.

Direction matters and only one direction is allowed: **code cites the store; the store never cites
code.** `tests/test_reference_purity.py` enforces this against nine patterns with a deliberately
empty allowlist. Adding to that allowlist needs a stated reason in the diff.

---

## Linking the store to the engine

The store says what the law requires. `docs/legal-implementation-map.md` says what the engine does
about it. Neither file may do the other's job.

### Claim IDs

`GT-<AREA>-<NNN>`, one per statutory unit that already carries a heading. Areas: `GT-ESTG20`,
`GT-ESTG23`, `GT-INVSTG`, `GT-CREDIT` (§ 32d / 34c / 34d / 36 / 45a), `GT-FORM`, `GT-FX`.

IDs exist because the map has to point at a requirement and keep pointing at it. A heading anchor
breaks the moment the heading is reworded, silently — this repo already carries one dead anchor
citation. An ID is greppable, survives rewording, and its disappearance is caught by a test.
Allocate the next free number in the area; **never reuse a retired ID.**

### The map

Every claim ID has exactly one row in `docs/legal-implementation-map.md`, recording the engine's
**Position** — `implements`, `deviates`, `not reached`, or `out of scope` — the module, and the
tests that would notice if the behaviour stopped.

`tests/test_reference_purity.py` asserts this in both directions: a claim with no row fails,
because that is a requirement nobody has decided about, and a row citing a claim that does not
exist fails too.

Where a claim is an open question, the map records which reading was chosen and why. Both readings
and their authorities stay in `reference/research/open-legal-questions.md`. **Choosing is an
implementation act and does not belong in the store.**

A map row is never a change of its own. It moves with the behaviour it records, or with the
`ks-maint` audit that changed the standard underneath it.

---

## Managing the store: what counts as a source

### Source ranking (tier system)

#### Tier 1 — Primary law (highest authority)

| Source | URL | Description |
|--------|-----|-------------|
| gesetze-im-internet.de | https://www.gesetze-im-internet.de | Official federal law texts (BMJ) |
| dejure.org | https://dejure.org | Consolidated law with amendment history and court rulings |
| buzer.de | https://www.buzer.de | Law texts with version tracking across amendments |

**Use for:** Exact statutory text, paragraph/section references, effective dates of amendments.

#### Tier 2 — Official administrative guidance

| Source | URL | Description |
|--------|-----|-------------|
| BMF-Schreiben | https://www.bundesfinanzministerium.de | Federal Ministry of Finance circulars |
| EStH (Amtliches Einkommensteuer-Handbuch) | https://esth.bundesfinanzministerium.de | Official income tax handbook |
| Bundessteuerblatt (BStBl) | Published via BMF | Official tax gazette |
| BMF Basiszins publications | via BMF Downloads | Annual Vorabpauschale base rate notices |

**Use for:** Administrative interpretation, form line mappings, Basiszins rates,
Steuerbescheinigung rules.

#### Tier 3 — Official forms and instructions

| Source | URL | Description |
|--------|-----|-------------|
| formulare-bfinv.de | https://www.formulare-bfinv.de | Official tax form downloads |
| ELSTER Help | https://www.elster.de/eportal/helpGlobal | Official electronic filing guidance |

**Use for:** Form structure, line numbers, filing instructions.

#### Tier 4 — Court decisions

| Source | URL | Description |
|--------|-----|-------------|
| Bundesfinanzhof (BFH) | https://www.bundesfinanzhof.de | Federal Fiscal Court decisions |
| Bundesverfassungsgericht (BVerfG) | https://www.bundesverfassungsgericht.de | Constitutional Court (pending: 2 BvL 3/21) |

**Use for:** Authoritative interpretation, constitutional challenges, binding precedent.
**Never as sole source.** A decision interprets a provision — cite the provision too, and check
whether a later decision or a BMF-Schreiben has overtaken it.

#### Tier 5 — Professional commentary (interpretation only)

| Source | URL | Description |
|--------|-----|-------------|
| Haufe Finance | https://www.haufe.de | Tax professional commentary |
| NWB Datenbank | https://datenbank.nwb.de | Tax professional database |
| Kleeberg | https://www.kleeberg.de | Tax advisory firm publications |

**Use for:** Cross-checking interpretations, identifying edge cases. Never as sole source.

### Validation Protocol

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
   claim ID in `docs/legal-implementation-map.md`. An unresolved question recorded is ground
   truth; an unresolved question silently resolved is not.
8. **On correcting a reference, check what cited the old reading.** Grep the code, the tests and
   the docs. A reference that changes while the code keeps its former justification leaves the two
   in conflict, which is the state this rule exists to prevent.
9. **State law, and only law** — the Purity Rule above, in its protocol form. Enforced by
   `tests/test_reference_purity.py`.

---

## Evolving the store

### Extending the library (required procedure)

When a needed rule is missing, stale, or ambiguous, extend the library before touching code:

1. **State the question** precisely: the event/asset, the tax year, and the figure or form line it
   affects.
2. **Locate sources** using the tier table above. Prefer Tier 1 (statute) and Tier 2 (BMF/EStH).
   Tier 4/5 may support interpretation but never stand alone.
3. **Verify against the Validation Protocol** — all **nine** items, not only the tier check.
4. **Write the reference file** into the matching subdirectory. Each file records: the statutory
   text or an accurate summary, the precise citation, the source URL and its tier, the retrieval
   date, applicable tax years, and **a stable claim ID on the heading of each normative
   requirement**. It records no implementation detail.
5. **Update the meta-docs**: add the file to `reference/INDEX.md`, and add or amend the relevant
   rows in `coverage-matrix.md`.
6. **Then implement**, citing the reference file in the code comment, test docstring, or commit
   message.
7. **Record the position in the map.** Every claim ID gets a row in
   `docs/legal-implementation-map.md`. A claim with no row is a claim nobody has decided about;
   the purity test fails on one.

If a question cannot be resolved to Tier 1/2 standard, record what was found, mark the gap
explicitly, and raise it with the user. Do not close the gap with general knowledge or an uncited
web result.

This procedure runs **inside** the `feat-func` or `fix-func` that needs the rule — store commit
first, then the code — so the order the Ground Truth Rule requires is visible in the history.

### The maintenance audit (`ks-maint`)

The procedure above is need-triggered: the engine wants a requirement it does not have. The audit
is the other direction — **the world moved and the store has not.** It is the only sanctioned
reason to change `reference/` without a code change attached.

**Triggers.** Nothing else opens one:

- a Jahressteuergesetz or other amendment is published
- a new BMF-Schreiben touches a covered area, including the annual Basiszins notice (typically
  January)
- new tax year forms are released
- a BFH or BVerfG decision lands on a covered point — especially a listed open question, and
  especially 2 BvL 3/21 on stock loss ring-fencing
- a re-audit of the store against the nine Validation Protocol items

**What the audit delivers.**

1. The store updated to current law, every touched file re-verified against all nine protocol
   items.
2. `reference/INDEX.md` and `coverage-matrix.md` in step.
3. **Every claim the audit touched has its map row re-decided.** This is the gate that is easy to
   skip: no code was changed, so a row can be left reading `implements` when the audit has just
   moved the law underneath it. It is now a `deviates`, and saying so is the point of the
   category.
4. The follow-up `fix-func` for each new deviation **named, not implied**.

An audit that produces no change still ends by saying what was checked and against what. A silent
audit is indistinguishable from no audit.

**Known consequence, accepted deliberately:** between a `ks-maint` audit and the `fix-func` that
closes a deviation it found, the engine emits a figure the store contradicts, and that is visible
only to someone who opens the map — not to the person filing the return. Whether such a deviation
should reach the report through `src/processing/data_gaps.py` is an open design question, recorded
here rather than resolved.

---

## Scope: supported taxable events and asset types

### Asset types
- Stocks (Aktien) — EStG 20
- Bonds (Anleihen) — EStG 20
- Investment Funds (Investmentfonds) — InvStG 2018
- Options/Derivatives (Termingeschäfte) — EStG 20
- CFDs — EStG 20
- Private Sale Assets (Gold ETCs, Crypto ETPs) — EStG 23
- Foreign Currency (Fremdwährung) — EStG 20 / EStG 23

### Taxable events
- Sale of securities (long/short) — EStG 20 Abs. 2
- Dividends — EStG 20 Abs. 1 Nr. 1
- Interest — EStG 20 Abs. 1 Nr. 7
- Fund distributions — InvStG 16
- Vorabpauschale — InvStG 18
- Fund sale gains/losses — InvStG 19 + 20
- Option premiums (Stillhalterprämien) — EStG 20 Abs. 1 Nr. 11
- Option expiration/exercise/assignment — EStG 20 Abs. 2
- Cash settlement (index options) — EStG 20 Abs. 2
- Corporate actions (merger, split, stock dividend) — EStG 20 Abs. 4a
- Foreign withholding tax — EStG 32d Abs. 5, 34c
- Currency gains/losses — EStG 20 Abs. 2 / EStG 23
- Private sales within speculation period — EStG 23 Abs. 1 Nr. 2

### Loss offsetting rules
- General capital loss offsetting — EStG 20 Abs. 6
- Stock loss ring-fencing — EStG 20 Abs. 6 Satz 4
- Derivative loss restriction (repealed for all open cases by JStG 2024; see
  `estg-20-abs6-verlustverrechnung.md` — not "from 2025", and the separate form lines outlive
  the restriction) — EStG 20 Abs. 6 Satz 5 a.F.
- Private sale loss rules — EStG 23 Abs. 3 Satz 7-8

---

## Directory structure

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
    coverage-matrix.md      # Event/asset vs. source mapping
    open-legal-questions.md # Points no Tier 1/2 source settles: both readings, both authorities
    inlaendisch-auslaendisch-relevance.md
```

Everything in that tree is law and only law. This document and
`docs/legal-implementation-map.md` sit outside it deliberately: both must talk about how the
engine and the store relate, which no file inside may do.

---

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
  Einzelfragen-zur-Abgeltungsteuer circular was recorded as unretrievable after WebFetch and a
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
