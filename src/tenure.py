#!/usr/bin/env python3
"""
Derive how long each removed stock had been IN the Nasdaq-100 (tenure) and tag an
archetype, so the dashboard can ask whether short-tenure "revolving-door" removals
recover differently from long-tenure "structural decliners".

Tenure = removal_date - addition_date, where addition_date is the most recent
"Added" event for that ticker (before its removal) in Wikipedia's Nasdaq-100
component-change tables -- the SAME source as `ndx_removals_study.py build-list`
(its table parser is reused here, not reimplemented).

A stock with no addition event in the table was a pre-window / original constituent:
its true tenure is unknown and only bounded below. We set tenure_censored = true and
record years_in_index as a LOWER BOUND (removal_date - earliest date the table covers).
We never fabricate a precise addition date.

archetype (thresholds parameterized, default <4y / >10y):
  revolving_door     years_in_index < SHORT (4)
  structural_decliner years_in_index > LONG (10)
  core_member        in between

Output: data/processed/tenure.json  keyed "TICKER-YYYY-MM-DD" ->
        {years_in_index, tenure_censored, archetype, addition_date|null}.
Small; merged onto RAW rows in index.html at load.
"""

import json
import sys
import io
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import ndx_removals_study as S  # reuse _find_changes_table / _clean / WIKI_URL

RESULTS = ROOT / "data" / "processed" / "results_per_stock.csv"
OUT = ROOT / "data" / "processed" / "tenure.json"

SHORT_YEARS = 4.0
LONG_YEARS = 10.0


def fetch_added_events():
    """Return (added_events: dict ticker->sorted list of pd.Timestamp, origin: Timestamp).
    origin = earliest date the change table covers (the censoring floor)."""
    import requests
    headers = {"User-Agent": "Mozilla/5.0 (research script)"}
    html = requests.get(S.WIKI_URL, headers=headers, timeout=30).text
    tables = pd.read_html(io.StringIO(html))
    t = S._find_changes_table(tables)
    if t is None:
        raise SystemExit("Could not locate the Nasdaq-100 component-changes table.")
    t = t.copy()
    t.columns = [f"{str(a).lower()}_{str(b).lower()}" for a, b in t.columns]
    date_col = next(c for c in t.columns if c.startswith("date"))
    add_tk = next(c for c in t.columns if c.startswith("added") and "tick" in c)

    added = {}
    all_dates = []
    for _, r in t.iterrows():
        d = pd.to_datetime(S._clean(r.get(date_col, "")), errors="coerce")
        if pd.isna(d):
            continue
        all_dates.append(d)
        tk = S._clean(r.get(add_tk, "")).upper()
        if tk and tk.lower() not in ("nan", "—", "-", ""):
            added.setdefault(tk, []).append(d)
    for tk in added:
        added[tk] = sorted(added[tk])
    origin = min(all_dates) if all_dates else pd.Timestamp("2005-01-01")
    return added, origin


def archetype(years, censored=False):
    # Censored tenure is a LOWER BOUND: we must not claim "revolving_door" (short
    # tenure) for a name that may actually be a long-lived original. Only the
    # structural_decliner label is safe when even the lower bound exceeds LONG;
    # otherwise stay neutral (core_member).
    if censored:
        return "structural_decliner" if years > LONG_YEARS else "core_member"
    if years < SHORT_YEARS:
        return "revolving_door"
    if years > LONG_YEARS:
        return "structural_decliner"
    return "core_member"


def main():
    res = pd.read_csv(RESULTS, parse_dates=["removal_date"])
    added, origin = fetch_added_events()
    print(f"Wikipedia: {sum(len(v) for v in added.values())} Added events across "
          f"{len(added)} tickers; table covers from {origin.date()}.")

    out = {}
    n_cens = 0
    for _, r in res.iterrows():
        tkr, rd = r["ticker"], r["removal_date"]
        key = f"{tkr}-{rd.strftime('%Y-%m-%d')}"
        cands = [d for d in added.get(tkr, []) if d < rd]
        if cands:
            add_date = max(cands)
            years = (rd - add_date).days / 365.25
            censored = False
            add_str = add_date.strftime("%Y-%m-%d")
        else:
            # pre-window / original constituent: lower bound only
            add_date = origin
            years = (rd - origin).days / 365.25
            censored = True
            add_str = None
            n_cens += 1
        out[key] = {"years_in_index": round(years, 2),
                    "tenure_censored": censored,
                    "archetype": archetype(years, censored),
                    "addition_date": add_str}

    OUT.write_text(json.dumps(out), encoding="utf-8")
    arche = {}
    for v in out.values():
        arche[v["archetype"]] = arche.get(v["archetype"], 0) + 1
    print(f"Wrote {OUT.name}: {len(out)} rows | censored (lower-bound tenure): {n_cens}")
    print(f"  archetype counts: {arche}")
    print(f"  thresholds: <{SHORT_YEARS}y revolving_door, >{LONG_YEARS}y structural_decliner")


if __name__ == "__main__":
    main()
