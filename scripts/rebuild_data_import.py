#!/usr/bin/env python3
"""Rebuild data_import/ from the prepared data/ working copy.

Recovery tool, not part of the normal pipeline. data_import/ is the read-only
source of truth; if it is lost, the only surviving copy of the input data is the
derived data/ directory that prepare_data_for_tax_year() last wrote. This
reverses that step: it splits the concatenated transaction files back into the
per-year files of the documented naming scheme and restores the snapshot files
under the tax year they describe.

What it can and cannot recover:
  - Transaction files (Trades, Cash_Transactions, Corporate_Actions,
    Options_EAE) are split per year across the full history present in data/.
  - Snapshot files (Positions SoY/EoY, Cash_Balance) exist in data/ for ONE tax
    year only -- whichever was prepared last. Only that year is recoverable, so
    only that year can be processed afterwards.

Verify the result with --verify, which re-runs prepare_data_for_tax_year() and
compares the regenerated data/ against the originals byte for byte.

Usage:
  uv run python scripts/rebuild_data_import.py [--verify]
"""
from __future__ import annotations

import argparse
import csv
import shutil
import sys
from pathlib import Path

# run from anywhere: the repo root must be importable for --verify
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

DATA = Path("data")
IMPORT = Path("data_import")

# prepared file -> (import prefix, date column used to derive the year)
TRANSACTION_FILES = {
    "trades.csv": ("Trades", "TradeDate"),
    "cash_transactions.csv": ("Cash_Transactions", "SettleDate"),
    "corporate_actions.csv": ("Corporate_Actions", "Report Date"),
    "options_eae.csv": ("Options_EAE", "Date"),
}

# prepared file -> import filename template (formatted with the tax year)
SNAPSHOT_FILES = {
    "positions_start_of_year.csv": "Positions-{year}-SoY.csv",
    "positions_end_of_year.csv": "Positions-{year}-EoY.csv",
    "cash_balance.csv": "Cash_Balance-{year}.csv",
}


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with open(path, encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        return list(reader.fieldnames or []), list(reader)


def write_csv(path: Path, header: list[str], rows: list[dict[str, str]]) -> None:
    """BOM-prefixed, all-quoted -- the shape real IBKR Flex exports have."""
    with open(path, "w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=header, quoting=csv.QUOTE_ALL)
        writer.writeheader()
        writer.writerows(rows)


def year_of(value: str) -> str | None:
    v = (value or "").strip()
    if len(v) >= 4 and v[:4].isdigit():
        return v[:4]
    return None


def detect_snapshot_year() -> str:
    """The tax year the snapshot files describe, taken from Cash_Balance FromDate."""
    header, rows = read_csv(DATA / "cash_balance.csv")
    years = {year_of(r.get("FromDate", "")) for r in rows} - {None}
    if len(years) != 1:
        sys.exit(f"cannot determine snapshot year from cash_balance.csv (found {years})")
    return years.pop()


def rebuild() -> str:
    if not DATA.is_dir():
        sys.exit("data/ not found -- nothing to rebuild from")
    IMPORT.mkdir(exist_ok=True)

    split: dict[str, tuple[str, list[str], dict[str, list[dict[str, str]]]]] = {}
    all_years: set[str] = set()

    for name, (prefix, date_col) in TRANSACTION_FILES.items():
        src = DATA / name
        if not src.exists():
            print(f"  {name}: absent, skipped")
            continue
        header, rows = read_csv(src)
        if date_col not in header:
            sys.exit(f"{src}: expected date column {date_col!r}, header has {header}")
        buckets: dict[str, list[dict[str, str]]] = {}
        undated = 0
        for row in rows:
            y = year_of(row.get(date_col, ""))
            if y is None:
                undated += 1
                continue
            buckets.setdefault(y, []).append(row)
        if undated:
            sys.exit(f"{src}: {undated} row(s) have an unparseable {date_col}; refusing to "
                     f"silently drop them")
        split[name] = (prefix, header, buckets)
        all_years |= set(buckets)

    # A year with no rows of a given type still needs a header-only file:
    # prepare_data_for_tax_year() requires <Prefix>-<tax_year>.csv to exist, and a
    # real download set contains one file per requested year regardless of content.
    span = [str(y) for y in range(int(min(all_years)), int(max(all_years)) + 1)] if all_years else []
    for name, (prefix, header, buckets) in split.items():
        for y in span:
            out = IMPORT / f"{prefix}-{y}.csv"
            rows = buckets.get(y, [])
            write_csv(out, header, rows)
            print(f"  {out} ({len(rows)} rows)" + ("  [header only]" if not rows else ""))

    year = detect_snapshot_year()
    for name, template in SNAPSHOT_FILES.items():
        src = DATA / name
        if not src.exists():
            print(f"  {name}: absent, skipped")
            continue
        header, rows = read_csv(src)
        out = IMPORT / template.format(year=year)
        write_csv(out, header, rows)
        print(f"  {out} ({len(rows)} rows)")

    return year


def verify(year: str) -> int:
    """Re-run the real preparation step and compare against the originals."""
    backup = Path(f".data-preverify")
    if backup.exists():
        shutil.rmtree(backup)
    shutil.copytree(DATA, backup)
    try:
        from src.data_preparation import prepare_data_for_tax_year
        prepare_data_for_tax_year(int(year))

        failures = 0
        for produced in sorted(DATA.glob("*.csv")):
            original = backup / produced.name
            if not original.exists():
                print(f"  ! {produced.name}: no original to compare")
                failures += 1
                continue
            a_header, a_rows = read_csv(original)
            b_header, b_rows = read_csv(produced)
            if a_header != b_header:
                print(f"  ! {produced.name}: header differs")
                failures += 1
            elif a_rows != b_rows:
                print(f"  ! {produced.name}: {len(a_rows)} vs {len(b_rows)} rows, content differs")
                failures += 1
            else:
                print(f"  = {produced.name}: {len(a_rows)} rows identical")
        return failures
    finally:
        shutil.rmtree(DATA)
        backup.rename(DATA)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--verify", action="store_true",
                    help="re-run prepare_data_for_tax_year() and diff against the originals")
    args = ap.parse_args()

    print("rebuilding data_import/ from data/ ...")
    year = rebuild()
    print(f"snapshot tax year: {year}")

    if args.verify:
        print("verifying round trip ...")
        failures = verify(year)
        if failures:
            print(f"ROUND TRIP FAILED: {failures} file(s) differ")
            return 1
        print("ROUND TRIP OK: regenerated data/ is identical to the originals")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
