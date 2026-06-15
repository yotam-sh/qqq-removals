#!/usr/bin/env python3
"""
Reconstruct the FULL Nasdaq-100 removal universe for the 20-year window and
classify the fate of every name that was NOT analyzed, so survivorship bias can
be measured instead of left unstated.

Inputs (read-only):
  data/raw/removals.csv            hand-reviewed removal list from
                                   `ndx_removals_study.py build-list` (has the
                                   `include` flag: 0 = acquisition/delisting-driven,
                                   excluded from the price study).
  data/processed/results_per_stock.csv   the names that actually analyzed (= survived
                                   AND returned a usable price series).
  data/processed/fates_to_review.csv     (optional) hand-filled fates; re-read on rerun.

Outputs:
  data/processed/universe.csv      one row per (ticker, removal_date): analyzed yes/no, fate.
  data/processed/fates_to_review.csv     every still-unknown fate, for hand-filling.

Fate is classified ONLY from the Wikipedia "reason" text (never guessed):
  acquired  -> stopped trading via acquisition / merger / going private (≈ deal exit)
  delisted  -> bankruptcy / liquidation / forced delisting (a real loss)
  unknown   -> not resolvable from the text (carried through as an explicit band).
Listing transfers, REIT conversions, reconstitution and weight drops mean the
company KEPT trading, so a non-analyzed name of that kind is `unknown` (no data),
NOT `delisted` -- we must not invent a loss.
"""

import os
import re
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
REMOVALS = ROOT / "data" / "raw" / "removals.csv"
RESULTS = ROOT / "data" / "processed" / "results_per_stock.csv"
UNIVERSE = ROOT / "data" / "processed" / "universe.csv"
REVIEW = ROOT / "data" / "processed" / "fates_to_review.csv"

ACQUIRED_PAT = re.compile(
    r"acqui|merg|bought|took over|taken private|going private|go private|"
    r"went private|private equity|closed-end fund|replaced", re.I)
DELISTED_PAT = re.compile(
    r"delist|bankrupt|liquidat|ceased|dissolv|pink sheet|chapter 11", re.I)


def classify(reason):
    """Return acquired/delisted/unknown from the reason text. Delisted is checked
    first so a 'delisted after a failed merger' note is recorded as the loss."""
    r = str(reason or "")
    if DELISTED_PAT.search(r):
        return "delisted"
    if ACQUIRED_PAT.search(r):
        return "acquired"
    return "unknown"


def load_review_overrides():
    """Hand-filled fates from a prior run: {(ticker, removal_date): fate}."""
    if not REVIEW.exists():
        return {}
    df = pd.read_csv(REVIEW, dtype=str).fillna("")
    out = {}
    for _, r in df.iterrows():
        f = r.get("fate", "").strip().lower()
        if f in ("acquired", "delisted", "unknown") and f != "unknown":
            out[(r["ticker"], r["removal_date"])] = f
    return out


def main():
    rem = pd.read_csv(REMOVALS, parse_dates=["removal_date"])
    rem["removal_date"] = rem["removal_date"].dt.strftime("%Y-%m-%d")
    rem = rem.drop_duplicates(subset=["ticker", "removal_date"]).reset_index(drop=True)

    res = pd.read_csv(RESULTS, parse_dates=["removal_date"])
    res["removal_date"] = res["removal_date"].dt.strftime("%Y-%m-%d")
    analyzed_keys = set(zip(res["ticker"], res["removal_date"]))

    overrides = load_review_overrides()

    rows, still_unknown = [], []
    for _, r in rem.iterrows():
        key = (r["ticker"], r["removal_date"])
        analyzed = key in analyzed_keys
        if analyzed:
            fate = "survived"
        else:
            fate = overrides.get(key) or classify(r["reason"])
            if fate == "unknown":
                still_unknown.append({"ticker": r["ticker"], "removal_date": r["removal_date"],
                                      "company": r.get("company", ""), "reason": r.get("reason", ""),
                                      "fate": ""})
        rows.append({"ticker": r["ticker"], "removal_date": r["removal_date"],
                     "company": r.get("company", ""), "analyzed": "yes" if analyzed else "no",
                     "fate": fate})

    uni = pd.DataFrame(rows)
    UNIVERSE.parent.mkdir(parents=True, exist_ok=True)
    uni.to_csv(UNIVERSE, index=False)

    # write/refresh the review file (preserve any hand-filled rows already resolved)
    rev = pd.DataFrame(still_unknown, columns=["ticker", "removal_date", "company", "reason", "fate"])
    rev.to_csv(REVIEW, index=False)

    n = len(uni)
    na = (uni["analyzed"] == "yes").sum()
    fates = uni[uni["analyzed"] == "no"]["fate"].value_counts().to_dict()
    print(f"universe.csv: {n} removals | analyzed {na} | not-analyzed {n-na}")
    print(f"  non-analyzed fate split: {fates}")
    print(f"  coverage (analyzed / total): {na/n*100:.1f}%")
    if not rev.empty:
        print(f"  {len(rev)} unknown fate(s) written to {REVIEW.name} for hand review:")
        for _, r in rev.iterrows():
            print(f"     {r['ticker']} {r['removal_date']}  ({r['company']})")
    else:
        print("  no unknown fates remaining.")


if __name__ == "__main__":
    main()
