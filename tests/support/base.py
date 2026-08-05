# tests/support/base.py
import os
import pytest
from decimal import Decimal
from typing import Any, Optional, List, Dict, Tuple

# Application components
from src.pipeline_runner import run_core_processing_pipeline, ProcessingOutput
from src.processing.data_gaps import DataGapError
from src.utils.exchange_rate_provider import ExchangeRateProvider  # Base class for mock
from src.domain.results import RealizedGainLoss
from src.domain.assets import Asset
from src.identification.asset_resolver import AssetResolver
# Ensure AssetClassifier is imported for the dummy instantiation
from src.classification.asset_classifier import AssetClassifier

# Test helpers
from tests.support.csv_creators import (
    create_trades_csv_string, create_positions_csv_string,
    create_cash_transactions_csv_string, create_corporate_actions_csv_string,
    create_cash_balance_csv_string
)
from tests.support.expected import ScenarioExpectedOutput

class FifoTestCaseBase:
    """
    Base class for FIFO test cases.
    Handles common setup like creating CSV files and running the pipeline.
    """

    @pytest.fixture(autouse=True)
    def setup_test_paths_and_config(self, mock_config_paths, monkeypatch):
        """Makes mocked config paths available and keeps pytest's per-test monkeypatch
        so _run_pipeline can patch global config with guaranteed undo at test teardown.

        Any patch applied through self._monkeypatch is reverted by pytest when THIS test
        ends — global state (e.g. src.config.TAX_YEAR) can never leak into later tests
        or other modules. (The previous hand-rolled MonkeyPatch/teardown pair leaked the
        patched TAX_YEAR across module boundaries, making test results order-dependent.)"""
        self.config_paths = mock_config_paths
        self._monkeypatch = monkeypatch

        # Ensure cache files don't exist from previous partial runs if they are file based
        classification_cache_path = self.config_paths.get("classification_cache")
        ecb_cache_path = self.config_paths.get("ecb_cache")

        if classification_cache_path and os.path.exists(classification_cache_path):
            os.remove(classification_cache_path)
        if ecb_cache_path and os.path.exists(ecb_cache_path):
            os.remove(ecb_cache_path)


    def seed_classification(self, asset_key: str, category: str,
                            fund_type: str = "NONE", note: str = "test fixture"):
        """Provide a user classification as test INPUT (what the user would
        answer interactively), written to this test's own temp cache — tests
        must never depend on the developer's real cache/ files."""
        import json, os
        path = self.config_paths["classification_cache"]
        os.makedirs(os.path.dirname(path), exist_ok=True)
        cache = {}
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as fh:
                cache = json.load(fh)
        cache[asset_key] = [category, fund_type, note]
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(cache, fh)

    def _run_pipeline(self,
                      trades_data: Optional[List[List[Any]]] = None,
                      positions_start_data: Optional[List[List[Any]]] = None,
                      positions_end_data: Optional[List[List[Any]]] = None,
                      positions_prior_start_data: Optional[List[List[Any]]] = None,
                      positions_prior_end_data: Optional[List[List[Any]]] = None,
                      cash_transactions_data: Optional[List[List[Any]]] = None,
                      corporate_actions_data: Optional[List[List[Any]]] = None,
                      cash_balance_data: Optional[List[List[Any]]] = None,
                      custom_rate_provider: Optional[ExchangeRateProvider] = None,
                      tax_year: int = 2023,
                      monkeypatch_global_tax_year: bool = True
                      ) -> ProcessingOutput:
        """
        Helper to write CSV data, run the pipeline, and return results.
        """
        paths = self.config_paths 

        if monkeypatch_global_tax_year:
            # Patch via the per-test monkeypatch fixture: pytest reverts it when THIS test
            # ends, so the patched year cannot leak into later tests or other modules.
            import src.config as app_config_module_for_tax_year
            self._monkeypatch.setattr(app_config_module_for_tax_year, "TAX_YEAR", tax_year, raising=True)

        file_map = {
            paths["trades"]: (trades_data, create_trades_csv_string),
            paths["pos_start"]: (positions_start_data, create_positions_csv_string),
            paths["pos_end"]: (positions_end_data, create_positions_csv_string),
            paths["cash"]: (cash_transactions_data, create_cash_transactions_csv_string),
            paths["corp_actions"]: (corporate_actions_data, create_corporate_actions_csv_string),
            paths["cash_balance"]: (cash_balance_data, create_cash_balance_csv_string),
        }

        for path, (data, creator_func) in file_map.items():
            if data is not None:
                with open(path, "w", encoding="utf-8-sig") as f:
                    f.write(creator_func(data))
            else: 
                # Ensure directory exists for the cache file path
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "w", encoding="utf-8-sig") as f:
                    f.write(creator_func([])) # Write empty CSV (headers only)

        # Prior-year snapshots are written ONLY when the scenario supplies them, and the
        # path is passed only then. An empty file is not equivalent to an absent one here:
        # the engine reads "a prior-year snapshot was supplied" from the presence of the
        # path, and a headers-only file would suppress the FAIL_FAST gap that a genuinely
        # missing snapshot must raise.
        prior_paths = {"positions_prior_start_file_path": None,
                       "positions_prior_end_file_path": None}
        for key, path_key, data in (
            ("positions_prior_start_file_path", "pos_prior_start", positions_prior_start_data),
            ("positions_prior_end_file_path", "pos_prior_end", positions_prior_end_data),
        ):
            if data is not None:
                with open(paths[path_key], "w", encoding="utf-8-sig") as f:
                    f.write(create_positions_csv_string(data))
                prior_paths[key] = paths[path_key]

        try:
            # Ensure IS_INTERACTIVE_CLASSIFICATION is False for tests (auto-undone at teardown)
            import src.config as app_config_module_interactive
            self._monkeypatch.setattr(app_config_module_interactive, "IS_INTERACTIVE_CLASSIFICATION", False)

            results: ProcessingOutput = run_core_processing_pipeline(
                trades_file_path=paths["trades"],
                cash_transactions_file_path=paths["cash"],
                positions_start_file_path=paths["pos_start"],
                positions_end_file_path=paths["pos_end"],
                corporate_actions_file_path=paths["corp_actions"],
                interactive_classification_mode=False,
                tax_year_to_process=tax_year,
                custom_rate_provider=custom_rate_provider,
                cash_balance_file_path=paths["cash_balance"],
                **prior_paths,
            )
            return results

        except DataGapError:
            # A fail-fast data gap is a deliberate engine verdict, not a harness
            # failure: scenarios that specify an abort (e.g. the Group 3 EoY
            # reconciliation mismatches) assert it with pytest.raises. Converting it
            # into pytest.fail here would make that outcome unassertable.
            raise
        except Exception as e:
            print(f"Error during pipeline execution in test: {e}")
            import traceback
            traceback.print_exc()
            
            # Corrected AssetClassifier instantiation
            dummy_classifier = AssetClassifier(cache_file_path=paths.get("classification_cache"))
            dummy_resolver = AssetResolver(asset_classifier=dummy_classifier)
            
            # Ensure ProcessingOutput is instantiated with all required fields,
            # even if some are empty lists for failure cases.
            # The original ProcessingOutput definition was:
            # realized_gains_losses, vorabpauschale_items, processed_income_events,
            # all_financial_events_enriched, asset_resolver, eoy_mismatch_error_count
            # The final_assets_by_id was part of it but removed and accessed via asset_resolver.
            pytest.fail(f"Pipeline execution failed: {e}")
            # The line below is unreachable due to pytest.fail but makes linters/type checkers happy.
            return ProcessingOutput([], [], [], [], dummy_resolver, -1)


    def assert_results(self,
                       actual_results: ProcessingOutput,
                       expected_test_outcome: ScenarioExpectedOutput):
        """
        Compares actual processing results with expected results.
        'expected_test_outcome' is an instance of ScenarioExpectedOutput.
        """
        
        assert actual_results.eoy_mismatch_error_count == expected_test_outcome.expected_eoy_mismatch_error_count, \
            (f"EOY mismatch error count: Expected {expected_test_outcome.expected_eoy_mismatch_error_count}, "
             f"Got {actual_results.eoy_mismatch_error_count}")

        assert len(actual_results.realized_gains_losses) == len(expected_test_outcome.expected_rgls), \
            (f"Number of RGLs: Expected {len(expected_test_outcome.expected_rgls)}, "
             f"Got {len(actual_results.realized_gains_losses)}. "
             f"Actual RGLs: {actual_results.realized_gains_losses}")

        matched_actual_rgl_indices = [False] * len(actual_results.realized_gains_losses)
        for i_expected, expected_rgl in enumerate(expected_test_outcome.expected_rgls):
            found_match_for_expected = False
            for i_actual, actual_rgl_obj in enumerate(actual_results.realized_gains_losses):
                if matched_actual_rgl_indices[i_actual]:
                    continue
                if not isinstance(actual_rgl_obj, RealizedGainLoss):
                     pytest.fail(f"Actual RGL item is not of type RealizedGainLoss: {type(actual_rgl_obj)}")

                if expected_rgl.matches(actual_rgl_obj, actual_results.asset_resolver):
                    matched_actual_rgl_indices[i_actual] = True
                    found_match_for_expected = True
                    break
            
            assert found_match_for_expected, \
                f"No matching actual RGL found for expected RGL: {expected_rgl}. \n" \
                f"Actual RGLs were: {actual_results.realized_gains_losses}"
        
        unmatched_actual_rgl_count = len([m for m in matched_actual_rgl_indices if not m])
        if unmatched_actual_rgl_count > 0 :
             unmatched_details = [actual_results.realized_gains_losses[i] for i, matched in enumerate(matched_actual_rgl_indices) if not matched]
             pytest.fail(f"Found {unmatched_actual_rgl_count} actual RGL(s) that were not matched by any expected RGL: {unmatched_details}")

        all_actual_assets = list(actual_results.asset_resolver.assets_by_internal_id.values())
        for expected_eoy_state in expected_test_outcome.expected_eoy_states:
            found_asset_for_eoy_check = False
            for actual_asset_obj in all_actual_assets:
                if not isinstance(actual_asset_obj, Asset): 
                    pytest.fail(f"Item in asset_resolver.assets_by_internal_id is not an Asset: {type(actual_asset_obj)}")
                
                temp_identifier_type, temp_identifier_value = expected_eoy_state.asset_identifier.split(":", 1) if ":" in expected_eoy_state.asset_identifier else ("SYMBOL", expected_eoy_state.asset_identifier)
                
                preliminary_match = False
                if temp_identifier_type == "ISIN" and actual_asset_obj.ibkr_isin == temp_identifier_value:
                    preliminary_match = True
                elif temp_identifier_type == "CONID" and actual_asset_obj.ibkr_conid == temp_identifier_value:
                    preliminary_match = True
                elif temp_identifier_type == "SYMBOL": 
                    if actual_asset_obj.ibkr_symbol == temp_identifier_value:
                         preliminary_match = True
                    elif any(alias.upper() == f"SYMBOL:{temp_identifier_value.upper()}" for alias in actual_asset_obj.aliases):
                         preliminary_match = True
                elif str(actual_asset_obj.internal_asset_id) == expected_eoy_state.asset_identifier : 
                     preliminary_match = True

                if preliminary_match:
                    if expected_eoy_state.matches(actual_asset_obj): 
                        found_asset_for_eoy_check = True
                        break 
            
            assert found_asset_for_eoy_check, \
                (f"Asset for EOY state check (identifier: {expected_eoy_state.asset_identifier}) "
                 f"not found or did not match in actual EOY asset states. "
                 f"Checked against {len(all_actual_assets)} assets with details: {[(a.internal_asset_id, a.get_classification_key() if hasattr(a, 'get_classification_key') else 'N/A', a.eoy_quantity) for a in all_actual_assets]}.")

