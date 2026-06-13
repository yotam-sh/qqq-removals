#!/usr/bin/env python3
"""
Nasdaq-100 removal study: for every stock removed from the NDX in the last
~20 years, analyze its first year of trading after removal.

Per stock:
  - lowest close in the year, as % vs. the close of the first day "out",
    and how many trading days after that first day it occurred
  - same for the highest close
  - total 1-year return, and excess return vs. QQQ over the same window

Aggregate:
  - distribution stats (median/mean trough depth, time-to-trough, peak,
    time-to-peak, % positive after 1 year, hit-rate vs. QQQ), plus a
    breakdown by removal year.

USAGE
  Step 1 - build the removal list (run on a machine with internet access):
      python src/ndx_removals_study.py build-list
    This scrapes the Wikipedia "Nasdaq-100" article's yearly-changes tables
    and writes data/raw/removals.csv. REVIEW THIS FILE BY HAND: fix dates, mark
    the 'reason' column (acquisition / delisted / reconstitution), since
    acquisition-driven removals must be excluded (no post-removal trading).
    Cross-check against Nasdaq's annual reconstitution press releases
    (usually published mid-December, effective before market open on the
    Monday after the third Friday of December).

  Step 2 - run the analysis:
      python src/ndx_removals_study.py analyze
    Reads data/raw/removals.csv, pulls daily data via yfinance, writes
    data/processed/results_per_stock.csv and prints the macro summary.

KNOWN DATA CAVEAT (important): Yahoo Finance often has no data for tickers
that were later delisted (bankruptcy or acquisition AFTER removal). Stocks
that died after leaving the index are exactly the worst performers, so any
missing tickers bias results UPWARD (survivorship bias). The script reports
its coverage rate; if it's well below ~85-90%, prefer a survivorship-free
source (CRSP via WRDS, Norgate Data, or EODHD's delisted-tickers feed) and
plug it into fetch_prices().
"""

import sys
import time
import io
import re
from datetime import timedelta
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]   # repo root (this file lives in src/)
REMOVALS_CSV = str(ROOT / "data" / "raw" / "removals.csv")
RESULTS_CSV = str(ROOT / "data" / "processed" / "results_per_stock.csv")
WINDOW_TRADING_DAYS = 252          # ~1 calendar year
MIN_DAYS_FOR_FULL_YEAR = 240       # below this, mark window as truncated
BENCHMARK = "QQQ"
WIKI_URL = "https://en.wikipedia.org/wiki/Nasdaq-100"


# ---------------------------------------------------------------------------
# Step 1: build the removal list from Wikipedia (run locally, then hand-check)
# ---------------------------------------------------------------------------

def _clean(s):
    """Strip Wikipedia footnote refs like [17]/[note 2] and surrounding space."""
    return re.sub(r"\[[^\]]*\]", "", str(s)).strip()


def _find_changes_table(tables):
    """Pick the 'Component changes' table: a 2-level-header frame whose top
    level carries both an 'Added' and a 'Removed' group plus 'Date'."""
    for t in tables:
        if not isinstance(t.columns, pd.MultiIndex):
            continue
        top = {str(c).lower() for c in t.columns.get_level_values(0)}
        if "added" in top and "removed" in top and "date" in top:
            return t
    return None


# Reasons meaning the removed stock STOPPED trading as an independent US-listed
# name (no meaningful "year after") -> exclude. Everything else (annual
# reconstitution, minimum-weight-requirement drops, NYSE<->Nasdaq listing
# transfers) is kept, because the company kept trading.
EXCLUDE_PAT = re.compile(
    r"acqui|merg|bought|took over|taken private|going private|go private|"
    r"went private|goes private|private equity|delist|bankrupt|liquidat|"
    r"ceased|dissolv|spun off|spin[-\s]?off",
    re.I,
)

# Hand-verified overrides where the reason text doesn't classify cleanly.
# (ticker, before-date) -> these stocks have no usable US "year after":
#   MICC  Millicom withdrew its NASDAQ US listing (no continuous US series)
#   MNST  Monster Worldwide; Yahoo later reused 'MNST' for Monster Beverage,
#         so a price pull would silently return the WRONG company's data.
MANUAL_EXCLUDE_TICKERS = {"MICC", "MNST"}


def build_list():
    import requests

    headers = {"User-Agent": "Mozilla/5.0 (research script)"}
    html = requests.get(WIKI_URL, headers=headers, timeout=30).text
    tables = pd.read_html(io.StringIO(html))
    t = _find_changes_table(tables)
    if t is None:
        raise SystemExit("Could not locate the Nasdaq-100 'Component changes' "
                         "table; Wikipedia's layout may have changed.")

    # Flatten the 2-level header (e.g. ('Removed','Ticker')) to 'removed_ticker'.
    t = t.copy()
    t.columns = [f"{str(a).lower()}_{str(b).lower()}" for a, b in t.columns]
    date_col = next(c for c in t.columns if c.startswith("date"))
    rt_col = next(c for c in t.columns if c.startswith("removed") and "tick" in c)
    rs_col = next(c for c in t.columns if c.startswith("removed") and "tick" not in c)
    reason_col = next((c for c in t.columns if c.startswith("reason")), None)

    rows = []
    for _, r in t.iterrows():
        tick = _clean(r.get(rt_col, ""))
        if not tick or tick.lower() in ("nan", "—", "-", ""):
            continue
        rows.append({
            "ticker": tick.upper(),
            "removal_date": _clean(r.get(date_col, "")),
            "company": _clean(r.get(rs_col, "")),
            "reason": _clean(r.get(reason_col, "")) if reason_col else "",
        })

    df = pd.DataFrame(rows).drop_duplicates(subset=["ticker", "removal_date"])
    df["removal_date"] = pd.to_datetime(df["removal_date"], errors="coerce")
    df = df.dropna(subset=["removal_date"])
    cutoff = pd.Timestamp.now() - pd.DateOffset(years=20)
    df = df[df["removal_date"] >= cutoff].sort_values("removal_date")
    # 'include' column: 0 for acquisition/delisting-driven removals (no year after)
    df["include"] = 1
    df.loc[df["reason"].str.contains(EXCLUDE_PAT, na=False), "include"] = 0
    # Hand-verified overrides (ticker collisions / withdrawn US listings):
    df.loc[(df["ticker"].isin(MANUAL_EXCLUDE_TICKERS)) &
           (df["removal_date"] < pd.Timestamp("2012-01-01")), "include"] = 0
    Path(REMOVALS_CSV).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(REMOVALS_CSV, index=False)
    print(f"Wrote {len(df)} removals to {REMOVALS_CSV}.")
    print(f"  pre-flagged as excluded (acquisition/delisting/etc.): {(df['include']==0).sum()}")
    print(f"  kept for analysis (company kept trading):            {(df['include']==1).sum()}")
    print("NOW REVIEW THE FILE BY HAND before running 'analyze'; verify dates")
    print("and the include flag against Nasdaq's December reconstitution notices.")


# ---------------------------------------------------------------------------
# Step 2: per-stock analysis
# ---------------------------------------------------------------------------

def fetch_prices(ticker, start, end):
    """Daily closes for [start, end] from Yahoo. Swap this out for
    CRSP/Norgate/EODHD if you need survivorship-free coverage."""
    import yfinance as yf
    df = yf.download(ticker, start=start.strftime("%Y-%m-%d"),
                     end=end.strftime("%Y-%m-%d"),
                     auto_adjust=True, progress=False)
    if df is None or df.empty:
        return None
    close = df["Close"]
    if isinstance(close, pd.DataFrame):   # yfinance sometimes returns 2-D
        close = close.iloc[:, 0]
    return close.dropna()


def fetch_prices_stooq(ticker, start, end):
    """Fallback source that carries some delisted tickers Yahoo drops.
    NOTE: Stooq closes are only partially adjusted, so a fallback row is less
    comparable than a yfinance row — the 'source' column flags which is which."""
    from pandas_datareader import data as pdr
    for sym in (f"{ticker}.US", ticker):
        try:
            d = pdr.DataReader(sym, "stooq", start, end)
        except Exception:
            d = None
        if d is not None and not d.empty and "Close" in d:
            return d["Close"].sort_index().dropna()
    return None


def fetch_with_source(ticker, start, end):
    """Try Yahoo, fall back to Stooq. Returns (closes_or_None, source_str)."""
    try:
        closes = fetch_prices(ticker, start, end)
    except Exception as e:
        print(f"  {ticker}: yfinance error ({e})")
        closes = None
    if closes is not None and not closes.empty:
        return closes, "yfinance"
    try:
        closes = fetch_prices_stooq(ticker, start, end)
    except Exception as e:
        print(f"  {ticker}: stooq error ({e})")
        closes = None
    if closes is not None and not closes.empty:
        return closes, "stooq"
    return None, "missing"


# Yahoo drops a ticker's whole history once it is delisted. For removals where
# the SAME economic entity still trades under a renamed symbol, fetch the
# current symbol instead (its history is continuous through the rename, so the
# old-window returns are recovered). Verified each carries data for its window.
# NB: only true renames belong here -- NOT acquisitions (e.g. ESRX->Cigna would
# measure a different company), which stay excluded.
TICKER_RENAMES = {
    "AEOS": "AEO",    # American Eagle Outfitters
    "UAUA": "UAL",    # UAL Corp -> United Airlines Holdings
    "HANS": "MNST",   # Hansen Natural -> Monster Beverage
    "RIMM": "BB",     # Research In Motion -> BlackBerry
    "MYL":  "VTRS",   # Mylan -> Viatris
    "NLOK": "GEN",    # NortonLifeLock -> Gen Digital
    "DISCA": "WBD",   # Discovery -> Warner Bros. Discovery (windows pre-2022)
    "DISCK": "WBD",   # Discovery Series C -> WBD
    "QRTEA": "QVCGA", # Qurate Retail -> QVC Group (returns valid; reverse split)
}


def analyze_one(closes, removal_date):
    """closes: Series of daily closes from removal date onward.
    Baseline = close of the first trading day out of the index."""
    closes = closes[closes.index >= pd.Timestamp(removal_date)]
    if len(closes) < 5:
        return None
    window = closes.iloc[:WINDOW_TRADING_DAYS + 1]
    base = float(window.iloc[0])
    rel = (window / base - 1.0) * 100.0

    after = rel.iloc[1:] if len(rel) > 1 else rel
    i_min = after.values.argmin()
    i_max = after.values.argmax()

    return {
        "first_day_out": window.index[0].date(),
        "last_day": window.index[-1].date(),
        "base_close": round(base, 4),
        "lowest_pct": round(float(after.iloc[i_min]), 2),
        "days_to_low": int(i_min + 1),            # trading days after day 1
        "date_of_low": after.index[i_min].date(),
        "highest_pct": round(float(after.iloc[i_max]), 2),
        "days_to_high": int(i_max + 1),
        "date_of_high": after.index[i_max].date(),
        "one_year_pct": round(float(rel.iloc[-1]), 2),
        "data_days": len(window),
        "truncated": len(window) < MIN_DAYS_FOR_FULL_YEAR,
    }


def analyze():
    removals = pd.read_csv(REMOVALS_CSV, parse_dates=["removal_date"])
    if "include" in removals.columns:
        excluded = removals[removals["include"] != 1]
        removals = removals[removals["include"] == 1]
        print(f"Excluded {len(excluded)} acquisition/delisting removals; "
              f"{len(removals)} candidates remain.")

    # Download the QQQ benchmark ONCE over the full span, then slice per stock
    # (the old code re-downloaded it for every single removal).
    span_start = removals["removal_date"].min() - timedelta(days=10)
    span_end = removals["removal_date"].max() + timedelta(days=420)
    print(f"Downloading {BENCHMARK} benchmark once for "
          f"{span_start.date()}..{span_end.date()} ...")
    qqq_full = fetch_prices(BENCHMARK, span_start, span_end)
    if qqq_full is None or qqq_full.empty:
        print("  WARNING: could not fetch QQQ; excess-vs-QQQ will be blank.")

    results, missing = [], []
    for _, row in removals.iterrows():
        tkr = row["ticker"]
        rd = row["removal_date"]
        fetch_tkr = TICKER_RENAMES.get(tkr, tkr)  # use current symbol if renamed
        start = rd - timedelta(days=5)
        end = rd + timedelta(days=420)            # buffer past 252 trading days
        closes, source = fetch_with_source(fetch_tkr, start, end)
        if closes is None:
            missing.append(tkr)
            continue
        stats = analyze_one(closes, rd)
        if stats is None:
            missing.append(tkr)
            continue
        # benchmark over the identical calendar window [first_day_out .. last_day]
        stats["qqq_same_window_pct"] = None
        stats["excess_vs_qqq_pct"] = None
        if qqq_full is not None and not qqq_full.empty:
            qwin = qqq_full[(qqq_full.index >= pd.Timestamp(stats["first_day_out"])) &
                            (qqq_full.index <= pd.Timestamp(stats["last_day"]))]
            if len(qwin) >= 2:
                qqq_ret = (float(qwin.iloc[-1]) / float(qwin.iloc[0]) - 1) * 100
                stats["qqq_same_window_pct"] = round(qqq_ret, 2)
                stats["excess_vs_qqq_pct"] = round(stats["one_year_pct"] - qqq_ret, 2)

        stats["ticker"] = tkr
        stats["fetch_ticker"] = fetch_tkr
        stats["removal_date"] = rd.date()
        stats["source"] = source
        results.append(stats)
        flag = "" if source == "yfinance" else f"  [{source}]"
        print(f"  {tkr} ({rd.date()}): low {stats['lowest_pct']}% @ d{stats['days_to_low']}, "
              f"high {stats['highest_pct']}% @ d{stats['days_to_high']}, "
              f"1y {stats['one_year_pct']}%{flag}")
        if source == "yfinance":
            time.sleep(0.4)                        # be polite to Yahoo

    df = pd.DataFrame(results)
    if df.empty:
        print("No results — check removals.csv and connectivity.")
        return
    Path(RESULTS_CSV).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(RESULTS_CSV, index=False)
    macro_summary(df, missing, len(removals))


def macro_summary(df, missing, n_candidates):
    full = df[~df["truncated"]]
    print("\n" + "=" * 64)
    print("MACRO ANALYSIS — first year after leaving the Nasdaq-100")
    print("=" * 64)
    cov = len(df) / n_candidates * 100 if n_candidates else 0
    print(f"Coverage: {len(df)}/{n_candidates} candidates ({cov:.0f}%); "
          f"{len(missing)} missing from data source: {', '.join(missing) or '-'}")
    if cov < 85:
        print("  WARNING: coverage below ~85% -> meaningful survivorship bias.")
    if "source" in df.columns:
        sc = df["source"].value_counts().to_dict()
        print(f"Data source: yfinance {sc.get('yfinance', 0)}, "
              f"stooq (fallback) {sc.get('stooq', 0)}")
    print(f"Truncated windows (stock stopped trading within the year): "
          f"{df['truncated'].sum()}")

    def block(name, s):
        print(f"\n{name}: median {s.median():+.1f}, mean {s.mean():+.1f}, "
              f"p25 {s.quantile(.25):+.1f}, p75 {s.quantile(.75):+.1f}")

    block("Trough depth, % vs first-day-out close", df["lowest_pct"])
    print(f"Days to trough: median {df['days_to_low'].median():.0f}, "
          f"mean {df['days_to_low'].mean():.0f}")
    print(f"  troughs in first 21 trading days (~1 month): "
          f"{(df['days_to_low'] <= 21).mean()*100:.0f}%")
    block("Peak height, % vs first-day-out close", df["highest_pct"])
    print(f"Days to peak: median {df['days_to_high'].median():.0f}, "
          f"mean {df['days_to_high'].mean():.0f}")
    block("1-year total return %", full["one_year_pct"])
    print(f"Positive after 1 year: {(full['one_year_pct'] > 0).mean()*100:.0f}%")
    if full["excess_vs_qqq_pct"].notna().any():
        ex = full["excess_vs_qqq_pct"].dropna()
        block("Excess return vs QQQ, same window", ex)
        print(f"Beat QQQ: {(ex > 0).mean()*100:.0f}%")

    print("\nBy removal year (median 1y return %, n):")
    by = df.assign(year=pd.to_datetime(df["removal_date"]).dt.year) \
           .groupby("year")["one_year_pct"].agg(["median", "count"])
    for y, r in by.iterrows():
        print(f"  {y}: {r['median']:+7.1f}%  (n={int(r['count'])})")
    print(f"\nPer-stock detail written to {RESULTS_CSV}")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "build-list":
        build_list()
    elif cmd == "analyze":
        analyze()
    else:
        print(__doc__)
