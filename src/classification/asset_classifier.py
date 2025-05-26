# src/classification/asset_classifier.py
import json
import os
from typing import Dict, Optional, Tuple, List

from src.domain.assets import (
    Asset, InvestmentFund, Stock, Bond, Option, Cfd, PrivateSaleAsset, CashBalance # Changed Section23EstgAsset to PrivateSaleAsset
)
from src.domain.enums import AssetCategory, InvestmentFundType
from src import config as app_config # Added import

class AssetClassifier:
    def __init__(self, cache_file_path: Optional[str] = None): # Modified signature
        if cache_file_path is None:
            self.cache_file_path = app_config.CLASSIFICATION_CACHE_FILE_PATH # Use config
        else:
            self.cache_file_path = cache_file_path

        self.classifications_cache: Dict[str, Tuple[str, str, str]] = {}
        self._dialog_options: List[Tuple[str, AssetCategory, InvestmentFundType]] = [
            ("Aktienfonds (KAP-INV)", AssetCategory.INVESTMENT_FUND, InvestmentFundType.AKTIENFONDS),
            ("Mischfonds (KAP-INV)", AssetCategory.INVESTMENT_FUND, InvestmentFundType.MISCHFONDS),
            ("Immobilienfonds (KAP-INV)", AssetCategory.INVESTMENT_FUND, InvestmentFundType.IMMOBILIENFONDS),
            ("Auslands-Immobilienfonds (KAP-INV)", AssetCategory.INVESTMENT_FUND, InvestmentFundType.AUSLANDS_IMMOBILIENFONDS),
            ("Sonstige Investmentfonds (KAP-INV)", AssetCategory.INVESTMENT_FUND, InvestmentFundType.SONSTIGE_FONDS),
            ("§23 EStG / Anlage SO (z.B. Gold-ETC, Krypto-ETP)", AssetCategory.PRIVATE_SALE_ASSET, InvestmentFundType.NONE), # Changed from SECTION_23_ESTG_ASSET
            ("Aktie (Anlage KAP)", AssetCategory.STOCK, InvestmentFundType.NONE),
            ("Anleihe (Anlage KAP)", AssetCategory.BOND, InvestmentFundType.NONE),
            ("Option/Termingeschäft (Anlage KAP)", AssetCategory.OPTION, InvestmentFundType.NONE),
            ("CFD (Anlage KAP)", AssetCategory.CFD, InvestmentFundType.NONE),
            ("Cash / Währungssaldo (ECHT)", AssetCategory.CASH_BALANCE, InvestmentFundType.NONE), # Clarified for interactive prompt
            ("Devisenhandelspaar (z.B. EUR.USD) - wird als UNKNOWN klassifiziert", AssetCategory.UNKNOWN, InvestmentFundType.NONE), # Added for clarity if interactive
            ("Sonstiges (Standard Anlage KAP)", AssetCategory.STOCK, InvestmentFundType.NONE), # Default for other unknowns
        ]
        self.load_classifications()

    def load_classifications(self):
        if os.path.exists(self.cache_file_path):
            try:
                with open(self.cache_file_path, 'r', encoding='utf-8') as f:
                    raw_cache = json.load(f)
                    for key, data_list in raw_cache.items():
                        if isinstance(data_list, list) and len(data_list) == 3:
                             self.classifications_cache[key] = (data_list[0], data_list[1], data_list[2])
            except json.JSONDecodeError:
                print(f"Error: Could not decode JSON from {self.cache_file_path}. Starting with an empty cache.")
            except Exception as e:
                print(f"Error loading classifications: {e}. Starting with an empty cache.")

    def save_classifications(self):
        os.makedirs(os.path.dirname(self.cache_file_path), exist_ok=True)
        try:
            with open(self.cache_file_path, 'w', encoding='utf-8') as f:
                json.dump(self.classifications_cache, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Error saving classifications: {e}")

    def _is_potentially_special(self, asset: Asset) -> bool:
        desc_upper = (asset.description or "").upper()
        cat_raw_upper = (asset.ibkr_asset_class_raw or "").upper()
        sub_cat_raw_upper = (asset.ibkr_sub_category_raw or "").upper()
        symbol_upper = (asset.ibkr_symbol or "").upper()

        if cat_raw_upper == "FUND" or "ETF" in sub_cat_raw_upper or "FUND" in sub_cat_raw_upper :
            return True
        if "ETF" in desc_upper or "FUND" in desc_upper or "INVESTMENT FUND" in desc_upper:
             return True
        if "XETRA-GOLD" in desc_upper or "PHYSICAL GOLD" in desc_upper or \
           "GOLD ETC" in desc_upper or symbol_upper in ("4GLD", "XAD5", "GZLD"):
            return True
        if "BTCETC" in desc_upper or "BITCOIN ETP" in desc_upper or "CRYPTO ETP" in desc_upper or \
           "ETHEREUM ETP" in desc_upper or symbol_upper in ("BTCE", "ETCZERO", "BITC"):
             return True
        if " ETC" in desc_upper and " COMMODITY" in desc_upper : # Generic Commodity ETC might be SO
            return True
        
        # If it's an FX Pair (symbol like "EUR.USD" and IBKR class "CASH"), it needs special attention
        # because its preliminary classification will now be UNKNOWN.
        if cat_raw_upper == "CASH" and symbol_upper and '.' in symbol_upper:
            parts = symbol_upper.split('.')
            if len(parts) == 2 and len(parts[0]) == 3 and len(parts[1]) == 3: # Basic CCY.CCY check
                return True # Needs review, even if it becomes UNKNOWN

        if asset.asset_category in [AssetCategory.OPTION, AssetCategory.CFD]:
            return False # These are usually clear.
        if asset.asset_category in [AssetCategory.STOCK, AssetCategory.BOND]:
             if asset.asset_category == AssetCategory.STOCK and ("ETF" in desc_upper or "FUND" in desc_upper): # Stock that looks like a fund
                 return True
             return False
        # For true CashBalance, it's not "special" in terms of needing re-classification usually.
        if asset.asset_category == AssetCategory.CASH_BALANCE:
            return False
            
        return asset.asset_category == AssetCategory.UNKNOWN


    def preliminary_classify(self,
                               ibkr_asset_class: str,
                               ibkr_sub_category: Optional[str],
                               description: str,
                               symbol: Optional[str]
                              ) -> Tuple[AssetCategory, Optional[InvestmentFundType]]:
        cat_raw = (ibkr_asset_class or "").upper()
        sub_cat_raw = (ibkr_sub_category or "").upper()
        desc_upper = (description or "").upper()
        sym_upper = (symbol or "").upper()

        # Handle Investment Funds
        if cat_raw == "FUND" or "ETF" in sub_cat_raw or "FUND" in sub_cat_raw or \
           "ETF" in desc_upper or "INVESTMENT FUND" in desc_upper:
            fund_type_guess = InvestmentFundType.SONSTIGE_FONDS
            if "AKTIEN" in desc_upper or "EQUITY" in desc_upper or "STOCK" in desc_upper :
                fund_type_guess = InvestmentFundType.AKTIENFONDS
            elif "MISCH" in desc_upper or "MIXED" in desc_upper or "MULTI-ASSET" in desc_upper:
                fund_type_guess = InvestmentFundType.MISCHFONDS
            elif "IMMOBILIEN" in desc_upper or "REAL ESTATE" in desc_upper:
                fund_type_guess = InvestmentFundType.IMMOBILIENFONDS
            return AssetCategory.INVESTMENT_FUND, fund_type_guess

        # Handle §23 EStG Assets (Gold, Crypto ETCs/ETPs)
        if "XETRA-GOLD" in desc_upper or "PHYSICAL GOLD" in desc_upper or sym_upper in ("4GLD", "XAD5", "GZLD") or \
           "BTCETC" in desc_upper or "BITCOIN ETP" in desc_upper or sym_upper == "BTCE" or \
           ("ETC" in desc_upper and ("GOLD" in desc_upper or "CRYPTO" in desc_upper or "BITCOIN" in desc_upper)):
            return AssetCategory.PRIVATE_SALE_ASSET, InvestmentFundType.NONE # Changed from SECTION_23_ESTG_ASSET
        
        # Handle Options and CFDs
        if cat_raw == "OPT":
            return AssetCategory.OPTION, InvestmentFundType.NONE
        if cat_raw == "CFD":
            return AssetCategory.CFD, InvestmentFundType.NONE

        # Handle Stocks and Bonds
        if cat_raw == "STK" or sub_cat_raw == "COMMON" or sub_cat_raw == "PREFERRED":
            return AssetCategory.STOCK, InvestmentFundType.NONE
        if cat_raw == "BOND":
            return AssetCategory.BOND, InvestmentFundType.NONE

        # Handle CASH: Distinguish true cash balances from FX pairs
        if cat_raw == "CASH":
            is_currency_pair_symbol = False
            if sym_upper and '.' in sym_upper:
                parts = sym_upper.split('.')
                # A more robust check might involve known currency codes, but this is a common pattern.
                if len(parts) == 2 and len(parts[0]) == 3 and len(parts[1]) == 3:
                    is_currency_pair_symbol = True
            
            if is_currency_pair_symbol:
                # This is an FX trading instrument (e.g., EUR.USD), not a cash balance itself.
                # Classify as UNKNOWN so it can be reviewed or handled as a distinct (non-CashBalance) asset.
                # Trades of this instrument will result in CurrencyConversionEvents.
                return AssetCategory.UNKNOWN, InvestmentFundType.NONE
            else:
                # Assumed to be an actual cash balance entry (e.g., symbol 'EUR', currency 'EUR')
                return AssetCategory.CASH_BALANCE, InvestmentFundType.NONE

        # Fallbacks based on description
        if "AKTIE" in desc_upper or "SHARE" in desc_upper: return AssetCategory.STOCK, InvestmentFundType.NONE
        if "ANLEIHE" in desc_upper or "BOND" in desc_upper: return AssetCategory.BOND, InvestmentFundType.NONE
        
        # Default to UNKNOWN if no other rule matches
        return AssetCategory.UNKNOWN, InvestmentFundType.NONE

    def _get_python_type_for_category(self, category: AssetCategory) -> Optional[type]:
        if category == AssetCategory.INVESTMENT_FUND: return InvestmentFund
        if category == AssetCategory.STOCK: return Stock
        if category == AssetCategory.BOND: return Bond
        if category == AssetCategory.OPTION: return Option
        if category == AssetCategory.CFD: return Cfd
        if category == AssetCategory.PRIVATE_SALE_ASSET: return PrivateSaleAsset # Changed from SECTION_23_ESTG_ASSET and Section23EstgAsset
        if category == AssetCategory.CASH_BALANCE: return CashBalance
        return Asset # Fallback for UNKNOWN or other non-specific types

    def _determine_classification_interactively_or_heuristically(
        self, asset: Asset, asset_key: str, interactive_mode: bool
    ) -> Tuple[AssetCategory, Optional[InvestmentFundType], str, bool]:
        """
        Helper to determine classification if not from a valid cache entry.
        Returns: target_asset_cat, target_fund_type, target_user_notes, needs_type_replacement
        """
        target_asset_cat: AssetCategory
        target_fund_type: Optional[InvestmentFundType] = InvestmentFundType.NONE
        target_user_notes: str = asset.user_notes or "" 

        asset_needs_special_attention = self._is_potentially_special(asset)
        
        is_likely_fx_pair_instrument = False
        if asset.ibkr_asset_class_raw == "CASH" and asset.ibkr_symbol and '.' in asset.ibkr_symbol:
            parts = asset.ibkr_symbol.split('.')
            if len(parts) == 2 and len(parts[0]) == 3 and len(parts[1]) == 3:
                is_likely_fx_pair_instrument = True

        if interactive_mode and asset_needs_special_attention and not is_likely_fx_pair_instrument:
            print(f"\n--- Asset Classification Needed ---")
            print(f"  Asset Key: {asset_key}")
            print(f"  Description: {asset.description}")
            print(f"  ISIN: {asset.ibkr_isin}, Conid: {asset.ibkr_conid}, Symbol: {asset.ibkr_symbol}")
            print(f"  IBKR Category: {asset.ibkr_asset_class_raw} (Sub: {asset.ibkr_sub_category_raw})")
            print(f"  Current Preliminary Category (in object): {asset.asset_category.name}") # From preliminary_classify run by resolver
            if isinstance(asset, InvestmentFund) and asset.fund_type:
                print(f"  Current Preliminary Fund Type: {asset.fund_type.name}")

            print("Please classify this asset:")
            for i, (display_name, _, _) in enumerate(self._dialog_options):
                print(f"  {i+1}. {display_name}")
            
            default_choice_idx = 0 
            try:
                current_prelim_cat = asset.asset_category
                current_prelim_ft = asset.fund_type if isinstance(asset, InvestmentFund) and asset.fund_type else InvestmentFundType.NONE
                
                exact_match_found = False
                for idx, (_, cat_opt, ft_opt) in enumerate(self._dialog_options):
                    if cat_opt == current_prelim_cat and \
                       (current_prelim_cat != AssetCategory.INVESTMENT_FUND or ft_opt == current_prelim_ft):
                        default_choice_idx = idx
                        exact_match_found = True
                        break
                
                if not exact_match_found and current_prelim_cat != AssetCategory.INVESTMENT_FUND:
                    for idx, (_, cat_opt, _) in enumerate(self._dialog_options):
                        if cat_opt == current_prelim_cat:
                            default_choice_idx = idx
                            break
                elif current_prelim_cat == AssetCategory.UNKNOWN and not is_likely_fx_pair_instrument:
                     for idx, (disp_name, _, _) in enumerate(self._dialog_options):
                        if "Sonstiges (Standard Anlage KAP)" in disp_name :
                            default_choice_idx = idx
                            break
            except Exception: pass


            while True:
                choice_str = input(f"Enter number (1-{len(self._dialog_options)}) [Default: {default_choice_idx+1} - {self._dialog_options[default_choice_idx][0]}]: ")
                if not choice_str:
                    chosen_index = default_choice_idx
                    break
                try:
                    choice_idx = int(choice_str) - 1
                    if 0 <= choice_idx < len(self._dialog_options):
                        chosen_index = choice_idx
                        break
                    else: print("Invalid choice. Please try again.")
                except ValueError: print("Invalid input. Please enter a number.")
            
            _, chosen_tax_cat_dialog, chosen_fund_type_dialog = self._dialog_options[chosen_index]
            target_asset_cat = chosen_tax_cat_dialog
            target_fund_type = chosen_fund_type_dialog if target_asset_cat == AssetCategory.INVESTMENT_FUND else InvestmentFundType.NONE
            
            if is_likely_fx_pair_instrument and target_asset_cat == AssetCategory.CASH_BALANCE:
                print(f"Warning: Asset {asset.ibkr_symbol} appears to be an FX trading pair. It should not be classified as a Cash Balance. Defaulting to UNKNOWN.")
                target_asset_cat = AssetCategory.UNKNOWN 
                target_fund_type = InvestmentFundType.NONE

            target_user_notes = input("Enter any notes for this classification (optional): ") or ""
            self.classifications_cache[asset_key] = (target_asset_cat.name, target_fund_type.name, target_user_notes)
            self.save_classifications()

        elif asset.asset_category == AssetCategory.UNKNOWN :
            if is_likely_fx_pair_instrument:
                target_asset_cat = AssetCategory.UNKNOWN 
                target_fund_type = InvestmentFundType.NONE
                target_user_notes = "Auto-classified as UNKNOWN (likely FX Pair instrument)."
            elif asset.ibkr_asset_class_raw == "CASH" and asset.ibkr_symbol == asset.currency: 
                 target_asset_cat = AssetCategory.CASH_BALANCE
                 target_fund_type = InvestmentFundType.NONE
                 target_user_notes = "Auto-defaulted to CASH_BALANCE from UNKNOWN (matched symbol/currency)."
            else: 
                target_asset_cat = AssetCategory.STOCK
                target_fund_type = InvestmentFundType.NONE
                target_user_notes = "Auto-defaulted from UNKNOWN to STOCK (non-special, non-FX-pair)."
            self.classifications_cache[asset_key] = (target_asset_cat.name, target_fund_type.name, target_user_notes)
        
        else: 
            target_asset_cat = asset.asset_category
            if isinstance(asset, InvestmentFund) and asset.fund_type:
                target_fund_type = asset.fund_type
            elif target_asset_cat == AssetCategory.INVESTMENT_FUND: 
                 target_fund_type = InvestmentFundType.SONSTIGE_FONDS 
            else:
                target_fund_type = InvestmentFundType.NONE
            
            if not target_user_notes: 
                target_user_notes = "Auto-classified based on heuristics."
            self.classifications_cache[asset_key] = (target_asset_cat.name, target_fund_type.name, target_user_notes)

        needs_type_replacement = False
        expected_python_type = self._get_python_type_for_category(target_asset_cat)
        if expected_python_type and not isinstance(asset, expected_python_type):
            needs_type_replacement = True
        
        return target_asset_cat, target_fund_type, target_user_notes, needs_type_replacement

    def ensure_final_classification(self, asset: Asset, interactive_mode: bool = True) -> Tuple[AssetCategory, Optional[InvestmentFundType], str, bool]:
        asset_key = asset.get_classification_key()
        target_asset_cat: AssetCategory
        target_fund_type: Optional[InvestmentFundType]
        target_user_notes: str
        needs_type_replacement: bool

        if asset_key in self.classifications_cache:
            cat_name, fund_type_name, notes_from_cache = self.classifications_cache[asset_key]
            try:
                target_asset_cat = AssetCategory[cat_name]
                if target_asset_cat == AssetCategory.INVESTMENT_FUND:
                    target_fund_type = InvestmentFundType[fund_type_name]
                else:
                    target_fund_type = InvestmentFundType.NONE
                target_user_notes = notes_from_cache
                
                is_likely_fx_pair_instrument_from_key = False
                if asset.ibkr_asset_class_raw == "CASH" and asset.ibkr_symbol and '.' in asset.ibkr_symbol: 
                     parts = asset.ibkr_symbol.split('.')
                     if len(parts) == 2 and len(parts[0]) == 3 and len(parts[1]) == 3:
                        is_likely_fx_pair_instrument_from_key = True
                
                if is_likely_fx_pair_instrument_from_key and target_asset_cat == AssetCategory.CASH_BALANCE:
                    print(f"Warning: Cached classification for {asset_key} is CashBalance, but asset appears to be an FX Pair. Overriding to UNKNOWN.")
                    target_asset_cat = AssetCategory.UNKNOWN
                    target_fund_type = InvestmentFundType.NONE
                    target_user_notes = "Auto-overridden to UNKNOWN from cached CashBalance (likely FX Pair)."
                    self.classifications_cache[asset_key] = (target_asset_cat.name, target_fund_type.name, target_user_notes)
                    self.save_classifications()


                expected_python_type = self._get_python_type_for_category(target_asset_cat)
                needs_type_replacement = bool(expected_python_type and not isinstance(asset, expected_python_type))
                return target_asset_cat, target_fund_type, target_user_notes, needs_type_replacement
            except KeyError:
                 print(f"Warning: Invalid classification names in cache for {asset_key}. Re-classifying.")
                 self.classifications_cache.pop(asset_key)
        
        return self._determine_classification_interactively_or_heuristically(asset, asset_key, interactive_mode)
