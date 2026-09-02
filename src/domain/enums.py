# src/domain/enums.py
from enum import Enum, auto

class AssetCategory(Enum):
    STOCK = auto()
    BOND = auto()
    # A sonstige Kapitalforderung under 20 Abs. 2 Satz 1 Nr. 7 that is NOT a bond:
    # an unbacked gold or commodity ETC (BMF 14.05.2025 Rz. 57, [GT-ESTG23-011]), a
    # Zertifikat (expressly not a Termingeschaeft, Rz. 9, [GT-ESTG20-038]), an
    # unallocated spot metal position at the broker (Q11, Reading C).
    #
    # It lands on the same Anlage KAP lines as BOND -- Zeile 19 / Zeile 22 -- but it is a
    # separate member on purpose: BOND used to carry both meanings, so nothing could
    # distinguish "this is a bond" from "this is something else on 19/22", and the
    # bond-only handling (percentage-of-nominal prices, Stueckzinsen, BM maturity) would
    # have applied to instruments that have none of those properties.
    SONSTIGE_KAPITALFORDERUNG = auto()
    INVESTMENT_FUND = auto()
    OPTION = auto()
    CFD = auto()
    FUTURE = auto()
    PRIVATE_SALE_ASSET = auto() # Renamed from SECTION_23_ESTG_ASSET
    CASH_BALANCE = auto()
    UNKNOWN = auto() # For assets that couldn't be definitively categorized initially

class InvestmentFundType(Enum):
    AKTIENFONDS = auto()
    MISCHFONDS = auto()
    IMMOBILIENFONDS = auto()
    AUSLANDS_IMMOBILIENFONDS = auto()
    SONSTIGE_FONDS = auto()
    NONE = auto() # Explicitly for non-funds or when fund type is not applicable/known

class FinancialEventType(Enum):
    TRADE_BUY_LONG = auto()
    TRADE_SELL_LONG = auto()
    TRADE_SELL_SHORT_OPEN = auto()
    TRADE_BUY_SHORT_COVER = auto()
    DIVIDEND_CASH = auto() # For stocks
    CAPITAL_REPAYMENT = auto() # For tax-free capital repayments (Einlagenrückgewähr)
    DISTRIBUTION_FUND = auto() # For investment funds
    INTEREST_RECEIVED = auto()
    INTEREST_PAID_STUECKZINSEN = auto()
    CORP_SPLIT_FORWARD = auto() # Renamed from CORP_ACTION_SPLIT_FORWARD
    CORP_MERGER_CASH = auto() # Renamed from CORP_ACTION_MERGER_CASH
    CORP_MERGER_STOCK = auto() # Renamed from CORP_ACTION_MERGER_STOCK
    CORP_STOCK_DIVIDEND = auto() # Renamed from CORP_ACTION_STOCK_DIVIDEND
    CORP_EXPIRE_DIVIDEND_RIGHTS = auto() # For ED corporate actions - used only for post-processing
    OPTION_EXERCISE = auto()
    OPTION_ASSIGNMENT = auto()
    OPTION_EXPIRATION_WORTHLESS = auto()
    OPTION_CASH_SETTLEMENT = auto()
    WITHHOLDING_TAX = auto()
    FEE_TRANSACTION = auto()
    CURRENCY_CONVERSION = auto() # From FX trades or explicit conversions
    INTERNAL_TRANSFER = auto() # A move of a holding between the taxpayer's own accounts ([GT-ESTG20-014])
    # A currency BALANCE moved between the taxpayer's own accounts. Deliberately not
    # INTERNAL_TRANSFER: that one relocates lots because a securities move is no disposal
    # ([GT-ESTG20-014]), and this one is the opposite — an Umbuchung of a
    # Fremdwaehrungsguthaben is a disposal of the sending account's Kapitalforderung and
    # an acquisition of the receiving account's ([GT-FX-009]). One enum member per legal
    # consequence, so no dispatch can confuse them.
    INTERNAL_CASH_TRANSFER = auto()

class RealizationType(Enum):
    """Defines how a gain or loss was realized."""
    LONG_POSITION_SALE = auto()          # Renamed from SALE_OF_LONG_INSTRUMENT
    SHORT_POSITION_COVER = auto()     # Renamed from COVERING_OF_SHORT_INSTRUMENT
    CASH_MERGER_PROCEEDS = auto()             # Renamed from CASH_MERGER_DISPOSAL
    OPTION_EXPIRED_LONG = auto() # Renamed from OPTION_EXPIRATION_WORTHLESS_LONG
    OPTION_EXPIRED_SHORT = auto()# Renamed from OPTION_EXPIRATION_WORTHLESS_SHORT
    OPTION_CASH_SETTLED_LONG = auto()            # Long option exercised with cash settlement (index options)
    OPTION_CASH_SETTLED_SHORT = auto()           # Short option assigned with cash settlement (index options)
    OPTION_TRADE_CLOSE_LONG = auto()          # Selling an option contract that was previously bought (Kept as per PRD body text analysis)
    OPTION_TRADE_CLOSE_SHORT = auto()         # Buying back an option contract that was previously sold short (Kept as per PRD body text analysis)
    # Note: Option exercises/assignments that result in stock delivery adjust the stock's
    # cost basis/proceeds and do not typically create a separate RGL for the option itself,
    # unless the option is traded out before exercise/assignment.

    # Currency/FX realization types (Phase 1-4: Explicit FX trades)
    FX_CONVERSION_SALE = auto()              # Long currency sold via explicit FX conversion
    FX_CONVERSION_SHORT_COVER = auto()       # Short currency position covered via explicit FX conversion

    # Currency/FX realization types (Phase 5a: Implicit currency from security trades)
    FX_IMPLICIT_SECURITY_PURCHASE = auto()   # Currency consumed to buy security (implicit FX disposal)
    FX_IMPLICIT_SECURITY_SALE = auto()       # Short currency covered by security sale proceeds

    # Currency/FX realization types (Phase 5c: Implicit currency from cash flows)
    # Also carry a balance moved between the taxpayer's own accounts ([GT-FX-009]): the
    # sending side consumes lots and the receiving side covers a short, which is the same
    # operation on the ledger. The names say "cashflow" and the label reaches the PDF, so
    # the comment has to say what else is in the set rather than let the name decide.
    FX_IMPLICIT_CASHFLOW_EXPENSE = auto()    # Currency consumed to pay fees/WHT, or moved out of an account (implicit FX disposal)
    FX_IMPLICIT_CASHFLOW_INCOME = auto()     # Short currency covered by dividend/interest receipt, or by a balance moved in

class TaxReportingCategory(Enum):
    ANLAGE_KAP_AKTIEN_GEWINN = auto()
    ANLAGE_KAP_AKTIEN_VERLUST = auto()
    ANLAGE_KAP_TERMIN_GEWINN = auto()
    ANLAGE_KAP_TERMIN_VERLUST = auto()
    # Zeile 19 / Zeile 22. Interest, non-fund dividends, stückzinsen, and disposals of
    # both AssetCategory.BOND and AssetCategory.SONSTIGE_KAPITALFORDERUNG.
    ANLAGE_KAP_SONSTIGE_KAPITALERTRAEGE = auto()
    ANLAGE_KAP_SONSTIGE_VERLUSTE = auto()
    ANLAGE_KAP_AUSLAENDISCHE_KAPITALERTRAEGE_GESAMT = auto() # Added for Zeile 19 as per PRD
    ANLAGE_KAP_FOREIGN_TAX_PAID = auto() # Zeile 41 - Anrechenbare ausländische Steuern

    # KAP-INV Gross Amounts (as per PRD for form lines)
    ANLAGE_KAP_INV_AKTIENFONDS_AUSSCHUETTUNG_GROSS = auto()
    ANLAGE_KAP_INV_AKTIENFONDS_GEWINN_GROSS = auto() # Covers gains and losses, sign indicates
    ANLAGE_KAP_INV_MISCHFONDS_AUSSCHUETTUNG_GROSS = auto()
    ANLAGE_KAP_INV_MISCHFONDS_GEWINN_GROSS = auto()
    ANLAGE_KAP_INV_IMMOBILIENFONDS_AUSSCHUETTUNG_GROSS = auto()
    ANLAGE_KAP_INV_IMMOBILIENFONDS_GEWINN_GROSS = auto()
    ANLAGE_KAP_INV_AUSLANDS_IMMOBILIENFONDS_AUSSCHUETTUNG_GROSS = auto()
    ANLAGE_KAP_INV_AUSLANDS_IMMOBILIENFONDS_GEWINN_GROSS = auto()
    ANLAGE_KAP_INV_SONSTIGE_FONDS_AUSSCHUETTUNG_GROSS = auto()
    ANLAGE_KAP_INV_SONSTIGE_FONDS_GEWINN_GROSS = auto()

    # Vorabpauschale will be zero for 2023, but categories are defined for completeness
    ANLAGE_KAP_INV_AKTIENFONDS_VORABPAUSCHALE_BRUTTO = auto()
    ANLAGE_KAP_INV_MISCHFONDS_VORABPAUSCHALE_BRUTTO = auto()
    ANLAGE_KAP_INV_IMMOBILIENFONDS_VORABPAUSCHALE_BRUTTO = auto() # Added
    ANLAGE_KAP_INV_AUSLANDS_IMMOBILIENFONDS_VORABPAUSCHALE_BRUTTO = auto() # Added
    ANLAGE_KAP_INV_SONSTIGE_FONDS_VORABPAUSCHALE_BRUTTO = auto() # Added

    # Zeile 53 -- "Waehrend der Besitzzeit angesetzte Vorabpauschalen", entered before
    # Teilfreistellung (19 Abs. 1 S. 3-4 InvStG). NOT Zeile 55, which is
    # "Gewinne aus der Veraeusserung von bestandsgeschuetzten Alt-Anteilen".
    # See reference/tax-forms/anlage-kap-inv-zeilen.md.
    ANLAGE_KAP_INV_VORABPAUSCHALE_ABZUG_Z53 = auto()

    SECTION_23_ESTG_TAXABLE_GAIN = auto()
    SECTION_23_ESTG_TAXABLE_LOSS = auto()
    SECTION_23_ESTG_EXEMPT_HOLDING_PERIOD_MET = auto() # For record keeping
    
    NON_TAXABLE_OTHER = auto() # For events that are processed but have no direct tax line impact by themselves
