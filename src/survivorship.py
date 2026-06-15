#!/usr/bin/env python3
"""
Quantify survivorship bias: recompute the macro medians (1-year return and
excess-vs-QQQ) under three scenarios and write survivorship.json for the dashboard
coverage panel.

Pools:
  Survivors only      the 126 analyzed names (current, optimistic baseline).
  Conservative floor  + every DELISTED name entered at -100% (a real, omitted loss).
  Most-defensible     + delisted at -100%, + ACQUIRED frozen at the market return over
                      its own window (=> ~0% idiosyncratic / 0 excess), and UNKNOWN
                      carried as a band: best-case (treated like acquired) to
                      worst-case (treated like delisted).

For a synthetic name we never invent a stock path. We DO use the real QQQ return
over that name's identical 252-day window (from the cached _qqq.json) so:
  - acquired raw return ~= QQQ window return (idiosyncratic 0), excess = 0
  - delisted raw return  = -100, excess = -100 - QQQ_window
Coverage and a funnel (total -> acquired-excluded -> eligible -> analyzed/missing)
are included for the banner.

Inputs:  data/processed/universe.csv, results_per_stock.csv, series/_qqq.json
Output:  data/processed/survivorship.json
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
UNIVERSE = ROOT / "data" / "processed" / "universe.csv"
RESULTS = ROOT / "data" / "processed" / "results_per_stock.csv"
QQQ = ROOT / "data" / "processed" / "series" / "_qqq.json"
OUT = ROOT / "data" / "processed" / "survivorship.json"

WINDOW = 252


def load_qqq():
    d = json.load(open(QQQ, encoding="utf-8"))
    s = pd.Series(d["close"], index=pd.to_datetime(d["dates"])).sort_index()
    return s


def qqq_window_return(qqq, removal_date):
    """Real QQQ % over the same first-252-trading-day window. None if not covered."""
    rd = pd.Timestamp(removal_date)
    win = qqq[qqq.index >= rd]
    if len(win) < 2:
        return None
    win = win.iloc[:WINDOW + 1]
    return (float(win.iloc[-1]) / float(win.iloc[0]) - 1.0) * 100.0


def med(a):
    a = [x for x in a if x is not None and not (isinstance(x, float) and np.isnan(x))]
    return round(float(np.median(a)), 2) if a else None


def main():
    uni = pd.read_csv(UNIVERSE)
    res = pd.read_csv(RESULTS)
    qqq = load_qqq()

    # survivor pools (the 126 analyzed)
    surv_1y = res["one_year_pct"].dropna().tolist()
    surv_ex = res["excess_vs_qqq_pct"].dropna().tolist()

    # synthetic contributions per fate, using the real QQQ window
    nonan = uni[uni["analyzed"] == "no"].copy()
    add = {"delisted": {"1y": [], "ex": []},
           "acquired": {"1y": [], "ex": []},
           "unknown": {"1y": [], "ex": []}}
    no_qqq = []
    for _, r in nonan.iterrows():
        qw = qqq_window_return(qqq, r["removal_date"])
        fate = r["fate"]
        if fate == "delisted":
            add[fate]["1y"].append(-100.0)
            add[fate]["ex"].append(None if qw is None else (-100.0 - qw))
        else:  # acquired or unknown: market-neutral (idiosyncratic 0)
            if qw is None:
                no_qqq.append((r["ticker"], r["removal_date"], fate))
                continue
            add[fate]["1y"].append(qw)      # raw ~ market
            add[fate]["ex"].append(0.0)     # excess ~ 0

    # also need delisted excess fallback if qqq missing: keep -100 raw, drop excess
    n_del = len(add["delisted"]["1y"])
    n_acq = len(add["acquired"]["1y"])
    n_unk = len(add["unknown"]["1y"])

    # scenarios -------------------------------------------------------------
    one_year = {
        "survivors": med(surv_1y),
        "conservative": med(surv_1y + add["delisted"]["1y"]),
        "defensible_best": med(surv_1y + add["delisted"]["1y"] + add["acquired"]["1y"] + add["unknown"]["1y"]),
        "defensible_worst": med(surv_1y + add["delisted"]["1y"] + add["acquired"]["1y"]
                                 + [-100.0] * n_unk),
    }
    excess = {
        "survivors": med(surv_ex),
        "conservative": med(surv_ex + add["delisted"]["ex"]),
        "defensible_best": med(surv_ex + add["delisted"]["ex"] + add["acquired"]["ex"] + add["unknown"]["ex"]),
        "defensible_worst": med(surv_ex + add["delisted"]["ex"] + add["acquired"]["ex"]
                                 + [(-100.0 - qqq_window_return(qqq, r["removal_date"]))
                                    for _, r in nonan[nonan["fate"] == "unknown"].iterrows()
                                    if qqq_window_return(qqq, r["removal_date"]) is not None]),
    }

    total = len(uni)
    acquired_excluded = n_acq           # legitimately exited via M&A, not a loss
    missing = n_del + n_unk             # the survivorship gap (loss + unresolved)
    analyzed = int((uni["analyzed"] == "yes").sum())
    eligible = analyzed + missing
    coverage = round(analyzed / eligible * 100, 1) if eligible else None

    out = {
        "funnel": {"total": total, "acquired_excluded": acquired_excluded,
                   "eligible": eligible, "analyzed": analyzed, "missing": missing,
                   "delisted": n_del, "unknown": n_unk, "acquired": n_acq},
        "coverage_pct": coverage,                       # analyzed / (analyzed+missing)
        "coverage_pct_all": round(analyzed / total * 100, 1),
        "one_year": one_year,
        "excess": excess,
        "spread": {
            "one_year": [one_year["defensible_worst"], one_year["survivors"]],
            "excess": [excess["defensible_worst"], excess["survivors"]],
        },
        "anchor": "defensible_best",
    }
    OUT.write_text(json.dumps(out), encoding="utf-8")
    print(f"Wrote {OUT.name}")
    print(f"  funnel: {out['funnel']}")
    print(f"  coverage (analyzed/eligible): {coverage}%   (of all removals: {out['coverage_pct_all']}%)")
    print(f"  1-yr median   survivors={one_year['survivors']}  conservative={one_year['conservative']}"
          f"  defensible={one_year['defensible_best']}..{one_year['defensible_worst']}")
    print(f"  excess median survivors={excess['survivors']}  conservative={excess['conservative']}"
          f"  defensible={excess['defensible_best']}..{excess['defensible_worst']}")
    print(f"  bias range on 1-yr headline: {one_year['survivors']}  ->  "
          f"{one_year['defensible_worst']} (spread {round(one_year['survivors']-one_year['defensible_worst'],1)} pp)")
    if no_qqq:
        print(f"  NOTE: {len(no_qqq)} non-analyzed names had no QQQ window coverage and were "
              f"omitted from acquired/unknown pools: {[t for t,_,_ in no_qqq]}")


if __name__ == "__main__":
    main()
