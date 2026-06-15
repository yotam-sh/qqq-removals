#!/usr/bin/env python3
r"""
Pass-2 injector: adds round-trip/ultimate-fate, deletion-effect explainer, market-regime
layer, sector + comparables, the grounded abstract, and the what-if basket to the BUILT
pages. Idempotent (marker /*NDX-EXT2*/); requires pass-1 (/*NDX-EXT v1*/) already applied.

Only ADDS; preserves existing UI. New charts join the existing CHARTS registry and get
zoom at construction via zoomCfg (bars -> 'y', doughnut zoom disabled — no axes). New
per-ticker fields are merged onto RAW (index) and STOCKS (stocks) the way pass-1 merges
TENURE. Embeds only small aggregates (no raw series into index.html).
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
PROC = ROOT / "data" / "processed"
MARKER = "/*NDX-EXT2*/"


def read(p):
    return Path(p).read_text(encoding="utf-8")


def checked(t, old, new, label):
    c = t.count(old)
    if c != 1:
        sys.exit(f"ANCHOR ERROR [{label}]: expected 1 match, found {c}.")
    return t.replace(old, new, 1)


RT = read(PROC / "roundtrip.json")
REG = read(PROC / "regime.json")
SEC = read(PROC / "sectors.json")
ABS = read(PROC / "abstract.json")
COMP = read(PROC / "comparables.json")

# ============================ INDEX.HTML ============================
IDX_EMBED = ("\n" + MARKER + "\nconst ROUNDTRIP=" + RT + ";\nconst REGIME=" + REG +
             ";\nconst SECTORS=" + SEC + ";\nconst ABSTRACT=" + ABS + ";\n"
             "RAW.forEach(function(r){ var k=r.ticker+'-'+r.removal_date;"
             " var rt=ROUNDTRIP.per_id[k]; if(rt){ r.ultimate_fate=rt.ultimate_fate; r.re_added=rt.re_added; r.round_trip_years=rt.round_trip_years; }"
             " var rg=REGIME.per_id[k]; if(rg){ r.market_regime=rg.market_regime; r.episode=rg.episode; }"
             " var sc=SECTORS.per_id[k]; if(sc){ r.sector=sc.sector; } });\n"
             r"""(function(){ var el=document.getElementById('abstract'); if(!el||!ABSTRACT) return;
  el.innerHTML='<div class="abx"><div class="abx-h">Executive summary — auto-generated from the computed figures</div>'+
    ABSTRACT.sentences.map(function(t){return '<p>'+t+'</p>';}).join('')+
    '<p class="abx-cav">'+ABSTRACT.caveat+'</p></div>'; })();
(function(){ var el=document.getElementById('exBody'); if(!el) return;
  var F=(ABSTRACT&&ABSTRACT.figures)||{};
  function p(v){ return v==null?'—':((v>=0?'+':'')+(+v).toFixed(1)+'%'); }
  var trough=F.median_trough_pct, day=F.median_days_to_low, endp=F.avgpath_end_pct,
      pos=F.pct_positive, beat=F.pct_beat_qqq;
  var ev = (trough!=null) ? ('In this dataset the median removed stock bottomed at <b>'+p(trough)+'</b> around trading day <b>'+
      (day!=null?Math.round(day):'—')+'</b>, and the median indexed path stood at <b>'+(endp!=null?p(endp):'—')+
      '</b> by day 252'+(pos!=null?(' — <b>'+pos+'%</b> finished positive'):'')+(beat!=null?(', but only <b>'+beat+'%</b> beat QQQ').toString():'')+
      '. Read as an upper bound (survivorship).') : '';
  el.innerHTML =
   '<h4>What happens each December</h4><p>Nasdaq re-ranks eligible companies by market capitalization at its annual reconstitution; '+
   'the smallest current members can be dropped and replaced. Removals also occur off-cycle when a name falls below minimum-weight rules or changes its listing exchange.</p>'+
   '<h4>Why removal forces selling</h4><p>Funds that track the index — most visibly the QQQ ETF — must sell a removed name to keep matching the index, near the effective date and regardless of fundamentals. That is a burst of forced, price-insensitive selling concentrated in a short window.</p>'+
   '<h4>Two competing explanations (unresolved)</h4><p><b>Temporary price-pressure:</b> the forced selling pushes the price temporarily below fair value, and it rebounds once the selling clears. <b>Permanent information / downward-demand:</b> removal signals deterioration and shrinks the long-term investor base, so part of the drop persists. Which effect dominates is genuinely debated; this project does not resolve it.</p>'+
   '<h4>What this project’s own numbers show</h4><p>'+ev+'</p>'+
   '<p class="abx-cav">Mechanisms above are standard market structure. No specific academic studies, authors, or effect-size figures are cited — those would be added as a separately-sourced layer.</p>';
})();
""")

IDX_ABSTRACT_DIV = '  <div id="abstract"></div>\n  <div id="banner"></div>'

IDX_SECTIONS = r"""  <h2>Ultimate fate &amp; round-trips</h2>
  <p class="cap">After the one-year window, where did removed names land — and did any earn their way back into the index?</p>
  <div class="grid2">
    <div class="chart-box"><div class="chart-area"><canvas id="cFate"></canvas></div>
      <p class="cap">Ultimate fate across all 204 removals (re-added / still-out / acquired / delisted / unknown), derived from the index-change tables and universe.csv — present-day status not asserted.</p></div>
    <div class="chart-box"><div class="chart-area"><canvas id="cGap"></canvas></div>
      <p class="cap">For names that round-tripped, how many years until re-addition. Round-trips are the deletion-effect's strongest anecdote — a stock that fell, then earned its way back.</p></div>
  </div>

  <h2>Was it the stock or the market?</h2>
  <p class="cap">Median 1-year return and median excess vs QQQ grouped by the QQQ market regime over each window (n + 95% CI; muted = small sample). A −40% stock in a −38% market is a different story than −40% in a flat one.</p>
  <div class="chart-box"><div class="chart-area"><canvas id="cRegime"></canvas></div></div>

  <h2>Outcome by sector</h2>
  <p class="cap">Median 1-year return by GICS sector (n + 95% CI). Unknown sectors are excluded; small groups have wide bars — read with the CI.</p>
  <div class="chart-box"><div class="chart-area"><canvas id="cSector"></canvas></div></div>

  <h2>Tenure & archetype — does time in the index matter?</h2>"""

IDX_EXPLAINER = r"""  <details class="explainer" id="explainer">
    <summary>How to read the deletion effect — the mechanics behind these charts</summary>
    <div class="ex-body" id="exBody"></div>
  </details>
  <div class="caveats">"""

# new chart builders (reuse global getCSS / CHARTS / zoomCfg / ciWhiskers / nLabels / ciWhiskers2 / nLabels2)
IDX_BUILDERS = r"""// ---------- pass-2 charts: fate / gap / regime / sector ----------
function buildFate(){ var cv=document.getElementById('cFate'); if(!cv||!ROUNDTRIP) return;
  var d=ROUNDTRIP.fate_distribution||{}; var order=['re_added','still_out','acquired','delisted','unknown'];
  var cmap={re_added:getCSS('--posborder'),still_out:getCSS('--barfill'),acquired:getCSS('--faint'),delisted:getCSS('--negborder'),unknown:getCSS('--line')};
  var labels=[],data=[],colors=[]; order.forEach(function(k){ if(d[k]){ labels.push(k.replace(/_/g,' ')); data.push(d[k]); colors.push(cmap[k]); } });
  var tot=data.reduce(function(a,b){return a+b;},0);
  CHARTS.push(new Chart(cv,{type:'doughnut',
    data:{labels:labels,datasets:[{data:data,backgroundColor:colors,borderColor:getCSS('--card'),borderWidth:2}]},
    options:{responsive:true,maintainAspectRatio:false,
      plugins:{ zoom:{zoom:{wheel:{enabled:false},pinch:{enabled:false},drag:{enabled:false}},pan:{enabled:false}},
        legend:{position:'right',labels:{color:getCSS('--muted'),font:{size:11},boxWidth:12}},
        tooltip:{callbacks:{label:function(c){return c.label+': '+c.raw+' ('+(c.raw/tot*100).toFixed(0)+'%)';}}}}}}));
}
function buildGap(){ var cv=document.getElementById('cGap'); if(!cv||!ROUNDTRIP) return;
  var g=ROUNDTRIP.gap_years||[]; var box=cv.closest('.chart-box');
  if(!g.length){ if(box) box.style.display='none'; return; }
  var maxy=Math.max(1,Math.ceil(Math.max.apply(null,g))); var bins=[],labels=[];
  for(var i=0;i<maxy;i++){ bins.push(0); labels.push(i+'–'+(i+1)+'y'); }
  g.forEach(function(v){ var i=Math.min(Math.floor(v),maxy-1); if(i<0)i=0; bins[i]++; });
  CHARTS.push(new Chart(cv,{type:'bar',
    data:{labels:labels,datasets:[{data:bins,backgroundColor:getCSS('--barfill'),borderColor:getCSS('--barborder'),borderWidth:1}]},
    options:{responsive:true,maintainAspectRatio:false,
      plugins:{legend:{display:false}, zoom:zoomCfg('y'),
        tooltip:{callbacks:{title:function(i){return 'gap '+i[0].label;},label:function(i){return i.raw+' round-trips';}}}},
      scales:{x:{grid:{display:false},ticks:{font:{size:10},color:getCSS('--muted')}},
        y:{grid:{color:getCSS('--grid')},ticks:{precision:0,font:{size:10},color:getCSS('--muted')},title:{display:true,text:'# round-trips',font:{size:10},color:getCSS('--muted')}}}}}));
}
function buildRegime(){ var cv=document.getElementById('cRegime'); if(!cv||!REGIME) return;
  var br=REGIME.by_regime||{}; var order=(REGIME.order||Object.keys(br)).filter(function(r){return br[r]&&br[r].n>0;});
  var labels=order.map(function(r){return r.replace(/_/g,' ');});
  var ci1=order.map(function(r){return br[r].one_year;}), cie=order.map(function(r){return br[r].excess;}), ns=order.map(function(r){return br[r].n;});
  CHARTS.push(new Chart(cv,{type:'bar',
    data:{labels:labels,datasets:[
      {label:'median 1-yr return',data:ci1.map(function(c){return c.median;}),backgroundColor:getCSS('--barfill'),borderColor:getCSS('--barborder'),borderWidth:1},
      {label:'median excess vs QQQ',data:cie.map(function(c){return c.median;}),backgroundColor:getCSS('--dot'),borderColor:getCSS('--slate'),borderWidth:1}]},
    options:{responsive:true,maintainAspectRatio:false,
      plugins:{legend:{display:true,labels:{boxWidth:10,font:{size:10},color:getCSS('--muted')}}, zoom:zoomCfg('y'),
        tooltip:{callbacks:{afterBody:function(it){var i=it[0].dataIndex;return 'n='+ns[i];},
          label:function(it){var i=it.dataIndex;var c=it.datasetIndex===0?ci1[i]:cie[i];var cs=(c&&c.lo!=null)?'  95% CI ['+fmtPct(c.lo)+', '+fmtPct(c.hi)+']':'';return it.dataset.label+': '+fmtPct(it.raw)+cs;}}}},
      scales:{x:{grid:{display:false},ticks:{font:{size:10},color:getCSS('--muted')}},
        y:{grid:{color:getCSS('--grid')},ticks:{callback:function(v){return v+'%';},font:{size:10},color:getCSS('--muted')}}}},
    plugins:[ciWhiskers2(ci1,cie), nLabels2(ns)]}));
}
function buildSector(){ var cv=document.getElementById('cSector'); if(!cv||!SECTORS) return;
  var bs=SECTORS.by_sector||{}; var order=(SECTORS.order||Object.keys(bs));
  var ci1=order.map(function(s){return bs[s].one_year;}), ns=order.map(function(s){return bs[s].n;}), small=order.map(function(s){return bs[s].one_year.small;});
  CHARTS.push(new Chart(cv,{type:'bar',
    data:{labels:order,datasets:[{data:ci1.map(function(c){return c.median;}),
      backgroundColor:small.map(function(x){return x?getCSS('--line'):getCSS('--barfill');}),borderColor:getCSS('--barborder'),borderWidth:1}]},
    options:{responsive:true,maintainAspectRatio:false,
      plugins:{legend:{display:false}, zoom:zoomCfg('y'),
        tooltip:{callbacks:{afterBody:function(it){var i=it[0].dataIndex;return 'n='+ns[i]+(small[i]?'  (small sample)':'');},
          label:function(it){var i=it.dataIndex;var c=ci1[i];var cs=(c&&c.lo!=null)?'  95% CI ['+fmtPct(c.lo)+', '+fmtPct(c.hi)+']':'';return 'median 1-yr '+fmtPct(it.raw)+cs;}}}},
      scales:{x:{grid:{display:false},ticks:{font:{size:9},color:getCSS('--muted'),maxRotation:50,minRotation:30}},
        y:{grid:{color:getCSS('--grid')},ticks:{callback:function(v){return v+'%';},font:{size:10},color:getCSS('--muted')},title:{display:true,text:'median 1-yr return',font:{size:10},color:getCSS('--muted')}}}},
    plugins:[ciWhiskers(ci1), nLabels(ns)]}));
}
// ---------- what-if basket ----------
function updateBasket(rows){ var el=document.getElementById('basket'); if(!el) return;
  var oy=rows.map(function(r){return num(r,'one_year_pct');}).filter(function(v){return v!=null;});
  var ex=rows.map(function(r){return num(r,'excess_vs_qqq_pct');}).filter(function(v){return v!=null;});
  var avg=function(a){return a.length?a.reduce(function(x,y){return x+y;},0)/a.length:null;};
  var a1=avg(oy), ae=avg(ex), pos=oy.length?oy.filter(function(v){return v>0;}).length/oy.length*100:null, n=rows.length;
  var band=(SURV&&SURV.one_year)?SURV.one_year:null;
  el.innerHTML='<div class="bk-h">What-if basket — current filter ('+n+' removals, equal-weight)</div>'+
    '<div class="bk-row">'+
    '<div class="bk"><div class="bk-v '+(a1>=0?'pos':'neg')+'">'+(a1==null?'—':fmtPct(a1))+'</div><div class="bk-l">avg 1-yr return</div></div>'+
    '<div class="bk"><div class="bk-v '+(ae>=0?'pos':'neg')+'">'+(ae==null?'—':fmtPct(ae))+'</div><div class="bk-l">avg excess vs QQQ</div></div>'+
    '<div class="bk"><div class="bk-v">'+(pos==null?'—':pos.toFixed(0)+'%')+'</div><div class="bk-l">positive</div></div>'+
    '<div class="bk"><div class="bk-v">'+n+'</div><div class="bk-l">in basket</div></div></div>'+
    '<p class="bk-cav">A descriptive equal-weight blend of historical outcomes — <b>not a strategy and not investment advice</b>. '+
    (band?('These survivor-only averages inherit the upward survivorship bias build_universe quantified: across the full universe the median 1-yr ranges ['+fmtPct(band.defensible_worst)+', '+fmtPct(band.survivors)+'].'):'')+'</p>';
}
"""

IDX_RENDERCHARTS = ("  buildAvgPath(); buildTenure(); buildArchetype();\n"
                    "  buildFate(); buildGap(); buildRegime(); buildSector();")

IDX_CONTROLS_OLD = """    <input type="text" id="fSearch" placeholder="search ticker…">
    <span class="meta" id="tableCount"></span>
  </div>"""
IDX_CONTROLS_NEW = """    <input type="text" id="fSearch" placeholder="search ticker…">
    <select id="fArch"><option value="">all archetypes</option></select>
    <select id="fSector"><option value="">all sectors</option></select>
    <select id="fRegime"><option value="">all regimes</option></select>
    <span class="meta" id="tableCount"></span>
  </div>
  <div id="basket" class="basket"></div>"""

IDX_PASSFILTERS_OLD = """  const q=document.getElementById('fSearch').value.trim().toLowerCase();
  if(q && !String(r.ticker).toLowerCase().includes(q)) return false;
  return true;"""
IDX_PASSFILTERS_NEW = """  const q=document.getElementById('fSearch').value.trim().toLowerCase();
  if(q && !String(r.ticker).toLowerCase().includes(q)) return false;
  var fa=document.getElementById('fArch'); if(fa&&fa.value&&r.archetype!==fa.value) return false;
  var fs=document.getElementById('fSector'); if(fs&&fs.value&&r.sector!==fs.value) return false;
  var fr=document.getElementById('fRegime'); if(fr&&fr.value&&r.market_regime!==fr.value) return false;
  return true;"""

IDX_RENDER_OLD = """  document.getElementById('tableCount').textContent=`${rows.length} of ${RAW.length} stocks`;
}"""
IDX_RENDER_NEW = """  document.getElementById('tableCount').textContent=`${rows.length} of ${RAW.length} stocks`;
  if(typeof updateBasket==='function') updateBasket(rows);
}"""

IDX_INITFILTERS_OLD = """  ['fTrunc','fYmin','fYmax','fSearch'].forEach(id=>{
    const el=document.getElementById(id);
    el.addEventListener(el.type==='checkbox'?'change':'input', render);});
  render();"""
IDX_INITFILTERS_NEW = """  ['fTrunc','fYmin','fYmax','fSearch'].forEach(id=>{
    const el=document.getElementById(id);
    el.addEventListener(el.type==='checkbox'?'change':'input', render);});
  (function(){ var uniq=function(k){return [...new Set(RAW.map(function(r){return r[k];}).filter(Boolean))].sort();};
    var fill=function(id,vals){var el=document.getElementById(id);if(!el)return;vals.forEach(function(v){var o=document.createElement('option');o.value=v;o.textContent=String(v).replace(/_/g,' ');el.appendChild(o);});};
    fill('fArch',uniq('archetype')); fill('fSector',uniq('sector')); fill('fRegime',uniq('market_regime'));
    ['fArch','fSector','fRegime'].forEach(function(id){var el=document.getElementById(id);if(el)el.addEventListener('change',render);}); })();
  render();"""

IDX_CSS = """  /* ---- pass-2 ---- */
  .abx{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px 18px;margin:0 0 16px;font-size:14px;line-height:1.55}
  .abx-h{font-size:11.5px;text-transform:uppercase;letter-spacing:.05em;color:var(--muted);margin-bottom:8px}
  .abx p{margin:0 0 8px} .abx-cav{color:var(--muted);font-size:12.5px;font-style:italic;border-top:1px solid var(--line);padding-top:8px;margin-top:4px}
  .explainer{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:2px 18px;margin-top:14px}
  .explainer summary{cursor:pointer;padding:14px 0;font-weight:600;font-size:15px;color:var(--fg)}
  .explainer .ex-body{padding:0 0 12px;font-size:14px;line-height:1.6;color:var(--slate)}
  .explainer h4{margin:12px 0 3px;font-size:13.5px;color:var(--fg)}
  .controls select{border:1px solid var(--line);border-radius:7px;padding:6px 9px;font:inherit;font-size:13px;background:var(--card);color:var(--fg);min-height:34px}
  .basket{background:var(--card);border:1px solid var(--bnbd);border-radius:12px;padding:14px 16px;margin:12px 0}
  .bk-h{font-size:12px;color:var(--muted);text-transform:uppercase;letter-spacing:.03em;margin-bottom:8px}
  .bk-row{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}
  .bk{background:var(--thbg);border:1px solid var(--line);border-radius:9px;padding:9px 10px}
  .bk-v{font-size:20px;font-weight:680;letter-spacing:-.02em} .bk-l{font-size:11px;color:var(--muted)}
  .bk-cav{color:var(--muted);font-size:12px;font-style:italic;margin:10px 0 0;line-height:1.5}
  @media (max-width:640px){ .bk-row{grid-template-columns:repeat(2,1fr)} }
"""


def patch_index(html):
    if MARKER in html:
        print("index.html already pass-2 (marker present) — skipping."); return html
    if "/*NDX-EXT v1*/" not in html:
        sys.exit("index.html missing pass-1 marker; run apply_extensions.py first.")
    html = checked(html, "RAW.forEach(function(r){ var t=TENURE[r.ticker+'-'+r.removal_date]; if(t){ r.years_in_index=t.years_in_index; r.tenure_censored=t.tenure_censored; r.archetype=t.archetype; } });",
                   "RAW.forEach(function(r){ var t=TENURE[r.ticker+'-'+r.removal_date]; if(t){ r.years_in_index=t.years_in_index; r.tenure_censored=t.tenure_censored; r.archetype=t.archetype; } });\n" + IDX_EMBED, "idx embed")
    html = checked(html, "  <div id=\"banner\"></div>", IDX_ABSTRACT_DIV, "idx abstract div")
    html = checked(html, "  <h2>Tenure & archetype — does time in the index matter?</h2>", IDX_SECTIONS, "idx sections")
    html = checked(html, "  <div class=\"caveats\">", IDX_EXPLAINER, "idx explainer")
    html = checked(html, "// ---------- render all charts (re-run on theme change) ----------",
                   IDX_BUILDERS + "// ---------- render all charts (re-run on theme change) ----------", "idx builders")
    html = checked(html, "  buildAvgPath(); buildTenure(); buildArchetype();", IDX_RENDERCHARTS, "idx renderCharts")
    html = checked(html, IDX_CONTROLS_OLD, IDX_CONTROLS_NEW, "idx controls")
    html = checked(html, IDX_PASSFILTERS_OLD, IDX_PASSFILTERS_NEW, "idx passFilters")
    html = checked(html, IDX_RENDER_OLD, IDX_RENDER_NEW, "idx render basket")
    html = checked(html, IDX_INITFILTERS_OLD, IDX_INITFILTERS_NEW, "idx initFilters")
    html = checked(html, "</style>", IDX_CSS + "</style>", "idx css")
    return html


# ============================ STOCKS.HTML ===========================
STK_EMBED = ("\n" + MARKER + "\nconst RT2=" + RT + ".per_id||{}; const REG2=(" + REG +
             ").per_id||{}; const SEC2=(" + SEC + ").per_id||{}; const COMP2=" + COMP + ";\n"
             "STOCKS.forEach(function(s){ var k=s.id;"
             " var rt=RT2[k]; if(rt){ s.re_added=rt.re_added; s.readd_date=rt.readd_date; s.round_trip_years=rt.round_trip_years; s.ultimate_fate=rt.ultimate_fate; }"
             " var rg=REG2[k]; if(rg){ s.market_regime=rg.market_regime; s.episode=rg.episode; s.qqq_max_drawdown=rg.qqq_max_drawdown; }"
             " var sc=SEC2[k]; if(sc){ s.sector=sc.sector; }"
             " var cp=COMP2[k]; if(cp){ s.comparable_ids=cp.comparable_ids; s.comp_criteria=cp.criteria; } });\n")

STK_COMPUTE = r"""  const arc=(function(){
    if(s.re_added && s.readd_date) return `<p class="arc pos">↩ Re-added to the Nasdaq-100 on <b>${s.readd_date}</b>, ${s.round_trip_years} years later.</p>`;
    var lbl={still_out:'Never re-added — still out, as of last data',acquired:'Never re-added — later acquired',delisted:'Never re-added — delisted',unknown:'Never re-added — fate unresolved'}[s.ultimate_fate]||'Never re-added';
    return `<p class="arc">${lbl}.</p>`; })();
  const regimeLine=(function(){ if(s.market_regime==null) return '';
    var names={crash:'crash',bear:'bear market',flat:'flat market',bull:'bull market',strong_bull:'strong bull market'};
    var ep=s.episode?` · ${s.episode}`:'';
    return `<div class="regime"><b>Market context.</b> Over this window QQQ returned <b>${fmtPct(s.qqq_same_window_pct)}</b> (a ${names[s.market_regime]||s.market_regime}${ep}). The stock's ${fmtPct(s.one_year_pct)} decomposes as market ${fmtPct(s.qqq_same_window_pct)} + stock-specific ${fmtPct(s.excess_vs_qqq_pct)} (excess vs QQQ) — a return decomposition, not a causal claim.</div>`; })();
  const compsPanel=(function(){ var ids=s.comparable_ids||[]; if(!ids.length) return '';
    var rows=ids.map(function(id){ var p=BY_ID[id]; if(!p) return '';
      return `<tr><td class="tk"><a href="#${id}">${p.ticker}</a> <span class="muted">${p.removal_date}</span></td>`+
        `<td class="${sign(p.one_year_pct)}">${fmtPct(p.one_year_pct)}</td>`+
        `<td class="${sign(p.excess_vs_qqq_pct)}">${fmtPct(p.excess_vs_qqq_pct)}</td>`+
        `<td>${p.sector||'—'}</td><td>${(p.ultimate_fate||'—').replace(/_/g,' ')}</td></tr>`; }).join('');
    return `<h2>Comparable removals</h2><p class="cap">Most similar prior removals by ${s.comp_criteria||'sector, archetype, regime and decline'}.</p>`+
      `<div class="tablewrap"><table><thead><tr><th>Peer</th><th>1-yr</th><th>Excess</th><th>Sector</th><th>Fate</th></tr></thead><tbody>${rows}</tbody></table></div>`; })();
"""

STK_HEAD_OLD = """    <div class="badges">${badges.join('')}</div>`;"""
STK_HEAD_NEW = """    <div class="badges">${badges.join('')}</div>${arc}`;"""

STK_PAGE_OLD = "document.getElementById('page').innerHTML = head + verdict + `\n    <h2>Price path"
STK_PAGE_NEW = "document.getElementById('page').innerHTML = head + verdict + regimeLine + `\n    <h2>Price path"

STK_COMMENTARY_OLD = """    <h2>Commentary</h2>
    <div class="commentary" id="commentary"></div>`;"""
STK_COMMENTARY_NEW = """    <h2>Commentary</h2>
    <div class="commentary" id="commentary"></div>` + compsPanel;"""

STK_CSS = """  /* ---- pass-2 ---- */
  .arc{font-size:13.5px;margin:8px 0 0;color:var(--slate)} .arc.pos{color:var(--green);font-weight:600}
  .regime{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 14px;margin:16px 0;font-size:13.5px;line-height:1.55;color:var(--slate)}
  td .muted,.muted{color:var(--muted);font-size:12px;font-weight:400}
</style>"""


def patch_stocks(html):
    if MARKER in html:
        print("stocks.html already pass-2 (marker present) — skipping."); return html
    if "/*NDX-EXT v1*/" not in html:
        sys.exit("stocks.html missing pass-1 marker; run apply_extensions.py first.")
    html = checked(html, "const BY_ID = Object.fromEntries(STOCKS.map(s=>[s.id, s]));",
                   "const BY_ID = Object.fromEntries(STOCKS.map(s=>[s.id, s]));\n" + STK_EMBED, "stk embed")
    html = checked(html, "  const co = COMPANY[s.ticker];\n",
                   "  const co = COMPANY[s.ticker];\n" + STK_COMPUTE, "stk compute")
    html = checked(html, STK_HEAD_OLD, STK_HEAD_NEW, "stk head arc")
    html = checked(html, STK_PAGE_OLD, STK_PAGE_NEW, "stk regime line")
    html = checked(html, STK_COMMENTARY_OLD, STK_COMMENTARY_NEW, "stk comparables")
    html = checked(html, "</style>", STK_CSS, "stk css")
    return html


def main():
    ip = DIST / "index.html"; sp = DIST / "stocks.html"
    ih = patch_index(read(ip)); ip.write_text(ih, encoding="utf-8")
    sh = patch_stocks(read(sp)); sp.write_text(sh, encoding="utf-8")
    print(f"index.html  -> {len(ih)/1024:.0f} KB")
    print(f"stocks.html -> {len(sh)/1024:.0f} KB")
    print("Pass-2 features applied.")


if __name__ == "__main__":
    main()
