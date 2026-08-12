"""
IBKR Flex Web Service Downloader

Downloads CSV data from IBKR's Flex Web Service API with retry logic,
caching, and historical multi-year fetch support.

Two-step API flow:
1. SendRequest -> get reference code
2. Poll GetStatement with reference code -> get CSV content
"""

import csv
import hashlib
import io
import logging
import os
import time
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path
from typing import Optional

import requests

logger = logging.getLogger(__name__)

BASE_URL = "https://ndcdyn.interactivebrokers.com/AccountManagement/FlexWebService"

# Query types that use TransactionID for deduplication during merge
_TRANSACTION_ID_TYPES = {"trades", "cash_transactions"}

# IBKR Flex Web Service V3 error codes (official list from ibkrguides.com)
# "retry" = retryable with suggested delay, "fatal" = raise immediately, "empty" = no data
_ERROR_HANDLING = {
    1001: ("retry", 5, "Statement could not be generated at this time"),
    1003: ("empty", "Statement is not available"),
    1004: ("retry", 5, "Statement is incomplete at this time"),
    1005: ("retry", 5, "Settlement data is not ready at this time"),
    1006: ("retry", 5, "FIFO P/L data is not ready at this time"),
    1007: ("retry", 5, "MTM P/L data is not ready at this time"),
    1008: ("retry", 5, "MTM and FIFO P/L data is not ready at this time"),
    1009: ("retry", 5, "Server is under heavy load"),
    1010: ("fatal", "Legacy Flex Queries are no longer supported"),
    1011: ("fatal", "Service account is inactive"),
    1012: ("fatal", "Token has expired"),
    1013: ("fatal", "IP restriction"),
    1014: ("fatal", "Query is invalid"),
    1015: ("fatal", "Token is invalid"),
    1016: ("fatal", "Account is invalid"),
    1017: ("fatal", "Reference code is invalid"),
    1018: ("retry", 10, "Too many requests from this token"),
    1019: ("retry", 5, "Statement generation in progress"),
    1020: ("fatal", "Invalid request or unable to validate request"),
    1021: ("retry", 10, "Statement could not be retrieved at this time"),
}

MAX_RETRIES = 10
MAX_BACKOFF_SECONDS = 120


class FlexDownloadError(Exception):
    """Raised for fatal Flex Web Service errors."""
    pass


class NoDataError(Exception):
    """Raised when IBKR returns 'Statement is not available' (error 1003)."""
    pass


def resolve_token() -> str:
    """
    Resolve IBKR Flex token from environment variable or file.

    Resolution order:
    1. IBKR_FLEX_TOKEN environment variable
    2. ~/.ibkr_flex_token file (first line, stripped)

    Returns:
        Token string

    Raises:
        FlexDownloadError: If no token found
    """
    # Try environment variable first
    token = os.environ.get("IBKR_FLEX_TOKEN", "").strip()
    if token:
        logger.info("Using IBKR token from IBKR_FLEX_TOKEN environment variable.")
        return token

    # Try file locations
    token_paths = [
        Path(os.path.expanduser("~/.ibkr_flex_token")),
        Path("ibkr_token"),  # project-local fallback
    ]
    for token_path in token_paths:
        if token_path.exists():
            token = token_path.read_text().strip().splitlines()[0].strip()
            if token:
                logger.info("Using IBKR token from %s.", token_path)
                return token

    raise FlexDownloadError(
        "IBKR Flex token not found. Set the IBKR_FLEX_TOKEN environment variable, "
        "create ~/.ibkr_flex_token, or place an ibkr_token file in the project root."
    )


def _parse_xml_response(xml_text: str) -> tuple[str, Optional[str], Optional[int], Optional[str]]:
    """
    Parse an IBKR Flex Web Service XML response.

    Returns:
        (status, reference_code_or_none, error_code_or_none, error_message_or_none)
    """
    root = ET.fromstring(xml_text)

    status_el = root.find("Status")
    if status_el is None:
        raise FlexDownloadError(f"Invalid XML response: no Status element.\n{xml_text[:500]}")

    if status_el.text == "Success":
        ref_code_el = root.find("ReferenceCode")
        ref_code = ref_code_el.text if ref_code_el is not None else None
        return "Success", ref_code, None, None

    error_code_el = root.find("ErrorCode")
    error_msg_el = root.find("ErrorMessage")
    error_code = int(error_code_el.text) if error_code_el is not None and error_code_el.text.isdigit() else None
    error_msg = error_msg_el.text if error_msg_el is not None else "Unknown error"

    return "Fail", None, error_code, error_msg


def _handle_error(error_code: Optional[int], error_msg: str, context: str) -> float:
    """
    Handle an IBKR error code. Returns retry delay if retryable.

    Raises:
        FlexDownloadError: For fatal errors
        NoDataError: For error code 1016 (no data)
    """
    if error_code and error_code in _ERROR_HANDLING:
        entry = _ERROR_HANDLING[error_code]
        action = entry[0]

        if action == "fatal":
            raise FlexDownloadError(f"{context}: Error {error_code} - {entry[1]} ({error_msg})")
        elif action == "empty":
            raise NoDataError(f"No data for date range (error {error_code})")
        elif action == "retry":
            delay = entry[1]
            description = entry[2]
            logger.warning("%s: Error %d - %s. Retrying in %ds...", context, error_code, description, delay)
            return float(delay)

    # Unknown error code - treat as fatal
    raise FlexDownloadError(f"{context}: Unknown error {error_code} - {error_msg}")


def fetch_flex_statement(
    token: str,
    query_id: int,
    from_date: date,
    to_date: date,
) -> Optional[str]:
    """
    Fetch a single Flex Query statement as CSV content.

    Two-step flow:
    1. SendRequest with token + query_id + date range -> reference code
    2. Poll GetStatement with reference code -> CSV content

    Args:
        token: IBKR Flex Web Service token
        query_id: Flex Query ID
        from_date: Start date
        to_date: End date

    Returns:
        CSV content string, or None if no data for date range

    Raises:
        FlexDownloadError: For fatal API errors or timeout
    """
    fd_str = from_date.strftime("%Y%m%d")
    td_str = to_date.strftime("%Y%m%d")

    # Step 1: SendRequest
    ref_code = None
    for attempt in range(MAX_RETRIES):
        url = f"{BASE_URL}/SendRequest?t={token}&q={query_id}&v=3&fd={fd_str}&td={td_str}"
        logger.info("SendRequest for query %d (%s - %s), attempt %d...", query_id, fd_str, td_str, attempt + 1)

        try:
            resp = requests.get(url, timeout=60)
            resp.raise_for_status()
        except requests.RequestException as e:
            if attempt < MAX_RETRIES - 1:
                delay = min(5 * (2 ** attempt), MAX_BACKOFF_SECONDS)
                logger.warning("HTTP error during SendRequest: %s. Retrying in %ds...", e, delay)
                time.sleep(delay)
                continue
            raise FlexDownloadError(f"SendRequest failed after {MAX_RETRIES} attempts: {e}")

        status, ref_code_val, error_code, error_msg = _parse_xml_response(resp.text)

        if status == "Success" and ref_code_val:
            ref_code = ref_code_val
            logger.info("Got reference code: %s", ref_code)
            break

        try:
            delay = _handle_error(error_code, error_msg or "", "SendRequest")
            time.sleep(delay)
        except NoDataError:
            return None

    if ref_code is None:
        raise FlexDownloadError(f"SendRequest failed to get reference code after {MAX_RETRIES} attempts")

    # Step 2: Poll GetStatement
    for attempt in range(MAX_RETRIES):
        # Initial wait before first poll
        delay = min(5 * (1 + attempt), MAX_BACKOFF_SECONDS)
        logger.info("Waiting %ds before polling GetStatement (attempt %d)...", delay, attempt + 1)
        time.sleep(delay)

        url = f"{BASE_URL}/GetStatement?t={token}&q={ref_code}&v=3"

        try:
            resp = requests.get(url, timeout=120)
            resp.raise_for_status()
        except requests.RequestException as e:
            if attempt < MAX_RETRIES - 1:
                logger.warning("HTTP error during GetStatement: %s. Retrying...", e)
                continue
            raise FlexDownloadError(f"GetStatement failed after {MAX_RETRIES} attempts: {e}")

        content = resp.text

        # If response is XML, it's either an error or "still generating"
        if content.strip().startswith("<"):
            status, _, error_code, error_msg = _parse_xml_response(content)

            if status == "Success":
                # Shouldn't happen for GetStatement but handle gracefully
                continue

            try:
                _handle_error(error_code, error_msg or "", "GetStatement")
                # If _handle_error returns (retryable), continue polling
                continue
            except NoDataError:
                return None

        # Got CSV content
        logger.info("Received CSV statement (%d bytes).", len(content))
        return content

    raise FlexDownloadError(f"GetStatement timed out after {MAX_RETRIES} attempts (ref: {ref_code})")


def _cache_path(cache_dir: str, query_type: str, from_date: date, to_date: date) -> Path:
    """Build the cache file path for a query type and date range."""
    fd_str = from_date.strftime("%Y%m%d")
    td_str = to_date.strftime("%Y%m%d")
    return Path(cache_dir) / f"{query_type}_{fd_str}_{td_str}.csv"


def download_query_type(
    token: str,
    query_type: str,
    query_id: int,
    from_date: date,
    to_date: date,
    cache_dir: str,
    force: bool = False,
) -> Optional[Path]:
    """
    Download a single query type for a date range, with caching.

    Args:
        token: IBKR Flex token
        query_type: Type name (e.g., "trades", "cash_transactions")
        query_id: Flex Query ID
        from_date: Start date
        to_date: End date
        cache_dir: Cache directory path
        force: If True, re-download even if cached

    Returns:
        Path to cached CSV file, or None if no data
    """
    cached = _cache_path(cache_dir, query_type, from_date, to_date)

    if cached.exists() and not force:
        logger.info("Cache hit for %s (%s - %s): %s", query_type, from_date, to_date, cached)
        return cached

    logger.info("Downloading %s for %s - %s...", query_type, from_date, to_date)
    csv_content = fetch_flex_statement(token, query_id, from_date, to_date)

    if csv_content is None:
        logger.info("No data returned for %s (%s - %s).", query_type, from_date, to_date)
        return None

    cached.parent.mkdir(parents=True, exist_ok=True)
    cached.write_text(csv_content, encoding="utf-8-sig")
    logger.info("Cached %s to %s (%d bytes).", query_type, cached, len(csv_content))
    return cached


def download_historical(
    token: str,
    query_type: str,
    query_id: int,
    tax_year: int,
    cache_dir: str,
    force: bool = False,
    max_years_back: int = 10,
) -> list[Path]:
    """
    Fetch current year + historical years backwards until no data.

    IBKR limits queries to 365 days, so each year is one request.
    Stops when IBKR returns no data (error 1016) or max_years_back reached.

    Returns:
        List of paths to cached CSV files (oldest first)
    """
    paths = []

    for offset in range(max_years_back + 1):
        year = tax_year - offset
        from_date = date(year, 1, 1)
        to_date = date(year, 12, 31)

        try:
            path = download_query_type(token, query_type, query_id, from_date, to_date, cache_dir, force)
        except FlexDownloadError as e:
            logger.warning("Stopping historical fetch for %s at year %d: %s", query_type, year, e)
            break

        if path is None:
            if offset == 0:
                logger.warning("No data for %s in %d (current tax year).", query_type, year)
            else:
                logger.info("No data for %s in %d. Historical fetch reached boundary.", query_type, year)
                if offset == 1:
                    print(f"  Note: {query_type} only available for {tax_year}. "
                          f"To fetch older years, set Flex Query period to 'Custom Date Range' in IBKR portal.")
            break

        paths.append(path)

    # Return oldest first
    paths.reverse()
    return paths


def _merge_csvs(paths: list[Path], query_type: str) -> str:
    """
    Merge multiple CSV files, deduplicating rows.

    For trades/cash_transactions: deduplicate by TransactionID column.
    For others: deduplicate by full row hash.

    Returns:
        Merged CSV content as string
    """
    if not paths:
        return ""

    use_transaction_id = query_type in _TRANSACTION_ID_TYPES
    header = None
    seen = set()
    rows = []
    transaction_id_col = None

    for path in paths:
        content = path.read_text(encoding="utf-8-sig")
        reader = csv.reader(io.StringIO(content))

        for i, row in enumerate(reader):
            if i == 0:
                if header is None:
                    header = row
                    if use_transaction_id:
                        try:
                            transaction_id_col = row.index("TransactionID")
                        except ValueError:
                            logger.warning("TransactionID column not found in %s. Falling back to row hash.", query_type)
                            use_transaction_id = False
                # Skip header rows in subsequent files
                continue

            if use_transaction_id and transaction_id_col is not None:
                key = row[transaction_id_col]
            else:
                key = hashlib.md5(",".join(row).encode()).hexdigest()

            if key not in seen:
                seen.add(key)
                rows.append(row)

    if header is None:
        return ""

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(header)
    writer.writerows(rows)
    return output.getvalue()


def _year_date_range(year: int) -> tuple[date, date]:
    """Full date range for a calendar year."""
    return date(year, 1, 1), date(year, 12, 31)


def download_and_merge(
    tax_year: int,
    query_ids: dict[str, Optional[int]],
    cache_dir: str,
    force: bool = False,
) -> dict[str, Path]:
    """
    Download all query types for a single tax year and write CSVs
    to data_import/ using the standard naming scheme.

    Only downloads data for the specified tax year. Historical data
    must be downloaded manually via the IBKR portal.

    Args:
        tax_year: The tax year to download
        query_ids: Mapping of query type -> Flex Query ID
        cache_dir: Directory for cached downloads
        force: Re-download even if cached

    Returns:
        Dict mapping file description to final file path
    """
    import_dir = Path("data_import")
    import_dir.mkdir(parents=True, exist_ok=True)

    token = resolve_token()
    result_paths = {}

    # Map query types to their import file prefix
    prefix_mapping = {
        "trades": "Trades",
        "cash_transactions": "Cash_Transactions",
        "corporate_actions": "Corporate_Actions",
        "cash_balance": "Cash_Balance",
        "options_eae": "Options_EAE",
        # A query type missing here is not a query type that is skipped loudly: the loop
        # below reaches `prefix_mapping.get(query_type)`, finds None, and `continue`s
        # without a word. Transfers was absent while its query ID was configurable, so a
        # `--download` run silently produced no Transfers file for the year -- which the
        # engine then reads as a year it cannot see a move in.
        "transfers": "Transfers",
    }

    # Positions are special: SOY and EOY are separate files from the same query
    positions_query_id = query_ids.get("positions")

    for query_type, query_id in query_ids.items():
        if query_id is None:
            logger.info("Skipping %s (no query ID configured).", query_type)
            continue

        if query_type == "positions":
            continue

        prefix = prefix_mapping.get(query_type)
        if prefix is None:
            # Loud, because the silent version of this is what let a whole report go
            # missing: a query type the user has configured an ID for is a query type
            # they expect to be downloaded, and skipping it without a word produces a
            # `data_import/` that looks complete and is not.
            raise FlexDownloadError(
                f"Query type {query_type!r} has a Flex Query ID configured but no "
                f"filename prefix, so the download would be skipped and no file would "
                f"appear in data_import/. Add it to prefix_mapping in this function "
                f"(known: {', '.join(sorted(prefix_mapping))}, plus 'positions').")

        print(f"Downloading {query_type} for {tax_year}...")
        from_date, to_date = _year_date_range(tax_year)
        path = download_query_type(token, query_type, query_id, from_date, to_date, cache_dir, force)

        if path is None:
            logger.warning("No data downloaded for %s.", query_type)
            continue

        out = import_dir / f"{prefix}-{tax_year}.csv"
        if out.exists():
            logger.info("Skipping %s (already exists in %s).", out.name, import_dir)
            print(f"  Skipping {out.name} (already exists)")
        else:
            content = path.read_text(encoding="utf-8-sig")
            out.write_text(content, encoding="utf-8-sig")
            print(f"  -> {out} ({len(content)} bytes)")
        result_paths[query_type] = out

    # Handle positions (SOY and EOY)
    if positions_query_id is not None:
        print(f"Downloading positions (start of year {tax_year})...")
        soy_date = date(tax_year, 1, 1)
        soy_path = download_query_type(
            token, f"positions_soy_{tax_year}", positions_query_id,
            soy_date, soy_date, cache_dir, force
        )
        if soy_path:
            soy_out = import_dir / f"Positions-{tax_year}-SoY.csv"
            if soy_out.exists():
                logger.info("Skipping %s (already exists).", soy_out.name)
                print(f"  Skipping {soy_out.name} (already exists)")
            else:
                content = soy_path.read_text(encoding="utf-8-sig")
                soy_out.write_text(content, encoding="utf-8-sig")
                print(f"  -> {soy_out}")
            result_paths["positions_soy"] = soy_out

        print(f"Downloading positions (end of year {tax_year})...")
        eoy_date = date(tax_year, 12, 31)
        eoy_path = download_query_type(
            token, f"positions_eoy_{tax_year}", positions_query_id,
            eoy_date, eoy_date, cache_dir, force
        )
        if eoy_path:
            eoy_out = import_dir / f"Positions-{tax_year}-EoY.csv"
            if eoy_out.exists():
                logger.info("Skipping %s (already exists).", eoy_out.name)
                print(f"  Skipping {eoy_out.name} (already exists)")
            else:
                content = eoy_path.read_text(encoding="utf-8-sig")
                eoy_out.write_text(content, encoding="utf-8-sig")
                print(f"  -> {eoy_out}")
            result_paths["positions_eoy"] = eoy_out
    else:
        logger.info("Skipping positions (no query ID configured).")

    print(f"\nDownload complete. {len(result_paths)} file(s) written to {import_dir}/.")
    return result_paths
