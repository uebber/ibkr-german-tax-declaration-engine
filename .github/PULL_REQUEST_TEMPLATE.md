<!--
One category per PR. No mixing. If this change needs two, it is two PRs — store before code.
The categories are in CLAUDE.md, under 'Before you start'. Each gate there states the
failure it prevents; read that line before deciding a gate is overhead.
-->

## Category

<!-- Tick exactly one. Delete the band whose gates do not apply. -->

**Band A — changes what a correct figure is, or produces one**

- [ ] `feat-func` — expands the tax events or asset types the engine can process
- [ ] `fix-func` — moves a declared figure, or where it lands, from wrong to compliant
- [ ] `ks-maint` — brings `reference/` up to current law after an audit trigger; no behaviour change

**Band B — must provably not move a figure**

- [ ] `feat-ux` — reduces the effort of getting from broker export to a checked declaration
- [ ] `fix-ux` — corrects presentation that misleads, without moving a figure
- [ ] `fix-nonfunc` — removes a way the engine can fail, a way a failure can go unnoticed, or a way this repository can disclose what it must not
- [ ] `refactor` — restructures code for a specific imminent change; output-identical

## What and why

<!-- What changed, and what it is measured against. If `refactor`, name the imminent
     feat-*/fix-* that justifies it. If `ks-maint`, name the trigger. -->

## Every change

- [ ] Clean-clone: `cp src/config_example.py src/config.py && uv run pytest -q`
- [ ] No silent default — anything unresolvable raises, after collecting every case
- [ ] No account data; no reference to a document this repo does not contain
- [ ] No half-converted tree — sites enumerated **including docs, comments and docstrings**; `grep` count before/after: 
- [ ] Looked at what any destructive step would remove before running it
- [ ] Standing constraints honoured (no pre-existing test or application code changed without an explicit ask)
- [ ] Every factual claim below names how it was measured

## Band A gates

- [ ] The requirement was in `reference/` **before** the code, cited to the sentence, verified against all nine Validation Protocol items
- [ ] `GT-<AREA>-<NNN>` claim ID cited in code, test or commit — which: 
- [ ] `docs/legal-implementation-map.md` row present and honest; `INDEX.md` and `coverage-matrix.md` in step
- [ ] `feat-func` / `fix-func` only — red-first verified, count: 
- [ ] `feat-func` / `fix-func` only — parity measured, assessment year: 
- [ ] `ks-maint` only — **every claim the audit touched has its map row re-decided**, and each new `deviates` names the `fix-func` that will close it

## Band B gates

- [ ] Figures provably unmoved — parity, assessment year:  <!-- or: diff does not touch src/ -->
- [ ] Zero map rows changed, zero claim IDs changed
- [ ] `refactor` only — probed site by site, not merely run
- [ ] `fix-nonfunc` only — **calibrated against a deliberately broken tree**; what was broken and what tripped: 

## How each claim above was measured

<!-- One line per factual claim. "The suite passed" is not a measurement of anything the
     gates ask about; a green result from an uncalibrated instrument is worth nothing. -->
