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

    # Optional transaction types (no error if missing)
    optional_transaction_types = {
        "options_eae": "Options_EAE",
        "transfers": "Transfers",   # internal Depotübertragungen (per-Depot FIFO + transfers)
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

    # --- Positions: copy SoY and EoY for the tax year ---
    soy_file = _find_import_file("Positions", tax_year, "-SoY.csv")
    if soy_file:
        soy_output = WORKING_DIR / "positions_start_of_year.csv"
        _copy_file(soy_file, soy_output)
        result["positions_start"] = str(soy_output)
    else:
        # SoY may not exist for the first year of trading
        logger.warning("No Positions-%d-SoY.csv found. This is expected for the first year of trading.", tax_year)
        result["positions_start"] = ""

    eoy_file = _find_import_file("Positions", tax_year, "-EoY.csv")
    if eoy_file:
        eoy_output = WORKING_DIR / "positions_end_of_year.csv"
        _copy_file(eoy_file, eoy_output)
        result["positions_end"] = str(eoy_output)
    else:
        logger.warning("No Positions-%d-EoY.csv found.", tax_year)
        result["positions_end"] = ""

    # --- Prior-year SoY positions (optional): for the §18 Abs. 3 Vorabpauschale that
    # flows into this assessment year (the prior calendar year's VP). ---
    prior_soy_file = _find_import_file("Positions", tax_year - 1, "-SoY.csv")
    if prior_soy_file:
        prior_soy_output = WORKING_DIR / "positions_prior_start_of_year.csv"
        _copy_file(prior_soy_file, prior_soy_output)
        result["positions_prior_start"] = str(prior_soy_output)
    else:
        logger.info("No Positions-%d-SoY.csv found (prior-year SoY for Vorabpauschale).", tax_year - 1)
        result["positions_prior_start"] = ""

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
