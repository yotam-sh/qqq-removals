#!/usr/bin/env python3
"""
Fetch and cache the DAILY price series behind every row in results_per_stock.csv,
for the stock and for QQQ over the identical post-removal window, then verify the
fetched series reproduces the CSV's summary stats before anything ships.

Reuses ndx_removals_study's own functions (fetch + analyze_one) so the accuracy
gate exercises the exact code path that produced the CSV. Does not modify
ndx_removals_study.py or results_per_stock.csv.

Output (under data/processed/series/):
  {TICKER}_{YYYY-MM-DD}.json   per-stock aligned series + meta + gate
  _qqq.json                    cached QQQ over the full span
  _manifest.json               availability + gate status per stock

Re-runs read the cache and never re-hit Yahoo. On any HARD mismatch (series
fetched fine but a recomputed stat disagrees with the CSV beyond tolerance) the
script prints the offenders and exits non-zero rather than shipping inconsistent
numbers. Tickers that can no longer be fetched are marked unavailable and the
run continues (their page will degrade gracefully).
"""

import json
import os
import sys
import time
from pathlib import Path

import pandas as pd

import ndx_removals_study as S   # reuse fetch_* and analyze_one

ROOT = Path(__file__).resolve().parents[1]   # repo root (this file lives in src/)
CSV = str(ROOT / "data" / "processed" / "results_per_stock.csv")
SERIES_DIR = str(ROOT / "data" / "processed" / "series")
TOL_PCT = 0.1     # percentage points
TOL_DAY = 1       # trading days

GATE_FIELDS = [   # (field, tolerance, is_day)
    ("lowest_pct", TOL_PCT, False),
    ("days_to_low", TOL_DAY, True),
    ("highest_pct", TOL_PCT, False),
    ("days_to_high", TOL_DAY, True),
    ("one_year_pct", TOL_PCT, False),
    ("excess_vs_qqq_pct", TOL_PCT, False),
]


def cache_path(tkr, rd_str):
    return os.path.join(SERIES_DIR, f"{tkr}_{rd_str}.json")


def get_qqq(span_start, span_end):
    """QQQ closes over the full span, cached to disk and reloaded as a Series."""
    p = os.path.join(SERIES_DIR, "_qqq.json")
    if os.path.exists(p):
        d = json.load(open(p, encoding="utf-8"))
        return pd.Series(d["close"], index=pd.to_datetime(d["dates"]))
    print(f"Fetching QQQ once over {span_start.date()}..{span_end.date()} ...")
    q = S.fetch_prices(S.BENCHMARK, span_start, span_end)
    if q is None or q.empty:
        sys.exit("FATAL: could not fetch QQQ; cannot build relative series.")
    q.index = pd.to_datetime(q.index)
    json.dump({"dates": [t.strftime("%Y-%m-%d") for t in q.index],
               "close": [float(x) for x in q.values]},
              open(p, "w", encoding="utf-8"))
    return q


def build_entry(row, qqq):
    """Fetch one stock, build the aligned window series, and run the gate.
    Returns the cache entry dict (available True/False, gate ok/not)."""
    tkr = row["ticker"]
    rd = row["removal_date"]
    rd_str = rd.strftime("%Y-%m-%d")
    ftkr = row.get("fetch_ticker") if isinstance(row.get("fetch_ticker"), str) else tkr
    ftkr = ftkr or tkr

    closes, source = S.fetch_with_source(ftkr, rd - pd.Timedelta(days=5),
                                         rd + pd.Timedelta(days=420))
    if closes is None or closes.empty:
        return {"ticker": tkr, "removal_date": rd_str, "fetch_ticker": ftkr,
                "available": False, "reason": "not fetchable from data source"}, source

    # Clip to the study's snapshot end. Recent removals have INCOMPLETE 252-day
    # windows that keep growing as new bars print; the CSV froze them at last_day.
    # Clipping reproduces the exact window the study (and dashboard) used, so the
    # deep-dive numbers stay consistent with the dashboard. Older complete windows
    # already end at last_day, so this is a no-op for them.
    if isinstance(row.get("last_day"), str):
        closes = closes[closes.index <= pd.Timestamp(row["last_day"])]
        if closes.empty:
            return {"ticker": tkr, "removal_date": rd_str, "fetch_ticker": ftkr,
                    "available": False, "reason": "no data within snapshot window"}, source

    stats = S.analyze_one(closes, rd)
    if stats is None:
        return {"ticker": tkr, "removal_date": rd_str, "fetch_ticker": ftkr,
                "available": False, "reason": "insufficient data after removal"}, source

    # window exactly as the study builds it
    cw = closes[closes.index >= pd.Timestamp(rd)]
    win = cw.iloc[:S.WINDOW_TRADING_DAYS + 1]
    dates = [t.strftime("%Y-%m-%d") for t in win.index]
    stock = [round(float(x), 4) for x in win.values]
    qv = []
    for t in win.index:
        v = qqq.get(t)
        qv.append(round(float(v), 4) if v is not None and not pd.isna(v) else None)

    # QQQ excess over the identical [first_day_out, last_day] window (mirror analyze())
    fdo, lastd = pd.Timestamp(stats["first_day_out"]), pd.Timestamp(stats["last_day"])
    qwin = qqq[(qqq.index >= fdo) & (qqq.index <= lastd)]
    excess = None
    if len(qwin) >= 2:
        qqq_ret = (float(qwin.iloc[-1]) / float(qwin.iloc[0]) - 1) * 100
        excess = round(stats["one_year_pct"] - qqq_ret, 2)

    recomputed = dict(stats)
    recomputed["excess_vs_qqq_pct"] = excess

    # gate: recomputed vs CSV
    gate = {"ok": True, "fields": {}}
    for f, tol, _is_day in GATE_FIELDS:
        a = recomputed.get(f)
        b = row.get(f)
        if a is None or b is None or pd.isna(b):
            ok = (a is None) and (b is None or pd.isna(b))
            diff = None
        else:
            diff = abs(float(a) - float(b))
            ok = diff <= tol
        gate["fields"][f] = {"recomputed": a, "csv": (None if pd.isna(b) else b),
                             "diff": diff, "ok": ok}
        gate["ok"] = gate["ok"] and ok

    entry = {
        "ticker": tkr, "removal_date": rd_str, "fetch_ticker": ftkr,
        "available": True, "source": source,
        "first_day_out": str(stats["first_day_out"]), "last_day": str(stats["last_day"]),
        "data_days": int(stats["data_days"]), "truncated": bool(stats["truncated"]),
        "dates": dates, "stock": stock, "qqq": qv,
        "gate": gate,
    }
    return entry, source


def main():
    df = pd.read_csv(CSV, parse_dates=["removal_date"])
    os.makedirs(SERIES_DIR, exist_ok=True)
    print(f"Read {CSV}: {len(df)} stocks.")

    span_start = df["removal_date"].min() - pd.Timedelta(days=10)
    span_end = df["removal_date"].max() + pd.Timedelta(days=420)
    qqq = get_qqq(span_start, span_end)
    qqq.index = pd.to_datetime(qqq.index)

    manifest, mismatches, unavailable = {}, [], []
    n_cache = n_fetch = n_avail = 0

    for _, row in df.iterrows():
        tkr, rd = row["ticker"], row["removal_date"]
        rd_str = rd.strftime("%Y-%m-%d")
        key = f"{tkr}_{rd_str}"
        cp = cache_path(tkr, rd_str)

        if os.path.exists(cp):
            entry = json.load(open(cp, encoding="utf-8"))
            n_cache += 1
        else:
            entry, source = build_entry(row, qqq)
            json.dump(entry, open(cp, "w", encoding="utf-8"))
            n_fetch += 1
            if source == "yfinance":
                time.sleep(0.4)   # polite only on live hits

        if not entry.get("available"):
            unavailable.append(key)
        else:
            n_avail += 1
            if not entry["gate"]["ok"]:
                mismatches.append((key, entry["gate"]))
        manifest[key] = {
            "available": entry.get("available"),
            "gate_ok": entry.get("gate", {}).get("ok") if entry.get("available") else None,
            "source": entry.get("source"),
            "truncated": entry.get("truncated"),
            "data_days": entry.get("data_days"),
        }

    json.dump(manifest, open(os.path.join(SERIES_DIR, "_manifest.json"), "w",
                             encoding="utf-8"), indent=0)

    print(f"\n{'='*60}\nEXPORT SUMMARY")
    print(f"  cached (skipped fetch): {n_cache}   newly fetched: {n_fetch}")
    print(f"  available: {n_avail}/{len(df)}   unavailable: {len(unavailable)}")
    if unavailable:
        print(f"  unavailable tickers: {', '.join(unavailable)}")

    if mismatches:
        print(f"\n*** ACCURACY GATE FAILED: {len(mismatches)} stock(s) disagree "
              f"with {CSV} beyond tolerance (±{TOL_PCT}pp / ±{TOL_DAY}d) ***")
        for key, gate in mismatches:
            bad = {f: v for f, v in gate["fields"].items() if not v["ok"]}
            print(f"  {key}:")
            for f, v in bad.items():
                print(f"     {f}: recomputed={v['recomputed']} vs csv={v['csv']} "
                      f"(diff={v['diff']})")
        print("\nNot shipping inconsistent numbers. Investigate before building pages.")
        sys.exit(1)

    print(f"\nACCURACY GATE PASSED for all {n_avail} available stocks "
          f"(±{TOL_PCT}pp / ±{TOL_DAY}d). Cache in {SERIES_DIR}/ ready for build_stocks.py.")


if __name__ == "__main__":
    main()
