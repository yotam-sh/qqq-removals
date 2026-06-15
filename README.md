# Nasdaq-100 Removals — the year after leaving the index

A small data study of stocks removed from the Nasdaq-100 (NDX): for every removal in the
last ~20 years (where the company kept trading), it measures how the stock behaved over its
first 252 trading days *out* of the index — trough depth, peak, one-year return, and excess
return versus QQQ over the identical window — then renders the results as two self-contained,
no-build static pages.

- **`index.html`** — the aggregate overview: an auto-generated executive abstract, a
  coverage/survivorship panel with three bias-corrected scenarios, the "average path" chart,
  outcome distributions, timing scatters, by-year cohorts, tenure/archetype, market-regime and
  sector breakdowns (with bootstrap CIs), an ultimate-fate & round-trips view, a collapsible
  deletion-effect explainer, a what-if basket tied to the filters, and a sortable/filterable table.
- **`stocks.html`** — a per-stock deep-dive: indexed price path, drawdown, relative strength vs
  QQQ, a quarter-by-quarter return table, commentary, plus a round-trip/ultimate-fate badge, a
  market-regime return decomposition, and a comparable-removals panel.

Both pages share a dark/light theme and cross-link; the dashboard's table rows link into the
matching stock deep-dive. Every chart supports wheel/pinch zoom, drag-to-pan, and double-click reset.

## Repository layout

```
data/
  raw/         removals.csv            hand-reviewed Wikipedia scrape (the pipeline input)
  processed/   results_per_stock.csv   per-stock summary stats (study output)
               series/                 daily aligned stock/QQQ series cache (+ _qqq, _manifest)
               universe.csv            full 204-removal universe + fate (survivorship base)
               fates_to_review.csv     unresolved fates for hand-filling (re-read on rerun)
               sectors.csv             GICS sector per ticker (correctable)
               *.json                  embedded aggregates: survivorship, average_path, tenure,
                                        cis, roundtrip, regime, sectors, comparables, abstract
src/
  ndx_removals_study.py   build the removal list + run the per-stock analysis
  export_series.py        fetch/cache daily series and reconcile them against the CSV
  build_dashboard.py      render data/processed -> dist/index.html  (base page)
  build_stocks.py         render data/processed -> dist/stocks.html (base page)
  build_universe.py  survivorship.py  average_path.py  tenure.py  bootstrap.py
                          pass-1 analysis: coverage/survivorship, average path, tenure, bootstrap CIs
  roundtrip.py  regime.py  sectors.py  comparables.py  abstract.py
                          pass-2 analysis: fate/round-trips, market regime, sector, peers, abstract
  apply_extensions.py     inject pass-1 sections + the zoom layer into dist/*.html (idempotent)
  apply_extensions2.py    inject pass-2 sections into dist/*.html (idempotent)
  wrapup.py  wrapup2.py   reconciliation + headline reports (read-only)
dist/          index.html stocks.html  the built site (gitignored — regenerate from src/)
logs/          run logs (gitignored)
requirements.txt  README.md  LICENSE  .gitignore
```

The processed data (`results_per_stock.csv`, the `series/` cache, and the embedded aggregates) is
committed so the site can be rebuilt offline — delisted-ticker history is hard to refetch later, so
the cache is the source of truth for the pages.

## Setup

```sh
pip install -r requirements.txt      # tested on Python 3.13
```

## Pipeline

Run the scripts from the repository root. They resolve their own paths relative to the repo,
so the working directory doesn't matter, but the `src/` prefix below assumes you're at the root.

1. **Build the removal list** (needs internet — scrapes Wikipedia):
   ```sh
   python src/ndx_removals_study.py build-list
   ```
   Writes `data/raw/removals.csv`. **Review it by hand**: verify dates and the `include`/`reason`
   columns, since acquisition- and delisting-driven removals (no real "year after") are excluded.
   Cross-check against Nasdaq's December reconstitution notices.

2. **Run the analysis** (needs internet — pulls daily data via yfinance):
   ```sh
   python src/ndx_removals_study.py analyze
   ```
   Reads `data/raw/removals.csv`, writes `data/processed/results_per_stock.csv`, prints the macro
   summary, and reports coverage (a low coverage rate means survivorship bias — see the caveat
   in the script docstring).

3. **Cache + verify the daily series** (network only for tickers not already cached):
   ```sh
   python src/export_series.py
   ```
   Writes `data/processed/series/*.json` and re-derives each stock's stats through the same code
   path that produced the CSV; it **exits non-zero** if any recomputed stat disagrees with the CSV
   beyond tolerance, so the pages never ship inconsistent numbers.

4. **Build the site** (offline — reads only the processed data):
   ```sh
   python src/build_dashboard.py
   python src/build_stocks.py
   ```
   Writes the **base** `dist/index.html` and `dist/stocks.html`. Open either file directly in a
   browser (Chart.js is loaded from a CDN, the only thing that needs internet when viewing).

5. **Pass-1 analysis + inject** (compute small aggregates, then add them to the built pages):
   ```sh
   python src/build_universe.py    # universe.csv + fates_to_review.csv  (hand-fill unresolved fates, then re-run)
   python src/survivorship.py      # survivorship.json  (three scenario medians + bias range)
   python src/average_path.py      # average_path.json  (offset-aligned median/IQR bands; reconciles vs the CSV)
   python src/tenure.py            # tenure.json  (years-in-index + archetype; scrapes Wikipedia)
   python src/bootstrap.py         # cis.json  (10k bootstrap 95% CIs)
   python src/apply_extensions.py  # inject coverage panel, average-path, tenure/archetype, CIs + zoom into dist/
   ```

6. **Pass-2 analysis + inject** (run in this order — later steps read earlier outputs):
   ```sh
   python src/roundtrip.py          # roundtrip.json  (re-additions + ultimate fate; scrapes Wikipedia)
   python src/regime.py             # regime.json  (market regime per window; reconciles QQQ vs the CSV)
   python src/sectors.py            # sectors.csv/json  (GICS sector; edit sectors.csv to correct)
   python src/comparables.py        # comparables.json  (similar prior removals per stock)
   python src/abstract.py           # abstract.json  (grounded executive summary)
   python src/apply_extensions2.py  # inject fate/round-trips, regime, sector, abstract, what-if, comparables
   ```
   Optional: `python src/wrapup.py` / `wrapup2.py` print reconciliation spot-checks and the headline
   numbers. The injectors are idempotent (guarded by `/*NDX-EXT*/` markers) and edit `dist/` in place.

> Note: `dist/` is gitignored (a deploy artifact), so it isn't in the repo — your locally built/served
> `dist/` is the live site. A few `dist/`-only refinements (mobile media queries, footer attribution,
> favicon link) live in the built files rather than the `build_*.py` templates, so a from-scratch
> rebuild won't reproduce those pages 1:1.

## Deploying

The built site is just **two self-contained files** — copy only these to your server, **in the same
directory**, and serve that directory:

```
index.html      (the overview / landing page)
stocks.html     (the per-stock deep-dives)
```

- Keep the two files **side by side**. The `← Dashboard` link and the dashboard's `stocks.html#…`
  links are relative, so the per-stock view (e.g. `stocks.html#ZM-2023-12-18`) only resolves when
  `stocks.html` sits next to `index.html`. There are **no per-stock files** — each deep-dive is a
  URL-hash route within the single `stocks.html`.
- Do **not** upload `data/`, `src/`, or `logs/` — they are build-time inputs only and are never read
  at runtime.
- Viewing needs outbound internet for the Chart.js CDN; nothing else is fetched.
- **`stocks.html` is ~1 MB.** Upload it in **binary** mode and confirm the server copy's byte size
  matches your local file. A truncated/corrupted transfer is the usual cause of a blank stock page
  (the embedded data breaks and the script aborts before rendering); check the browser console for a
  `SyntaxError` if a deep-dive comes up empty.

## Data & attribution

- Price data via **Yahoo Finance** (the [`yfinance`](https://pypi.org/project/yfinance/) library);
  a partial Stooq fallback is used only where Yahoo has no data, flagged in the `source` column.
- The removal list is derived from the Wikipedia "Nasdaq-100" article's component-change tables.
- **"Nasdaq-100"** is a trademark of Nasdaq, Inc.; **"QQQ"** (Invesco QQQ Trust) is a product of
  Invesco — referenced here for identification only. This project is not affiliated with, endorsed
  by, or sponsored by either.
- **Survivorship caveat:** tickers that were delisted or acquired after removal are dropped by the
  data source, and those were disproportionately the worst performers — so every figure is biased
  upward. The pages state this prominently.

Built by Hesanka with Claude.

## License

Code is released under the [MIT License](LICENSE). The license covers the code in this repository,
**not** the third-party market data it fetches, which remains subject to its providers' terms.
