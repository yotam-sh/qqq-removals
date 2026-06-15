#!/usr/bin/env python3
"""
"Was it the stock or the market?" — classify the market regime of each removal's
post-removal window from its MATCHED QQQ series (the same series the pages embed),
and decompose the stock's return into market + stock-specific parts.

Reads the series cache (source of truth for daily prices; no refetch) + RESULTS for
reconciliation. Recomputes QQQ window return and checks it against the CSV's
qqq_same_window_pct (+/-0.1pp); stops on mismatch.

market_regime thresholds are EXPLICIT params (window return + max drawdown):
  crash       ret <= CRASH_RET and maxdd <= CRASH_DD
  bear        ret <= BEAR_RET
  flat        BEAR_RET < ret < BULL_RET
  bull        BULL_RET <= ret < STRONG_RET
  strong_bull ret >= STRONG_RET
Secondary `episode` tag (GFC/COVID/rate-shock) by first_day_out date.

Output data/processed/regime.json: per_id {market_regime, episode, qqq_window_pct,
qqq_max_drawdown}; by_regime medians/CIs/n; thresholds; display order.
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SERIES = ROOT / "data" / "processed" / "series"
RESULTS = ROOT / "data" / "processed" / "results_per_stock.csv"
OUT = ROOT / "data" / "processed" / "regime.json"

# explicit thresholds (percent)
CRASH_RET, CRASH_DD = -10.0, -25.0
BEAR_RET, BULL_RET, STRONG_RET = -10.0, 10.0, 30.0
ORDER = ["crash", "bear", "flat", "bull", "strong_bull"]
TOL = 0.1
N_BOOT = 10000
rng = np.random.default_rng(20260615)

EPISODES = [("GFC 2008", "2007-09-01", "2009-03-31"),
            ("COVID 2020", "2020-02-01", "2020-06-30"),
            ("Rate shock 2022", "2022-01-01", "2022-12-31")]


def regime(ret, maxdd):
    if ret <= CRASH_RET and maxdd <= CRASH_DD:
        return "crash"
    if ret <= BEAR_RET:
        return "bear"
    if ret < BULL_RET:
        return "flat"
    if ret < STRONG_RET:
        return "bull"
    return "strong_bull"


def episode_of(first_day_out):
    d = pd.Timestamp(first_day_out)
    for name, a, b in EPISODES:
        if pd.Timestamp(a) <= d <= pd.Timestamp(b):
            return name
    return None


def qqq_stats(qqq):
    q = [v for v in qqq if v is not None]
    if len(q) < 2:
        return None, None
    ret = (q[-1] / q[0] - 1.0) * 100.0
    peak, mdd = -1e18, 0.0
    for v in q:
        peak = max(peak, v)
        mdd = min(mdd, (v / peak - 1.0) * 100.0)
    return ret, mdd


def ci(vals):
    a = np.array([v for v in vals if v is not None and not np.isnan(v)], float)
    n = len(a)
    if n == 0:
        return {"median": None, "lo": None, "hi": None, "n": 0, "small": True}
    if n == 1:
        v = round(float(a[0]), 2)
        return {"median": v, "lo": v, "hi": v, "n": 1, "small": True}
    meds = np.median(a[rng.integers(0, n, size=(N_BOOT, n))], axis=1)
    return {"median": round(float(np.median(a)), 2),
            "lo": round(float(np.percentile(meds, 2.5)), 2),
            "hi": round(float(np.percentile(meds, 97.5)), 2),
            "n": int(n), "small": bool(n < 5)}


def main():
    res = pd.read_csv(RESULTS, parse_dates=["removal_date"])
    res["rd"] = res["removal_date"].dt.strftime("%Y-%m-%d")

    per_id, mism = {}, []
    groups = {r: {"1y": [], "ex": []} for r in ORDER}
    for _, r in res.iterrows():
        cp = SERIES / f"{r['ticker']}_{r['rd']}.json"
        if not cp.exists():
            continue
        e = json.load(open(cp, encoding="utf-8"))
        if not e.get("available"):
            continue
        ret, mdd = qqq_stats(e["qqq"])
        if ret is None:
            continue
        # reconcile QQQ window return vs CSV
        if pd.notna(r["qqq_same_window_pct"]) and abs(ret - float(r["qqq_same_window_pct"])) > TOL:
            mism.append((r["ticker"], r["rd"], round(ret, 2), float(r["qqq_same_window_pct"])))
        reg = regime(ret, mdd)
        per_id[f"{r['ticker']}-{r['rd']}"] = {
            "market_regime": reg, "episode": episode_of(r["first_day_out"]),
            "qqq_window_pct": round(ret, 2), "qqq_max_drawdown": round(mdd, 2)}
        groups[reg]["1y"].append(float(r["one_year_pct"]) if pd.notna(r["one_year_pct"]) else None)
        if pd.notna(r["excess_vs_qqq_pct"]):
            groups[reg]["ex"].append(float(r["excess_vs_qqq_pct"]))

    if mism:
        print("RECONCILIATION FAILED (QQQ window return vs CSV > 0.1pp):")
        for t, d, a, b in mism:
            print(f"   {t} {d}: regime {a} vs csv {b}")
        sys.exit(1)

    by_regime = {r: {"one_year": ci(groups[r]["1y"]), "excess": ci(groups[r]["ex"]),
                     "n": len(groups[r]["1y"])} for r in ORDER}
    out = {"per_id": per_id, "by_regime": by_regime, "order": ORDER,
           "thresholds": {"crash_ret": CRASH_RET, "crash_dd": CRASH_DD, "bear_ret": BEAR_RET,
                          "bull_ret": BULL_RET, "strong_ret": STRONG_RET}}
    OUT.write_text(json.dumps(out), encoding="utf-8")
    print(f"Wrote {OUT.name} ({len(per_id)} windows classified)")
    counts = {r: by_regime[r]["n"] for r in ORDER}
    print(f"  regime counts: {counts}")
    for r in ORDER:
        c = by_regime[r]["one_year"]
        if c["n"]:
            print(f"  {r:12s} median 1y {c['median']:>7}  95% CI [{c['lo']}, {c['hi']}]  n={c['n']}")
    print(f"  reconciliation OK ({len(per_id)} windows within {TOL}pp).")


if __name__ == "__main__":
    main()
