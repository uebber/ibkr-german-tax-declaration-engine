# src/classification/asset_classifier.py
import json
import logging
import os
from typing import Dict, Optional, Tuple, List

logger = logging.getLogger(__name__)

from src.domain.assets import (
    Asset, InvestmentFund, Stock, Bond, SonstigeKapitalforderung, Option, Cfd, Future,
    PrivateSaleAsset, CashBalance
)
from src.domain.enums import AssetCategory, InvestmentFundType
from src.domain.exceptions import DataIntegrityError
from src import config as app_config # Added import


class AssetClassifier:
    def __init__(self, cache_file_path: Optional[str] = None): # Modified signature
        if cache_file_path is None:
            self.cache_file_path = app_config.CLASSIFICATION_CACHE_FILE_PATH # Use config
        else:
            self.cache_file_path = cache_file_path

        self.classifications_cache: Dict[str, Tuple[str, str, str]] = {}
        # Each label names the CRITERION that decides the option, not just the instrument's
        # trade name, because the taxpayer is reading a factsheet and has to match it against
        # something. Two things are deliberately absent:
        #
        #   - Teilfreistellung rates. reference/investment-tax-law/invstg-20-teilfreistellung.md
        #     states that it is "the only statement of the Teilfreistellung rates in this
        #     library. Do not restate them elsewhere". The quota that DECIDES the fund type is
        #     what the user needs here; the rate is the consequence and the engine applies it.
        #   - Zeilen numbers. They are year-specific -- Termingeschaefte are declared on their
        #     own lines up to VZ 2024 and folded in from VZ 2025 (src/tax_law/registry.py) --
        #     so a fixed number in a static label would be wrong for half the years the engine
        #     supports. The form and the Verlustverrechnungskreis are named instead, and the
        #     report states the lines for the year actually being processed.
        self._dialog_options: List[Tuple[str, AssetCategory, InvestmentFundType]] = [
            # Fund quotas, all "fortlaufend gemaess den Anlagebedingungen": Aktienfonds is
            # *mehr als 50 %* Kapitalbeteiligungen ([GT-INVSTG-026]), Mischfonds *mindestens
            # 25 %* ([GT-INVSTG-027]), Immobilienfonds *mehr als 50 %* of Aktivvermoegen in
            # Immobilien and Auslands-Immobilienfonds the same test against foreign property
            # ([GT-INVSTG-029]). The Mischfonds label states no upper bound because the
            # statute states none — a fund above 50 % is an Aktienfonds by the more specific
            # rule, which is what "aber kein Aktienfonds" says.
            ("Aktienfonds — fortlaufend mehr als 50 % des Aktivvermögens in Kapitalbeteiligungen (Anlage KAP-INV)", AssetCategory.INVESTMENT_FUND, InvestmentFundType.AKTIENFONDS),
            ("Mischfonds — fortlaufend mindestens 25 % des Aktivvermögens in Kapitalbeteiligungen, aber kein Aktienfonds (Anlage KAP-INV)", AssetCategory.INVESTMENT_FUND, InvestmentFundType.MISCHFONDS),
            ("Immobilienfonds — fortlaufend mehr als 50 % des Aktivvermögens in Immobilien / Immobilien-Gesellschaften (Anlage KAP-INV)", AssetCategory.INVESTMENT_FUND, InvestmentFundType.IMMOBILIENFONDS),
            ("Auslands-Immobilienfonds — dieselbe Quote, gemessen an ausländischen Immobilien (Anlage KAP-INV)", AssetCategory.INVESTMENT_FUND, InvestmentFundType.AUSLANDS_IMMOBILIENFONDS),
            ("Sonstige Investmentfonds — Fonds, der keine dieser Quoten erfüllt; keine Teilfreistellung (Anlage KAP-INV)", AssetCategory.INVESTMENT_FUND, InvestmentFundType.SONSTIGE_FONDS),
            # These two options are the two OUTCOMES of one test, and the test is stated in
            # BMF 14.05.2025 Rz. 57 ([GT-ESTG23-011]): a commodity Inhaberschuldverschreibung
            # is a Sachleistungsanspruch -- and so a 23 EStG asset -- only where the issuer
            # must invest the capital almost entirely in the commodity AND the holder's claim
            # is exclusively to delivery of the deposited commodity or to the proceeds of its
            # sale. Where it is not backed that way, the disposal is 20 Abs. 2 Satz 1 Nr. 7
            # income. The deciding facts are in the Emissionsbedingungen and cannot be read
            # off the IBKR asset class, which is why this is asked rather than inferred.
            #
            # The 23 EStG label deliberately does NOT promise "steuerfrei nach einem Jahr".
            # The engine applies the one-year Frist unconditionally, and [GT-ESTG23-005]
            # records that as a deviation: 23 Abs. 1 Satz 1 Nr. 2 Satz 4 extends it to ten
            # years for an asset that produced income in at least one year. Printing the
            # one-year promise on the prompt would make the engine's own defect look like law.
            ("§23 EStG / Anlage SO — physisch hinterlegter Rohstoff mit ausschließlichem Lieferanspruch (z.B. Xetra-Gold), oder Krypto-ETP", AssetCategory.PRIVATE_SALE_ASSET, InvestmentFundType.NONE), # Changed from SECTION_23_ESTG_ASSET
            # Rz. 9 puts the "kein Termingeschäft" half beyond doubt: "Zertifikate und
            # Optionsscheine gehören nicht zu den Termingeschäften" ([GT-ESTG20-038]). That a
            # Zertifikat is instead a sonstige Kapitalforderung is [GT-ESTG20-008].
            #
            # Optionsscheine are excluded from the Termingeschaefte by the same sentence, and
            # the store does not say where they DO belong. They are therefore named in no
            # option here, deliberately: guessing them into this one would be implementing a
            # position no reference file carries. See the gap noted against [GT-ESTG20-038].
            ("Sonstige Kapitalforderung §20 Abs. 2 S. 1 Nr. 7, kein Termingeschäft — ungedeckter Gold-/Rohstoff-ETC, Zertifikat, Spot-Edelmetall (Anlage KAP)", AssetCategory.SONSTIGE_KAPITALFORDERUNG, InvestmentFundType.NONE),
            # The Aktienverlusttopf is the one consequence a taxpayer cannot undo later, and
            # it is still in force after the JStG-2024 repeal of the Termingeschaeft cap:
            # 20 Abs. 6 Satz 4, "losses from the sale of shares may ONLY be offset against
            # gains from the sale of shares" ([GT-ESTG20-033]). It is why picking "Aktie" for
            # something that is not one costs money, and why the label warns rather than
            # merely naming the instrument.
            ("Aktie — Anteil an einer Kapitalgesellschaft; Verluste sind NUR mit Aktiengewinnen verrechenbar (Aktienverlusttopf) (Anlage KAP)", AssetCategory.STOCK, InvestmentFundType.NONE),
            # Same Verlustverrechnungskreis as the Nr. 7 option above, but not the same
            # handling: a bond's trade price is read as a percentage of nominal, Stueckzinsen
            # are recognised, and an IBKR "BM" record redeems it at maturity as a deemed
            # Veraeusserung (20 Abs. 2 Satz 2, [GT-ESTG20-009]). Choosing this for an ETC
            # divides its proceeds and cost by 100.
            ("Anleihe — Schuldverschreibung mit Nennwert; Kurs wird als Prozent des Nennwerts gelesen, Stückzinsen und Einlösung bei Fälligkeit werden verarbeitet (Anlage KAP)", AssetCategory.BOND, InvestmentFundType.NONE),
            # Rz. 9 enumerates these expressly -- "Optionsgeschaefte, Swaps,
            # Devisentermingeschaefte und Forwards oder Futures ... sowie Contracts for
            # Difference (CFDs)" ([GT-ESTG20-038]). A CFD is a Termingeschaeft by name, not by
            # analogy, which makes it the best-grounded of these three.
            #
            # CAUTION, and this label got it wrong once: Rz. 9 carries TWO enumerations and they
            # are not interchangeable. The five *Bezugsgroessen* the price may depend on include
            # "Waren oder Edelmetallen"; the *Basiswerte* named for CFDs are "Aktien, Indizes,
            # Waehrungspaare oder Zinssaetze". A CFD on a precious metal is still a
            # Termingeschaeft -- via the Edelmetalle Bezugsgroesse -- but Edelmetall is not in
            # the Basiswerte list and must not be presented as if it were. See the same
            # distinction drawn in reference/research/coverage-matrix.md.
            #
            # Stillhalterpraemien are 20 Abs. 1 Nr. 11, taxable "die ... vereinnahmt werden"
            # ([GT-ESTG20-004]).
            ("Option — Termingeschäft; Stillhalterprämien sind bei Vereinnahmung steuerpflichtig (Anlage KAP)", AssetCategory.OPTION, InvestmentFundType.NONE),
            ("Future — Termingeschäft (Anlage KAP)", AssetCategory.FUTURE, InvestmentFundType.NONE),
            ("CFD — Termingeschäft; Basiswert z.B. Aktie, Index, Währungspaar oder Zinssatz (Anlage KAP)", AssetCategory.CFD, InvestmentFundType.NONE),
            # "(ECHT)" used to be the whole distinction here and meant nothing to a reader.
            # What it was guarding against is the next option, so both now say so.
            ("Währungssaldo — tatsächlicher Fremdwährungsbestand auf dem Konto, KEIN Handelspaar (Anlage KAP)", AssetCategory.CASH_BALANCE, InvestmentFundType.NONE),
            # The old label exposed the internal enum name and implied the position is untaxed.
            # It is not: an FX pair trade becomes a CurrencyConversionEvent keyed off the raw
            # IBKR asset class, and the gain or loss is realised on the two currency ledgers.
            # This option records that the INSTRUMENT itself carries none.
            ("Devisen-Handelspaar (z.B. EUR.USD) — kein eigenes Wirtschaftsgut; Gewinn/Verlust entsteht auf den beteiligten Währungssalden, nicht hier", AssetCategory.UNKNOWN, InvestmentFundType.NONE),
            # There is deliberately NO catch-all option, and nothing here may become one.
            #
            # A fifteenth option used to sit at this line: "Sonstiges (Standard Anlage KAP)",
            # which reads as ordinary Anlage KAP income and was AssetCategory.STOCK -- issue
            # #52. Renaming it to say "wie eine Aktie" left it a second door to the Aktie
            # option above, differing only in wording, so it is gone rather than reworded
            # twice. An instrument that matches no option is a gap in this list or a question
            # the store has not answered; either way the answer is not a residual bucket that
            # applies the Aktienverlusttopf ([GT-ESTG20-033]) to whatever lands in it.
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

        if asset.asset_category in [AssetCategory.OPTION, AssetCategory.CFD, AssetCategory.FUTURE]:
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
        if cat_raw == "FUT":
            return AssetCategory.FUTURE, InvestmentFundType.NONE

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
        if category == AssetCategory.SONSTIGE_KAPITALFORDERUNG: return SonstigeKapitalforderung
        if category == AssetCategory.OPTION: return Option
        if category == AssetCategory.CFD: return Cfd
        if category == AssetCategory.FUTURE: return Future
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
            
            # The Enter key may only CONFIRM a classification the engine actually arrived at.
            # Where it arrived at none, there is no default and the prompt insists on a number
            # -- issue #52. The two ways a default used to appear without anything behind it:
            #
            #   - UNKNOWN. It matched the Devisen-Handelspaar option, whose category is
            #     UNKNOWN, and was then redirected to the "Sonstiges" catch-all, which was
            #     STOCK. Either way Enter bought the Aktienverlusttopf ([GT-ESTG20-033]) on an
            #     instrument nothing had classified.
            #   - An InvestmentFund whose fund_type matches no option, InvestmentFundType.NONE
            #     among them. No branch caught that, so the default stayed at its initial 0 --
            #     Aktienfonds, and with it a Teilfreistellung the fund may not be entitled to.
            #
            # Hence: exact match on what the preliminary pass produced, or nothing. The
            # second, category-only loop that used to follow was unreachable -- for any
            # non-fund category the exact-match condition already reduces to the same test.
            default_choice_idx: Optional[int] = None
            current_prelim_cat = asset.asset_category
            current_prelim_ft = asset.fund_type if isinstance(asset, InvestmentFund) and asset.fund_type else InvestmentFundType.NONE

            if current_prelim_cat != AssetCategory.UNKNOWN:
                for idx, (_, cat_opt, ft_opt) in enumerate(self._dialog_options):
                    if cat_opt == current_prelim_cat and \
                       (current_prelim_cat != AssetCategory.INVESTMENT_FUND or ft_opt == current_prelim_ft):
                        default_choice_idx = idx
                        break

            if default_choice_idx is None:
                print(
                    f"Kein Vorschlag: diese Position konnte nicht automatisch eingeordnet "
                    f"werden. Bitte 1-{len(self._dialog_options)} wählen."
                )
                prompt = f"Enter number (1-{len(self._dialog_options)}): "
            else:
                prompt = (
                    f"Enter number (1-{len(self._dialog_options)}) "
                    f"[Default: {default_choice_idx+1} - {self._dialog_options[default_choice_idx][0]}]: "
                )

            while True:
                choice_str = input(prompt)
                if not choice_str:
                    if default_choice_idx is None:
                        print("Kein Vorschlag für diese Position — bitte eine Zahl eingeben.")
                        continue
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
                raise DataIntegrityError(
                    f"Asset '{asset_key}' (Symbol: {asset.ibkr_symbol}, ISIN: {getattr(asset, 'isin', 'N/A')}, "
                    f"AssetClass: {asset.ibkr_asset_class_raw}) has category UNKNOWN and cannot be auto-classified. "
                    f"Run with --interactive to classify it manually, or add it to the classification cache."
                )
            # Do NOT cache auto-classifications — only user-confirmed entries belong in cache

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
            # Do NOT cache auto-classifications — only user-confirmed entries belong in cache

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
