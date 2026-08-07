# src/engine/loss_offsetting.py
import logging
import uuid
from decimal import Decimal, Context
from collections import defaultdict
from typing import List, Dict, Optional

from src.domain.results import RealizedGainLoss, VorabpauschaleData, LossOffsettingResult
from src.domain.events import FinancialEvent, CashFlowEvent, WithholdingTaxEvent
from src.domain.enums import AssetCategory, FinancialEventType, InvestmentFundType, TaxReportingCategory
from src.domain.assets import Asset, InvestmentFund
from src.domain.exceptions import ProcessingError
from src.identification.asset_resolver import AssetResolver
from src.utils.tax_utils import get_teilfreistellung_rate_for_fund_type
from src.reporting.form_rules import get_form_rules
from src.processing.data_gaps import DataGapCollector, GapSeverity
import src.config as global_config

logger = logging.getLogger(__name__)

class LossOffsettingEngine:
    def __init__(self,
                 realized_gains_losses: List[RealizedGainLoss],
                 vorabpauschale_items: List[VorabpauschaleData],
                 current_year_financial_events: List[FinancialEvent],
                 asset_resolver: AssetResolver,
                 tax_year: int,
                 apply_conceptual_derivative_loss_capping: Optional[bool] = None,
                 # Optional so existing callers keep working. When absent, a Zeile 53 gap is
                 # logged but not collected into the report -- see
                 # _record_zeile_53_gap_if_funds_disposed.
                 data_gap_collector: Optional["DataGapCollector"] = None):
        # None -> read the user config AT CALL TIME (the previous module-global
        # default was bound at import time — ambient mutable state).
        if apply_conceptual_derivative_loss_capping is None:
            apply_conceptual_derivative_loss_capping = global_config.APPLY_CONCEPTUAL_DERIVATIVE_LOSS_CAPPING
        self.realized_gains_losses = realized_gains_losses
        self.vorabpauschale_items = vorabpauschale_items
        self.current_year_financial_events = current_year_financial_events
        self.asset_resolver = asset_resolver
        self.tax_year = tax_year
        self.apply_conceptual_derivative_loss_capping = apply_conceptual_derivative_loss_capping
        self.data_gap_collector = data_gap_collector
        # Built lazily by _income_gross_eur_by_event_id for the German-KESt rate test.
        self._income_gross_cache: Optional[Dict[uuid.UUID, Decimal]] = None

        self.ctx = Context(prec=global_config.INTERNAL_CALCULATION_PRECISION, rounding=global_config.DECIMAL_ROUNDING_MODE) # Renamed INTERNAL_WORKING_PRECISION
        self.TWO_PLACES = global_config.OUTPUT_PRECISION_AMOUNTS # Renamed from PRECISION_TOTAL_AMOUNTS

    def _calculate_net_fund_distribution(self, event: CashFlowEvent, asset: InvestmentFund) -> Decimal:
        if not isinstance(event, CashFlowEvent) or event.event_type != FinancialEventType.DISTRIBUTION_FUND:
            return self.ctx.create_decimal(Decimal('0'))
        if not isinstance(asset, InvestmentFund):
            logger.error(f"Asset {asset.internal_asset_id} for fund distribution event {event.event_id} is not of type InvestmentFund.")
            return event.gross_amount_eur if event.gross_amount_eur is not None else self.ctx.create_decimal(Decimal('0'))

        gross_dist_eur = event.gross_amount_eur
        if gross_dist_eur is None:
            return self.ctx.create_decimal(Decimal('0'))

        tf_rate = get_teilfreistellung_rate_for_fund_type(asset.fund_type)

        tf_amount = self.ctx.multiply(gross_dist_eur.copy_abs(), tf_rate)
        if gross_dist_eur >= Decimal('0'):
            net_dist_eur = self.ctx.subtract(gross_dist_eur, tf_amount)
        else:
            net_dist_eur = self.ctx.add(gross_dist_eur, tf_amount)

        return net_dist_eur.quantize(self.TWO_PLACES, context=self.ctx)


    # The German composite rate, 25% KESt x 1.055 SolZ = 26.375%
    # (reference/tax-law/estg-36-45a-kapitalertragsteuer-anrechnung.md [GT-CREDIT-025]).
    # The band around it is EMPIRICAL, not derived. Measured against real broker data, the
    # withheld amount is not reproducible from the paired gross by any simple rounding rule:
    # one-step round(gross x 0.26375, 2), two-step KESt-then-SolZ half-up, and two-step
    # round-down each reproduced exactly half of the known-German rows, with observed
    # deviations up to two cents. Rationale for the width is recorded in
    # docs/legal-implementation-map.md under GT-CREDIT-025; do not restate it as derived.
    _KEST_RATE_LOW = Decimal("26.30")
    _KEST_RATE_HIGH = Decimal("26.45")
    # IBKR emits this as a country code but it denotes "unknown/multiple", not a jurisdiction.
    _NON_COUNTRY_CODES = frozenset({"XX"})

    def _is_german_kest(self, event: WithholdingTaxEvent) -> bool:
        """Is this withholding German Kapitalertragsteuer rather than foreign tax?

        legal_basis: [GT-FORM-007] — German KESt on a German issuer's dividend is not an
        auslaendische Steuer and does not belong on Zeile 41. [GT-CREDIT-025] gives the
        26.375% composite that identifies it.

        Two signals, in order of authority. The issuer country decides when the broker
        supplies one; its availability depends on export vintage, so older data falls back
        to the rate composite. Both limits are recorded against GT-CREDIT-025 in
        docs/legal-implementation-map.md.

        A row that matches neither is treated as foreign, which is the pre-existing
        behaviour: this method narrows Zeile 41, it never widens it.
        """
        code = (event.source_country_code or "").strip().upper()
        if code and code not in self._NON_COUNTRY_CODES:
            return code == "DE"

        # No usable country code: fall back to the rate composite against the linked income.
        if event.taxed_income_event_id is None or event.gross_amount_eur is None:
            return False
        gross = self._income_gross_eur_by_event_id().get(event.taxed_income_event_id)
        if gross is None or gross <= 0:
            return False
        rate_pct = abs(event.gross_amount_eur) / gross * Decimal("100")
        return self._KEST_RATE_LOW <= rate_pct <= self._KEST_RATE_HIGH

    def _income_gross_eur_by_event_id(self) -> Dict[uuid.UUID, Decimal]:
        """Gross EUR income per event id, for the rate test. Built once per run."""
        if self._income_gross_cache is None:
            self._income_gross_cache = {
                e.event_id: e.gross_amount_eur
                for e in self.current_year_financial_events
                if isinstance(e, CashFlowEvent) and e.gross_amount_eur is not None
            }
        return self._income_gross_cache

    def _record_german_kest_gap(self, count: int, total_eur: Decimal) -> None:
        """Report German KESt that was excluded from Zeile 41 and cannot be declared for you.

        [GT-FORM-007] routes the credit to Zeile 7 with Zeilen 37/38/39. The engine does not
        fill those: Zeilen 7-15 are the figures *taken from* the Steuerbescheinigung of the
        inlaendische auszahlende Stelle, and 36 Abs. 2 Satz 2 bars the credit outright when no
        certificate is presented ([GT-CREDIT-022]). Zeile 7 transcribes a document the taxpayer
        holds; computing it here would fabricate the one figure the form defines as copied.

        Severity is WARNING, and the direction is what makes that honest: removing the amount
        from Zeile 41 *reduces* the credit claimed, so the declaration becomes more
        conservative, not income-understating. The taxpayer must obtain the certificate and
        fill Zeilen 7/37/38 by hand to recover the credit.
        """
        if count == 0:
            return
        detail = (
            f"{count} withholding row(s) totalling EUR {total_eur.quantize(self.TWO_PLACES, context=self.ctx)} "
            f"were identified as German Kapitalertragsteuer (25% KESt plus 5.5% SolZ) rather than "
            f"foreign withholding tax, and have been EXCLUDED from Anlage KAP Zeile 41, which is "
            f"for anrechenbare auslaendische Steuer only. This tax is creditable, but through "
            f"Zeile 7 with Zeilen 37/38/39 — and only on presentation of a Steuerbescheinigung "
            f"(36 Abs. 2 Satz 2 EStG). Those lines are transcribed from that certificate, so the "
            f"engine cannot fill them. Request the Steuerbescheinigung from the German custodian "
            f"via your broker and complete Zeilen 7/37/38 by hand, or the credit is lost."
        )
        if self.data_gap_collector is not None:
            self.data_gap_collector.record(
                code="ANLAGE_KAP_GERMAN_KEST_NOT_DECLARABLE",
                subject=f"Anlage KAP Zeilen 7/37/38 ({self.tax_year})",
                detail=detail,
                severity=GapSeverity.WARNING,
            )
        else:
            logger.warning(
                "Data gap [ANLAGE_KAP_GERMAN_KEST_NOT_DECLARABLE] "
                "Anlage KAP Zeilen 7/37/38 (%d): %s", self.tax_year, detail
            )

    def _record_zeile_53_gap_if_funds_disposed(self) -> None:
        """Report that Anlage KAP-INV Zeile 53 cannot be filled by the engine.

        Zeile 53 takes the Vorabpauschalen assessed during the holding period of the units
        disposed of, gross of Teilfreistellung (19 Abs. 1 S. 3-4 InvStG), and only so far as
        they were actually brought to tax -- for a foreign broker's units the Anleitung makes
        that condition explicit. Computing it needs per-lot Vorabpauschale history across every
        year the lot was held, which this engine does not keep.

        Severity is WARNING, not FAIL_FAST, and the direction matters: omitting the deduction
        leaves the declared fund gain **overstated**, so the figures are complete and
        conservative rather than income-understating. That is the WARNING contract in
        src/processing/data_gaps.py. The taxpayer must supply Zeile 53 by hand from their prior
        returns before filing.

        Nothing is reported when no fund units were disposed of: Zeile 53 is then legitimately
        empty and there is no gap.
        """
        disposed_funds = {
            rgl.asset_internal_id
            for rgl in self.realized_gains_losses
            if rgl.asset_category_at_realization == AssetCategory.INVESTMENT_FUND
        }
        if not disposed_funds:
            return

        detail = (
            f"{len(disposed_funds)} investment fund position(s) were disposed of in "
            f"{self.tax_year}. Anlage KAP-INV Zeile 53 ('Waehrend der Besitzzeit angesetzte "
            f"Vorabpauschalen', before Teilfreistellung) reduces the disposal gain by the "
            f"Vorabpauschalen assessed over the holding period of those units, so far as they "
            f"were declared in earlier years (19 Abs. 1 S. 3-4 InvStG). The engine does not "
            f"track per-lot Vorabpauschale history and leaves the line empty, which OVERSTATES "
            f"the declared fund gain. Fill Zeile 53 by hand from the Vorabpauschalen reported "
            f"on Zeilen 9-13 of your earlier returns for these units."
        )
        if self.data_gap_collector is not None:
            self.data_gap_collector.record(
                code="KAP_INV_Z53_VORABPAUSCHALE_DEDUCTION_NOT_COMPUTED",
                subject=f"Anlage KAP-INV Zeile 53 ({self.tax_year})",
                detail=detail,
                severity=GapSeverity.WARNING,
            )
        else:
            logger.warning(
                "Data gap [KAP_INV_Z53_VORABPAUSCHALE_DEDUCTION_NOT_COMPUTED] "
                "Anlage KAP-INV Zeile 53 (%d): %s", self.tax_year, detail
            )

    def calculate_reporting_figures(self) -> LossOffsettingResult:
        result = LossOffsettingResult()

        stock_gains_gross = self.ctx.create_decimal(Decimal('0'))
        stock_losses_abs = self.ctx.create_decimal(Decimal('0'))
        derivative_gains_gross = self.ctx.create_decimal(Decimal('0'))
        derivative_losses_abs = self.ctx.create_decimal(Decimal('0'))
        kap_other_income_positive = self.ctx.create_decimal(Decimal('0'))
        kap_other_losses_abs = self.ctx.create_decimal(Decimal('0'))

        fund_income_net_taxable = self.ctx.create_decimal(Decimal('0'))

        p23_net_total = self.ctx.create_decimal(Decimal('0'))

        for rgl in self.realized_gains_losses:
            gross_gl_eur = rgl.gross_gain_loss_eur if rgl.gross_gain_loss_eur is not None else self.ctx.create_decimal(Decimal('0'))

            cat = rgl.asset_category_at_realization
            if cat == AssetCategory.STOCK:
                if gross_gl_eur > Decimal('0'):
                    stock_gains_gross = self.ctx.add(stock_gains_gross, gross_gl_eur)
                else:
                    stock_losses_abs = self.ctx.add(stock_losses_abs, gross_gl_eur.copy_abs())
            elif cat in [AssetCategory.OPTION, AssetCategory.CFD, AssetCategory.FUTURE]:
                if gross_gl_eur > Decimal('0'):
                    derivative_gains_gross = self.ctx.add(derivative_gains_gross, gross_gl_eur)
                else:
                    derivative_losses_abs = self.ctx.add(derivative_losses_abs, gross_gl_eur.copy_abs())
            elif cat in [AssetCategory.BOND, AssetCategory.SONSTIGE_KAPITALFORDERUNG]:
                # Both are 20 Abs. 2 Satz 1 Nr. 7 income: Zeile 19 for a gain, Zeile 22 for
                # a loss. SONSTIGE_KAPITALFORDERUNG carries the Nr. 7 instruments that are
                # not bonds -- unbacked commodity ETCs ([GT-ESTG23-011], Rz. 57),
                # Zertifikate and unallocated spot metal ([GT-ESTG20-038], Rz. 9).
                if gross_gl_eur > Decimal('0'):
                    kap_other_income_positive = self.ctx.add(kap_other_income_positive, gross_gl_eur)
                else:
                    kap_other_losses_abs = self.ctx.add(kap_other_losses_abs, gross_gl_eur.copy_abs())
            elif cat == AssetCategory.INVESTMENT_FUND:
                net_gl_eur_after_tf = rgl.net_gain_loss_after_teilfreistellung_eur
                if net_gl_eur_after_tf is None:
                     logger.warning(f"RGL {rgl.originating_event_id} for fund {rgl.asset_internal_id} has no net_gain_loss_after_teilfreistellung_eur. Using gross_gain_loss_eur.")
                     net_gl_eur_after_tf = gross_gl_eur

                fund_income_net_taxable = self.ctx.add(fund_income_net_taxable, net_gl_eur_after_tf)

            elif cat == AssetCategory.PRIVATE_SALE_ASSET:
                if rgl.is_taxable_under_section_23:
                    p23_net_total = self.ctx.add(p23_net_total, gross_gl_eur)

            elif cat == AssetCategory.CASH_BALANCE:
                # FX gains/losses go to "Other Capital Income" under Section 20 EStG
                # Per BMF circular May 2022 (para. 131): IBKR FX reserves are interest-bearing
                if gross_gl_eur > Decimal('0'):
                    kap_other_income_positive = self.ctx.add(kap_other_income_positive, gross_gl_eur)
                else:
                    kap_other_losses_abs = self.ctx.add(kap_other_losses_abs, gross_gl_eur.copy_abs())

        stueckzinsen_paid_sum = self.ctx.create_decimal(Decimal('0')) # Only used for logging/future explicit handling

        for event in self.current_year_financial_events:
            asset_resolved = self.asset_resolver.get_asset_by_id(event.asset_internal_id)
            if not asset_resolved:
                raise ProcessingError(f"LossOffsettingEngine: could not resolve asset ID {event.asset_internal_id} for financial event {event.event_id} ({event.event_type.name}).")

            event_gross_eur = event.gross_amount_eur if event.gross_amount_eur is not None else self.ctx.create_decimal(Decimal('0'))

            if event.event_type == FinancialEventType.DIVIDEND_CASH and isinstance(asset_resolved, Asset) and asset_resolved.asset_category == AssetCategory.STOCK:
                if event_gross_eur > Decimal('0'):
                    kap_other_income_positive = self.ctx.add(kap_other_income_positive, event_gross_eur)
            elif event.event_type == FinancialEventType.INTEREST_RECEIVED:
                 if event_gross_eur > Decimal('0'):
                    kap_other_income_positive = self.ctx.add(kap_other_income_positive, event_gross_eur)
            elif event.event_type == FinancialEventType.INTEREST_PAID_STUECKZINSEN:
                 stueckzinsen_paid_sum = self.ctx.add(stueckzinsen_paid_sum, event_gross_eur.copy_abs())
                 # According to PRD Section 2.6, paid Stückzinsen reduce "Other Capital Income".
                 # If they are reliably parsed as negative amounts, this would be:
                 # kap_other_income_positive = self.ctx.add(kap_other_income_positive, event_gross_eur)
                 # Or if always positive cost:
                 if event_gross_eur.copy_abs() > Decimal('0'): # ensure non-zero before adding to losses
                    kap_other_losses_abs = self.ctx.add(kap_other_losses_abs, event_gross_eur.copy_abs())

            elif event.event_type == FinancialEventType.DISTRIBUTION_FUND and isinstance(asset_resolved, InvestmentFund):
                net_dist_eur = self._calculate_net_fund_distribution(event, asset_resolved)
                fund_income_net_taxable = self.ctx.add(fund_income_net_taxable, net_dist_eur)
            elif event.event_type == FinancialEventType.CORP_STOCK_DIVIDEND:
                 if isinstance(asset_resolved, Asset) and asset_resolved.asset_category == AssetCategory.STOCK and event_gross_eur > Decimal('0'):
                    kap_other_income_positive = self.ctx.add(kap_other_income_positive, event_gross_eur)
            elif event.event_type == FinancialEventType.CAPITAL_REPAYMENT:
                 # Capital repayments themselves don't create taxable income
                 # Excess amounts are now handled as separate DIVIDEND_CASH events
                 pass

        for vp_item in self.vorabpauschale_items:
            # `declaration_year` is the VZ this Vorabpauschale belongs on: the VP for calendar
            # X flows on the first working day of X+1 (18 Abs. 3 InvStG). The engine builds the
            # items for calendar `tax_year - 1`, so this selects them.
            if vp_item.declaration_year == self.tax_year:
                net_vp_eur = vp_item.net_taxable_vorabpauschale_eur
                if net_vp_eur is None:
                    logger.warning(f"Vorabpauschale item for asset {vp_item.asset_internal_id} has no net_taxable_vorabpauschale_eur. Assuming 0.")
                    net_vp_eur = self.ctx.create_decimal(Decimal('0'))

                fund_income_net_taxable = self.ctx.add(fund_income_net_taxable, net_vp_eur)

        result.conceptual_fund_income_net_taxable = fund_income_net_taxable.quantize(self.TWO_PLACES, context=self.ctx)

        # --- Anlage KAP-INV Zeile 53 ---
        # "Waehrend der Besitzzeit angesetzte Vorabpauschalen", before Teilfreistellung
        # (19 Abs. 1 S. 3-4 InvStG). This is the Vorabpauschale accumulated over the holding
        # period OF THE UNITS DISPOSED OF, across every year they were held, and only so far as
        # it was actually brought to tax.
        #
        # The engine cannot compute it: there is no per-lot Vorabpauschale accumulation, and no
        # record of which prior years' Vorabpauschalen were declared. Until 2026-08-03 this line
        # carried the sum of the CURRENT year's gross Vorabpauschalen under the label "Z55" --
        # wrong line, wrong quantity, and plausible enough to file. It now emits nothing and
        # says so. See reference/investment-tax-law/invstg-19-veraeusserungsgewinne.md.
        self._record_zeile_53_gap_if_funds_disposed()

        # Calculate foreign tax paid (Zeile 41). German KESt is not an auslaendische Steuer and
        # is excluded here -- see _is_german_kest and _record_german_kest_gap.
        # legal_basis: reference/tax-forms/anlage-kap-zeilen.md [GT-FORM-007].
        foreign_tax_total = self.ctx.create_decimal(Decimal('0'))
        german_kest_total = self.ctx.create_decimal(Decimal('0'))
        german_kest_count = 0
        for event in self.current_year_financial_events:
            if isinstance(event, WithholdingTaxEvent):
                tax_amount = event.gross_amount_eur if event.gross_amount_eur is not None else self.ctx.create_decimal(Decimal('0'))
                if self._is_german_kest(event):
                    german_kest_total = self.ctx.add(german_kest_total, tax_amount)
                    german_kest_count += 1
                    continue
                foreign_tax_total = self.ctx.add(foreign_tax_total, tax_amount)
        self._record_german_kest_gap(german_kest_count, german_kest_total)

        # Store raw component values for reporters (always available regardless of form year)
        result.raw_derivative_gains_gross = derivative_gains_gross.quantize(self.TWO_PLACES, context=self.ctx)
        result.raw_derivative_losses_abs = derivative_losses_abs.quantize(self.TWO_PLACES, context=self.ctx)
        result.raw_other_losses_abs = kap_other_losses_abs.quantize(self.TWO_PLACES, context=self.ctx)

        # Year-specific form rules
        form_rules = get_form_rules(self.tax_year)

        # Anlage KAP Line Calculations (as per PRD Sec 2.7, year-dependent)
        result.form_line_values[TaxReportingCategory.ANLAGE_KAP_AKTIEN_GEWINN] = stock_gains_gross.quantize(self.TWO_PLACES, context=self.ctx)
        result.form_line_values[TaxReportingCategory.ANLAGE_KAP_AKTIEN_VERLUST] = stock_losses_abs.quantize(self.TWO_PLACES, context=self.ctx)
        result.form_line_values[TaxReportingCategory.ANLAGE_KAP_SONSTIGE_KAPITALERTRAEGE] = kap_other_income_positive.quantize(self.TWO_PLACES, context=self.ctx)
        result.form_line_values[TaxReportingCategory.ANLAGE_KAP_FOREIGN_TAX_PAID] = foreign_tax_total.quantize(self.TWO_PLACES, context=self.ctx)

        if form_rules.separate_derivative_lines:
            # <= 2024: Separate Z21 (derivative gains) and Z24 (derivative losses)
            result.form_line_values[TaxReportingCategory.ANLAGE_KAP_TERMIN_GEWINN] = derivative_gains_gross.quantize(self.TWO_PLACES, context=self.ctx)
            result.form_line_values[TaxReportingCategory.ANLAGE_KAP_TERMIN_VERLUST] = derivative_losses_abs.quantize(self.TWO_PLACES, context=self.ctx)
            # Z22: only non-stock, non-derivative losses
            result.form_line_values[TaxReportingCategory.ANLAGE_KAP_SONSTIGE_VERLUSTE] = kap_other_losses_abs.quantize(self.TWO_PLACES, context=self.ctx)
        else:
            # >= 2025: No separate derivative lines; derivative losses fold into Z22
            result.form_line_values[TaxReportingCategory.ANLAGE_KAP_TERMIN_GEWINN] = Decimal('0.00')
            result.form_line_values[TaxReportingCategory.ANLAGE_KAP_TERMIN_VERLUST] = Decimal('0.00')
            z22_combined = self.ctx.add(kap_other_losses_abs, derivative_losses_abs)
            result.form_line_values[TaxReportingCategory.ANLAGE_KAP_SONSTIGE_VERLUSTE] = z22_combined.quantize(self.TWO_PLACES, context=self.ctx)

        # Zeile 19 Calculation
        zeile_19_amount = self.ctx.add(stock_gains_gross, derivative_gains_gross)
        zeile_19_amount = self.ctx.add(zeile_19_amount, kap_other_income_positive)
        zeile_19_amount = self.ctx.subtract(zeile_19_amount, stock_losses_abs)
        zeile_19_amount = self.ctx.subtract(zeile_19_amount, kap_other_losses_abs)
        if form_rules.z19_subtracts_derivative_losses:
            # >= 2025: Derivative losses are no longer restricted, subtract them in Z19
            zeile_19_amount = self.ctx.subtract(zeile_19_amount, derivative_losses_abs)
        result.form_line_values[TaxReportingCategory.ANLAGE_KAP_AUSLAENDISCHE_KAPITALERTRAEGE_GESAMT] = zeile_19_amount.quantize(self.TWO_PLACES, context=self.ctx)


        # Anlage SO
        result.form_line_values["ANLAGE_SO_Z54_NET_GV"] = p23_net_total.quantize(self.TWO_PLACES, context=self.ctx)

        # Anlage KAP-INV (Gross Figures)
        kap_inv_gross_dist_collector = defaultdict(lambda: self.ctx.create_decimal(Decimal('0')))
        kap_inv_gross_gl_collector = defaultdict(lambda: self.ctx.create_decimal(Decimal('0')))
        kap_inv_gross_vop_collector = defaultdict(lambda: self.ctx.create_decimal(Decimal('0'))) # Should be 0 for 2023

        for event in self.current_year_financial_events:
            if isinstance(event, CashFlowEvent) and event.event_type == FinancialEventType.DISTRIBUTION_FUND:
                asset = self.asset_resolver.get_asset_by_id(event.asset_internal_id)
                if isinstance(asset, InvestmentFund) and event.gross_amount_eur is not None:
                    from src.reporting.reporting_utils import get_kap_inv_category_for_reporting
                    reporting_cat = get_kap_inv_category_for_reporting(asset.fund_type, is_distribution=True, is_gain=False) # For distributions
                    if reporting_cat:
                        kap_inv_gross_dist_collector[reporting_cat] = self.ctx.add(kap_inv_gross_dist_collector[reporting_cat], event.gross_amount_eur)

        for key, val in kap_inv_gross_dist_collector.items():
            result.form_line_values[key] = val.quantize(self.TWO_PLACES, context=self.ctx)

        for rgl in self.realized_gains_losses:
            if rgl.asset_category_at_realization == AssetCategory.INVESTMENT_FUND and rgl.gross_gain_loss_eur is not None:
                from src.reporting.reporting_utils import get_kap_inv_category_for_reporting
                reporting_cat = get_kap_inv_category_for_reporting(rgl.fund_type_at_sale, is_distribution=False, is_gain=True)
                if reporting_cat:
                     if rgl.tax_reporting_category:
                         kap_inv_gross_gl_collector[rgl.tax_reporting_category] = self.ctx.add(kap_inv_gross_gl_collector[rgl.tax_reporting_category], rgl.gross_gain_loss_eur)
                     else:
                         logger.warning(f"RGL for fund {rgl.asset_internal_id} missing tax_reporting_category. Using derived category {reporting_cat}.")
                         kap_inv_gross_gl_collector[reporting_cat] = self.ctx.add(kap_inv_gross_gl_collector[reporting_cat], rgl.gross_gain_loss_eur)


        for key, val in kap_inv_gross_gl_collector.items():
            result.form_line_values[key] = val.quantize(self.TWO_PLACES, context=self.ctx)

        # Gross Vorabpauschale onto Zeilen 9-13, selected by DECLARATION year: the VP for
        # calendar X is declared in VZ X+1 (18 Abs. 3 InvStG).
        for vp_item in self.vorabpauschale_items:
             if vp_item.declaration_year == self.tax_year and vp_item.gross_vorabpauschale_eur != Decimal(0):
                if vp_item.tax_reporting_category_gross:
                     kap_inv_gross_vop_collector[vp_item.tax_reporting_category_gross] = self.ctx.add(kap_inv_gross_vop_collector[vp_item.tax_reporting_category_gross], vp_item.gross_vorabpauschale_eur)

        for key, val in kap_inv_gross_vop_collector.items():
            result.form_line_values[key] = val.quantize(self.TWO_PLACES, context=self.ctx)

        # Conceptual Net Balances (as per PRD Sec 2.8)
        result.conceptual_net_stocks = (self.ctx.subtract(stock_gains_gross, stock_losses_abs)).quantize(self.TWO_PLACES, context=self.ctx)
        result.conceptual_net_other_income = (self.ctx.subtract(kap_other_income_positive, kap_other_losses_abs)).quantize(self.TWO_PLACES, context=self.ctx)
        result.conceptual_net_p23_estg = p23_net_total.quantize(self.TWO_PLACES, context=self.ctx)

        net_derivatives_uncapped = self.ctx.subtract(derivative_gains_gross, derivative_losses_abs)
        result.conceptual_net_derivatives_uncapped = net_derivatives_uncapped.quantize(self.TWO_PLACES, context=self.ctx)

        if form_rules.derivative_loss_cap_applies and self.apply_conceptual_derivative_loss_capping and net_derivatives_uncapped < Decimal('0'):
            capped_net_derivative_loss = max(net_derivatives_uncapped, self.ctx.create_decimal(Decimal('-20000')))
            result.conceptual_net_derivatives_capped = capped_net_derivative_loss.quantize(self.TWO_PLACES, context=self.ctx)
        else:
            result.conceptual_net_derivatives_capped = net_derivatives_uncapped.quantize(self.TWO_PLACES, context=self.ctx)

        return result
