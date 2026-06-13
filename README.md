# Nasdaq-100 Removals — the year after leaving the index

A small data study of stocks removed from the Nasdaq-100 (NDX): for every removal in the
last ~20 years (where the company kept trading), it measures how the stock behaved over its
first 252 trading days *out* of the index — trough depth, peak, one-year return, and excess
return versus QQQ over the identical window — then renders the results as two self-contained,
no-build static pages.

- **`index.html`** — the aggregate overview (distributions, timing scatters, by-year
  cohorts, and a sortable/filterable table of every stock).
- **`stocks.html`** — a per-stock deep-dive with indexed price path, drawdown, relative
  strength vs QQQ, a quarter-by-quarter return table, and plain-language commentary.

Both pages share a dark/light theme and cross-link; the dashboard's table rows link into the
matching stock deep-dive.

## Repository layout

```
data/
  raw/         removals.csv              hand-reviewed Wikipedia scrape (the pipeline input)
  processed/   results_per_stock.csv     per-stock summary stats (study output)
               series/                   daily aligned stock/QQQ series cache (+ _qqq, _manifest)
src/           ndx_removals_study.py      build the removal list + run the per-stock analysis
               export_series.py           fetch/cache daily series and gate them against the CSV
               build_dashboard.py         render data/processed -> dist/index.html
               build_stocks.py            render data/processed -> dist/stocks.html
dist/          index.html stocks.html    the built site (gitignored — regenerate from src/)
logs/          run logs (gitignored)
requirements.txt  README.md  LICENSE  .gitignore
```

The processed data (`results_per_stock.csv` and the `series/` cache) is committed so the site
can be rebuilt offline — delisted-ticker history is hard to refetch later, so the cache is the
source of truth for the pages.

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
   Writes `dist/index.html` and `dist/stocks.html`. Open either file directly in a browser
   (Chart.js is loaded from a CDN, the only thing that needs internet when viewing).

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
