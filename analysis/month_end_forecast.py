"""Month-end revenue forecast from inside the month, compared with simple baselines.

Standing on day 7, 14 or 21 of a month, using only orders up to that day, estimate the month's
total revenue. Methods:
  run_rate      month-to-date x (days in month / days elapsed)
  trailing_28   month-to-date + (last 28 days' daily revenue) x days remaining
  account_cycle month-to-date + expected orders from repeat customers who are due before month end
                (from each customer's own order cycle and average order value, scaled by a hit rate
                learned on earlier months) + a trailing baseline for customers with no history
Evaluation months: 2010-03 to 2011-11 (December 2011 is partial).
"""
from pathlib import Path

import duckdb
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CUTOFFS = [7, 14, 21]


def load():
    con = duckdb.connect(str(ROOT / "data" / "warehouse.duckdb"), read_only=True)
    o = con.execute("select customer_id, order_date, revenue from fct_orders").df()
    o["order_date"] = pd.to_datetime(o["order_date"])
    return o


def cycle_expectation(orders, cutoff, month_end):
    """Expected remaining orders/revenue from repeat customers due before month end."""
    past = orders[orders.order_date <= cutoff]
    g = past.groupby("customer_id")
    c = pd.DataFrame({"first": g.order_date.min(), "last": g.order_date.max(), "n": g.size(), "aov": g.revenue.mean()})
    c = c[(c.n >= 2) & (c["last"] >= cutoff - pd.Timedelta(days=365))]
    c["gap"] = ((c["last"] - c["first"]).dt.days / (c.n - 1)).clip(lower=7)
    nxt = c["last"] + pd.to_timedelta(c.gap, unit="D")
    start = nxt.where(nxt > cutoff, cutoff + pd.Timedelta(days=1))
    remaining = (month_end - start).dt.days.clip(lower=-1)
    due = remaining >= 0
    exp_orders = np.where(due, 1 + np.floor(remaining / c.gap), 0)
    return float((exp_orders * c.aov).sum()), set(c.index)


def main():
    orders = load()
    daily = orders.groupby("order_date").revenue.sum()
    months = pd.date_range("2010-03-01", "2011-11-01", freq="MS")
    rows = []
    for m in months:
        month_end = m + pd.offsets.MonthEnd(0)
        actual = daily[(daily.index >= m) & (daily.index <= month_end)].sum()
        dim = month_end.day
        for d in CUTOFFS:
            cutoff = m + pd.Timedelta(days=d - 1)
            mtd = daily[(daily.index >= m) & (daily.index <= cutoff)].sum()
            last28 = daily[(daily.index > cutoff - pd.Timedelta(days=28)) & (daily.index <= cutoff)].sum() / 28
            exp_rev, pool = cycle_expectation(orders, cutoff, month_end)
            rest = orders[(orders.order_date > cutoff) & (orders.order_date <= month_end)]
            rows.append({"month": m, "cutoff": d, "actual": actual, "mtd": mtd,
                         "run_rate": mtd * dim / d, "trailing_28": mtd + last28 * (dim - d),
                         "exp_rev": exp_rev,
                         "realized_pool": rest[rest.customer_id.isin(pool)].revenue.sum(),
                         "realized_other": rest[~rest.customer_id.isin(pool)].revenue.sum(),
                         "days_left": dim - d})
    df = pd.DataFrame(rows).sort_values(["cutoff", "month"])
    # walk-forward calibration: hit rate and non-pool baseline learned only from earlier months
    preds = []
    for d, sub in df.groupby("cutoff"):
        sub = sub.reset_index(drop=True)
        for i, r in sub.iterrows():
            hist = sub.iloc[max(0, i - 6):i]
            hit = (hist.realized_pool.sum() / hist.exp_rev.sum()) if len(hist) >= 2 and hist.exp_rev.sum() > 0 else 0.6
            other_rate = (hist.realized_other / hist.days_left).mean() if len(hist) >= 2 else 0.0
            preds.append(r.mtd + hit * r.exp_rev + other_rate * r.days_left)
        df.loc[df.cutoff == d, "account_cycle"] = preds[-len(sub):]
        pace = []
        for i, r in sub.iterrows():
            hist = sub.iloc[max(0, i - 6):i]
            share = (hist.mtd / hist.actual).median() if len(hist) >= 2 else r.cutoff / (r.cutoff + r.days_left)
            pace.append(r.mtd / share)
        df.loc[df.cutoff == d, "pace_curve"] = pace
    df = df[df.month >= "2010-05-01"]  # need at least two prior months for calibration
    df["blend"] = (df.pace_curve + df.account_cycle) / 2
    methods = ["run_rate", "trailing_28", "pace_curve", "account_cycle", "blend"]
    for mth in methods:
        df[f"bias_{mth}"] = (df[mth] - df.actual) / df.actual
    for mth in methods:
        df[f"ape_{mth}"] = (df[mth] - df.actual).abs() / df.actual

    summ = df.groupby("cutoff")[[f"ape_{m}" for m in methods]].median()
    bias = df.groupby("cutoff")[[f"bias_{m}" for m in methods]].median()
    best = min(["pace_curve", "account_cycle", "blend"], key=lambda m: summ[f"ape_{m}"].mean())
    wins = df.groupby("cutoff").apply(lambda s: (s[f"ape_{best}"] < s.ape_run_rate).mean(), include_groups=False)

    fig, ax = plt.subplots(figsize=(6, 4))
    for mth in methods:
        ax.plot(CUTOFFS, summ[f"ape_{mth}"] * 100, marker="o", label=mth)
    ax.set_xlabel("day of month at forecast"); ax.set_ylabel("median absolute % error"); ax.set_xticks(CUTOFFS)
    ax.set_title("Month-end revenue forecast error"); ax.legend(fontsize=8); fig.tight_layout()
    fig.savefig(ROOT / "results" / "figures" / "month_end_forecast_error.png", dpi=150)

    names = {"run_rate": "Run rate", "trailing_28": "Trailing 28 days", "pace_curve": "Pace curve",
             "account_cycle": "Account cycle", "blend": "Blend (pace + cycle)"}
    md = ["# Month-end revenue forecast\n",
          f"- Evaluation months: {df.month.min():%Y-%m} to {df.month.max():%Y-%m} ({df.month.nunique()} months), three forecast days each.",
          "- Error = |forecast − actual| / actual. Every learned parameter (pace share, hit rate, new-customer baseline) uses only earlier months.\n",
          "## Median absolute percentage error\n",
          "| Forecast day | " + " | ".join(names[m] for m in methods) + " |",
          "|---|" + "---|" * len(methods)]
    for d in CUTOFFS:
        md.append(f"| {d} | " + " | ".join(f"{summ.loc[d, f'ape_{m}']:.1%}" for m in methods) + " |")
    md += ["\n## Median bias (forecast ÷ actual − 1; negative = under-forecast)\n",
           "| Forecast day | " + " | ".join(names[m] for m in methods) + " |",
           "|---|" + "---|" * len(methods)]
    for d in CUTOFFS:
        md.append(f"| {d} | " + " | ".join(f"{bias.loc[d, f'bias_{m}']:+.1%}" for m in methods) + " |")
    md.append(f"\nBest learned method: **{names[best]}**, which beats run rate in "
              + ", ".join(f"{wins.loc[d]:.0%} of months on day {d}" for d in CUTOFFS) + ".")
    md.append("\nAbout 19 months per forecast day, so read differences as direction, not as a significance claim.\n")
    md.append("![Forecast error](figures/month_end_forecast_error.png)\n")
    (ROOT / "results" / "month_end_forecast.md").write_text("\n".join(md))
    print("\n".join(md))


if __name__ == "__main__":
    main()
