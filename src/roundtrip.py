#!/usr/bin/env python3
"""
Round-trip & ultimate fate: did a removed stock later earn its way back into the
Nasdaq-100, and where did it ultimately land?

Re-addition is derived ENTIRELY from Wikipedia's component-change tables (the same
source as tenure.py / build-list) -- we never assert a stock's present-day status
from memory. ultimate_fate combines re-addition with universe.csv's `fate` column
(we reuse that classification, we do not redo it).

Outputs data/processed/roundtrip.json:
  per_id      : {TICKER-YYYY-MM-DD: {re_added, readd_date, round_trip_years, ultimate_fate}}
                for the 126 analyzed removals (-> merged onto RAW and STOCKS)
  fate_distribution : counts of ultimate_fate across the full 204-removal universe
  gap_years   : round_trip_years for analyzed re-added names (for the gap histogram)
  round_trip_rate, median_gap_years
ultimate_fate in {re_added, still_out, acquired, delisted, unknown}.
"""

import io
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import ndx_removals_study as S  # reuse _find_changes_table / _clean / WIKI_URL

RESULTS = ROOT / "data" / "processed" / "results_per_stock.csv"
UNIVERSE = ROOT / "data" / "processed" / "universe.csv"
OUT = ROOT / "data" / "processed" / "roundtrip.json"


def fetch_added_events():
    """ticker -> sorted list of pd.Timestamp it was ADDED to the index."""
    import requests
    html = requests.get(S.WIKI_URL, headers={"User-Agent": "Mozilla/5.0 (research script)"},
                        timeout=30).text
    tables = pd.read_html(io.StringIO(html))
    t = S._find_changes_table(tables)
    if t is None:
        sys.exit("Could not locate the Nasdaq-100 component-changes table.")
    t = t.copy()
    t.columns = [f"{str(a).lower()}_{str(b).lower()}" for a, b in t.columns]
    date_col = next(c for c in t.columns if c.startswith("date"))
    add_tk = next(c for c in t.columns if c.startswith("added") and "tick" in c)
    added = {}
    for _, r in t.iterrows():
        d = pd.to_datetime(S._clean(r.get(date_col, "")), errors="coerce")
        if pd.isna(d):
            continue
        tk = S._clean(r.get(add_tk, "")).upper()
        if tk and tk.lower() not in ("nan", "—", "-", ""):
            added.setdefault(tk, []).append(d)
    for tk in added:
        added[tk] = sorted(added[tk])
    return added


def readd_for(added, ticker, removal_date):
    """First re-addition strictly after the removal date, or (False, None, None)."""
    rd = pd.Timestamp(removal_date)
    later = [d for d in added.get(ticker, []) if d > rd]
    if later:
        d0 = min(later)
        return True, d0.strftime("%Y-%m-%d"), round((d0 - rd).days / 365.25, 2)
    return False, None, None


def ultimate(re_added, fate):
    if re_added:
        return "re_added"
    if fate == "survived":          # analyzed, still independent as of last data
        return "still_out"
    if fate in ("acquired", "delisted", "unknown"):
        return fate
    return "unknown"


def main():
    added = fetch_added_events()
    uni = pd.read_csv(UNIVERSE)
    uni["removal_date"] = pd.to_datetime(uni["removal_date"]).dt.strftime("%Y-%m-%d")
    res = pd.read_csv(RESULTS, parse_dates=["removal_date"])
    res["rd"] = res["removal_date"].dt.strftime("%Y-%m-%d")
    analyzed_keys = set(zip(res["ticker"], res["rd"]))

    # full-universe ultimate fate distribution (204)
    dist = {}
    for _, r in uni.iterrows():
        ra, _, _ = readd_for(added, r["ticker"], r["removal_date"])
        uf = ultimate(ra, r["fate"])
        dist[uf] = dist.get(uf, 0) + 1

    # per-id for the 126 analyzed
    per_id, gaps = {}, []
    for _, r in res.iterrows():
        tkr, rd = r["ticker"], r["rd"]
        ra, rdate, gap = readd_for(added, tkr, rd)
        # fate from universe (analyzed rows are 'survived')
        urow = uni[(uni["ticker"] == tkr) & (uni["removal_date"] == rd)]
        fate = urow.iloc[0]["fate"] if len(urow) else "survived"
        uf = ultimate(ra, fate)
        per_id[f"{tkr}-{rd}"] = {"re_added": ra, "readd_date": rdate,
                                 "round_trip_years": gap, "ultimate_fate": uf}
        if ra and gap is not None:
            gaps.append(gap)

    out = {
        "per_id": per_id,
        "fate_distribution": dist,
        "gap_years": sorted(gaps),
        "round_trip_rate": round(len(gaps) / len(per_id) * 100, 1) if per_id else 0,
        "median_gap_years": round(float(pd.Series(gaps).median()), 2) if gaps else None,
        "n_analyzed": len(per_id),
    }
    OUT.write_text(json.dumps(out), encoding="utf-8")
    print(f"Wrote {OUT.name}")
    print(f"  round-trip rate (analyzed): {out['round_trip_rate']}%  "
          f"({len(gaps)}/{len(per_id)}), median gap {out['median_gap_years']}y")
    print(f"  ultimate_fate over 204 universe: {dist}")
    rts = sorted([(v['round_trip_years'], k) for k, v in per_id.items() if v['re_added']])
    print(f"  round-trippers: {', '.join(k+' ('+str(g)+'y)' for g,k in rts)}")


if __name__ == "__main__":
    main()
