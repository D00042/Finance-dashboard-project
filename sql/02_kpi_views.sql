-- KPI layer. Every number on the dashboard comes from these views.
-- Flow: fact tables -> v_pnl_entity_month / v_bs_entity_month -> v_base (adds Group) -> v_kpi_monthly

DROP VIEW IF EXISTS v_kpi_monthly;
DROP VIEW IF EXISTS v_base;
DROP VIEW IF EXISTS v_entity_month;
DROP VIEW IF EXISTS v_bs_entity_month;
DROP VIEW IF EXISTS v_pnl_entity_month;

-- 1) P&L pivoted by category (actual and budget side by side)
CREATE VIEW v_pnl_entity_month AS
SELECT
    p.month, p.entity_id,
    SUM(CASE WHEN a.category = 'Revenue'  THEN p.actual END) AS revenue,
    SUM(CASE WHEN a.category = 'COGS'     THEN p.actual END) AS cogs,
    SUM(CASE WHEN a.category = 'Opex'     THEN p.actual END) AS opex,
    SUM(CASE WHEN a.category = 'D&A'      THEN p.actual END) AS da,
    SUM(CASE WHEN a.category = 'Interest' THEN p.actual END) AS interest,
    SUM(CASE WHEN a.category = 'Tax'      THEN p.actual END) AS tax,
    SUM(CASE WHEN a.category = 'Revenue'  THEN p.budget END) AS b_revenue,
    SUM(CASE WHEN a.category = 'COGS'     THEN p.budget END) AS b_cogs,
    SUM(CASE WHEN a.category = 'Opex'     THEN p.budget END) AS b_opex,
    SUM(CASE WHEN a.category = 'D&A'      THEN p.budget END) AS b_da,
    SUM(CASE WHEN a.category = 'Interest' THEN p.budget END) AS b_interest,
    SUM(CASE WHEN a.category = 'Tax'      THEN p.budget END) AS b_tax
FROM fact_pnl p
JOIN dim_account a USING (account_id)
GROUP BY p.month, p.entity_id;

-- 2) Balance sheet pivoted by line
CREATE VIEW v_bs_entity_month AS
SELECT
    month, entity_id,
    SUM(CASE WHEN account_id = 1010 THEN amount END) AS cash,
    SUM(CASE WHEN account_id = 1100 THEN amount END) AS receivables,
    SUM(CASE WHEN account_id = 1500 THEN amount END) AS prepaid,
    SUM(CASE WHEN account_id = 1800 THEN amount END) AS fixed_assets,
    SUM(CASE WHEN account_id = 2100 THEN amount END) AS payables,
    SUM(CASE WHEN account_id = 2200 THEN amount END) AS accruals,
    SUM(CASE WHEN account_id = 2300 THEN amount END) AS st_debt,
    SUM(CASE WHEN account_id = 2500 THEN amount END) AS lt_debt,
    SUM(CASE WHEN account_id = 3100 THEN amount END) AS equity
FROM fact_balance
GROUP BY month, entity_id;

CREATE VIEW v_entity_month AS
SELECT * FROM v_pnl_entity_month JOIN v_bs_entity_month USING (month, entity_id);

-- 3) Entities + consolidated Group ('GRP') in one table
CREATE VIEW v_base AS
SELECT * FROM v_entity_month
UNION ALL
SELECT
    month, 'GRP' AS entity_id,
    SUM(revenue), SUM(cogs), SUM(opex), SUM(da), SUM(interest), SUM(tax),
    SUM(b_revenue), SUM(b_cogs), SUM(b_opex), SUM(b_da), SUM(b_interest), SUM(b_tax),
    SUM(cash), SUM(receivables), SUM(prepaid), SUM(fixed_assets),
    SUM(payables), SUM(accruals), SUM(st_debt), SUM(lt_debt), SUM(equity)
FROM v_entity_month
GROUP BY month;

-- 4) KPI layer (profitability, budget variance, liquidity, leverage, working capital, returns)
CREATE VIEW v_kpi_monthly AS
WITH calc AS (
    SELECT
        b.*,
        revenue - cogs                                                   AS gross_profit,
        revenue - cogs - opex                                            AS ebitda,
        revenue - cogs - opex - da                                       AS ebit,
        revenue - cogs - opex - da - interest - tax                      AS net_income,
        b_revenue - b_cogs                                               AS b_gross_profit,
        b_revenue - b_cogs - b_opex                                      AS b_ebitda,
        b_revenue - b_cogs - b_opex - b_da - b_interest - b_tax          AS b_net_income,
        cash + receivables + prepaid                                     AS current_assets,
        cash + receivables + prepaid + fixed_assets                      AS total_assets,
        payables + accruals + st_debt                                    AS current_liabilities,
        payables + accruals + st_debt + lt_debt                          AS total_liabilities
    FROM v_base b
),
win AS (
    SELECT
        c.*,
        SUM(revenue) OVER w3 AS rev_3m,
        SUM(cogs)    OVER w3 AS cogs_3m,
        COUNT(*)     OVER w3 AS n_3m,
        SUM(net_income) OVER w12 AS ttm_net_income,
        SUM(ebitda)     OVER w12 AS ttm_ebitda,
        COUNT(*)        OVER w12 AS n_12m
    FROM calc c
    WINDOW w3  AS (PARTITION BY entity_id ORDER BY month ROWS BETWEEN 2  PRECEDING AND CURRENT ROW),
           w12 AS (PARTITION BY entity_id ORDER BY month ROWS BETWEEN 11 PRECEDING AND CURRENT ROW)
)
SELECT
    month, entity_id,
    -- P&L
    revenue, cogs, opex, da, interest, tax,
    gross_profit, ebitda, ebit, net_income,
    gross_profit * 1.0 / revenue AS gross_margin,
    ebitda       * 1.0 / revenue AS ebitda_margin,
    net_income   * 1.0 / revenue AS net_margin,
    -- Budget & variance (favourable = positive)
    b_revenue, b_gross_profit, b_ebitda, b_net_income,
    revenue - b_revenue          AS revenue_var,
    ebitda  - b_ebitda           AS ebitda_var,
    net_income - b_net_income    AS net_income_var,
    -- Balance sheet
    cash, receivables, prepaid, fixed_assets, payables, accruals, st_debt, lt_debt, equity,
    total_assets, current_assets, current_liabilities, total_liabilities,
    ROUND(total_assets - total_liabilities - equity, 2) AS bs_check,          -- must be 0
    -- Liquidity & leverage
    current_assets - current_liabilities                    AS working_capital,
    current_assets * 1.0 / current_liabilities              AS current_ratio,
    (cash + receivables) * 1.0 / current_liabilities        AS quick_ratio,
    cash * 1.0 / current_liabilities                        AS cash_ratio,
    st_debt + lt_debt - cash                                AS net_debt,
    CASE WHEN n_12m = 12 THEN (st_debt + lt_debt - cash) * 1.0 / ttm_ebitda END AS net_debt_to_ebitda,
    -- Working-capital cycle (3-month rolling basis smooths travel seasonality)
    receivables * 1.0 / rev_3m  * 30.4 * n_3m               AS dso,
    payables    * 1.0 / cogs_3m * 30.4 * n_3m               AS dpo,
    receivables * 1.0 / rev_3m  * 30.4 * n_3m
      - payables * 1.0 / cogs_3m * 30.4 * n_3m              AS cash_gap_days,
    receivables - payables                                  AS trade_working_capital,
    -- Returns (trailing-12-month net income / period-end balance)
    CASE WHEN n_12m = 12 THEN ttm_net_income * 1.0 / total_assets END AS roa,
    CASE WHEN n_12m = 12 THEN ttm_net_income * 1.0 / equity END       AS roe,
    ttm_net_income, ttm_ebitda
FROM win;
