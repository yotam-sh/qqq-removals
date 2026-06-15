#!/usr/bin/env python3
"""
Auto-generate a grounded executive abstract for the top of index.html.

Reads the computed JSONs (survivorship, average_path, cis, regime, roundtrip, sectors)
plus results_per_stock.csv, and emits abstract.json: headline `figures` + a list of
`sentences`. EVERY sentence maps to a computed number; if a dependency JSON is missing,
that sentence is omitted rather than invented. No citations, no outside findings.
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PROC = ROOT / "data" / "processed"
RESULTS = PROC / "results_per_stock.csv"
OUT = PROC / "abstract.json"


def jload(name):
    p = PROC / name
    return json.load(open(p, encoding="utf-8")) if p.exists() else None


def med(s):
    s = s.dropna()
    return round(float(s.median()), 1) if len(s) else None


def pct1(v):
    return ("+" if v >= 0 else "") + f"{v:.1f}%"


def main():
    res = pd.read_csv(RESULTS, parse_dates=["removal_date"])
    res["trunc"] = res["truncated"].astype(str).str.lower().isin(["true", "1"])
    full = res[~res["trunc"]]
    surv = jload("survivorship.json"); ap = jload("average_path.json"); cis = jload("cis.json")
    reg = jload("regime.json"); rt = jload("roundtrip.json"); sec = jload("sectors.json")

    fig, sent = {}, []
    firstyear = int(res["removal_date"].dt.year.min())

    # 1. coverage / survivorship
    if surv:
        f = surv["funnel"]
        fig["coverage_pct"] = surv["coverage_pct"]; fig["funnel"] = f
        sent.append(f"Of {f['total']} Nasdaq-100 removals since {firstyear}, {f['analyzed']} "
                    f"({surv['coverage_pct']}% of the {f['eligible']} eligible) had a usable "
                    f"post-removal price series; the rest were acquisitions ({f['acquired_excluded']}) "
                    f"or names that left no data ({f['missing']}). Because the missing names skew toward "
                    f"the worst outcomes, the figures below are an upper bound.")

    # 2. trough + timing  (all rows; matches dashboard cards)
    mt, mdl = med(res["lowest_pct"]), med(res["days_to_low"])
    if mt is not None:
        fig["median_trough_pct"] = mt; fig["median_days_to_low"] = mdl
        sent.append(f"The median removed stock bottomed at {pct1(mt)} versus its first close out of "
                    f"the index, about {int(mdl)} trading days later.")

    # 3. average path (balanced panel)
    if ap:
        bal = ap.get("balanced", {}).get("raw", {}).get("median", [])
        if bal and bal[-1] is not None:
            end = round(bal[-1] - 100, 1)
            minv = min(v for v in bal if v is not None)
            fig["avgpath_end_pct"] = end
            dipped = minv < 100
            sent.append(f"Across stocks, the median indexed path {'dipped below' if dipped else 'never fell below'} "
                        f"its starting level and stood at {pct1(end)} by trading day 252 (balanced panel of full-year windows).")

    # 4. one-year + positive + beat
    if cis and cis.get("overall", {}).get("one_year"):
        o = cis["overall"]["one_year"]
        posp = round((full["one_year_pct"] > 0).mean() * 100) if len(full) else None
        exf = full["excess_vs_qqq_pct"].dropna()
        beat = round((exf > 0).mean() * 100) if len(exf) else None
        fig["median_1y_pct"] = o["median"]; fig["ci_1y"] = [o["lo"], o["hi"]]
        fig["pct_positive"] = posp; fig["pct_beat_qqq"] = beat
        s = f"Median one-year return was {pct1(o['median'])} (95% CI [{pct1(o['lo'])}, {pct1(o['hi'])}], n={o['n']})"
        if posp is not None:
            s += f"; {posp}% of full-year names were positive"
        if beat is not None:
            s += f", but only {beat}% beat QQQ over the same window"
        sent.append(s + ".")

    # 5. survivorship bias band
    if surv:
        oy = surv["one_year"]
        fig["bias_range_1y"] = [oy["defensible_worst"], oy["survivors"]]
        sent.append(f"Correcting for the missing names pulls that median as low as {pct1(oy['defensible_worst'])} "
                    f"(a bias spread of about {round(oy['survivors']-oy['defensible_worst'],1)} points).")

    # 6. regime
    if reg and reg.get("by_regime"):
        br = reg["by_regime"]
        def m(r): return (br.get(r, {}).get("one_year", {}) or {}).get("median")
        sb, cr = m("strong_bull"), m("crash")
        if sb is not None and cr is not None:
            fig["regime_strong_bull_1y"] = sb; fig["regime_crash_1y"] = cr
            sent.append(f"Outcomes tracked the market: median one-year return was {pct1(sb)} for removals during "
                        f"strong-bull QQQ windows versus {pct1(cr)} during crash windows.")

    # 7. sector
    if sec and sec.get("by_sector"):
        bs = {s: v["one_year"]["median"] for s, v in sec["by_sector"].items()
              if v["one_year"]["median"] is not None and v["n"] >= 5}
        if len(bs) >= 2:
            best = max(bs, key=bs.get); worst = min(bs, key=bs.get)
            fig["sector_best"] = [best, bs[best]]; fig["sector_worst"] = [worst, bs[worst]]
            sent.append(f"By sector (groups with n≥5), {best} removals fared best (median {pct1(bs[best])}) "
                        f"and {worst} worst (median {pct1(bs[worst])}).")

    # 8. round-trip
    if rt:
        fig["round_trip_rate"] = rt["round_trip_rate"]; fig["median_gap_years"] = rt["median_gap_years"]
        sent.append(f"And then what? {rt['round_trip_rate']}% of analyzed removals later re-entered the "
                    f"Nasdaq-100, a median {rt['median_gap_years']} years after leaving.")

    caveat = ("Descriptive and educational, not investment advice. Survivorship bias applies throughout: "
              "delisted and unresolved names are under-represented, so realized outcomes were likely worse.")
    out = {"figures": fig, "sentences": sent, "caveat": caveat}
    OUT.write_text(json.dumps(out), encoding="utf-8")
    print(f"Wrote {OUT.name}: {len(sent)} grounded sentences.")
    for s in sent:
        print("  - " + s.encode("ascii", "replace").decode())


if __name__ == "__main__":
    main()
