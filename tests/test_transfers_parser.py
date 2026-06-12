"""Parser for IBKR Transfers (Depotübertragung) exports: keep position-bearing rows, drop the
paired 'ST' settlement-marker rows; both INTERNAL legs (OUT/IN) are retained."""
from decimal import Decimal

from src.parsers.transfers_parser import parse_transfers_csv

HEADER = (
    '"ClientAccountID","AccountAlias","CurrencyPrimary","AssetClass","Symbol","Description",'
    '"Conid","ISIN","UnderlyingConid","UnderlyingSymbol","Multiplier","ReportDate","Date",'
    '"DateTime","SettleDate","Type","Direction","TransferAccount","TransferAccountName",'
    '"Quantity","TransferPrice","PositionAmount","PositionAmountInBase","PnlAmount",'
    '"PnlAmountInBase","CashTransfer","Code","ClientReference","TransactionID","SerialNumber",'
    '"DeliveryType","CommodityType"'
)


def _row(account, isin, direction, transfer_acct, qty, tid, asset_class="STK", settle="20230620", code="0"):
    return (
        f'"{account}","","EUR","{asset_class}","SYM","desc","123","{isin}","","","1","20230619",'
        f'"20230619","20230619;08","{settle}","INTERNAL","{direction}","{transfer_acct}","",'
        f'"{qty}","0","-5430","-5430","0","0","0","{code}","","{tid}","","",""'
    )


def _write(tmp_path, rows):
    p = tmp_path / "Transfers-2023.csv"
    p.write_text("\n".join([HEADER] + rows) + "\n", encoding="utf-8-sig")
    return str(p)


def test_st_marker_rows_are_dropped(tmp_path):
    rows = [
        _row("U1", "DE000LEG1110", "OUT", "U2", "-100", "1944630875"),              # real OUT
        _row("U1", "DE000LEG1110", "OUT", "U2", "100", "", settle="", code="ST"),   # ST marker (no TID)
        _row("U2", "DE000LEG1110", "IN", "U1", "100", "1944630875"),                # real IN
        _row("U2", "DE000LEG1110", "IN", "U1", "100", "", settle="", code="ST"),    # ST marker
    ]
    recs = parse_transfers_csv(_write(tmp_path, rows))
    assert len(recs) == 2                                  # ST markers dropped
    assert {r.direction for r in recs} == {"OUT", "IN"}
    out = next(r for r in recs if r.direction == "OUT")
    assert out.client_account_id == "U1" and out.transfer_account == "U2"
    assert out.isin == "DE000LEG1110" and out.quantity == Decimal("-100")
    assert out.transfer_type == "INTERNAL" and out.transaction_id == "1944630875"


def test_cash_transfer_row_parsed(tmp_path):
    recs = parse_transfers_csv(_write(tmp_path, [_row("U1", "", "OUT", "U2", "-500", "999", asset_class="CASH")]))
    assert len(recs) == 1 and recs[0].asset_class == "CASH"


def test_duplicate_header_row_is_skipped(tmp_path):
    """IBKR exports duplicate the header; the repeated line must not become a record."""
    rows = [HEADER, _row("U1", "DE000LEG1110", "OUT", "U2", "-100", "1944630875")]
    recs = parse_transfers_csv(_write(tmp_path, rows))
    assert len(recs) == 1 and recs[0].direction == "OUT"


def test_missing_file_returns_empty():
    assert parse_transfers_csv("/no/such/Transfers-2099.csv") == []
