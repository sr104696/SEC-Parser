# SEC Financial Data Toolkit — Unified Reference

A Python-based toolkit that fetches SEC EDGAR filings (10-K and 10-Q), extracts key financial metrics, and outputs a CSV plus an interactive HTML dashboard or table.

---

## Setup (one-time)

```
pip install -r requirements.txt
```

Requires Python 3.8+.

---

## Usage

**Double-click `run_unified.bat`** (or run `python sec_unified.py` / `python sec_parser_smart.py`)

You'll be prompted for:
- Ticker symbol (e.g. `META`, `AAPL`, `MSFT`, `GOOG`, `CASY`)
- Start year (e.g. `2020`)
- End year (e.g. `2025`)

**Output files** (saved in the same folder as the script):
- `{TICKER}_financials_{START}_{END}.csv` — raw extracted data
- `{TICKER}_table.html` or `{TICKER}_dashboard_{START}_{END}.html` — open in any browser

---

## What Gets Extracted

| Column | Description |
|---|---|
| `filing_date` | Date SEC filing was submitted |
| `year` | Calendar year |
| `qlabel` | Q1–Q4 or FY (annual); e.g. Q1'24, FY'24 |
| `period_type` | Quarterly or Annual |
| `scale` | Unit as reported (millions, thousands, billions) |
| `revenue` | Total revenue / net sales |
| `gross_profit` | Gross profit (blank for retailers that don't report it separately) |
| `gross_margin` | Gross margin % |
| `operating_income` | Operating income / income before income taxes |
| `operating_margin` | Operating margin % |
| `net_income` | Net income |
| `net_margin` | Net margin % |
| `operating_cash_flow` | Cash from operating activities |
| `capex` | Capital expenditures (stored as negative) |
| `free_cash_flow` | OCF + CapEx |

### Example CSV Output
```
filing_date  year  quarter  period_type  revenue   operating_income  net_income  ...
2021-02-02   2021  FY       Annual       182527    41224             40269       ...
2021-04-27   2021  Q1       Quarterly    55314     16437             17930       ...
2021-07-27   2021  Q2       Quarterly    61983     19361             18525       ...
```

---

## HTML Output

### Table view (`sec_unified.py`)
For every metric, three rows are shown:
- **Raw value** — reported figure, scaled to B/M/T for readability
- **↳ YoY Δ (abs)** — absolute change vs same quarter one year prior
- **↳ YoY Δ (%)** — percentage change vs same quarter one year prior

Annual (FY) columns are lightly shaded. A **CAGR summary** appears below the table.

### Dashboard view (`sec_unified.py` — Alt Dashboard variant)
- YoY absolute and percentage changes
- CAGR calculations across full period
- Color-coded positive/negative values
- Fiscal year column highlighting
- Responsive table layout

---

## How the Parser Works

Each filing goes through two phases:

**1. Format detection** — determines whether the filing is HTML, Inline XBRL (iXBRL), or a pure XBRL instance document, then routes to the appropriate parser. Once XBRL is detected, the format is locked for all subsequent filings — no re-detection or wasted HTTP requests.

**2. Adaptive extraction** — pulls each metric using the company's actual label vocabulary rather than a fixed list:
- **HTML filings**: scans income statement and cash flow tables, detects reporting scale, identifies the current-period column (vs prior-year comparatives), and searches rows by label.
- **XBRL filings**: maps standard `us-gaap` concept names directly to metrics; selects the context whose period end date is closest to the filing date.

A plausibility guard rejects values implausibly small relative to revenue (prevents footnote reference numbers from being mistaken for financial figures). If any core metric is missing after the first pass, the parser retries up to 4 times with a relaxed table-matching threshold.

Progress is printed per filing. A `↻ retry` message means the parser made a second pass.

---

## Dashboard Changelog

### 1. Wired in JSON Data Source
Data now loads from `alphabet_unified_data.json` instead of hardcoded arrays — single source of truth, easier to update.

### 2. Fixed Empty Rows Bug in Drag Panel
**Root cause**: `computeStats` filtered out datasets where either the start OR end value was null, causing all datasets to be dropped when dragging across quarters with null YoY values.

```javascript
// Before
if(v0===null||v0===undefined||v1===null||v1===undefined||isNaN(v0)||isNaN(v1)) return;

// After
if((v0===null||v0===undefined) && (v1===null||v1===undefined)) return;
if(v0!==null && v0!==undefined && isNaN(v0)) return;
if(v1!==null && v1!==undefined && isNaN(v1)) return;
```

Also updated `delta`, `pctChg`, and `cagr` calculations to handle null values.

### 3. Async Data Loading
- Chart init wrapped in `initCharts()`
- Trend bars wrapped in `initTrendBars()`
- Raw data table wrapped in `initRawTable()`
- All called after JSON loads; fallback to hardcoded data if fetch fails

### 4. Misc Optimizations
- Removed duplicate `DR` (derived series) definition
- Moved derived series calculation inside `initCharts()` to use loaded data

#### Testing Checklist
- [ ] Dashboard loads with JSON data
- [ ] All charts render correctly
- [ ] Drag-to-analyze works across quarters with null values
- [ ] Trend bars and raw data table populate correctly
- [ ] Fallback to hardcoded data works if JSON fails to load

---

## Dashboard Adaptation (LLM Prompt)

Use this prompt to adapt the dashboard to any company.

### What to Provide
1. Company name and ticker
2. 20+ quarters of financial data:
   - Revenue segments (by business line/product)
   - Operating income by segment
   - Net income, OCF, CapEx, FCF

### Data Format
```javascript
const companyData = {
  ticker: "ACME",
  name: "Acme Corporation",
  quarters: ['Q1\'21', 'Q2\'21', ...],
  segments: {
    productA: [1200, 1350, ...],
    productB: [800, 850, ...],
  },
  operatingIncome: {
    productA: [300, 340, ...],
    corporate: [-50, -55, ...],
  },
  totalRevenue: [2400, 2650, ...],
  totalOpIncome: [480, 535, ...],
  netIncome: [380, 425, ...],
  ocf: [500, 550, ...],
  capex: [-100, -110, ...],
  fcf: [400, 440, ...],
};
```

### Adaptation Steps
1. **Map segments** — identify business lines, assign variable names
2. **Update branding** — company name, ticker, color scheme
3. **Adjust KPIs** — most relevant metrics, YoY growth, margins
4. **Customize insights** — use badges: `ACCELERATING`, `DECELERATING`, `PLATEAU`, `WATCH`, `RISK`
5. **Adapt tabs** — remove irrelevant tabs (e.g. "Cloud Deep-Dive"), add new ones if needed
6. **Update forecasts** — scenario projections based on historical growth rates

### Output Requirements
- Standalone HTML, no external dependencies except Chart.js CDN
- All data, styles, and scripts inline
- Works in Chrome, Firefox, Safari, Edge

### Special Cases
| Situation | Handling |
|---|---|
| Fewer segments | Simplify charts, remove unused color vars |
| More segments | Add colors, expand stacked bars, group minor into "Other" |
| Missing metrics | Hide those charts, note in tab structure |
| Not profitable | Handle negative margins, focus on path to profitability |
| Non-calendar fiscal year | Adjust quarter labels, clarify in subtitle |

### Validation Checklist
- [ ] Units correct (millions/billions/percentages)
- [ ] YoY uses same quarter prior year (Q1 vs Q1, not Q1 vs Q4)
- [ ] Margins = operating income / revenue
- [ ] FCF = OCF − CapEx
- [ ] No stale Google/GOOG references remain

### Debugging an Existing Dashboard
Provide: the HTML file or relevant code, description of the issue, the data being visualized, and any browser console errors.

---

## Notes

- Monetary values are in the unit reported in the original SEC filing (`scale` column) — **not** normalized across companies.
- `gross_profit` is blank for retailers (e.g. Casey's General Stores) that don't report a separate gross profit line. This is expected.
- `operating_income` covers both "income from operations" and "income before income taxes" to handle retailers using pre-tax income as their primary profitability line.
- YoY comparisons use the same-quarter prior year (Q1 vs Q1, not Q1 vs Q4).
- CAGR is undefined (shown as `—`) if a metric crosses zero during the period.
- The parser respects SEC EDGAR's rate limit with a 0.15s delay between requests.
- Always verify figures against the source filing before using in a model or presentation.
