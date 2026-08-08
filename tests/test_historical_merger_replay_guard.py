# tests/test_historical_merger_replay_guard.py
"""
Guard: the historical-merger replay must actually transfer the source lots,
and the transferred lot must keep its original acquisition date.

Why this needs its own test. In `run_main_calculations` the two ledger lookups
that open the replay are not symmetric: a missing TARGET ledger raises, but a
missing SOURCE ledger only logs a warning and `continue`s. A silently skipped
merger is then papered over by the reconcile phase, which compares every ledger
against the SoY snapshot and synthesises a fallback lot for the shortfall -- and that
fallback lot is dated `f"{tax_year-1}-12-31"` (`FifoLedger.reconcile_with_soy_
position`), not the real acquisition date, while its cost basis is read from the
Positions file.

Because a merged holding's SoY cost basis *is* the carried-over basis, the
fallback reproduces the correct cost basis exactly. The pre-existing merger
tests assert quantity, cost basis, proceeds and gain -- all four of which the
fallback gets right -- so they pass whether or not the replay ran. Demonstrated:
breaking the source lookup in `_replay_historical_merger` left the entire
463-test suite green.

The acquisition date is the one observable that separates the two paths, so it
is what this test pins. It is not cosmetic: for a `PRIVATE_SALE_ASSET` the
acquisition date decides the § 23 EStG Jahresfrist (reference/tax-law/
estg-23-private-veraeusserung.md), so a silently skipped historical merger would
move a disposal between taxable and exempt while every figure the other tests
check still looked right.
"""
from decimal import Decimal

from src.domain.enums import RealizationType
from tests.support.base import FifoTestCaseBase
from tests.support.mock_providers import MockECBExchangeRateProvider
from tests.support.expected import (
    ScenarioExpectedOutput, ExpectedRealizedGainLoss, ExpectedAssetEoyState,
)


class TestHistoricalMergerReplayGuard(FifoTestCaseBase):

    def test_replayed_merger_keeps_the_original_acquisition_date(self, mock_config_paths):
        """
        2022: BUY 130 GZUR, merger GZUR->SGBS 1:1
        2023: SELL 130 SGBS

        The lot sold in 2023 must carry GZUR's 2022-03-01 acquisition date. If
        the replay skipped the transfer, the reconcile phase's SoY fallback
        supplies a lot dated 2022-12-31 with the same cost basis, and every
        other assertion below still holds.
        """
        tax_year = 2023
        account = "U_HIST_MERGER_GUARD"
        mock_provider = MockECBExchangeRateProvider(foreign_to_eur_init_value=Decimal("1.0"))

        trades_data = [
            [account, "EUR", "STK", "", "GZUR", "GZUR Stock", "DE0000000015",
             "", "", "", "2022-03-01", "130", "167.56", "-2.00", "EUR",
             "BUY", "TX_BUY_GZUR", "", "", "CON_GZUR", "", "1", "O"],
            [account, "EUR", "STK", "", "SGBS", "SGBS Stock", "JE0000000014",
             "", "", "", "2023-08-22", "-130", "168.00", "-2.00", "EUR",
             "SELL", "TX_SELL_SGBS", "", "", "CON_SGBS", "", "1", "C"],
        ]

        corp_actions_data = [
            [account, "GZUR", "GZUR(DE0000000015) MERGED(Acquisition) WITH SGBS 1 FOR 1",
             "DE0000000015", "2022-08-22", "TC", "TC", "900034051",
             "CON_GZUR", "", "", "EUR", "0", "0", "-21782.80", "-130"],
        ]

        positions_start = [
            [account, "EUR", "STK", "", "SGBS", "SGBS Stock", "JE0000000014",
             "130", "21800.00", "167.69", "21784.80", "", "CON_SGBS", "", "1"],
        ]

        expected = ScenarioExpectedOutput(
            test_description="Historical merger replay preserves the original acquisition date",
            expected_rgls=[
                ExpectedRealizedGainLoss(
                    asset_identifier="SGBS",
                    realization_date="2023-08-22",
                    quantity_realized=Decimal("130"),
                    total_cost_basis_eur=Decimal("21784.80"),
                    total_realization_value_eur=Decimal("21838.00"),
                    gross_gain_loss_eur=Decimal("53.20"),
                    realization_type=RealizationType.LONG_POSITION_SALE.name,
                    # The discriminator: GZUR's own acquisition date, carried
                    # through the merger. The SoY fallback would say 2022-12-31.
                    acquisition_date="2022-03-01",
                ),
            ],
            expected_eoy_states=[
                ExpectedAssetEoyState(asset_identifier="SGBS", eoy_quantity=Decimal("0")),
            ],
            expected_eoy_mismatch_error_count=0,
        )

        results = self._run_pipeline(
            trades_data=trades_data,
            corporate_actions_data=corp_actions_data,
            positions_start_data=positions_start,
            positions_end_data=[],
            custom_rate_provider=mock_provider,
            tax_year=tax_year,
        )

        self.assert_results(results, expected)
