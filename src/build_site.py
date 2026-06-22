#!/usr/bin/env python3
"""
Build the production QQQ-Removals dashboard — the Comet-branded single-page site.

Reads the repo's real processed data (data/processed/*) and emits a single
self-contained `dist/index.html` that opens directly in a browser (CDN deps only:
Chart.js + zoom plugin, Google Fonts, Lucide). The Comet design system look is
reproduced by inlining the vendored token layers in `src/comet-tokens.css` and
hand-writing the components — no React / no _ds_bundle.js.

Per-stock deep-dives are an overlay synced to the URL hash, so links like
`index.html#NFLX-2012-12-24` open directly and are shareable.

This is the only HTML builder: it consumes the analysis JSON/CSV in data/processed
directly (no base-page + patch passes). The analysis scripts that produce those
files are unchanged. Run it after the analysis pipeline:

    py -3.13 src/build_site.py
"""
from __future__ import annotations
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROC = ROOT / "data" / "processed"
HERE = Path(__file__).resolve().parent

FATE = {
    "still_out":  {"label": "Trading",  "tone": "neutral"},
    "re_added":   {"label": "Re-added", "tone": "positive"},
    "acquired":   {"label": "Acquired", "tone": "accent"},
    "delisted":   {"label": "Delisted", "tone": "negative"},
    "unknown":    {"label": "Unknown",  "tone": "neutral"},
}


def load_json(name: str):
    return json.loads((PROC / name).read_text(encoding="utf-8"))


def fnum(s):
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def build_data() -> dict:
    abstract = load_json("abstract.json")
    fig = abstract["figures"]
    cis = load_json("cis.json")
    sectors = load_json("sectors.json")
    surv = load_json("survivorship.json")
    avg = load_json("average_path.json")
    roundtrip = load_json("roundtrip.json")
    tenure = load_json("tenure.json")
    regime = load_json("regime.json")
    comparables = load_json("comparables.json")

    # company names + fate keyed by ticker|removal_date
    company = {}
    with (PROC / "universe.csv").open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            company[f"{r['ticker']}|{r['removal_date']}"] = r["company"]

    # reason for removal, keyed by ticker|removal_date (raw scrape)
    reason = {}
    with (ROOT / "data" / "raw" / "removals.csv").open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            reason[f"{r['ticker']}|{r['removal_date']}"] = r["reason"]

    rt_per = roundtrip.get("per_id", {})
    sec_per = sectors.get("per_id", {})
    rg_per = regime.get("per_id", {})

    # ---- per-stock rows (all analyzed removals) ----
    stocks = []
    with (PROC / "results_per_stock.csv").open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            tk, rdate = r["ticker"], r["removal_date"]
            sid = f"{tk}-{rdate}"
            key = f"{tk}|{rdate}"
            rt = rt_per.get(sid, {})
            fate = FATE.get(rt.get("ultimate_fate", "unknown"), FATE["unknown"])
            tn = tenure.get(sid, {})
            rg = rg_per.get(sid, {})
            cmp = comparables.get(sid, {})
            row = {
                "id": sid,
                "ticker": tk,
                "company": company.get(key, ""),
                "reason": reason.get(key, ""),
                "removed": rdate,
                "firstDayOut": r["first_day_out"],
                "lastDay": r["last_day"],
                "baseClose": fnum(r["base_close"]),
                "trough": fnum(r["lowest_pct"]),
                "daysToLow": int(float(r["days_to_low"])),
                "dateOfLow": r["date_of_low"],
                "peak": fnum(r["highest_pct"]),
                "daysToHigh": int(float(r["days_to_high"])),
                "dateOfHigh": r["date_of_high"],
                "ret1y": fnum(r["one_year_pct"]),
                "qqq": fnum(r["qqq_same_window_pct"]),
                "excess": fnum(r["excess_vs_qqq_pct"]),
                "dataDays": int(float(r["data_days"])),
                "truncated": r["truncated"].strip().lower() == "true",
                "sector": sec_per.get(sid, {}).get("sector", ""),
                "fate": fate["label"],
                "fateTone": fate["tone"],
                "reAdded": bool(rt.get("re_added")),
                "readdDate": rt.get("readd_date"),
                "roundTripYears": rt.get("round_trip_years"),
                # tenure
                "yearsInIndex": tn.get("years_in_index"),
                "tenureCensored": bool(tn.get("tenure_censored")),
                "archetype": tn.get("archetype"),
                # market regime / context
                "regime": rg.get("market_regime"),
                "episode": rg.get("episode"),
                "qqqMaxDrawdown": rg.get("qqq_max_drawdown"),
                # comparables
                "comparableIds": cmp.get("comparable_ids", []),
                "comparableCriteria": cmp.get("criteria", ""),
            }
            # embed the daily series (indexed in the browser) for the deep-dive
            sf = PROC / "series" / f"{tk}_{rdate}.json"
            if sf.exists():
                s = json.loads(sf.read_text(encoding="utf-8"))
                if s.get("stock") and s.get("qqq"):
                    row["series"] = {
                        "dates": s["dates"],
                        "stock": s["stock"],
                        "qqq": s["qqq"],
                    }
            stocks.append(row)

    # ---- by-year cohorts (chronological) ----
    by_year = [
        {"year": y, "median": v["median"], "n": v["n"], "small": v.get("small", False)}
        for y, v in sorted(cis.get("by_year", {}).items())
    ]

    # ---- by-sector cohorts (best -> worst median) ----
    by_sector = []
    for name, v in sectors.get("by_sector", {}).items():
        oy = v["one_year"]
        by_sector.append({"name": name, "median": oy["median"], "n": v["n"],
                          "small": oy.get("small", False)})
    by_sector.sort(key=lambda s: s["median"], reverse=True)

    # ---- archetype cohorts (tenure) ----
    ARCH_LABEL = {
        "revolving_door": "Revolving door",
        "core_member": "Core member",
        "structural_decliner": "Structural decliner",
    }
    arch_counts = {}
    for v in tenure.values():
        a = v.get("archetype")
        arch_counts[a] = arch_counts.get(a, 0) + 1
    archetypes = []
    for key in ("revolving_door", "core_member", "structural_decliner"):
        ba = cis.get("by_archetype", {}).get(key, {})
        oy, ex = ba.get("one_year", {}), ba.get("excess", {})
        archetypes.append({
            "key": key,
            "label": ARCH_LABEL[key],
            "oneYear": oy,
            "excess": ex,
            "n": oy.get("n", arch_counts.get(key, 0)),
        })

    # ---- regime metadata for the table toggle ----
    rg_counts = {}
    for v in rg_per.values():
        rg_counts[v.get("market_regime")] = rg_counts.get(v.get("market_regime"), 0) + 1
    regime_meta = {"order": regime.get("order", []), "counts": rg_counts}

    # ---- survivorship-adjusted median scenarios ----
    oy = surv["one_year"]
    scenarios = [
        {"name": "Covered only",     "median": oy["survivors"],       "note": "survivors as-reported"},
        {"name": "Conservative",     "median": oy["conservative"],    "note": "imputed midpoint"},
        {"name": "Defensible best",  "median": oy["defensible_best"], "note": "anchor"},
        {"name": "Defensible worst", "median": oy["defensible_worst"],"note": "bias floor"},
    ]

    return {
        "abstract": " ".join(abstract["sentences"][:4]),
        "caveat": abstract["caveat"],
        "headline": {
            "covered": fig["funnel"]["analyzed"],
            "universe": fig["funnel"]["total"],
            "eligible": fig["funnel"]["eligible"],
            "coveragePct": fig["coverage_pct"],
            "medianReturn": fig["median_1y_pct"],
            "ci": fig["ci_1y"],
            "medianExcess": cis["overall"]["excess"]["median"],
            "medianTrough": fig["median_trough_pct"],
            "pctPositive": fig["pct_positive"],
            "beatQqq": fig["pct_beat_qqq"],
            "roundTrip": fig["round_trip_rate"],
            "gapYears": fig["median_gap_years"],
        },
        "scenarios": scenarios,
        "avgPath": {
            "offsets": avg["offsets"],
            "median": avg["all"]["raw"]["median"],
            "p25": avg["all"]["raw"]["p25"],
            "p75": avg["all"]["raw"]["p75"],
        },
        "byYear": by_year,
        "sectors": by_sector,
        "archetypes": archetypes,
        "regimeMeta": regime_meta,
        "stocks": stocks,
    }


# ---------------------------------------------------------------------------
# HTML template (Comet-branded). Injection points: /*__TOKENS__*/, /*__DATA__*/,
# data:image/svg favicon.
# ---------------------------------------------------------------------------
PAGE_CSS = r"""
  html, body { min-height: 100%; }
  body {
    background: var(--color-bg);
    background-image: var(--grad-aurora);
    background-attachment: fixed;
    /* QQQ per-app type personality: editorial research-paper */
    --font-display: 'Bricolage Grotesque', system-ui, sans-serif;
    --font-sans: 'Hanken Grotesk', system-ui, sans-serif;
  }
  .num { font-family: var(--font-mono); font-variant-numeric: tabular-nums; letter-spacing: -0.01em; }
  .wrap { max-width: 1180px; margin: 0 auto; padding: 0 22px; }

  /* sticky nav */
  .topnav {
    position: sticky; top: 0; z-index: 40;
    background: color-mix(in srgb, var(--surface-card) 88%, transparent);
    backdrop-filter: blur(var(--blur-md));
    border-bottom: 1px solid var(--border);
  }
  .topnav .bar { height: 58px; display: flex; align-items: center; justify-content: space-between; }
  .brand { display: flex; align-items: center; gap: 11px; }
  .brand img { width: 28px; height: 28px; border-radius: 7px; }
  .brand .t { font-family: var(--font-display); font-size: var(--fs-md); font-weight: 700; color: var(--text-heading); line-height: 1.1; }
  .brand .s { font-size: var(--fs-2xs); color: var(--text-muted); }
  .navlink { display: inline-flex; align-items: center; gap: 6px; font-size: var(--fs-sm); color: var(--text-secondary); font-weight: 600; }
  .navlink:hover { color: var(--text-body); }

  main { padding: 24px 0 64px; animation: comet-fade-up var(--dur-slow) var(--ease-out); }

  /* card */
  .card { background: var(--surface-card); border: 1px solid var(--border); border-radius: var(--radius-md); box-shadow: var(--shadow-md); padding: var(--card-pad); }
  .card.glow { box-shadow: var(--shadow-md), var(--glow-violet); }
  .card + .card, .stack > * + * { margin-top: 20px; }
  .card-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; padding-bottom: 12px; margin-bottom: 14px; border-bottom: 1px solid var(--border-soft); }
  .card-head.flush { border: 0; padding: 0; margin-bottom: 12px; }
  .card-title { font-family: var(--font-display); font-size: var(--fs-md); font-weight: 600; color: var(--text-heading); }
  .card-sub { font-size: var(--fs-xs); color: var(--text-muted); margin-top: 2px; }
  .eyebrow { font-size: var(--fs-xs); font-weight: 700; letter-spacing: var(--ls-wide); text-transform: uppercase; color: var(--accent); }
  .lede { font-size: var(--fs-md); line-height: 1.65; color: var(--text-body); text-wrap: pretty; }

  /* stat grid */
  .statgrid { display: grid; grid-template-columns: repeat(auto-fit, minmax(168px, 1fr)); gap: 14px; }
  .stat { position: relative; background: var(--surface-card); border: 1px solid var(--border); border-left: 3px solid var(--border-strong); border-radius: var(--radius-md); box-shadow: var(--shadow-sm); padding: 14px 16px; }
  .stat.pos { border-left-color: var(--positive); }
  .stat.neg { border-left-color: var(--negative); }
  .stat.warn { border-left-color: var(--warning); }
  .stat.accent { border-left-color: var(--accent); }
  .stat.neutral { border-left-color: var(--text-muted); }
  .stat .label { display: flex; align-items: center; gap: 6px; font-size: var(--fs-2xs); text-transform: uppercase; letter-spacing: var(--ls-wide); color: var(--text-secondary); font-weight: 600; }
  .stat .value { margin-top: 8px; font-family: var(--font-mono); font-variant-numeric: tabular-nums; font-size: var(--fs-2xl); font-weight: 600; color: var(--text-heading); line-height: 1.05; letter-spacing: -0.02em; }
  .stat .sub { margin-top: 4px; font-size: var(--fs-2xs); color: var(--text-muted); }
  .stat .value.pos { color: var(--positive); }
  .stat .value.neg { color: var(--negative); }
  .stat .value.warn { color: var(--warning); }
  .stat .value.accent { color: var(--accent); }

  /* warning strip */
  .warn-strip { display: flex; align-items: flex-start; gap: 10px; padding: 12px 16px; background: var(--warning-soft); border: 1px solid color-mix(in srgb, var(--warning) 35%, transparent); border-radius: var(--radius); }
  .warn-strip .i { color: var(--warning); flex-shrink: 0; margin-top: 1px; }
  .warn-strip b { color: var(--warning); }
  .warn-strip .body { font-size: var(--fs-sm); color: var(--text-body); line-height: 1.55; }

  /* scenarios */
  .scenrow { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 12px; }
  .scen { flex: 1 1 150px; background: var(--surface-elevated); border: 1px solid var(--border-soft); border-radius: var(--radius); padding: 10px 12px; }
  .scen .k { font-size: var(--fs-2xs); text-transform: uppercase; letter-spacing: var(--ls-wide); color: var(--text-secondary); font-weight: 600; }
  .scen .v { font-family: var(--font-mono); font-variant-numeric: tabular-nums; font-size: var(--fs-lg); font-weight: 600; margin-top: 4px; }
  .scen .n { font-size: var(--fs-2xs); color: var(--text-muted); margin-top: 2px; }

  /* two-col grid */
  .cols { display: grid; grid-template-columns: repeat(auto-fit, minmax(330px, 1fr)); gap: 16px; }
  .cols.cohorts { align-items: start; }
  /* cards in a grid are siblings → the global ".card + .card" top margin would
     push the 2nd card (By sector) down 20px; cancel it so both align at the top */
  .cols .card + .card { margin-top: 0; }
  .cols.cohorts .card-sub { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .cohort-body { overflow: hidden; min-height: 0; }

  /* footer */
  footer.foot { border-top: 1px solid var(--border-soft); margin-top: 8px; padding: 24px 0 8px; }
  footer.foot p { font-size: var(--fs-xs); color: var(--text-muted); line-height: 1.7; max-width: 80ch; }
  footer.foot a { color: var(--text-secondary); }

  /* legend */
  .legend { display: flex; gap: 14px; font-size: var(--fs-xs); align-items: center; flex-wrap: wrap; }
  .legend span { display: inline-flex; align-items: center; gap: 6px; color: var(--text-secondary); }
  .swatch { width: 14px; height: 3px; border-radius: 2px; display: inline-block; }
  .swatch.band { height: 11px; border-radius: 3px; }

  /* cohort diverging bars */
  .cohort { display: flex; align-items: center; gap: 10px; }
  .cohort + .cohort { margin-top: 9px; }
  .cohort .lab { width: 96px; font-size: var(--fs-xs); color: var(--text-body); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .cohort .lab.yr { width: 42px; font-family: var(--font-mono); color: var(--text-secondary); }
  .cohort .track { flex: 1; position: relative; height: 18px; }
  .cohort .axis { position: absolute; left: 50%; top: 0; bottom: 0; width: 1px; background: var(--border); }
  .cohort .fill { position: absolute; top: 3px; height: 12px; border-radius: 2px; }
  .cohort .val { width: 58px; text-align: right; font-family: var(--font-mono); font-variant-numeric: tabular-nums; font-size: var(--fs-xs); }
  .cohort .cnt { width: 30px; text-align: right; font-family: var(--font-mono); font-size: var(--fs-2xs); color: var(--text-muted); }
  .pos { color: var(--positive); } .neg { color: var(--negative); }
  .bg-pos { background: var(--positive); } .bg-neg { background: var(--negative); }
  .dim { opacity: 0.5; }

  /* badge */
  .badge { display: inline-flex; align-items: center; font-family: var(--font-sans); font-size: var(--fs-2xs); font-weight: 600; padding: 2px 9px; border-radius: var(--radius-pill); border: 1px solid transparent; letter-spacing: 0.01em; }
  .badge.neutral { background: var(--surface-active); color: var(--text-secondary); border-color: var(--border); }
  .badge.accent { background: var(--accent-soft); color: var(--accent-hover); border-color: var(--accent-line); }
  .badge.positive { background: var(--positive-soft); color: var(--positive); }
  .badge.negative { background: var(--negative-soft); color: var(--negative); }

  /* table */
  .tablecard { padding: 0; overflow: hidden; }
  .table-top { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 16px var(--card-pad); border-bottom: 1px solid var(--border-soft); }
  .search { display: flex; align-items: center; gap: 8px; background: var(--surface-inset); border: 1px solid var(--border); border-radius: var(--radius); padding: 0 10px; height: 32px; }
  .search input { background: transparent; border: 0; outline: 0; color: var(--text-body); font-family: var(--font-sans); font-size: var(--fs-sm); width: 180px; }
  .search input::placeholder { color: var(--text-muted); }
  .scroll { max-height: 560px; overflow: auto; }
  table.dt { width: 100%; border-collapse: collapse; font-size: var(--fs-sm); }
  table.dt thead th { position: sticky; top: 0; z-index: 1; background: var(--surface-elevated); color: var(--text-secondary); font-weight: 600; font-size: var(--fs-2xs); text-transform: uppercase; letter-spacing: var(--ls-wide); text-align: left; padding: 10px 14px; border-bottom: 1px solid var(--border); cursor: pointer; white-space: nowrap; user-select: none; }
  table.dt thead th.r { text-align: right; }
  table.dt thead th.c { text-align: center; }
  table.dt thead th:hover { color: var(--text-body); }
  table.dt tbody td { padding: 10px 14px; border-bottom: 1px solid var(--border-soft); white-space: nowrap; }
  table.dt tbody tr { cursor: pointer; transition: background var(--dur-fast) var(--ease-out); }
  table.dt tbody tr:hover { background: var(--surface-hover); }
  table.dt td.r { text-align: right; }
  table.dt td.c { text-align: center; }
  .tk { font-family: var(--font-mono); font-weight: 700; color: var(--text-heading); }
  .co { color: var(--text-muted); }
  td .num { font-size: var(--fs-sm); }

  /* mini panels + distribution/timing/tenure */
  .mini-t { font-size: var(--fs-sm); font-weight: 600; color: var(--text-body); margin-bottom: 8px; }
  .mini-t .cap { font-weight: 400; color: var(--text-muted); font-size: var(--fs-2xs); }
  .quadgrid { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 18px; }
  .chartbox.sm { height: 180px; }
  .cap { font-size: var(--fs-2xs); color: var(--text-muted); }

  /* archetype cohort blocks */
  .archwrap { display: flex; flex-direction: column; gap: 12px; }
  .arch { background: var(--surface-elevated); border: 1px solid var(--border-soft); border-radius: var(--radius); padding: 12px 14px; }
  .arch-h { display: flex; align-items: baseline; justify-content: space-between; margin-bottom: 8px; }
  .arch-name { font-weight: 600; color: var(--text-heading); }
  .arch-row { display: grid; grid-template-columns: 56px 70px 1fr; align-items: baseline; gap: 8px; font-size: var(--fs-sm); padding: 2px 0; }
  .arch-k { font-size: var(--fs-2xs); text-transform: uppercase; letter-spacing: var(--ls-wide); color: var(--text-secondary); }
  .arch-row .ci { color: var(--text-muted); font-size: var(--fs-xs); text-align: right; }

  /* filter bar */
  .filters { display: flex; align-items: center; gap: 14px; flex-wrap: wrap; }
  .fgroup { display: flex; align-items: center; gap: 8px; }
  .fgroup > .lbl { font-size: var(--fs-2xs); text-transform: uppercase; letter-spacing: var(--ls-wide); color: var(--text-secondary); font-weight: 600; }

  /* toggle switch */
  .switch { display: inline-flex; align-items: center; gap: 8px; cursor: pointer; font-size: var(--fs-sm); color: var(--text-body); user-select: none; }
  .switch input { position: absolute; opacity: 0; pointer-events: none; }
  .switch .track { width: 36px; height: 20px; border-radius: var(--radius-pill); background: var(--surface-active); border: 1px solid var(--border); position: relative; transition: background var(--dur) var(--ease-out); }
  .switch .thumb { position: absolute; top: 2px; left: 2px; width: 14px; height: 14px; border-radius: 50%; background: var(--text-secondary); transition: transform var(--dur) var(--ease-spring), background var(--dur) var(--ease-out); }
  .switch input:checked + .track { background: var(--accent-soft); border-color: var(--accent-line); }
  .switch input:checked + .track .thumb { transform: translateX(16px); background: var(--accent); }

  /* year range slider */
  .range { display: flex; align-items: center; gap: 10px; }
  .range .rr { position: relative; width: 168px; height: 20px; }
  .range input[type=range] { position: absolute; left: 0; top: 0; width: 100%; margin: 0; background: transparent; -webkit-appearance: none; appearance: none; pointer-events: none; height: 20px; }
  .range input[type=range]::-webkit-slider-runnable-track { height: 4px; background: transparent; }
  .range input[type=range]::-webkit-slider-thumb { -webkit-appearance: none; appearance: none; pointer-events: auto; width: 14px; height: 14px; border-radius: 50%; background: var(--accent); border: 2px solid var(--color-bg); margin-top: -5px; cursor: pointer; box-shadow: var(--shadow-sm); }
  .range input[type=range]::-moz-range-thumb { pointer-events: auto; width: 14px; height: 14px; border-radius: 50%; background: var(--accent); border: 2px solid var(--color-bg); cursor: pointer; }
  .range .rail { position: absolute; left: 0; right: 0; top: 8px; height: 4px; border-radius: 2px; background: var(--surface-active); }
  .range .sel { position: absolute; top: 8px; height: 4px; border-radius: 2px; background: var(--accent); }
  .range .yr-lab { font-family: var(--font-mono); font-variant-numeric: tabular-nums; font-size: var(--fs-xs); color: var(--text-secondary); min-width: 96px; }

  /* regime 5-way toggle */
  .regime-toggle { display: inline-flex; background: var(--surface-inset); border: 1px solid var(--border); border-radius: var(--radius-pill); padding: 3px; gap: 2px; }
  .regime-toggle button { width: 34px; height: 28px; border: 0; background: transparent; border-radius: var(--radius-pill); cursor: pointer; font-size: 15px; line-height: 1; display: inline-flex; align-items: center; justify-content: center; filter: grayscale(0.4) opacity(0.7); transition: all var(--dur-fast) var(--ease-out); }
  .regime-toggle button:hover { background: var(--surface-hover); filter: none; }
  .regime-toggle button.on { background: var(--accent); filter: none; box-shadow: var(--shadow-sm); }
  .regime-toggle button:disabled { opacity: 0.28; cursor: not-allowed; filter: grayscale(1); }
  .regime-toggle button .blank { width: 12px; height: 12px; border-radius: 50%; border: 1.5px solid var(--text-secondary); }
  .regime-toggle button.on .blank { border-color: var(--accent-contrast); }

  /* market context + comparables */
  .ctx-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 12px; margin-bottom: 12px; }
  .ctx { background: var(--surface-elevated); border: 1px solid var(--border-soft); border-radius: var(--radius); padding: 10px 12px; }
  .ctx .k { font-size: var(--fs-2xs); text-transform: uppercase; letter-spacing: var(--ls-wide); color: var(--text-secondary); font-weight: 600; }
  .ctx .v { font-family: var(--font-mono); font-variant-numeric: tabular-nums; font-size: var(--fs-lg); font-weight: 600; margin-top: 4px; }
  .decomp { font-size: var(--fs-sm); color: var(--text-body); line-height: 1.6; }
  .meta-block { display: flex; flex-wrap: wrap; gap: 8px 16px; font-size: var(--fs-sm); color: var(--text-secondary); margin: 6px 0 16px; }
  .meta-block .mk { color: var(--text-muted); }
  .reason { font-style: italic; color: var(--text-secondary); }

  /* deep-dive overlay */
  .overlay { position: fixed; inset: 0; z-index: 80; display: none; }
  .overlay.open { display: block; }
  .scrim { position: absolute; inset: 0; background: rgba(8, 5, 14, 0.58); backdrop-filter: blur(var(--blur-sm)); animation: comet-fade-up var(--dur) var(--ease-out); }
  .sheet { position: absolute; inset: 0; overflow: auto; }
  .sheet-inner { max-width: 1080px; margin: 0 auto; padding: 22px; animation: comet-fade-up var(--dur-slow) var(--ease-out); }
  .dd-top { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 18px; }
  .btn { display: inline-flex; align-items: center; gap: 7px; height: 36px; padding: 0 14px; border-radius: var(--radius); border: 1px solid var(--border); background: var(--surface-card); color: var(--text-body); font-family: var(--font-sans); font-size: var(--fs-sm); font-weight: 600; cursor: pointer; transition: all var(--dur-fast) var(--ease-out); }
  .btn:hover { background: var(--surface-hover); border-color: var(--accent-line); }
  .dd-id { display: flex; align-items: baseline; gap: 10px; flex-wrap: wrap; }
  .dd-id h1 { font-family: var(--font-display); font-size: var(--fs-2xl); }
  .dd-id .meta { font-size: var(--fs-sm); color: var(--text-secondary); }
  .dd-badges { display: flex; gap: 8px; }
  .chartbox { position: relative; height: 280px; }
  .chartbox.tall { height: 320px; }
  .commentary { font-size: var(--fs-md); line-height: 1.7; color: var(--text-body); max-width: 80ch; }
  .nodata { font-size: var(--fs-sm); color: var(--text-muted); padding: 24px; text-align: center; }
  .tl { width: 100%; border-collapse: collapse; font-size: var(--fs-sm); }
  .tl th, .tl td { padding: 9px 12px; border-bottom: 1px solid var(--border-soft); text-align: right; }
  .tl th:first-child, .tl td:first-child { text-align: left; }
  .tl thead th { color: var(--text-secondary); font-size: var(--fs-2xs); text-transform: uppercase; letter-spacing: var(--ls-wide); }
  .tl td.lbl { color: var(--text-body); }
  @media (max-width: 640px) { .wrap, .sheet-inner { padding-left: 14px; padding-right: 14px; } }
"""

PAGE_JS = r"""
const $ = (s, r=document) => r.querySelector(s);
const el = (t, c, h) => { const n = document.createElement(t); if (c) n.className = c; if (h != null) n.innerHTML = h; return n; };
const BY_ID = Object.fromEntries(DATA.stocks.map(s => [s.id, s]));
const MINUS = '−';
const fmt = (v, signed=true, dp=1) => {
  if (v == null || isNaN(v)) return '—';
  const s = v.toFixed(dp);
  if (v < 0) return MINUS + s.slice(1) + '%';
  return (signed ? '+' : '') + s + '%';
};
const toneOf = (v) => v >= 0 ? 'pos' : 'neg';

// Literal brand colors (getComputedStyle does NOT resolve nested var() for
// custom properties, so canvas strokes must use concrete values).
const COLORS = {
  accent: '#a382f7', accentSoft: 'rgba(139,92,246,0.16)', accentStrong: '#8b5cf6',
  muted: '#756a8c', secondary: '#a89ec0', heading: '#f2edf8',
  positive: '#46cf83', negative: '#ff5d6c', warning: '#f0ab3e', info: '#5cc8ff', glow: '#ff9d6b',
  border: '#322a42', borderSoft: '#271f34', surfaceEl: '#241d30',
  series: ['#a382f7','#ff9d6b','#5cc8ff','#46cf83','#f0ab3e','#f070c4','#7c84ff','#45d6c4'],
};

// ---- Chart.js global theme ----
function themeCharts() {
  if (!window.Chart) return;
  Chart.defaults.color = COLORS.muted;
  Chart.defaults.font.family = "'JetBrains Mono', ui-monospace, monospace";
  Chart.defaults.font.size = 11;
  Chart.defaults.borderColor = COLORS.borderSoft;
  // register the zoom/pan plugin once (CDN exposes it under a few names)
  try { if (!Chart.registry.plugins.get('zoom')) {
    const z = window.ChartZoom || window.chartjsPluginZoom || window['chartjs-plugin-zoom'] || window.Zoom;
    if (z) Chart.register(z);
  } } catch (e) {}
}
// wheel zoom + pinch + drag-pan, clamped to the original view; double-click resets.
function zoomCfg(mode) {
  const lim = {};
  if (mode !== 'y') lim.x = { min: 'original', max: 'original' };
  if (mode !== 'x') lim.y = { min: 'original', max: 'original' };
  return {
    zoom: { wheel: { enabled: true, speed: 0.1 }, pinch: { enabled: true }, drag: { enabled: false }, mode },
    pan: { enabled: true, mode, threshold: 8 },
    limits: lim,
  };
}
function gridOpts() {
  return {
    grid: { color: COLORS.borderSoft, drawTicks: false },
    border: { color: COLORS.border },
    ticks: { color: COLORS.muted },
  };
}
function tooltipStyle(callbacks, filter) {
  return {
    backgroundColor: COLORS.surfaceEl, borderColor: COLORS.border, borderWidth: 1,
    titleColor: COLORS.secondary, bodyColor: '#d7cfe6', padding: 10, cornerRadius: 8,
    displayColors: false,
    callbacks: callbacks || {},
    filter: filter || (() => true),
  };
}

// ============================ OVERVIEW ============================
function renderOverview() {
  const root = $('#overview');
  const h = DATA.headline;

  // abstract
  const ab = el('div', 'card glow');
  ab.append(el('div', null, '<div class="eyebrow"><i data-lucide="sparkles"></i> Executive abstract</div>'));
  const p = el('p', 'lede', DATA.abstract); p.style.marginTop = '10px';
  ab.append(p);
  root.append(ab);

  // stat grid
  const sg = el('div', 'statgrid'); sg.style.marginTop = '20px';
  const stat = (cls, label, value, vcls, sub) => {
    const s = el('div', 'stat ' + cls);
    s.innerHTML = `<div class="label">${label}</div><div class="value ${vcls||''}">${value}</div>` + (sub ? `<div class="sub">${sub}</div>` : '');
    return s;
  };
  sg.append(stat('neutral', '<i data-lucide="layers"></i> Coverage', `${h.covered} / ${h.universe}`, '', `${h.coveragePct}% of ${h.eligible} eligible`));
  sg.append(stat('pos', 'Median 1Y return', fmt(h.medianReturn), 'pos', `95% CI ${fmt(h.ci[0])} … ${fmt(h.ci[1])}`));
  sg.append(stat('accent', 'Median excess vs QQQ', fmt(h.medianExcess), 'accent', 'same-window benchmark'));
  sg.append(stat('warn', 'Median trough', fmt(h.medianTrough), 'warn', 'vs first close out'));
  sg.append(stat('neutral', 'Positive at 1Y', `${h.pctPositive}%`, '', 'of full-year names'));
  sg.append(stat('accent', 'Beat QQQ', `${h.beatQqq}%`, 'accent', `${h.roundTrip}% later re-added`));
  root.append(sg);

  // survivorship strip + scenarios
  const strip = el('div', 'card'); strip.style.marginTop = '20px';
  const w = el('div', 'warn-strip');
  w.innerHTML = `<i class="i" data-lucide="alert-triangle"></i><div class="body"><b>Survivorship bias.</b> Delisted and unresolved names are under-represented by the data source — and were disproportionately the worst performers. Every figure here is an upper bound. Adjusting for the missing names pulls the median 1-year return across this range:</div>`;
  strip.append(w);
  const sr = el('div', 'scenrow');
  DATA.scenarios.forEach(s => {
    const c = el('div', 'scen');
    c.innerHTML = `<div class="k">${s.name}</div><div class="v ${toneOf(s.median)}">${fmt(s.median)}</div><div class="n">${s.note}</div>`;
    sr.append(c);
  });
  strip.append(sr);
  root.append(strip);

  // average path chart
  const apc = el('div', 'card'); apc.style.marginTop = '20px';
  apc.innerHTML = `<div class="card-head"><div><div class="card-title">Average path — first 252 trading days out</div><div class="card-sub">Offset-aligned median of the indexed price, base 100 at removal · shaded IQR (25th–75th pct)</div></div>
    <div class="legend"><span><i class="swatch" style="background:var(--accent)"></i>Median</span><span><i class="swatch band" style="background:var(--accent-soft)"></i>IQR</span><span><i class="swatch" style="background:var(--text-muted)"></i>Base 100</span></div></div>
    <div class="chartbox"><canvas id="apChart"></canvas></div>`;
  root.append(apc);

  // cohorts
  const cols = el('div', 'cols cohorts'); cols.style.marginTop = '20px';
  const yearCard = cohortCard('By removal year', 'Median 1Y return per cohort · scroll for all years', DATA.byYear.map(c => ({ lab: c.year, yr: true, median: c.median, n: c.n, small: c.small })));
  const sectorCard = cohortCard('By sector', 'Median 1Y return (groups with n≥5 solid)', DATA.sectors.map(s => ({ lab: s.name, yr: false, median: s.median, n: s.n, small: s.small })));
  cols.append(yearCard, sectorCard);
  root.append(cols);
  // Cohort rows are fixed-height (18px track + 9px gap), so the by-sector body
  // height is deterministic — no DOM/font measurement. Pin BOTH bodies to it:
  // by-sector fits exactly (no blank space), by-year (20 rows) scrolls. Headers
  // are identical markup with single-line subtitles, so both cards match exactly.
  const ROW_H = 18, ROW_GAP = 9;
  const bodyH = DATA.sectors.length * ROW_H + (DATA.sectors.length - 1) * ROW_GAP;
  [sectorCard, yearCard].forEach(card => {
    const b = card.querySelector('.cohort-body');
    b.style.height = bodyH + 'px';
    b.style.overflowY = 'auto';
    b.style.paddingRight = '6px';
  });

  // outcome distributions + timing + tenure
  root.append(distributionsCard());
  root.append(timingCard());
  root.append(tenureCard());

  // table
  root.append(removalsTable());

  drawAvgPath();
  drawDistributions();
  drawTiming();
  drawTenure();
  window.lucide && lucide.createIcons();
}

// ---- shared chart helpers ----
function median(arr) {
  const a = arr.filter(v => v != null && !isNaN(v)).sort((x, y) => x - y);
  if (!a.length) return null;
  const m = Math.floor(a.length / 2);
  return a.length % 2 ? a[m] : (a[m - 1] + a[m]) / 2;
}
function histogram(vals, nbins) {
  const a = vals.filter(v => v != null && !isNaN(v));
  const lo = Math.min(...a), hi = Math.max(...a);
  const w = (hi - lo) / nbins || 1;
  const counts = new Array(nbins).fill(0);
  a.forEach(v => { let i = Math.floor((v - lo) / w); if (i >= nbins) i = nbins - 1; if (i < 0) i = 0; counts[i]++; });
  const mids = counts.map((_, i) => lo + w * (i + 0.5));
  return { counts, mids, lo, hi, w, med: median(a) };
}
// dashed median marker drawn over a histogram (category x-axis → position by data range)
const medianLine = {
  id: 'medianLine',
  afterDraw(chart, args, opts) {
    if (opts.value == null || opts.hi == null) return;
    const { ctx, chartArea: { top, bottom, left, right } } = chart;
    const span = opts.hi - opts.lo || 1;
    const frac = Math.max(0, Math.min(1, (opts.value - opts.lo) / span));
    const px = left + frac * (right - left);
    ctx.save();
    ctx.strokeStyle = COLORS.glow;
    ctx.setLineDash([4, 4]); ctx.lineWidth = 1.5;
    ctx.beginPath(); ctx.moveTo(px, top); ctx.lineTo(px, bottom); ctx.stroke();
    ctx.setLineDash([]);
    ctx.fillStyle = COLORS.glow; ctx.font = "600 10px 'JetBrains Mono', monospace";
    ctx.textAlign = frac > 0.5 ? 'right' : 'left';
    ctx.fillText('median ' + opts.label, px + (ctx.textAlign === 'right' ? -6 : 6), top + 11);
    ctx.restore();
  },
};

function distributionsCard() {
  const card = el('div', 'card'); card.style.marginTop = '20px';
  card.innerHTML = `<div class="card-head flush"><div><div class="card-title">Outcome distributions</div>
    <div class="card-sub">How the 126 removals spread across each metric · coral line marks the median</div></div></div>
    <div class="quadgrid">
      <div class="mini"><div class="mini-t">Trough depth</div><div class="chartbox sm"><canvas id="hTrough"></canvas></div></div>
      <div class="mini"><div class="mini-t">Trading days to trough</div><div class="chartbox sm"><canvas id="hDays"></canvas></div></div>
      <div class="mini"><div class="mini-t">Return at window end</div><div class="chartbox sm"><canvas id="hRet"></canvas></div></div>
      <div class="mini"><div class="mini-t">Excess vs QQQ</div><div class="chartbox sm"><canvas id="hExc"></canvas></div></div>
    </div>`;
  return card;
}

function timingCard() {
  const card = el('div', 'card'); card.style.marginTop = '20px';
  card.innerHTML = `<div class="card-head flush"><div><div class="card-title">Timing</div>
    <div class="card-sub">When the extreme happened vs how deep/high it went · each dot is one removal</div></div></div>
    <div class="cols">
      <div class="mini"><div class="mini-t">Days to trough vs depth</div><div class="chartbox"><canvas id="scLow"></canvas></div></div>
      <div class="mini"><div class="mini-t">Days to peak vs height</div><div class="chartbox"><canvas id="scHigh"></canvas></div></div>
    </div>`;
  return card;
}

function tenureCard() {
  const card = el('div', 'card'); card.style.marginTop = '20px';
  let bars = '';
  DATA.archetypes.forEach(a => {
    const oy = a.oneYear, ex = a.excess, small = oy.small;
    bars += `<div class="arch${small ? ' dim' : ''}">
      <div class="arch-h"><span class="arch-name">${a.label}</span><span class="cnt">n${a.n}</span></div>
      <div class="arch-row"><span class="arch-k">1Y</span><span class="num ${toneOf(oy.median)}">${fmt(oy.median)}</span><span class="ci num">[${fmt(oy.lo)}, ${fmt(oy.hi)}]</span></div>
      <div class="arch-row"><span class="arch-k">vs QQQ</span><span class="num ${toneOf(ex.median)}">${fmt(ex.median)}</span><span class="ci num">[${fmt(ex.lo)}, ${fmt(ex.hi)}]</span></div>
    </div>`;
  });
  card.innerHTML = `<div class="card-head flush"><div><div class="card-title">Tenure</div>
    <div class="card-sub">How long the name spent in the index before removal · revolving-door &lt;4y · core 4–10y · structural &gt;10y</div></div></div>
    <div class="cols">
      <div class="mini"><div class="mini-t">Median outcome by archetype <span class="cap">(95% CI)</span></div><div class="archwrap">${bars}</div></div>
      <div class="mini"><div class="mini-t">Years in index vs return <span class="cap">(hollow = censored tenure)</span></div><div class="chartbox"><canvas id="scTenure"></canvas></div></div>
    </div>`;
  return card;
}

function drawDistributions() {
  const defs = [
    { id: 'hTrough', vals: DATA.stocks.map(s => s.trough), bins: 22, signed: true },
    { id: 'hDays', vals: DATA.stocks.map(s => s.daysToLow), bins: 20, signed: false },
    { id: 'hRet', vals: DATA.stocks.map(s => s.ret1y), bins: 24, signed: true },
    { id: 'hExc', vals: DATA.stocks.map(s => s.excess), bins: 24, signed: true },
  ];
  defs.forEach(d => {
    const ctx = document.getElementById(d.id); if (!ctx) return;
    const h = histogram(d.vals, d.bins);
    const c = new Chart(ctx, {
      type: 'bar',
      data: {
        labels: h.mids.map(m => m.toFixed(0)),
        datasets: [{ data: h.counts, backgroundColor: COLORS.accentSoft, borderColor: COLORS.accent, borderWidth: 1, borderRadius: 2, barPercentage: 1, categoryPercentage: 1 }],
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          zoom: zoomCfg('xy'),
          medianLine: { value: h.med, lo: h.lo, hi: h.hi, label: (d.signed ? fmt(h.med) : h.med.toFixed(0)) },
          tooltip: tooltipStyle({ title: (it) => (d.signed ? fmt(parseFloat(it[0].label)) : it[0].label), label: (it) => `${it.parsed.y} removals` }),
        },
        scales: {
          x: { ...gridOpts(), grid: { display: false }, ticks: { color: COLORS.muted, maxTicksLimit: 6 } },
          y: { ...gridOpts(), ticks: { color: COLORS.muted, precision: 0 }, beginAtZero: true },
        },
      },
      plugins: [medianLine],
    });
    OV_CHARTS.push(c);
  });
}

function scatterChart(id, pts, xt, yt) {
  const ctx = document.getElementById(id); if (!ctx) return;
  const c = new Chart(ctx, {
    type: 'scatter',
    data: { datasets: [{ data: pts, backgroundColor: 'rgba(163,130,247,0.5)', borderColor: COLORS.accent, borderWidth: 1, radius: 3.5, hoverRadius: 6 }] },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        zoom: zoomCfg('xy'),
        tooltip: tooltipStyle({ label: (it) => `${it.raw.t} (${it.raw.d}): day ${it.parsed.x}, ${fmt(it.parsed.y)}` }),
      },
      scales: {
        x: { ...gridOpts(), title: { display: true, text: xt, color: COLORS.muted }, ticks: { color: COLORS.muted } },
        y: { ...gridOpts(), title: { display: true, text: yt, color: COLORS.muted }, ticks: { color: COLORS.muted } },
      },
    },
  });
  OV_CHARTS.push(c);
}

function drawTiming() {
  scatterChart('scLow', DATA.stocks.map(s => ({ x: s.daysToLow, y: s.trough, t: s.ticker, d: s.removed })), 'Trading days to trough', 'Trough depth %');
  scatterChart('scHigh', DATA.stocks.map(s => ({ x: s.daysToHigh, y: s.peak, t: s.ticker, d: s.removed })), 'Trading days to peak', 'Peak height %');
}

const ARCH_COLOR = { revolving_door: '#5cc8ff', core_member: '#a382f7', structural_decliner: '#ff9d6b' };
function drawTenure() {
  const ctx = document.getElementById('scTenure'); if (!ctx) return;
  const groups = {};
  DATA.stocks.forEach(s => {
    if (s.yearsInIndex == null || s.ret1y == null) return;
    (groups[s.archetype] = groups[s.archetype] || []).push({ x: s.yearsInIndex, y: s.ret1y, t: s.ticker, d: s.removed, c: s.tenureCensored });
  });
  const ds = Object.keys(groups).map(k => ({
    label: k,
    data: groups[k],
    backgroundColor: groups[k].map(p => p.c ? 'transparent' : ARCH_COLOR[k]),
    borderColor: ARCH_COLOR[k], borderWidth: 1.5, radius: 4, hoverRadius: 6,
  }));
  const c = new Chart(ctx, {
    type: 'scatter',
    data: { datasets: ds },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        zoom: zoomCfg('xy'),
        tooltip: tooltipStyle({ label: (it) => `${it.raw.t}: ${it.parsed.x.toFixed(1)}y in index, ${fmt(it.parsed.y)}` }),
      },
      scales: {
        x: { ...gridOpts(), title: { display: true, text: 'Years in index', color: COLORS.muted }, ticks: { color: COLORS.muted }, beginAtZero: true },
        y: { ...gridOpts(), title: { display: true, text: 'Return at window end %', color: COLORS.muted }, ticks: { color: COLORS.muted } },
      },
    },
  });
  OV_CHARTS.push(c);
}

function cohortCard(title, sub, rows) {
  const card = el('div', 'card');
  card.innerHTML = `<div class="card-head flush"><div><div class="card-title">${title}</div><div class="card-sub">${sub}</div></div></div>`;
  const max = Math.max(...rows.map(r => Math.abs(r.median)), 1);
  const body = el('div', 'cohort-body');
  rows.forEach(r => {
    const pos = r.median >= 0;
    const wpct = Math.abs(r.median) / max * 48;
    const row = el('div', 'cohort' + (r.small ? ' dim' : ''));
    row.innerHTML =
      `<div class="lab ${r.yr ? 'yr' : ''}" title="${r.lab}">${r.lab}</div>` +
      `<div class="track"><div class="axis"></div><div class="fill ${pos ? 'bg-pos' : 'bg-neg'}" style="width:${wpct}%;${pos ? 'left:50%' : 'right:50%'}"></div></div>` +
      `<div class="val ${pos ? 'pos' : 'neg'}">${fmt(r.median)}</div>` +
      `<div class="cnt">n${r.n}</div>`;
    body.append(row);
  });
  card.append(body);
  return card;
}

let SORT = { key: 'removed', dir: -1 };
const YEARS = DATA.stocks.map(s => +s.removed.slice(0, 4));
const Y_MIN = Math.min(...YEARS), Y_MAX = Math.max(...YEARS);
const FILTER = { q: '', yMin: Y_MIN, yMax: Y_MAX, truncatedHidden: false, regime: 'all' };
// 5-stop regime toggle — ⚪ all is dead-center & default; 🐂 = bull OR strong_bull; 🐻 disabled (n=0)
const REGIMES = [
  { key: 'crash', emoji: '💥', label: 'Crash' },
  { key: 'bear', emoji: '🐻', label: 'Bear' },
  { key: 'all', emoji: '', label: 'All regimes', blank: true },
  { key: 'flat', emoji: '➖', label: 'Flat' },
  { key: 'bull', emoji: '🐂', label: 'Bull / strong bull' },
];

function removalsTable() {
  const card = el('div', 'card tablecard'); card.style.marginTop = '20px';
  card.innerHTML = `<div class="table-top" style="flex-direction:column;align-items:stretch;gap:14px">
      <div style="display:flex;align-items:center;justify-content:space-between;gap:12px">
        <div><div class="card-title">Removals</div><div class="card-sub">Click a row for the per-stock deep-dive</div></div>
        <span class="badge neutral" id="rowcount"></span>
      </div>
      <div class="filters">
        <div class="search"><i data-lucide="search" style="width:14px;height:14px;color:var(--text-muted)"></i><input id="q" placeholder="Filter ticker / sector…"></div>
        <label class="switch"><input type="checkbox" id="fTrunc"><span class="track"><span class="thumb"></span></span> Hide truncated rows</label>
        <div class="fgroup"><span class="lbl">Years</span>
          <div class="range"><div class="rr"><div class="rail"></div><div class="sel" id="ySel"></div>
            <input type="range" id="yLo" min="${Y_MIN}" max="${Y_MAX}" step="1" value="${Y_MIN}">
            <input type="range" id="yHi" min="${Y_MIN}" max="${Y_MAX}" step="1" value="${Y_MAX}"></div>
            <span class="yr-lab" id="yLab">${Y_MIN} – ${Y_MAX}</span></div></div>
        <div class="fgroup"><span class="lbl">Regime</span><div class="regime-toggle" id="regToggle"></div></div>
      </div></div>
    <div class="scroll"><table class="dt"><thead><tr>
      <th data-k="ticker">Ticker</th>
      <th data-k="removed">Removed</th>
      <th data-k="sector">Sector</th>
      <th class="r" data-k="trough">Trough</th>
      <th class="r" data-k="ret1y">1Y return</th>
      <th class="r" data-k="qqq">QQQ</th>
      <th class="r" data-k="excess">vs QQQ</th>
      <th class="c" data-k="fate">Fate</th>
    </tr></thead><tbody id="tbody"></tbody></table></div>`;
  setTimeout(() => { setupFilters(card); paintRows(); }, 0);
  return card;
}

function setupFilters(card) {
  $('#q').addEventListener('input', (e) => { FILTER.q = e.target.value.trim().toUpperCase(); paintRows(); });
  $('#fTrunc').addEventListener('change', (e) => { FILTER.truncatedHidden = e.target.checked; paintRows(); });

  // dual-handle year range
  const lo = $('#yLo'), hi = $('#yHi');
  const syncYears = () => {
    let a = +lo.value, b = +hi.value;
    if (a > b) { if (document.activeElement === lo) b = a, hi.value = b; else a = b, lo.value = a; }
    FILTER.yMin = a; FILTER.yMax = b;
    const span = Y_MAX - Y_MIN || 1;
    const l = (a - Y_MIN) / span * 100, r = (b - Y_MIN) / span * 100;
    const sel = $('#ySel'); sel.style.left = l + '%'; sel.style.width = (r - l) + '%';
    $('#yLab').textContent = `${a} – ${b}`;
    paintRows();
  };
  lo.addEventListener('input', syncYears); hi.addEventListener('input', syncYears);
  syncYears();

  // regime 5-way toggle
  const rt = $('#regToggle');
  REGIMES.forEach(r => {
    const b = el('button');
    b.title = r.label; b.setAttribute('aria-label', r.label);
    b.innerHTML = r.blank ? '<span class="blank"></span>' : r.emoji;
    if (r.key === FILTER.regime) b.classList.add('on');
    const count = r.key === 'bull' ? (DATA.regimeMeta.counts.bull || 0) + (DATA.regimeMeta.counts.strong_bull || 0)
                : r.key === 'all' ? DATA.stocks.length : (DATA.regimeMeta.counts[r.key] || 0);
    if (count === 0) b.disabled = true;
    b.addEventListener('click', () => {
      FILTER.regime = r.key;
      rt.querySelectorAll('button').forEach(x => x.classList.remove('on'));
      b.classList.add('on'); paintRows();
    });
    rt.append(b);
  });

  // sortable headers
  card.querySelectorAll('thead th').forEach(th => th.addEventListener('click', () => {
    const k = th.dataset.k;
    SORT.dir = (SORT.key === k) ? -SORT.dir : (k === 'ticker' || k === 'sector' ? 1 : -1);
    SORT.key = k; paintRows();
  }));
  window.lucide && lucide.createIcons();
}

function regimeMatch(s) {
  if (FILTER.regime === 'all') return true;
  if (FILTER.regime === 'bull') return s.regime === 'bull' || s.regime === 'strong_bull';
  return s.regime === FILTER.regime;
}

function paintRows() {
  const q = FILTER.q;
  let rows = DATA.stocks.filter(s => {
    if (q && !(s.ticker.includes(q) || (s.sector || '').toUpperCase().includes(q))) return false;
    if (FILTER.truncatedHidden && s.truncated) return false;
    const yr = +s.removed.slice(0, 4);
    if (yr < FILTER.yMin || yr > FILTER.yMax) return false;
    if (!regimeMatch(s)) return false;
    return true;
  });
  const k = SORT.key;
  rows = rows.slice().sort((a, b) => {
    let x = a[k], y = b[k];
    if (typeof x === 'string') return x.localeCompare(y) * SORT.dir;
    return ((x ?? -1e9) - (y ?? -1e9)) * SORT.dir;
  });
  const tb = $('#tbody'); tb.innerHTML = '';
  rows.forEach(s => {
    const tr = el('tr');
    tr.innerHTML =
      `<td><span class="tk">${s.ticker}</span> <span class="co">${s.company || ''}</span></td>` +
      `<td><span class="num co">${s.removed}</span></td>` +
      `<td style="color:var(--text-secondary)">${s.sector || '—'}</td>` +
      `<td class="r"><span class="num warn" style="color:var(--warning)">${fmt(s.trough)}</span></td>` +
      `<td class="r"><span class="num ${toneOf(s.ret1y)}">${fmt(s.ret1y)}</span></td>` +
      `<td class="r"><span class="num ${toneOf(s.qqq)}">${fmt(s.qqq)}</span></td>` +
      `<td class="r"><span class="num ${toneOf(s.excess)}">${fmt(s.excess)}</span></td>` +
      `<td class="c"><span class="badge ${s.fateTone}">${s.fate}</span></td>`;
    tr.addEventListener('click', () => openDetail(s.id));
    tb.append(tr);
  });
  $('#rowcount').textContent = `${rows.length} of ${DATA.stocks.length}`;
}

// ============================ DEEP-DIVE ============================
let OV_CHARTS = [];   // overview charts — persist for the page lifetime
let DD_CHARTS = [];   // deep-dive charts — destroyed when the overlay closes
function destroyCharts() { DD_CHARTS.forEach(c => c.destroy()); DD_CHARTS = []; }

function openDetail(id, fromHash) {
  const s = BY_ID[id];
  if (!s) return;
  // keep the URL hash in sync so deep-dives are shareable / back-navigable
  if (!fromHash && decodeURIComponent(location.hash.slice(1)) !== id) location.hash = id;
  const ov = $('#overlay');
  const host = $('#sheet-inner');
  host.innerHTML = '';

  // header
  const top = el('div', 'dd-top');
  const back = el('button', 'btn'); back.innerHTML = '<i data-lucide="arrow-left"></i> Back to study';
  back.addEventListener('click', () => closeDetail());
  const badges = el('div', 'dd-badges');
  badges.innerHTML = `<span class="badge ${s.fateTone}">${s.fate}</span>` +
    (s.truncated ? '<span class="badge neutral">Truncated window</span>' : '') +
    (s.reAdded && s.readdDate ? `<span class="badge positive">Re-added ${s.readdDate}</span>` : '');
  top.append(back, badges);
  host.append(top);

  const idblk = el('div', 'dd-id'); idblk.style.marginBottom = '16px';
  idblk.innerHTML = `<h1 class="tk" style="font-size:var(--fs-2xl)">${s.ticker}</h1>
    <span class="meta">${s.company || ''}</span>
    <span class="meta">· removed <span class="num">${s.removed}</span> · window <span class="num">${s.firstDayOut}</span> → <span class="num">${s.lastDay}</span></span>`;
  host.append(idblk);
  host.append(metaBlock(s));

  // KPI cards
  const sg = el('div', 'statgrid'); sg.style.marginBottom = '20px';
  const kpi = (cls, label, v, vc) => { const n = el('div', 'stat ' + cls); n.innerHTML = `<div class="label">${label}</div><div class="value ${vc}">${v}</div>`; return n; };
  sg.append(kpi('warn', `Trough · day ${s.daysToLow}`, fmt(s.trough), 'warn'));
  sg.append(kpi('accent', `Peak · day ${s.daysToHigh}`, fmt(s.peak), 'accent'));
  sg.append(kpi(s.ret1y >= 0 ? 'pos' : 'neg', 'Return at window end', fmt(s.ret1y), toneOf(s.ret1y)));
  sg.append(kpi(s.excess >= 0 ? 'pos' : 'neg', 'Excess vs QQQ', fmt(s.excess), toneOf(s.excess)));
  host.append(sg);

  // market context
  if (s.regime) host.append(marketContextCard(s));

  // price-path chart
  const pc = el('div', 'card'); pc.style.marginBottom = '20px';
  if (s.series) {
    pc.innerHTML = `<div class="card-head"><div><div class="card-title">Indexed price path</div><div class="card-sub">Base 100 at first close out of the index · ${s.dataDays} trading days</div></div>
      <div class="legend"><span><i class="swatch" style="background:var(--accent)"></i>${s.ticker}</span><span><i class="swatch" style="background:var(--text-muted)"></i>QQQ</span></div></div>
      <div class="chartbox tall"><canvas id="ddPrice"></canvas></div>`;
  } else {
    pc.innerHTML = `<div class="card-head flush"><div class="card-title">Indexed price path</div></div><div class="nodata">Daily price series unavailable for this name.</div>`;
  }
  host.append(pc);

  // timeline table + commentary
  if (s.series) host.append(timelineCard(s));
  const cm = el('div', 'card'); cm.style.marginBottom = '20px';
  cm.innerHTML = `<div class="card-head flush"><div class="card-title">Commentary</div></div><p class="commentary">${commentary(s)}</p>`;
  host.append(cm);

  // comparables
  const cc = comparablesCard(s);
  if (cc) host.append(cc);

  ov.classList.add('open');
  document.body.style.overflow = 'hidden';
  $('#sheet').scrollTop = 0;
  destroyCharts();
  if (s.series) { drawPrice(s); }
  window.lucide && lucide.createIcons();
}

function closeDetail(fromHash) {
  $('#overlay').classList.remove('open');
  document.body.style.overflow = '';
  destroyCharts();
  // drop the per-stock hash when the user closes the overlay directly
  if (!fromHash && location.hash) history.replaceState(null, '', location.pathname + location.search);
}

function indexed(arr) { const b = arr[0]; return arr.map(v => v / b * 100); }

function timelineCard(s) {
  const st = indexed(s.series.stock), qq = indexed(s.series.qqq), d = s.series.dates;
  const last = st.length - 1;
  const marks = [
    { lbl: 'First 21 days', off: 21 },
    { lbl: 'Quarter 1', off: 63 },
    { lbl: 'Quarter 2', off: 126 },
    { lbl: 'Quarter 3', off: 189 },
    { lbl: 'Full window', off: last },
  ].filter(m => m.off <= last);
  const card = el('div', 'card'); card.style.marginBottom = '20px';
  let rows = '';
  marks.forEach(m => {
    const sp = st[m.off] - 100, qp = qq[m.off] - 100, ex = sp - qp;
    rows += `<tr><td class="lbl">${m.lbl}</td><td class="num co">${d[m.off]}</td>` +
      `<td class="num ${toneOf(sp)}">${fmt(sp)}</td>` +
      `<td class="num ${toneOf(qp)}">${fmt(qp)}</td>` +
      `<td class="num ${toneOf(ex)}">${fmt(ex)}</td></tr>`;
  });
  card.innerHTML = `<div class="card-head flush"><div><div class="card-title">Timeline</div><div class="card-sub">Cumulative return vs QQQ over the window</div></div></div>
    <table class="tl"><thead><tr><th>Period</th><th>As of</th><th>${s.ticker}</th><th>QQQ</th><th>Excess</th></tr></thead><tbody>${rows}</tbody></table>`;
  return card;
}

function commentary(s) {
  const dir = s.ret1y >= 0 ? 'gained' : 'lost';
  const beat = s.excess >= 0 ? `beating QQQ by ${fmt(s.excess).replace('+','')}` : `trailing QQQ by ${fmt(-s.excess).replace('+','')}`;
  let txt = `Over ${s.dataDays} trading days after leaving the Nasdaq-100, ${s.ticker} ${dir} ${fmt(Math.abs(s.ret1y), false)} versus ${fmt(s.qqq)} for QQQ over the identical window — ${beat}. `;
  txt += `It bottomed at ${fmt(s.trough)} on ${s.dateOfLow} (${s.daysToLow} trading days out) and peaked at ${fmt(s.peak)} on ${s.dateOfHigh}. `;
  if (s.reAdded && s.readdDate) {
    const yrs = s.roundTripYears != null ? ` (${s.roundTripYears.toFixed(2)} years later)` : '';
    txt += `${s.ticker} later re-entered the index on ${s.readdDate}${yrs}.`;
  } else if (s.fate === 'Acquired') {
    txt += `${s.ticker} was ultimately acquired.`;
  } else {
    txt += `${s.ticker} has not re-entered the index.`;
  }
  if (s.truncated) txt += ' The post-removal window is truncated by the data cutoff, so the figures cover a shorter span.';
  return txt;
}

// ---- deep-dive context blocks ----
const ARCH_NAME = { revolving_door: 'Revolving door', core_member: 'Core member', structural_decliner: 'Structural decliner' };
const REGIME_NAME = { crash: 'crash', bear: 'bear market', flat: 'flat market', bull: 'bull market', strong_bull: 'strong bull market' };

function metaBlock(s) {
  const b = el('div', 'meta-block');
  const parts = [];
  if (s.company) parts.push(`<span><span class="mk">Company</span> ${s.company}</span>`);
  if (s.sector) parts.push(`<span><span class="mk">Sector</span> ${s.sector}</span>`);
  if (s.archetype) {
    const yrs = s.yearsInIndex != null ? ` · <span class="num">${s.yearsInIndex.toFixed(1)}y</span> in index${s.tenureCensored ? ' (censored)' : ''}` : '';
    parts.push(`<span><span class="mk">Tenure</span> ${ARCH_NAME[s.archetype] || s.archetype}${yrs}</span>`);
  }
  b.innerHTML = parts.join('');
  if (s.reason) { const r = el('div', 'reason'); r.textContent = '“' + s.reason + '”'; b.append(r); }
  return b;
}

function marketContextCard(s) {
  const card = el('div', 'card'); card.style.marginBottom = '20px';
  const rname = REGIME_NAME[s.regime] || s.regime || 'unclassified';
  const ep = s.episode ? `<span class="badge accent">${s.episode}</span>` : '';
  card.innerHTML = `<div class="card-head flush"><div style="display:flex;align-items:center;gap:10px"><div class="card-title">Market context</div>${ep}</div></div>
    <div class="ctx-grid">
      <div class="ctx"><div class="k">QQQ over window</div><div class="v ${toneOf(s.qqq)}">${fmt(s.qqq)}</div></div>
      <div class="ctx"><div class="k">QQQ max drawdown</div><div class="v" style="color:var(--warning)">${fmt(s.qqqMaxDrawdown)}</div></div>
      <div class="ctx"><div class="k">Regime</div><div class="v" style="font-size:var(--fs-md);color:var(--text-heading)">${rname}</div></div>
    </div>
    <p class="decomp">Total <span class="num ${toneOf(s.ret1y)}">${fmt(s.ret1y)}</span> decomposes as market <span class="num ${toneOf(s.qqq)}">${fmt(s.qqq)}</span> + stock-specific <span class="num ${toneOf(s.excess)}">${fmt(s.excess)}</span> (excess vs QQQ) — a return decomposition, not a causal claim.</p>`;
  return card;
}

function comparablesCard(s) {
  if (!s.comparableIds || !s.comparableIds.length) return null;
  const card = el('div', 'card tablecard'); card.style.marginBottom = '20px';
  let rows = '';
  s.comparableIds.forEach(pid => {
    const p = DATA.stocks.find(x => x.id === pid);
    if (!p) return;
    rows += `<tr data-id="${p.id}">
      <td><span class="tk">${p.ticker}</span> <span class="num co">${p.removed}</span></td>
      <td class="r"><span class="num ${toneOf(p.ret1y)}">${fmt(p.ret1y)}</span></td>
      <td class="r"><span class="num ${toneOf(p.excess)}">${fmt(p.excess)}</span></td>
      <td style="color:var(--text-secondary)">${p.sector || '—'}</td>
      <td class="c"><span class="badge ${p.fateTone}">${p.fate}</span></td></tr>`;
  });
  card.innerHTML = `<div class="table-top"><div><div class="card-title">Comparable removals</div>
      <div class="card-sub">Most similar prior removals — ${s.comparableCriteria || ''}</div></div></div>
    <div style="overflow:auto"><table class="dt"><thead><tr>
      <th>Peer</th><th class="r">1Y return</th><th class="r">vs QQQ</th><th>Sector</th><th class="c">Fate</th>
    </tr></thead><tbody>${rows}</tbody></table></div>`;
  setTimeout(() => card.querySelectorAll('tbody tr').forEach(tr =>
    tr.addEventListener('click', () => openDetail(tr.dataset.id))), 0);
  return card;
}

// ============================ CHARTS ============================
function drawAvgPath() {
  const ctx = $('#apChart'); if (!ctx) return;
  const a = DATA.avgPath;
  const c = new Chart(ctx, {
    type: 'line',
    data: {
      labels: a.offsets,
      datasets: [
        { data: a.p75, borderColor: 'transparent', pointRadius: 0, fill: false, tension: 0.25 },
        { data: a.p25, borderColor: 'transparent', backgroundColor: COLORS.accentSoft, pointRadius: 0, fill: '-1', tension: 0.25 },
        { label: 'Median', data: a.median, borderColor: COLORS.accent, borderWidth: 2.5, pointRadius: 0, fill: false, tension: 0.25 },
        { data: a.offsets.map(() => 100), borderColor: COLORS.muted, borderWidth: 1, borderDash: [3, 4], pointRadius: 0, fill: false },
      ],
    },
    options: baseLineOpts('Trading days out', (v) => v.toFixed(0)),
  });
  OV_CHARTS.push(c);
}

function drawPrice(s) {
  const ctx = $('#ddPrice'); if (!ctx) return;
  const st = indexed(s.series.stock), qq = indexed(s.series.qqq);
  const labels = st.map((_, i) => i);
  const c = new Chart(ctx, {
    type: 'line',
    data: {
      labels,
      datasets: [
        { label: 'QQQ', data: qq, borderColor: COLORS.muted, borderWidth: 1.5, borderDash: [5, 4], pointRadius: 0, tension: 0.15 },
        { label: s.ticker, data: st, borderColor: COLORS.accent, borderWidth: 2.5, pointRadius: 0, tension: 0.15 },
      ],
    },
    options: baseLineOpts('Trading days out', (v) => v.toFixed(0)),
  });
  DD_CHARTS.push(c);
}

function baseLineOpts(xtitle, xfmt) {
  return {
    responsive: true, maintainAspectRatio: false,
    interaction: { mode: 'index', intersect: false },
    plugins: {
      legend: { display: false },
      zoom: zoomCfg('x'),
      tooltip: tooltipStyle({
        title: (it) => `Day ${it[0].label}`,
        label: (it) => it.dataset.label ? `${it.dataset.label}: ${it.parsed.y.toFixed(1)}` : null,
      }, (it) => !!it.dataset.label),
    },
    scales: {
      x: { ...gridOpts(), title: { display: true, text: xtitle, color: COLORS.muted },
           ticks: { color: COLORS.muted, maxTicksLimit: 8, callback: function (v) { return xfmt(this.getLabelForValue(v)); } } },
      y: { ...gridOpts(), ticks: { color: COLORS.muted } },
    },
  };
}

// ============================ BOOT ============================
// open/close the overlay to match the current URL hash (#TICKER-DATE)
function syncFromHash() {
  const id = decodeURIComponent(location.hash.slice(1));
  if (id && BY_ID[id]) openDetail(id, true);
  else closeDetail(true);
}

window.addEventListener('DOMContentLoaded', () => {
  themeCharts();
  renderOverview();
  $('#scrim').addEventListener('click', () => closeDetail());
  // clicking the empty side gutters of the deep-dive (outside the content column) goes back
  const sheet = $('#sheet');
  sheet.addEventListener('click', (e) => { if (e.target === sheet) closeDetail(); });
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeDetail(); });
  // double-click any chart to reset its zoom/pan to the original view
  document.addEventListener('dblclick', (e) => {
    const cv = e.target && e.target.closest && e.target.closest('canvas');
    if (!cv || !window.Chart) return;
    const c = Chart.getChart(cv); if (c && c.resetZoom) c.resetZoom();
  });
  // shareable deep-links: open the hash target on load, and follow hash changes
  window.addEventListener('hashchange', syncFromHash);
  syncFromHash();
});
"""

HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Nasdaq-100 Removals — the year after leaving the index</title>
<link rel="icon" type="image/svg+xml" href="__FAVICON__">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,400;12..96,600;12..96,700&family=Hanken+Grotesk:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600;700&display=swap" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.3/dist/chart.umd.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/hammerjs@2.0.8/hammer.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/chartjs-plugin-zoom@2.0.1/dist/chartjs-plugin-zoom.min.js"></script>
<script src="https://unpkg.com/lucide@latest/dist/umd/lucide.min.js"></script>
<style>
/*__TOKENS__*/
</style>
<style>
/*__PAGECSS__*/
</style>
</head>
<body>
<header class="topnav"><div class="wrap bar">
  <div class="brand">
    <img src="__FAVICON__" alt="">
    <div><div class="t">Nasdaq-100 Removals</div><div class="s">The year after leaving the index</div></div>
  </div>
  <a class="navlink" href="https://github.com/yotam-sh/qqq-removals" target="_blank" rel="noopener"><i data-lucide="github"></i> Source</a>
</div></header>

<main><div class="wrap stack" id="overview"></div></main>

<footer class="foot"><div class="wrap"><p>
  Generated from <span class="num">results_per_stock.csv</span> · charts via Chart.js · Comet design system.<br>
  Price data via Yahoo Finance (yfinance). “Nasdaq-100” is a trademark of Nasdaq, Inc.; “QQQ” (Invesco QQQ Trust) is a product of Invesco — used for identification only.
  Descriptive and educational, not investment advice. Built by Hesanka with Claude. © 2026.
</p></div></footer>

<div class="overlay" id="overlay">
  <div class="scrim" id="scrim"></div>
  <div class="sheet" id="sheet"><div class="sheet-inner" id="sheet-inner"></div></div>
</div>

<script>
const DATA = /*__DATA__*/;
</script>
<script>
/*__PAGEJS__*/
</script>
</body>
</html>
"""


def main():
    data = build_data()
    tokens = (HERE / "comet-tokens.css").read_text(encoding="utf-8")
    favicon = (HERE / "qqq-favicon.svg").read_text(encoding="utf-8")

    import urllib.parse
    favicon_uri = "data:image/svg+xml," + urllib.parse.quote(favicon)

    html = HTML_TEMPLATE
    html = html.replace("/*__TOKENS__*/", tokens)
    html = html.replace("/*__PAGECSS__*/", PAGE_CSS)
    html = html.replace("/*__PAGEJS__*/", PAGE_JS)
    html = html.replace("/*__DATA__*/", json.dumps(data, separators=(",", ":")))
    html = html.replace("__FAVICON__", favicon_uri)
    html = html.replace("\\u2014", "—")  # title placeholder

    out = ROOT / "dist" / "index.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    n_series = sum(1 for s in data["stocks"] if "series" in s)
    kb = len(html.encode("utf-8")) / 1024
    print(f"Wrote {out}")
    print(f"  {len(data['stocks'])} removals, {n_series} with embedded deep-dive series")
    print(f"  {len(data['byYear'])} year cohorts, {len(data['sectors'])} sectors")
    print(f"  output size: {kb:.0f} KiB")


if __name__ == "__main__":
    main()
