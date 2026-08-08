# src/parsers/csv_reader.py
"""One reader behind all six CSV parsers.

**A row that cannot be parsed stops the run.** It is not printed and dropped.

Until August 2026 each of the six parsers carried its own copy of this loop, and
every copy did the opposite: a `ValidationError` was printed to stdout and the
row was skipped, the run continuing on whatever survived. Nothing anywhere
compared a file's row count against `len(raw_*)`, so the loss was unobservable
-- the orchestrator's "Loaded N raw ... records" counts survivors and has
nothing to compare against.

The consequence was uneven, and worst where nobody would look. A dropped *trade*
usually surfaces: the SoY -> EoY reconciliation is fatal and compares net
quantity per asset, so a missing trade shows up as a mismatch. A dropped *cash
transaction* does not. A dividend, an interest credit or a withholding entry
touches no share quantity, the securities reconciliation stays green, and the
income is simply not declared -- a silently understated figure, which is the one
failure CLAUDE.md's fail-fast rule exists to prevent.

Three narrower defects went with it, each removed here rather than narrowed:

- **A bare `except Exception` around the model constructor.** It caught
  programming errors as well as bad data and printed them as if they were rows
  the broker had got wrong. Only `ValidationError` is caught now; anything else
  is a defect in this repository and propagates.
- **A file-level `except Exception` that swallowed `validate_csv_columns`.**
  That helper raises `ValueError` when the export's headers drift out of step
  with `column_validator.py`, which is the whole reason it exists -- and it was
  caught one frame later, printed, and turned into an empty record list.
  Measured 2026-08-08 before the change: renaming `Quantity` to `Qty` in a
  Trades header returned 0 records and raised nothing. An empty trades list
  against a non-empty positions file would trip reconciliation; an empty *cash
  transactions* list would not.
- **`except FileNotFoundError` returning `[]`.** `data_preparation.py` already
  raises for a missing required file before any parser is reached, so this was a
  second, weaker layer that could only disagree with the first. One place
  decides.

Failures are collected across the whole file and raised together, so one run
identifies the whole problem rather than the first row of it -- the same shape
`DomainEventFactory` uses for its `data_errors` list.
"""
import csv
from typing import Any, Dict, List, Sequence, Type, TypeVar

from pydantic import BaseModel, ValidationError

from src.domain.exceptions import DataIntegrityError

from .column_validator import validate_csv_columns

M = TypeVar("M", bound=BaseModel)

# Tried in order to name the offending row in a way the reader can find in the
# export. Purely for the error message; absence of all of them is fine, the line
# number always stands.
_ROW_LABEL_COLUMNS = ("TransactionID", "ActionID", "Symbol", "Description")


def _label(row: Dict[str, Any]) -> str:
    for column in _ROW_LABEL_COLUMNS:
        value = (row.get(column) or "").strip() if isinstance(row.get(column), str) else None
        if value:
            return f" [{column}={value}]"
    return ""


def _describe(row: Dict[str, Any], error: ValidationError) -> str:
    """The columns that failed and what they contained -- not the whole row.

    The raw value is what a reader needs to act, and it is the one part of the
    row pydantic's own message leaves out.
    """
    parts = []
    for detail in error.errors():
        location = detail.get("loc") or ()
        column = str(location[0]) if location else "?"
        raw = row.get(column)
        parts.append(f"{column}={raw!r}: {detail.get('msg')}")
    return "; ".join(parts)


def parse_records(file_path: str,
                  model: Type[M],
                  expected_columns: Sequence[str],
                  file_description: str,
                  *,
                  encoding: str = "utf-8-sig",
                  allow_extra: bool = False) -> List[M]:
    """Read `file_path` into `model` instances, or raise naming every bad row.

    Raises `FileNotFoundError` if the file is absent, `ValueError` if its header
    does not match `expected_columns`, and `DataIntegrityError` listing every row
    that failed validation. None of the three is caught here: a parser that keeps
    going past one of them produces a declaration from an input it could not read.
    """
    records: List[M] = []
    failures: List[str] = []

    with open(file_path, mode="r", encoding=encoding) as csvfile:
        reader = csv.DictReader(csvfile)
        validate_csv_columns(reader.fieldnames or [], expected_columns,
                             f"{file_description} ({file_path})", allow_extra=allow_extra)
        # start=2: line 1 is the header, so this is the line number in the file.
        for line_number, row in enumerate(reader, start=2):
            if None in row:
                # DictReader files a row's surplus values under the None key. Passing
                # that to a model is a TypeError about keyword names, which says
                # nothing about the CSV; report the ragged row instead.
                failures.append(
                    f"line {line_number}{_label(row)}: row has more fields than the "
                    f"header ({len(expected_columns)} columns expected)")
                continue
            try:
                records.append(model(**row))
            except ValidationError as e:
                failures.append(f"line {line_number}{_label(row)}: {_describe(row, e)}")

    if failures:
        raise DataIntegrityError(
            f"{len(failures)} row(s) in {file_description} ({file_path}) could not be "
            f"parsed. Every row of an export is an input to a declared figure, so the "
            f"run stops rather than continuing on the rows that happened to survive:\n  "
            + "\n  ".join(failures))

    return records
