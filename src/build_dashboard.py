"""Read the KPI views from SQLite and render the static, interactive dashboard (docs/index.html).

The page is a single HTML file + a local copy of plotly.js, so it works offline and on GitHub Pages.
"""
import json
import shutil
import sqlite3
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
TEMPLATE = Path(__file__).with_name("dashboard_template.html")

MONEY_COLS = ["revenue", "cogs", "opex", "da", "interest", "tax", "gross_profit", "ebitda", "ebit", "net_income",
              "b_revenue", "b_gross_profit", "b_ebitda", "b_net_income", "revenue_var", "ebitda_var", "net_income_var",
              "cash", "receivables", "prepaid", "fixed_assets", "payables", "accruals", "st_debt", "lt_debt", "equity",
              "total_assets", "current_assets", "current_liabilities", "working_capital", "net_debt",
              "trade_working_capital", "ttm_net_income", "ttm_ebitda"]
RATIO_COLS = ["gross_margin", "ebitda_margin", "net_margin", "current_ratio", "quick_ratio", "cash_ratio",
              "net_debt_to_ebitda", "dso", "dpo", "cash_gap_days", "roa", "roe"]
ENTITY_NAMES = {"GRP": "Group (consolidated)"}


def fmt_m(v):
    return f"€{v / 1e6:,.1f}M"


def make_insights(kpi: pd.DataFrame, pnl: pd.DataFrame) -> list[str]:
    """Plain-English findings for the default view (latest fiscal year, year-to-date) - computed, never hand-typed."""
    y = int(kpi.month.str[:4].max())
    last_m = int(kpi[kpi.month.str[:4] == str(y)].month.str[5:7].astype(int).max())
    k = kpi.assign(y=kpi.month.str[:4].astype(int), mn=kpi.month.str[5:7].astype(int))
    cur = k[(k.y == y) & (k.mn <= last_m)]
    out = []

    g = cur[cur.entity_id == "GRP"]
    rev, brev = g.revenue.sum(), g.b_revenue.sum()
    eb, beb = g.ebitda.sum(), g.b_ebitda.sum()
    out.append(f"Group revenue is {fmt_m(rev)} YTD, {abs(rev / brev - 1):.1%} {'above' if rev >= brev else 'below'} budget; "
               f"EBITDA is {fmt_m(eb)} ({eb / rev:.1%} margin), {abs(eb / beb - 1):.1%} {'above' if eb >= beb else 'below'} budget.")

    ents = cur[cur.entity_id != "GRP"].groupby("entity_id")[["revenue", "b_revenue"]].sum()
    ents["gap"] = ents.revenue / ents.b_revenue - 1
    worst, best = ents.gap.idxmin(), ents.gap.idxmax()
    out.append(f"Revenue vs budget ranges from {ents.gap[best]:+.1%} ({best}) to {ents.gap[worst]:+.1%} ({worst}); the {worst} shortfall is the main drag on the Group.")

    dso_now = k[(k.y == y) & (k.mn == last_m) & (k.entity_id != "GRP")].set_index("entity_id").dso
    dso_prev = k[(k.y == y - 1) & (k.mn == 12) & (k.entity_id != "GRP")].set_index("entity_id").dso
    chg = (dso_now - dso_prev).sort_values(ascending=False)
    e = chg.index[0]
    cash_now = k[(k.y == y) & (k.mn == last_m) & (k.entity_id == e)].cash.iloc[0]
    cash_prev = k[(k.y == y - 1) & (k.mn == 12) & (k.entity_id == e)].cash.iloc[0]
    out.append(f"{e} receivables are slowing: DSO rose from {dso_prev[e]:.0f} to {dso_now[e]:.0f} days since December, "
               f"and its cash fell {fmt_m(cash_prev)} → {fmt_m(cash_now)}.")

    p = pnl[(pnl.e != "GRP") & (pnl.y == y) & (pnl.mn <= last_m) & (pnl.c == "Opex")].groupby(["e", "a"])[["act", "bud"]].sum()
    p["over"] = p.act / p.bud - 1
    (e2, a2) = p.over.idxmax()
    out.append(f"Biggest cost overrun: {a2.lower()} in {e2} is {p.over.max():+.0%} vs budget ({fmt_m(p.act[(e2, a2)] - p.bud[(e2, a2)])} over).")
    return out


def main(con: sqlite3.Connection | None = None):
    own = con is None
    if own:
        con = sqlite3.connect(ROOT / "data" / "finance.db")

    kpi = pd.read_sql("SELECT * FROM v_kpi_monthly ORDER BY entity_id, month", con)
    ent = pd.read_sql("SELECT entity_id, entity_name FROM dim_entity", con)
    names = {**dict(zip(ent.entity_id, ent.entity_name)), **ENTITY_NAMES}

    pnl = pd.read_sql("""
        SELECT p.month, p.entity_id AS e, a.account_name AS a, a.category AS c, p.actual AS act, p.budget AS bud
        FROM fact_pnl p JOIN dim_account a USING (account_id)
        UNION ALL
        SELECT p.month, 'GRP', a.account_name, a.category, SUM(p.actual), SUM(p.budget)
        FROM fact_pnl p JOIN dim_account a USING (account_id) GROUP BY p.month, a.account_name, a.category
    """, con)
    pnl["y"], pnl["mn"] = pnl.month.str[:4].astype(int), pnl.month.str[5:7].astype(int)

    insights = make_insights(kpi, pnl)

    kpi_js = kpi.copy()
    kpi_js[MONEY_COLS] = kpi_js[MONEY_COLS].round(0)
    kpi_js[RATIO_COLS] = kpi_js[RATIO_COLS].round(4)
    kpi_js["y"], kpi_js["mn"] = kpi_js.month.str[:4].astype(int), kpi_js.month.str[5:7].astype(int)
    keep = ["month", "y", "mn"] + MONEY_COLS + RATIO_COLS
    data = {
        "kpi": {e: g[keep].astype(object).where(g[keep].notna(), None).to_dict("records") for e, g in kpi_js.groupby("entity_id")},
        "pnl": pnl.drop(columns="month").round(0).to_dict("records"),
        "entities": [{"id": i, "name": names[i]} for i in ["GRP", "FR", "DE", "UK", "TN"]],
        "years": sorted(kpi_js.y.unique().tolist()),
        "insights": insights,
    }

    DOCS.mkdir(exist_ok=True)
    (DOCS / "assets").mkdir(exist_ok=True)
    import plotly
    shutil.copy(Path(plotly.__file__).parent / "package_data" / "plotly.min.js", DOCS / "assets" / "plotly.min.js")
    html = TEMPLATE.read_text(encoding="utf-8").replace("__DATA__", json.dumps(data, separators=(",", ":")))
    (DOCS / "index.html").write_text(html, encoding="utf-8")
    print(f"   docs/index.html written ({len(html) / 1e3:,.0f} KB)")
    for line in insights:
        print("   •", line)
    if own:
        con.close()


if __name__ == "__main__":
    main()
