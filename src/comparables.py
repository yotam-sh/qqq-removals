#!/usr/bin/env python3
"""
For each removal, find the most similar PRIOR removals (peers) via an EXPLICIT
similarity score over dimensions already computed by other steps (no refetch):

  similarity(i, j) =  3.0 * same_sector
                    + 2.0 * same_archetype (tenure band)
                    + 2.0 * same_market_regime
                    + 3.0 * (1 - min(|trough_i - trough_j|, CAP) / CAP)   # early-decline closeness

Only j with removal_date strictly before i qualify (a peer must be a prior event).
Top 5 by score are emitted as comparable_ids per id (-> embedded into STOCKS).

Inputs: results_per_stock.csv + sectors.json + tenure.json + regime.json.
Output: data/processed/comparables.json {id: {comparable_ids:[...], criteria:"..."}}.
"""

import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PROC = ROOT / "data" / "processed"
RESULTS = PROC / "results_per_stock.csv"
OUT = PROC / "comparables.json"

CAP = 50.0      # trough-difference (pp) at which decline-closeness contributes 0
TOPN = 5
CRITERIA = ("same sector (+3), same tenure archetype (+2), same market regime (+2), "
            "and closeness of trough depth (+0–3); peers limited to earlier removals")


def load_json(name):
    p = PROC / name
    return json.load(open(p, encoding="utf-8")) if p.exists() else {}


def main():
    res = pd.read_csv(RESULTS, parse_dates=["removal_date"])
    res["rd"] = res["removal_date"].dt.strftime("%Y-%m-%d")
    sec = load_json("sectors.json").get("per_id", {})
    ten = load_json("tenure.json")
    reg = load_json("regime.json").get("per_id", {})

    recs = []
    for _, r in res.iterrows():
        i = f"{r['ticker']}-{r['rd']}"
        recs.append({"id": i, "date": r["removal_date"],
                     "sector": (sec.get(i) or {}).get("sector"),
                     "arch": (ten.get(i) or {}).get("archetype"),
                     "regime": (reg.get(i) or {}).get("market_regime"),
                     "trough": float(r["lowest_pct"]) if pd.notna(r["lowest_pct"]) else None})

    out = {}
    for a in recs:
        scored = []
        for b in recs:
            if b["id"] == a["id"] or b["date"] >= a["date"]:
                continue  # peers must be strictly prior
            s = 0.0
            if a["sector"] and a["sector"] == b["sector"]:
                s += 3.0
            if a["arch"] and a["arch"] == b["arch"]:
                s += 2.0
            if a["regime"] and a["regime"] == b["regime"]:
                s += 2.0
            if a["trough"] is not None and b["trough"] is not None:
                s += 3.0 * (1 - min(abs(a["trough"] - b["trough"]), CAP) / CAP)
            scored.append((s, b["date"], b["id"]))
        # highest score; tie-break to the most recent prior event
        scored.sort(key=lambda t: (-t[0], -t[1].toordinal()))
        out[a["id"]] = {"comparable_ids": [i for _, _, i in scored[:TOPN]], "criteria": CRITERIA}

    OUT.write_text(json.dumps(out), encoding="utf-8")
    n_with = sum(1 for v in out.values() if v["comparable_ids"])
    print(f"Wrote {OUT.name}: {len(out)} stocks, {n_with} with >=1 prior peer.")
    # show a couple of examples
    for ex in ("ENPH-2023-12-18", "PTON-2022-01-24", "NFLX-2012-12-24"):
        if ex in out:
            print(f"  {ex} -> {out[ex]['comparable_ids']}")


if __name__ == "__main__":
    main()
