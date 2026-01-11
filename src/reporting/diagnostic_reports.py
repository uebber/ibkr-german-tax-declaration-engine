# src/reporting/diagnostic_reports.py
import logging
from decimal import Decimal
from collections import defaultdict
from typing import List, Dict, Any, Optional

import src.config as config 
from src.domain.assets import Asset, InvestmentFund 
from src.domain.events import FinancialEvent, TradeEvent # Added TradeEvent for type hint
from src.domain.enums import AssetCategory, InvestmentFundType, FinancialEventType, RealizationType 
from src.identification.asset_resolver import AssetResolver 
from src.domain.results import RealizedGainLoss, VorabpauschaleData 

logger = logging.getLogger(__name__)

def _get_asset_display_key(asset: Optional[Asset]) -> str:
    """Generates a display key for an asset."""
    if not asset:
        return "UNKNOWN_ASSET"
    try:
        return asset.get_classification_key()
    except ValueError: 
        desc = asset.description or f"ID_{str(asset.internal_asset_id)[:8]}"
        return f"UNKEYED_{desc}"

def print_grouped_event_details(
        events: List[FinancialEvent],
        asset_resolver: AssetResolver
    ):
    """Prints detailed financial events grouped by asset."""
    grouped_events: Dict[str, List[FinancialEvent]] = defaultdict(list)
    for event in events:
        asset = asset_resolver.get_asset_by_id(event.asset_internal_id)
        asset_key = _get_asset_display_key(asset) if asset else f"UNKNOWN_ASSET_ID_{event.asset_internal_id}"
        grouped_events[asset_key].append(event)

    print("\n--- Detailed Financial Events by Asset ---")
    for asset_key in sorted(grouped_events.keys()):
        asset_events = grouped_events[asset_key]
        asset = None
        if not asset_key.startswith("UNKEYED_") and not asset_key.startswith("UNKNOWN_ASSET"):
             asset = asset_resolver.get_asset_by_alias(asset_key)
        if not asset and asset_events: 
            asset = asset_resolver.get_asset_by_id(asset_events[0].asset_internal_id)

        asset_desc_print = asset.description if asset else asset_key
        asset_cat_print = asset.asset_category.name if asset and asset.asset_category else 'N/A'
        print(f"\n--- Asset: {asset_desc_print} ({asset_cat_print}) ---")

        if asset and isinstance(asset, InvestmentFund) and asset.fund_type != InvestmentFundType.NONE:
            print(f"    Fund Type: {asset.fund_type.name}")

        for event in sorted(asset_events, key=lambda e: (e.event_date, e.event_id)): 
            details = [f"  {event.event_date}", f"{event.event_type.name[:25]:<25}"]
            display_precision = config.OUTPUT_PRECISION_AMOUNTS # Renamed
            per_share_precision = config.OUTPUT_PRECISION_PER_SHARE # Renamed
            qty_precision = config.PRECISION_QUANTITY

            if event.gross_amount_foreign_currency is not None:
                amt = event.gross_amount_foreign_currency
                details.append(f"Amt: {amt.quantize(display_precision) if isinstance(amt, Decimal) else amt} {event.local_currency or ''}")
            if event.gross_amount_eur is not None:
                amt_eur = event.gross_amount_eur
                details.append(f"EUR: {amt_eur.quantize(display_precision) if isinstance(amt_eur, Decimal) else amt_eur}")

            if isinstance(event, TradeEvent): # Check if it's a TradeEvent
                trade_event: TradeEvent = event 
                qty_val = trade_event.quantity.quantize(qty_precision) if trade_event.quantity else Decimal(0)
                price_val = trade_event.price_foreign_currency.quantize(per_share_precision) if trade_event.price_foreign_currency else Decimal(0)
                
                details.append(f"Qty: {qty_val!s:<15}")
                details.append(f"Price: {price_val!s:<15}")
                if trade_event.commission_foreign_currency is not None and trade_event.commission_foreign_currency != Decimal(0):
                    comm = trade_event.commission_foreign_currency
                    details.append(f"Comm: {(comm.quantize(display_precision) if isinstance(comm, Decimal) else comm)} {trade_event.commission_currency or ''}")
                if trade_event.commission_eur is not None and trade_event.commission_eur != Decimal(0):
                    comm_eur = trade_event.commission_eur
                    details.append(f"CommEUR: {(comm_eur.quantize(display_precision) if isinstance(comm_eur, Decimal) else comm_eur)}")
            print(" | ".join(details))
            if event.ibkr_activity_description:
                print(f"    Desc: {event.ibkr_activity_description[:80]}")

def print_asset_positions_diagnostic(asset_resolver: AssetResolver):
    """Prints SOY and EOY asset positions."""
    print("\n--- Asset Positions (Start & End of Year) ---")
    sorted_assets = sorted(asset_resolver.assets_by_internal_id.values(), key=_get_asset_display_key)
    for asset in sorted_assets:
        soy_info = "N/A"
        if asset.soy_quantity is not None: # Renamed from initial_quantity_soy
            qty_val = asset.soy_quantity.quantize(config.PRECISION_QUANTITY) # Renamed from initial_quantity_soy
            cost_val_soy = asset.soy_cost_basis_amount # Renamed from initial_cost_basis_money_soy
            cost_val = cost_val_soy.quantize(config.OUTPUT_PRECISION_AMOUNTS) if cost_val_soy else 'N/A' # Renamed
            soy_info = f"Qty: {qty_val!s}, Cost: {cost_val!s} {asset.soy_cost_basis_currency or ''}" # Renamed from initial_cost_basis_currency_soy

        eoy_info = "N/A"
        if asset.eoy_quantity is not None:
            qty_val_eoy = asset.eoy_quantity.quantize(config.PRECISION_QUANTITY)
            price_val_eoy = asset.eoy_market_price # Renamed from eoy_mark_price
            value_val_eoy = asset.eoy_position_value
            
            price_val = price_val_eoy.quantize(config.OUTPUT_PRECISION_PER_SHARE) if price_val_eoy else 'N/A' # Renamed
            value_val = value_val_eoy.quantize(config.OUTPUT_PRECISION_AMOUNTS) if value_val_eoy else 'N/A' # Renamed
            eoy_info = f"Qty: {qty_val_eoy!s}, MarkPrice: {price_val!s} {asset.eoy_mark_price_currency or ''}, Value: {value_val!s}"
        
        asset_display_key_val = _get_asset_display_key(asset)
        asset_desc_print_val = asset.description or asset_display_key_val
        print(f"  {asset_desc_print_val:<50} | "
              f"Cat: {asset.asset_category.name if asset.asset_category else 'N/A':<20} | "
              f"SOY: {soy_info:<50} | EOY: {eoy_info}")

def print_assets_by_category_diagnostic(asset_resolver: AssetResolver):
    """Prints assets grouped by their final classification."""
    print("\n--- Assets by Final Category ---")
    categorized_assets: Dict[Optional[AssetCategory], List[Asset]] = defaultdict(list) 
    for asset in asset_resolver.assets_by_internal_id.values():
        categorized_assets[asset.asset_category].append(asset)

    sorted_categories = sorted(
        [cat for cat in categorized_assets.keys() if cat is not None],
        key=lambda c: c.name
    )
    if None in categorized_assets: 
        sorted_categories.append(None)


    for category in sorted_categories:
        assets_in_cat = categorized_assets[category]
        cat_name = category.name if category else "UNCLASSIFIED"
        print(f"\n  Category: {cat_name}")
        for asset_obj in sorted(assets_in_cat, key=_get_asset_display_key):
            asset_display_key_val = _get_asset_display_key(asset_obj)
            asset_desc_print_val = asset_obj.description or asset_display_key_val
            details = [f"    - {asset_desc_print_val} (ID: {str(asset_obj.internal_asset_id)[:8]})"]
            if asset_obj.ibkr_conid: details.append(f"ConID: {asset_obj.ibkr_conid}")
            if asset_obj.ibkr_isin: details.append(f"ISIN: {asset_obj.ibkr_isin}")
            if asset_obj.currency: details.append(f"Curr: {asset_obj.currency}")
            if isinstance(asset_obj, InvestmentFund) and asset_obj.fund_type != InvestmentFundType.NONE:
                details.append(f"FundType: {asset_obj.fund_type.name}")
            print(" | ".join(details))
            if asset_obj.user_notes:
                print(f"      User Notes: {asset_obj.user_notes}")

def print_object_counts_diagnostic(
    asset_resolver: AssetResolver,
    all_events: List[FinancialEvent],
    rgl_items: List[RealizedGainLoss],
    vp_items: List[VorabpauschaleData]
):
    """Prints counts of various object types."""
    print("\n--- Object Counts ---")
    asset_type_counts = defaultdict(int)
    fund_type_counts = defaultdict(int)
    total_assets = 0
    for asset_obj in asset_resolver.assets_by_internal_id.values():
        total_assets +=1
        asset_type_name = type(asset_obj).__name__
        asset_type_counts[asset_type_name] += 1
        if isinstance(asset_obj, InvestmentFund):
            fund_name = asset_obj.fund_type.name if asset_obj.fund_type else InvestmentFundType.NONE.name
            fund_type_counts[fund_name] += 1

    print(f"\n  Total Unique Assets: {total_assets}")
    print("  Asset Types Breakdown:")
    for asset_type_name, count in sorted(asset_type_counts.items()):
        print(f"    {asset_type_name:<30}: {count}")
    if fund_type_counts:
        print("  InvestmentFund Types Breakdown:")
        for fund_type_name, count in sorted(fund_type_counts.items()):
            print(f"    {fund_type_name:<30}: {count}")

    event_type_counts = defaultdict(int)
    total_events = 0
    for event_obj in all_events:
        total_events +=1
        event_type_name = type(event_obj).__name__ 
        event_type_counts[event_type_name] += 1

    print(f"\n  Total Financial Events: {total_events}")
    print("  Financial Event (Object Types) Breakdown:") 
    for event_type_name, count in sorted(event_type_counts.items()):
        print(f"    {event_type_name:<30}: {count}")

    print("\n  Result Types:")
    print(f"    RealizedGainLoss          : {len(rgl_items)}")
    print(f"    VorabpauschaleData        : {len(vp_items)}")

def print_realized_gains_losses_diagnostic(
        realized_gains_losses: List[RealizedGainLoss],
        asset_resolver: AssetResolver
    ):
    """Prints detailed Realized Gains/Losses."""
    print("\n--- Realized Gains/Losses (Diagnostic) ---")
    if not realized_gains_losses:
        print("  No realized gains/losses generated.")
        return

    display_precision_total = config.OUTPUT_PRECISION_AMOUNTS # Renamed
    display_precision_unit = config.OUTPUT_PRECISION_PER_SHARE # Renamed
    display_precision_qty = config.PRECISION_QUANTITY

    def get_rgl_sort_key(rgl_item):
        asset = asset_resolver.get_asset_by_id(rgl_item.asset_internal_id)
        asset_key = _get_asset_display_key(asset) if asset else f"UNKNOWN_ASSET_RGL_{rgl_item.asset_internal_id}"
        return (rgl_item.realization_date, asset_key, rgl_item.originating_event_id) 

    sorted_rgls = sorted(realized_gains_losses, key=get_rgl_sort_key)
    for rgl_item_idx, rgl_item in enumerate(sorted_rgls):
        asset_for_rgl = asset_resolver.get_asset_by_id(rgl_item.asset_internal_id)
        asset_display_key_rgl = _get_asset_display_key(asset_for_rgl) if asset_for_rgl else "UNKNOWN_ASSET"
        asset_desc_rgl = asset_for_rgl.description if asset_for_rgl else asset_display_key_rgl
        
        cost_basis_unit_disp = (rgl_item.unit_cost_basis_eur or Decimal(0)).quantize(display_precision_unit) # Renamed
        realization_value_unit_disp = (rgl_item.unit_realization_value_eur or Decimal(0)).quantize(display_precision_unit) # Renamed
        qty_realized_disp = (rgl_item.quantity_realized or Decimal(0)).quantize(display_precision_qty)
        asset_cat_name = rgl_item.asset_category_at_realization.name if rgl_item.asset_category_at_realization else "N/A"
        realization_type_name = rgl_item.realization_type.name if rgl_item.realization_type else "N/A"


        print(f"  RGL {rgl_item_idx+1}: Asset: {asset_desc_rgl} ({asset_cat_name})")
        print(f"    Originating Event ID: {str(rgl_item.originating_event_id)[:8] if rgl_item.originating_event_id else 'N/A'}")
        print(f"    Acq. Date: {rgl_item.acquisition_date}, Real. Date: {rgl_item.realization_date}, Type: {realization_type_name}, Holding: {rgl_item.holding_period_days or 'N/A'} days")
        print(f"    Qty Realized: {qty_realized_disp!s}, Cost/Unit EUR: {cost_basis_unit_disp!s}, Realization Val/Unit EUR: {realization_value_unit_disp!s}")
        print(f"    Total Cost EUR: {(rgl_item.total_cost_basis_eur or Decimal(0)).quantize(display_precision_total)!s}, Total Realization Val EUR: {(rgl_item.total_realization_value_eur or Decimal(0)).quantize(display_precision_total)!s}") # Renamed total_cost_basis_eur
        print(f"    Gross G/L EUR: {(rgl_item.gross_gain_loss_eur or Decimal(0)).quantize(display_precision_total)!s}")
        if rgl_item.tax_reporting_category:
            print(f"    Tax Category: {rgl_item.tax_reporting_category.name}")
        if rgl_item.net_gain_loss_after_teilfreistellung_eur is not None and \
           rgl_item.net_gain_loss_after_teilfreistellung_eur.compare(rgl_item.gross_gain_loss_eur) != Decimal(0): 
            net_gl_tf = rgl_item.net_gain_loss_after_teilfreistellung_eur
            print(f"    Net G/L (after TF if any) EUR: {net_gl_tf.quantize(display_precision_total)!s}")

def print_vorabpauschale_diagnostic(vorabpauschale_items: List[VorabpauschaleData]):
    """Prints detailed Vorabpauschale data."""
    print("\n--- Vorabpauschale Data (Diagnostic) ---")
    if not vorabpauschale_items:
        print("  No Vorabpauschale data generated.")
        return
    
    for vp_item_idx, vp_item in enumerate(vorabpauschale_items):
            print(f"  VP Item {vp_item_idx+1}: {vp_item}")


def print_withholding_tax_linking_diagnostic(events: List[FinancialEvent], asset_resolver: AssetResolver):
    """Prints diagnostic information about withholding tax linking."""
    from src.domain.events import WithholdingTaxEvent, CashFlowEvent

    print("\n--- Withholding Tax Linking Diagnostic ---")

    wht_events = [ev for ev in events if isinstance(ev, WithholdingTaxEvent)]

    if not wht_events:
        print("  No withholding tax events found.")
        return

    print(f"  Total withholding tax events: {len(wht_events)}")

    # Count linked vs unlinked events
    linked_events = [ev for ev in wht_events if getattr(ev, 'taxed_income_event_id', None) is not None]
    unlinked_events = [ev for ev in wht_events if getattr(ev, 'taxed_income_event_id', None) is None]

    print(f"  Linked events: {len(linked_events)}")
    print(f"  Unlinked events: {len(unlinked_events)}")

    if linked_events:
        # Show confidence distribution
        confidence_counts = {'high': 0, 'medium': 0, 'low': 0, 'unknown': 0}
        total_confidence = 0
        count_with_confidence = 0

        for wht_event in linked_events:
            confidence = getattr(wht_event, 'link_confidence_score', None)
            if confidence is not None:
                total_confidence += confidence
                count_with_confidence += 1
                if confidence >= 80:
                    confidence_counts['high'] += 1
                elif confidence >= 60:
                    confidence_counts['medium'] += 1
                else:
                    confidence_counts['low'] += 1
            else:
                confidence_counts['unknown'] += 1

        print(f"  Confidence distribution: High (≥80%): {confidence_counts['high']}, Medium (60-79%): {confidence_counts['medium']}, Low (<60%): {confidence_counts['low']}, Unknown: {confidence_counts['unknown']}")

        if count_with_confidence > 0:
            avg_confidence = total_confidence / count_with_confidence
            print(f"  Average confidence: {avg_confidence:.1f}%")

    if unlinked_events:
        print(f"\n  Unlinked withholding tax events ({len(unlinked_events)}):")
        for wht_event in unlinked_events:
            asset = asset_resolver.get_asset_by_id(wht_event.asset_internal_id)
            asset_desc = _get_asset_display_key(asset)
            amount_str = f"{wht_event.gross_amount_foreign_currency or 'N/A'} {wht_event.local_currency or 'N/A'}"
            print(f"    - Date: {wht_event.event_date}, Asset: {asset_desc}, Amount: {amount_str}")
            if wht_event.ibkr_activity_description:
                print(f"      Description: {wht_event.ibkr_activity_description}")

    # Show linking examples for linked events
    if linked_events:
        print(f"\n  Sample linked events (first 3):")
        for i, wht_event in enumerate(linked_events[:3]):
            asset = asset_resolver.get_asset_by_id(wht_event.asset_internal_id)
            asset_desc = _get_asset_display_key(asset)

            # Find the linked income event
            income_event = None
            if wht_event.taxed_income_event_id:
                income_event = next((ev for ev in events if ev.event_id == wht_event.taxed_income_event_id), None)

            confidence = getattr(wht_event, 'link_confidence_score', 'N/A')
            tax_rate = getattr(wht_event, 'effective_tax_rate', None)
            tax_rate_str = f"{(tax_rate * 100):.1f}%" if tax_rate else "N/A"

            print(f"    {i+1}. WHT Event: {wht_event.event_date}, {asset_desc}")
            print(f"       Amount: {wht_event.gross_amount_foreign_currency} {wht_event.local_currency}")
            print(f"       Confidence: {confidence}%, Tax Rate: {tax_rate_str}")

            if income_event:
                income_asset = asset_resolver.get_asset_by_id(income_event.asset_internal_id)
                income_asset_desc = _get_asset_display_key(income_asset)
                print(f"       Linked to: {income_event.event_type.name}, {income_asset_desc}")
                print(f"       Income Amount: {income_event.gross_amount_foreign_currency} {income_event.local_currency}")
            else:
                print(f"       Linked to: Event not found (ID: {wht_event.taxed_income_event_id})")

    print("--- End Withholding Tax Linking Diagnostic ---")


def print_asset_pl_summary_debug(
    asset_resolver: AssetResolver,
    realized_gains_losses: List[RealizedGainLoss]
):
    """Prints debug summary of each asset with classification and gross P/L."""
    import uuid

    # Aggregate P/L by asset
    asset_pl_map: Dict[uuid.UUID, Decimal] = defaultdict(Decimal)
    for rgl in realized_gains_losses:
        asset_pl_map[rgl.asset_internal_id] += rgl.gross_gain_loss_eur

    # Define category sort order
    category_order = {
        AssetCategory.STOCK: 1,
        AssetCategory.BOND: 2,
        AssetCategory.INVESTMENT_FUND: 3,
        AssetCategory.OPTION: 4,
        AssetCategory.CFD: 5,
        AssetCategory.PRIVATE_SALE_ASSET: 6,
        AssetCategory.CASH_BALANCE: 7,
        AssetCategory.UNKNOWN: 8,
    }

    # Define fund type sort order (for sub-sorting within INVESTMENT_FUND)
    fund_type_order = {
        InvestmentFundType.AKTIENFONDS: 1,
        InvestmentFundType.MISCHFONDS: 2,
        InvestmentFundType.IMMOBILIENFONDS: 3,
        InvestmentFundType.AUSLANDS_IMMOBILIENFONDS: 4,
        InvestmentFundType.SONSTIGE_FONDS: 5,
        InvestmentFundType.NONE: 6,
    }

    # Create sortable list
    def get_sort_key(item):
        asset_id, asset = item

        # Primary: Category order
        cat_order = category_order.get(asset.asset_category, 999)

        # Secondary: Fund type (if INVESTMENT_FUND)
        fund_order = 0
        if isinstance(asset, InvestmentFund):
            fund_order = fund_type_order.get(asset.fund_type, 999)

        # Tertiary: Alphanumeric by identifier
        try:
            identifier = asset.get_classification_key()
        except ValueError:
            identifier = str(asset.internal_asset_id)

        return (cat_order, fund_order, identifier)

    # Sort assets
    sorted_assets = sorted(
        asset_resolver.assets_by_internal_id.items(),
        key=get_sort_key
    )

    # Print header
    print("\n" + "=" * 110)
    print("DEBUG: Asset Summary with Classification and P/L")
    print("=" * 110)
    print(f"{'Classification':<40} | {'Identifier':<25} | {'Description':<25} | {'Gross P/L (EUR)':>15}")
    print("-" * 110)

    # Print each asset
    total_pl = Decimal('0')
    assets_with_pl = 0

    for asset_id, asset in sorted_assets:
        # Get full classification
        if isinstance(asset, InvestmentFund):
            fund_type_name = asset.fund_type.name if asset.fund_type else "NONE"
            classification = f"{asset.asset_category.name} / {fund_type_name}"
        else:
            classification = asset.asset_category.name

        # Get identifier
        try:
            identifier = asset.get_classification_key()
        except ValueError:
            identifier = f"ID_{str(asset.internal_asset_id)[:8]}"

        # Truncate for display
        identifier_display = identifier[:25]

        # Get description
        description = (asset.description or "N/A")[:25]

        # Get total P/L for this asset
        pl = asset_pl_map.get(asset_id, Decimal('0'))
        if pl != Decimal('0'):
            assets_with_pl += 1
        total_pl += pl

        # Format P/L
        pl_display = f"{pl:,.2f}"

        # Print row
        print(f"{classification:<40} | {identifier_display:<25} | {description:<25} | {pl_display:>15}")

    # Print summary
    print("-" * 110)
    print(f"Total Assets: {len(sorted_assets)}")
    print(f"Assets with Realized P/L: {assets_with_pl}")
    print(f"Total Gross P/L: {total_pl:,.2f} EUR")
    print("=" * 110)
