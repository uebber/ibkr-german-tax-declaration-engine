# src/utils/exchange_rate_provider.py
import datetime
import json
import logging
import os
from decimal import Decimal
from typing import Dict, Optional, Tuple, Set # Added Set for prefetch_rates type hint

import requests

logger = logging.getLogger(__name__)

# Default constants if not overridden by constructor arguments
DEFAULT_ECB_API_URL_TEMPLATE = "https://data-api.ecb.europa.eu/service/data/EXR/D.{currency_code}.EUR.SP00.A?startPeriod={start_date_str}&endPeriod={end_date_str}&format=jsondata"
DEFAULT_MAX_FALLBACK_DAYS = 7
DEFAULT_REQUEST_TIMEOUT_SECONDS = 15
DEFAULT_CURRENCY_CODE_MAPPING: Dict[str, str] = {
    "CNH": "CNY",
}


class ExchangeRateProvider:
    """
    Abstract base class for exchange rate providers.
    Defines the interface for fetching exchange rates.
    """
    def get_rate(self, date_of_conversion: datetime.date, currency_code: str) -> Optional[Decimal]:
        """
        Gets the exchange rate for a given currency against EUR for a specific date.
        Rate should be expressed as: 1 unit of Foreign Currency = X EUR (if base is foreign)
        OR X units of Foreign Currency = 1 EUR (if base is EUR, which is ECB's way).
        The CurrencyConverter class expects the ECB's way: Foreign Currency units per 1 EUR.
        """
        raise NotImplementedError("Subclasses must implement get_rate")

    def prefetch_rates(self, start_date: datetime.date, end_date: datetime.date, currencies: Set[str]):
        """
        Optional method to prefetch a range of rates to optimize repeated calls.
        Subclasses can implement this if their backend supports bulk queries.
        """
        logger.debug(f"{self.__class__.__name__} does not implement prefetch_rates or it's a no-op for this provider.")
        pass # Default implementation is a no-op

    def get_currency_code_mapping(self) -> Dict[str, str]:
        """Returns the currency code mapping used by the provider."""
        raise NotImplementedError("Subclasses must implement get_currency_code_mapping")

    def get_max_fallback_days(self) -> int:
        """Returns the maximum number of fallback days configured for the provider."""
        raise NotImplementedError("Subclasses must implement get_max_fallback_days")


class ECBExchangeRateProvider(ExchangeRateProvider):
    def __init__(self,
                 cache_file_path: str = "cache/ecb_exchange_rates.json",
                 api_url_template_override: Optional[str] = None,
                 max_fallback_days_override: Optional[int] = None,
                 currency_code_mapping_override: Optional[Dict[str, str]] = None,
                 request_timeout_seconds_override: Optional[int] = None):
        super().__init__() # Call to parent constructor if ExchangeRateProvider had one
        self.cache_file_path = cache_file_path
        self.api_url_template = api_url_template_override or DEFAULT_ECB_API_URL_TEMPLATE
        self.max_fallback_days = max_fallback_days_override if max_fallback_days_override is not None else DEFAULT_MAX_FALLBACK_DAYS
        self.currency_code_mapping = currency_code_mapping_override if currency_code_mapping_override is not None else DEFAULT_CURRENCY_CODE_MAPPING.copy()
        self.request_timeout_seconds = request_timeout_seconds_override or DEFAULT_REQUEST_TIMEOUT_SECONDS
        
        self.rates_cache: Dict[str, Dict[str, Optional[str]]] = {} # Date string -> {Currency Code -> Rate String or None for failure}
        self._load_cache()

    def _load_cache(self):
        if os.path.exists(self.cache_file_path):
            try:
                with open(self.cache_file_path, 'r', encoding='utf-8') as f:
                    self.rates_cache = json.load(f)
                loaded_rate_count = sum(1 for date_rates in self.rates_cache.values() for rate_val in date_rates.values() if rate_val is not None)
                loaded_failure_markers = sum(1 for date_rates in self.rates_cache.values() for rate_val in date_rates.values() if rate_val is None)
                logger.info(f"Loaded {loaded_rate_count} exchange rates and {loaded_failure_markers} failure markers from {self.cache_file_path}")
            except json.JSONDecodeError:
                logger.error(f"Error decoding JSON from {self.cache_file_path}. Starting with an empty cache.")
                self.rates_cache = {}
            except Exception as e:
                logger.error(f"Error loading exchange rate cache from {self.cache_file_path}: {e}. Starting with an empty cache.")
                self.rates_cache = {}
        else:
            logger.info(f"Exchange rate cache file {self.cache_file_path} not found. Will create a new one if rates are fetched.")
            self.rates_cache = {}
        
        cache_dir = os.path.dirname(self.cache_file_path)
        if cache_dir: # Ensure directory exists only if path includes a directory
            os.makedirs(cache_dir, exist_ok=True)


    def _save_cache(self):
        try:
            with open(self.cache_file_path, 'w', encoding='utf-8') as f:
                json.dump(self.rates_cache, f, indent=2, ensure_ascii=False)
            logger.debug(f"Saved exchange rate cache to {self.cache_file_path}")
        except Exception as e:
            logger.error(f"Error saving exchange rate cache to {self.cache_file_path}: {e}")

    def _get_effective_currency_code(self, currency_code: str) -> str:
        return self.currency_code_mapping.get(currency_code.upper(), currency_code.upper())

    def _fetch_rate_from_ecb(self, query_date: datetime.date, original_currency_code: str) -> Optional[Tuple[Decimal, datetime.date]]:
        effective_currency_code = self._get_effective_currency_code(original_currency_code)
        date_str = query_date.strftime("%Y-%m-%d")
        
        url = self.api_url_template.format(currency_code=effective_currency_code, start_date_str=date_str, end_date_str=date_str)
        
        logger.debug(f"Attempting ECB fetch for {effective_currency_code} (original: {original_currency_code}) on {date_str} from URL: {url}")
        response = None
        try:
            response = requests.get(url, timeout=self.request_timeout_seconds, headers={'Accept': 'application/json'})
            response.raise_for_status()

            if not response.content:
                logger.info(f"ECB API returned an empty response for {effective_currency_code} on {date_str}. No data for this day.")
                return None

            data = response.json()
            
            if not data.get("dataSets") or not data["dataSets"][0].get("series"):
                logger.warning(f"ECB API response for {effective_currency_code} on {date_str} lacks 'dataSets' or 'series'. Response snippet: {str(data)[:200]}")
                return None

            series = data["dataSets"][0]["series"]
            if not series: # This means no data for the currency AT ALL in the series object
                logger.info(f"No series data in ECB response for {effective_currency_code} on {date_str} (currency might be invalid or not tracked for this period).")
                return None

            # series_key usually is like '0:USD:EUR:SP00:A'
            # If the currency code is invalid for ECB, series might be empty or the key construction fails.
            # However, the API usually returns 404 earlier if the currency is completely unknown.
            # If it's a valid currency but no data for the day, observations would be missing.
            series_key = list(series.keys())[0] # Assumes there's always at least one series if 'series' itself is not empty
            observations = series[series_key].get("observations")

            if not observations:
                logger.info(f"No 'observations' in ECB response for {effective_currency_code} on {date_str}.")
                return None
            
            obs_dim_values = data.get("structure", {}).get("dimensions", {}).get("observation", [])
            if not obs_dim_values:
                 logger.warning(f"ECB API response for {effective_currency_code} on {date_str} lacks 'structure.dimensions.observation'.")
                 return None

            for obs_struct_item in obs_dim_values:
                if obs_struct_item.get("id") == "TIME_PERIOD":
                    for i, time_period_value_obj in enumerate(obs_struct_item.get("values", [])):
                        actual_obs_date_str = time_period_value_obj.get("id")
                        if actual_obs_date_str == date_str: # We are looking for an exact match for the queried date
                            observation_key_for_date = str(i) # The key in observations dict is the index as a string
                            if observation_key_for_date in observations:
                                rate_value_list = observations[observation_key_for_date]
                                if rate_value_list and isinstance(rate_value_list[0], (int, float, str)):
                                    try:
                                        rate_decimal = Decimal(str(rate_value_list[0])) # Initialize Decimal from string
                                        actual_date = datetime.datetime.strptime(actual_obs_date_str, "%Y-%m-%d").date()
                                        logger.info(f"ECB rate successfully fetched for {effective_currency_code} (orig: {original_currency_code}) on {actual_date}: {rate_decimal}")
                                        return rate_decimal, actual_date
                                    except ValueError:
                                        logger.error(f"Could not convert rate value '{rate_value_list[0]}' to Decimal for {effective_currency_code} on {date_str}.")
                                        return None
                            # If key not in observations, it means no data for this specific date.
                            logger.info(f"Rate for {effective_currency_code} on {date_str} (observation index {observation_key_for_date}) not present in 'observations' dict.")
                            return None
            
            logger.info(f"Rate for {effective_currency_code} (orig: {original_currency_code}) on {date_str} not found: TIME_PERIOD dimension did not match or no corresponding observation value.")
            return None

        except requests.exceptions.HTTPError as http_err:
            response_text = http_err.response.text[:200] if http_err.response else "No response body"
            if http_err.response is not None and http_err.response.status_code == 404:
                 logger.warning(f"ECB API returned 404 (Not Found) for {effective_currency_code} (orig: {original_currency_code}) on {date_str}. URL: {url}. Response: {response_text}")
            else:
                 logger.error(f"HTTP error occurred while fetching rate for {effective_currency_code} (orig: {original_currency_code}) on {date_str}: {http_err}. URL: {url}. Response: {response_text}")
        except json.JSONDecodeError as json_err:
            response_text_on_json_error = response.text[:200] if response is not None else "No response object"
            logger.error(f"JSONDecodeError parsing ECB response for {effective_currency_code} (orig: {original_currency_code}) on {date_str}: {json_err}. Response text: '{response_text_on_json_error}'. URL: {url}")
        except requests.exceptions.RequestException as req_err:
            logger.error(f"Request error occurred while fetching rate for {effective_currency_code} (orig: {original_currency_code}) on {date_str}: {req_err}. URL: {url}")
        except (KeyError, IndexError, TypeError) as parse_err: # Catch issues from malformed/unexpected JSON structure
            response_data_for_logging = "Response content unavailable or not valid JSON"
            if response is not None and response.content:
                try: response_data_for_logging = str(response.json())[:200] # Try to log snippet of JSON
                except json.JSONDecodeError: response_data_for_logging = response.text[:200] if hasattr(response, 'text') else "Non-JSON response content" # Log raw text if not JSON
            logger.error(f"Error parsing ECB API JSON structure for {effective_currency_code} (orig: {original_currency_code}) on {date_str}: {parse_err}. Response data snippet: {response_data_for_logging}")
        
        return None # General failure exit

    def get_rate(self, date_of_conversion: datetime.date, currency_code: str) -> Optional[Decimal]:
        original_currency_code_upper = currency_code.upper()
        if original_currency_code_upper == "EUR":
            return Decimal("1.0")

        effective_currency_code_for_ecb = self._get_effective_currency_code(original_currency_code_upper)
        original_date_str = date_of_conversion.strftime("%Y-%m-%d")

        for i in range(self.max_fallback_days + 1): # Loop from 0 (today) up to max_fallback_days
            current_search_date = date_of_conversion - datetime.timedelta(days=i)
            current_search_date_str = current_search_date.strftime("%Y-%m-%d")
            cache_updated_this_iteration = False # Flag to save cache only if modified

            # Check cache first for the current_search_date
            if current_search_date_str in self.rates_cache:
                if effective_currency_code_for_ecb in self.rates_cache[current_search_date_str]:
                    cached_rate_str = self.rates_cache[current_search_date_str][effective_currency_code_for_ecb]
                    if cached_rate_str is None: # Explicit None means previously fetched and failed
                        logger.debug(f"Rate for {effective_currency_code_for_ecb} on {current_search_date_str} (fallback {i} days for {original_date_str}) previously determined as unavailable. Skipping API call.")
                        # If it's the first day (i=0) and it's None, we might still want to retry if policies change,
                        # but for now, if it's None, it's None. For subsequent fallback days, continue to next older day.
                        if i == 0: pass # Allow to proceed to API call for day 0 if it was None (e.g. to refresh if cache logic changes)
                                        # Or, to be strict: if None, then treat as unavailable for THIS search date.
                        else: # For fallback days, if it's cached as None, move to the next older day.
                            continue 
                    else: # Cached rate string exists
                        logger.debug(f"Rate for {effective_currency_code_for_ecb} on {current_search_date_str} (fallback {i} days for {original_date_str}) from cache: {cached_rate_str}")
                        try:
                            return Decimal(cached_rate_str) # Initialize Decimal from string
                        except ValueError:
                            logger.error(f"Invalid rate format '{cached_rate_str}' in cache for {effective_currency_code_for_ecb} on {current_search_date_str}. Removing from cache.")
                            # Remove the bad entry and allow fetch attempt
                            del self.rates_cache[current_search_date_str][effective_currency_code_for_ecb] 
                            cache_updated_this_iteration = True # Mark cache as modified
            
            # If not in cache, or bad entry removed, or day 0 and was None (and we decide to retry day 0 if None)
            # Attempt to fetch from ECB
            logger.debug(f"Cache miss or no explicit failure marker for {effective_currency_code_for_ecb} on {current_search_date_str} (fallback {i} days for {original_date_str}). Attempting fetch.")
            fetched_data = self._fetch_rate_from_ecb(current_search_date, original_currency_code_upper) # Pass original code for logging in _fetch
            
            # Ensure date entry exists in cache before trying to add currency rate to it
            if current_search_date_str not in self.rates_cache:
                self.rates_cache[current_search_date_str] = {}

            if fetched_data:
                rate_decimal, actual_rate_date = fetched_data
                # The ECB API for a specific date query (startPeriod=date, endPeriod=date)
                # should only return data for that date if available.
                # So, actual_rate_date should ideally be current_search_date.
                if actual_rate_date != current_search_date:
                    # This case should be rare if API behaves as expected for specific date queries.
                    # If it happens, it implies the API might be returning the closest available past date automatically.
                    logger.warning(f"ECB returned rate for {actual_rate_date} when {current_search_date} was queried for {effective_currency_code_for_ecb}. Using returned date's rate. Caching under {current_search_date_str}.")
                
                # Cache the fetched rate (as string) under the date we searched for (current_search_date_str)
                # This ensures that if we search for date X and find a rate (even if it's for X-1),
                # that rate for X-1 is considered "the rate for X" in this fallback logic.
                if self.rates_cache[current_search_date_str].get(effective_currency_code_for_ecb) != str(rate_decimal): # Avoid rewriting if same
                    self.rates_cache[current_search_date_str][effective_currency_code_for_ecb] = str(rate_decimal)
                    cache_updated_this_iteration = True
                
                # If the actual date of the rate is suitable (i.e., on or before the target conversion date)
                # and within the fallback window logic (which is handled by the loop `i`), return it.
                # The crucial part is that `_fetch_rate_from_ecb` was called for `current_search_date`.
                if actual_rate_date <= date_of_conversion: # Redundant check, loop ensures this for current_search_date
                     if cache_updated_this_iteration: self._save_cache()
                     logger.info(f"Using rate {rate_decimal} for {effective_currency_code_for_ecb} from {actual_rate_date} (target: {original_date_str}, fallback {i} days).")
                     return rate_decimal
            else: # Fetch failed or no data for current_search_date
                # Mark this date and currency as "failed to fetch" by storing None
                # This avoids repeated API calls for the same missing rate within the same provider instance session.
                is_already_marked_none = (
                    effective_currency_code_for_ecb in self.rates_cache[current_search_date_str] and
                    self.rates_cache[current_search_date_str][effective_currency_code_for_ecb] is None
                )
                if not is_already_marked_none: # Avoid rewriting if already None
                    self.rates_cache[current_search_date_str][effective_currency_code_for_ecb] = None 
                    cache_updated_this_iteration = True
                    logger.debug(f"Fetch failed for {effective_currency_code_for_ecb} on {current_search_date_str}. Cached as None.")

            # Save cache if it was modified in this iteration
            if cache_updated_this_iteration:
                self._save_cache()
        
        # If loop completes without returning a rate
        logger.warning(f"Failed to get exchange rate for {effective_currency_code_for_ecb} (original: {original_currency_code_upper}) for target date {original_date_str} after checking back {self.max_fallback_days} days.")
        return None

    def get_currency_code_mapping(self) -> Dict[str, str]:
        return self.currency_code_mapping.copy() # Return a copy

    def get_max_fallback_days(self) -> int:
        return self.max_fallback_days

    # prefetch_rates is not naturally suited for this specific ECB API structure (one currency per call).
    # A possible implementation would loop through currencies and date ranges,
    # but it might be inefficient and hit API rate limits.
    # For now, it will use the base class's no-op.
    # If implemented, it should populate self.rates_cache.
