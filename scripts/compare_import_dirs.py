"""
Compare a freshly fetched import directory against the one in use.

Written for a clean-room check of the Client Portal downloader: fetch every
report into a scratch directory, then ask what differs from the files the engine
is actually running on. Byte comparison is useless here — this project writes
UTF-8 with a BOM and LF, while a hand export carries CRLF — so both sides are
normalised before comparing, and encoding-only differences are reported as
"same content".

Row order is not normalised. A report whose rows come back in a different order
is a real finding: the engine's replay ordering is load-bearing.

    uv run python scripts/compare_import_dirs.py private/fetch_all data_import
"""

import csv
import io
import sys
from pathlib import Path


def _normalise(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig").replace("\r\n", "\n").rstrip("\n")


def _rows(text: str) -> list[list[str]]:
    return list(csv.reader(io.StringIO(text)))


def _describe(fresh: Path, current: Path) -> tuple[str, str]:
    """Return (verdict, detail) for one file present on both sides."""
    a, b = _normalise(fresh), _normalise(current)
    if a == b:
        same_bytes = fresh.read_bytes() == current.read_bytes()
        return ("identical", "" if same_bytes else "content same; BOM/line endings differ")

    rows_a, rows_b = _rows(a), _rows(b)
    if rows_a and rows_b and rows_a[0] != rows_b[0]:
        return ("HEADER DIFFERS", f"{len(rows_a[0])} columns vs {len(rows_b[0])}")

    body_a, body_b = rows_a[1:], rows_b[1:]
    if sorted(body_a) == sorted(body_b):
        return ("row order differs", f"{len(body_a)} rows, same set")

    only_fresh = [r for r in body_a if r not in body_b]
    only_current = [r for r in body_b if r not in body_a]
    return ("CONTENT DIFFERS",
            f"{len(body_a)} vs {len(body_b)} rows; "
            f"+{len(only_fresh)} only in fresh, +{len(only_current)} only in current")


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__)
        return 2
    fresh_dir, current_dir = Path(argv[1]), Path(argv[2])
    if not fresh_dir.is_dir():
        print(f"No such directory: {fresh_dir}")
        return 2

    names = sorted({p.name for p in fresh_dir.glob("*.csv")}
                   | {p.name for p in current_dir.glob("*.csv")})
    counts: dict[str, int] = {}
    for name in names:
        fresh, current = fresh_dir / name, current_dir / name
        if not fresh.exists():
            verdict, detail = "missing from fresh", ""
        elif not current.exists():
            verdict, detail = "new in fresh", f"{fresh.stat().st_size} bytes"
        else:
            verdict, detail = _describe(fresh, current)
        counts[verdict] = counts.get(verdict, 0) + 1
        flag = " " if verdict in ("identical", "row order differs") else "!"
        print(f" {flag} {name:32} {verdict}{'  — ' + detail if detail else ''}")

    print()
    for verdict, n in sorted(counts.items(), key=lambda kv: -kv[1]):
        print(f"  {n:3}  {verdict}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
