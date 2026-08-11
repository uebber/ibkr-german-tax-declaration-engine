"""
A snapshot the broker reports per account is the taxpayer's SUM across accounts.

legal_basis: [GT-ESTG20-061] -- 2 Abs. 1 Satz 1 Nr. 5 EStG taxes the Einkuenfte
aus Kapitalvermoegen *"die der Steuerpflichtige ... erzielt"*, and 25 Abs. 1 EStG
assesses the Einkommen *"das der Steuerpflichtige in diesem Veranlagungszeitraum
bezogen hat"*. The person and the period are the units of assessment; no cited
provision makes a Depot one. See
reference/tax-law/estg-20-kapitalvermoegen.md, section "Whose income".

This is independent of open question Q2 (whether the *"einzelne Depot"* FIFO
boundary of BMF Rz. 97 Satz 2 transposes to a foreign broker's sub-accounts).
Q2 governs WHICH LOT a disposal consumes; these tests govern WHOSE HOLDING is
declared, and they hold whichever way Q2 falls.

All figures here are INVENTED. CLAUDE.md forbids a cash balance or position
value copied from a real export reaching a commit.
"""
from decimal import Decimal
from unittest.mock import MagicMock

from src.classification.asset_classifier import AssetClassifier
from src.identification.asset_resolver import AssetResolver
from src.parsers.parsing_orchestrator import ParsingOrchestrator
from src.parsers.raw_models import RawCashBalanceRecord, RawPositionRecord
from src.domain.enums import AssetCategory


A, B = "U10000001", "U10000002"


def _orchestrator() -> ParsingOrchestrator:
    """Classifier stubbed on asset class alone — these tests are about how many
    rows are folded into one asset, never about which category it gets."""
    classifier = MagicMock(spec=AssetClassifier)

    def _prelim(ibkr_asset_class=None, ibkr_sub_category=None, description=None, symbol=None):
        if (ibkr_asset_class or "").upper() == "CASH":
            return (AssetCategory.CASH_BALANCE, None)
        return (AssetCategory.STOCK, None)

    classifier.preliminary_classify.side_effect = _prelim
    resolver = AssetResolver(classifier)
    return ParsingOrchestrator(resolver, classifier, interactive_classification=False)


def _cash(account, ccy, soy, eoy, year=2025) -> RawCashBalanceRecord:
    return RawCashBalanceRecord(**{
        "ClientAccountID": account, "CurrencyPrimary": ccy,
        "FromDate": f"{year}0101", "ToDate": f"{year}1231",
        "StartingCash": Decimal(soy), "EndingCash": Decimal(eoy),
    })


def _pos(account, isin, qty, cost, value, price="10", ccy="EUR") -> RawPositionRecord:
    return RawPositionRecord(**{
        "ClientAccountID": account, "CurrencyPrimary": ccy, "AssetClass": "STK",
        "Symbol": isin[:6], "Description": f"{isin[:6]} security", "ISIN": isin,
        "Conid": isin, "Quantity": Decimal(qty), "MarkPrice": Decimal(price),
        "PositionValue": Decimal(value), "CostBasisMoney": Decimal(cost),
    })


def _find(resolver, *, currency=None, category=None, isin=None):
    for asset in resolver.assets_by_internal_id.values():
        if category is not None and asset.asset_category != category:
            continue
        if currency is not None and asset.currency != currency:
            continue
        if isin is not None and getattr(asset, "ibkr_isin", None) != isin:
            continue
        return asset
    return None


# NOTE — `RawPositionRecord` does not map `ClientAccountID`, and this change does
# NOT add it. Aggregation folds by resolved asset identity and never reads the
# account, so the field would be code no production path reaches. The omission is
# a deliberate, recorded decision (issue #69; pinned by
# tests/test_raw_model_fields.py::test_the_models_that_deliberately_drop_a_requested_column_are_listed,
# whose docstring notes it is "inert until the per-Depot flip"). It becomes a real
# prerequisite for Phase 2, which keys ledgers by account, and belongs there.


# ---------------------------------------------------------------------------
# Cash balances
# ---------------------------------------------------------------------------

class TestCashBalanceAggregation:

    def test_one_currency_summed_across_two_accounts(self):
        orch = _orchestrator()
        orch.raw_cash_balances = [
            _cash(A, "USD", "700", "250"),
            _cash(B, "USD", "-200", "-50"),
        ]
        orch._process_cash_balance_positions(tax_year=2025)
        usd = _find(orch.asset_resolver, currency="USD", category=AssetCategory.CASH_BALANCE)
        assert usd is not None
        assert usd.soy_quantity == Decimal("500")
        assert usd.eoy_quantity == Decimal("200")

    def test_each_currency_summed_independently(self):
        """A sum must not leak between currency buckets."""
        orch = _orchestrator()
        orch.raw_cash_balances = [
            _cash(A, "USD", "700", "250"), _cash(B, "USD", "-200", "-50"),
            _cash(A, "CHF", "80", "40"), _cash(B, "CHF", "20", "10"),
        ]
        orch._process_cash_balance_positions(tax_year=2025)
        usd = _find(orch.asset_resolver, currency="USD", category=AssetCategory.CASH_BALANCE)
        chf = _find(orch.asset_resolver, currency="CHF", category=AssetCategory.CASH_BALANCE)
        assert (usd.soy_quantity, usd.eoy_quantity) == (Decimal("500"), Decimal("200"))
        assert (chf.soy_quantity, chf.eoy_quantity) == (Decimal("100"), Decimal("50"))

    def test_eur_and_base_summary_never_reach_the_sum(self):
        """BASE_SUMMARY is IBKR's per-account aggregate row. Summing it would
        double-count every currency in that account."""
        orch = _orchestrator()
        orch.raw_cash_balances = [
            _cash(A, "BASE_SUMMARY", "9999", "9999"),
            _cash(B, "BASE_SUMMARY", "8888", "8888"),
            _cash(A, "EUR", "500", "500"),
            _cash(A, "USD", "700", "250"), _cash(B, "USD", "-200", "-50"),
        ]
        orch._process_cash_balance_positions(tax_year=2025)
        assert _find(orch.asset_resolver, currency="BASE_SUMMARY",
                     category=AssetCategory.CASH_BALANCE) is None
        assert _find(orch.asset_resolver, currency="EUR",
                     category=AssetCategory.CASH_BALANCE) is None
        usd = _find(orch.asset_resolver, currency="USD", category=AssetCategory.CASH_BALANCE)
        assert usd.soy_quantity == Decimal("500")

    def test_threshold_applies_to_the_summed_balance(self):
        """Two sub-threshold rows that SUM above the threshold are kept; two that
        stay below it together are not."""
        orch = _orchestrator()
        orch.raw_cash_balances = [
            _cash(A, "USD", "0.006", "0"), _cash(B, "USD", "0.006", "0"),   # 0.012 >= 0.01
            _cash(A, "CHF", "0.004", "0"), _cash(B, "CHF", "0.004", "0"),   # 0.008 <  0.01
        ]
        orch._process_cash_balance_positions(tax_year=2025)
        usd = _find(orch.asset_resolver, currency="USD", category=AssetCategory.CASH_BALANCE)
        assert usd is not None and usd.soy_quantity == Decimal("0.012")
        assert _find(orch.asset_resolver, currency="CHF",
                     category=AssetCategory.CASH_BALANCE) is None

    def test_net_zero_but_actively_held_currency_is_kept(self):
        """+800 in one account, -800 in the other: the SUM is zero and below the
        tiny-balance threshold, but the currency is actively held and its FIFO
        ledger carries real FX gain/loss. Thresholding the sum alone would drop
        it, which is why the rule is 'sum OR any single account clears it'."""
        orch = _orchestrator()
        orch.raw_cash_balances = [
            _cash(A, "USD", "800", "0"),
            _cash(B, "USD", "-800", "0"),
        ]
        orch._process_cash_balance_positions(tax_year=2025)
        usd = _find(orch.asset_resolver, currency="USD", category=AssetCategory.CASH_BALANCE)
        assert usd is not None, "net-zero currency dropped; its FX ledger would vanish"
        assert usd.soy_quantity == Decimal("0")

    def test_single_account_is_unchanged(self):
        orch = _orchestrator()
        orch.raw_cash_balances = [_cash(A, "USD", "1000", "900")]
        orch._process_cash_balance_positions(tax_year=2025)
        usd = _find(orch.asset_resolver, currency="USD", category=AssetCategory.CASH_BALANCE)
        assert (usd.soy_quantity, usd.eoy_quantity) == (Decimal("1000"), Decimal("900"))


# ---------------------------------------------------------------------------
# Security positions
# ---------------------------------------------------------------------------

class TestPositionAggregation:

    def test_soy_quantity_cost_and_value_summed(self):
        orch = _orchestrator()
        orch.raw_positions_start = [
            _pos(A, "US000000BBB1", "100", "600", "1000"),
            _pos(B, "US000000BBB1", "50", "300", "500"),
        ]
        orch.process_positions()
        asset = _find(orch.asset_resolver, isin="US000000BBB1")
        assert asset.soy_quantity == Decimal("150")
        assert asset.soy_cost_basis_amount == Decimal("900")
        assert asset.soy_position_value == Decimal("1500")

    def test_eoy_quantity_and_value_summed(self):
        """EoY is a separate loop from SoY, so it needs its own assertion."""
        orch = _orchestrator()
        orch.raw_positions_end = [
            _pos(A, "US000000CCC1", "40", "0", "400"),
            _pos(B, "US000000CCC1", "60", "0", "600"),
        ]
        orch.process_positions()
        asset = _find(orch.asset_resolver, isin="US000000CCC1")
        assert asset.eoy_quantity == Decimal("100")
        assert asset.eoy_position_value == Decimal("1000")

    def test_prior_year_snapshots_summed(self):
        """The Vorabpauschale reference snapshots are a third and fourth loop.
        The PR train shipped its aggregation fix without them and needed a
        follow-up commit, so they are asserted separately here."""
        orch = _orchestrator()
        orch.raw_positions_prior_start = [
            _pos(A, "US000000DDD1", "30", "180", "300"),
            _pos(B, "US000000DDD1", "70", "420", "700"),
        ]
        orch.raw_positions_prior_end = [
            _pos(A, "US000000DDD1", "10", "60", "100"),
            _pos(B, "US000000DDD1", "20", "120", "200"),
        ]
        orch.process_positions()
        asset = _find(orch.asset_resolver, isin="US000000DDD1")
        assert asset.prior_year_soy_quantity == Decimal("100")
        assert asset.prior_year_eoy_quantity == Decimal("30")

    def test_zero_quantity_row_in_a_second_account_adds_nothing(self):
        """A closed position in another account must neither change the sum nor
        create a phantom holding."""
        orch = _orchestrator()
        orch.raw_positions_start = [
            _pos(A, "US000000EEE1", "100", "600", "1000"),
            _pos(B, "US000000EEE1", "0", "0", "0"),
        ]
        orch.process_positions()
        asset = _find(orch.asset_resolver, isin="US000000EEE1")
        assert asset.soy_quantity == Decimal("100")
        assert asset.soy_cost_basis_amount == Decimal("600")

    def test_held_in_one_account_at_soy_and_another_at_eoy(self):
        """A position moved between the taxpayer's own accounts is never co-held
        in one snapshot. Both snapshots must still report the whole holding."""
        orch = _orchestrator()
        orch.raw_positions_start = [_pos(A, "US000000FFF1", "100", "600", "1000")]
        orch.raw_positions_end = [_pos(B, "US000000FFF1", "100", "600", "1000")]
        orch.process_positions()
        asset = _find(orch.asset_resolver, isin="US000000FFF1")
        assert asset.soy_quantity == Decimal("100")
        assert asset.eoy_quantity == Decimal("100")

    def test_prior_year_opening_quantity_summed(self):
        """The opening snapshot of the year BEFORE the Vorabpauschale year.

        Not diagnostic: calculation_engine reads it as `held_before_the_year`,
        and `undated_units > held_before_the_year` decides whether a
        Vorabpauschale is computed at all. Taking one account's row understates
        it and SUPPRESSES a declared figure rather than mis-stating one.
        """
        orch = _orchestrator()
        orch.raw_positions_prior_opening = [
            _pos(A, "US000000HHH1", "30", "180", "300"),
            _pos(B, "US000000HHH1", "70", "420", "700"),
        ]
        orch.process_positions()
        asset = _find(orch.asset_resolver, isin="US000000HHH1")
        assert asset.prior_year_opening_quantity == Decimal("100")

    def test_checkpoint_mark_sums_quantity_and_cost_basis_together(self):
        """A mark carries a quantity AND a cost basis, and they must describe the
        same holding. Quantity was already summed; the basis was taken from the
        last row, so a mark could report 100 units carrying the cost of 70.
        `reconcile_with_mark` discards the reconstruction on disagreement and
        takes the snapshot, synthesising a lot with that wrong basis.
        """
        orch = _orchestrator()
        orch.raw_positions_marks = {2023: [
            _pos(A, "US000000III1", "30", "180", "300"),
            _pos(B, "US000000III1", "70", "420", "700"),
        ]}
        orch.process_positions()
        asset = _find(orch.asset_resolver, isin="US000000III1")
        mark = orch.mark_positions[2023][asset.internal_asset_id]
        assert mark.quantity == Decimal("100")
        assert mark.cost_basis_amount == Decimal("600"), \
            "quantity and cost basis must describe the same holding"

    def test_single_account_position_is_unchanged(self):
        orch = _orchestrator()
        orch.raw_positions_start = [_pos(A, "US000000GGG1", "100", "600", "1000")]
        orch.process_positions()
        asset = _find(orch.asset_resolver, isin="US000000GGG1")
        assert asset.soy_quantity == Decimal("100")
        assert asset.soy_cost_basis_amount == Decimal("600")
        assert asset.soy_position_value == Decimal("1000")
