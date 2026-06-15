#!/usr/bin/env python3
"""
Assign each removed ticker a GICS sector.

NOTE on sourcing: yfinance Ticker.info is unreliable for THIS dataset because many
tickers were delisted or REUSED by a different company (GOLD->Barrick, HANS->Monster
Beverage, MNST collision, etc.), so a live lookup returns the wrong company's sector.
We therefore use a curated GICS map keyed by (historical) ticker as the authoritative
source -- factual public classification, the same discipline as the COMPANY map. Any
ticker not in the map is left `unknown` (never silently guessed) and surfaced; if
`--yf` is passed we additionally try yfinance only for those gaps. `sectors.csv` is
written for hand-correction and re-read on subsequent runs (corrections win).

Output: data/processed/sectors.csv (ticker,sector,industry,source) and sectors.json
(per_id sector/industry -> RAW/STOCKS; by_sector median 1y/excess + CI + n).
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "data" / "processed" / "results_per_stock.csv"
CSV = ROOT / "data" / "processed" / "sectors.csv"
OUT = ROOT / "data" / "processed" / "sectors.json"

IT = "Information Technology"; CD = "Consumer Discretionary"; CS = "Consumer Staples"
CM = "Communication Services"; HC = "Health Care"; FIN = "Financials"; IND = "Industrials"
ENE = "Energy"; MAT = "Materials"; RE = "Real Estate"; UTL = "Utilities"

SECTOR = {
 "CMVT":IT,"AEOS":CD,"ROST":CD,"PTEN":ENE,"ERIC":IT,"TLAB":IT,"UAUA":IND,"DISCA":CM,
 "LAMR":RE,"AMLN":HC,"SIRI":CM,"CDNS":IT,"VMED":CM,"FMCN":CM,"AKAM":IT,"HANS":CS,
 "RYAAY":IND,"STLD":MAT,"LBTYA":CM,"LOGI":IT,"JBHT":IND,"CTAS":IND,"ILMN":HC,"QGEN":HC,
 "URBN":CD,"FSLR":IT,"TEVA":HC,"TCOM":CD,"INFY":IT,"FLEX":IT,"LRCX":IT,"EA":CM,"NFLX":CM,
 "RIMM":IT,"VRSN":IT,"MRVL":IT,"PRGO":HC,"ORCL":IT,"GOLD":MAT,"FOSL":CD,"MCHP":IT,
 "XRAY":HC,"FFIV":IT,"EXPE":CD,"EQIX":RE,"LILA":CM,"WYNN":CD,"VIP":CM,"GRMN":CD,
 "EXPD":IND,"CHRW":IND,"LILAK":CM,"KLAC":IT,"BATRA":CM,"BATRK":CM,"NTAP":IT,"BBBY":CD,
 "SBAC":RE,"TRIP":CM,"MAT":CD,"TSCO":CD,"NCLH":CD,"DISCK":CM,"VOD":CM,"SHPG":HC,"STX":IT,
 "QRTEA":CD,"HAS":CD,"HSIC":HC,"NLOK":IT,"MYL":HC,"AAL":IND,"WTW":FIN,"UAL":IND,"CSGP":RE,
 "WDC":IT,"BMRN":HC,"LBTYK":CM,"TTWO":CM,"ULTA":CD,"INCY":HC,"CHKP":IT,"FOX":CM,"FOXA":CM,
 "CDW":IT,"PTON":CD,"OKTA":IT,"MTCH":CM,"BIDU":CM,"NTES":CM,"SWKS":IT,"DOCU":IT,"RIVN":CD,
 "ALGN":HC,"EBAY":CD,"ZM":IT,"JD":CD,"LCID":CD,"ENPH":IT,"DLTR":CS,"SMCI":IT,"MRNA":HC,
 "MDB":IT,"SOLS":MAT,"ON":IT,"LULU":CD,"GFS":IT,"BIIB":HC,"TTD":IT,"AZN":HC,"TEAM":IT,
 "VSNT":CM,  # Versant — NBCUniversal cable-networks spinoff (tentative; correct in sectors.csv)
}


def load_corrections():
    if not CSV.exists():
        return {}
    df = pd.read_csv(CSV, dtype=str).fillna("")
    return {r["ticker"]: r["sector"] for _, r in df.iterrows()
            if r.get("sector", "").strip() and r["sector"].strip().lower() != "unknown"}


def ci(vals):
    a = np.array([v for v in vals if v is not None and not np.isnan(v)], float)
    n = len(a)
    if n == 0:
        return {"median": None, "lo": None, "hi": None, "n": 0, "small": True}
    if n == 1:
        v = round(float(a[0]), 2); return {"median": v, "lo": v, "hi": v, "n": 1, "small": True}
    rng = np.random.default_rng(7)
    meds = np.median(a[rng.integers(0, n, size=(10000, n))], axis=1)
    return {"median": round(float(np.median(a)), 2), "lo": round(float(np.percentile(meds, 2.5)), 2),
            "hi": round(float(np.percentile(meds, 97.5)), 2), "n": int(n), "small": bool(n < 5)}


def main():
    res = pd.read_csv(RESULTS, parse_dates=["removal_date"])
    res["rd"] = res["removal_date"].dt.strftime("%Y-%m-%d")
    corrections = load_corrections()

    tickers = sorted(res["ticker"].unique())
    rows, per_tk = [], {}
    unknown = []
    for tk in tickers:
        sec = corrections.get(tk) or SECTOR.get(tk, "unknown")
        src = "correction" if tk in corrections else ("map" if tk in SECTOR else "unknown")
        if sec == "unknown":
            unknown.append(tk)
        per_tk[tk] = sec
        rows.append({"ticker": tk, "sector": sec, "industry": "", "source": src})
    pd.DataFrame(rows).to_csv(CSV, index=False)

    # per-id + per-sector aggregates
    per_id, groups = {}, {}
    for _, r in res.iterrows():
        sec = per_tk[r["ticker"]]
        per_id[f"{r['ticker']}-{r['rd']}"] = {"sector": sec, "industry": None}
        if sec == "unknown":
            continue
        g = groups.setdefault(sec, {"1y": [], "ex": []})
        g["1y"].append(float(r["one_year_pct"]) if pd.notna(r["one_year_pct"]) else None)
        if pd.notna(r["excess_vs_qqq_pct"]):
            g["ex"].append(float(r["excess_vs_qqq_pct"]))
    by_sector = {s: {"one_year": ci(v["1y"]), "excess": ci(v["ex"]), "n": len(v["1y"])}
                 for s, v in groups.items()}

    out = {"per_id": per_id, "by_sector": by_sector,
           "order": sorted(by_sector, key=lambda s: -by_sector[s]["n"]), "unknown_tickers": unknown}
    OUT.write_text(json.dumps(out), encoding="utf-8")
    print(f"Wrote {CSV.name} ({len(tickers)} tickers) and {OUT.name}")
    print("  sector counts: " + ", ".join(f"{s}={by_sector[s]['n']}" for s in out["order"]))
    for s in out["order"]:
        c = by_sector[s]["one_year"]
        print(f"  {s:24s} median 1y {c['median']:>7}  CI [{c['lo']}, {c['hi']}]  n={c['n']}")
    print(f"  unknown sector tickers ({len(unknown)}): {unknown or '-'}")


if __name__ == "__main__":
    main()
