"""Data contract for the raw export: run before every dbt build.

Each check returns PASS / WARN / FAIL with a one-line explanation. FAIL exits non-zero,
so a bad file never reaches the model layer.
"""
from pathlib import Path
import sys

import duckdb

RAW = Path(__file__).resolve().parents[1] / "data" / "raw" / "online_retail_ii.parquet"
EXPECTED = ["invoice", "stock_code", "description", "quantity", "invoice_ts", "unit_price", "customer_id", "country"]


def main() -> int:
    con = duckdb.connect()
    con.execute(f"create view r as select * from read_parquet('{RAW}')")
    q = lambda sql: con.execute(sql).fetchone()[0]
    checks = []

    def check(name, ok, detail, level="FAIL"):
        checks.append(("PASS" if ok else level, name, detail))

    cols = [c[0] for c in con.execute("describe r").fetchall()]
    check("columns present", cols == EXPECTED, f"{cols}")
    n = q("select count(*) from r")
    check("row count above floor", n > 1_000_000, f"{n:,} rows")
    check("timestamps parse", q("select count(*) from r where invoice_ts is null") == 0, "no null invoice_ts")
    lo, hi = con.execute("select min(invoice_ts), max(invoice_ts) from r").fetchone()
    check("date window", str(lo)[:10] >= "2009-12-01" and str(hi)[:10] <= "2011-12-31", f"{lo} to {hi}")
    check("invoice not null", q("select count(*) from r where invoice is null") == 0, "every line has an invoice")
    check("stock code not null", q("select count(*) from r where stock_code is null") == 0, "every line has a stock code")
    bad_cancel = q("""select count(*) from r where starts_with(invoice,'C') and quantity > 0
                      and upper(stock_code) not in ('M','D','POST','DOT','BANK CHARGES','AMAZONFEE','ADJUST','ADJUST2','C2','CRUK','PADS','S','B')""")
    check("cancellations carry negative quantity", bad_cancel == 0, f"{bad_cancel} positive-quantity cancellation lines on product codes")
    neg_price = q("select count(*) from r where unit_price < 0")
    check("no negative prices on product lines", neg_price <= 5, f"{neg_price} negative-price lines (bad-debt adjustments)", "WARN")
    pct_null_cust = q("select avg((customer_id is null)::int) from r")
    check("customer id coverage", pct_null_cust < 0.25, f"{pct_null_cust:.1%} lines without customer id", "WARN")
    fmt = q("select count(*) from r where customer_id is not null and not regexp_matches(customer_id, '^[0-9]{5}$')")
    check("customer id format", fmt == 0, f"{fmt} ids not five digits")
    dup = q("select count(*) - count(distinct (invoice, stock_code, quantity, unit_price, invoice_ts, customer_id)) from r")
    check("exact duplicate lines", dup / n < 0.01, f"{dup:,} exact duplicates ({dup/n:.2%})", "WARN")
    multi = q("select count(*) from (select customer_id from r where customer_id is not null group by 1 having count(distinct country) > 1)")
    check("one country per customer", multi < 50, f"{multi} customers with more than one country", "WARN")
    days = q("select count(distinct cast(invoice_ts as date)) from r")
    check("trading days present", days > 550, f"{days} trading days")
    gaps = q("""select max(g) from (select date_diff('day', lag(d) over (order by d), d) g
                from (select distinct cast(invoice_ts as date) d from r))""")
    check("no long gaps in trading days", gaps <= 14, f"longest gap {gaps} days", "WARN")
    zero_qty = q("select count(*) from r where quantity = 0")
    check("no zero quantities", zero_qty == 0, f"{zero_qty} zero-quantity lines")
    desc_null = q("select avg((description is null)::int) from r")
    check("description coverage", desc_null < 0.01, f"{desc_null:.2%} lines without description", "WARN")

    width = max(len(c[1]) for c in checks)
    for level, name, detail in checks:
        print(f"{level:4}  {name:<{width}}  {detail}")
    fails = sum(c[0] == "FAIL" for c in checks)
    print(f"\n{len(checks)} checks: {sum(c[0]=='PASS' for c in checks)} pass, "
          f"{sum(c[0]=='WARN' for c in checks)} warn, {fails} fail")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
