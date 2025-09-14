# src/reporting/console_reporter.py
import logging
from decimal import Decimal
from collections import defaultdict
from typing import List, Dict, Tuple, Optional 
import uuid 

from src.domain.results import RealizedGainLoss, VorabpauschaleData
from src.domain.events import FinancialEvent, WithholdingTaxEvent, CashFlowEvent, TradeEvent
from src.domain.enums import AssetCategory, InvestmentFundType, FinancialEventType, TaxReportingCategory, RealizationType
from src.domain.assets import Asset, InvestmentFund
from src.identification.asset_resolver import AssetResolver
import src.config as config
from src.utils.type_utils import parse_ibkr_date
from src.engine.loss_offsetting import LossOffsettingResult
from src.reporting.reporting_utils import _q, _q_qty, _q_price, get_kap_inv_category_for_reporting


logger = logging.getLogger(__name__)


def generate_console_tax_report(
    realized_gains_losses: List[RealizedGainLoss], 
    vorabpauschale_items: List[VorabpauschaleData], 
    all_financial_events: List[FinancialEvent], 
    asset_resolver: AssetResolver,
    tax_year: int,
    eoy_mismatch_count: int,
    loss_offsetting_summary: LossOffsettingResult 
):
    logger.info(f"Generating console tax declaration summary for tax year {tax_year}...")
    print(f"\n--- Tax Declaration Summary for Year {tax_year} (All amounts in EUR) ---")
    print("--- Figures for direct entry into German tax forms (as per PRD v3.2.2) ---")
    
    tax_year_start_date = parse_ibkr_date(f"{tax_year}-01-01")
    tax_year_end_date = parse_ibkr_date(f"{tax_year}-12-31")

    current_year_events: List[FinancialEvent] = []
    if tax_year_start_date and tax_year_end_date:
        for ev in all_financial_events: 
            ev_date = parse_ibkr_date(ev.event_date)
            if ev_date and tax_year_start_date <= ev_date <= tax_year_end_date:
                current_year_events.append(ev)
    else:
        current_year_events = list(all_financial_events) # Fallback, less likely

    current_year_rgls: List[RealizedGainLoss] = []
    if tax_year_start_date and tax_year_end_date:
        for rgl_item in realized_gains_losses:
            rgl_realization_date = parse_ibkr_date(rgl_item.realization_date)
            if rgl_realization_date and tax_year_start_date <= rgl_realization_date <= tax_year_end_date:
                current_year_rgls.append(rgl_item)
    else:
        current_year_rgls = list(realized_gains_losses) # Fallback

    # --- Anlage KAP (from LossOffsettingResult) ---
    print("\nAnlage KAP (Einkünfte aus Kapitalvermögen)")
    print(f"  Zeile 19 (Ausländische Kapitalerträge nach Saldierung, ohne Fonds & Derivatverluste): {_q(loss_offsetting_summary.form_line_values.get(TaxReportingCategory.ANLAGE_KAP_AUSLAENDISCHE_KAPITALERTRAEGE_GESAMT, Decimal(0)))}")
    print(f"  Zeile 20 (Gewinne aus Aktienveräußerungen): {_q(loss_offsetting_summary.form_line_values.get(TaxReportingCategory.ANLAGE_KAP_AKTIEN_GEWINN, Decimal(0)))}")
    print(f"  Zeile 21 (Einkünfte Stillhalterprämien & Gewinne Termingeschäfte): {_q(loss_offsetting_summary.form_line_values.get(TaxReportingCategory.ANLAGE_KAP_TERMIN_GEWINN, Decimal(0)))}")
    print(f"  Zeile 22 (Verluste Kapitalerträge ohne Aktien & Termingeschäfte): {_q(loss_offsetting_summary.form_line_values.get(TaxReportingCategory.ANLAGE_KAP_SONSTIGE_VERLUSTE, Decimal(0)))}")
    print(f"  Zeile 23 (Verluste aus Aktienveräußerungen): {_q(loss_offsetting_summary.form_line_values.get(TaxReportingCategory.ANLAGE_KAP_AKTIEN_VERLUST, Decimal(0)))}")
    print(f"  Zeile 24 (Verluste aus Termingeschäften): {_q(loss_offsetting_summary.form_line_values.get(TaxReportingCategory.ANLAGE_KAP_TERMIN_VERLUST, Decimal(0)))}")

    # --- WHT (From centralized calculation) ---
    wht_total_eur = loss_offsetting_summary.form_line_values.get(TaxReportingCategory.ANLAGE_KAP_FOREIGN_TAX_PAID, Decimal(0))
    print(f"  Zeile 41 (Anrechenbare ausländische Steuern): {_q(wht_total_eur)}")
    
    # Add linking statistics for withholding tax events
    wht_events = [ev for ev in current_year_events if isinstance(ev, WithholdingTaxEvent)]
    if wht_events:
        linked_wht_events = [ev for ev in wht_events if getattr(ev, 'taxed_income_event_id', None) is not None]
        unlinked_wht_events = [ev for ev in wht_events if getattr(ev, 'taxed_income_event_id', None) is None]
        
        print(f"    └─ Quellensteuer-Ereignisse: {len(wht_events)} gesamt, {len(linked_wht_events)} verknüpft, {len(unlinked_wht_events)} nicht verknüpft")
        
        if linked_wht_events:
            # Show confidence distribution
            high_confidence = len([ev for ev in linked_wht_events if getattr(ev, 'link_confidence_score', 0) >= 80])
            medium_confidence = len([ev for ev in linked_wht_events if 60 <= getattr(ev, 'link_confidence_score', 0) < 80])
            low_confidence = len([ev for ev in linked_wht_events if getattr(ev, 'link_confidence_score', 0) < 60])
            print(f"    └─ Verknüpfungs-Konfidenz: {high_confidence} hoch (≥80%), {medium_confidence} mittel (60-79%), {low_confidence} niedrig (<60%)")
        
        if unlinked_wht_events:
            print(f"    └─ WARNUNG: {len(unlinked_wht_events)} Quellensteuer-Ereignisse konnten nicht mit Erträgen verknüpft werden")


    # --- Detailed Stock G/L (Gross, for transparency) ---
    stock_g_l_per_asset: Dict[uuid.UUID, Dict[str, Any]] = defaultdict( 
        lambda: {'description': 'Unknown Asset', 'total_gross_gain_loss': Decimal(0), 'realizations': []}
    )
    for rgl in current_year_rgls: # Use filtered list
        if rgl.asset_category_at_realization == AssetCategory.STOCK:
            asset = asset_resolver.get_asset_by_id(rgl.asset_internal_id)
            asset_desc = asset.description if asset and asset.description else f"Asset ID: {rgl.asset_internal_id}"
            stock_g_l_per_asset[rgl.asset_internal_id]['description'] = asset_desc
            current_total = stock_g_l_per_asset[rgl.asset_internal_id]['total_gross_gain_loss']
            if isinstance(current_total, Decimal):
                 stock_g_l_per_asset[rgl.asset_internal_id]['total_gross_gain_loss'] = current_total + (rgl.gross_gain_loss_eur or Decimal(0))

    print("\n  Detaillierte Aufschlüsselung: Gewinne/Verluste aus Aktienveräußerungen pro Aktie (Brutto, vor Verrechnung)")
    print("  " + "-"*80)
    print(f"  {'Aktienbezeichnung':<50} | {'Gesamt G/V (EUR)':>25}")
    print("  " + "-"*80)
    if stock_g_l_per_asset:
        sorted_stock_g_l = sorted(stock_g_l_per_asset.items(), key=lambda item: str(item[1]['description'])) 
        for _, data in sorted_stock_g_l:
            print(f"  {str(data['description']):<50} | {_q(data['total_gross_gain_loss'] if isinstance(data['total_gross_gain_loss'], Decimal) else Decimal(0)):>25}")
    else:
        print("  Keine Aktienveräußerungen in diesem Zeitraum erfasst.")
    print("  " + "-"*80)


    # --- Anlage KAP-INV (Gross figures) ---
    kap_inv_report_lines: Dict[TaxReportingCategory, Decimal] = defaultdict(Decimal)
    for rgl in current_year_rgls: # Use filtered list
        if rgl.asset_category_at_realization == AssetCategory.INVESTMENT_FUND:
            kap_inv_cat = get_kap_inv_category_for_reporting(rgl.fund_type_at_sale, is_distribution=False, is_gain=True)
            if kap_inv_cat:
                kap_inv_report_lines[kap_inv_cat] += rgl.gross_gain_loss_eur or Decimal(0)

    for event in current_year_events: # Already filtered for tax year
        asset = asset_resolver.get_asset_by_id(event.asset_internal_id)
        if not asset: continue
        if event.event_type == FinancialEventType.DISTRIBUTION_FUND and isinstance(asset, InvestmentFund):
            kap_inv_cat = get_kap_inv_category_for_reporting(asset.fund_type, is_distribution=True, is_gain=False)
            if kap_inv_cat:
                kap_inv_report_lines[kap_inv_cat] += event.gross_amount_eur or Decimal(0)
    
    print("\nAnlage KAP-INV (Investmenterträge - KEINE Alt-Anteile)")
    print("  Ausschüttungen (Brutto, vor Teilfreistellung):")
    print(f"    Zeile 4 (Aktienfonds): {_q(kap_inv_report_lines.get(TaxReportingCategory.ANLAGE_KAP_INV_AKTIENFONDS_AUSSCHUETTUNG_GROSS, Decimal(0)))}")
    print(f"    Zeile 5 (Mischfonds): {_q(kap_inv_report_lines.get(TaxReportingCategory.ANLAGE_KAP_INV_MISCHFONDS_AUSSCHUETTUNG_GROSS, Decimal(0)))}")
    print(f"    Zeile 6 (Immobilienfonds): {_q(kap_inv_report_lines.get(TaxReportingCategory.ANLAGE_KAP_INV_IMMOBILIENFONDS_AUSSCHUETTUNG_GROSS, Decimal(0)))}")
    print(f"    Zeile 7 (Auslands-Immobilienfonds): {_q(kap_inv_report_lines.get(TaxReportingCategory.ANLAGE_KAP_INV_AUSLANDS_IMMOBILIENFONDS_AUSSCHUETTUNG_GROSS, Decimal(0)))}")
    print(f"    Zeile 8 (Sonstige Investmentfonds): {_q(kap_inv_report_lines.get(TaxReportingCategory.ANLAGE_KAP_INV_SONSTIGE_FONDS_AUSSCHUETTUNG_GROSS, Decimal(0)))}")

    print("  Vorabpauschale (Brutto, vor Teilfreistellung) - für 2023: 0 EUR")
    vp_gross_by_fund_type: Dict[InvestmentFundType, Decimal] = defaultdict(Decimal)
    for vp_item in vorabpauschale_items: # Already filtered by engine for tax year in generation
        if vp_item.tax_year == tax_year: # Double check, though vp_items should be for tax_year
             vp_gross_by_fund_type[vp_item.fund_type] += vp_item.gross_vorabpauschale_eur

    print(f"    Zeile 9 (Aktienfonds Vorabpauschale): {_q(vp_gross_by_fund_type.get(InvestmentFundType.AKTIENFONDS, Decimal(0)))}")
    print(f"    Zeile 10 (Mischfonds Vorabpauschale): {_q(vp_gross_by_fund_type.get(InvestmentFundType.MISCHFONDS, Decimal(0)))}")
    print(f"    Zeile 11 (Immobilienfonds Vorabpauschale): {_q(vp_gross_by_fund_type.get(InvestmentFundType.IMMOBILIENFONDS, Decimal(0)))}")
    print(f"    Zeile 12 (Auslands-Immobilienfonds Vorabpauschale): {_q(vp_gross_by_fund_type.get(InvestmentFundType.AUSLANDS_IMMOBILIENFONDS, Decimal(0)))}")
    print(f"    Zeile 13 (Sonstige Fonds Vorabpauschale): {_q(vp_gross_by_fund_type.get(InvestmentFundType.SONSTIGE_FONDS, Decimal(0)) + vp_gross_by_fund_type.get(InvestmentFundType.NONE, Decimal(0)))}")


    print("  Gewinne/Verluste aus Veräußerung von Investmentfondsanteilen (Brutto, vor Teilfreistellung):")
    print(f"    Zeile 14 (Aktienfonds G/V): {_q(kap_inv_report_lines.get(TaxReportingCategory.ANLAGE_KAP_INV_AKTIENFONDS_GEWINN_GROSS, Decimal(0)))}")
    print(f"    Zeile 17 (Mischfonds G/V): {_q(kap_inv_report_lines.get(TaxReportingCategory.ANLAGE_KAP_INV_MISCHFONDS_GEWINN_GROSS, Decimal(0)))}")
    print(f"    Zeile 20 (Immobilienfonds G/V): {_q(kap_inv_report_lines.get(TaxReportingCategory.ANLAGE_KAP_INV_IMMOBILIENFONDS_GEWINN_GROSS, Decimal(0)))}")
    print(f"    Zeile 23 (Auslands-Immobilienfonds G/V): {_q(kap_inv_report_lines.get(TaxReportingCategory.ANLAGE_KAP_INV_AUSLANDS_IMMOBILIENFONDS_GEWINN_GROSS, Decimal(0)))}")
    print(f"    Zeile 26 (Sonstige Investmentfonds G/V): {_q(kap_inv_report_lines.get(TaxReportingCategory.ANLAGE_KAP_INV_SONSTIGE_FONDS_GEWINN_GROSS, Decimal(0)))}")

    # --- Anlage SO (from LossOffsettingResult) ---
    print("\nAnlage SO (Sonstige Einkünfte - §23 EStG Private Sales)")
    so_z54_value = loss_offsetting_summary.form_line_values.get("ANLAGE_SO_Z54_NET_GV", Decimal(0)) 
    print(f"  Zeile 54 (Aggregierter Gewinn/Verlust aus §23 EStG Veräußerungen): {_q(so_z54_value)}")
    if so_z54_value != Decimal(0):
         print("    (Details zu §23 EStG Transaktionen werden im PDF-Bericht erwartet.)")

    # --- Summary of Net Taxable Income per Conceptual Pot (from LossOffsettingResult) ---
    print("\n--- Zusammenfassung: Saldo der konzeptionellen Steuertöpfe (vor Anwendung Sparer-Pauschbetrag etc.) ---")
    print(f"  Saldo Aktien: {_q(loss_offsetting_summary.conceptual_net_stocks)}")
    
    print(f"  Saldo Termingeschäfte (konzeptionell, nach Verrechnung und ggf. Verlustbegrenzung): {_q(loss_offsetting_summary.conceptual_net_derivatives_capped)}")
    if loss_offsetting_summary.conceptual_net_derivatives_uncapped != loss_offsetting_summary.conceptual_net_derivatives_capped:
        print(f"     (Saldo Termingeschäfte vor konzeptioneller Verlustbegrenzung: {_q(loss_offsetting_summary.conceptual_net_derivatives_uncapped)})")
    print(f"     (Für Anlage KAP Zeile 24 deklarierte Verluste (Brutto, unbegrenzt): {_q(loss_offsetting_summary.form_line_values.get(TaxReportingCategory.ANLAGE_KAP_TERMIN_VERLUST, Decimal(0)))})")
    
    print(f"  Saldo Sonstige Kapitalerträge (nicht Fonds) & Investmentfonds (Netto, nach TF): {_q(loss_offsetting_summary.conceptual_net_other_income)}")

    # --- NEW DETAILED BREAKDOWN FOR Sonstige Kapitalerträge (nicht Fonds) - POSITIVE PART ---
    print(f"    Detaillierte positive Komponenten für 'Sonstige Kapitalerträge (nicht Fonds)' (Beitrag zu Anlage KAP Zeile 19):")
    
    sum_interest_income_gross = Decimal('0')
    sum_non_fund_dividends_gross = Decimal('0')
    sum_bond_gains_gross = Decimal('0')

    # Process events for interest and non-fund dividends
    for event in current_year_events: # Already filtered for tax year
        asset = asset_resolver.get_asset_by_id(event.asset_internal_id)
        if not asset:
            continue

        event_gross_eur = event.gross_amount_eur if event.gross_amount_eur is not None else Decimal('0')

        if event.event_type == FinancialEventType.INTEREST_RECEIVED and event_gross_eur > Decimal('0'):
            sum_interest_income_gross += event_gross_eur
        
        elif event.event_type == FinancialEventType.DIVIDEND_CASH and asset.asset_category == AssetCategory.STOCK and event_gross_eur > Decimal('0'):
            sum_non_fund_dividends_gross += event_gross_eur
            
        elif event.event_type == FinancialEventType.CORP_STOCK_DIVIDEND and asset.asset_category == AssetCategory.STOCK and event_gross_eur > Decimal('0'):
            # Assuming event_gross_eur for CORP_STOCK_DIVIDEND is the taxable FMV
            sum_non_fund_dividends_gross += event_gross_eur

    # Process RGLs for bond gains
    for rgl in current_year_rgls: # Already filtered for tax year
        if rgl.asset_category_at_realization == AssetCategory.BOND and \
           rgl.gross_gain_loss_eur is not None and rgl.gross_gain_loss_eur > Decimal('0'):
            sum_bond_gains_gross += rgl.gross_gain_loss_eur
            
    print(f"      Zinserträge (brutto positiv): {_q(sum_interest_income_gross)}")
    print(f"      Dividenden (Aktien, brutto positiv, inkl. steuerpfl. Stock-Dividenden): {_q(sum_non_fund_dividends_gross)}")
    print(f"      Gewinne aus Anleihenverkäufen (brutto positiv): {_q(sum_bond_gains_gross)}")
    
    total_kap_other_income_positive_components = sum_interest_income_gross + sum_non_fund_dividends_gross + sum_bond_gains_gross
    print(f"      Summe dieser positiven Komponenten (nicht Fonds): {_q(total_kap_other_income_positive_components)}")
    print(f"      (Hinweis: Gezahlte Stückzinsen mindern 'Sonstige Verluste'. Erhaltene Stückzinsen sind i.d.R. in 'Zinserträge' enthalten.)")
    # --- END OF NEW DETAILED BREAKDOWN ---

    print(f"  Saldo §23 EStG: {_q(loss_offsetting_summary.conceptual_net_p23_estg)}")

    print("\n--- Hinweise und Warnungen ---")
    if eoy_mismatch_count > 0:
        print(f"  ACHTUNG: {eoy_mismatch_count} kritische Differenzen bei der End-of-Year Mengenvalidierung festgestellt. Siehe Log für Details.")
    else:
        print("  Keine kritischen Differenzen bei der End-of-Year Mengenvalidierung festgestellt (basierend auf Log-Analyse).")

    print("  Die Berechnung der *anrechenbaren* ausländischen Quellensteuer ist nicht Teil dieses Tools (nur Summe der gezahlten für Z. 41).")
    print("  Verlustvorträge über Steuerjahre hinweg sind nicht implementiert.")
    print("  Die endgültige Steuerlast (Sparer-Pauschbetrag, Steuersätze, Soli, KiSt) wird nicht berechnet.")
    print("  Alle Angaben ohne Gewähr. Bitte überprüfen Sie alle Zahlen sorgfältig und konsultieren Sie ggf. einen Steuerberater.")
    print("--- Ende des Steuererklärungs-Summaries ---")

def generate_stock_trade_report_for_symbol(
    stock_symbol_arg: str,
    all_financial_events: List[FinancialEvent],
    rgl_items: List[RealizedGainLoss],
    asset_resolver: AssetResolver,
    tax_year: int
):
    logger.info(f"Generating stock trade details report for symbol '{stock_symbol_arg}' for tax year {tax_year}...")

    target_asset: Optional[Asset] = None
    alias_key_symbol = f"SYMBOL:{stock_symbol_arg.upper()}"
    target_asset = asset_resolver.get_asset_by_alias(alias_key_symbol)

    if not target_asset:
        for asset_obj in asset_resolver.assets_by_internal_id.values():
            if asset_obj.ibkr_symbol == stock_symbol_arg.upper() and asset_obj.asset_category == AssetCategory.STOCK:
                target_asset = asset_obj
                break

    if not target_asset:
        print(f"\nError: Stock with symbol '{stock_symbol_arg}' not found or not classified as STOCK.")
        return

    if target_asset.asset_category != AssetCategory.STOCK:
        print(f"\nWarning: Asset '{target_asset.description}' (Symbol: {stock_symbol_arg.upper()}) is type {target_asset.asset_category.name}, not STOCK. Report output for non-stock may be misleading.")

    print(f"\n--- Detailed Trade Report for: {target_asset.description or 'N/A'} (Symbol: {stock_symbol_arg.upper()}, Asset ID: {str(target_asset.internal_asset_id)[:8]}) ---")
    print(f"--- Tax Year: {tax_year} ---")

    tax_year_start_date = parse_ibkr_date(f"{tax_year}-01-01")
    tax_year_end_date = parse_ibkr_date(f"{tax_year}-12-31")

    # Filter events and RGLs for the current tax year and target asset for this report
    current_year_events_for_symbol_report: List[FinancialEvent] = []
    if tax_year_start_date and tax_year_end_date:
        for ev in all_financial_events: # Use all_financial_events passed to function
            ev_date = parse_ibkr_date(ev.event_date)
            if ev_date and tax_year_start_date <= ev_date <= tax_year_end_date:
                if ev.asset_internal_id == target_asset.internal_asset_id:
                    current_year_events_for_symbol_report.append(ev)
    else: # Fallback
        current_year_events_for_symbol_report = [
            ev for ev in all_financial_events if ev.asset_internal_id == target_asset.internal_asset_id
        ]
    
    current_year_rgls_for_symbol_report: List[RealizedGainLoss] = []
    if tax_year_start_date and tax_year_end_date:
        for rgl_item in rgl_items: # Use rgl_items passed to function
            rgl_realization_date = parse_ibkr_date(rgl_item.realization_date)
            if rgl_realization_date and tax_year_start_date <= rgl_realization_date <= tax_year_end_date:
                if rgl_item.asset_internal_id == target_asset.internal_asset_id:
                    current_year_rgls_for_symbol_report.append(rgl_item)
    else: # Fallback
        current_year_rgls_for_symbol_report = [
            rgl for rgl in rgl_items if rgl.asset_internal_id == target_asset.internal_asset_id
        ]

    asset_trades_in_year: List[TradeEvent] = []
    for event in current_year_events_for_symbol_report: # Already filtered by year and asset
        if isinstance(event, TradeEvent):
            asset_trades_in_year.append(event)

    if not asset_trades_in_year:
        print("No trades found for this asset in the specified tax year.")
        return

    asset_trades_in_year.sort(key=lambda e: (e.event_date, e.event_id))

    date_w, type_w, qty_w, price_w, curr_w = 10, 22, 15, 15, 4
    val_loc_w, comm_loc_w, net_val_loc_w = 18, 15, 18
    avg_acq_open_eur_w = 20 
    net_val_eur_w, gl_eur_w = 18, 20

    header_parts = [
        f"{'Date':<{date_w}}", f"{'Type':<{type_w}}", f"{'Qty':>{qty_w}}", f"{'Price':>{price_w}}", f"{'Curr':<{curr_w}}",
        f"{'Value (Local)':>{val_loc_w}}", f"{'Comm (Local)':>{comm_loc_w}}", f"{'Net Val (Local)':>{net_val_loc_w}}",
        f"{'Avg Acq/Open EUR':>{avg_acq_open_eur_w}}",
        f"{'Net Val (EUR)':>{net_val_eur_w}}", f"{'Realized G/L (EUR)':>{gl_eur_w}}"
    ]
    header = " | ".join(header_parts)
    print(header)
    print("-" * len(header))

    for trade in asset_trades_in_year: # Already filtered
        trade_date_str = trade.event_date
        trade_type_str = trade.event_type.name

        abs_quantity = trade.quantity.copy_abs() if trade.quantity else Decimal(0)
        price_local = trade.price_foreign_currency
        currency_str = trade.local_currency or "N/A"

        gross_value_local = abs_quantity * (price_local if price_local else Decimal(0))
        commission_local = trade.commission_foreign_currency or Decimal(0)

        net_value_local: Decimal
        if trade.event_type in [FinancialEventType.TRADE_BUY_LONG, FinancialEventType.TRADE_BUY_SHORT_COVER]:
            net_value_local = gross_value_local + commission_local
        else:
            net_value_local = gross_value_local - commission_local

        net_value_eur = trade.net_proceeds_or_cost_basis_eur or Decimal(0)
        realized_gl_eur_sum = Decimal(0)
        avg_acq_open_price_eur_str = "N/A"

        is_realizing_trade = trade.event_type in [FinancialEventType.TRADE_SELL_LONG, FinancialEventType.TRADE_BUY_SHORT_COVER]

        if is_realizing_trade:
            rgl_for_event: List[RealizedGainLoss] = []
            # Use current_year_rgls_for_symbol_report which is already filtered by year and asset
            for r in current_year_rgls_for_symbol_report: 
                if r.originating_event_id == trade.event_id: # Match specific RGLs to this trade event
                    rgl_for_event.append(r)
            
            if rgl_for_event:
                realized_gl_eur_sum = sum(r.gross_gain_loss_eur for r in rgl_for_event if r.gross_gain_loss_eur is not None)
                total_qty_from_rgls = sum(r.quantity_realized for r in rgl_for_event if r.quantity_realized is not None)
                if total_qty_from_rgls > Decimal(0):
                    if trade.event_type == FinancialEventType.TRADE_SELL_LONG:
                        weighted_sum_cost_basis = sum(
                            r.quantity_realized * r.unit_cost_basis_eur
                            for r in rgl_for_event 
                            if r.quantity_realized is not None and r.unit_cost_basis_eur is not None
                        )
                        avg_price = weighted_sum_cost_basis / total_qty_from_rgls
                        avg_acq_open_price_eur_str = f"{_q_price(avg_price)}"
                    elif trade.event_type == FinancialEventType.TRADE_BUY_SHORT_COVER:
                        weighted_sum_orig_proceeds = sum(
                            r.quantity_realized * r.unit_realization_value_eur
                            for r in rgl_for_event
                            if r.quantity_realized is not None and r.unit_realization_value_eur is not None
                        )
                        avg_price = weighted_sum_orig_proceeds / total_qty_from_rgls
                        avg_acq_open_price_eur_str = f"{_q_price(avg_price)}"
                
                rgl_display_str = f"{_q(realized_gl_eur_sum)}"
            else:
                rgl_display_str = "N/A (No RGL)"
        else: 
            rgl_display_str = "N/A"

        qty_str = f"{_q_qty(abs_quantity)}"
        price_str = f"{_q_price(price_local)}" if price_local is not None else "N/A"


        row_values = [
            f"{trade_date_str:<{date_w}}",
            f"{trade_type_str:<{type_w}}",
            f"{qty_str:>{qty_w}}",
            f"{price_str:>{price_w}}",
            f"{currency_str:<{curr_w}}",
            f"{_q(gross_value_local):>{val_loc_w}}",
            f"{_q(commission_local):>{comm_loc_w}}",
            f"{_q(net_value_local):>{net_val_loc_w}}",
            f"{avg_acq_open_price_eur_str:>{avg_acq_open_eur_w}}", 
            f"{_q(net_value_eur):>{net_val_eur_w}}",
            f"{rgl_display_str:>{gl_eur_w}}"
        ]
        print(" | ".join(row_values))

    print("-" * len(header))
    print("Notes:")
    print("  - 'Qty' is the absolute quantity of shares traded.")
    print("  - 'Price' is per share in local currency.")
    print("  - 'Value (Local)' is Qty * Price.")
    print("  - 'Net Val (Local)' is Value (Local) +/- Commission (Local).")
    print("  - 'Avg Acq/Open EUR' is the weighted average EUR cost per share for shares sold (long positions),")
    print("    or the weighted average EUR proceeds per share from opening short sales (for short covers). N/A for opening trades.")
    print("  - 'Net Val (EUR)' is the trade's net cost or proceeds in EUR from IBKR data, including EUR commissions and option premium adjustments.")
    print("  - 'Realized G/L (EUR)' is shown for sell/cover trades. It sums all G/L (in EUR) from FIFO lots")
    print("    realized by that specific trade event within the tax year.")
    print("  - Realized G/L in local currency is not directly provided by this report due to FIFO complexities with")
    print("    historical exchange rates for cost basis calculation; all G/L is determined in EUR.")
