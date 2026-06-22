# Nasdaq-100 Removals — the year after leaving the index

A small data study of stocks removed from the Nasdaq-100 (NDX): for every removal in the
last ~20 years (where the company kept trading), it measures how the stock behaved over its
first 252 trading days *out* of the index — trough depth, peak, one-year return, and excess
return versus QQQ over the identical window — then renders the results as a single self-contained,
no-build static page styled with the **Comet** design system (dark, warm-purple, finance-grade).

- **`index.html`** — the whole site in one file. The overview has an auto-generated executive
  abstract, a coverage/survivorship panel with bias-corrected scenarios, the "average path" chart,
  outcome distributions, timing scatters, a tenure/archetype view, by-year and by-sector cohorts,
  and a sortable/filterable removals table (search · hide-truncated · year range · a 5-way market-regime
  toggle). Clicking a removal opens a **per-stock deep-dive overlay** — verdict KPIs, indexed price
  path vs QQQ, a market-regime return decomposition, a quarter-by-quarter timeline, commentary, and a
  comparable-removals table.

The deep-dive overlay is synced to the URL hash, so links like `index.html#NFLX-2012-12-24` open a
specific stock directly and are shareable. Every chart supports wheel/pinch zoom, drag-to-pan, and
double-click reset.

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
  build_universe.py  survivorship.py  average_path.py  tenure.py  bootstrap.py
                          pass-1 analysis: coverage/survivorship, average path, tenure, bootstrap CIs
  roundtrip.py  regime.py  sectors.py  comparables.py  abstract.py
                          pass-2 analysis: fate/round-trips, market regime, sector, peers, abstract
  build_site.py           render data/processed -> dist/index.html (the whole Comet site, self-contained)
  comet-tokens.css        Comet design tokens (inlined into the page by build_site.py)
  qqq-favicon.svg         favicon (embedded as a data URI by build_site.py)
  wrapup.py  wrapup2.py   reconciliation + headline reports (read-only)
dist/          index.html  the built site (gitignored — regenerate from src/)
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

4. **Compute the aggregates** (offline — reads the processed data; later steps read earlier outputs):
   ```sh
   python src/build_universe.py     # universe.csv + fates_to_review.csv  (hand-fill unresolved fates, then re-run)
   python src/survivorship.py       # survivorship.json  (scenario medians + bias range)
   python src/average_path.py       # average_path.json  (offset-aligned median/IQR bands; reconciles vs the CSV)
   python src/tenure.py             # tenure.json  (years-in-index + archetype; scrapes Wikipedia)
   python src/bootstrap.py          # cis.json  (10k bootstrap 95% CIs)
   python src/roundtrip.py          # roundtrip.json  (re-additions + ultimate fate; scrapes Wikipedia)
   python src/regime.py             # regime.json  (market regime per window; reconciles QQQ vs the CSV)
   python src/sectors.py            # sectors.csv/json  (GICS sector; edit sectors.csv to correct)
   python src/comparables.py        # comparables.json  (similar prior removals per stock)
   python src/abstract.py           # abstract.json  (grounded executive summary)
   ```

5. **Build the site** (offline — reads only the processed data):
   ```sh
   python src/build_site.py
   ```
   Reads `data/processed/*` directly and writes the single self-contained `dist/index.html`
   (Comet tokens inlined, favicon embedded). Open it directly in a browser (Chart.js, the zoom
   plugin, Lucide, and Google Fonts load from CDNs — the only things that need internet when viewing).

   Optional: `python src/wrapup.py` / `wrapup2.py` print reconciliation spot-checks and the headline
   numbers.

> Note: `dist/` is gitignored (a deploy artifact), so it isn't in the repo — your locally built/served
> `dist/index.html` is the live site, and `build_site.py` reproduces it 1:1 from the processed data.

## Deploying

The built site is a **single self-contained file** — copy it to your server and serve it:

```
index.html      (the whole site: overview + per-stock deep-dive overlay)
```

- There are **no per-stock files** and no sidecar assets — the design tokens, favicon, and all
  per-stock daily series are embedded in `index.html`. Each deep-dive is a URL-hash route within it
  (e.g. `index.html#ZM-2023-12-18`), so those links are shareable.
- Do **not** upload `data/`, `src/`, or `logs/` — they are build-time inputs only and are never read
  at runtime.
- Viewing needs outbound internet for the Chart.js / zoom / Lucide / Google Fonts CDNs; nothing else
  is fetched.
- **`index.html` is ~1 MB.** Upload it in **binary** mode and confirm the server copy's byte size
  matches your local file. A truncated/corrupted transfer is the usual cause of a blank page (the
  embedded data breaks and the script aborts before rendering); check the browser console for a
  `SyntaxError` if it comes up empty.

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
