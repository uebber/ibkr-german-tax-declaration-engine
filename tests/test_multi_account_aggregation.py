"""
Multi-account aggregation in position/cash-balance processing.

IBKR Flex exports emit one row **per account** for cash balances and security positions.
Assets are resolved account-agnostically (by currency / ISIN / Conid — German tax aggregates
across a person's accounts), so when the same currency or security is held in more than one
account the per-account rows must be **summed**, not overwritten.

Two bugs this guards against (both: a per-account row assigned with ``=`` onto a shared asset):
  A. Cash balances (``_process_cash_balance_positions``) — ACTIVE in real data: every foreign
     currency (CAD/USD/SGD/CHF) appears in two account rows; only the last survived.
  B. Security SoY/EoY positions (``process_positions``) — latent: any ISIN held in 2 accounts.

Requirement (data semantics, not tax law): quantities, cost basis and position values sum
across accounts; per-unit mark price is identical and is taken as-is; EUR (base) and
BASE_SUMMARY rows are not tracked as foreign-currency cash.
"""
import logging
from decimal import Decimal
from unittest.mock import MagicMock

from src.identification.asset_resolver import AssetResolver
from src.classification.asset_classifier import AssetClassifier
from src.parsers.parsing_orchestrator import ParsingOrchestrator
from src.parsers.raw_models import RawCashBalanceRecord, RawPositionRecord
from src.domain.enums import AssetCategory


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _orchestrator():
    classifier = MagicMock(spec=AssetClassifier)

    def _prelim(ibkr_asset_class=None, ibkr_sub_category=None, description="", symbol=None):
        if (ibkr_asset_class or "").upper() == "CASH":
            return (AssetCategory.CASH_BALANCE, None)
        return (AssetCategory.STOCK, None)

    classifier.preliminary_classify.side_effect = _prelim
    resolver = AssetResolver(classifier)
    return ParsingOrchestrator(resolver, classifier, interactive_classification=False)


def _cash(acct, ccy, soy, eoy):
    return RawCashBalanceRecord(**{
        "ClientAccountID": acct, "CurrencyPrimary": ccy,
        "FromDate": "20250101", "ToDate": "20251231",
        "StartingCash": Decimal(soy), "EndingCash": Decimal(eoy),
    })


def _pos(isin, qty, cost, value, price="100", ccy="USD", account="U10000000"):
    return RawPositionRecord(**{
        "ClientAccountID": account,
        "CurrencyPrimary": ccy, "AssetClass": "STK", "Symbol": isin, "Description": isin,
        "ISIN": isin, "Conid": isin, "Quantity": Decimal(qty), "MarkPrice": Decimal(price),
        "PositionValue": Decimal(value), "CostBasisMoney": Decimal(cost),
    })


def _find(resolver, *, currency=None, category=None, isin=None):
    for asset in resolver.assets_by_internal_id.values():
        if category is not None and asset.asset_category != category:
            continue
        if currency is not None and (asset.currency or "").upper() != currency.upper():
            continue
        if isin is not None and getattr(asset, "ibkr_isin", None) != isin:
            continue
        return asset
    return None


# ---------------------------------------------------------------------------
# A. Cash balances summed across accounts
# ---------------------------------------------------------------------------

class TestCashBalanceMultiAccount:

    def test_usd_summed_across_two_accounts(self):
        """Two accounts hold USD: +4486.46 and -121.24 -> summed SoY 4365.22."""
        orch = _orchestrator()
        orch.raw_cash_balances = [
            _cash("U10000001", "USD", "-121.24", "0"),
            _cash("U10000002", "USD", "4486.46", "-0.01"),
        ]
        orch._process_cash_balance_positions(tax_year=2025)

        usd = _find(orch.asset_resolver, currency="USD", category=AssetCategory.CASH_BALANCE)
        assert usd is not None
        assert usd.soy_quantity == Decimal("4365.22")
        assert usd.eoy_quantity == Decimal("-0.01")  # 0 + (-0.01)

    def test_each_currency_summed_independently(self):
        orch = _orchestrator()
        orch.raw_cash_balances = [
            _cash("A", "CAD", "100", "10"), _cash("B", "CAD", "25", "5"),
            _cash("A", "SGD", "300", "0"), _cash("B", "SGD", "-50", "0"),
        ]
        orch._process_cash_balance_positions(tax_year=2025)
        cad = _find(orch.asset_resolver, currency="CAD", category=AssetCategory.CASH_BALANCE)
        sgd = _find(orch.asset_resolver, currency="SGD", category=AssetCategory.CASH_BALANCE)
        assert cad.soy_quantity == Decimal("125")
        assert cad.eoy_quantity == Decimal("15")
        assert sgd.soy_quantity == Decimal("250")

    def test_eur_and_base_summary_not_tracked(self):
        orch = _orchestrator()
        orch.raw_cash_balances = [
            _cash("A", "EUR", "500", "500"), _cash("B", "EUR", "200", "200"),
            _cash("A", "BASE_SUMMARY", "9999", "9999"),
        ]
        orch._process_cash_balance_positions(tax_year=2025)
        assert _find(orch.asset_resolver, currency="EUR", category=AssetCategory.CASH_BALANCE) is None
        assert _find(orch.asset_resolver, currency="BASE_SUMMARY", category=AssetCategory.CASH_BALANCE) is None

    def test_tiny_threshold_applies_to_summed_balance(self):
        """Two sub-threshold rows of the same currency that *sum* above the threshold are kept."""
        orch = _orchestrator()
        orch.raw_cash_balances = [
            _cash("A", "USD", "0.006", "0"), _cash("B", "USD", "0.006", "0"),  # sum 0.012 >= 0.01
            _cash("A", "CHF", "0.004", "0"), _cash("B", "CHF", "0.004", "0"),  # sum 0.008 < 0.01
        ]
        orch._process_cash_balance_positions(tax_year=2025)
        usd = _find(orch.asset_resolver, currency="USD", category=AssetCategory.CASH_BALANCE)
        chf = _find(orch.asset_resolver, currency="CHF", category=AssetCategory.CASH_BALANCE)
        assert usd is not None and usd.soy_quantity == Decimal("0.012")
        assert chf is None  # summed balance below threshold -> not tracked

    def test_single_account_unchanged(self):
        orch = _orchestrator()
        orch.raw_cash_balances = [_cash("A", "USD", "1000", "900")]
        orch._process_cash_balance_positions(tax_year=2025)
        usd = _find(orch.asset_resolver, currency="USD", category=AssetCategory.CASH_BALANCE)
        assert usd.soy_quantity == Decimal("1000")
        assert usd.eoy_quantity == Decimal("900")

    def test_net_zero_but_actively_held_currency_is_kept(self):
        """+5000 / -5000 across accounts nets to 0 but is actively held — the currency asset
        (and thus its FIFO ledger) must still be created so intra-year FX is tracked."""
        orch = _orchestrator()
        orch.raw_cash_balances = [
            _cash("A", "USD", "5000", "0"),
            _cash("B", "USD", "-5000", "0"),
        ]
        orch._process_cash_balance_positions(tax_year=2025)
        usd = _find(orch.asset_resolver, currency="USD", category=AssetCategory.CASH_BALANCE)
        assert usd is not None  # not dropped despite a ~0 net balance
        assert usd.soy_quantity == Decimal("0")


# ---------------------------------------------------------------------------
# B. Security positions summed across accounts
# ---------------------------------------------------------------------------

class TestSecurityPositionMultiAccount:

    def test_soy_quantity_cost_value_summed(self):
        orch = _orchestrator()
        orch.raw_positions_start = [
            _pos("US0000000001", qty="100", cost="600", value="1000", price="10"),
            _pos("US0000000001", qty="50", cost="300", value="500", price="10"),
        ]
        orch.process_positions()
        asset = _find(orch.asset_resolver, isin="US0000000001")
        assert asset.soy_quantity == Decimal("150")
        assert asset.soy_cost_basis_amount == Decimal("900")
        assert asset.soy_position_value == Decimal("1500")
        assert asset.soy_market_price == Decimal("10")  # per-unit price not summed

    def test_eoy_quantity_value_summed(self):
        orch = _orchestrator()
        orch.raw_positions_end = [
            _pos("US0000000002", qty="40", cost="0", value="400", price="10"),
            _pos("US0000000002", qty="60", cost="0", value="600", price="10"),
        ]
        orch.process_positions()
        asset = _find(orch.asset_resolver, isin="US0000000002")
        assert asset.eoy_quantity == Decimal("100")
        assert asset.eoy_position_value == Decimal("1000")
        assert asset.eoy_market_price == Decimal("10")

    def test_single_account_security_unchanged(self):
        orch = _orchestrator()
        orch.raw_positions_start = [_pos("US0000000003", qty="100", cost="600", value="1000")]
        orch.process_positions()
        asset = _find(orch.asset_resolver, isin="US0000000003")
        assert asset.soy_quantity == Decimal("100")
        assert asset.soy_cost_basis_amount == Decimal("600")


# ---------------------------------------------------------------------------
# C. Co-holding detection: warn when a security is in >1 account in one snapshot
#    (merged FIFO is account-agnostic; per-Depot precision not modelled).
#    Must NOT fire for a transfer (same ISIN in only one account per snapshot).
# ---------------------------------------------------------------------------

class TestCoHoldingDetection:

    def test_security_co_held_in_two_accounts_warns(self, caplog):
        orch = _orchestrator()
        orch.raw_positions_start = [
            _pos("US0000000020", qty="100", cost="600", value="1000", account="U10000001"),
            _pos("US0000000020", qty="50", cost="300", value="500", account="U10000002"),
        ]
        with caplog.at_level(logging.WARNING):
            orch.process_positions()
        assert any("multiple accounts" in r.message for r in caplog.records)

    def test_transfer_between_accounts_does_not_warn(self, caplog):
        """SoY in account A, EoY in account B (a transfer A->B): never co-held in one snapshot."""
        orch = _orchestrator()
        orch.raw_positions_start = [_pos("US0000000021", qty="100", cost="600", value="1000", account="U10000001")]
        orch.raw_positions_end = [_pos("US0000000021", qty="100", cost="600", value="1000", account="U10000002")]
        with caplog.at_level(logging.WARNING):
            orch.process_positions()
        assert not any("multiple accounts" in r.message for r in caplog.records)
        # ...and the merged ledger still tracks the position (transfer carried correctly).
        asset = _find(orch.asset_resolver, isin="US0000000021")
        assert asset.soy_quantity == Decimal("100") and asset.eoy_quantity == Decimal("100")

    def test_single_account_does_not_warn(self, caplog):
        orch = _orchestrator()
        orch.raw_positions_start = [_pos("US0000000022", qty="100", cost="600", value="1000", account="U10000001")]
        with caplog.at_level(logging.WARNING):
            orch.process_positions()
        assert not any("multiple accounts" in r.message for r in caplog.records)

    def test_zero_quantity_second_account_does_not_warn(self, caplog):
        """A zero/closed position in a second account is not co-holding."""
        orch = _orchestrator()
        orch.raw_positions_start = [
            _pos("US0000000023", qty="100", cost="600", value="1000", account="U10000001"),
            _pos("US0000000023", qty="0", cost="0", value="0", account="U10000002"),
        ]
        with caplog.at_level(logging.WARNING):
            orch.process_positions()
        assert not any("multiple accounts" in r.message for r in caplog.records)

    def test_currency_in_multiple_accounts_warns_once(self, caplog):
        """Currencies: a single summary warning (not per-currency), since FX FIFO is merged."""
        orch = _orchestrator()
        orch.raw_cash_balances = [
            _cash("U10000001", "USD", "1000", "0"), _cash("U10000002", "USD", "2000", "0"),
            _cash("U10000001", "CAD", "500", "0"), _cash("U10000002", "CAD", "300", "0"),
        ]
        with caplog.at_level(logging.WARNING):
            orch._process_cash_balance_positions(tax_year=2025)
        warns = [r for r in caplog.records if "multiple accounts" in r.message]
        assert len(warns) == 1                      # one summary line, not one per currency
        assert "USD" in warns[0].message and "CAD" in warns[0].message

    def test_currency_single_account_no_warn(self, caplog):
        orch = _orchestrator()
        orch.raw_cash_balances = [_cash("U10000001", "USD", "1000", "0")]
        with caplog.at_level(logging.WARNING):
            orch._process_cash_balance_positions(tax_year=2025)
        assert not any("multiple accounts" in r.message for r in caplog.records)
