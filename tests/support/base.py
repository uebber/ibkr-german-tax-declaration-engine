# tests/support/base.py
import os
import pytest
from decimal import Decimal
from typing import Any, Optional, List, Dict, Tuple

# Application components
from src.pipeline_runner import run_core_processing_pipeline, ProcessingOutput
from src.utils.exchange_rate_provider import ExchangeRateProvider  # Base class for mock
from src.domain.results import RealizedGainLoss
from src.domain.assets import Asset
from src.identification.asset_resolver import AssetResolver
# Ensure AssetClassifier is imported for the dummy instantiation
from src.classification.asset_classifier import AssetClassifier

# Test helpers
from tests.support.csv_creators import (
    create_trades_csv_string, create_positions_csv_string,
    create_cash_transactions_csv_string, create_corporate_actions_csv_string
)
from tests.support.expected import ScenarioExpectedOutput

class FifoTestCaseBase:
    """
    Base class for FIFO test cases.
    Handles common setup like creating CSV files and running the pipeline.
    """

    @pytest.fixture(autouse=True)
    def setup_test_paths_and_config(self, mock_config_paths, monkeypatch):
        """Makes mocked config paths available and patches TAX_YEAR for the test instance."""
        self.config_paths = mock_config_paths
        
        # Ensure cache files don't exist from previous partial runs if they are file based
        classification_cache_path = self.config_paths.get("classification_cache")
        ecb_cache_path = self.config_paths.get("ecb_cache")

        if classification_cache_path and os.path.exists(classification_cache_path):
            os.remove(classification_cache_path)
        if ecb_cache_path and os.path.exists(ecb_cache_path):
            os.remove(ecb_cache_path)
        
        # Store original tax year to reset it later if patched globally
        try:
            from src import config as app_config
            self.original_tax_year = app_config.TAX_YEAR
        except ImportError:
            self.original_tax_year = 2023 # Fallback
            print("Warning: src.config not found in FifoTestCaseBase setup, using fallback tax year for original_tax_year.")


    def _run_pipeline(self,
                      trades_data: Optional[List[List[Any]]] = None,
                      positions_start_data: Optional[List[List[Any]]] = None,
                      positions_end_data: Optional[List[List[Any]]] = None,
                      cash_transactions_data: Optional[List[List[Any]]] = None,
                      corporate_actions_data: Optional[List[List[Any]]] = None,
                      custom_rate_provider: Optional[ExchangeRateProvider] = None,
                      tax_year: int = 2023, 
                      monkeypatch_global_tax_year: bool = True
                      ) -> ProcessingOutput:
        """
        Helper to write CSV data, run the pipeline, and return results.
        """
        paths = self.config_paths 

        if monkeypatch_global_tax_year:
            try:
                # Use a fresh MonkeyPatch instance for this specific patching action
                mp_tax_year = pytest.MonkeyPatch()
                # Ensure src.config is the target for patching TAX_YEAR
                # This assumes src.config can be imported and patched.
                import src.config as app_config_module_for_tax_year
                mp_tax_year.setattr(app_config_module_for_tax_year, "TAX_YEAR", tax_year, raising=True)
                # Store the monkeypatch instance if you need to undo it specifically, 
                # or rely on pytest's fixture teardown for patches applied via fixtures.
                # For locally created MonkeyPatch, it's good practice to undo if not auto-managed.
                request = getattr(self, 'request', None) # If pytest request object is available
                if request:
                    request.addfinalizer(mp_tax_year.undo)
                else: # If used outside a test function context where request fixture is auto-used.
                    # This scenario is less common for _run_pipeline which is called within tests.
                    # If self.request is not available, manual undo might be needed or rely on test isolation.
                    # For safety, we can store it and undo in a finalizer added to the class or test.
                    # However, monkeypatch applied in a fixture (`mock_config_paths`) is auto-undone.
                    # Here, TAX_YEAR is patched *conditionally* inside a helper method.
                    # The fixture _reset_global_tax_year_after_test handles resetting TAX_YEAR.
                    pass

            except Exception as e:
                print(f"Warning: Could not monkeypatch src.config.TAX_YEAR to {tax_year}: {e}")


        file_map = {
            paths["trades"]: (trades_data, create_trades_csv_string),
            paths["pos_start"]: (positions_start_data, create_positions_csv_string),
            paths["pos_end"]: (positions_end_data, create_positions_csv_string),
            paths["cash"]: (cash_transactions_data, create_cash_transactions_csv_string),
            paths["corp_actions"]: (corporate_actions_data, create_corporate_actions_csv_string),
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
        
        try:
            # Ensure IS_INTERACTIVE_CLASSIFICATION is False for tests
            mp_interactive = pytest.MonkeyPatch()
            try:
                import src.config as app_config_module_interactive
                mp_interactive.setattr(app_config_module_interactive, "IS_INTERACTIVE_CLASSIFICATION", False)
                # If using request fixture, it would handle undo:
                # request = getattr(self, 'request', None)
                # if request: request.addfinalizer(mp_interactive.undo)
            except ImportError:
                print("Warning: Could not import src.config to set IS_INTERACTIVE_CLASSIFICATION for test.")
            except AttributeError:
                 print(f"Warning: Could not set IS_INTERACTIVE_CLASSIFICATION on src.config module.")


            results: ProcessingOutput = run_core_processing_pipeline(
                trades_file_path=paths["trades"],
                cash_transactions_file_path=paths["cash"],
                positions_start_file_path=paths["pos_start"],
                positions_end_file_path=paths["pos_end"],
                corporate_actions_file_path=paths["corp_actions"],
                interactive_classification_mode=False, 
                tax_year_to_process=tax_year, 
                custom_rate_provider=custom_rate_provider
            )
            mp_interactive.undo() # Manually undo if not tied to fixture lifecycle
            return results

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

    @pytest.fixture(autouse=True)
    def _reset_global_tax_year_after_test(self, request):
        """Resets the global TAX_YEAR in src.config after each test method if it was patched."""
        # This fixture uses 'request' to manage teardown, ensuring patches are undone.
        # It stores the original tax year before any test-specific patches in _run_pipeline.
        # It must run after setup_test_paths_and_config which might set self.original_tax_year.
        
        # If _run_pipeline conditionally patches TAX_YEAR, that patch should ideally also be
        # added to pytest's finalizer chain to ensure it's undone.
        # The current _run_pipeline tries to use a local monkeypatch or rely on this fixture.
        
        # Store original tax year at the beginning of the test method's lifecycle
        # Note: self.original_tax_year is already set by setup_test_paths_and_config
        original_year_for_this_test = getattr(self, 'original_tax_year', 2023) # Default if not set

        yield # Test runs here

        # Teardown: Reset TAX_YEAR to its original value for this test instance
        # This ensures that if _run_pipeline changed it, it's restored.
        try:
            mp_teardown = pytest.MonkeyPatch() # Use a new instance for teardown
            # Ensure src.config is the target for patching TAX_YEAR
            import src.config as app_config_module_teardown
            current_patched_year = app_config_module_teardown.TAX_YEAR
            if current_patched_year != original_year_for_this_test:
                 mp_teardown.setattr(app_config_module_teardown, "TAX_YEAR", original_year_for_this_test, raising=True)
            # mp_teardown.undo() # MonkeyPatch.undo() for locally created instances is good practice if not fixture-managed
        except Exception as e:
            print(f"Warning: Could not reset src.config.TAX_YEAR to {original_year_for_this_test}: {e}")
        
        # Clean up monkeypatch instance if stored on self from _run_pipeline (if it was structured to do so)
        # However, _run_pipeline as provided uses local MonkeyPatch instances or this fixture.
        if hasattr(self, '_mp_tax_year_instance_from_run_pipeline'): # Example if _run_pipeline stored its patcher
            self._mp_tax_year_instance_from_run_pipeline.undo()
            delattr(self, '_mp_tax_year_instance_from_run_pipeline')
