"""
Multi-account aggregation in position/cash-balance processing.

IBKR Flex exports emit one row **per account** for cash balances and security positions.
Assets are resolved account-agnostically (by currency / ISIN / Conid — German tax aggregates
across a person's accounts), so when the same currency or security is held in more than one
account the per-account rows must be **summed**, not overwritten.

Two bugs this guards against (both: a per-account row assigned with ``=`` onto a shared asset):
  A. Cash balances (``_process_cash_balance_positions``) — a currency held in more than one
     account arrives as one row per account; before the fix only the last one survived.
  B. Security SoY/EoY positions (``process_positions``) — the same, for any instrument held in
     more than one account.

Summing the per-account rows is data semantics, not tax law: it reconstructs the holding the
rows describe. What the engine then does with a pooled holding is a separate question — for a
security co-held in two accounts, one merged FIFO queue is the recorded deviation
[GT-ESTG20-013]; for a currency it is not a deviation at all (see
``test_currency_in_multiple_accounts_does_not_warn``). Neither is decided here.

Also pinned: per-unit mark price is not summed; EUR (base) and BASE_SUMMARY rows are not
tracked as foreign-currency cash.
"""
import logging
from decimal import Decimal

import pytest
from unittest.mock import MagicMock

from src.identification.asset_resolver import AssetResolver
from src.classification.asset_classifier import AssetClassifier
from src.parsers.parsing_orchestrator import ParsingOrchestrator
from src.parsers.raw_models import RawCashBalanceRecord, RawPositionRecord
from src.domain.enums import AssetCategory
from src.domain.exceptions import DataIntegrityError


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

    def test_zero_cost_basis_is_summed_not_rejected(self):
        """A reported cost basis of 0 means zero, not "not reported". The engine itself books
        stock-dividend shares at EUR 0 basis, so a zero-basis holding is legitimate input and
        must survive aggregation rather than being treated as missing."""
        orch = _orchestrator()
        orch.raw_positions_start = [
            _pos("US0000000006", qty="100", cost="600", value="1000", account="U10000001"),
            _pos("US0000000006", qty="50", cost="0", value="500", account="U10000002"),
        ]
        orch.process_positions()
        asset = _find(orch.asset_resolver, isin="US0000000006")
        assert asset.soy_quantity == Decimal("150")
        assert asset.soy_cost_basis_amount == Decimal("600")

    def test_rows_disagreeing_on_currency_raise(self):
        """Summing across currencies would add unlike amounts and label the total with whichever
        row was read last, producing a plausible figure that is simply wrong. Refuse instead."""
        orch = _orchestrator()
        orch.raw_positions_start = [
            _pos("US0000000007", qty="100", cost="600", value="1000", ccy="USD", account="U10000001"),
            _pos("US0000000007", qty="50", cost="300", value="500", ccy="CHF", account="U10000002"),
        ]
        with pytest.raises(DataIntegrityError) as exc:
            orch.process_positions()
        assert "CHF" in str(exc.value) and "USD" in str(exc.value)

    def test_all_currency_disagreements_reported_together(self):
        """One run must identify the whole problem, not one instrument per attempt."""
        orch = _orchestrator()
        orch.raw_positions_start = [
            _pos("US0000000008", qty="10", cost="10", value="10", ccy="USD", account="U10000001"),
            _pos("US0000000008", qty="10", cost="10", value="10", ccy="CHF", account="U10000002"),
            _pos("US0000000009", qty="10", cost="10", value="10", ccy="USD", account="U10000001"),
            _pos("US0000000009", qty="10", cost="10", value="10", ccy="CAD", account="U10000002"),
        ]
        with pytest.raises(DataIntegrityError) as exc:
            orch.process_positions()
        msg = str(exc.value)
        assert "2 instrument(s)" in msg
        assert "US0000000008" in msg and "US0000000009" in msg

    def test_single_account_security_unchanged(self):
        orch = _orchestrator()
        orch.raw_positions_start = [_pos("US0000000003", qty="100", cost="600", value="1000")]
        orch.process_positions()
        asset = _find(orch.asset_resolver, isin="US0000000003")
        assert asset.soy_quantity == Decimal("100")
        assert asset.soy_cost_basis_amount == Decimal("600")


# ---------------------------------------------------------------------------
# B2. Prior-year snapshots summed across accounts
#     Same per-account row shape, a third pair of snapshots. These feed only the
#     Vorabpauschale reference figures (18 Abs. 3 InvStG), never cost basis or
#     reconciliation.
# ---------------------------------------------------------------------------

class TestPriorYearPositionMultiAccount:

    def test_prior_year_soy_quantity_and_value_summed(self):
        orch = _orchestrator()
        orch.raw_positions_prior_start = [
            _pos("US0000000010", qty="100", cost="0", value="1000", price="10", account="U10000001"),
            _pos("US0000000010", qty="50", cost="0", value="500", price="10", account="U10000002"),
        ]
        orch.process_positions()
        asset = _find(orch.asset_resolver, isin="US0000000010")
        assert asset.prior_year_soy_quantity == Decimal("150")
        assert asset.prior_year_soy_position_value == Decimal("1500")

    def test_prior_year_eoy_value_summed(self):
        orch = _orchestrator()
        orch.raw_positions_prior_end = [
            _pos("US0000000011", qty="100", cost="0", value="1200", price="12", account="U10000001"),
            _pos("US0000000011", qty="50", cost="0", value="600", price="12", account="U10000002"),
        ]
        orch.process_positions()
        asset = _find(orch.asset_resolver, isin="US0000000011")
        assert asset.prior_year_eoy_position_value == Decimal("1800")

    def test_closed_row_in_second_account_does_not_zero_the_prior_year_quantity(self):
        """The worst case, and the reason this is not a rounding-scale defect.

        IBKR emits a zero row for a closed position, so a fund held in one account can carry a
        second row with quantity 0. Assigned per row, the zero row lands last and the fund's
        prior-year quantity becomes 0 — and ``calculation_engine`` skips any fund whose
        ``prior_year_soy_quantity <= 0`` with a bare ``continue`` and no log line at any level.
        The Vorabpauschale for that fund is then omitted from the declaration silently.
        """
        orch = _orchestrator()
        orch.raw_positions_prior_start = [
            _pos("US0000000014", qty="100", cost="0", value="1000", price="10", account="U10000001"),
            _pos("US0000000014", qty="0", cost="0", value="0", price="10", account="U10000002"),
        ]
        orch.raw_positions_prior_end = [
            _pos("US0000000014", qty="100", cost="0", value="1200", price="12", account="U10000001"),
            _pos("US0000000014", qty="0", cost="0", value="0", price="12", account="U10000002"),
        ]
        orch.process_positions()
        asset = _find(orch.asset_resolver, isin="US0000000014")
        # > 0, so the fund is not skipped, and the value that drives Basisertrag survives.
        assert asset.prior_year_soy_quantity == Decimal("100")
        assert asset.prior_year_soy_position_value == Decimal("1000")
        assert asset.prior_year_eoy_position_value == Decimal("1200")

    def test_prior_year_single_account_unchanged(self):
        orch = _orchestrator()
        orch.raw_positions_prior_start = [
            _pos("US0000000012", qty="80", cost="0", value="800", price="10", account="U10000001"),
        ]
        orch.process_positions()
        asset = _find(orch.asset_resolver, isin="US0000000012")
        assert asset.prior_year_soy_quantity == Decimal("80")
        assert asset.prior_year_soy_position_value == Decimal("800")

    def test_prior_year_co_holding_does_not_warn(self, caplog):
        """No per-Depot warning for these snapshots: they feed the Vorabpauschale, which is
        computed from a fund's quantity and its year-start/year-end values. No FIFO lot is
        consumed, so the pooled-vs-per-Depot lot-order question does not arise here."""
        orch = _orchestrator()
        orch.raw_positions_prior_start = [
            _pos("US0000000013", qty="100", cost="0", value="1000", account="U10000001"),
            _pos("US0000000013", qty="50", cost="0", value="500", account="U10000002"),
        ]
        with caplog.at_level(logging.WARNING):
            orch.process_positions()
        assert not any("multiple accounts" in r.message for r in caplog.records)


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

    def test_security_co_held_only_in_the_eoy_snapshot_warns(self, caplog):
        """The EoY snapshot has its own `_warn_if_co_held` call. Without this, that call could be
        deleted outright with the suite green — a security first co-held during the tax year
        would go unreported."""
        orch = _orchestrator()
        orch.raw_positions_end = [
            _pos("US0000000024", qty="100", cost="600", value="1000", account="U10000001"),
            _pos("US0000000024", qty="50", cost="300", value="500", account="U10000002"),
        ]
        with caplog.at_level(logging.WARNING):
            orch.process_positions()
        warns = [r for r in caplog.records if "multiple accounts" in r.message]
        assert len(warns) == 1
        assert "EoY" in warns[0].message

    def test_single_account_does_not_warn(self, caplog):
        orch = _orchestrator()
        orch.raw_positions_start = [_pos("US0000000022", qty="100", cost="600", value="1000", account="U10000001")]
        with caplog.at_level(logging.WARNING):
            orch.process_positions()
        assert not any("multiple accounts" in r.message for r in caplog.records)

    def test_zero_quantity_second_account_does_not_warn(self, caplog):
        """A zero/closed position in a second account is not co-holding.

        The quantity assertion is not incidental: assigned per row the closed row lands last and
        zeroes the holding, so this pins that the open position survives a trailing zero row."""
        orch = _orchestrator()
        orch.raw_positions_start = [
            _pos("US0000000023", qty="100", cost="600", value="1000", account="U10000001"),
            _pos("US0000000023", qty="0", cost="0", value="0", account="U10000002"),
        ]
        with caplog.at_level(logging.WARNING):
            orch.process_positions()
        assert not any("multiple accounts" in r.message for r in caplog.records)
        asset = _find(orch.asset_resolver, isin="US0000000023")
        assert asset.soy_quantity == Decimal("100")
        assert asset.soy_cost_basis_amount == Decimal("600")

    def test_currency_in_multiple_accounts_does_not_warn(self, caplog):
        """Currencies get no co-holding warning, and this pins that deliberately.

        The per-Depot boundary that makes pooling a deviation for securities does not reach a
        currency balance: BMF 14.05.2025 Rz. 97 Satz 2 scopes itself to the Fifo-Methode *im
        Sinne des § 20 Absatz 4 Satz 7 EStG*, and that Satz is conditioned on vertretbare
        Wertpapiere in Sammelverwahrung (§ 5 DepotG). Currency FIFO is grounded in BMF Rz. 131
        and § 23 Abs. 1 Satz 1 Nr. 2 Satz 3 EStG, neither of which draws an account boundary —
        so a merged per-currency queue is what the rule prescribes, not a departure from it.
        See reference/bmf-guidance/fremdwaehrung-konten.md [GT-FX-008].
        """
        orch = _orchestrator()
        orch.raw_cash_balances = [
            _cash("U10000001", "USD", "1000", "0"), _cash("U10000002", "USD", "2000", "0"),
            _cash("U10000001", "CAD", "500", "0"), _cash("U10000002", "CAD", "300", "0"),
        ]
        with caplog.at_level(logging.WARNING):
            orch._process_cash_balance_positions(tax_year=2025)
        assert not any("multiple accounts" in r.message for r in caplog.records)
        # ...and the balances are still summed, which is the part that matters.
        usd = _find(orch.asset_resolver, currency="USD", category=AssetCategory.CASH_BALANCE)
        assert usd.soy_quantity == Decimal("3000")

    def test_cash_row_without_currency_raises(self):
        """A balance that belongs to no currency cannot reach any FX ledger. Skipping it would
        drop it from the computation with only a debug line as evidence."""
        orch = _orchestrator()
        orch.raw_cash_balances = [
            _cash("U10000001", "USD", "1000", "900"),
            _cash("U10000002", "", "5000", "5000"),
        ]
        with pytest.raises(DataIntegrityError) as exc:
            orch._process_cash_balance_positions(tax_year=2025)
        assert "no CurrencyPrimary" in str(exc.value)
        assert "5000" in str(exc.value)

    def test_all_unnamed_currency_rows_reported_together(self):
        orch = _orchestrator()
        orch.raw_cash_balances = [
            _cash("U10000001", "", "100", "0"),
            _cash("U10000002", "", "200", "0"),
        ]
        with pytest.raises(DataIntegrityError) as exc:
            orch._process_cash_balance_positions(tax_year=2025)
        assert "2 cash-balance row(s)" in str(exc.value)

    def test_transfer_between_accounts_does_not_warn_for_currency(self, caplog):
        """A currency moved A->B was warned about before the warning was removed; pinned so a
        future per-account currency rule cannot reintroduce that false positive silently."""
        orch = _orchestrator()
        orch.raw_cash_balances = [
            _cash("U10000001", "USD", "1000", "0"), _cash("U10000002", "USD", "0", "1000"),
        ]
        with caplog.at_level(logging.WARNING):
            orch._process_cash_balance_positions(tax_year=2025)
        assert not any("multiple accounts" in r.message for r in caplog.records)
