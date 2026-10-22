# Power BI version: data model + DAX

The same KPIs the web dashboard shows, written as DAX so the model can be rebuilt in Power BI Desktop in about 30 minutes.
Source files: `data/raw/*.csv` (star schema). Amounts are stored as positive numbers; the sign comes from the account `category`.

## 1. Load and model

Get Data → Text/CSV → load the five files in `data/raw/`, then create these relationships (all one-to-many, single direction):

| From (one) | To (many) |
|---|---|
| `dim_entity[entity_id]` | `fact_pnl[entity_id]`, `fact_balance[entity_id]` |
| `dim_account[account_id]` | `fact_pnl[account_id]`, `fact_balance[account_id]` |
| `dim_date[month]` | `fact_pnl[month]`, `fact_balance[month]` |

Mark `dim_date` as the date table (Table tools → Mark as date table → `month`). Set `month` to Date type in Power Query.

## 2. P&L measures

```dax
Revenue =
CALCULATE ( SUM ( fact_pnl[actual] ), dim_account[category] = "Revenue" )

Revenue Budget =
CALCULATE ( SUM ( fact_pnl[budget] ), dim_account[category] = "Revenue" )

Direct Costs =
CALCULATE ( SUM ( fact_pnl[actual] ), dim_account[category] = "COGS" )

Opex =
CALCULATE ( SUM ( fact_pnl[actual] ), dim_account[category] = "Opex" )

Gross Profit = [Revenue] - [Direct Costs]

EBITDA = [Gross Profit] - [Opex]

EBITDA Budget =
[Revenue Budget]
    - CALCULATE ( SUM ( fact_pnl[budget] ), dim_account[category] = "COGS" )
    - CALCULATE ( SUM ( fact_pnl[budget] ), dim_account[category] = "Opex" )

Net Income =
[EBITDA]
    - CALCULATE ( SUM ( fact_pnl[actual] ),
        dim_account[category] IN { "D&A", "Interest", "Tax" } )

Gross Margin % = DIVIDE ( [Gross Profit], [Revenue] )
EBITDA Margin % = DIVIDE ( [EBITDA], [Revenue] )
Net Margin % = DIVIDE ( [Net Income], [Revenue] )
```

## 3. Budget vs actual

```dax
Revenue Var = [Revenue] - [Revenue Budget]
Revenue Var % = DIVIDE ( [Revenue Var], [Revenue Budget] )

EBITDA Var = [EBITDA] - [EBITDA Budget]
EBITDA Var % = DIVIDE ( [EBITDA Var], ABS ( [EBITDA Budget] ) )

-- Cost overrun on a single line (use with dim_account[account_name] on rows)
Cost Var % =
VAR _act = SUM ( fact_pnl[actual] )
VAR _bud = SUM ( fact_pnl[budget] )
RETURN DIVIDE ( _act - _bud, _bud )

-- Conditional-format colour (green = favourable)
Var Colour =
IF ( [EBITDA Var] >= 0, "#1F8A5B", "#C0392B" )
```

## 4. Time intelligence

```dax
Revenue PY =
CALCULATE ( [Revenue], SAMEPERIODLASTYEAR ( dim_date[month] ) )

Revenue YoY % = DIVIDE ( [Revenue] - [Revenue PY], [Revenue PY] )

Revenue YTD = TOTALYTD ( [Revenue], dim_date[month] )

EBITDA TTM =
CALCULATE ( [EBITDA], DATESINPERIOD ( dim_date[month], MAX ( dim_date[month] ), -12, MONTH ) )

Net Income TTM =
CALCULATE ( [Net Income], DATESINPERIOD ( dim_date[month], MAX ( dim_date[month] ), -12, MONTH ) )
```

## 5. Balance sheet (point-in-time: use the last month in context)

```dax
-- Helper: balance of one account at the latest month in the filter context
Balance (latest month) =
VAR _m = MAX ( dim_date[month] )
RETURN CALCULATE ( SUM ( fact_balance[amount] ), dim_date[month] = _m )

Cash =
CALCULATE ( [Balance (latest month)], dim_account[account_id] = 1010 )

Receivables =
CALCULATE ( [Balance (latest month)], dim_account[account_id] = 1100 )

Payables =
CALCULATE ( [Balance (latest month)], dim_account[account_id] = 2100 )

Current Assets =
CALCULATE ( [Balance (latest month)], dim_account[category] = "Current assets" )

Current Liabilities =
CALCULATE ( [Balance (latest month)], dim_account[category] = "Current liabilities" )

Total Assets =
CALCULATE ( [Balance (latest month)], dim_account[statement] = "BS",
    dim_account[category] IN { "Current assets", "Non-current assets" } )

Equity =
CALCULATE ( [Balance (latest month)], dim_account[account_id] = 3100 )

Debt =
CALCULATE ( [Balance (latest month)], dim_account[account_id] IN { 2300, 2500 } )

Net Debt = [Debt] - [Cash]
Working Capital = [Current Assets] - [Current Liabilities]
Current Ratio = DIVIDE ( [Current Assets], [Current Liabilities] )
Quick Ratio = DIVIDE ( [Cash] + [Receivables], [Current Liabilities] )
Net Debt / EBITDA = DIVIDE ( [Net Debt], [EBITDA TTM] )

ROA (TTM) = DIVIDE ( [Net Income TTM], [Total Assets] )
ROE (TTM) = DIVIDE ( [Net Income TTM], [Equity] )
```

## 6. DSO / DPO (3-month rolling, same definition as the SQL layer)

```dax
Revenue 3M =
CALCULATE ( [Revenue], DATESINPERIOD ( dim_date[month], MAX ( dim_date[month] ), -3, MONTH ) )

Direct Costs 3M =
CALCULATE ( [Direct Costs], DATESINPERIOD ( dim_date[month], MAX ( dim_date[month] ), -3, MONTH ) )

DSO = DIVIDE ( [Receivables], [Revenue 3M] ) * 91.2
DPO = DIVIDE ( [Payables], [Direct Costs 3M] ) * 91.2
Cash Gap (days) = [DSO] - [DPO]
```

> `91.2` = 3 × 30.4 days. In the first two months of the dataset the SQL view uses a shorter window; Power BI will give a slightly different DSO for Jan–Feb 2024 only.

## 7. Suggested report pages
1. **Executive summary:** KPI cards (Revenue, EBITDA, EBITDA %, Net Income, Cash, DSO), revenue actual vs budget, EBITDA waterfall, entity matrix.
2. **Profitability:** margin lines, cost lines vs budget (bar), net income vs budget.
3. **Liquidity:** cash/net debt, current & quick ratio, balance sheet stacked columns.
4. **Working capital:** DSO/DPO lines, DSO by entity, cash gap.

Slicers: `dim_entity[entity_name]`, `dim_date[year]`. Use *Sync slicers* so they apply to all pages.

> Note: the consolidated "Group" view is simply "no entity selected" in Power BI, whereas the SQL layer materialises it as `GRP`.
