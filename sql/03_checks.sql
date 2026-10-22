-- Data-quality checks. Each query must return 0 rows / 0 violations.

-- 1. Balance sheet balances for every entity and month (incl. Group)
SELECT 'balance sheet balances (0 violations)' AS check_name, COUNT(*) AS violations
FROM v_kpi_monthly WHERE ABS(bs_check) > 1;

-- 2. No missing months (33 months x 5 entities incl. Group)
SELECT 'complete: 33 months x 5 entities', ABS(COUNT(*) - 165) FROM v_kpi_monthly;

-- 3. Revenue is positive everywhere
SELECT 'revenue positive everywhere', COUNT(*) FROM v_kpi_monthly WHERE revenue <= 0;

-- 4. Group = sum of entities
SELECT 'group = sum of entities', COUNT(*)
FROM v_kpi_monthly g
JOIN (SELECT month, SUM(revenue) AS r FROM v_kpi_monthly WHERE entity_id <> 'GRP' GROUP BY month) e USING (month)
WHERE g.entity_id = 'GRP' AND ABS(g.revenue - e.r) > 1;

-- 5. Cash never negative
SELECT 'cash never negative', COUNT(*) FROM v_kpi_monthly WHERE cash < 0;
