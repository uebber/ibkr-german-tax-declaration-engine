# IBKR Flex Query Setup Guide

This document describes the Flex Queries needed to automate data retrieval for the German Tax Declaration Engine.

## Overview

The Flex Web Service API requires pre-configured query templates created in the IBKR Client Portal. Once created, you can fetch them programmatically with date overrides.

**Portal Location:** Client Portal → Performance & Reports → Flex Queries → Activity Flex Query

## Required Queries

You need to create **5 separate Activity Flex Queries**:

| Query Name | Purpose | Period Setting | Notes |
|------------|---------|----------------|-------|
| `trades_yearly` | Trade history | Last 365 Calendar Days | Use with date overrides for specific years |
| `cash_transactions_yearly` | Dividends, WHT, interest | Last 365 Calendar Days | Use with date overrides |
| `corporate_actions_yearly` | Splits, mergers, stock dividends | Last 365 Calendar Days | Use with date overrides |
| `positions_eoy` | End-of-year positions | Last Business Day | Override to Dec 31 |
| `positions_soy` | Start-of-year positions | Last Business Day | Override to Jan 1 |

---

## Query 1: Trades (`trades_yearly`)

### General Configuration
- **Query Name:** `trades_yearly`
- **Date Period:** Last 365 Calendar Days (will be overridden via API)
- **Date Format:** yyyy-MM-dd (ISO-8601)
- **Time Format:** HH:mm:ss
- **Output Format:** CSV

### Sections to Include
Enable **Trades** section only.

### Required Fields (Trades Section)
Select these fields in this order:

| Field Name | Maps to CSV Header |
|------------|-------------------|
| ClientAccountID | ClientAccountID |
| CurrencyPrimary | CurrencyPrimary |
| AssetClass | AssetClass |
| SubCategory | SubCategory |
| Symbol | Symbol |
| Description | Description |
| ISIN | ISIN |
| Strike | Strike |
| Expiry | Expiry |
| Put/Call | Put/Call |
| TradeDate | TradeDate |
| Quantity | Quantity |
| TradePrice | TradePrice |
| IBCommission | IBCommission |
| IBCommissionCurrency | IBCommissionCurrency |
| Buy/Sell | Buy/Sell |
| TransactionID | TransactionID |
| Notes/Codes | Notes/Codes |
| UnderlyingSymbol | UnderlyingSymbol |
| Conid | Conid |
| UnderlyingConid | UnderlyingConid |
| Multiplier | Multiplier |
| Open/CloseIndicator | Open/CloseIndicator |

**CRITICAL:** The `Open/CloseIndicator` field is essential for accurate trade classification (opening vs closing trades).

---

## Query 2: Cash Transactions (`cash_transactions_yearly`)

### General Configuration
- **Query Name:** `cash_transactions_yearly`
- **Date Period:** Last 365 Calendar Days
- **Date Format:** yyyy-MM-dd
- **Output Format:** CSV

### Sections to Include
Enable **Cash Transactions** section only.

### Required Fields (Cash Transactions Section)

| Field Name | Maps to CSV Header |
|------------|-------------------|
| ClientAccountID | ClientAccountID |
| CurrencyPrimary | CurrencyPrimary |
| AssetClass | AssetClass |
| SubCategory | SubCategory |
| Symbol | Symbol |
| Description | Description |
| SettleDate | SettleDate |
| Amount | Amount |
| Type | Type |
| Conid | Conid |
| UnderlyingConid | UnderlyingConid |
| ISIN | ISIN |
| IssuerCountryCode | IssuerCountryCode |
| TransactionID | TransactionID |

---

## Query 3: Corporate Actions (`corporate_actions_yearly`)

### General Configuration
- **Query Name:** `corporate_actions_yearly`
- **Date Period:** Last 365 Calendar Days
- **Date Format:** yyyy-MM-dd
- **Output Format:** CSV

### Sections to Include
Enable **Corporate Actions** section only.

### Required Fields (Corporate Actions Section)

| Field Name | Maps to CSV Header |
|------------|-------------------|
| ClientAccountID | ClientAccountID |
| Symbol | Symbol |
| Description | Description |
| ISIN | ISIN |
| ReportDate | Report Date |
| Code | Code |
| Type | Type |
| ActionID | ActionID |
| Conid | Conid |
| UnderlyingConid | UnderlyingConid |
| UnderlyingSymbol | UnderlyingSymbol |
| CurrencyPrimary | CurrencyPrimary |
| Amount | Amount |
| Proceeds | Proceeds |
| Value | Value |
| Quantity | Quantity |

---

## Query 4 & 5: Positions (`positions_eoy`, `positions_soy`)

### General Configuration
- **Query Name:** `positions_eoy` / `positions_soy`
- **Date Period:** Last Business Day (will be overridden to specific date)
- **Date Format:** yyyy-MM-dd
- **Output Format:** CSV

### Sections to Include
Enable **Open Positions** section only.

### Required Fields (Open Positions Section)

| Field Name | Maps to CSV Header |
|------------|-------------------|
| ClientAccountID | ClientAccountID |
| CurrencyPrimary | CurrencyPrimary |
| AssetClass | AssetClass |
| SubCategory | SubCategory |
| Symbol | Symbol |
| Description | Description |
| ISIN | ISIN |
| Quantity | Quantity |
| PositionValue | PositionValue |
| MarkPrice | MarkPrice |
| CostBasisMoney | CostBasisMoney |
| UnderlyingSymbol | UnderlyingSymbol |
| Conid | Conid |
| UnderlyingConid | UnderlyingConid |
| Multiplier | Multiplier |

---

## API Usage

Once you have created the queries and noted their Query IDs, update the configuration file.

### Endpoint Format

**SendRequest (Step 1):**
```
https://ndcdyn.interactivebrokers.com/AccountManagement/FlexWebService/SendRequest?t={TOKEN}&q={QUERY_ID}&v=3
```

**With Date Overrides:**
```
https://ndcdyn.interactivebrokers.com/AccountManagement/FlexWebService/SendRequest?t={TOKEN}&q={QUERY_ID}&fd={FROM_DATE}&td={TO_DATE}&v=3
```

**GetStatement (Step 2):**
```
https://ndcdyn.interactivebrokers.com/AccountManagement/FlexWebService/GetStatement?t={TOKEN}&q={REFERENCE_CODE}&v=3
```

### Parameters

| Parameter | Description | Format |
|-----------|-------------|--------|
| `t` | Access token from Client Portal | String |
| `q` | Query ID (SendRequest) or Reference Code (GetStatement) | Numeric |
| `fd` | From date override | yyyymmdd |
| `td` | To date override | yyyymmdd |
| `v` | API version (always use 3) | 3 |

### Headers Required
```
User-Agent: Python/3.11
```

### Date Range Limits
- Maximum 365 days per request
- For multi-year data, make multiple requests with different date ranges

---

## Example: Fetching 2024 Tax Year Data

### Trades (Full Year)
```bash
# From: 2024-01-01 To: 2024-12-31
curl -H "User-Agent: Python/3.11" \
  "https://ndcdyn.interactivebrokers.com/AccountManagement/FlexWebService/SendRequest?t=${TOKEN}&q=${TRADES_QUERY_ID}&fd=20240101&td=20241231&v=3"
```

### Positions Start of Year (2024-01-01)
```bash
# Single day: Jan 1, 2024
curl -H "User-Agent: Python/3.11" \
  "https://ndcdyn.interactivebrokers.com/AccountManagement/FlexWebService/SendRequest?t=${TOKEN}&q=${POSITIONS_QUERY_ID}&fd=20240101&td=20240101&v=3"
```

### Positions End of Year (2024-12-31)
```bash
# Single day: Dec 31, 2024
curl -H "User-Agent: Python/3.11" \
  "https://ndcdyn.interactivebrokers.com/AccountManagement/FlexWebService/SendRequest?t=${TOKEN}&q=${POSITIONS_QUERY_ID}&fd=20241231&td=20241231&v=3"
```

---

## Next Steps

1. Log into IBKR Client Portal
2. Navigate to: Performance & Reports → Flex Queries → Create Activity Flex Query
3. Create each of the 5 queries above with the specified fields
4. Note down the Query IDs
5. Enable Flex Web Service: Flex Queries → Flex Web Service Configuration → Enable
6. Generate/note your access token
7. Update `ibkr_flex_config.py` with your Query IDs (see next section)
