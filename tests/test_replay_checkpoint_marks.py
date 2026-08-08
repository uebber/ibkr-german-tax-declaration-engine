# tests/test_replay_checkpoint_marks.py
"""
The historical replay reconciles at every position snapshot in the window, not
only at the tax year's opening one.

Why this needs its own test. A partial ledger is the normal starting condition:
the transaction files reach back only so far, so the earliest interval is always
missing whatever was held before the window opened. Before checkpointing, that
shortfall was absorbed once, at the end -- and by then it had already corrupted
every interval in between. One oversell in the first year offset the ledger for
every year that followed, and the tax year's reconciliation could only see the
net effect, which it resolved by throwing the whole reconstruction away and
synthesising a single undated lot.

Measured on the maintainer's data before this change: five securities reached
the tax-year snapshot with a synthesised lot across VZ 2023-2025, and in every
one of those the disagreement originated in 2021.

The discriminator here is the acquisition date, for the reason CLAUDE.md gives
under "where the suite is blind": a start-of-year snapshot rebuilds quantity,
cost basis, proceeds and gain, so a scenario that asserts those four passes
whether or not the lots are real. Only the date separates a reconstruction from
a fabrication.
"""
from decimal import Decimal

from src.domain.enums import RealizationType
from src.processing.data_gaps import GapSeverity
from tests.support.base import FifoTestCaseBase
from tests.support.mock_providers import MockECBExchangeRateProvider
from tests.support.expected import (
    ScenarioExpectedOutput, ExpectedRealizedGainLoss, ExpectedAssetEoyState,
)

_ACCOUNT = "U_CHECKPOINT"
_ISIN = "DE0000000031"


def _trade(date_str, qty, price, tx_id, buy_sell, open_close):
    return [_ACCOUNT, "EUR", "STK", "", "CHKP", "CHKP Stock", _ISIN,
            "", "", "", date_str, qty, price, "-1.00", "EUR",
            buy_sell, tx_id, "", "", "CON_CHKP", "", "1", open_close]


def _position(qty, position_value, mark_price, cost_basis):
    return [_ACCOUNT, "EUR", "STK", "", "CHKP", "CHKP Stock", _ISIN,
            qty, position_value, mark_price, cost_basis, "", "CON_CHKP", "", "1"]


class TestCheckpointMarks(FifoTestCaseBase):

    def test_a_pre_window_holding_stops_corrupting_later_years(self, mock_config_paths):
        """
        The ledger opens short of the truth and recovers at the first mark.

        Held before the window: 60 units the transaction files do not contain.

        2021-09-10  SELL 60   <- oversells; the engine holds none of them
        2021-12-31  mark: broker reports 40
        2022-05-04  BUY  40
        2022-11-08  SELL 40   <- consumes the 2021-12-31 anchored units, FIFO
        2022-12-31  mark: broker reports 40   (the 2022-05-04 purchase)
        2023-12-31  opening snapshot: 40
        2024-03-12  SELL 40

        Without marks the 2021 shortfall is still in the ledger at the end of
        2023, the reconstruction disagrees with the opening snapshot, and the
        2024 disposal is measured against a lot dated 2023-12-31 that nobody
        observed. With them, the shortfall is absorbed in 2021, and the units
        sold in 2024 are the real 2022-05-04 purchase.

        The cost basis reported at each snapshot equals the real purchase cost,
        so a synthesised lot reproduces every figure except the date.
        """
        mock_provider = MockECBExchangeRateProvider(foreign_to_eur_init_value=Decimal("1.0"))

        trades_data = [
            _trade("2021-09-10", "-60", "30.00", "TX_SELL_2021", "SELL", "C"),
            _trade("2022-05-04", "40", "25.00", "TX_BUY_2022", "BUY", "O"),
            _trade("2022-11-08", "-40", "32.00", "TX_SELL_2022", "SELL", "C"),
            _trade("2024-03-12", "-40", "35.00", "TX_SELL_2024", "SELL", "C"),
        ]

        marks = {
            2021: [_position("40", "1200.00", "30.00", "1000.00")],
            2022: [_position("40", "1280.00", "32.00", "1001.00")],
        }

        # Opening snapshot for VZ 2024 = Positions-2023-EoY.csv.
        positions_start = [_position("40", "1320.00", "33.00", "1001.00")]

        expected = ScenarioExpectedOutput(
            test_description="Pre-window shortfall absorbed at the first mark",
            expected_rgls=[
                ExpectedRealizedGainLoss(
                    asset_identifier="CHKP",
                    realization_date="2024-03-12",
                    quantity_realized=Decimal("40"),
                    total_cost_basis_eur=Decimal("1001.00"),
                    total_realization_value_eur=Decimal("1399.00"),
                    gross_gain_loss_eur=Decimal("398.00"),
                    realization_type=RealizationType.LONG_POSITION_SALE.name,
                    # The discriminator. Without checkpointing: 2023-12-31.
                    acquisition_date="2022-05-04",
                ),
            ],
            expected_eoy_states=[
                ExpectedAssetEoyState(asset_identifier="CHKP", eoy_quantity=Decimal("0")),
            ],
            expected_eoy_mismatch_error_count=0,
        )

        results = self._run_pipeline(
            trades_data=trades_data,
            positions_mark_data=marks,
            positions_start_data=positions_start,
            positions_end_data=[],
            custom_rate_provider=mock_provider,
            tax_year=2024,
        )

        self.assert_results(results, expected)

    def test_the_first_interval_may_disagree_and_says_so(self, mock_config_paths):
        """
        The 2021 disagreement above is recorded, not swallowed.

        It is a WARNING and not an error because that interval did not start
        from a reported snapshot: its ledger begins empty while the real holding
        did not, so it is *expected* to disagree by whatever was held before the
        window opened. The units carried forward are the broker's, and the lot
        built from them is undated.
        """
        mock_provider = MockECBExchangeRateProvider(foreign_to_eur_init_value=Decimal("1.0"))

        results = self._run_pipeline(
            trades_data=[
                _trade("2021-09-10", "-60", "30.00", "TX_SELL_2021", "SELL", "C"),
                _trade("2022-05-04", "40", "25.00", "TX_BUY_2022", "BUY", "O"),
                _trade("2022-11-08", "-40", "32.00", "TX_SELL_2022", "SELL", "C"),
                _trade("2024-03-12", "-40", "35.00", "TX_SELL_2024", "SELL", "C"),
            ],
            positions_mark_data={
                2021: [_position("40", "1200.00", "30.00", "1000.00")],
                2022: [_position("40", "1280.00", "32.00", "1001.00")],
            },
            positions_start_data=[_position("40", "1320.00", "33.00", "1001.00")],
            positions_end_data=[],
            custom_rate_provider=mock_provider,
            tax_year=2024,
        )

        marks = [g for g in results.data_gaps if g.code == "REPLAY_MARK_UNCONFIRMED_START"]
        assert len(marks) == 1, [g.code for g in results.data_gaps]
        assert marks[0].severity is GapSeverity.WARNING
        assert "2021-12-31" in marks[0].subject
        # No error-grade gap: the only disagreement is the expected one.
        assert not [g for g in results.data_gaps if g.code == "REPLAY_MARK_MISMATCH"]


class TestTheSnapshotIsTheArbiter(FifoTestCaseBase):
    """
    Two rules about which lots survive a reconciliation. Both were previously
    decided by something other than the snapshot, and both destroyed real
    acquisition dates.
    """

    def test_an_exactly_matching_reconstruction_survives_an_oversell(self, mock_config_paths):
        """
        The oversell flag must not override an exact agreement.

        A pre-window holding is sold inside the window, so the replay oversells
        and the flag is set. The position is then rebuilt by real purchases, and
        by the opening snapshot the quantity is exactly what the broker reports.

        `fifo_manager` used to open reconciliation with
        `use_fallback = historical_simulation_inconsistent`, discarding the
        reconstruction before comparing anything. On the maintainer's data that
        threw away `DE0006766504`'s two real 2022-12-29 lots at a moment when
        the reconstruction agreed with the broker to the unit.
        """
        mock_provider = MockECBExchangeRateProvider(foreign_to_eur_init_value=Decimal("1.0"))

        results = self._run_pipeline(
            trades_data=[
                # oversells against an empty ledger: sets the flag
                _trade("2022-02-01", "-25", "20.00", "TX_OVERSELL", "SELL", "C"),
                # then the holding is rebuilt for real
                _trade("2022-12-29", "30", "22.00", "TX_REBUILD", "BUY", "O"),
                _trade("2023-06-01", "-30", "27.00", "TX_SELL_2023", "SELL", "C"),
            ],
            positions_start_data=[_position("30", "690.00", "23.00", "661.00")],
            positions_end_data=[],
            custom_rate_provider=mock_provider,
            tax_year=2023,
        )

        assert len(results.realized_gains_losses) == 1
        rgl = results.realized_gains_losses[0]
        # The real purchase, not a lot dated 2022-12-31.
        assert rgl.acquisition_date == "2022-12-29", rgl.acquisition_date

    def test_an_over_reconstruction_keeps_the_newest_lots(self, mock_config_paths):
        """
        Where the reconstruction exceeds the report, the survivors are the NEWEST.

        The excess means a disposal the input does not contain, and FIFO
        consumes oldest-first, so the units still held are the ones acquired
        last. Filling from the oldest end — what the code did before — returns
        the wrong lot the moment the ledger holds more than one.

        `SOY_H_001` and `SOY_H_002` also cover over-reconstruction, but each
        holds a single lot, so either end returns the same answer. This holds
        two.
        """
        mock_provider = MockECBExchangeRateProvider(foreign_to_eur_init_value=Decimal("1.0"))

        results = self._run_pipeline(
            trades_data=[
                _trade("2022-03-01", "50", "10.00", "TX_OLD", "BUY", "O"),
                _trade("2022-09-01", "50", "18.00", "TX_NEW", "BUY", "O"),
                # The disposal of the older 50 is absent from the input; the broker
                # nonetheless reports only 50 held at the close of 2022.
                _trade("2023-04-01", "-50", "21.00", "TX_SELL_2023", "SELL", "C"),
            ],
            positions_start_data=[_position("50", "1000.00", "20.00", "901.00")],
            positions_end_data=[],
            custom_rate_provider=mock_provider,
            tax_year=2023,
        )

        assert len(results.realized_gains_losses) == 1
        rgl = results.realized_gains_losses[0]
        assert rgl.acquisition_date == "2022-09-01", rgl.acquisition_date
