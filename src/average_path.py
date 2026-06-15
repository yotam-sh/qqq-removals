#!/usr/bin/env python3
"""
Build the "average path" aggregates: what the typical removed stock does over its
first 252 trading days out of the index, aligned on trading-day OFFSET (not date).

Reads ONLY the daily series already embedded in the study (the series/ cache that
also backs stocks.html) -- never refetches. For each analyzed stock it indexes the
stock and its matched QQQ to 100 at offset 0 (first day out), then at each offset d
computes, across all stocks that still have data at d, the median / 25th / 75th
percentiles and the count n(d), for:
  - raw   : stock indexed to 100
  - excess: stock_idx - qqq_idx  (percentage points vs QQQ; 0 = matched the market)

Two panels are emitted to guard the shrinking-n problem on the right side:
  - all      : every stock with data at offset d (survivor-leaning late)
  - balanced : only stocks with a full 252-day window (truncated == false)

A reconciliation gate recomputes one_year_pct from the series and checks it against
results_per_stock.csv within +/-0.1 pp; on any mismatch it prints and exits non-zero
rather than shipping inconsistent numbers.

Output: data/processed/average_path.json  (a few hundred points; safe to embed).
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SERIES_DIR = ROOT / "data" / "processed" / "series"
RESULTS = ROOT / "data" / "processed" / "results_per_stock.csv"
OUT = ROOT / "data" / "processed" / "average_path.json"

MAXOFF = 252
TOL = 0.1  # percentage points


def load_series():
    """Yield (ticker, removal_date, dates, stock[], qqq[], truncated) for every
    available cached series."""
    res = pd.read_csv(RESULTS, parse_dates=["removal_date"])
    res["rd"] = res["removal_date"].dt.strftime("%Y-%m-%d")
    want = {(r["ticker"], r["rd"]): r for _, r in res.iterrows()}
    out = []
    for cp in sorted(SERIES_DIR.glob("*.json")):
        if cp.name.startswith("_"):
            continue
        e = json.load(open(cp, encoding="utf-8"))
        if not e.get("available"):
            continue
        key = (e["ticker"], e["removal_date"])
        if key not in want:
            continue
        out.append((e["ticker"], e["removal_date"], e["dates"], e["stock"],
                    e["qqq"], bool(e.get("truncated")), want[key]))
    return out


def reconcile(series):
    """Recompute one_year_pct from the series and check vs the CSV."""
    bad = []
    for tkr, rd, dates, stock, qqq, trunc, row in series:
        s = [v for v in stock if v is not None]
        if len(s) < 2:
            continue
        recomputed = (s[-1] / s[0] - 1.0) * 100.0
        csv_val = row["one_year_pct"]
        if pd.notna(csv_val) and abs(recomputed - float(csv_val)) > TOL:
            bad.append((tkr, rd, round(recomputed, 3), float(csv_val)))
    if bad:
        print("RECONCILIATION FAILED (series one_year_pct disagrees with CSV > 0.1pp):")
        for tkr, rd, a, b in bad:
            print(f"   {tkr} {rd}: series {a} vs csv {b}")
        sys.exit(1)
    print(f"Reconciliation OK: {len(series)} series match results_per_stock.csv within +/-{TOL}pp.")


def indexed(arr):
    b = arr[0]
    return [None if (v is None or b in (None, 0)) else v / b * 100.0 for v in arr]


def aggregate(series, balanced_only):
    """Per-offset median/p25/p75/n for raw and excess across the chosen panel."""
    raw_cols = [[] for _ in range(MAXOFF + 1)]
    exc_cols = [[] for _ in range(MAXOFF + 1)]
    for tkr, rd, dates, stock, qqq, trunc, row in series:
        if balanced_only and (trunc or len([v for v in stock if v is not None]) < MAXOFF + 1):
            continue
        sidx, qidx = indexed(stock), indexed(qqq)
        for d in range(min(len(sidx), MAXOFF + 1)):
            sv = sidx[d]
            if sv is None:
                continue
            raw_cols[d].append(sv)
            qv = qidx[d]
            if qv is not None:
                exc_cols[d].append(sv - qv)

    def stat(cols):
        med, p25, p75, n = [], [], [], []
        for c in cols:
            if c:
                a = np.array(c, float)
                med.append(round(float(np.median(a)), 3))
                p25.append(round(float(np.percentile(a, 25)), 3))
                p75.append(round(float(np.percentile(a, 75)), 3))
                n.append(len(c))
            else:
                med.append(None); p25.append(None); p75.append(None); n.append(0)
        return {"median": med, "p25": p25, "p75": p75, "n": n}

    return {"raw": stat(raw_cols), "excess": stat(exc_cols)}


def crossing(median, baseline):
    """First offset (>0) where the median crosses the baseline (100 raw / 0 excess)."""
    prev = median[0]
    for d in range(1, len(median)):
        v = median[d]
        if v is None or prev is None:
            prev = v if v is not None else prev
            continue
        if (prev - baseline) == 0 or (prev - baseline) * (v - baseline) < 0:
            return d
        prev = v
    return None


def main():
    series = load_series()
    reconcile(series)
    allp = aggregate(series, balanced_only=False)
    balp = aggregate(series, balanced_only=True)
    out = {
        "offsets": list(range(MAXOFF + 1)),
        "all": allp,
        "balanced": balp,
        "n_start": {"all": allp["raw"]["n"][0], "balanced": balp["raw"]["n"][0]},
        "raw_cross_100": {"all": crossing(allp["raw"]["median"], 100),
                          "balanced": crossing(balp["raw"]["median"], 100)},
        "excess_cross_0": {"all": crossing(allp["excess"]["median"], 0),
                           "balanced": crossing(balp["excess"]["median"], 0)},
    }
    OUT.write_text(json.dumps(out), encoding="utf-8")
    kb = OUT.stat().st_size / 1024
    print(f"Wrote {OUT.name} ({kb:.0f} KB).")
    print(f"  panel n at offset 0: all={out['n_start']['all']}, balanced={out['n_start']['balanced']}")
    for off in (21, 63, 126, 252):
        a = allp["raw"]["median"][off]; b = balp["raw"]["median"][off]
        ae = allp["excess"]["median"][off]; be = balp["excess"]["median"][off]
        print(f"  offset {off:3d}: raw median all={a} balanced={b} | "
              f"excess all={ae} balanced={be} | n all={allp['raw']['n'][off]} bal={balp['raw']['n'][off]}")
    # bottom of the raw median (all panel)
    med = [v for v in allp["raw"]["median"] if v is not None]
    bottom = min(range(len(allp["raw"]["median"])),
                 key=lambda d: allp["raw"]["median"][d] if allp["raw"]["median"][d] is not None else 1e9)
    print(f"  raw median (all) bottoms at offset {bottom} = {allp['raw']['median'][bottom]}")


if __name__ == "__main__":
    main()
