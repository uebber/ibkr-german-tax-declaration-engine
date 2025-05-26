# src/identification/asset_resolver.py
import uuid
from decimal import Decimal
from typing import Dict, Set, Optional, Tuple, Any

from src.domain.assets import (
    Asset, Stock, Bond, InvestmentFund, Option, Cfd, PrivateSaleAsset, CashBalance, Derivative # Changed Section23EstgAsset to PrivateSaleAsset
)
from src.domain.enums import AssetCategory, InvestmentFundType
from src.classification.asset_classifier import AssetClassifier # Dependency
from src.utils.type_utils import safe_decimal, parse_ibkr_date

class AssetResolver:
    def __init__(self, asset_classifier: AssetClassifier):
        self.asset_classifier: AssetClassifier = asset_classifier
        self.alias_map: Dict[str, Asset] = {}
        self.assets_by_internal_id: Dict[uuid.UUID, Asset] = {}

    def get_asset_by_id(self, internal_asset_id: uuid.UUID) -> Optional[Asset]:
        """Retrieves an asset by its internal UUID."""
        return self.assets_by_internal_id.get(internal_asset_id)

    def get_asset_by_alias(self, alias_key: str) -> Optional[Asset]:
        """Retrieves an asset by one of its alias strings."""
        return self.alias_map.get(alias_key)

    def _generate_aliases(self,
                          isin: Optional[str],
                          conid: Optional[str],
                          symbol: Optional[str],
                          currency: Optional[str],
                          ibkr_asset_class: Optional[str]
                         ) -> Set[str]:
        aliases: Set[str] = set()
        if isin: aliases.add(f"ISIN:{isin.strip().upper()}")
        if conid: aliases.add(f"CONID:{conid.strip()}")
        if symbol: aliases.add(f"SYMBOL:{symbol.strip().upper()}")
        if ibkr_asset_class and ibkr_asset_class.upper() == "CASH" and \
           symbol and currency and symbol.strip().upper() == currency.strip().upper():
            aliases.add(f"CASH_BALANCE:{currency.strip().upper()}")
        return aliases

    def _extract_common_asset_fields(self, asset: Asset) -> Dict[str, Any]:
        common = {
            "internal_asset_id": asset.internal_asset_id,
            "aliases": asset.aliases.copy(), # Ensure new asset gets a copy
            "description": asset.description,
            "currency": asset.currency,
            "user_notes": asset.user_notes,
            "ibkr_conid": asset.ibkr_conid,
            "ibkr_symbol": asset.ibkr_symbol,
            "ibkr_isin": asset.ibkr_isin,
            "ibkr_asset_class_raw": asset.ibkr_asset_class_raw,
            "ibkr_sub_category_raw": asset.ibkr_sub_category_raw,
            "soy_quantity": asset.soy_quantity, # Renamed from initial_quantity_soy
            "soy_cost_basis_amount": asset.soy_cost_basis_amount, # Renamed from initial_cost_basis_money_soy
            "soy_cost_basis_currency": asset.soy_cost_basis_currency, # Renamed from initial_cost_basis_currency_soy
            "eoy_quantity": asset.eoy_quantity,
            "eoy_mark_price_currency": asset.eoy_mark_price_currency,
            "eoy_market_price": asset.eoy_market_price, # Renamed from eoy_mark_price
            "eoy_position_value": asset.eoy_position_value,
        }
        if isinstance(asset, Derivative):
            common["underlying_asset_internal_id"] = asset.underlying_asset_internal_id
            common["underlying_ibkr_conid"] = asset.underlying_ibkr_conid
            common["underlying_ibkr_symbol"] = asset.underlying_ibkr_symbol
            common["multiplier"] = asset.multiplier
        if isinstance(asset, Option):
            common["option_type"] = asset.option_type
            common["strike_price"] = asset.strike_price
            common["expiry_date"] = asset.expiry_date
        return common

    def replace_asset_type(self,
                           internal_asset_id: uuid.UUID,
                           new_category: AssetCategory,
                           new_fund_type: Optional[InvestmentFundType],
                           new_user_notes: str) -> Asset:
        old_asset = self.assets_by_internal_id.get(internal_asset_id)
        if not old_asset:
            raise ValueError(f"Asset with ID {internal_asset_id} not found for type replacement.")

        common_kwargs = self._extract_common_asset_fields(old_asset)
        common_kwargs["user_notes"] = new_user_notes # Ensure new notes are used

        new_asset: Asset

        if new_category == AssetCategory.INVESTMENT_FUND:
            new_asset = InvestmentFund(fund_type=new_fund_type or InvestmentFundType.NONE, **common_kwargs)
        elif new_category == AssetCategory.STOCK:
            new_asset = Stock(**common_kwargs)
        elif new_category == AssetCategory.BOND:
            new_asset = Bond(**common_kwargs)
        elif new_category == AssetCategory.OPTION:
            new_asset = Option(
                option_type=common_kwargs.pop("option_type", None),
                strike_price=common_kwargs.pop("strike_price", None),
                expiry_date=common_kwargs.pop("expiry_date", None),
                underlying_ibkr_conid=common_kwargs.pop("underlying_ibkr_conid", None),
                underlying_ibkr_symbol=common_kwargs.pop("underlying_ibkr_symbol", None),
                underlying_asset_internal_id=common_kwargs.pop("underlying_asset_internal_id", None),
                multiplier=common_kwargs.pop("multiplier", Decimal("100")),
                **common_kwargs
            )
        elif new_category == AssetCategory.CFD:
            new_asset = Cfd(
                underlying_ibkr_conid=common_kwargs.pop("underlying_ibkr_conid", None),
                underlying_ibkr_symbol=common_kwargs.pop("underlying_ibkr_symbol", None),
                underlying_asset_internal_id=common_kwargs.pop("underlying_asset_internal_id", None),
                multiplier=common_kwargs.pop("multiplier", Decimal("1")),
                **common_kwargs
            )
        elif new_category == AssetCategory.PRIVATE_SALE_ASSET: # Changed from SECTION_23_ESTG_ASSET
            new_asset = PrivateSaleAsset(**common_kwargs) # Changed from Section23EstgAsset
        elif new_category == AssetCategory.CASH_BALANCE:
            cb_currency = common_kwargs.pop("currency", None)
            if not cb_currency:
                 raise ValueError("Currency not found or was None in common_kwargs for CashBalance replacement. This is unexpected.")
            new_asset = CashBalance(currency=cb_currency, **common_kwargs)
        else: # AssetCategory.UNKNOWN or any other non-specific type
            new_asset = Asset(asset_category=new_category, **common_kwargs)
        
        new_asset.asset_category = new_category # Explicitly set after construction for clarity/safety
        new_asset.user_notes = new_user_notes
        if isinstance(new_asset, InvestmentFund) and new_category == AssetCategory.INVESTMENT_FUND:
            new_asset.fund_type = new_fund_type or InvestmentFundType.NONE
        
        new_asset.internal_asset_id = old_asset.internal_asset_id # Crucial: re-use ID
        new_asset.aliases = old_asset.aliases # Crucial: re-use aliases set object or ensure it's a full copy

        self.assets_by_internal_id[new_asset.internal_asset_id] = new_asset
        for alias_str in new_asset.aliases: # Ensure all aliases point to the new object
            self.alias_map[alias_str] = new_asset
        
        return new_asset

    def get_or_create_asset(self,
                              raw_isin: Optional[str],
                              raw_conid: Optional[str],
                              raw_symbol: Optional[str],
                              raw_currency: Optional[str],
                              raw_ibkr_asset_class: Optional[str],
                              raw_description: Optional[str],
                              # ADDED description_source_type to the signature
                              description_source_type: str = "unknown", 
                              raw_ibkr_sub_category: Optional[str] = None,
                              raw_multiplier: Optional[Any] = None,
                              raw_strike: Optional[Any] = None,
                              raw_expiry: Optional[str] = None,
                              raw_put_call: Optional[str] = None,
                              raw_underlying_conid: Optional[str] = None,
                              raw_underlying_symbol: Optional[str] = None
                             ) -> Asset:

        isin = raw_isin.strip().upper() if raw_isin and raw_isin.strip() else None
        conid = raw_conid.strip() if raw_conid and raw_conid.strip() else None
        symbol = raw_symbol.strip().upper() if raw_symbol and raw_symbol.strip() else None
        currency = raw_currency.strip().upper() if raw_currency and raw_currency.strip() else None
        ibkr_asset_class = raw_ibkr_asset_class.strip().upper() if raw_ibkr_asset_class and raw_ibkr_asset_class.strip() else "UNKNOWN"
        description_from_row = raw_description.strip() if raw_description and raw_description.strip() else None
        ibkr_sub_category = raw_ibkr_sub_category.strip() if raw_ibkr_sub_category and raw_ibkr_sub_category.strip() else None

        multiplier_val = safe_decimal(raw_multiplier)
        strike_price = safe_decimal(raw_strike)
        expiry_date_obj = parse_ibkr_date(raw_expiry) if raw_expiry else None
        expiry_date_to_store = expiry_date_obj.isoformat() if expiry_date_obj else None

        put_call_val = raw_put_call.strip().upper() if raw_put_call and raw_put_call.strip() else None
        underlying_conid_val = raw_underlying_conid.strip() if raw_underlying_conid and raw_underlying_conid.strip() else None
        underlying_symbol_val = raw_underlying_symbol.strip().upper() if raw_underlying_symbol and raw_underlying_symbol.strip() else None
        
        is_generic_cash_instrument = (ibkr_asset_class == "CASH" and symbol == currency)
        if not is_generic_cash_instrument and not isin and not conid and not symbol:
            # print(f"Warning: Asset with description '{description_from_row}' (Class: {ibkr_asset_class}) lacks ISIN, Conid, and Symbol. Creating minimal asset object.")
            pass

        current_row_aliases = self._generate_aliases(isin, conid, symbol, currency, ibkr_asset_class)

        found_assets: Set[Asset] = set()
        for alias_str in current_row_aliases:
            if alias_str in self.alias_map:
                found_assets.add(self.alias_map[alias_str])

        asset_instance: Asset
        if not found_assets:
            prelim_cat, prelim_fund_type = self.asset_classifier.preliminary_classify(
                ibkr_asset_class=ibkr_asset_class,
                ibkr_sub_category=ibkr_sub_category,
                description=description_from_row or "", # Prelim classification can use desc_from_row initially
                symbol=symbol
            )

            asset_args = {
                "description": None, # Initialize description to None; will be set carefully later
                "ibkr_conid": conid,
                "ibkr_symbol": symbol,
                "ibkr_isin": isin,
                "ibkr_asset_class_raw": ibkr_asset_class,
                "ibkr_sub_category_raw": ibkr_sub_category,
            }
            if not (prelim_cat == AssetCategory.CASH_BALANCE and currency):
                asset_args["currency"] = currency


            if prelim_cat == AssetCategory.INVESTMENT_FUND:
                asset_instance = InvestmentFund(fund_type=prelim_fund_type or InvestmentFundType.NONE, **asset_args)
            elif prelim_cat == AssetCategory.OPTION:
                asset_instance = Option(
                    option_type=put_call_val, strike_price=strike_price, expiry_date=expiry_date_to_store,
                    underlying_ibkr_conid=underlying_conid_val, underlying_ibkr_symbol=underlying_symbol_val,
                    multiplier=multiplier_val if multiplier_val is not None else Decimal("100"),
                    **asset_args
                )
            elif prelim_cat == AssetCategory.CFD:
                asset_instance = Cfd(
                    underlying_ibkr_conid=underlying_conid_val, underlying_ibkr_symbol=underlying_symbol_val,
                    multiplier=multiplier_val if multiplier_val is not None else Decimal("1"),
                    **asset_args
                )
            elif prelim_cat == AssetCategory.STOCK:
                asset_instance = Stock(**asset_args)
            elif prelim_cat == AssetCategory.BOND:
                asset_instance = Bond(**asset_args)
            elif prelim_cat == AssetCategory.PRIVATE_SALE_ASSET: # Changed from SECTION_23_ESTG_ASSET
                asset_instance = PrivateSaleAsset(**asset_args) # Changed from Section23EstgAsset
            elif prelim_cat == AssetCategory.CASH_BALANCE and currency:
                asset_instance = CashBalance(currency=currency, **asset_args)
            else: 
                asset_instance = Asset(asset_category=prelim_cat, **asset_args)
            
            asset_instance.asset_category = prelim_cat 
            asset_instance.aliases.update(current_row_aliases)
            self.assets_by_internal_id[asset_instance.internal_asset_id] = asset_instance

        elif len(found_assets) == 1:
            asset_instance = found_assets.pop()
        else: 
            sorted_assets = sorted(list(found_assets), key=lambda a: (
                0 if isinstance(a, CashBalance) else 1, 
                0 if isinstance(a, InvestmentFund) else 1, 
                0 if isinstance(a, Option) else 1,
                0 if isinstance(a, Cfd) else 1,
                0 if isinstance(a, Stock) else 1,
                0 if isinstance(a, Bond) else 1,
                0 if isinstance(a, PrivateSaleAsset) else 1, # Changed from Section23EstgAsset
                0 if a.ibkr_isin else 1,
                0 if a.ibkr_conid else 1,
                str(a.internal_asset_id) 
            ))
            asset_instance = sorted_assets[0] 
            for loser_asset in sorted_assets[1:]:
                if loser_asset.internal_asset_id == asset_instance.internal_asset_id:
                    continue 
                
                asset_instance.aliases.update(loser_asset.aliases)
                for alias_str in loser_asset.aliases:
                    self.alias_map[alias_str] = asset_instance
                
                if loser_asset.internal_asset_id in self.assets_by_internal_id:
                    del self.assets_by_internal_id[loser_asset.internal_asset_id]
        
        # Update asset_instance.description based on source priority
        if description_from_row:
            current_desc = asset_instance.description
            new_desc = description_from_row
            update_description = False

            generic_placeholders = ["STOCK", "BOND", "FUND", "ETF", "UNKNOWN ASSET"]
            is_current_generic = current_desc is None or current_desc.upper() in generic_placeholders or \
                                 (current_desc.startswith("Unnamed Asset"))

            if description_source_type in ["trade", "position", "cash_balance_generated"]:
                if is_current_generic:
                    update_description = True
                elif current_desc is not None:
                    # Avoid replacing good text with purely numeric "description"
                    is_current_numeric_like = all(c.isdigit() or c in ['.', ',', '-'] for c in current_desc.strip())
                    is_new_numeric_like = all(c.isdigit() or c in ['.', ',', '-'] for c in new_desc.strip())

                    if is_current_numeric_like and not is_new_numeric_like: # Prefer new text over current number-like
                        update_description = True
                    elif not is_current_numeric_like and is_new_numeric_like: # Don't overwrite current text with new number-like
                        pass
                    elif len(new_desc) > len(current_desc): # Prefer longer if same type (both text or both number-like)
                        update_description = True
                    elif current_desc is None : # If current is none, always update
                        update_description = True

            elif description_source_type == "corp_act_asset":
                # Asset description from CA file: only if current is None or very generic.
                if is_current_generic and new_desc.upper() not in generic_placeholders:
                    update_description = True
            
            # For "unknown" (or if no specific rule matched above and current is None)
            # Cash_tx descriptions are deliberately NOT used to update asset description
            elif current_desc is None and description_source_type not in ["cash_tx"]:
                 update_description = True


            if update_description:
                asset_instance.description = new_desc
        
        # Other attribute updates
        if currency and not asset_instance.currency: asset_instance.currency = currency
        if isin and not asset_instance.ibkr_isin: asset_instance.ibkr_isin = isin
        if conid and not asset_instance.ibkr_conid: asset_instance.ibkr_conid = conid
        
        if symbol and (not asset_instance.ibkr_symbol or (asset_instance.ibkr_symbol == asset_instance.currency and symbol != asset_instance.currency)):
             asset_instance.ibkr_symbol = symbol
        
        if (not asset_instance.ibkr_asset_class_raw or asset_instance.ibkr_asset_class_raw == "UNKNOWN") and ibkr_asset_class != "UNKNOWN":
            asset_instance.ibkr_asset_class_raw = ibkr_asset_class
        if not asset_instance.ibkr_sub_category_raw and ibkr_sub_category:
            asset_instance.ibkr_sub_category_raw = ibkr_sub_category

        if isinstance(asset_instance, Option):
            if put_call_val and not asset_instance.option_type: asset_instance.option_type = put_call_val
            if strike_price is not None and asset_instance.strike_price is None: asset_instance.strike_price = strike_price
            if expiry_date_to_store and not asset_instance.expiry_date: asset_instance.expiry_date = expiry_date_to_store
        
        if isinstance(asset_instance, Derivative): 
            if underlying_conid_val and not asset_instance.underlying_ibkr_conid:
                asset_instance.underlying_ibkr_conid = underlying_conid_val
            if underlying_symbol_val and not asset_instance.underlying_ibkr_symbol:
                asset_instance.underlying_ibkr_symbol = underlying_symbol_val
            if multiplier_val is not None and (asset_instance.multiplier is None or asset_instance.multiplier == Decimal("1.0")): 
                default_mult = Decimal("100") if isinstance(asset_instance, Option) else Decimal("1")
                asset_instance.multiplier = multiplier_val if multiplier_val != Decimal("0") else default_mult


        asset_instance.aliases.update(current_row_aliases)
        for alias_str in asset_instance.aliases: 
            self.alias_map[alias_str] = asset_instance
        
        if isinstance(asset_instance, CashBalance) and asset_instance.currency:
            cash_bal_alias = f"CASH_BALANCE:{asset_instance.currency}"
            if cash_bal_alias not in asset_instance.aliases:
                 asset_instance.add_alias(cash_bal_alias)
            self.alias_map[cash_bal_alias] = asset_instance 

        return asset_instance

    def link_derivatives(self):
        for asset in self.assets_by_internal_id.values():
            if isinstance(asset, Derivative) and asset.underlying_asset_internal_id is None:
                underlying_asset: Optional[Asset] = None
                if asset.underlying_ibkr_conid:
                    alias_key = f"CONID:{asset.underlying_ibkr_conid}"
                    if alias_key in self.alias_map:
                        underlying_asset = self.alias_map[alias_key]
                
                if underlying_asset is None and asset.underlying_ibkr_symbol:
                    alias_key = f"SYMBOL:{asset.underlying_ibkr_symbol.upper()}"
                    potential_matches = [
                        a for symbol_alias, a in self.alias_map.items()
                        if symbol_alias == alias_key and not isinstance(a, CashBalance)
                    ]
                    if len(potential_matches) == 1 :
                        underlying_asset = potential_matches[0]
                    elif not potential_matches: 
                        if alias_key in self.alias_map: 
                            pass 

                if underlying_asset:
                    asset.underlying_asset_internal_id = underlying_asset.internal_asset_id
