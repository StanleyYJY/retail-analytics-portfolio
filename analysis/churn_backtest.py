"""Churn early warning on repeat customers, evaluated with a weekly walk-forward backtest.

Question: each Friday, which active repeat customers will place no order in the next 60 days?
Baseline: the kind of rule teams use in practice ("overdue by 2x their own order cycle", or
"no order for 90 days"). Model: logistic regression on order-cycle features. Both are compared at
the SAME list size each week, so the comparison is about ranking quality, not list length.

Leakage control: features use only orders strictly before the snapshot; the model for week t is
trained only on snapshots whose 60-day label window closed before t.
"""
from pathlib import Path

import duckdb
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, precision_recall_curve, roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parents[1]
HORIZON = 60          # days without an order that count as lapsed
ACTIVE_WINDOW = 180   # pool = repeat customers with an order in the last 180 days
FEATURES = ["log_recency", "log_gap", "overdue_ratio", "log_orders", "log_rev_180", "trend_90", "log_aov"]


def load_orders() -> pd.DataFrame:
    con = duckdb.connect(str(ROOT / "data" / "warehouse.duckdb"), read_only=True)
    df = con.execute("select customer_id, order_date, revenue from fct_orders").df()
    df["order_date"] = pd.to_datetime(df["order_date"])
    return df


def snapshot(orders: pd.DataFrame, t: pd.Timestamp) -> pd.DataFrame:
    past = orders[orders.order_date < t]
    g = past.groupby("customer_id")
    s = pd.DataFrame({
        "first": g.order_date.min(), "last": g.order_date.max(), "n": g.size(),
        "rev_180": past[past.order_date >= t - pd.Timedelta(days=ACTIVE_WINDOW)].groupby("customer_id").revenue.sum(),
        "o90": past[past.order_date >= t - pd.Timedelta(days=90)].groupby("customer_id").size(),
        "o90p": past[(past.order_date < t - pd.Timedelta(days=90)) & (past.order_date >= t - pd.Timedelta(days=180))]
                .groupby("customer_id").size(),
        "aov": g.revenue.mean(),
    }).fillna({"rev_180": 0, "o90": 0, "o90p": 0})
    s = s[(s.n >= 2) & (s["last"] >= t - pd.Timedelta(days=ACTIVE_WINDOW))].copy()
    s["recency"] = (t - s["last"]).dt.days
    s["gap"] = ((s["last"] - s["first"]).dt.days / (s.n - 1)).clip(lower=1)
    s["overdue_ratio"] = s.recency / s.gap
    s["log_recency"] = np.log1p(s.recency)
    s["log_gap"] = np.log(s.gap)
    s["log_orders"] = np.log(s.n)
    s["log_rev_180"] = np.log1p(s.rev_180.clip(lower=0))
    s["trend_90"] = (s.o90 - s.o90p) / (s.o90 + s.o90p + 1)
    s["log_aov"] = np.log1p(s.aov.clip(lower=0))
    future = orders[(orders.order_date >= t) & (orders.order_date < t + pd.Timedelta(days=HORIZON))]
    s["lapsed"] = (~s.index.isin(future.customer_id.unique())).astype(int)
    s["rule_overdue_2x"] = (s.overdue_ratio >= 2).astype(int)
    s["rule_90d"] = (s.recency >= 90).astype(int)
    s["rule_any"] = ((s.rule_overdue_2x + s.rule_90d) > 0).astype(int)
    s["snapshot"] = t
    return s.reset_index()


def main() -> None:
    orders = load_orders()
    fridays = pd.date_range("2010-06-04", "2011-09-30", freq="W-FRI")
    snaps = pd.concat([snapshot(orders, t) for t in fridays], ignore_index=True)

    rows, weekly = [], []
    for t in fridays:
        train = snaps[snaps.snapshot + pd.Timedelta(days=HORIZON) <= t]
        if train.snapshot.nunique() < 8:
            continue
        test = snaps[snaps.snapshot == t].copy()
        model = make_pipeline(StandardScaler(), LogisticRegression(max_iter=1000))
        model.fit(train[FEATURES], train.lapsed)
        test["score"] = model.predict_proba(test[FEATURES])[:, 1]
        rows.append(test)
        for rule in ["rule_overdue_2x", "rule_90d", "rule_any"]:
            k = int(test[rule].sum())
            top = test.nlargest(k, "score") if k else test.iloc[:0]
            weekly.append({"snapshot": t, "rule": rule, "k": k, "positives": int(test.lapsed.sum()),
                           "rule_tp": int((test[rule] & test.lapsed).sum()), "model_tp": int(top.lapsed.sum())})
    scored = pd.concat(rows, ignore_index=True)
    w = pd.DataFrame(weekly)

    rng = np.random.default_rng(7)
    weeks = w.snapshot.unique()
    out = []
    for rule, sub in w.groupby("rule"):
        k, pos, rtp, mtp = sub.k.sum(), sub.positives.sum(), sub.rule_tp.sum(), sub.model_tp.sum()
        diffs = []
        for _ in range(2000):
            b = sub.set_index("snapshot").loc[rng.choice(weeks, len(weeks))]
            diffs.append((b.model_tp.sum() - b.rule_tp.sum()) / b.positives.sum())
        lo, hi = np.percentile(diffs, [5, 95])
        out.append({"rule": rule, "weekly_list": k / len(sub), "rule_precision": rtp / k, "rule_recall": rtp / pos,
                    "model_precision": mtp / k, "model_recall": mtp / pos, "recall_gain_90ci": f"{lo*100:+.1f} to {hi*100:+.1f} pts"})
    res = pd.DataFrame(out).set_index("rule").loc[["rule_overdue_2x", "rule_90d", "rule_any"]]

    auc = roc_auc_score(scored.lapsed, scored.score)
    ap = average_precision_score(scored.lapsed, scored.score)
    coef = pd.Series(make_pipeline(StandardScaler(), LogisticRegression(max_iter=1000))
                     .fit(snaps[snaps.snapshot + pd.Timedelta(days=HORIZON) <= fridays[-1]][FEATURES],
                          snaps[snaps.snapshot + pd.Timedelta(days=HORIZON) <= fridays[-1]].lapsed)[-1].coef_[0],
                     index=FEATURES).sort_values(key=abs, ascending=False)

    p, r, _ = precision_recall_curve(scored.lapsed, scored.score)
    fig, ax = plt.subplots(figsize=(6, 4.2))
    ax.plot(r, p, label=f"model (AP {ap:.2f})")
    for rule, m in zip(res.index, ["o", "s", "^"]):
        ax.scatter(res.loc[rule, "rule_recall"], res.loc[rule, "rule_precision"], marker=m, label=rule.replace("rule_", "rule: "))
    ax.axhline(scored.lapsed.mean(), ls=":", c="grey", label=f"base rate {scored.lapsed.mean():.0%}")
    ax.set_xlabel("recall"); ax.set_ylabel("precision"); ax.set_title("Churn early warning, walk-forward backtest")
    ax.legend(fontsize=8); fig.tight_layout(); fig.savefig(ROOT / "results" / "figures" / "churn_pr_curve.png", dpi=150)

    fmt = lambda x: f"{x:.0%}" if isinstance(x, float) and x <= 1 else (f"{x:.1f}" if isinstance(x, float) else x)
    md = [
        "# Churn early warning: walk-forward backtest\n",
        f"- Snapshots: {scored.snapshot.nunique()} weekly test Fridays, {scored.snapshot.min():%Y-%m-%d} to {scored.snapshot.max():%Y-%m-%d}",
        f"- Customer-weeks scored: {len(scored):,}; customers: {scored.customer_id.nunique():,}; base lapse rate: {scored.lapsed.mean():.0%}",
        f"- Label: no order in the next {HORIZON} days. Pool: repeat customers with an order in the last {ACTIVE_WINDOW} days.",
        f"- Ranking quality: AUC {auc:.2f}, average precision {ap:.2f} (random = {scored.lapsed.mean():.2f}).\n",
        "## Same list size as each rule\n",
        "| Rule | Avg weekly list | Rule precision | Rule recall | Model precision | Model recall | Recall gain, 90% CI (week bootstrap) |",
        "|---|---|---|---|---|---|---|",
    ]
    for rule, row in res.iterrows():
        md.append(f"| {rule.replace('rule_', '')} | {row.weekly_list:.0f} | {row.rule_precision:.0%} | {row.rule_recall:.0%} | "
                  f"{row.model_precision:.0%} | {row.model_recall:.0%} | {row.recall_gain_90ci} |")
    md += ["\n## What the model leans on (standardized coefficients, final fit)\n", "| Feature | Coefficient |", "|---|---|"]
    md += [f"| {f} | {c:+.2f} |" for f, c in coef.items()]
    md.append("\n![PR curve](figures/churn_pr_curve.png)\n")
    (ROOT / "results" / "churn_backtest.md").write_text("\n".join(md))
    print("\n".join(md))


if __name__ == "__main__":
    main()
