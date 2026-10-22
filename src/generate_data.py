"""Generate a synthetic, fully fictional finance dataset for "Meridian Travel Group".

Output: star-schema CSVs in data/raw/
    dim_entity, dim_account, dim_date, fact_pnl (actual + budget), fact_balance

Design goals
- Realistic travel-industry seasonality (summer peak, winter trough)
- Balance sheet that balances by construction (cash is the plug)
- A few deliberate "stories" an analyst would find, so the dashboard has something to say:
    * UK: revenue shortfall + customers paying slower (DSO drifts up in 2026) -> cash squeeze
    * Germany: marketing overspend in 2026 -> EBITDA below budget
    * Tunisia: outperforming budget
    * France: stable core business
Everything is synthetic. No real company data is used.
"""
from pathlib import Path

import numpy as np
import pandas as pd

SEED = 42
START, END = "2024-01-01", "2026-09-01"  # 33 months (FY2026 is year-to-date)
OUT = Path(__file__).resolve().parents[1] / "data" / "raw"

ENTITIES = [
    # id, name, country, base monthly revenue (EUR)
    ("FR", "Meridian France", "France", 6_000_000),
    ("DE", "Meridian Germany", "Germany", 4_500_000),
    ("UK", "Meridian UK", "United Kingdom", 3_000_000),
    ("TN", "Meridian Tunisia", "Tunisia", 1_500_000),
]

# account_id, name, statement, category
ACCOUNTS = [
    (4100, "Package tours", "P&L", "Revenue"),
    (4200, "Flight sales", "P&L", "Revenue"),
    (4300, "Hotel & ancillary", "P&L", "Revenue"),
    (5100, "Direct costs", "P&L", "COGS"),
    (6100, "Personnel", "P&L", "Opex"),
    (6200, "Marketing", "P&L", "Opex"),
    (6300, "IT & systems", "P&L", "Opex"),
    (6400, "Admin & other", "P&L", "Opex"),
    (6800, "Depreciation & amortisation", "P&L", "D&A"),
    (7100, "Interest expense", "P&L", "Interest"),
    (8100, "Income tax", "P&L", "Tax"),
    (1010, "Cash", "BS", "Current assets"),
    (1100, "Trade receivables", "BS", "Current assets"),
    (1500, "Prepaid & other current assets", "BS", "Current assets"),
    (1800, "Fixed assets (net)", "BS", "Non-current assets"),
    (2100, "Trade payables", "BS", "Current liabilities"),
    (2200, "Accruals & other current liabilities", "BS", "Current liabilities"),
    (2300, "Short-term debt", "BS", "Current liabilities"),
    (2500, "Long-term debt", "BS", "Non-current liabilities"),
    (3100, "Equity", "BS", "Equity"),
]

# Travel seasonality, mean-normalised (Jan..Dec)
SEASON = np.array([0.70, 0.70, 0.85, 0.95, 1.00, 1.20, 1.50, 1.55, 1.10, 0.90, 0.70, 0.85])
SEASON = SEASON / SEASON.mean()
REV_SPLIT = {4100: 0.60, 4200: 0.25, 4300: 0.15}
TAX_RATE, INTEREST_RATE, DA_LIFE_MONTHS = 0.25, 0.055, 60

# Budget assumptions per entity
BUDGET = {
    "FR": dict(growth=0.05, cogs=0.690, mkt=0.040),
    "DE": dict(growth=0.05, cogs=0.695, mkt=0.040),
    "UK": dict(growth=0.06, cogs=0.690, mkt=0.045),
    "TN": dict(growth=0.08, cogs=0.680, mkt=0.035),
}


def actual_perf(ent: str, year: int) -> dict:
    """How reality deviates from the budget (the 'stories')."""
    perf = {
        "FR": {2024: (1.00, 0.000, 0.000), 2025: (1.01, 0.000, 0.000), 2026: (1.01, 0.000, 0.000)},
        "DE": {2024: (1.00, 0.000, 0.000), 2025: (0.99, 0.002, 0.002), 2026: (0.99, 0.006, 0.016)},
        "UK": {2024: (1.00, 0.000, 0.000), 2025: (0.97, 0.003, 0.002), 2026: (0.91, 0.008, 0.004)},
        "TN": {2024: (1.02, -0.003, 0.000), 2025: (1.06, -0.004, 0.000), 2026: (1.10, -0.005, 0.001)},
    }[ent][year]
    return dict(rev_mult=perf[0], cogs_add=perf[1], mkt_add=perf[2])


def dso_target(ent: str, t: int, date: pd.Timestamp, rng) -> float:
    base = {"FR": 40, "DE": 38, "UK": 42, "TN": 55}[ent]
    if ent == "UK" and date.year == 2026:  # receivables deteriorate through 2026
        base += (date.month) * 2.9
    return base + rng.normal(0, 1.2)


def dpo_target(ent: str, rng) -> float:
    return {"FR": 45, "DE": 42, "UK": 40, "TN": 60}[ent] + rng.normal(0, 1.5)


def build_pnl(ent, base_rev, dates, scenario, rng):
    """Return a list of P&L rows for one entity and one scenario ('budget' | 'actual')."""
    rows, ytd_ebt, ytd_tax = [], 0.0, 0.0
    fixed_assets = base_rev * 2.0
    debt_total = base_rev * 2.0
    for t, d in enumerate(dates):
        b = BUDGET[ent]
        growth = (1 + b["growth"]) ** (t / 12)
        revenue = base_rev * SEASON[d.month - 1] * growth
        cogs_pct, mkt_pct = b["cogs"], b["mkt"]
        if scenario == "actual":
            p = actual_perf(ent, d.year)
            revenue *= p["rev_mult"] * (1 + rng.normal(0, 0.012))
            cogs_pct += p["cogs_add"] + rng.normal(0, 0.003)
            mkt_pct += p["mkt_add"] + rng.normal(0, 0.002)
        # Opex: mostly fixed (not seasonal), grows ~3% a year
        fixed_growth = 1.03 ** (t / 12)
        personnel = base_rev * 0.140 * fixed_growth
        it = base_rev * 0.025 * fixed_growth
        admin = base_rev * 0.035 * fixed_growth
        marketing = revenue * mkt_pct
        if scenario == "actual":
            personnel *= 1 + rng.normal(0, 0.006)
            it *= 1 + rng.normal(0, 0.02)
            admin *= 1 + rng.normal(0, 0.02)
        cogs = revenue * cogs_pct
        da = fixed_assets / DA_LIFE_MONTHS
        capex = da * 1.10
        fixed_assets = fixed_assets + capex - da
        interest = debt_total * INTEREST_RATE / 12
        ebt = revenue - cogs - personnel - marketing - it - admin - da - interest
        if d.month == 1:
            ytd_ebt, ytd_tax = 0.0, 0.0
        ytd_ebt += ebt
        tax_ytd_target = TAX_RATE * max(ytd_ebt, 0)
        tax = tax_ytd_target - ytd_tax
        ytd_tax = tax_ytd_target
        lines = {
            4100: revenue * REV_SPLIT[4100] * (1 + (rng.normal(0, 0.01) if scenario == "actual" else 0)),
            4200: revenue * REV_SPLIT[4200],
            4300: None,  # plug so the three lines sum to total revenue
            5100: cogs, 6100: personnel, 6200: marketing, 6300: it, 6400: admin,
            6800: da, 7100: interest, 8100: tax,
        }
        lines[4300] = revenue - lines[4100] - lines[4200]
        for acc, val in lines.items():
            rows.append((d, ent, acc, val))
    return rows


def main():
    rng = np.random.default_rng(SEED)
    dates = list(pd.date_range(START, END, freq="MS"))

    pnl_rows, bs_rows = [], []
    for ent, _, _, base_rev in ENTITIES:
        bud = pd.DataFrame(build_pnl(ent, base_rev, dates, "budget", rng), columns=["month", "entity_id", "account_id", "budget"])
        act = pd.DataFrame(build_pnl(ent, base_rev, dates, "actual", rng), columns=["month", "entity_id", "account_id", "actual"])
        pnl = act.merge(bud, on=["month", "entity_id", "account_id"])
        pnl_rows.append(pnl)

        # ---- Balance sheet (actuals only) -------------------------------------------------
        piv = act.pivot(index="month", columns="account_id", values="actual")
        revenue = piv[[4100, 4200, 4300]].sum(axis=1)
        cogs = piv[5100]
        opex = piv[[6100, 6200, 6300, 6400]].sum(axis=1)
        net_income = revenue - cogs - opex - piv[6800] - piv[7100] - piv[8100]

        fixed_assets = base_rev * 2.0
        equity0 = base_rev * 3.5
        st_debt, lt_debt = base_rev * 0.5, base_rev * 1.5
        cum_ni = 0.0
        for t, d in enumerate(dates):
            da = piv.loc[d, 6800]
            fixed_assets = fixed_assets + da * 1.10 - da
            cum_ni += net_income[d]
            window = slice(max(0, t - 2), t + 1)
            avg_rev = revenue.iloc[window].mean()
            avg_cogs = cogs.iloc[window].mean()
            ar = avg_rev * dso_target(ent, t, d, rng) / 30.4
            ap = avg_cogs * dpo_target(ent, rng) / 30.4
            prepaid = revenue.iloc[t] * 0.45
            accruals = opex.iloc[t] * 0.35
            equity = equity0 + cum_ni
            # round every line to whole euros first, then let cash absorb the difference -> balances exactly
            ar, ap, prepaid, accruals, fa, equity_r, std, ltd = (round(v) for v in (ar, ap, prepaid, accruals, fixed_assets, equity, st_debt, lt_debt))
            cash = equity_r + std + ltd + ap + accruals - ar - prepaid - fa  # balancing item
            for acc, val in {1010: cash, 1100: ar, 1500: prepaid, 1800: fa, 2100: ap,
                             2200: accruals, 2300: std, 2500: ltd, 3100: equity_r}.items():
                bs_rows.append((d, ent, acc, val))

    fact_pnl = pd.concat(pnl_rows, ignore_index=True)
    fact_bs = pd.DataFrame(bs_rows, columns=["month", "entity_id", "account_id", "amount"])
    assert fact_bs.pivot_table(index=["month", "entity_id"], columns="account_id", values="amount")[1010].min() > 0, "negative cash"

    for df, cols in ((fact_pnl, ["actual", "budget"]), (fact_bs, ["amount"])):
        df[cols] = df[cols].round(0)

    OUT.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(ENTITIES, columns=["entity_id", "entity_name", "country", "base_monthly_revenue"]).drop(columns="base_monthly_revenue").assign(currency="EUR").to_csv(OUT / "dim_entity.csv", index=False)
    pd.DataFrame(ACCOUNTS, columns=["account_id", "account_name", "statement", "category"]).to_csv(OUT / "dim_account.csv", index=False)
    dd = pd.DataFrame({"month": dates})
    dd["year"], dd["quarter"], dd["month_num"] = dd.month.dt.year, dd.month.dt.quarter, dd.month.dt.month
    dd["month_name"] = dd.month.dt.strftime("%b")
    dd["period_label"] = dd.month.dt.strftime("%Y-%m")
    dd.to_csv(OUT / "dim_date.csv", index=False)
    fact_pnl.to_csv(OUT / "fact_pnl.csv", index=False, date_format="%Y-%m-%d")
    fact_bs.to_csv(OUT / "fact_balance.csv", index=False, date_format="%Y-%m-%d")
    print(f"fact_pnl: {len(fact_pnl):,} rows | fact_balance: {len(fact_bs):,} rows | months: {len(dates)}")


if __name__ == "__main__":
    main()
