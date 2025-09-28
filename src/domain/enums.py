# src/domain/enums.py
from enum import Enum, auto

class AssetCategory(Enum):
    STOCK = auto()
    BOND = auto()
    INVESTMENT_FUND = auto()
    OPTION = auto()
    CFD = auto()
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
    WITHHOLDING_TAX = auto()
    FEE_TRANSACTION = auto()
    CURRENCY_CONVERSION = auto() # From FX trades or explicit conversions

class RealizationType(Enum):
    """Defines how a gain or loss was realized."""
    LONG_POSITION_SALE = auto()          # Renamed from SALE_OF_LONG_INSTRUMENT
    SHORT_POSITION_COVER = auto()     # Renamed from COVERING_OF_SHORT_INSTRUMENT
    CASH_MERGER_PROCEEDS = auto()             # Renamed from CASH_MERGER_DISPOSAL
    OPTION_EXPIRED_LONG = auto() # Renamed from OPTION_EXPIRATION_WORTHLESS_LONG
    OPTION_EXPIRED_SHORT = auto()# Renamed from OPTION_EXPIRATION_WORTHLESS_SHORT
    OPTION_TRADE_CLOSE_LONG = auto()          # Selling an option contract that was previously bought (Kept as per PRD body text analysis)
    OPTION_TRADE_CLOSE_SHORT = auto()         # Buying back an option contract that was previously sold short (Kept as per PRD body text analysis)
    # Note: Option exercises/assignments that result in stock delivery adjust the stock's
    # cost basis/proceeds and do not typically create a separate RGL for the option itself,
    # unless the option is traded out before exercise/assignment.

class TaxReportingCategory(Enum):
    ANLAGE_KAP_AKTIEN_GEWINN = auto()
    ANLAGE_KAP_AKTIEN_VERLUST = auto()
    ANLAGE_KAP_TERMIN_GEWINN = auto()
    ANLAGE_KAP_TERMIN_VERLUST = auto()
    ANLAGE_KAP_SONSTIGE_KAPITALERTRAEGE = auto() # Interest, non-fund dividends, bond gains, stückzinsen
    ANLAGE_KAP_SONSTIGE_VERLUSTE = auto() # Bond losses, etc.
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

    SECTION_23_ESTG_TAXABLE_GAIN = auto()
    SECTION_23_ESTG_TAXABLE_LOSS = auto()
    SECTION_23_ESTG_EXEMPT_HOLDING_PERIOD_MET = auto() # For record keeping
    
    NON_TAXABLE_OTHER = auto() # For events that are processed but have no direct tax line impact by themselves
