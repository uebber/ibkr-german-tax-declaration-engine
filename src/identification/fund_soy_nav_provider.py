# src/identification/fund_soy_nav_provider.py
"""
Interactive, cached provider for start-of-year fund NAVs.

For the §18 Abs. 2 InvStG partial-year Vorabpauschale, the Basisertrag of a fund
acquired during the tax year is computed on the fund's redemption price at the
*start of the calendar year* (1 Jan) — not the purchase price. When the fund was
not held on 1 Jan, that NAV is absent from IBKR data and must be supplied by the
user. This provider prompts for it interactively (once) and caches it.

The cache key is year-specific (the 1 Jan NAV differs each year):
    "{asset.get_classification_key()}:{tax_year}"  e.g. "ISIN:IE0001234567:2025"
Cache value: [nav_per_unit_str, currency].

Mirrors the cache/prompt pattern of AssetClassifier.
"""
import json
import logging
import os
from decimal import Decimal, InvalidOperation
from typing import Dict, List, Optional

from src.domain.assets import Asset
from src import config as app_config

logger = logging.getLogger(__name__)


class FundSoyNavProvider:
    def __init__(self, cache_file_path: Optional[str] = None):
        self.cache_file_path = cache_file_path or app_config.FUND_SOY_NAV_CACHE_FILE_PATH
        # key -> [nav_per_unit_str, currency]
        self.nav_cache: Dict[str, List[str]] = {}
        self.load()

    # -- persistence -------------------------------------------------------
    def load(self):
        if os.path.exists(self.cache_file_path):
            try:
                with open(self.cache_file_path, "r", encoding="utf-8") as f:
                    raw = json.load(f)
                    for key, value in raw.items():
                        if isinstance(value, list) and len(value) == 2:
                            self.nav_cache[key] = [str(value[0]), str(value[1])]
            except json.JSONDecodeError:
                print(f"Error: Could not decode JSON from {self.cache_file_path}. Starting with an empty NAV cache.")
            except Exception as e:
                print(f"Error loading fund SoY NAVs: {e}. Starting with an empty NAV cache.")

    def save(self):
        os.makedirs(os.path.dirname(self.cache_file_path), exist_ok=True)
        try:
            with open(self.cache_file_path, "w", encoding="utf-8") as f:
                json.dump(self.nav_cache, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Error saving fund SoY NAVs: {e}")

    # -- lookup ------------------------------------------------------------
    @staticmethod
    def cache_key(asset: Asset, tax_year: int) -> str:
        return f"{asset.get_classification_key()}:{tax_year}"

    def get_cached(self, asset: Asset, tax_year: int) -> Optional[Decimal]:
        entry = self.nav_cache.get(self.cache_key(asset, tax_year))
        if not entry:
            return None
        try:
            return Decimal(entry[0])
        except (InvalidOperation, IndexError):
            return None

    def get_or_prompt(
        self,
        asset: Asset,
        tax_year: int,
        interactive: bool,
        context_lines: Optional[List[str]] = None,
    ) -> Optional[Decimal]:
        """
        Return the per-unit start-of-year NAV (in the fund's currency) for the
        given fund and tax year. Cache hit -> return it without prompting.
        Cache miss + interactive -> prompt and persist. Cache miss +
        non-interactive -> return None (caller decides how to handle).
        """
        cached = self.get_cached(asset, tax_year)
        if cached is not None:
            return cached

        if not interactive:
            return None

        currency = asset.vp_soy_nav_currency or asset.currency or "EUR"
        print("\n--- Start-of-Year NAV Needed (Vorabpauschale) ---")
        print(f"  Fund: {asset.description or asset.get_classification_key()}")
        print(f"  ISIN: {asset.ibkr_isin or '-'}, Symbol: {asset.ibkr_symbol or '-'}")
        print(f"  Currency: {currency}")
        for line in (context_lines or []):
            print(f"  {line}")
        print(
            f"  Enter the fund's redemption price (NAV) PER UNIT on the first trading "
            f"day of {tax_year}, in {currency}."
        )
        raw = input("  SoY NAV per unit (blank to skip -> VP not computed): ").strip()
        if not raw:
            logger.warning(
                "No SoY NAV provided for %s (%d); Vorabpauschale will not be computed.",
                asset.get_classification_key(), tax_year,
            )
            return None

        raw = raw.replace(",", ".")  # tolerate German decimal comma
        try:
            nav = Decimal(raw)
        except InvalidOperation:
            print(f"  '{raw}' is not a valid number; skipping.")
            return None
        if nav <= Decimal("0"):
            print("  NAV must be positive; skipping.")
            return None

        self.nav_cache[self.cache_key(asset, tax_year)] = [str(nav), currency]
        self.save()
        return nav
