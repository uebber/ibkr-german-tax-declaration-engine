# src/identification/declared_vp_provider.py
"""
Interactive, cached provider for the Vorabpauschale a user *declared* per fund per year.

§19 Abs. 1 S. 3 InvStG reduces a fund's disposal gain by the Vorabpauschalen assessed
during the holding period — but the official Anlage KAP-INV instructions (Z53) limit the
deduction to VP that was actually subjected to taxation in the prior years (Z9-13). The
engine cannot know what the user filed in past returns, so it asks (once per fund-year)
and caches the answer.

Cache key is year-specific:  "{asset.get_classification_key()}:{year}"  e.g.
    "ISIN:LU1234567890:2024"
Cache value: the declared gross VP for that year as a decimal string ("0" if the user
declared none). Mirrors the cache/prompt pattern of FundSoyNavProvider.
"""
import json
import logging
import os
from decimal import Decimal, InvalidOperation
from typing import Dict, List, Optional

from src.domain.assets import Asset
from src import config as app_config

logger = logging.getLogger(__name__)


class DeclaredVpProvider:
    def __init__(self, cache_file_path: Optional[str] = None):
        self.cache_file_path = cache_file_path or app_config.DECLARED_VP_CACHE_FILE_PATH
        # key -> declared gross VP (decimal string)
        self.cache: Dict[str, str] = {}
        self.load()

    # -- persistence -------------------------------------------------------
    def load(self):
        if os.path.exists(self.cache_file_path):
            try:
                with open(self.cache_file_path, "r", encoding="utf-8") as f:
                    raw = json.load(f)
                    for key, value in raw.items():
                        self.cache[key] = str(value)
            except json.JSONDecodeError:
                print(f"Error: Could not decode JSON from {self.cache_file_path}. Starting with an empty declared-VP cache.")
            except Exception as e:
                print(f"Error loading declared Vorabpauschale: {e}. Starting with an empty declared-VP cache.")

    def save(self):
        os.makedirs(os.path.dirname(self.cache_file_path), exist_ok=True)
        try:
            with open(self.cache_file_path, "w", encoding="utf-8") as f:
                json.dump(self.cache, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Error saving declared Vorabpauschale: {e}")

    # -- lookup ------------------------------------------------------------
    @staticmethod
    def cache_key(asset: Asset, year: int) -> str:
        return f"{asset.get_classification_key()}:{year}"

    def get_cached(self, asset: Asset, year: int) -> Optional[Decimal]:
        value = self.cache.get(self.cache_key(asset, year))
        if value is None:
            return None
        try:
            return Decimal(value)
        except InvalidOperation:
            return None

    def set(self, asset: Asset, year: int, value: Decimal) -> None:
        """Write (and persist) a value for a fund-year, overwriting any existing entry.

        Used to auto-enter the *computed* current holding-year (V-1) Vorabpauschale — the
        figure the engine places on Anlage KAP-INV Z13 — so it is never prompted for, is
        auditable, and is reused (as a prior year) on future runs.
        """
        self.cache[self.cache_key(asset, year)] = str(value)
        self.save()

    def get_or_prompt(
        self,
        asset: Asset,
        year: int,
        interactive: bool,
        context_lines: Optional[List[str]] = None,
    ) -> Optional[Decimal]:
        """Return the declared gross Vorabpauschale (EUR, vor Teilfreistellung) for the
        given fund and calendar year. Cache hit -> return it without prompting. Cache miss
        + interactive -> prompt and persist (blank -> 0, meaning "not declared"). Cache
        miss + non-interactive -> return None (caller decides how to handle).
        """
        cached = self.get_cached(asset, year)
        if cached is not None:
            return cached

        if not interactive:
            return None

        print("\n--- Erklärte Vorabpauschale benötigt (§19 Abs. 1 S. 3 InvStG) ---")
        print(f"  Fonds: {asset.description or asset.get_classification_key()}")
        print(f"  ISIN: {asset.ibkr_isin or '-'}, Symbol: {asset.ibkr_symbol or '-'}")
        print(
            f"  Beim Verkauf wird der Gewinn um die während der Besitzzeit angesetzten "
            f"Vorabpauschalen gemindert. Wie viel BRUTTO-Vorabpauschale (vor Teilfrei-"
            f"stellung) hast du für DIESEN Fonds im Haltejahr {year} erklärt? Betrag in EUR."
        )
        print(
            f"  Fundstelle: deine Steuererklärung {year + 1} (abgegeben {year + 2}), "
            f"Anlage KAP-INV Zeile 9-13 (dort in EUR ausgewiesen; die VP aus Haltejahr "
            f"{year} steht dort wegen der 1-Jahres-Zuflussregel)."
        )
        for line in (context_lines or []):
            print(f"  {line}")
        raw = input(f"  Erklärte VP Haltejahr {year} in EUR (leer/0 = nichts erklärt): ").strip()
        if not raw:
            value = Decimal("0")
        else:
            raw = raw.replace(",", ".")  # tolerate German decimal comma
            try:
                value = Decimal(raw)
            except InvalidOperation:
                print(f"  '{raw}' is not a valid number; skipping (no deduction for {year}).")
                return None
            if value < Decimal("0"):
                print("  Declared VP cannot be negative; skipping.")
                return None

        self.cache[self.cache_key(asset, year)] = str(value)
        self.save()
        return value
