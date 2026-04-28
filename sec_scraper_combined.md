# SEC Scraper — Combined Documentation

---

# SEC Financial Data Toolkit

A single Python script that pulls financial data from SEC EDGAR filings and turns it into a browsable HTML table with growth metrics.

---

## Setup (one-time)

```
pip install -r requirements.txt
```

Requires Python 3.8+.

---

## Usage

**Double-click `run_unified.bat`** (or run `python sec_unified.py`)

You'll be prompted for:
- Ticker symbol (e.g. `META`, `AAPL`, `MSFT`, `CASY`)
- Start year (e.g. `2021`)
- End year (e.g. `2025`)

The script fetches every 10-K and 10-Q filed in that range directly from SEC EDGAR, extracts key financial metrics, saves a CSV, and generates an HTML table — all in one step.

**Output files** (saved in the same folder as the script):
- `{TICKER}_financials_{START}_{END}.csv` — raw data
- `{TICKER}_table.html` — the HTML table; open in any browser

---

## What gets extracted

| Column | Description |
|---|---|
| `filing_date` | Date SEC filing was submitted |
| `year` | Calendar year |
| `qlabel` | Q1–Q4 or FY (annual) |
| `period_type` | Quarterly or Annual |
| `scale` | Unit as reported (millions, thousands, etc.) |
| `revenue` | Total revenue / net sales |
| `gross_profit` | Gross profit (blank for retailers that don't report it) |
| `gross_margin` | Gross margin % |
| `operating_income` | Operating income / income before income taxes |
| `operating_margin` | Operating margin % |
| `net_income` | Net income |
| `net_margin` | Net margin % |
| `operating_cash_flow` | Cash from operating activities |
| `capex` | Capital expenditures (stored as negative) |
| `free_cash_flow` | OCF + CapEx |

---

## What the HTML table shows

For every metric, three rows are shown:

- **Raw value** — the reported figure, scaled to B/M/T for readability
- **↳ YoY Δ (abs)** — absolute change vs the same quarter one year prior
- **↳ YoY Δ (%)** — percentage change vs the same quarter one year prior

Annual (FY) columns are lightly shaded to distinguish them from quarterly periods.

Below the main table, a **CAGR summary** shows the compound annual growth rate for each metric across the full date range.

---

## How the parser works

Each filing goes through two phases:

**1. Format detection** — the script inspects the filing to determine whether it's HTML, Inline XBRL (iXBRL), or a pure XBRL instance document, then routes to the appropriate parser. Once a XBRL filing is detected, the script locks that format for all subsequent filings — no re-detection needed, and no wasted HTTP requests.

**2. Adaptive extraction** — pulls each metric using the company's actual label vocabulary rather than a fixed list:
- For HTML filings: scans income statement and cash flow tables, detects the reporting scale (millions/thousands/billions), identifies the current-period column (vs prior-year comparatives shown side by side), and searches rows by label.
- For XBRL filings: maps standard `us-gaap` concept names directly to metrics, selects the context whose period end date is closest to the filing date.

A plausibility guard rejects values that are implausibly small relative to revenue (catches footnote reference numbers being mistaken for financial figures). If any core metric is missing after the first pass, the parser retries up to 4 times with a relaxed table-matching threshold.

Progress is printed per filing. A `↻ retry` message means the parser made a second pass.

---

## Notes

- All monetary values are in the unit reported in the original SEC filing (shown in the `scale` column and the table subtitle). They are **not** normalised across companies.
- `gross_profit` is blank for retailers (like Casey's General Stores) that do not report a separate gross profit line in their income statements. This is expected and correct.
- `operating_income` covers both "income from operations" and "income before income taxes" to handle retailers that use pre-tax income as their primary profitability line.
- YoY comparisons use the same-quarter prior year (Q1 vs Q1, not Q1 vs Q4).
- CAGR is calculated from the first to the last period in the CSV. If a metric crosses zero, CAGR is shown as `—` (mathematically undefined).
- The parser respects SEC EDGAR's rate limit with a 0.15s delay between requests.
- Numbers are spot-checked against actual filings where possible, but complex or non-standard table layouts can occasionally cause a metric to be missed or pulled from the wrong column. Always verify against the source filing for anything you'll use in a model or presentation.
