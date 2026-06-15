#!/usr/bin/env python3
"""Pass-2 wrap-up: spot-check reconciliation + the headline prints. Read-only."""

import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PROC = ROOT / "data" / "processed"


def jload(n):
    p = PROC / n
    return json.load(open(p, encoding="utf-8")) if p.exists() else {}


def main():
    res = pd.read_csv(PROC / "results_per_stock.csv", parse_dates=["removal_date"])
    res["rd"] = res["removal_date"].dt.strftime("%Y-%m-%d")
    res["id"] = res["ticker"] + "-" + res["rd"]
    uni = pd.read_csv(PROC / "universe.csv")
    rt = jload("roundtrip.json"); reg = jload("regime.json"); sec = jload("sectors.json")

    print("=" * 72)
    print("SPOT-CHECK: new fields vs source")
    print("=" * 72)
    # round-tripper
    rid = "NFLX-2012-12-24"
    r = rt["per_id"].get(rid, {})
    print(f"\n round-tripper {rid}: re_added={r.get('re_added')} readd={r.get('readd_date')} "
          f"gap={r.get('round_trip_years')}y ultimate_fate={r.get('ultimate_fate')}")
    print(f"   (source: appears on the Added side of the index-change table after its removal)")
    # delisted name (non-analyzed; from universe)
    d = uni[(uni["ticker"] == "NIHD")]
    if len(d):
        print(f"\n delisted NIHD {d.iloc[0]['removal_date']}: universe fate={d.iloc[0]['fate']}, "
              f"analyzed={d.iloc[0]['analyzed']} (no series -> not in RAW/STOCKS; counted in fate breakdown)")
    # bear/crash-market removal: reconcile QQQ window
    crash_ids = [k for k, v in reg.get("per_id", {}).items() if v["market_regime"] == "crash"]
    bid = crash_ids[0] if crash_ids else None
    if bid:
        rv = reg["per_id"][bid]; row = res[res["id"] == bid].iloc[0]
        diff = abs(rv["qqq_window_pct"] - float(row["qqq_same_window_pct"]))
        print(f"\n crash-market {bid}: regime={rv['market_regime']} qqq_window={rv['qqq_window_pct']}% "
              f"(CSV {row['qqq_same_window_pct']}%, diff {diff:.3f}) qqq_maxDD={rv['qqq_max_drawdown']}%")
        print(f"   decomposition: stock {row['one_year_pct']}% = market {rv['qqq_window_pct']}% + excess {row['excess_vs_qqq_pct']}%"
              f"  -> {'RECONCILES' if diff <= 0.1 else 'MISMATCH'}")

    print("\n" + "=" * 72)
    print("ROUND-TRIPS & ULTIMATE FATE")
    print("=" * 72)
    print(f"  round-trip rate (analyzed): {rt['round_trip_rate']}%  median gap {rt['median_gap_years']}y")
    print(f"  ultimate_fate over 204 universe: {rt['fate_distribution']}")

    print("\n" + "=" * 72)
    print("OUTCOME BY REGIME (median 1-yr / excess, 95% CI, n)")
    print("=" * 72)
    for r_ in reg["order"]:
        v = reg["by_regime"][r_]
        if v["n"]:
            o, e = v["one_year"], v["excess"]
            print(f"  {r_:12s} 1y {o['median']:>7} [{o['lo']}, {o['hi']}] | excess {e['median']:>7} [{e['lo']}, {e['hi']}] | n={v['n']}")

    print("\n" + "=" * 72)
    print("OUTCOME BY SECTOR (median 1-yr, 95% CI, n)")
    print("=" * 72)
    for s in sec["order"]:
        v = sec["by_sector"][s]; o = v["one_year"]
        print(f"  {s:24s} {o['median']:>7} [{o['lo']}, {o['hi']}]  n={v['n']}{'  (small)' if o['small'] else ''}")

    print("\n" + "=" * 72)
    print("UNKNOWNS")
    print("=" * 72)
    print(f"  unknown sector tickers: {sec.get('unknown_tickers') or '-'}")
    unk_fate = uni[uni['fate'] == 'unknown']['ticker'].tolist()
    print(f"  universe fate=unknown ({len(unk_fate)}): {', '.join(unk_fate)}")


if __name__ == "__main__":
    main()
