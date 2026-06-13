#!/usr/bin/env python3
"""
Generate a single self-contained stocks.html: one analyst deep-dive page per
removed stock, with the daily series embedded (from the series/ cache produced
by export_series.py) and Chart.js from a CDN. Double-click to open; deep links
like stocks.html#ZM-2023-12-18 route to a specific stock.

Reads results_per_stock.csv (authoritative summary stats) + series/*.json
(daily aligned stock/QQQ series). Does not modify either source.
Run export_series.py first (it gates the numbers).
"""

import json
import os
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]   # repo root (this file lives in src/)
CSV = str(ROOT / "data" / "processed" / "results_per_stock.csv")
SERIES_DIR = str(ROOT / "data" / "processed" / "series")
OUT = str(ROOT / "dist" / "stocks.html")

STAT_COLS = ["ticker", "removal_date", "first_day_out", "last_day", "base_close",
             "lowest_pct", "days_to_low", "date_of_low",
             "highest_pct", "days_to_high", "date_of_high",
             "one_year_pct", "qqq_same_window_pct", "excess_vs_qqq_pct",
             "data_days", "truncated", "source"]


def load():
    if not os.path.exists(CSV):
        sys.exit(f"ERROR: {CSV} not found.")
    df = pd.read_csv(CSV, parse_dates=["removal_date"])
    df = df.sort_values("removal_date").reset_index(drop=True)
    stocks = []
    n_series = n_unavail = 0
    for _, r in df.iterrows():
        rd = r["removal_date"].strftime("%Y-%m-%d")
        rec = {"id": f"{r['ticker']}-{rd}"}
        for c in STAT_COLS:
            v = r[c]
            if c == "removal_date":
                v = rd
            elif c == "truncated":
                v = bool(v)
            elif pd.isna(v):
                v = None
            elif hasattr(v, "item"):
                v = v.item()
            rec[c] = v
        cp = os.path.join(SERIES_DIR, f"{r['ticker']}_{rd}.json")
        if os.path.exists(cp):
            entry = json.load(open(cp, encoding="utf-8"))
            if entry.get("available"):
                rec["available"] = True
                rec["dates"] = entry["dates"]
                rec["stock"] = entry["stock"]
                rec["qqq"] = entry["qqq"]
                n_series += 1
            else:
                rec["available"] = False
                rec["reason"] = entry.get("reason", "not fetchable")
                n_unavail += 1
        else:
            rec["available"] = False
            rec["reason"] = "no cached series (run export_series.py)"
            n_unavail += 1
        stocks.append(rec)
    print(f"Loaded {len(stocks)} stocks: {n_series} with daily series, "
          f"{n_unavail} degraded (no series).")
    return stocks


HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="icon" type="image/svg+xml" href="favicon.svg">
<title>Nasdaq-100 Removals — Stock Deep-Dives</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<script>
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
    --thbg:#f8fafc; --thhover:#eef2f6; --rowline:#f1f1f1; --rowhover:#f8fafc;
    --bnbg:#fef3c7; --bnbd:#f59e0b; --bnfg:#92400e;
    --green:#15803d; --red:#b91c1c;
    --grid:#eef0f2; --accent:#2563eb; --qqq:#9aa1ab;
    --band:rgba(100,116,139,.13); --ddfill:rgba(185,28,28,.14);
  }
  html[data-theme="dark"]{
    --bg:#0f1115; --fg:#e6e8ec; --muted:#9aa4b2; --faint:#6b7280; --line:#2a2f3a;
    --card:#171a21; --slate:#c7d0db;
    --thbg:#1c2029; --thhover:#222732; --rowline:#23272f; --rowhover:#1b1f27;
    --bnbg:#2a2410; --bnbd:#a16207; --bnfg:#fde68a;
    --green:#22c55e; --red:#f87171;
    --grid:#23282f; --accent:#60a5fa; --qqq:#6b7480;
    --band:rgba(148,163,184,.12); --ddfill:rgba(248,113,113,.13);
  }
  html{background:var(--bg)}
  *{box-sizing:border-box}
  body{margin:0;background:var(--bg);color:var(--fg);
    font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
    line-height:1.5;-webkit-font-smoothing:antialiased;
    font-variant-numeric:tabular-nums}
  .wrap{max-width:1100px;margin:0 auto;padding:28px 24px 80px}
  a{color:var(--accent);text-decoration:none}
  a:hover{text-decoration:underline}
  /* top nav */
  .topnav{display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin-bottom:22px}
  .topnav .home{font-size:13px}
  select,button{font:inherit}
  select#picker{font-size:14px;padding:7px 10px;border:1px solid var(--line);
    border-radius:8px;background:var(--card);color:var(--fg);min-width:230px}
  .navbtn,#themeBtn{background:var(--card);color:var(--fg);border:1px solid var(--line);
    border-radius:8px;padding:7px 11px;font-size:13px;cursor:pointer}
  .navbtn:hover,#themeBtn:hover{background:var(--thhover)}
  .navbtn:disabled{opacity:.4;cursor:default}
  .spacer{flex:1}
  .counter{color:var(--muted);font-size:12.5px}
  /* header */
  h1{font-size:30px;font-weight:680;margin:0;letter-spacing:-.02em}
  .subhead{color:var(--muted);font-size:14.5px;margin:4px 0 0}
  .badges{margin-top:10px;display:flex;gap:8px;flex-wrap:wrap}
  .badge{font-size:12px;font-weight:600;padding:3px 9px;border-radius:999px;
    border:1px solid var(--bnbd);background:var(--bnbg);color:var(--bnfg)}
  .badge.gray{background:var(--thbg);border-color:var(--line);color:var(--muted)}
  /* verdict */
  .verdict{display:grid;grid-template-columns:repeat(4,1fr);gap:13px;margin:22px 0 8px}
  .vc{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:15px 17px}
  .vc .v{font-size:25px;font-weight:680;letter-spacing:-.02em}
  .vc .l{color:var(--muted);font-size:12px;margin-bottom:5px;text-transform:uppercase;
    letter-spacing:.04em}
  .vc .s{color:var(--faint);font-size:11.5px;margin-top:3px}
  .pos{color:var(--green)} .neg{color:var(--red)}
  h2{font-size:16px;font-weight:600;margin:38px 0 3px;letter-spacing:-.01em}
  .cap{color:var(--muted);font-size:13px;font-style:italic;margin:0 0 14px}
  .chart-box{background:var(--card);border:1px solid var(--line);border-radius:12px;
    padding:14px 16px 8px}
  .chart-area{position:relative;height:340px}
  .chart-area.sm{height:240px}
  .ctrls{display:flex;justify-content:flex-end;gap:6px;margin-bottom:4px}
  .ctrls button{font-size:11.5px;padding:3px 9px;border:1px solid var(--line);
    border-radius:6px;background:var(--card);color:var(--muted);cursor:pointer}
  .ctrls button.on{background:var(--accent);color:#fff;border-color:var(--accent)}
  /* table */
  table{border-collapse:collapse;width:100%;font-size:13px;margin-top:2px}
  th,td{padding:8px 12px;text-align:right;border-bottom:1px solid var(--rowline)}
  th:first-child,td:first-child{text-align:left}
  thead th{color:var(--muted);font-weight:600;border-bottom:1px solid var(--line)}
  .commentary{background:var(--card);border:1px solid var(--line);border-radius:12px;
    padding:16px 20px;margin-top:14px;font-size:14.5px;line-height:1.65}
  .unavail{background:var(--card);border:1px dashed var(--bnbd);border-radius:12px;
    padding:18px 20px;color:var(--muted);font-size:14px}
  .foot{color:var(--faint);font-size:12px;margin-top:40px;text-align:center}
</style>
</head>
<body>
<div class="wrap">
  <div class="topnav">
    <a class="home" href="index.html">← Dashboard</a>
    <select id="picker"></select>
    <button class="navbtn" id="prev" title="Previous (←)">‹ Prev</button>
    <button class="navbtn" id="next" title="Next (→)">Next ›</button>
    <span class="counter" id="counter"></span>
    <span class="spacer"></span>
    <button id="themeBtn" type="button" aria-label="Toggle dark mode"></button>
  </div>
  <div id="page"></div>
  <p class="foot">Indexed-to-100 timelines · daily adjusted closes · QQQ benchmark over the
     identical window · charts via Chart.js</p>
</div>

<script>
const STOCKS = __STOCKS__;
const BY_ID = Object.fromEntries(STOCKS.map(s=>[s.id, s]));
const ORDER = STOCKS.map(s=>s.id);   // already sorted by removal date

const getCSS = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const fmtPct = v => (v==null||isNaN(v)) ? "—" : (v>=0?"+":"") + (+v).toFixed(1) + "%";
const sign = v => v==null?"":(+v>=0?"pos":"neg");
const CHARTS = [];
Chart.defaults.animation.duration = 200;
Chart.defaults.font.family = getComputedStyle(document.body).fontFamily;

// ---------- picker ----------
const picker = document.getElementById('picker');
picker.innerHTML = STOCKS.map(s=>{
  const r = s.one_year_pct==null ? '' : `  (${fmtPct(s.one_year_pct)})`;
  return `<option value="${s.id}">${s.ticker} · ${s.removal_date}${r}</option>`;
}).join('');
picker.addEventListener('change', ()=>{ location.hash = '#'+picker.value; });

// ---------- helpers for series math ----------
function indexed(arr){ const b=arr[0]; return arr.map(v=> v==null||b==null?null:v/b*100); }
function ret(arr,i,j){ if(arr[i]==null||arr[j]==null) return null; return (arr[j]/arr[i]-1)*100; }
function runningDD(arr){ let peak=-Infinity; return arr.map(v=>{ if(v==null) return null;
  if(v>peak) peak=v; return (v/peak-1)*100; }); }

// ---------- render one stock ----------
function destroyCharts(){ while(CHARTS.length){ try{CHARTS.pop().destroy();}catch(e){} } }

function render(id){
  destroyCharts();
  const s = BY_ID[id]; if(!s) return;
  picker.value = id;
  const idx = ORDER.indexOf(id);
  document.getElementById('prev').disabled = idx<=0;
  document.getElementById('next').disabled = idx>=ORDER.length-1;
  document.getElementById('counter').textContent = `${idx+1} of ${ORDER.length} · by removal date`;

  const badges = [];
  if(s.truncated) badges.push(`<span class="badge">Truncated — stopped trading after ${s.data_days} trading days</span>`);
  if(!s.available) badges.push(`<span class="badge">Data unavailable</span>`);
  if(s.source && s.source!=='yfinance') badges.push(`<span class="badge gray">source: ${s.source}</span>`);

  const head = `
    <h1>${s.ticker}</h1>
    <p class="subhead">Removed from the Nasdaq-100 on <b>${s.removal_date}</b>
       · window ${s.first_day_out} → ${s.last_day} · ${s.data_days} trading days</p>
    <div class="badges">${badges.join('')}</div>`;

  const verdict = `
    <div class="verdict">
      <div class="vc"><div class="l">Trough</div>
        <div class="v ${sign(s.lowest_pct)}">${fmtPct(s.lowest_pct)}</div>
        <div class="s">${s.date_of_low} · day ${s.days_to_low}</div></div>
      <div class="vc"><div class="l">Peak</div>
        <div class="v ${sign(s.highest_pct)}">${fmtPct(s.highest_pct)}</div>
        <div class="s">${s.date_of_high} · day ${s.days_to_high}</div></div>
      <div class="vc"><div class="l">1-Year Return</div>
        <div class="v ${sign(s.one_year_pct)}">${fmtPct(s.one_year_pct)}</div>
        <div class="s">vs first close out</div></div>
      <div class="vc"><div class="l">Excess vs QQQ</div>
        <div class="v ${sign(s.excess_vs_qqq_pct)}">${fmtPct(s.excess_vs_qqq_pct)}</div>
        <div class="s">QQQ ${fmtPct(s.qqq_same_window_pct)} same window</div></div>
    </div>`;

  if(!s.available){
    document.getElementById('page').innerHTML = head + verdict + `
      <div class="unavail">The daily price series for <b>${s.ticker}</b> can no longer be
      retrieved from the data source (the ticker was delisted/acquired and its history was
      dropped). The summary figures above were computed when the study ran and remain valid,
      but the timeline charts cannot be drawn — and no prices are invented to fill the gap.</div>`;
    window.scrollTo(0,0);
    return;
  }

  document.getElementById('page').innerHTML = head + verdict + `
    <h2>Price path — indexed to 100 at the first close out</h2>
    <p class="cap">Solid = ${s.ticker}, dashed = QQQ, both set to 100 on day one (y-axis not
       zero-based). Shaded band spans the peak→trough drawdown. Toggle linear/log at right.</p>
    <div class="chart-box"><div class="ctrls">
        <button id="scaleLin" class="on">Linear</button><button id="scaleLog">Log</button></div>
      <div class="chart-area"><canvas id="cMain"></canvas></div></div>

    <h2>Drawdown from the post-removal high</h2>
    <p class="cap">Percent below the highest close reached so far — how deep the pain got, and whether it recovered.</p>
    <div class="chart-box"><div class="chart-area sm"><canvas id="cDD"></canvas></div></div>

    <h2>Relative strength vs QQQ</h2>
    <p class="cap">The ${s.ticker}/QQQ ratio, set to 100 on day one. Rising = beating QQQ; falling = lagging it — isolates stock weakness from market weakness.</p>
    <div class="chart-box"><div class="chart-area sm"><canvas id="cRS"></canvas></div></div>

    <h2>Returns by window quarter</h2>
    <p class="cap">Each quarter = ~63 trading days of the post-removal window; the first 21 days are the index price-pressure window. Returns are within-period, not cumulative.</p>
    <div id="timeline"></div>

    <h2>Commentary</h2>
    <div class="commentary" id="commentary"></div>`;

  buildMain(s);
  buildDD(s);
  buildRS(s);
  buildTimeline(s);
  document.getElementById('commentary').innerHTML = commentary(s);
  window.scrollTo(0,0);
}

// ---------- main indexed chart ----------
function annotPlugin(s){
  return { id:'annot', afterDatasetsDraw(chart){
    const meta=chart.getDatasetMeta(0); if(!meta||!meta.data.length) return;
    const {ctx,chartArea}=chart;
    const pLo=meta.data[s.days_to_low], pHi=meta.data[s.days_to_high];
    if(pLo&&pHi){ const x1=Math.min(pLo.x,pHi.x), x2=Math.max(pLo.x,pHi.x);
      ctx.save(); ctx.fillStyle=getCSS('--band');
      ctx.fillRect(x1, chartArea.top, x2-x1, chartArea.bottom-chartArea.top); ctx.restore(); }
    const fg=getCSS('--fg'), card=getCSS('--card');
    function mark(p,val,label,below){ if(!p) return; const col = val>=0?getCSS('--green'):getCSS('--red');
      ctx.save(); ctx.fillStyle=col; ctx.strokeStyle=card; ctx.lineWidth=2;
      ctx.beginPath(); ctx.arc(p.x,p.y,4.5,0,Math.PI*2); ctx.fill(); ctx.stroke();
      ctx.fillStyle=fg; ctx.font='11px system-ui'; ctx.textAlign='center';
      ctx.fillText(label, p.x, below? p.y+16 : p.y-9); ctx.restore(); }
    mark(pHi, s.highest_pct, 'Peak '+fmtPct(s.highest_pct), false);
    mark(pLo, s.lowest_pct, 'Trough '+fmtPct(s.lowest_pct), true);
  }};
}
function buildMain(s){
  const sIdx=indexed(s.stock), qIdx=indexed(s.qqq);
  const mk=(data,color,dash,w)=>({data, borderColor:color, borderWidth:w, borderDash:dash,
     pointRadius:0, pointHoverRadius:3, spanGaps:false, tension:0});
  const c = new Chart(document.getElementById('cMain'), {
    type:'line',
    data:{labels:s.dates, datasets:[
      Object.assign(mk(sIdx, getCSS('--accent'), [], 2.2), {label:s.ticker}),
      Object.assign(mk(qIdx, getCSS('--qqq'), [5,4], 1.5), {label:'QQQ'})]},
    options:{responsive:true, maintainAspectRatio:false, interaction:{mode:'index',intersect:false},
      plugins:{legend:{display:true, labels:{boxWidth:18, font:{size:11}, color:getCSS('--muted')}},
        tooltip:{callbacks:{
          title:i=>i[0].label,
          label:c=>{ const v=c.parsed.y; if(v==null) return c.dataset.label+': —';
            return `${c.dataset.label}: ${v.toFixed(1)} (${fmtPct(v-100)})`; }}}},
      scales:{
        x:{grid:{display:false}, ticks:{maxTicksLimit:8, maxRotation:0, font:{size:10}, color:getCSS('--muted')}},
        y:{type:'linear', grid:{color:getCSS('--grid')}, ticks:{font:{size:10}, color:getCSS('--muted')},
           title:{display:true, text:'Indexed (100 = first close out)', font:{size:11}, color:getCSS('--muted')}}}},
    plugins:[annotPlugin(s)]
  });
  CHARTS.push(c);
  const lin=document.getElementById('scaleLin'), log=document.getElementById('scaleLog');
  lin.onclick=()=>{ c.options.scales.y.type='linear'; lin.classList.add('on'); log.classList.remove('on'); c.update(); };
  log.onclick=()=>{ c.options.scales.y.type='logarithmic'; log.classList.add('on'); lin.classList.remove('on'); c.update(); };
}

// ---------- drawdown ----------
function buildDD(s){
  const dd=runningDD(s.stock);
  CHARTS.push(new Chart(document.getElementById('cDD'), {
    type:'line',
    data:{labels:s.dates, datasets:[{data:dd, borderColor:getCSS('--red'), borderWidth:1.6,
      backgroundColor:getCSS('--ddfill'), fill:true, pointRadius:0, pointHoverRadius:3,
      spanGaps:false, tension:0}]},
    options:{responsive:true, maintainAspectRatio:false, interaction:{mode:'index',intersect:false},
      plugins:{legend:{display:false}, tooltip:{callbacks:{
        title:i=>i[0].label, label:c=>`Drawdown: ${fmtPct(c.parsed.y)}`}}},
      scales:{x:{grid:{display:false}, ticks:{maxTicksLimit:8, maxRotation:0, font:{size:10}, color:getCSS('--muted')}},
        y:{grid:{color:getCSS('--grid')}, ticks:{callback:v=>v+'%', font:{size:10}, color:getCSS('--muted')},
           title:{display:true, text:'Drawdown from prior high (%)', font:{size:11}, color:getCSS('--muted')}}}}
  }));
}

// ---------- relative strength ----------
function rsBaseline(){ return { id:'rsbase', afterDraw(chart){
  const {ctx,chartArea,scales:{y}}=chart; const yy=y.getPixelForValue(100);
  if(yy<chartArea.top||yy>chartArea.bottom) return;
  ctx.save(); ctx.strokeStyle=getCSS('--muted'); ctx.globalAlpha=.5; ctx.setLineDash([3,3]);
  ctx.beginPath(); ctx.moveTo(chartArea.left,yy); ctx.lineTo(chartArea.right,yy); ctx.stroke(); ctx.restore();
}};}
function buildRS(s){
  const rs=s.stock.map((v,i)=> (v==null||s.qqq[i]==null)?null:(v/s.qqq[i]));
  const rsIdx=indexed(rs);
  CHARTS.push(new Chart(document.getElementById('cRS'), {
    type:'line',
    data:{labels:s.dates, datasets:[{data:rsIdx, borderColor:getCSS('--accent'), borderWidth:1.8,
      pointRadius:0, pointHoverRadius:3, spanGaps:false, tension:0}]},
    options:{responsive:true, maintainAspectRatio:false, interaction:{mode:'index',intersect:false},
      plugins:{legend:{display:false}, tooltip:{callbacks:{
        title:i=>i[0].label, label:c=>`${s.ticker}/QQQ: ${c.parsed.y==null?'—':c.parsed.y.toFixed(1)} (${fmtPct(c.parsed.y-100)})`}}},
      scales:{x:{grid:{display:false}, ticks:{maxTicksLimit:8, maxRotation:0, font:{size:10}, color:getCSS('--muted')}},
        y:{grid:{color:getCSS('--grid')}, ticks:{font:{size:10}, color:getCSS('--muted')},
           title:{display:true, text:'Stock ÷ QQQ (100 = day one)', font:{size:11}, color:getCSS('--muted')}}}},
    plugins:[rsBaseline()]
  }));
}

// ---------- timeline table ----------
function buildTimeline(s){
  const n=s.stock.length, last=n-1;
  const bounds=[[0,21,'First 21 days'],
                [0,63,'Quarter 1'],[63,126,'Quarter 2'],[126,189,'Quarter 3'],[189,252,'Quarter 4'],
                [0,252,'Full window']];
  const cell=v=> v==null?'<td>—</td>':`<td class="${sign(v)}">${fmtPct(v)}</td>`;
  const rows=bounds.map(([a,b,label])=>{
    if(a>=last){   // period begins at/after the last available bar -> no data
      return `<tr><td>${label}<div style="color:var(--faint);font-size:11px">no data in window</div></td>${cell(null)}${cell(null)}${cell(null)}</tr>`;
    }
    const i=a, j=Math.min(b,last);
    const partial = b>last && label.indexOf('Quarter')===0;
    const sr=ret(s.stock,i,j), qr=ret(s.qqq,i,j);
    const ex = (sr==null||qr==null)?null:sr-qr;
    const dr = `${s.dates[i]} → ${s.dates[j]}`;
    return `<tr><td>${label}${partial?' *':''}<div style="color:var(--faint);font-size:11px">${dr}</div></td>${cell(sr)}${cell(qr)}${cell(ex)}</tr>`;
  }).join('');
  document.getElementById('timeline').innerHTML =
    `<table><thead><tr><th>Period</th><th>${s.ticker}</th><th>QQQ</th><th>Excess</th></tr></thead>
     <tbody>${rows}</tbody></table>` +
    (s.truncated?`<p class="cap" style="margin-top:8px">* window ended after ${s.data_days} trading days; later quarters clipped to available data.</p>`:'');
}

// ---------- price-only commentary ----------
function commentary(s){
  const dir = s.one_year_pct>=0 ? 'gained' : 'lost';
  const mag = Math.abs(s.one_year_pct).toFixed(1);
  const dd = runningDD(s.stock); const maxdd = Math.min(...dd.filter(v=>v!=null));
  const first21 = ret(s.stock,0,Math.min(21,s.stock.length-1));
  const reclaimed = s.highest_pct>0;
  const beat = s.excess_vs_qqq_pct!=null && s.excess_vs_qqq_pct>=0;
  const parts=[];
  parts.push(`Over the ${s.data_days} trading days after leaving the index${s.truncated?' (its window was cut short when trading stopped)':''}, <b>${s.ticker}</b> ${dir} <b>${mag}%</b> versus its first close out.`);
  parts.push(`It bottomed at ${fmtPct(s.lowest_pct)} on ${s.date_of_low} (trading day ${s.days_to_low}) and reached its high of ${fmtPct(s.highest_pct)} on ${s.date_of_high} (day ${s.days_to_high}).`);
  parts.push(reclaimed
    ? `It traded back above its exit price at some point during the window.`
    : `It never traded above its exit price during the window.`);
  parts.push(`Its deepest drawdown from a post-removal high was ${fmtPct(maxdd)}.`);
  if(first21!=null) parts.push(`In the first 21 trading days — the window when index-fund selling pressure is greatest — it moved ${fmtPct(first21)}.`);
  if(s.excess_vs_qqq_pct!=null) parts.push(`Measured against QQQ over the same window, it ${beat?'outperformed':'lagged'} the benchmark by ${Math.abs(s.excess_vs_qqq_pct).toFixed(1)} points (QQQ ${fmtPct(s.qqq_same_window_pct)}).`);
  return parts.join(' ');
}

// ---------- routing + nav ----------
function go(id){ if(BY_ID[id]) location.hash='#'+id; }
function current(){ const h=decodeURIComponent(location.hash.slice(1)); return BY_ID[h]?h:ORDER[0]; }
function onHash(){ render(current()); }
window.addEventListener('hashchange', onHash);
document.getElementById('prev').onclick=()=>{ const i=ORDER.indexOf(current()); if(i>0) go(ORDER[i-1]); };
document.getElementById('next').onclick=()=>{ const i=ORDER.indexOf(current()); if(i<ORDER.length-1) go(ORDER[i+1]); };
document.addEventListener('keydown',e=>{
  if(e.target.tagName==='SELECT') return;
  if(e.key==='ArrowLeft') document.getElementById('prev').click();
  if(e.key==='ArrowRight') document.getElementById('next').click();
});

// ---------- theme toggle ----------
(function(){
  const btn=document.getElementById('themeBtn');
  const setLabel=()=>{ const d=document.documentElement.getAttribute('data-theme')==='dark';
    btn.textContent = d ? '☀ Light' : '🌙 Dark'; };
  setLabel();
  btn.addEventListener('click',()=>{
    const d=document.documentElement.getAttribute('data-theme')==='dark';
    const t=d?'light':'dark'; document.documentElement.setAttribute('data-theme',t);
    try{ localStorage.setItem('ndxtheme',t);}catch(e){}
    setLabel(); render(current());   // rebuild charts in new theme
  });
})();

onHash();   // initial render from hash (or first stock)
</script>
</body>
</html>
"""


def main():
    stocks = load()
    html = HTML.replace("__STOCKS__", json.dumps(stocks))
    Path(OUT).parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(html)
    size = os.path.getsize(OUT) / (1024 * 1024)
    print(f"Wrote {OUT} ({size:.2f} MB, {len(stocks)} stocks embedded; single self-contained file).")


if __name__ == "__main__":
    main()
