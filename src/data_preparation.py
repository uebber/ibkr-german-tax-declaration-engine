"""
Data preparation module.

Resolves input files from data_import/ based on the selected tax year,
concatenates multi-year transaction files for historical FIFO tracking,
and writes working copies to data/ for pipeline consumption.

The data_import/ directory is READ-ONLY — this module never modifies it.
"""

import csv
import io
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

IMPORT_DIR = Path("data_import")

WORKING_DIR = Path("data")

# Naming scheme for data_import/ files
# Trades-{YYYY}.csv
# Cash_Transactions-{YYYY}.csv
# Corporate_Actions-{YYYY}.csv
# Cash_Balance-{YYYY}.csv
# Positions-{YYYY}-SoY.csv
# Positions-{YYYY}-EoY.csv


def _find_import_file(pattern_prefix: str, year: int, suffix: str = ".csv") -> Optional[Path]:
    """Find a single import file matching the naming scheme."""
    filename = f"{pattern_prefix}-{year}{suffix}"
    path = IMPORT_DIR / filename
    if path.exists():
        return path
    return None


def _earliest_import_year() -> int:
    """The first calendar year any input file covers.

    Used to bound the checkpoint marks. Reads the year out of every
    `<Prefix>-<YYYY>...csv` in the import directory rather than assuming a start
    year, so a user whose history begins later gets marks only where snapshots
    actually exist.
    """
    years = []
    for f in IMPORT_DIR.glob("*-*.csv"):
        for part in f.stem.split("-"):
            if len(part) == 4 and part.isdigit():
                years.append(int(part))
                break
    if not years:
        raise FileNotFoundError(
            f"No year-stamped input files found in {IMPORT_DIR}/. Expected the naming scheme "
            f"Trades-YYYY.csv, Positions-YYYY-EoY.csv, etc."
        )
    return min(years)


def _find_years_available(pattern_prefix: str) -> list[int]:
    """Find all years for which a given file type exists in data_import/."""
    years = []
    for f in sorted(IMPORT_DIR.glob(f"{pattern_prefix}-*.csv")):
        stem = f.stem  # e.g., "Trades-2024"
        parts = stem.split("-")
        if len(parts) >= 2 and parts[-1].isdigit():
            years.append(int(parts[-1]))
    return sorted(years)


def _concatenate_csvs(paths: list[Path], output_path: Path) -> None:
    """
    Concatenate multiple CSV files into one, keeping a single header row.
    Assumes all files have the same header structure.
    """
    header = None
    rows = []

    for path in paths:
        content = path.read_text(encoding="utf-8-sig")
        reader = csv.reader(io.StringIO(content))
        for i, row in enumerate(reader):
            if i == 0:
                if header is None:
                    header = row
                continue
            if row == header:  # skip repeated header rows IBKR inserts mid-file
                continue
            if row:  # skip empty rows
                rows.append(row)

    if header is None:
        logger.warning("No data found to concatenate for %s", output_path)
        return

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f, quoting=csv.QUOTE_ALL)
        writer.writerow(header)
        writer.writerows(rows)

    logger.info("Concatenated %d files (%d data rows) -> %s", len(paths), len(rows), output_path)


def _copy_file(src: Path, dest: Path) -> None:
    """Copy a CSV file to the working directory, stripping duplicate header rows."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    content = src.read_text(encoding="utf-8-sig")
    reader = csv.reader(io.StringIO(content))
    header = None
    rows = []
    for i, row in enumerate(reader):
        if i == 0:
            header = row
            rows.append(row)
            continue
        if row == header:
            continue
        if row:
            rows.append(row)
    with open(dest, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f, quoting=csv.QUOTE_ALL)
        writer.writerows(rows)
    logger.info("Copied %s -> %s", src, dest)


def prepare_data_for_tax_year(tax_year: int) -> dict[str, str]:
    """
    Prepare working data files in data/ for the given tax year.

    For transaction files (trades, cash_transactions, corporate_actions):
    concatenates all available years up to and including tax_year to provide
    full historical FIFO cost basis.

    For snapshot files (positions SoY/EoY, cash_balance):
    copies the single-year file for the tax year.

    Returns:
        Dict of file type -> working file path (for pipeline consumption)

    Raises:
        FileNotFoundError: If required files are missing in data_import/
    """
    if not IMPORT_DIR.exists():
        raise FileNotFoundError(
            f"Import directory '{IMPORT_DIR}' not found. "
            f"Place IBKR Flex Query CSV files there using the naming scheme: "
            f"Trades-YYYY.csv, Cash_Transactions-YYYY.csv, etc."
        )

    WORKING_DIR.mkdir(parents=True, exist_ok=True)
    result = {}

    # --- Transaction files: concatenate all years up to and including tax_year ---
    transaction_types = {
        "trades": "Trades",
        "cash_transactions": "Cash_Transactions",
        "corporate_actions": "Corporate_Actions",
    }

    # Optional here because whether the file is needed cannot be decided from its name:
    # an account that never traded options needs none, and one that only ever took
    # physical delivery needs none either -- those OptionEAE rows duplicate the Trades
    # export. Only a cash settlement carries information found nowhere else, and only the
    # trades say whether one happened. So the requirement is decided after parsing, in
    # `ParsingOrchestrator._require_option_cash_settlements`, not by a missing-file check
    # here. Absent means absent; it does not mean unnecessary.
    #
    # Transfers is optional in a plainer sense: a person who has never moved a holding
    # between their own accounts has no rows, and there is nothing to decide later --
    # a move that never happened leaves no lot in the wrong place. Both `_copy_file` and
    # `_concatenate_csvs` strip the repeated header row IBKR leaves mid-file where a
    # second account's export was appended, so neither reaches the parser as data.
    optional_transaction_types = {
        "options_eae": "Options_EAE",
        "transfers": "Transfers",
    }

    for file_key, prefix in transaction_types.items():
        available_years = _find_years_available(prefix)
        years_to_include = [y for y in available_years if y <= tax_year]

        if not years_to_include:
            raise FileNotFoundError(
                f"No {prefix} files found in {IMPORT_DIR}/ for {tax_year} or earlier. "
                f"Expected: {prefix}-{tax_year}.csv"
            )

        if tax_year not in years_to_include:
            raise FileNotFoundError(
                f"{prefix}-{tax_year}.csv not found in {IMPORT_DIR}/. "
                f"Available years: {years_to_include}"
            )

        paths = [IMPORT_DIR / f"{prefix}-{y}.csv" for y in years_to_include]
        output_path = WORKING_DIR / f"{file_key}.csv"

        if len(paths) == 1:
            _copy_file(paths[0], output_path)
        else:
            _concatenate_csvs(paths, output_path)

        result[file_key] = str(output_path)
        logger.info("%s: %d year(s) included (%s)", file_key, len(years_to_include),
                    ", ".join(str(y) for y in years_to_include))

    for file_key, prefix in optional_transaction_types.items():
        available_years = _find_years_available(prefix)
        years_to_include = [y for y in available_years if y <= tax_year]

        if not years_to_include:
            logger.info("No %s files found in %s/. Skipping.", prefix, IMPORT_DIR)
            result[file_key] = ""
            result[f"{file_key}_missing_years"] = ""
            continue

        paths = [IMPORT_DIR / f"{prefix}-{y}.csv" for y in years_to_include]
        output_path = WORKING_DIR / f"{file_key}.csv"

        if len(paths) == 1:
            _copy_file(paths[0], output_path)
        else:
            _concatenate_csvs(paths, output_path)

        result[file_key] = str(output_path)
        logger.info("%s: %d year(s) included (%s)", file_key, len(years_to_include),
                    ", ".join(str(y) for y in years_to_include))

        # An optional export that exists for SOME years is a different thing from one that
        # does not exist at all, and the difference has to reach the consumer rather than
        # be inferred from a path. The required types above stop the run when the tax
        # year's own file is missing; these cannot, because absence is legitimate. What
        # they can do is say which years are missing, so nothing downstream reports the
        # export as complete when it has a hole. Transfers is the case that needs it: the
        # multi-account warning tells the reader whether a move between their accounts
        # could be invisible, and a per-year gap is exactly when one could.
        expected_years = [y for y in range(min(years_to_include), tax_year + 1)]
        missing = [y for y in expected_years if y not in years_to_include]
        result[f"{file_key}_missing_years"] = ",".join(str(y) for y in missing)
        if missing:
            logger.warning(
                "%s: no file for %s, although %s exist(s). The window this export covers "
                "has a hole; anything reading it must not report it as complete.",
                file_key, ", ".join(str(y) for y in missing),
                ", ".join(str(y) for y in years_to_include))

    # --- Opening position: the PRECEDING year's end-of-year snapshot ---
    # The ledger's opening lots and the end-of-year reconciliation baseline must be the holding
    # as it stood before the tax year's first trade. That is the close of the preceding year,
    # not this year's own start-of-year file: a start-of-year snapshot is taken at the close of
    # the day it names, so if it names a trading day it already contains that day's trades and
    # the same trades arrive again from the Trades file. A VZ 2024 run failed exactly so.
    #
    # This year's Positions-{tax_year}-SoY.csv is deliberately not read here. It carries the
    # Ruecknahmepreis at the start of this calendar year, which belongs to the Vorabpauschale
    # declared one year later, and it is picked up then as the prior year's start snapshot.
    opening_file = _find_import_file("Positions", tax_year - 1, "-EoY.csv")
    if opening_file:
        soy_output = WORKING_DIR / "positions_start_of_year.csv"
        _copy_file(opening_file, soy_output)
        result["positions_start"] = str(soy_output)
    else:
        raise FileNotFoundError(
            f"Positions-{tax_year - 1}-EoY.csv not found in {IMPORT_DIR}/. It is the opening "
            f"position for tax year {tax_year}: the lots the year starts with, and the baseline "
            f"the end-of-year reconciliation is measured against. Without it the run would "
            f"begin from an empty portfolio and every carried-in holding would reconcile "
            f"wrongly. If {tax_year} is genuinely the first year with holdings, an empty file "
            f"with only a header row states that explicitly."
        )

    eoy_file = _find_import_file("Positions", tax_year, "-EoY.csv")
    if eoy_file:
        eoy_output = WORKING_DIR / "positions_end_of_year.csv"
        _copy_file(eoy_file, eoy_output)
        result["positions_end"] = str(eoy_output)
    else:
        logger.warning("No Positions-%d-EoY.csv found.", tax_year)
        result["positions_end"] = ""

    # --- Intermediate checkpoint marks for the historical replay ---
    # A partial ledger is the normal starting condition: the transaction files reach back only so
    # far, so the reconstruction of the earliest interval is missing whatever was held before the
    # window opened. The position snapshots are the ground truth to recover from, and there is one
    # at the close of every year, not just at the tax year's own boundary.
    #
    # Each `Positions-{Y}-EoY.csv` below the opening snapshot becomes a mark: the replay stops
    # there, compares, and either keeps the reconstruction or takes the snapshot and carries on.
    # `Positions-{tax_year-1}-EoY.csv` is NOT included -- it is the opening snapshot loaded above
    # and reconciled as the final mark by the existing path.
    #
    # EoY files only. A `Positions-{Y}-SoY.csv` names the close of the day it names, so on a
    # trading day it already contains that day's trades, and the same trades arrive again from the
    # Trades file (see the opening-position comment above). Those files feed the Vorabpauschale
    # reference prices and nothing else.
    mark_years = sorted(
        y for y in range(_earliest_import_year(), tax_year - 1)
        if _find_import_file("Positions", y, "-EoY.csv")
    )
    for year in mark_years:
        mark_file = _find_import_file("Positions", year, "-EoY.csv")
        mark_output = WORKING_DIR / f"positions_mark_{year}.csv"
        _copy_file(mark_file, mark_output)
        result[f"positions_mark_{year}"] = str(mark_output)
    if mark_years:
        logger.info("Historical replay checkpoint marks: %s",
                    ", ".join(f"{y}-12-31" for y in mark_years))
    else:
        logger.info("No intermediate checkpoint marks below %d-12-31.", tax_year - 1)

    # --- Positions for the preceding year: needed for the Vorabpauschale ---
    # The VP declared in VZ Y is the one computed FOR calendar Y-1 (18 Abs. 3 InvStG; Anleitung
    # zur Anlage KAP-INV, Zeilen 9-13). Its Basisertrag uses the Ruecknahmepreis at the start of
    # Y-1 and its cap the last price set in Y-1, so both of the PRIOR year's snapshots are
    # required. Absence is not an error here -- the engine decides what to do about a missing
    # snapshot at the point it knows whether any fund is actually held
    # (src/engine/calculation_engine.py).
    # Three snapshots, because the Basisertrag's price and its unit count are taken at
    # different moments. For the Vorabpauschale of calendar X (= tax_year - 1):
    #   positions_prior_start  X's first trading day    -> the Satz 2 price
    #   positions_prior_opening  close of X-1           -> the unit count, and the price
    #                                                      fallback when a fund was sold on
    #                                                      X's first trading day
    #   positions_prior_end    close of X               -> the Satz 3 cap's upper bound
    prior_year = tax_year - 1
    for file_key, suffix, label, year in (
        ("positions_prior_start", "-SoY.csv", "start", prior_year),
        ("positions_prior_end", "-EoY.csv", "end", prior_year),
        ("positions_prior_opening", "-EoY.csv", "opening", prior_year - 1),
    ):
        prior_file = _find_import_file("Positions", year, suffix)
        if prior_file:
            prior_output = WORKING_DIR / f"positions_prior_year_{label}.csv"
            _copy_file(prior_file, prior_output)
            result[file_key] = str(prior_output)
        else:
            logger.info(
                "No Positions-%d%s found. The Vorabpauschale for calendar %d cannot be "
                "computed from it; the engine will report this as a data gap if funds are held.",
                year, suffix, prior_year,
            )
            result[file_key] = ""

    # --- Cash Balance: copy for the tax year ---
    cash_balance_file = _find_import_file("Cash_Balance", tax_year)
    if cash_balance_file:
        cb_output = WORKING_DIR / "cash_balance.csv"
        _copy_file(cash_balance_file, cb_output)
        result["cash_balance"] = str(cb_output)
    else:
        logger.warning("No Cash_Balance-%d.csv found.", tax_year)
        result["cash_balance"] = ""

    return result
