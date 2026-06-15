#!/usr/bin/env python3
"""
Bootstrap 95% confidence intervals for every median the dashboard reports, so small
subgroups aren't over-read. For each median we draw 10,000 numpy resamples with
replacement and take the 2.5th / 97.5th percentiles. (Done offline; never in browser.)

Covered medians:
  overall   : 1-year return & excess-vs-QQQ (full-year rows), trough depth & days-to-low (all rows)
  by_year   : median 1-year return per removal year  (matches the byYear chart)
  by_archetype : median 1-year return & excess per tenure archetype (matches the new bar)
  survivorship : each scenario pool from survivorship.py (survivors / conservative / defensible band)

Output: data/processed/cis.json   (small; embedded). Buckets with n < 5 carry "small": true.
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import survivorship as SV  # reuse load_qqq / qqq_window_return (single source of truth)

RESULTS = ROOT / "data" / "processed" / "results_per_stock.csv"
UNIVERSE = ROOT / "data" / "processed" / "universe.csv"
TENURE = ROOT / "data" / "processed" / "tenure.json"
OUT = ROOT / "data" / "processed" / "cis.json"

N_BOOT = 10000
SMALL_N = 5
rng = np.random.default_rng(20260613)


def ci(values):
    """median + 95% bootstrap CI for a list of numbers."""
    a = np.array([v for v in values if v is not None and not (isinstance(v, float) and np.isnan(v))], float)
    n = len(a)
    if n == 0:
        return {"median": None, "lo": None, "hi": None, "n": 0, "small": True}
    if n == 1:
        v = round(float(a[0]), 2)
        return {"median": v, "lo": v, "hi": v, "n": 1, "small": True}
    idx = rng.integers(0, n, size=(N_BOOT, n))
    meds = np.median(a[idx], axis=1)
    return {"median": round(float(np.median(a)), 2),
            "lo": round(float(np.percentile(meds, 2.5)), 2),
            "hi": round(float(np.percentile(meds, 97.5)), 2),
            "n": int(n), "small": bool(n < SMALL_N)}


def main():
    res = pd.read_csv(RESULTS, parse_dates=["removal_date"])
    res["truncated_b"] = res["truncated"].astype(str).str.lower().isin(["true", "1"])
    full = res[~res["truncated_b"]]
    res["year"] = res["removal_date"].dt.year
    res["id"] = res["ticker"] + "-" + res["removal_date"].dt.strftime("%Y-%m-%d")

    out = {"overall": {}, "by_year": {}, "by_archetype": {}, "survivorship": {}}

    # overall (match dashboard card definitions)
    out["overall"]["one_year"] = ci(full["one_year_pct"].tolist())
    out["overall"]["excess"] = ci(full["excess_vs_qqq_pct"].tolist())
    out["overall"]["trough"] = ci(res["lowest_pct"].tolist())
    out["overall"]["days_to_low"] = ci(res["days_to_low"].tolist())

    # by removal year (median 1-year return over all rows in the year; matches byYear)
    for y, g in res.groupby("year"):
        out["by_year"][str(int(y))] = ci(g["one_year_pct"].tolist())

    # by archetype (needs tenure)
    ten = json.load(open(TENURE, encoding="utf-8"))
    res["archetype"] = res["id"].map(lambda k: ten.get(k, {}).get("archetype"))
    for arch, g in res.groupby("archetype"):
        out["by_archetype"][arch] = {"one_year": ci(g["one_year_pct"].tolist()),
                                     "excess": ci(g["excess_vs_qqq_pct"].tolist())}

    # survivorship scenario pools (rebuild exactly as survivorship.py)
    uni = pd.read_csv(UNIVERSE)
    qqq = SV.load_qqq()
    nonan = uni[uni["analyzed"] == "no"]
    del_1y, acq_1y, unk_1y = [], [], []
    del_ex, acq_ex, unk_ex, unk_ex_worst = [], [], [], []
    for _, r in nonan.iterrows():
        qw = SV.qqq_window_return(qqq, r["removal_date"])
        if r["fate"] == "delisted":
            del_1y.append(-100.0)
            if qw is not None:
                del_ex.append(-100.0 - qw)
        elif qw is not None:
            if r["fate"] == "acquired":
                acq_1y.append(qw); acq_ex.append(0.0)
            else:  # unknown
                unk_1y.append(qw); unk_ex.append(0.0); unk_ex_worst.append(-100.0 - qw)
    surv_1y = res["one_year_pct"].dropna().tolist()
    surv_ex = res["excess_vs_qqq_pct"].dropna().tolist()
    out["survivorship"]["one_year"] = {
        "survivors": ci(surv_1y),
        "conservative": ci(surv_1y + del_1y),
        "defensible_best": ci(surv_1y + del_1y + acq_1y + unk_1y),
        "defensible_worst": ci(surv_1y + del_1y + acq_1y + [-100.0] * len(unk_1y)),
    }
    out["survivorship"]["excess"] = {
        "survivors": ci(surv_ex),
        "conservative": ci(surv_ex + del_ex),
        "defensible_best": ci(surv_ex + del_ex + acq_ex + unk_ex),
        "defensible_worst": ci(surv_ex + del_ex + acq_ex + unk_ex_worst),
    }

    OUT.write_text(json.dumps(out), encoding="utf-8")
    print(f"Wrote {OUT.name} ({N_BOOT} resamples each).")
    o = out["overall"]["one_year"]
    print(f"  overall 1-yr median {o['median']}  95% CI [{o['lo']}, {o['hi']}]  n={o['n']}")
    print("  by archetype (1-yr median [CI] n):")
    for a, v in out["by_archetype"].items():
        c = v["one_year"]
        print(f"     {a:20s} {c['median']:>6}  [{c['lo']}, {c['hi']}]  n={c['n']}{'  (small)' if c['small'] else ''}")
    small_years = [y for y, v in out["by_year"].items() if v["small"]]
    print(f"  small-n removal years (<{SMALL_N}): {small_years}")


if __name__ == "__main__":
    main()
