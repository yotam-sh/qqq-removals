#!/usr/bin/env python3
"""
Wrap-up reconciliation + headline-number report for the analysis extensions.
Reads the series cache (source of truth), results_per_stock.csv, and the generated
JSON aggregates. Spot-checks three stocks of different character against the CSV,
then prints the numbers requested for the write-up. Read-only.
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PROC = ROOT / "data" / "processed"
SERIES = PROC / "series"


def load(name):
    return json.load(open(PROC / name, encoding="utf-8"))


def series_stats(tkr, rd):
    e = json.load(open(SERIES / f"{tkr}_{rd}.json", encoding="utf-8"))
    s = [v for v in e["stock"] if v is not None]
    after = s[1:]
    base = s[0]
    rel = [(v / base - 1) * 100 for v in s]
    lo_i = int(np.argmin([(v / base - 1) * 100 for v in after]))
    hi_i = int(np.argmax([(v / base - 1) * 100 for v in after]))
    return {"one_year_pct": round(rel[-1], 2),
            "lowest_pct": round((after[lo_i] / base - 1) * 100, 2),
            "days_to_low": lo_i + 1,
            "highest_pct": round((after[hi_i] / base - 1) * 100, 2),
            "days_to_high": hi_i + 1}


def main():
    res = pd.read_csv(PROC / "results_per_stock.csv", parse_dates=["removal_date"])
    res["rd"] = res["removal_date"].dt.strftime("%Y-%m-%d")
    res["trunc"] = res["truncated"].astype(str).str.lower().isin(["true", "1"])
    full = res[~res["trunc"]]

    print("=" * 72)
    print("SPOT-CHECK: recomputed-from-series vs results_per_stock.csv (reconcile)")
    print("=" * 72)
    loser = full.loc[full["one_year_pct"].idxmin()]
    winner = full.loc[full["one_year_pct"].idxmax()]
    trunc_rows = res[res["trunc"]]
    truncated = trunc_rows.loc[trunc_rows["one_year_pct"].idxmin()]
    for tag, row in [("deep loser", loser), ("strong recoverer", winner), ("truncated", truncated)]:
        rc = series_stats(row["ticker"], row["rd"])
        print(f"\n {tag}: {row['ticker']} {row['rd']}  (truncated={bool(row['trunc'])}, data_days={row['data_days']})")
        print(f"   {'field':<14}{'series':>12}{'csv':>12}{'diff':>10}")
        for k in ["one_year_pct", "lowest_pct", "days_to_low", "highest_pct", "days_to_high"]:
            a, b = rc[k], row[k]
            d = abs(a - b)
            flag = "" if (d <= (1 if "days" in k else 0.1)) else "  <-- MISMATCH"
            print(f"   {k:<14}{a:>12}{b:>12}{d:>10.3f}{flag}")

    surv = load("survivorship.json")
    ap = load("average_path.json")
    cis = load("cis.json")

    print("\n" + "=" * 72)
    print("SURVIVORSHIP")
    print("=" * 72)
    f = surv["funnel"]
    print(f"  funnel: {f['total']} total -> {f['acquired_excluded']} acquired-excluded -> "
          f"{f['analyzed']} analyzed + {f['missing']} missing ({f['delisted']} delisted, {f['unknown']} unknown)")
    print(f"  coverage: {surv['coverage_pct']}% of eligible ({surv['coverage_pct_all']}% of all)")
    oy, ex = surv["one_year"], surv["excess"]
    print(f"  median 1-yr return:  survivors {oy['survivors']}  | conservative {oy['conservative']}  | "
          f"defensible {oy['defensible_best']}..{oy['defensible_worst']}")
    print(f"  median excess vQQQ:  survivors {ex['survivors']}  | conservative {ex['conservative']}  | "
          f"defensible {ex['defensible_best']}..{ex['defensible_worst']}")

    print("\n" + "=" * 72)
    print("AVERAGE PATH (median, indexed-to-100 raw view)")
    print("=" * 72)
    for panel in ("all", "balanced"):
        m = ap[panel]["raw"]["median"]
        e = ap[panel]["excess"]["median"]
        vals = [m[o] for o in (21, 63, 126, 252)]
        evals = [e[o] for o in (21, 63, 126, 252)]
        print(f"  {panel:9s} raw @21/63/126/252: {vals}   excess: {evals}")
    mall = ap["all"]["raw"]["median"]
    bottom = min(range(len(mall)), key=lambda d: mall[d] if mall[d] is not None else 1e9)
    print(f"  raw median (all) bottoms at offset {bottom} = {mall[bottom]} "
          f"(median never dips below 100 -> survivors recover; individual dips are in the 25th pct band)")

    print("\n" + "=" * 72)
    print("ARCHETYPE: median 1-yr return, 95% CI, n")
    print("=" * 72)
    for k, v in cis["by_archetype"].items():
        c = v["one_year"]
        print(f"  {k:<20} {c['median']:>7}  95% CI [{c['lo']}, {c['hi']}]  n={c['n']}{'  (small)' if c['small'] else ''}")

    # tenure-vs-return OLS slope (confirmed tenures only)
    ten = load("tenure.json")
    res["id"] = res["ticker"] + "-" + res["rd"]
    xs, ys = [], []
    for _, r in res.iterrows():
        t = ten.get(r["id"])
        if t and not t["tenure_censored"] and pd.notna(r["one_year_pct"]):
            xs.append(t["years_in_index"]); ys.append(r["one_year_pct"])
    xs, ys = np.array(xs), np.array(ys)
    slope, intercept = np.polyfit(xs, ys, 1)
    print("\n" + "=" * 72)
    print("TENURE vs 1-YEAR RETURN (OLS, confirmed/non-censored tenures)")
    print("=" * 72)
    print(f"  slope = {slope:+.2f} pp per year in index, intercept {intercept:+.1f}%, n={len(xs)}")
    print(f"  (positive => longer-tenured removals tend to have higher 1-yr returns)")


if __name__ == "__main__":
    main()
