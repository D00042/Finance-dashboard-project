"""One command to rebuild everything:  python run_pipeline.py

1. generate synthetic data  -> data/raw/*.csv
2. load into SQLite star schema + build KPI views (sql/*.sql) -> data/finance.db
3. run data-quality checks
4. export KPI table for Power BI -> data/processed/kpi_monthly.csv
5. build the interactive dashboard -> docs/index.html
"""
import sqlite3
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))
import build_dashboard  # noqa: E402
import generate_data  # noqa: E402

DB = ROOT / "data" / "finance.db"


def run_sql(con, name):
    con.executescript((ROOT / "sql" / name).read_text(encoding="utf-8"))


def main():
    print("1/5 Generating synthetic data...")
    generate_data.main()

    print("2/5 Building SQLite model...")
    DB.unlink(missing_ok=True)
    con = sqlite3.connect(DB)
    run_sql(con, "01_schema.sql")
    for table in ["dim_entity", "dim_account", "dim_date", "fact_pnl", "fact_balance"]:
        pd.read_csv(ROOT / "data" / "raw" / f"{table}.csv").to_sql(table, con, if_exists="append", index=False)
    run_sql(con, "02_kpi_views.sql")

    print("3/5 Running data-quality checks...")
    failed = False
    for stmt in (ROOT / "sql" / "03_checks.sql").read_text(encoding="utf-8").split(";"):
        body = "\n".join(l for l in stmt.splitlines() if not l.strip().startswith("--")).strip()
        if not body:
            continue
        name, n = con.execute(body).fetchone()
        print(f"   {'OK  ' if n == 0 else 'FAIL'} {name}")
        failed |= n != 0
    if failed:
        sys.exit("Data-quality checks failed")

    print("4/5 Exporting KPI table...")
    kpi = pd.read_sql("SELECT * FROM v_kpi_monthly ORDER BY entity_id, month", con)
    kpi.to_csv(ROOT / "data" / "processed" / "kpi_monthly.csv", index=False)

    print("5/5 Building dashboard...")
    build_dashboard.main(con)
    con.close()
    print("Done -> open docs/index.html")


if __name__ == "__main__":
    main()
