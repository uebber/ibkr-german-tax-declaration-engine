# src/processing/vorabpauschale_declarations.py
"""
What Vorabpauschale was **declared**, per fund and calendar year.

§ 19 Abs. 1 Satz 3 InvStG reduces the disposal gain by the Vorabpauschalen
*angesetzt* during the holding period ([GT-INVSTG-030]). For units that never
bore inlaendischer Steuerabzug -- which is every unit held at a foreign broker
-- the Anleitung's third sentence is the operative one: they reduce the gain
*"nur, soweit Sie diese Vorabpauschalen der Besteuerung unterworfen haben (Zeile
9 bis 13)"*, and the taxpayer must *"legen Sie dar"* that they did
([GT-INVSTG-034], [GT-FORM-033]). So the deduction is the mirror of a
declaration, and a declaration is not something this engine can recompute.

**Why not recompute it.** The engine matures. Its figure for calendar 2023 today
already differs from what the VZ 2024 return carried, after the Ruecknahmepreis,
Stichtag and Abs. 2 corrections. The deduction is capped at what was declared, so
recomputing would claim an amount nobody ever declared -- and a Vorabpauschale
that was never declared is not deferred to disposal, it is lost.

Third instance of the pattern `AssetClassifier` and `FundPriceStore` already
follow: a JSON file of answers to something nothing can derive. Two differences,
both deliberate:

- **Write-once.** A figure once declared is what was declared. Amending it is a
  deliberate edit of the file by someone who has the amended return in front of
  them, not a side effect of running the engine again.
- **Written only from an answer.** `FundPriceStore` saves as soon as it learns a
  price; this one records nothing the taxpayer did not state. Two writers, and
  both are the taxpayer speaking: the prompt below, asked once per fund and
  earlier calendar year, and `--commit-vorabpauschale-declaration`, which records
  the current return's own Zeilen 9-13 figures after it has been filed. Nothing
  on the ordinary computation path writes here — a run before filing is not a
  declaration, and auto-writing would record dry runs.

The divergence check that keeps the two honest lives in the engine: every run
compares its own figure for the preceding calendar year against the entry stored
for it, so a year the engine has since changed its mind about surfaces while the
return is still amendable.

**A committed year records every fund held at that year's close, including the
ones that owed nothing.** Without the explicit zeros a later run cannot tell
"declared nothing" from "never declared", and would report a gap against a fund
that owed nothing.

**Three states, not two.** The distinction that matters most in practice is
between a fund that declared a zero and a year where *nothing was declared at
all* -- which is the ordinary case for anyone whose returns were filed before
this engine could compute a Vorabpauschale. Both deduct nothing today; only the
second is a lost deduction that a corrected declaration would recover, and only
the second may later be superseded by a real figure. So:

    DECLARED      an amount was brought to tax that year (0.00 is a legitimate
                  amount: the fund owed nothing)
    NOT_DECLARED  the taxpayer states nothing was declared for that fund-year
    (absent)      nobody has been asked yet -- never treated as either of the above

**Nothing here is ever inferred.** An absent entry is not a zero, and the engine
may not fill one in from its own computation: that would be the invented input
CLAUDE.md refuses, and it would put a deduction on a return that the Anleitung's
condition does not support.
"""
import json
import logging
import os
from dataclasses import dataclass
from datetime import date
from enum import Enum
from decimal import Decimal
from typing import Dict, Iterable, List, Optional, Set

from src.domain.assets import InvestmentFund, SnapshotsByAccount, person_snapshot
from src.domain.exceptions import ProcessingError

logger = logging.getLogger(__name__)

# Recorded per fund and holding-period year the taxpayer states was never declared,
# when units of that fund were disposed of. WARNING: the deduction is left out, so
# the declared gain is if anything too HIGH -- but the deduction is real money and
# it is recoverable, which is why this names the year and the route to correcting
# it rather than merely noting an absence.
NOT_DECLARED_CODE = "KAP_INV_Z53_VORABPAUSCHALE_NOT_DECLARED"

# Recorded per fund and holding-period year where nobody has yet said whether a
# Vorabpauschale was declared -- a --no-interactive run, or a question deferred at
# the prompt. Distinct from NOT_DECLARED_CODE, which is an answer: this one is the
# absence of one, and the two call for different things from the reader. WARNING.
DECLARATION_UNKNOWN_CODE = "KAP_INV_Z53_VORABPAUSCHALE_DECLARATION_UNKNOWN"

# Recorded where a declared amount exists but cannot be split over the tranches:
# no year-end holding to split it by, or a lot whose acquisition date the replay
# invented. WARNING, same direction as above.
NOT_ATTRIBUTABLE_CODE = "KAP_INV_Z53_VORABPAUSCHALE_NOT_ATTRIBUTABLE"

# Recorded when this run's figure for the preceding calendar year differs from the
# one on record as declared. WARNING: the declared figure still governs, and the
# point is that the return is amendable.
DIVERGES_CODE = "VORABPAUSCHALE_DECLARATION_DIVERGES"


class DeclarationStatus(Enum):
    """Whether the fund-year was brought to tax at all."""
    DECLARED = "declared"
    NOT_DECLARED = "not_declared"


@dataclass(frozen=True)
class DeclaredVorabpauschale:
    """One fund-year, as the taxpayer says it was handled.

    `gross_eur` is the **gross** figure -- what went on Zeilen 9-13, before
    Teilfreistellung -- because Satz 4 makes the deduction the gross amount
    *"ungeachtet einer moeglichen Teilfreistellung nach § 20"*. Storing the net
    figure would silently cut the deduction by the Teilfreistellung rate. On a
    `NOT_DECLARED` record it is 0.00 and means nothing was brought to tax, which
    is not the same fact as a declared zero.

    `declared_on` and `source` are the provenance the Anleitung's *"Bitte legen
    Sie dar"* asks for: which return carried this figure, and when.
    """
    gross_eur: Decimal
    declared_on: date
    source: str
    status: DeclarationStatus = DeclarationStatus.DECLARED

    def __post_init__(self):
        if self.status is DeclarationStatus.NOT_DECLARED and self.gross_eur != Decimal("0.00"):
            raise ProcessingError(
                f"A NOT_DECLARED record cannot carry an amount ({self.gross_eur}). "
                "Nothing was brought to tax, so there is nothing to deduct.")

    @property
    def is_deductible(self) -> bool:
        """Whether § 19 Abs. 1 Satz 3 lets this fund-year reduce a disposal gain."""
        return self.status is DeclarationStatus.DECLARED


class VorabpauschaleDeclarationStore:
    """The declared Vorabpauschalen, keyed by classification key and calendar year.

    A file that cannot be read raises rather than starting empty. An empty store
    is a legitimate state -- nothing has been declared yet -- so a silent one
    would look exactly like a store whose file was corrupted, and would cost the
    taxpayer every deduction it holds.
    """

    def __init__(self, cache_file_path: Optional[str] = None):
        if cache_file_path is None:
            import src.config as app_config
            cache_file_path = app_config.VORABPAUSCHALE_DECLARATION_STORE_PATH
        self.cache_file_path = cache_file_path
        self._entries: Dict[str, DeclaredVorabpauschale] = {}
        self._load()

    @staticmethod
    def _key(classification_key: str, year: int) -> str:
        return f"{classification_key}|{year}"

    def _load(self) -> None:
        if not os.path.exists(self.cache_file_path):
            return
        try:
            with open(self.cache_file_path, "r", encoding="utf-8") as f:
                raw = json.load(f)
        except Exception as e:
            raise ProcessingError(
                f"The Vorabpauschale declaration store at {self.cache_file_path} "
                f"could not be read: {e}. It records what was declared on earlier "
                "returns, which nothing can recompute; treating it as empty would "
                "silently forfeit the § 19 Abs. 1 Satz 3 deduction. Fix the file."
            ) from e

        for key, entry in raw.items():
            try:
                self._entries[key] = DeclaredVorabpauschale(
                    # Decimal from the stored *text*: a float round-trip would
                    # alter a figure that was filed with a tax authority.
                    gross_eur=Decimal(str(entry["gross_eur"])),
                    declared_on=date.fromisoformat(entry["declared_on"]),
                    source=entry.get("source", ""),
                    # Absent on entries written before the three-state
                    # distinction existed. Those were all real declarations --
                    # the only writer was the commit at filing -- so DECLARED is
                    # what they meant, not a guess standing in for a missing
                    # value.
                    status=DeclarationStatus(entry.get("status", "declared")),
                )
            except (KeyError, ValueError, TypeError) as e:
                raise ProcessingError(
                    f"Declaration store entry {key!r} in {self.cache_file_path} is "
                    f"unreadable: {e}. A declared amount cannot be guessed at."
                ) from e

    def get(self, classification_key: str, year: int) -> Optional[DeclaredVorabpauschale]:
        return self._entries.get(self._key(classification_key, year))

    def committed_years(self) -> Set[int]:
        """Calendar years for which a declaration was recorded at all.

        The gap report turns on this: an entry missing from a committed year means
        the fund declared nothing that year, which is a fact about the
        declaration. A year that was never committed is a missing record.
        """
        years: Set[int] = set()
        for key in self._entries:
            _, _, year_text = key.rpartition("|")
            try:
                years.add(int(year_text))
            except ValueError:  # pragma: no cover - _load would have rejected it
                continue
        return years

    def commit(self, classification_key: str, year: int,
               entry: DeclaredVorabpauschale) -> None:
        """Record one fund-year. Write-once, with one deliberate exception.

        Re-recording the identical answer is a no-op, so re-running the commit
        after filing is harmless. Replacing a declared amount with a different
        one raises: what was declared does not change because the engine's figure
        has, and an amended return is a deliberate edit of this file by someone
        holding the amendment.

        **The exception is the correction path, and it is the point of the
        NOT_DECLARED state.** A year recorded as never declared is precisely the
        year a taxpayer goes back and corrects -- returns filed before this engine
        could compute a Vorabpauschale are the ordinary case -- and once it *is*
        declared, the record has to be able to say so. So NOT_DECLARED may be
        superseded by DECLARED. The reverse may not: a declaration that was made
        is not undone by an answer given later at a prompt.
        """
        existing = self._entries.get(self._key(classification_key, year))
        if existing is not None:
            if (existing.status == entry.status
                    and existing.gross_eur == entry.gross_eur):
                return
            if (existing.status is DeclarationStatus.NOT_DECLARED
                    and entry.status is DeclarationStatus.DECLARED):
                logger.info(
                    "%s for calendar %d was recorded as not declared and is now "
                    "recorded as declared at EUR %s (%s). The § 19 Abs. 1 Satz 3 "
                    "deduction for it is available from this run on.",
                    classification_key, year, entry.gross_eur, entry.source)
                self._entries[self._key(classification_key, year)] = entry
                return
            if entry.status is DeclarationStatus.NOT_DECLARED:
                raise ProcessingError(
                    f"{classification_key} for calendar {year} is on record as "
                    f"declared at EUR {existing.gross_eur} ({existing.source}, "
                    f"{existing.declared_on}); it cannot be recorded as never "
                    f"declared. If that record is wrong, edit "
                    f"{self.cache_file_path} by hand."
                )
            raise ProcessingError(
                f"{classification_key} for calendar {year} is already recorded as "
                f"declared at EUR {existing.gross_eur} (on {existing.declared_on}, "
                f"{existing.source}); the commit would replace it with EUR "
                f"{entry.gross_eur}. What was declared does not change because the "
                f"engine's figure has. If the return was amended, edit "
                f"{self.cache_file_path} by hand with the amended figure in front "
                f"of you."
            )
        self._entries[self._key(classification_key, year)] = entry

    def save(self) -> None:
        directory = os.path.dirname(self.cache_file_path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        payload = {
            key: {
                "gross_eur": str(e.gross_eur),
                "declared_on": e.declared_on.isoformat(),
                "source": e.source,
                "status": e.status.value,
            }
            for key, e in sorted(self._entries.items())
        }
        with open(self.cache_file_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)

    def __len__(self) -> int:
        return len(self._entries)


def commit_declared_vorabpauschale(
    *,
    store: VorabpauschaleDeclarationStore,
    asset_resolver,
    prior_eoy_positions: "SnapshotsByAccount",
    vorabpauschale_items: Iterable,
    vorabpauschale_year: int,
    declared_on: date,
    source: str,
) -> List[str]:
    """Record this run's Zeilen 9-13 figures as the declaration for one calendar year.

    Called at filing, never on the ordinary path. Every fund held at the close of
    `vorabpauschale_year` gets an entry -- the ones the run computed a
    Vorabpauschale for, and a zero for the rest, because "held and owed nothing"
    and "not on the record" must stay distinguishable.

    Which funds were held is read from the preceding year's closing snapshot, the
    same Rz. 18.4 count the Vorabpauschale itself multiplies by ([GT-INVSTG-017]),
    summed over the person's accounts ([GT-ESTG20-061]).

    Returns one line per entry written, for the console.
    """
    gross_by_asset = {
        item.asset_internal_id: item.gross_vorabpauschale_eur
        for item in vorabpauschale_items
        if item.vorabpauschale_year == vorabpauschale_year
    }

    written: List[str] = []
    for asset_id, asset in sorted(
        asset_resolver.assets_by_internal_id.items(),
        key=lambda pair: pair[1].get_classification_key(),
    ):
        if not isinstance(asset, InvestmentFund):
            continue
        reported = person_snapshot(prior_eoy_positions, asset_id)
        held = (reported.quantity if reported is not None else None) or Decimal(0)
        gross = gross_by_asset.get(asset_id)
        if held <= Decimal(0) and gross is None:
            continue
        key = asset.get_classification_key()
        entry = DeclaredVorabpauschale(
            gross_eur=(gross if gross is not None else Decimal("0.00")),
            declared_on=declared_on,
            source=source,
        )
        store.commit(key, vorabpauschale_year, entry)
        written.append(f"{key} ({asset.description or ''}) {vorabpauschale_year}: "
                       f"EUR {entry.gross_eur}")

    store.save()
    logger.info("Recorded %d declared Vorabpauschale entries for calendar %d in %s.",
                len(written), vorabpauschale_year, store.cache_file_path)
    return written


def prompt_for_declared_vorabpauschale(
    asset,
    calendar_year: int,
) -> Optional[DeclaredVorabpauschale]:
    """Ask at the console what an earlier return declared for one fund and year.

    Reached only for a calendar year **before** the one this return declares, and
    only where nothing is on record yet. The year this return itself declares is
    not asked about: its figures are on the form being produced, and the taxpayer
    is filing them.

    Three answers, and the third is why this exists:

    - **an amount** -- what Zeilen 9-13 of the VZ `calendar_year + 1` return
      carried for this fund, gross, before Teilfreistellung;
    - **nothing was declared** -- recorded as such, not as a zero. It is the
      ordinary answer for a return filed before this engine could compute a
      Vorabpauschale, and it is the answer that can later be superseded, because
      a corrected declaration brings the amount to tax and restores the deduction;
    - **not now** -- nothing is recorded, the deduction is not taken, and the run
      reports it. An unanswered year is never read as either of the other two.

    Deliberately does NOT offer the engine's own figure as a default. This engine
    can compute what that year's Vorabpauschale *should* have been, and it is not
    what the question asks: the deduction turns on what was brought to tax, and a
    number on the prompt line is the kind of thing that gets accepted with Enter.
    The way to obtain the figure is stated instead -- re-run the earlier year --
    which puts the taxpayer in front of that year's whole declaration rather than
    one number out of context.
    """
    key = asset.get_classification_key()
    print(f"\n--- Vorabpauschale {calendar_year}: was sie erklärt haben ---")
    print(f"  Fonds:  {asset.description or ''} [{key}]")
    print(f"  Anteile dieses Fonds wurden zum Ende von {calendar_year} gehalten und "
          f"später veräußert.")
    print(f"  Nur eine Vorabpauschale, die Sie tatsächlich der Besteuerung unterworfen")
    print(f"  haben, mindert den Veräußerungsgewinn (§ 19 Abs. 1 Satz 3 InvStG,")
    print(f"  Anleitung zu Zeile 53). Massgeblich ist die Erklärung für VZ "
          f"{calendar_year + 1}, Zeilen 9-13.")
    print(f"  Den Betrag, der dort hätte stehen müssen, zeigt Ihnen ein Lauf mit")
    print(f"  --tax-year {calendar_year + 1}.")
    print(f"  Antworten: Betrag in EUR  |  'n' = nichts erklärt  |  leer = später "
          f"entscheiden")

    raw = input(f"  Brutto-Vorabpauschale {calendar_year} laut Erklärung VZ "
                f"{calendar_year + 1} [EUR/n/leer]: ").strip().replace(",", ".")

    if not raw:
        logger.warning("No answer for %s / calendar %d; no deduction is taken.",
                       key, calendar_year)
        return None

    if raw.lower() in {"n", "nein", "no"}:
        print(f"  Notiert: für {calendar_year} wurde nichts erklärt. Der Abzug in "
              f"Zeile 53 entfällt für dieses Jahr,")
        print(f"  solange die Erklärung für VZ {calendar_year + 1} nicht berichtigt "
              f"wird. Nach einer Berichtigung hier den")
        print(f"  erklärten Betrag eintragen — die Notiz wird dann ersetzt.")
        return DeclaredVorabpauschale(
            gross_eur=Decimal("0.00"), declared_on=date.today(),
            source=(f"Angabe des Steuerpflichtigen: in der Erklärung für VZ "
                    f"{calendar_year + 1} wurde keine Vorabpauschale angesetzt"),
            status=DeclarationStatus.NOT_DECLARED)

    try:
        amount = Decimal(raw)
    except Exception:
        print(f"  '{raw}' ist keine Zahl. Übersprungen; es wird nichts abgezogen.")
        return None
    if amount < Decimal(0):
        print("  Eine angesetzte Vorabpauschale ist nicht negativ. Übersprungen.")
        return None

    # A figure that goes on a tax return has to be traceable to something outside
    # this program -- the same rule the year-start price prompt applies.
    source = input(
        f"  Beleg (z.B. 'Anlage KAP-INV {calendar_year + 1} Zeile 9, eingereicht "
        f"2025-05-14'): ").strip()
    if not source:
        print("  Ohne Beleg wird der Betrag nicht übernommen: die Anleitung zu "
              "Zeile 53 verlangt,")
        print("  dass Sie die Erklärung der Vorabpauschalen darlegen können.")
        return None

    return DeclaredVorabpauschale(
        gross_eur=amount, declared_on=date.today(), source=source,
        status=DeclarationStatus.DECLARED)


def make_declaration_prompt():
    """The `ask` callable the engine takes; None disables asking entirely."""
    def ask(asset, calendar_year: int) -> Optional[DeclaredVorabpauschale]:
        return prompt_for_declared_vorabpauschale(asset, calendar_year)
    return ask
