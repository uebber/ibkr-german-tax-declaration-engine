"""
The knowledge store states law; the map states what the engine does about it.
These guards keep the two apart and keep them in step.

legal_basis: infrastructure. No declared figure depends on these assertions.
What depends on them is whether `reference/` can still be trusted as ground
truth — CLAUDE.md's Purity Rule and research-strategy Validation Protocol
item 9. The rule exists because an "Engine Mapping" table in the store named
`RealizedGainLoss.accumulated_vorabpauschale`, a field that does not exist and
never did, and the store went on asserting it as ground truth. A legal fact
cannot go stale from a refactor; an identifier can.
"""
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
REFERENCE_DIR = REPO_ROOT / "reference"
MAP_DOC = REPO_ROOT / "docs" / "legal-implementation-map.md"

# Verbatim transcripts of official documents; their wording is not ours to edit.
# research-strategy.md is the procedure for growing the library, not a statement
# of law, and it necessarily talks about how the engine and the store relate.
EXEMPT = {"research/research-strategy.md"}


def _is_exempt(path: Path) -> bool:
    rel = path.relative_to(REFERENCE_DIR).as_posix()
    return path.name.startswith("Anltg_") or rel in EXEMPT


def reference_files() -> list[Path]:
    return sorted(p for p in REFERENCE_DIR.rglob("*.md") if not _is_exempt(p))


CLAIM_ID = re.compile(r"\bGT-[A-Z0-9]+-\d{3}\b")

# Each pattern is a way implementation state has actually leaked into the store.
# A match is a defect by definition — see the module docstring. The allowlist is
# deliberately empty; adding to it needs a stated reason in the diff.
IMPLEMENTATION_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("source path", re.compile(r"\b(?:src|tests|scripts)/[\w./-]+")),
    ("python module", re.compile(r"\b[\w/]+\.py\b")),
    ("code fence", re.compile(r"^\s*```\s*(?:python|py|pycon)\b", re.IGNORECASE)),
    # Backticked ALLCAPS: engine enum members and constants. Claim IDs contain
    # hyphens and so cannot match; German legal abbreviations (BStBl, BGBl, GZ,
    # AO, EStG) are mixed-case or shorter than the floor.
    ("engine identifier", re.compile(r"`[A-Z][A-Z0-9_]{3,}`")),
    # Backticked dotted attribute: `Class.field`, `module.function`. Excludes
    # document and URL suffixes, which are legitimate in citations.
    ("dotted attribute",
     re.compile(r"`[A-Za-z_]\w*\.(?!html\b|pdf\b|md\b|csv\b|de\b|com\b|org\b)[a-z_]\w*`")),
    # Backticked snake_case: a bare function or variable name, which the dotted
    # and ALLCAPS patterns both miss. `get_form_rules` survived in the store for
    # exactly that reason, together with a sentence describing what it raises.
    # German legal citations contain no underscores, so this cannot collide.
    ("snake_case identifier", re.compile(r"`[a-z][a-z0-9]*(?:_[a-z0-9]+)+`")),
    # Bare "engine" in any grammatical position. The earlier form required "the"
    # or "this" in front, and three violations slipped past it as "an engine
    # change", "engine correctness" and "engine-relevant". No German legal term
    # contains the word.
    ("engine prose", re.compile(r"\bengines?\b", re.IGNORECASE)),
    ("input data file", re.compile(r"\bdata_import\b|\b[\w-]+\.csv\b")),
]

ALLOWLIST: set[tuple[str, str, str]] = set()  # (relative path, pattern name, matched text)


def _violations(path: Path) -> list[tuple[int, str, str]]:
    rel = path.relative_to(REPO_ROOT).as_posix()
    found = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        for name, pattern in IMPLEMENTATION_PATTERNS:
            for match in pattern.finditer(line):
                text = match.group(0).strip()
                if (rel, name, text) in ALLOWLIST:
                    continue
                found.append((lineno, name, text))
    return found


class TestStoreStatesLawOnly:
    """Guard 1: nothing under reference/ names implementation state."""

    def test_the_corpus_is_not_empty(self):
        """Calibration: a guard that scans nothing passes trivially."""
        files = reference_files()
        assert len(files) >= 15, f"only {len(files)} reference files found; glob is wrong"

    @pytest.mark.parametrize("path", reference_files(), ids=lambda p: p.name)
    def test_no_implementation_references(self, path):
        found = _violations(path)
        assert not found, (
            f"{path.relative_to(REPO_ROOT)} names implementation state. "
            f"reference/ states law only; move this to docs/legal-implementation-map.md "
            f"(CLAUDE.md Purity Rule, research-strategy Validation Protocol item 9).\n"
            + "\n".join(f"  line {n}: [{kind}] {text}" for n, kind, text in found[:20])
        )


HEADING = re.compile(r"^\s{0,3}#{1,6}\s")


def _claim_ids_in(path: Path) -> list[str]:
    """Every mention, definition or cross-reference."""
    return CLAIM_ID.findall(path.read_text(encoding="utf-8"))


def _claim_ids_defined_in(path: Path) -> list[str]:
    """A claim is DEFINED by the heading it is tagged on. Anywhere else -- a
    summary table, a cross-reference from another file -- is a mention. Without
    this split, citing a claim by ID would register as a second definition and
    the uniqueness guard would forbid exactly the cross-referencing the IDs
    exist to enable."""
    return [c
            for line in path.read_text(encoding="utf-8").splitlines() if HEADING.match(line)
            for c in CLAIM_ID.findall(line)]


def _store_definitions() -> dict[str, list[str]]:
    """Claim ID -> the reference files whose headings define it."""
    definitions: dict[str, list[str]] = {}
    for path in reference_files():
        rel = path.relative_to(REPO_ROOT).as_posix()
        for claim in set(_claim_ids_defined_in(path)):
            definitions.setdefault(claim, []).append(rel)
    return definitions


class TestClaimIdsResolve:
    """Guards 2 and 3: the store and the map agree, in both directions."""

    def test_the_map_exists_and_has_claims(self):
        """Calibration: an empty map would make guard 2 vacuous."""
        assert MAP_DOC.exists(), f"{MAP_DOC} is missing"
        assert len(set(_claim_ids_in(MAP_DOC))) >= 20, "map carries almost no claim IDs"

    def test_every_claim_is_defined_exactly_once(self):
        """Guard 2. Two files defining the same ID means the map's row is
        ambiguous, which is the failure the IDs exist to prevent."""
        duplicated = {c: files for c, files in _store_definitions().items() if len(files) > 1}
        assert not duplicated, (
            "claim IDs defined in more than one reference file:\n"
            + "\n".join(f"  {c}: {', '.join(files)}" for c, files in sorted(duplicated.items()))
        )

    def test_every_mapped_claim_exists_in_the_store(self):
        """Guard 2. A map row pointing at nothing is a dead citation — the
        class of error a heading anchor produces silently."""
        store = set(_store_definitions())
        dangling = sorted(set(_claim_ids_in(MAP_DOC)) - store)
        assert not dangling, (
            f"docs/legal-implementation-map.md cites claim IDs that no reference file "
            f"defines: {', '.join(dangling)}"
        )

    def test_every_cross_reference_inside_the_store_resolves(self):
        """Guard 2. One file may cite another's claim by ID; that citation must
        land on a real definition."""
        store = set(_store_definitions())
        dangling: dict[str, list[str]] = {}
        for path in reference_files():
            rel = path.relative_to(REPO_ROOT).as_posix()
            for claim in sorted(set(_claim_ids_in(path)) - store):
                dangling.setdefault(claim, []).append(rel)
        assert not dangling, (
            "claim IDs mentioned in reference/ with no defining heading:\n"
            + "\n".join(f"  {c}: {', '.join(f)}" for c, f in sorted(dangling.items()))
        )

    def test_every_stored_claim_is_mapped(self):
        """Guard 3. A requirement with no map row is one nobody has decided
        about — neither implemented, nor deliberately not."""
        mapped = set(_claim_ids_in(MAP_DOC))
        unmapped = sorted(set(_store_definitions()) - mapped)
        assert not unmapped, (
            f"legal requirements with no row in docs/legal-implementation-map.md: "
            f"{', '.join(unmapped)}"
        )


class TestCitationsIntoTheStoreResolve:
    """Guard 4: code cites the reference; those citations must land somewhere.

    The cheap half of a rename tripwire. Renaming a reference file silently
    invalidates every prose citation pointing at it, and there are ~40.
    """

    CITATION = re.compile(r"\breference/[\w./-]*")

    def _cited_paths(self, roots: tuple[str, ...]) -> dict[str, list[str]]:
        cited: dict[str, list[str]] = {}
        for root in roots:
            for source in sorted((REPO_ROOT / root).rglob("*.py")):
                if "__pycache__" in source.parts:
                    continue
                text = source.read_text(encoding="utf-8")
                for match in self.CITATION.finditer(text):
                    target = match.group(0).rstrip(".,;:")
                    cited.setdefault(target, []).append(
                        source.relative_to(REPO_ROOT).as_posix())
        return cited

    def test_citations_from_src_and_tests_resolve(self):
        cited = self._cited_paths(("src", "tests"))
        assert cited, "no reference/ citations found at all; the scan is broken"
        broken = {}
        for target, sources in cited.items():
            path = REPO_ROOT / target
            # A citation may be line-wrapped and end at a directory boundary.
            ok = path.is_dir() if target.endswith("/") else path.exists()
            if not ok:
                broken[target] = sources
        assert not broken, (
            "code cites reference/ paths that do not exist (a rename or deletion "
            "left the citation dangling):\n"
            + "\n".join(f"  {t} <- {', '.join(sorted(set(s)))}" for t, s in sorted(broken.items()))
        )

    def test_claim_ids_cited_from_src_and_tests_resolve(self):
        """Guard 5. Docstrings cite claims by ID. An ID that no longer exists
        is the same failure the retired field pointer was — a citation that
        reads as authoritative and refers to nothing."""
        store = set(_store_definitions())
        assert store, "no claim IDs found in the store; the scan is broken"
        dangling: dict[str, list[str]] = {}
        for root in ("src", "tests"):
            for source in sorted((REPO_ROOT / root).rglob("*.py")):
                if "__pycache__" in source.parts or source.name == Path(__file__).name:
                    continue
                for claim in set(CLAIM_ID.findall(source.read_text(encoding="utf-8"))) - store:
                    dangling.setdefault(claim, []).append(
                        source.relative_to(REPO_ROOT).as_posix())
        assert not dangling, (
            "code cites claim IDs that no reference file defines:\n"
            + "\n".join(f"  {c} <- {', '.join(f)}" for c, f in sorted(dangling.items()))
        )
