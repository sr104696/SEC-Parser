# Alt Dashboard — Combined Documentation

---

# SEC Financial Data Tool

Single tool that fetches SEC filings, parses financial metrics, and generates an interactive HTML dashboard.

## Setup (one-time)

```
pip install -r requirements.txt
```

Requires Python 3.8+.

## Usage

**Double-click `run_unified.bat`** (or run `python sec_unified.py`)

You'll be prompted for:
- Ticker symbol (e.g., `META`, `AAPL`, `GOOGL`)
- Start year (e.g., `2020`)
- End year (e.g., `2024`)

The tool fetches every 10-K and 10-Q filed in that range from SEC EDGAR, parses the HTML, and generates:
- `{TICKER}_financials_{START}_{END}.csv` — raw data
- `{TICKER}_dashboard_{START}_{END}.html` — interactive dashboard

## What gets extracted

| Column | Description |
|---|---|
| `filing_date` | Date SEC filing was submitted |
| `year` | Calendar year |
| `qlabel` | Q1'24, Q2'24, FY'24, etc. |
| `period_type` | Quarterly or Annual |
| `scale` | Unit as reported (millions, thousands, billions) |
| `revenue` | Total revenue / net sales |
| `gross_profit` | Gross profit |
| `gross_margin` | Gross margin % |
| `operating_income` | Operating income |
| `operating_margin` | Operating margin % |
| `net_income` | Net income |
| `net_margin` | Net margin % |
| `operating_cash_flow` | Cash from operating activities |
| `capex` | Capital expenditures (negative) |
| `free_cash_flow` | OCF + CapEx |

## Dashboard features

- YoY absolute and percentage changes (same quarter prior year)
- CAGR calculations across full period
- Color-coded positive/negative values
- Fiscal year column highlighting
- Responsive table layout

## How it works

**Structure detection** — identifies scale (millions/thousands/billions), locates income statement and cash flow tables, detects which column contains current period data.

**Adaptive extraction** — pulls metrics using the company's actual label vocabulary rather than fixed patterns. Handles variations in table structure across different companies and filing formats.

## Notes

- Values are in the unit reported in SEC filings (shown in `scale` column)
- YoY comparisons use same quarter prior year (Q1 vs Q1, not Q1 vs Q4)
- CAGR undefined if metric crosses zero during period
- Respects SEC EDGAR rate limit (0.15s delay between requests)
- Always verify against source filing for critical use cases
