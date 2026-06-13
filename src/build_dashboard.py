#!/usr/bin/env python3
"""
Generate a single self-contained index.html from results_per_stock.csv.

The CSV rows are embedded directly into the HTML as a JS array at generation
time, so the output file needs no server and no build step -- just double-click
it. Charting is Chart.js loaded from a CDN (the only thing that needs internet
when the page is opened). Re-run this after the study updates to refresh.

Reads results_per_stock.csv read-only; never modifies it or the study script.
"""

import json
import os
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]   # repo root (this file lives in src/)
CSV = str(ROOT / "data" / "processed" / "results_per_stock.csv")
OUT = str(ROOT / "dist" / "index.html")

# Columns the dashboard uses; 'source' is optional (bonus provenance column).
WANT = ["ticker", "removal_date", "first_day_out", "base_close",
        "lowest_pct", "days_to_low", "date_of_low",
        "highest_pct", "days_to_high", "date_of_high",
        "one_year_pct", "qqq_same_window_pct", "excess_vs_qqq_pct",
        "data_days", "truncated", "source"]


def load_rows():
    if not os.path.exists(CSV):
        sys.exit(f"ERROR: {CSV} not found in {os.getcwd()}. "
                 "Run the study (python ndx_removals_study.py analyze) first; "
                 "not fabricating data.")
    df = pd.read_csv(CSV)
    print(f"Read {CSV}: {len(df)} rows, {len(df.columns)} columns.")
    cols = [c for c in WANT if c in df.columns]
    missing = [c for c in WANT if c not in df.columns and c != "source"]
    if missing:
        print(f"  NOTE: expected columns absent (charts will degrade): {missing}")
    df = df[cols].copy()
    if "truncated" in df:
        df["truncated"] = df["truncated"].astype(bool)
    # NaN -> None so it serializes to JS null (graceful-degrade path handles it)
    records = df.where(pd.notna(df), None).to_dict("records")
    # numpy scalar -> native python for json
    clean = []
    for r in records:
        clean.append({k: (bool(v) if isinstance(v, (bool,)) else
                          (v.item() if hasattr(v, "item") else v))
                      for k, v in r.items()})
    return df, clean


def median(s):
    return float(s.dropna().median())


def takeaways(df):
    """Compute the 5 plain-language bullets printed to the terminal."""
    n = len(df)
    trunc = int(df["truncated"].sum())
    full = df[~df["truncated"]]
    nf = len(full)
    med_trough = median(df["lowest_pct"])
    early = (df["days_to_low"] <= 21).mean() * 100
    med_days_low = median(df["days_to_low"])
    med_1y = median(full["one_year_pct"])
    pos = (full["one_year_pct"] > 0).mean() * 100
    ex = full["excess_vs_qqq_pct"].dropna()
    med_ex = float(ex.median()) if len(ex) else float("nan")
    beat = (ex > 0).mean() * 100 if len(ex) else float("nan")
    by = (df.assign(y=pd.to_datetime(df["removal_date"]).dt.year)
            .groupby("y")["one_year_pct"].median())
    best_y, best_v = by.idxmax(), by.max()

    bullets = [
        f"Survivorship caveat first: these are the {n} removed names that still "
        f"had post-removal prices; delisted/acquired tickers (the worst outcomes) "
        f"are absent and {trunc} rows ({trunc/n*100:.0f}%) are truncated -- so every "
        f"figure below is biased UPWARD.",
        f"Trough depth: the median stock fell {med_trough:.1f}% below its first-day-out "
        f"close at its low point; {early:.0f}% of troughs land within the first ~month "
        f"(21 trading days), median day-to-trough {med_days_low:.0f} -- only mild support "
        f"for an immediate forced-selling dip.",
        f"One year out (full-year rows, n={nf}): median total return {med_1y:+.1f}%, with "
        f"{pos:.0f}% of stocks positive -- but that largely rides the market being up.",
        f"Versus QQQ over the identical window (the fair, regime-neutral measure): median "
        f"excess {med_ex:+.1f}%, and only {beat:.0f}% beat QQQ -- the relative picture is "
        f"far weaker than the raw-return picture.",
        f"A few macro years dominate the tails: the {best_y} cohort shows a median "
        f"{best_v:+.0f}% (pure survivors rebounding) -- use the by-year chart to see how "
        f"uneven the story is across removal years.",
    ]
    return bullets


HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="icon" type="image/svg+xml" href="favicon.svg">
<title>Nasdaq-100 Removals — First Year After Leaving the Index</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<script>
  // set theme before paint to avoid a flash of the wrong colors
  (function(){ try{
    var t = localStorage.getItem('ndxtheme') ||
            (matchMedia('(prefers-color-scheme:dark)').matches ? 'dark' : 'light');
    document.documentElement.setAttribute('data-theme', t);
  }catch(e){} })();
</script>
<style>
  :root{
    --bg:#fafafa; --fg:#1a1a1a; --muted:#6b7280; --faint:#9ca3af; --line:#e5e7eb;
    --card:#ffffff; --slate:#334155;
    --rowline:#f1f1f1; --thbg:#f8fafc; --thhover:#eef2f6; --rowhover:#f8fafc;
    --bnbg:#fef3c7; --bnbd:#f59e0b; --bnfg:#92400e;
    --green:#15803d; --red:#b91c1c;
    /* chart colors (read by JS via getCSS) */
    --grid:#f1f1f1; --barfill:#94a3b8; --barborder:#64748b; --dot:rgba(51,65,85,.55);
    --posfill:rgba(21,128,61,.55); --posborder:#15803d;
    --negfill:rgba(185,28,28,.55); --negborder:#b91c1c;
  }
  html[data-theme="dark"]{
    --bg:#0f1115; --fg:#e6e8ec; --muted:#9aa4b2; --faint:#6b7280; --line:#2a2f3a;
    --card:#171a21; --slate:#c7d0db;
    --rowline:#23272f; --thbg:#1c2029; --thhover:#222732; --rowhover:#1b1f27;
    --bnbg:#2a2410; --bnbd:#a16207; --bnfg:#fde68a;
    --green:#22c55e; --red:#f87171;
    --grid:#262b36; --barfill:#64748b; --barborder:#94a3b8; --dot:rgba(148,163,184,.6);
    --posfill:rgba(34,197,94,.5); --posborder:#22c55e;
    --negfill:rgba(248,113,113,.5); --negborder:#f87171;
  }
  html{background:var(--bg)}
  *{box-sizing:border-box}
  body{margin:0;background:var(--bg);color:var(--fg);
    font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
    line-height:1.5;-webkit-font-smoothing:antialiased}
  .wrap{max-width:1080px;margin:0 auto;padding:40px 24px 80px}
  h1{font-size:26px;font-weight:650;margin:0 0 6px;letter-spacing:-.01em}
  .sub{color:var(--muted);font-size:15px;margin:0 0 24px}
  h2{font-size:18px;font-weight:600;margin:44px 0 4px;letter-spacing:-.01em}
  .cap{color:var(--muted);font-size:13.5px;font-style:italic;margin:0 0 16px}
  .banner{background:var(--bnbg);border:1px solid var(--bnbd);color:var(--bnfg);
    border-radius:10px;padding:14px 16px;font-size:14px;margin:0 0 8px}
  .banner b{font-weight:650}
  .cards{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin:8px 0 8px}
  .card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px 18px}
  .card .v{font-size:26px;font-weight:680;letter-spacing:-.02em}
  .card .l{color:var(--muted);font-size:12.5px;margin-top:3px}
  .card .n{color:var(--faint);font-size:11px;margin-top:2px}
  .pos{color:var(--green)} .neg{color:var(--red)}
  .grid2{display:grid;grid-template-columns:1fr 1fr;gap:26px}
  .chart-box{background:var(--card);border:1px solid var(--line);border-radius:12px;
    padding:14px 14px 6px}
  .chart-area{position:relative;height:280px}
  /* table */
  .controls{display:flex;flex-wrap:wrap;gap:14px;align-items:center;margin:6px 0 12px;
    font-size:13.5px;color:var(--slate)}
  .controls input[type=text],.controls input[type=number]{
    border:1px solid var(--line);border-radius:7px;padding:6px 9px;font:inherit;font-size:13px}
  .controls input[type=number]{width:74px}
  .controls label{display:inline-flex;align-items:center;gap:6px;cursor:pointer}
  .tablewrap{overflow-x:auto;border:1px solid var(--line);border-radius:12px;background:var(--card)}
  table{border-collapse:collapse;width:100%;font-size:12.5px;white-space:nowrap}
  th,td{padding:7px 11px;text-align:right;border-bottom:1px solid var(--rowline)}
  th:first-child,td:first-child{text-align:left;position:sticky;left:0;background:var(--card)}
  thead th{position:sticky;top:0;background:var(--thbg);cursor:pointer;user-select:none;
    font-weight:600;color:var(--slate);border-bottom:1px solid var(--line)}
  thead th:hover{background:var(--thhover)}
  th.sorted::after{content:" \25B4";color:var(--muted)}
  th.sorted.desc::after{content:" \25BE"}
  tbody tr:hover{background:var(--rowhover)}
  td.tk{font-weight:600}
  td.tk a{color:var(--slate);text-decoration:none}
  td.tk a:hover{text-decoration:underline}
  .meta{color:var(--muted);font-size:12.5px;margin:8px 2px 0}
  .caveats{background:var(--card);border:1px solid var(--line);border-radius:12px;
    padding:18px 22px;margin-top:14px;font-size:14px}
  .caveats h2{margin-top:0}
  .caveats li{margin:8px 0}
  .foot{color:var(--faint);font-size:12px;margin-top:34px;text-align:center}
  /* header + theme toggle */
  .head{display:flex;align-items:flex-start;justify-content:space-between;gap:16px}
  #themeBtn{flex:none;margin-top:4px;background:var(--card);color:var(--fg);
    border:1px solid var(--line);border-radius:8px;padding:7px 12px;font:inherit;
    font-size:13px;cursor:pointer}
  #themeBtn:hover{background:var(--thhover)}
</style>
</head>
<body>
<div class="wrap">
  <div class="head">
    <div>
      <h1>Nasdaq-100 Removals — the year after leaving the index</h1>
      <p class="sub">How stocks dropped from the NDX behaved over their first 252 trading days
         out. Baseline = close of the first day out. Read top to bottom.</p>
    </div>
    <button id="themeBtn" type="button" aria-label="Toggle dark mode"></button>
  </div>

  <div id="banner"></div>

  <div class="cards" id="cards"></div>

  <h2>Distributions</h2>
  <p class="cap">The shape of each outcome across all removed stocks; the dashed line marks the median.</p>
  <div class="grid2">
    <div class="chart-box"><div class="chart-area"><canvas id="hTrough"></canvas></div>
      <p class="cap" id="capTrough"></p></div>
    <div class="chart-box"><div class="chart-area"><canvas id="hDays"></canvas></div>
      <p class="cap" id="capDays"></p></div>
    <div class="chart-box"><div class="chart-area"><canvas id="hRet"></canvas></div>
      <p class="cap" id="capRet"></p></div>
    <div class="chart-box"><div class="chart-area"><canvas id="hEx"></canvas></div>
      <p class="cap" id="capEx"></p></div>
  </div>

  <h2>Timing — do troughs cluster early?</h2>
  <p class="cap">If forced index-fund selling drives prices down right after removal, low points
     should bunch at small x. A spread across the year argues against pure price-pressure.</p>
  <div class="grid2">
    <div class="chart-box"><div class="chart-area"><canvas id="sLow"></canvas></div>
      <p class="cap">Each dot = one stock: trading days until its lowest close (x) vs trough depth % (y). Hover for the ticker.</p></div>
    <div class="chart-box"><div class="chart-area"><canvas id="sHigh"></canvas></div>
      <p class="cap">Same for peaks: days until the highest close (x) vs peak height % (y).</p></div>
  </div>

  <h2>By removal year</h2>
  <p class="cap">Median 1-year return for each removal cohort (bar) with the number of stocks (n) per year.
     Watch for a few macro years (2008, 2022) driving the extremes.</p>
  <div class="chart-box"><div class="chart-area" style="height:320px"><canvas id="byYear"></canvas></div></div>

  <h2>Every stock</h2>
  <div class="controls">
    <label><input type="checkbox" id="fTrunc"> Hide truncated rows</label>
    <span>Years <input type="number" id="fYmin"> – <input type="number" id="fYmax"></span>
    <input type="text" id="fSearch" placeholder="search ticker…">
    <span class="meta" id="tableCount"></span>
  </div>
  <div class="tablewrap"><table id="tbl"><thead></thead><tbody></tbody></table></div>

  <div class="caveats">
    <h2>How to read this — and what it hides</h2>
    <ul id="caveatList">
      <li><b>Survivorship bias is the big one.</b> This file only contains removed stocks that
        <i>still had price data</i>. Tickers that were later delisted, went bankrupt, or were
        acquired get dropped by the data source — and those were disproportionately the
        <i>worst</i> post-removal performers. So the true numbers are lower than everything shown here.</li>
      <li><b>Truncated windows.</b> A stock acquired or delisted <i>during</i> its post-removal year
        has fewer than a full 252 trading days; its "1-year return" isn't a real year. The
        year-based stats (1-yr return, % positive, % beat QQQ) use full-year rows only; you can
        hide truncated rows in the table to see the rest.</li>
      <li><b>Excess vs QQQ is the fairer measure.</b> A raw return mostly reflects whether the
        market happened to be up or down over that particular year. Return <i>relative to QQQ</i>
        over the identical window strips out the regime, so it's the more meaningful comparison
        across a 2008 removal vs a 2021 one.</li>
    </ul>
  </div>

  <p class="foot">Generated from results_per_stock.csv · charts via Chart.js (CDN)</p>
</div>

<script>
const RAW = __ROWS__;

// ---------- helpers ----------
const fmtPct = v => (v==null||isNaN(v)) ? "—" : (v>=0?"+":"") + v.toFixed(1) + "%";
const num = (r,k) => (r[k]==null || r[k]==="" || isNaN(+r[k])) ? null : +r[k];
function colValues(key){ return RAW.map(r=>num(r,key)).filter(v=>v!=null); }
function median(a){ if(!a.length) return null; const s=[...a].sort((x,y)=>x-y);
  const m=Math.floor(s.length/2); return s.length%2 ? s[m] : (s[m-1]+s[m])/2; }
const yearOf = r => +String(r.removal_date).slice(0,4);
const sign = v => v==null?"":(v>=0?"pos":"neg");

// ---------- theme helper + chart registry ----------
const getCSS = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const CHARTS = [];
const skipped = new Set();
let skippedDone = false;
function haveCol(key){ return colValues(key).length > 0; }

// ---------- median line plugin for histograms (category axis) ----------
function medianPlugin(bins, med){
  return { id:'med'+Math.random().toString(36).slice(2), afterDraw(chart){
    if(med==null) return;
    const {ctx, chartArea:{top,bottom}, scales:{x}} = chart;
    let idx = bins.findIndex(b => med >= b.lo && med < b.hi);
    if(idx<0) idx = med < bins[0].lo ? 0 : bins.length-1;
    const c = x.getPixelForValue(idx);
    const cN = x.getPixelForValue(Math.min(idx+1,bins.length-1));
    const cP = x.getPixelForValue(Math.max(idx-1,0));
    const step = (cN - cP)/2 || (cN - c) || 12;
    const frac = (med - bins[idx].lo)/((bins[idx].hi - bins[idx].lo)||1);
    const px = c + (frac - 0.5)*step;
    const fg=getCSS('--fg');
    ctx.save();
    ctx.strokeStyle=fg; ctx.lineWidth=1.5; ctx.setLineDash([4,3]);
    ctx.beginPath(); ctx.moveTo(px,top); ctx.lineTo(px,bottom); ctx.stroke();
    ctx.setLineDash([]); ctx.fillStyle=fg;
    ctx.font='11px -apple-system,Segoe UI,sans-serif'; ctx.textAlign='center';
    ctx.fillText('median '+ (med>=0?'+':'') + med.toFixed(1), px, top+11);
    ctx.restore();
  }};
}

function histo(canvasId, capId, key, label, nbins, fmt){
  const vals = colValues(key);
  const box = document.getElementById(canvasId).closest('.chart-box');
  if(!vals.length){ box.style.display='none'; skipped.add(label); return; }
  const lo = Math.min(...vals), hi = Math.max(...vals);
  const span = (hi-lo)||1, w = span/nbins;
  const bins = Array.from({length:nbins}, (_,i)=>({lo:lo+i*w, hi:lo+(i+1)*w, c:0}));
  bins[nbins-1].hi += 1e-9;
  vals.forEach(v=>{ let i=Math.floor((v-lo)/w); if(i<0)i=0; if(i>=nbins)i=nbins-1; bins[i].c++; });
  const labels = bins.map(b=>fmt(Math.round((b.lo+b.hi)/2)));
  const med = median(vals);
  const grid=getCSS('--grid'), tick=getCSS('--muted');
  CHARTS.push(new Chart(document.getElementById(canvasId), {
    type:'bar',
    data:{labels, datasets:[{data:bins.map(b=>b.c), backgroundColor:getCSS('--barfill'),
      borderColor:getCSS('--barborder'), borderWidth:1, barPercentage:1, categoryPercentage:1}]},
    options:{responsive:true, maintainAspectRatio:false,
      plugins:{legend:{display:false},
        tooltip:{callbacks:{title:i=>label, label:i=>`${bins[i.dataIndex].lo.toFixed(0)}…${bins[i.dataIndex].hi.toFixed(0)}: ${i.raw} stocks`}}},
      scales:{x:{grid:{display:false}, ticks:{maxRotation:0, autoSkip:true, font:{size:10}, color:tick}},
        y:{grid:{color:grid}, ticks:{precision:0, font:{size:10}, color:tick}, title:{display:true,text:'# stocks',font:{size:10}, color:tick}}}},
    plugins:[medianPlugin(bins, med)]
  }));
  document.getElementById(capId).textContent =
    `${label}. Median = ${fmt(med.toFixed ? +med.toFixed(1):med)}${key.includes('day')?' days':'%'} (n=${vals.length}).`;
}

function scatter(canvasId, xk, yk, xlabel, ylabel){
  const box = document.getElementById(canvasId).closest('.chart-box');
  const pts = RAW.map(r=>({x:num(r,xk), y:num(r,yk), t:r.ticker, d:r.removal_date}))
                 .filter(p=>p.x!=null && p.y!=null);
  if(!pts.length){ box.style.display='none'; skipped.add(xlabel+' vs '+ylabel); return; }
  const grid=getCSS('--grid'), tick=getCSS('--muted');
  CHARTS.push(new Chart(document.getElementById(canvasId), {
    type:'scatter',
    data:{datasets:[{data:pts, backgroundColor:getCSS('--dot'), radius:4, hoverRadius:6}]},
    options:{responsive:true, maintainAspectRatio:false,
      plugins:{legend:{display:false}, tooltip:{callbacks:{
        label:c=>`${c.raw.t} (${c.raw.d}): day ${c.raw.x}, ${fmtPct(c.raw.y)}`}}},
      scales:{x:{title:{display:true,text:xlabel,font:{size:11},color:tick}, grid:{color:grid}, ticks:{font:{size:10},color:tick}},
        y:{title:{display:true,text:ylabel,font:{size:11},color:tick}, grid:{color:grid}, ticks:{font:{size:10},color:tick}}}}
  }));
}

// ---------- banner ----------
(function(){
  const n=RAW.length, trunc=RAW.filter(r=>r.truncated).length;
  const share=trunc/n;
  const el=document.getElementById('banner');
  if(share>=0.08 || n<140){
    el.innerHTML = `<b>Read these numbers as an upper bound.</b> This view has only the
      <b>${n}</b> removed stocks with available post-removal prices — delisted/acquired
      tickers that the data source dropped (typically the worst performers) are missing,
      and <b>${trunc}</b> (${(share*100).toFixed(0)}%) of these windows are truncated.
      Survivorship bias pushes every figure here upward.`;
  } else { el.style.display='none'; }
})();

// ---------- cards ----------
(function(){
  const all=RAW, full=RAW.filter(r=>!r.truncated);
  const med=(arr,k)=>median(arr.map(r=>num(r,k)).filter(v=>v!=null));
  const pct=(arr,fn)=>arr.length? (arr.filter(fn).length/arr.length*100):null;
  const exFull=full.filter(r=>num(r,'excess_vs_qqq_pct')!=null);
  const cards=[
    {v:all.length, l:'stocks analyzed', n:'survivors with price data'},
    {v:fmtPct(med(all,'lowest_pct')), l:'median trough depth', cls:'neg', n:`all ${all.length}`},
    {v:Math.round(med(all,'days_to_low'))+' d', l:'median days to trough', n:'trading days after day 1'},
    {v:fmtPct(med(full,'one_year_pct')), l:'median 1-year return', cls:sign(med(full,'one_year_pct')), n:`full-year rows, n=${full.length}`},
    {v:pct(full,r=>num(r,'one_year_pct')>0).toFixed(0)+'%', l:'positive after 1 year', n:`full-year rows, n=${full.length}`},
    {v:exFull.length? pct(exFull,r=>num(r,'excess_vs_qqq_pct')>0).toFixed(0)+'%':'—',
      l:'beat QQQ (same window)', n:`full-year rows, n=${exFull.length}`},
  ];
  document.getElementById('cards').innerHTML = cards.map(c=>
    `<div class="card"><div class="v ${c.cls||''}">${c.v}</div>
      <div class="l">${c.l}</div><div class="n">${c.n||''}</div></div>`).join('');
})();

// ---------- by year ----------
function drawByYear(){
  const years=[...new Set(RAW.map(yearOf))].sort();
  const agg=years.map(y=>{ const g=RAW.filter(r=>yearOf(r)===y);
    return {y, m:median(g.map(r=>num(r,'one_year_pct')).filter(v=>v!=null)), n:g.length}; });
  const grid=getCSS('--grid'), tick=getCSS('--muted');
  const pos=getCSS('--posfill'), posb=getCSS('--posborder'),
        neg=getCSS('--negfill'), negb=getCSS('--negborder');
  CHARTS.push(new Chart(document.getElementById('byYear'), {
    type:'bar',
    data:{labels:agg.map(a=>`${a.y}\n(n=${a.n})`),
      datasets:[{data:agg.map(a=>a.m),
        backgroundColor:agg.map(a=>a.m>=0?pos:neg),
        borderColor:agg.map(a=>a.m>=0?posb:negb), borderWidth:1}]},
    options:{responsive:true, maintainAspectRatio:false,
      plugins:{legend:{display:false},
        tooltip:{callbacks:{title:i=>agg[i[0].dataIndex].y,
          label:i=>`median ${fmtPct(i.raw)} · n=${agg[i.dataIndex].n}`}}},
      scales:{x:{grid:{display:false}, ticks:{font:{size:10}, color:tick,
          callback:function(v){return this.getLabelForValue(v).split('\n');}}},
        y:{grid:{color:grid}, ticks:{callback:v=>v+'%',font:{size:10}, color:tick},
          title:{display:true,text:'median 1-yr return',font:{size:10}, color:tick}}}}
  }));
}

// ---------- render all charts (re-run on theme change) ----------
function renderCharts(){
  CHARTS.forEach(c=>c.destroy()); CHARTS.length=0;
  Chart.defaults.color = getCSS('--muted');
  histo('hTrough','capTrough','lowest_pct','Trough depth vs first-day-out close', 22, v=>v);
  histo('hDays','capDays','days_to_low','Trading days to the trough', 21, v=>v);
  histo('hRet','capRet','one_year_pct','One-year total return', 24, v=>v);
  histo('hEx','capEx','excess_vs_qqq_pct','Excess return vs QQQ', 24, v=>v);
  scatter('sLow','days_to_low','lowest_pct','Trading days to trough','Trough depth %');
  scatter('sHigh','days_to_high','highest_pct','Trading days to peak','Peak height %');
  drawByYear();
  if(!skippedDone){ skippedDone=true;
    if(skipped.size){
      const li=document.createElement('li');
      li.innerHTML='<b>Charts skipped for missing data:</b> '+[...skipped].join(', ')+
        ' — the relevant column was empty in results_per_stock.csv.';
      document.getElementById('caveatList').appendChild(li);
    }
  }
}
renderCharts();

// ---------- theme toggle ----------
(function(){
  const btn=document.getElementById('themeBtn');
  const setLabel=()=>{ const dark=document.documentElement.getAttribute('data-theme')==='dark';
    btn.textContent = dark ? '☀ Light' : '🌙 Dark'; };
  setLabel();
  btn.addEventListener('click',()=>{
    const dark=document.documentElement.getAttribute('data-theme')==='dark';
    const t = dark ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', t);
    try{ localStorage.setItem('ndxtheme', t); }catch(e){}
    setLabel(); renderCharts();
  });
})();

// ---------- table ----------
const COLS=[
  {k:'ticker',t:'Ticker',s:'str'},{k:'removal_date',t:'Removed',s:'str'},
  {k:'first_day_out',t:'Day out',s:'str'},{k:'base_close',t:'Base $',s:'num'},
  {k:'lowest_pct',t:'Trough %',s:'num',col:1},{k:'days_to_low',t:'→ d',s:'num'},
  {k:'date_of_low',t:'Trough date',s:'str'},
  {k:'highest_pct',t:'Peak %',s:'num',col:1},{k:'days_to_high',t:'→ d',s:'num'},
  {k:'date_of_high',t:'Peak date',s:'str'},
  {k:'one_year_pct',t:'1-yr %',s:'num',col:1},
  {k:'qqq_same_window_pct',t:'QQQ %',s:'num',col:1},
  {k:'excess_vs_qqq_pct',t:'Excess %',s:'num',col:1},
  {k:'data_days',t:'Days',s:'num'},{k:'truncated',t:'Trunc',s:'str'},
];
if(RAW.some(r=>'source' in r)) COLS.push({k:'source',t:'Src',s:'str'});

let sortKey='removal_date', sortDir=1;
const thead=document.querySelector('#tbl thead'), tbody=document.querySelector('#tbl tbody');
thead.innerHTML='<tr>'+COLS.map(c=>`<th data-k="${c.k}">${c.t}</th>`).join('')+'</tr>';
thead.querySelectorAll('th').forEach(th=>th.addEventListener('click',()=>{
  const k=th.dataset.k; if(sortKey===k) sortDir*=-1; else {sortKey=k; sortDir=1;} render();}));

function passFilters(r){
  if(document.getElementById('fTrunc').checked && r.truncated) return false;
  const y=yearOf(r), ymin=+document.getElementById('fYmin').value, ymax=+document.getElementById('fYmax').value;
  if(y<ymin || y>ymax) return false;
  const q=document.getElementById('fSearch').value.trim().toLowerCase();
  if(q && !String(r.ticker).toLowerCase().includes(q)) return false;
  return true;
}
function render(){
  const meta=COLS.find(c=>c.k===sortKey)||{s:'str'};
  const rows=RAW.filter(passFilters).sort((a,b)=>{
    let x=a[sortKey], y=b[sortKey];
    if(meta.s==='num'){ x=num(a,sortKey); y=num(b,sortKey);
      if(x==null) return 1; if(y==null) return -1; return (x-y)*sortDir; }
    return String(x).localeCompare(String(y))*sortDir;
  });
  tbody.innerHTML=rows.map(r=>'<tr>'+COLS.map(c=>{
    let v=r[c.k], cls='';
    if(c.k==='ticker'){ cls='tk'; v=`<a href="stocks.html#${r.ticker}-${r.removal_date}">${r.ticker}</a>`; }
    if(c.col){ const nv=num(r,c.k); cls=sign(nv); v=fmtPct(nv); }
    else if(c.k==='base_close') v=(v==null?'—':(+v).toFixed(2));
    else if(c.k==='truncated') v=v?'yes':'';
    else if(v==null) v='—';
    return `<td class="${cls}">${v}</td>`;
  }).join('')+'</tr>').join('');
  thead.querySelectorAll('th').forEach(th=>{
    th.classList.toggle('sorted', th.dataset.k===sortKey);
    th.classList.toggle('desc', th.dataset.k===sortKey && sortDir<0);});
  document.getElementById('tableCount').textContent=`${rows.length} of ${RAW.length} stocks`;
}
(function initFilters(){
  const ys=RAW.map(yearOf);
  document.getElementById('fYmin').value=Math.min(...ys);
  document.getElementById('fYmax').value=Math.max(...ys);
  ['fTrunc','fYmin','fYmax','fSearch'].forEach(id=>{
    const el=document.getElementById(id);
    el.addEventListener(el.type==='checkbox'?'change':'input', render);});
  render();
})();

</script>
</body>
</html>
"""


def main():
    df, rows = load_rows()
    html = HTML.replace("__ROWS__", json.dumps(rows))
    Path(OUT).parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(html)
    size = os.path.getsize(OUT) / 1024
    print(f"Wrote {OUT} ({size:.0f} KB, {len(rows)} rows embedded).\n")
    print("KEY TAKEAWAYS")
    print("=" * 64)
    for i, b in enumerate(takeaways(df), 1):
        print(f"{i}. {b}\n")
    print("Open dist/index.html in your browser (just double-click it).")


if __name__ == "__main__":
    main()
