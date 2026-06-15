#!/usr/bin/env python3
r"""
Apply the analysis extensions (sections 1-3) and the zoom interaction layer (section 4)
to the BUILT pages dist/index.html and dist/stocks.html, in place.

This only ADDS: embedded aggregate JSON, a coverage panel, an average-path section,
a tenure scatter + archetype bar with bootstrap CIs, CIs on existing medians, and a
Chart.js zoom/pan layer. It preserves everything already in the files. It is idempotent
(re-running detects the marker and refuses to double-apply).

No raw daily series is embedded -- only the small aggregates from average_path.json,
survivorship.json, tenure.json, cis.json.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
PROC = ROOT / "data" / "processed"
MARKER = "/*NDX-EXT v1*/"


def read(p):
    return Path(p).read_text(encoding="utf-8")


def checked(text, old, new, label):
    c = text.count(old)
    if c != 1:
        sys.exit(f"ANCHOR ERROR [{label}]: expected exactly 1 match, found {c}.")
    return text.replace(old, new, 1)


# ---- payloads -------------------------------------------------------------
SURV = read(PROC / "survivorship.json")
AVG = read(PROC / "average_path.json")
TEN = read(PROC / "tenure.json")
CIS = read(PROC / "cis.json")

PLUGIN_TAGS = (
    '<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>\n'
    '<script src="https://cdn.jsdelivr.net/npm/hammerjs@2.0.8/hammer.min.js"></script>\n'
    '<script src="https://cdn.jsdelivr.net/npm/chartjs-plugin-zoom@2.0.1/dist/chartjs-plugin-zoom.min.js"></script>'
)
CHARTJS_TAG = '<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>'

# Zoom infrastructure inserted right after `const CHARTS = [];`. MODE = default pan/zoom
# mode for the file's charts ('xy' dashboard, 'x' time-series stock pages).
ZOOM_INFRA = r"""
""" + MARKER + r"""
/* zoom/pan layer: additive, inert until interaction, survives destroy()/rebuild.
   Registered once; config lives in Chart.defaults so every chart (existing + new,
   each rebuild) gets it at construction without per-chart wiring. */
(function(){ if(!window.Chart) return; try{ if(Chart.registry.plugins.get('zoom')) return; }catch(e){}
  var z=window.ChartZoom||window.chartjsPluginZoom||window['chartjs-plugin-zoom']||window.Zoom;
  if(z){ try{ Chart.register(z); }catch(e){} } })();
function zoomCfg(mode){ var lim={ x:{min:'original',max:'original'} };
  if(mode==='xy') lim.y={min:'original',max:'original'};
  return { zoom:{ wheel:{enabled:true, speed:0.1}, pinch:{enabled:true, speed:0.05}, drag:{enabled:false}, mode:mode },
           pan:{ enabled:true, mode:mode, threshold:10 }, limits:lim }; }
try{ if(window.Chart){ Chart.defaults.plugins.zoom = zoomCfg('__MODE__'); } }catch(e){}
/* double-click to reset to the current default view (incl. current log/linear scale) */
document.addEventListener('dblclick', function(e){
  var cv=e.target&&e.target.closest&&e.target.closest('canvas'); if(!cv||!window.Chart) return;
  var c=Chart.getChart(cv); if(c&&c.resetZoom) c.resetZoom(); });
"""

# ---- index.html: embedded data + merge onto RAW --------------------------
EMBED = ("\nconst SURV=" + SURV + ";\nconst AVGPATH=" + AVG + ";\nconst TENURE=" + TEN +
         ";\nconst CIS=" + CIS + ";\n"
         "RAW.forEach(function(r){ var t=TENURE[r.ticker+'-'+r.removal_date];"
         " if(t){ r.years_in_index=t.years_in_index; r.tenure_censored=t.tenure_censored;"
         " r.archetype=t.archetype; } });\n")

# ---- index.html: coverage panel (replaces the old banner IIFE) -----------
BANNER_OLD = """// ---------- banner ----------
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
})();"""

BANNER_NEW = r"""// ---------- coverage / survivorship panel (was: banner) ----------
(function(){
  const el=document.getElementById('banner'); const f=SURV.funnel;
  const fmt1=v=>v==null?'—':(v>=0?'+':'')+(+v).toFixed(1)+'%';
  const ci=c=>(!c||c.lo==null)?'':` <span class="cig">[${fmt1(c.lo)}, ${fmt1(c.hi)}]</span>`;
  const c1=(CIS.survivorship&&CIS.survivorship.one_year)||{};
  const seg=[['total',f.total,'--bar-total','all removals'],
             ['acquired',f.acquired_excluded,'--bar-acq','acquired / merged (excluded — not a loss)'],
             ['analyzed',f.analyzed,'--bar-an','analyzed (have a price series)'],
             ['missing',f.missing,'--bar-miss',`missing (${f.delisted} delisted + ${f.unknown} unknown)`]];
  const maxv=f.total;
  const bars=seg.map(s=>`<div class="cv-row"><span class="cv-lab">${s[0]}</span>
      <span class="cv-track"><span class="cv-fill" style="width:${(s[1]/maxv*100).toFixed(1)}%;background:var(${s[2]})"></span></span>
      <span class="cv-num">${s[1]}</span><span class="cv-note">${s[3]}</span></div>`).join('');
  const sc=[['Survivors only',SURV.one_year.survivors,'optimistic baseline',c1.survivors],
            ['Conservative floor',SURV.one_year.conservative,'+ delisted at −100%',c1.conservative],
            ['Most-defensible',SURV.one_year.defensible_best,'band (unknown best→worst)',c1.defensible_best]];
  const scen=sc.map(s=>`<div class="sc"><div class="sc-l">${s[0]}</div>
      <div class="sc-v ${s[1]>=0?'pos':'neg'}">${fmt1(s[1])}</div>
      <div class="sc-n">${s[2]}${ci(s[3])}</div></div>`).join('');
  const band=SURV.one_year;
  el.innerHTML = `<div class="cov">
    <div class="cov-head"><b>Coverage & survivorship.</b> Of <b>${f.total}</b> Nasdaq-100 removals in the window,
      <b>${f.analyzed}</b> have a usable post-removal price series — <b>${SURV.coverage_pct}%</b> of the
      <b>${f.eligible}</b> that should (acquisitions aside), <b>${SURV.coverage_pct_all}%</b> of all.
      The <b>${f.missing}</b> missing names (delisted/unresolved) are disproportionately the worst, so the raw medians are biased upward.</div>
    <div class="cov-grid">
      <div class="cv-funnel">${bars}</div>
      <div class="cv-scen"><div class="sc-title">Median 1-year return under three scenarios</div>
        <div class="sc-row">${scen}</div>
        <div class="sc-spread">Bias range on the headline: <b class="pos">${fmt1(band.survivors)}</b>
          down to <b class="neg">${fmt1(band.defensible_worst)}</b>
          (spread ${(band.survivors-band.defensible_worst).toFixed(1)} pp). Excess vs QQQ:
          <b>${fmt1(SURV.excess.survivors)}</b> → <b>${fmt1(SURV.excess.defensible_worst)}</b>.</div>
      </div>
    </div>
    <div class="cov-cap">Anchor on the <b>most-defensible</b> figure, not the survivors-only headline: it adds the
      acquired (market-neutral) and the known delisted losses, and brackets the unresolved names as a band.</div>
  </div>`;
})();"""

# ---- index.html: cards with CI (replaces the old cards IIFE) -------------
CARDS_OLD = """// ---------- cards ----------
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
})();"""

CARDS_NEW = r"""// ---------- cards (with bootstrap 95% CIs) ----------
(function(){
  const all=RAW, full=RAW.filter(r=>!r.truncated);
  const med=(arr,k)=>median(arr.map(r=>num(r,k)).filter(v=>v!=null));
  const pct=(arr,fn)=>arr.length? (arr.filter(fn).length/arr.length*100):null;
  const exFull=full.filter(r=>num(r,'excess_vs_qqq_pct')!=null);
  const O=CIS.overall||{};
  const ciTxt=c=>(!c||c.lo==null)?'':`95% CI [${(c.lo>=0?'+':'')+c.lo.toFixed(1)}%, ${(c.hi>=0?'+':'')+c.hi.toFixed(1)}%]`;
  const ciDay=c=>(!c||c.lo==null)?'':`95% CI [${Math.round(c.lo)}, ${Math.round(c.hi)}] d`;
  const cards=[
    {v:all.length, l:'stocks analyzed', n:'survivors with price data'},
    {v:fmtPct(med(all,'lowest_pct')), l:'median trough depth', cls:'neg', n:ciTxt(O.trough)||`all ${all.length}`},
    {v:Math.round(med(all,'days_to_low'))+' d', l:'median days to trough', n:ciDay(O.days_to_low)||'trading days after day 1'},
    {v:fmtPct(med(full,'one_year_pct')), l:'median 1-year return', cls:sign(med(full,'one_year_pct')), n:ciTxt(O.one_year)+` · n=${full.length}`},
    {v:pct(full,r=>num(r,'one_year_pct')>0).toFixed(0)+'%', l:'positive after 1 year', n:`full-year rows, n=${full.length}`},
    {v:exFull.length? pct(exFull,r=>num(r,'excess_vs_qqq_pct')>0).toFixed(0)+'%':'—',
      l:'beat QQQ (same window)', n:ciTxt(O.excess)+` · n=${exFull.length}`},
  ];
  document.getElementById('cards').innerHTML = cards.map(c=>
    `<div class="card"><div class="v ${c.cls||''}">${c.v}</div>
      <div class="l">${c.l}</div><div class="n">${c.n||''}</div></div>`).join('');
})();"""

# ---- index.html: drawByYear with CI error bars + small-n flag ------------
BYYEAR_OLD = """// ---------- by year ----------
function drawByYear(){
  const years=[...new Set(RAW.map(yearOf))].sort();
  const agg=years.map(y=>{ const g=RAW.filter(r=>yearOf(r)===y);
    return {y, m:median(g.map(r=>num(r,'one_year_pct')).filter(v=>v!=null)), n:g.length}; });
  const grid=getCSS('--grid'), tick=getCSS('--muted');
  const pos=getCSS('--posfill'), posb=getCSS('--posborder'),
        neg=getCSS('--negfill'), negb=getCSS('--negborder');
  CHARTS.push(new Chart(document.getElementById('byYear'), {
    type:'bar',
    data:{labels:agg.map(a=>`${a.y}\\n(n=${a.n})`),
      datasets:[{data:agg.map(a=>a.m),
        backgroundColor:agg.map(a=>a.m>=0?pos:neg),
        borderColor:agg.map(a=>a.m>=0?posb:negb), borderWidth:1}]},
    options:{responsive:true, maintainAspectRatio:false,
      plugins:{legend:{display:false},
        tooltip:{callbacks:{title:i=>agg[i[0].dataIndex].y,
          label:i=>`median ${fmtPct(i.raw)} · n=${agg[i.dataIndex].n}`}}},
      scales:{x:{grid:{display:false}, ticks:{font:{size:10}, color:tick,
          callback:function(v){return this.getLabelForValue(v).split('\\n');}}},
        y:{grid:{color:grid}, ticks:{callback:v=>v+'%',font:{size:10}, color:tick},
          title:{display:true,text:'median 1-yr return',font:{size:10}, color:tick}}}}
  }));
}"""

BYYEAR_NEW = r"""// ---------- by year (with bootstrap 95% CIs + small-n flag) ----------
function ciWhiskers(cis){ return { id:'ciw'+Math.random().toString(36).slice(2),
  afterDatasetsDraw(chart){ const m=chart.getDatasetMeta(0); const y=chart.scales.y; if(!m||!y) return;
    const ctx=chart.ctx; ctx.save(); ctx.strokeStyle=getCSS('--fg'); ctx.globalAlpha=.65; ctx.lineWidth=1;
    m.data.forEach((bar,i)=>{ const c=cis[i]; if(!c||c.lo==null||c.hi==null) return;
      const xp=bar.x, yl=y.getPixelForValue(c.lo), yh=y.getPixelForValue(c.hi);
      ctx.beginPath(); ctx.moveTo(xp,yl); ctx.lineTo(xp,yh);
      ctx.moveTo(xp-3.5,yl); ctx.lineTo(xp+3.5,yl); ctx.moveTo(xp-3.5,yh); ctx.lineTo(xp+3.5,yh); ctx.stroke(); });
    ctx.restore(); } }; }
function nLabels(ns){ return { id:'nl'+Math.random().toString(36).slice(2),
  afterDatasetsDraw(chart){ const m=chart.getDatasetMeta(0); const ca=chart.chartArea; if(!m) return;
    const ctx=chart.ctx; ctx.save(); ctx.fillStyle=getCSS('--faint'); ctx.font='9px system-ui'; ctx.textAlign='center';
    m.data.forEach((bar,i)=>{ if(ns[i]==null) return; ctx.fillText('n='+ns[i], bar.x, ca.bottom-3); }); ctx.restore(); } }; }
function drawByYear(){
  const years=[...new Set(RAW.map(yearOf))].sort();
  const byy=(CIS.by_year)||{};
  const agg=years.map(y=>{ const g=RAW.filter(r=>yearOf(r)===y); const c=byy[String(y)]||{};
    return {y, m:median(g.map(r=>num(r,'one_year_pct')).filter(v=>v!=null)), n:g.length,
            lo:c.lo, hi:c.hi, small:!!c.small}; });
  const grid=getCSS('--grid'), tick=getCSS('--muted');
  const pos=getCSS('--posfill'), posb=getCSS('--posborder'),
        neg=getCSS('--negfill'), negb=getCSS('--negborder'), mut=getCSS('--line');
  CHARTS.push(new Chart(document.getElementById('byYear'), {
    type:'bar',
    data:{labels:agg.map(a=>`${a.y}\n(n=${a.n})`),
      datasets:[{data:agg.map(a=>a.m),
        backgroundColor:agg.map(a=>a.small?mut:(a.m>=0?pos:neg)),
        borderColor:agg.map(a=>a.small?getCSS('--faint'):(a.m>=0?posb:negb)),
        borderWidth:1, borderDash:agg.map(a=>a.small?[3,2]:[])}]},
    options:{responsive:true, maintainAspectRatio:false,
      plugins:{legend:{display:false}, zoom:zoomCfg('y'),
        tooltip:{callbacks:{title:i=>agg[i[0].dataIndex].y,
          label:i=>{const a=agg[i.dataIndex]; const ci=(a.lo==null)?'':`  95% CI [${fmtPct(a.lo)}, ${fmtPct(a.hi)}]`;
            return `median ${fmtPct(i.raw)} · n=${a.n}${ci}${a.small?'  (small sample)':''}`;}}}},
      scales:{x:{grid:{display:false}, ticks:{font:{size:10}, color:tick,
          callback:function(v){return this.getLabelForValue(v).split('\n');}}},
        y:{grid:{color:grid}, ticks:{callback:v=>v+'%',font:{size:10}, color:tick},
          title:{display:true,text:'median 1-yr return',font:{size:10}, color:tick}}}},
    plugins:[ciWhiskers(agg.map(a=>({lo:a.lo,hi:a.hi}))), nLabels(agg.map(a=>a.n))]
  }));
}"""

# ---- index.html: new chart builders (avg-path, tenure, archetype) --------
NEW_BUILDERS = r"""// ---------- average path (headline) ----------
let avgChart=null, avgView='excess', avgPanel='all';
function baselineRef(base,label){ return { id:'bl'+Math.random().toString(36).slice(2),
  afterDatasetsDraw(chart){ const y=chart.scales.y, ca=chart.chartArea; if(!y) return; const yp=y.getPixelForValue(base);
    if(yp<ca.top||yp>ca.bottom) return; const ctx=chart.ctx; ctx.save();
    ctx.strokeStyle=getCSS('--muted'); ctx.globalAlpha=.6; ctx.setLineDash([4,4]); ctx.lineWidth=1;
    ctx.beginPath(); ctx.moveTo(ca.left,yp); ctx.lineTo(ca.right,yp); ctx.stroke();
    ctx.setLineDash([]); ctx.globalAlpha=1; ctx.fillStyle=getCSS('--muted'); ctx.font='10px system-ui';
    ctx.textAlign='left'; ctx.fillText(label, ca.left+4, yp-3); ctx.restore(); } }; }
function crossMark(off){ return { id:'cm'+Math.random().toString(36).slice(2),
  afterDatasetsDraw(chart){ if(off==null) return; const x=chart.scales.x, ca=chart.chartArea; if(!x) return;
    const xp=x.getPixelForValue(off); if(xp<ca.left||xp>ca.right) return; const ctx=chart.ctx; ctx.save();
    ctx.strokeStyle=getCSS('--slate'); ctx.globalAlpha=.45; ctx.setLineDash([2,3]); ctx.beginPath();
    ctx.moveTo(xp,ca.top); ctx.lineTo(xp,ca.bottom); ctx.stroke(); ctx.setLineDash([]); ctx.globalAlpha=1;
    ctx.fillStyle=getCSS('--muted'); ctx.font='10px system-ui'; ctx.textAlign='center';
    ctx.fillText('crosses @ d'+off, xp, ca.top+10); ctx.restore(); } }; }
function buildAvgPath(){
  if(avgChart){ try{avgChart.destroy();}catch(e){} avgChart=null; }
  const cv=document.getElementById('avgPath'); if(!cv||!AVGPATH) return;
  const off=AVGPATH.offsets, P=AVGPATH[avgPanel][avgView];
  const base = avgView==='raw'?100:0;
  const pts=k=>off.map((o,i)=>({x:o,y:P[k][i]}));
  const slate=getCSS('--slate'), band='rgba(100,116,139,0.18)', faint=getCSS('--faint');
  const cross = avgView==='raw' ? (AVGPATH.raw_cross_100||{})[avgPanel] : (AVGPATH.excess_cross_0||{})[avgPanel];
  avgChart=new Chart(cv,{ type:'line',
    data:{datasets:[
      {label:'p25', data:pts('p25'), borderColor:'transparent', pointRadius:0, fill:false, tension:.15, order:3},
      {label:'25–75%', data:pts('p75'), borderColor:'transparent', backgroundColor:band, pointRadius:0, fill:'-1', tension:.15, order:3},
      {label:'median', data:pts('median'), borderColor:slate, borderWidth:2.4, pointRadius:0, pointHoverRadius:3, fill:false, tension:.15, order:1},
      {label:'n(d)', data:pts('n'), yAxisID:'yN', borderColor:faint, borderWidth:1, borderDash:[3,3], pointRadius:0, fill:false, tension:0, order:4}
    ]},
    options:{responsive:true, maintainAspectRatio:false, interaction:{mode:'index',intersect:false},
      plugins:{ legend:{display:false},
        zoom: zoomCfg('x'),
        tooltip:{callbacks:{ title:i=>'trading day '+i[0].parsed.x,
          label:c=>{ if(c.dataset.label==='n(d)') return 'n = '+c.parsed.y;
            if(c.dataset.label==='p25'||c.dataset.label==='25–75%') return null;
            const u=avgView==='raw'?'':' pts'; return 'median: '+(c.parsed.y>=0?'+':'')+c.parsed.y.toFixed(1)+(avgView==='raw'?'':u); }}}},
      scales:{ x:{type:'linear', min:0, max:252, grid:{display:false}, title:{display:true,text:'trading days after removal',font:{size:11},color:getCSS('--muted')}, ticks:{font:{size:10},color:getCSS('--muted')}},
        y:{grid:{color:getCSS('--grid')}, ticks:{font:{size:10},color:getCSS('--muted'),callback:v=>avgView==='raw'?v:(v>=0?'+':'')+v},
           title:{display:true,text:avgView==='raw'?'indexed to 100 (first day out)':'points vs QQQ',font:{size:11},color:getCSS('--muted')}},
        yN:{position:'right', grid:{display:false}, ticks:{font:{size:9},color:getCSS('--faint'),maxTicksLimit:4}, title:{display:true,text:'n stocks',font:{size:9},color:getCSS('--faint')}, suggestedMin:0} }},
    plugins:[baselineRef(base, avgView==='raw'?'100 (flat)':'0 (= QQQ)'), crossMark(cross)]
  });
  document.getElementById('avgCap').textContent =
    `Median of all removed stocks at each trading-day offset (band = 25th–75th percentile), `+
    `${avgView==='raw'?'indexed to 100 at the first day out':'in points relative to QQQ'}; `+
    `${avgPanel==='all'?'all-available panel (right side is survivor-leaning as truncated names drop out)':'balanced panel (only full-252-day windows — the honest read for the back half)'}. `+
    `n starts at ${AVGPATH.n_start[avgPanel]}.`;
}
function setAvg(view,panel){ if(view) avgView=view; if(panel) avgPanel=panel;
  document.querySelectorAll('#avgCtrls [data-v]').forEach(b=>b.classList.toggle('on',b.dataset.v===avgView));
  document.querySelectorAll('#avgCtrls [data-p]').forEach(b=>b.classList.toggle('on',b.dataset.p===avgPanel));
  buildAvgPath(); }

// ---------- tenure scatter + archetype bar ----------
const ARCHES=[['revolving_door','Revolving door (<4y)'],['core_member','Core member (4–10y)'],['structural_decliner','Structural decliner (>10y)']];
function buildTenure(){
  const cv=document.getElementById('cTenure'); if(!cv) return;
  const rows=RAW.filter(r=>r.years_in_index!=null && num(r,'one_year_pct')!=null);
  const solid=rows.filter(r=>!r.tenure_censored), cens=rows.filter(r=>r.tenure_censored);
  const mk=r=>({x:+r.years_in_index, y:num(r,'one_year_pct'), t:r.ticker, d:r.removal_date, c:r.tenure_censored});
  // OLS fit on confirmed (non-censored) tenures only
  let line=[]; let slope=null;
  if(solid.length>=2){ const xs=solid.map(r=>+r.years_in_index), ys=solid.map(r=>num(r,'one_year_pct'));
    const n=xs.length, mx=xs.reduce((a,b)=>a+b)/n, my=ys.reduce((a,b)=>a+b)/n;
    let sxy=0,sxx=0; for(let i=0;i<n;i++){ sxy+=(xs[i]-mx)*(ys[i]-my); sxx+=(xs[i]-mx)**2; }
    slope=sxx?sxy/sxx:0; const b=my-slope*mx; const xlo=Math.min(...xs), xhi=Math.max(...xs);
    line=[{x:xlo,y:slope*xlo+b},{x:xhi,y:slope*xhi+b}]; }
  window.__tenureSlope=slope;
  const tick=getCSS('--muted'), grid=getCSS('--grid');
  CHARTS.push(new Chart(cv,{ type:'scatter',
    data:{datasets:[
      {label:'confirmed tenure', data:solid.map(mk), backgroundColor:getCSS('--dot'), radius:4, hoverRadius:6},
      {label:'censored (lower bound)', data:cens.map(mk), backgroundColor:'transparent', borderColor:getCSS('--slate'), borderWidth:1.2, pointStyle:'triangle', radius:5, hoverRadius:7},
      {label:'trend', type:'line', data:line, borderColor:getCSS('--red'), borderWidth:1.6, borderDash:[6,4], pointRadius:0, fill:false}
    ]},
    options:{responsive:true, maintainAspectRatio:false,
      plugins:{legend:{display:true, labels:{boxWidth:10, font:{size:10}, color:tick, filter:i=>i.text!=='trend'}},
        tooltip:{callbacks:{label:c=>c.raw.t?`${c.raw.t} (${c.raw.d}): ${c.raw.x.toFixed(1)}y${c.raw.c?'+ (censored)':''}, ${fmtPct(c.raw.y)}`:''}}},
      scales:{x:{title:{display:true,text:'years in the index (tenure)',font:{size:11},color:tick}, grid:{color:grid}, ticks:{font:{size:10},color:tick}, min:0},
        y:{title:{display:true,text:'1-year return %',font:{size:11},color:tick}, grid:{color:grid}, ticks:{font:{size:10},color:tick}}}}
  }));
}
function buildArchetype(){
  const cv=document.getElementById('cArche'); if(!cv) return;
  const ba=(CIS.by_archetype)||{};
  const med1=[],medE=[],ns=[],ci1=[],ciE=[],small=[];
  ARCHES.forEach(([k])=>{ const g=RAW.filter(r=>r.archetype===k);
    med1.push(median(g.map(r=>num(r,'one_year_pct')).filter(v=>v!=null)));
    medE.push(median(g.map(r=>num(r,'excess_vs_qqq_pct')).filter(v=>v!=null)));
    ns.push(g.length);
    const c=ba[k]||{}; ci1.push(c.one_year||{}); ciE.push(c.excess||{});
    small.push((c.one_year&&c.one_year.small)||g.length<5); });
  const tick=getCSS('--muted'), grid=getCSS('--grid');
  const c1col=getCSS('--barfill'), cEcol=getCSS('--dot');
  CHARTS.push(new Chart(cv,{ type:'bar',
    data:{labels:ARCHES.map(a=>a[1].split(' (')[0]),
      datasets:[
        {label:'median 1-yr return', data:med1, backgroundColor:small.map(s=>s?getCSS('--line'):c1col), borderColor:getCSS('--barborder'), borderWidth:1, borderDash:small.map(s=>s?[3,2]:[])},
        {label:'median excess vs QQQ', data:medE, backgroundColor:small.map(s=>s?getCSS('--line'):cEcol), borderColor:getCSS('--slate'), borderWidth:1, borderDash:small.map(s=>s?[3,2]:[])}
      ]},
    options:{responsive:true, maintainAspectRatio:false,
      plugins:{legend:{display:true, labels:{boxWidth:10,font:{size:10},color:tick}}, zoom:zoomCfg('y'),
        tooltip:{callbacks:{ afterBody:items=>{const i=items[0].dataIndex; return 'n='+ns[i]+(small[i]?'  (small sample — read with caution)':'');},
          label:it=>{ const i=it.dataIndex; const c=it.datasetIndex===0?ci1[i]:ciE[i];
            const cs=(c&&c.lo!=null)?`  95% CI [${fmtPct(c.lo)}, ${fmtPct(c.hi)}]`:''; return `${it.dataset.label}: ${fmtPct(it.raw)}${cs}`; }}}},
      scales:{x:{grid:{display:false}, ticks:{font:{size:10},color:tick}},
        y:{grid:{color:grid}, ticks:{callback:v=>v+'%',font:{size:10},color:tick}, title:{display:true,text:'median %',font:{size:10},color:tick}}}},
    plugins:[ ciWhiskers2(ci1,ciE), nLabels2(ns) ]
  }));
}
function ciWhiskers2(ci1,ciE){ return { id:'aw'+Math.random().toString(36).slice(2),
  afterDatasetsDraw(chart){ const y=chart.scales.y; if(!y) return; const ctx=chart.ctx; ctx.save();
    ctx.strokeStyle=getCSS('--fg'); ctx.globalAlpha=.6; ctx.lineWidth=1;
    [0,1].forEach(di=>{ const m=chart.getDatasetMeta(di); const arr=di===0?ci1:ciE;
      m.data.forEach((bar,i)=>{ const c=arr[i]; if(!c||c.lo==null) return; const xp=bar.x,
        yl=y.getPixelForValue(c.lo), yh=y.getPixelForValue(c.hi);
        ctx.beginPath(); ctx.moveTo(xp,yl); ctx.lineTo(xp,yh);
        ctx.moveTo(xp-3,yl); ctx.lineTo(xp+3,yl); ctx.moveTo(xp-3,yh); ctx.lineTo(xp+3,yh); ctx.stroke(); }); });
    ctx.restore(); } }; }
function nLabels2(ns){ return { id:'an'+Math.random().toString(36).slice(2),
  afterDatasetsDraw(chart){ const m=chart.getDatasetMeta(0); const ca=chart.chartArea; const ctx=chart.ctx;
    ctx.save(); ctx.fillStyle=getCSS('--faint'); ctx.font='9px system-ui'; ctx.textAlign='center';
    m.data.forEach((bar,i)=>{ ctx.fillText('n='+ns[i], bar.x, ca.bottom-3); }); ctx.restore(); } }; }

"""

# ---- index.html: HTML sections -------------------------------------------
AVG_SECTION = """  <h2>The average path — what the typical removed stock does</h2>
  <p class="cap">Median across all removed stocks at each trading day after removal, with the 25th–75th percentile band.
     Default view is relative to QQQ; toggle the raw indexed view and the balanced panel.</p>
  <div class="chart-box">
    <div class="ctrls2" id="avgCtrls">
      <span class="cg"><button data-v="excess" class="on" type="button">vs QQQ</button><button data-v="raw" type="button">Raw</button></span>
      <span class="cg"><button data-p="all" class="on" type="button">All available</button><button data-p="balanced" type="button">Balanced panel</button></span>
    </div>
    <div class="chart-area tall"><canvas id="avgPath"></canvas></div>
    <p class="cap" id="avgCap"></p>
  </div>

"""

TENURE_SECTION = """  <h2>Tenure & archetype — does time in the index matter?</h2>
  <p class="cap">Hypothesis: do short-tenure “revolving-door” removals recover differently from long-tenure “structural decliners”?
     Thresholds (&lt;4y / &gt;10y) are adjustable; censored points are lower bounds (pre-2007 originals), styled distinctly.</p>
  <div class="grid2">
    <div class="chart-box"><div class="chart-area"><canvas id="cTenure"></canvas></div>
      <p class="cap">Each point = one removal: years in the index (x) vs 1-year return (y). Dashed line = OLS fit on confirmed tenures only.</p></div>
    <div class="chart-box"><div class="chart-area"><canvas id="cArche"></canvas></div>
      <p class="cap">Median 1-year return and median excess vs QQQ by archetype, with bootstrap 95% CIs (whiskers) and n; muted/dashed = small sample (n&lt;5).</p></div>
  </div>

"""

# ---- CSS ------------------------------------------------------------------
CSS = """  /* ---- analysis extensions ---- */
  :root{ --bar-total:#94a3b8; --bar-acq:#cbd5e1; --bar-an:#22a06b; --bar-miss:#e06666; }
  html[data-theme="dark"]{ --bar-total:#64748b; --bar-acq:#475569; --bar-an:#2dd4a7; --bar-miss:#f87171; }
  .cov{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px 18px;margin:0 0 16px;font-size:13.5px}
  .cov-head{margin-bottom:16px;line-height:1.5}
  .cov-grid{display:grid;grid-template-columns:1.05fr 1fr;gap:22px;align-items:start}
  .cv-row{display:grid;grid-template-columns:62px 1fr auto;align-items:center;gap:8px;margin:5px 0;font-size:12px}
  .cv-lab{color:var(--muted);text-transform:uppercase;letter-spacing:.03em;font-size:10.5px}
  .cv-track{background:var(--thbg);border-radius:5px;height:14px;overflow:hidden}
  .cv-fill{display:block;height:100%;border-radius:5px}
  .cv-num{font-weight:650;font-variant-numeric:tabular-nums}
  .cv-note{grid-column:2 / 4;color:var(--faint);font-size:10.5px;margin-top:-2px}
  .cv-scen .sc-title{font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.03em;margin-bottom:8px}
  .sc-row{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}
  .sc{background:var(--thbg);border:1px solid var(--line);border-radius:9px;padding:9px 10px}
  .sc-l{font-size:11px;color:var(--muted)} .sc-v{font-size:20px;font-weight:680;letter-spacing:-.02em}
  .sc-n{font-size:10.5px;color:var(--faint);margin-top:1px} .cig{color:var(--faint)}
  .sc-spread{margin-top:10px;font-size:12px;color:var(--slate);line-height:1.5}
  .cov-cap{margin-top:16px;color:var(--muted);font-size:12.5px;font-style:italic;line-height:1.5}
  .ctrls2{display:flex;flex-wrap:wrap;gap:14px;justify-content:flex-end;margin-bottom:6px}
  .ctrls2 .cg{display:inline-flex;border:1px solid var(--line);border-radius:7px;overflow:hidden}
  .ctrls2 button{font:inherit;font-size:11.5px;padding:5px 11px;border:none;background:var(--card);color:var(--muted);cursor:pointer;min-height:30px}
  .ctrls2 button+button{border-left:1px solid var(--line)}
  .ctrls2 button.on{background:var(--slate);color:var(--card)}
  @media (max-width:640px){ .cov-grid{grid-template-columns:1fr;gap:16px} .ctrls2{justify-content:flex-start} }
"""


def patch_index(html):
    if MARKER in html:
        print("index.html already extended (marker present) — skipping.")
        return html
    # 1. plugin tags
    html = checked(html, CHARTJS_TAG, PLUGIN_TAGS, "index chartjs tag")
    # 2. zoom infra (xy default) after CHARTS
    html = checked(html, "const CHARTS = [];",
                   "const CHARTS = [];\n" + ZOOM_INFRA.replace("__MODE__", "xy"), "index CHARTS")
    # 3. embedded data before helpers comment
    html = checked(html, "// ---------- helpers ----------",
                   EMBED + "\n// ---------- helpers ----------", "index embed")
    # 4. banner -> coverage panel
    html = checked(html, BANNER_OLD, BANNER_NEW, "index banner")
    # 5. cards with CI
    html = checked(html, CARDS_OLD, CARDS_NEW, "index cards")
    # 6. drawByYear with error bars
    html = checked(html, BYYEAR_OLD, BYYEAR_NEW, "index byYear")
    # 6b. histograms -> y-only zoom (category x collapses on zoom-out otherwise)
    html = checked(html, """      plugins:{legend:{display:false},
        tooltip:{callbacks:{title:i=>label,""",
                   """      plugins:{legend:{display:false}, zoom:zoomCfg('y'),
        tooltip:{callbacks:{title:i=>label,""", "index histo zoom")
    # 7. new builders before renderCharts
    html = checked(html, "// ---------- render all charts (re-run on theme change) ----------",
                   NEW_BUILDERS + "// ---------- render all charts (re-run on theme change) ----------",
                   "index builders")
    # 8. call new builders inside renderCharts
    html = checked(html, "\n  drawByYear();\n",
                   "\n  drawByYear();\n  buildAvgPath(); buildTenure(); buildArchetype();\n", "index renderCharts calls")
    # 9. avg-path section
    html = checked(html, "  <h2>Distributions</h2>", AVG_SECTION + "  <h2>Distributions</h2>", "index avg section")
    # 10. tenure section
    html = checked(html, "  <h2>Every stock</h2>", TENURE_SECTION + "  <h2>Every stock</h2>", "index tenure section")
    # 11. CSS + 12. toggle wiring (append near end of script, before theme toggle IIFE)
    html = checked(html, "</style>", CSS + "</style>", "index css")
    wiring = ("\n// avg-path toggle wiring\n(function(){ var c=document.getElementById('avgCtrls');"
              " if(!c) return; c.addEventListener('click',function(e){ var b=e.target.closest('button'); if(!b) return;"
              " if(b.dataset.v) setAvg(b.dataset.v,null); else if(b.dataset.p) setAvg(null,b.dataset.p); }); })();\n")
    html = checked(html, "// ---------- theme toggle ----------",
                   wiring + "// ---------- theme toggle ----------", "index wiring")
    return html


def patch_stocks(html):
    if MARKER in html:
        print("stocks.html already extended (marker present) — skipping.")
        return html
    html = checked(html, CHARTJS_TAG, PLUGIN_TAGS, "stocks chartjs tag")
    html = checked(html, "const CHARTS = [];",
                   "const CHARTS = [];\n" + ZOOM_INFRA.replace("__MODE__", "x"), "stocks CHARTS")
    return html


def main():
    idx = DIST / "index.html"
    stk = DIST / "stocks.html"
    ih = patch_index(read(idx))
    idx.write_text(ih, encoding="utf-8")
    sh = patch_stocks(read(stk))
    stk.write_text(sh, encoding="utf-8")
    print(f"index.html  -> {len(ih)/1024:.0f} KB")
    print(f"stocks.html -> {len(sh)/1024:.0f} KB")
    print("Applied extensions + zoom layer.")


if __name__ == "__main__":
    main()
