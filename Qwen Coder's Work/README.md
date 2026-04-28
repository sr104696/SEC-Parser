# SEC Financial Data Toolkit

A comprehensive Python-based toolkit that fetches SEC EDGAR filings (10-K and 10-Q), extracts key financial metrics, and outputs both CSV data and an interactive HTML table with growth analysis.

## Features

- **Automated SEC Data Extraction**: Pulls all 10-K (annual) and 10-Q (quarterly) filings for any US public company
- **Smart Parsing**: Adapts to different companies' reporting formats and label vocabularies
- **Key Metrics Extracted**:
  - Revenue
  - Gross Profit & Margin
  - Operating Income & Margin
  - Net Income & Margin
  - Operating Cash Flow
  - Capital Expenditures (CapEx)
  - Free Cash Flow

- **Rich Output**:
  - CSV file with all raw data
  - Interactive HTML table with:
    - Year-over-Year (YoY) absolute changes
    - Year-over-Year (YoY) percentage changes
    - Compound Annual Growth Rate (CAGR) summary
    - Color-coded positive/negative values
    - Highlighted annual periods

## Quick Start

### Option 1: Double-click the BAT file (Windows)
1. Double-click `run_sec_toolkit.bat`
2. Enter ticker symbol (e.g., `AAPL`, `MSFT`, `GOOG`)
3. Enter start year (e.g., `2020`)
4. Enter end year (e.g., `2024`)
5. Wait for processing
6. Open the generated HTML file in your browser

### Option 2: Command Line
```bash
# Install dependencies (one-time)
pip install -r requirements.txt

# Run the script
python sec_unified.py
```

## Output Files

The toolkit generates two files in the same directory:

1. **CSV File** (`{TICKER}_financials_{START}_{END}.csv`)
   - Raw extracted data for further analysis
   - Columns: filing_date, year, qlabel, period_type, scale, revenue, gross_profit, gross_margin, operating_income, operating_margin, net_income, net_margin, operating_cash_flow, capex, free_cash_flow

2. **HTML Table** (`{TICKER}_table_{START}_{END}.html`)
   - Interactive web page openable in any browser
   - Shows each metric with three rows:
     - Raw value (scaled to B/M/K for readability)
     - YoY absolute change
     - YoY percentage change
   - CAGR summary section at the bottom

## Example Usage

```
Enter ticker symbol (e.g., AAPL, MSFT, GOOG): AAPL
Enter start year (e.g., 2020): 2020
Enter end year (e.g., 2024): 2024

Fetching data for AAPL from 2020 to 2024...
Looking up CIK number...
CIK for AAPL: 0000320193
Fetching filing list from SEC EDGAR...
Found 20 filings (10-K and 10-Q)

Processing filings...
  [1/20] Processing 10-K filed 2024-11-01... Revenue: 94930.0 (millions)
  [2/20] Processing 10-Q filed 2024-08-01... Revenue: 85780.0 (millions)
  ...

Successfully extracted data from 20 filings

CSV saved: AAPL_financials_2020_2024.csv
HTML table saved: AAPL_table_2020_2024.html

COMPLETE!
```

## How It Works

### 1. CIK Lookup
Converts the ticker symbol to a Central Index Key (CIK) number using SEC's company ticker database.

### 2. Filing Discovery
Fetches the list of all 10-K and 10-Q filings from SEC EDGAR within the specified date range.

### 3. Document Retrieval
Downloads each filing's HTML document directly from SEC servers.

### 4. Adaptive Parsing
- Detects the reporting scale (millions/thousands/billions)
- Identifies income statement and cash flow tables
- Searches for metrics using multiple label patterns
- Handles variations in how companies report their financials

### 5. Data Analysis
- Calculates derived metrics (margins, free cash flow)
- Computes YoY changes (comparing same quarter prior year)
- Calculates CAGR for annual periods

### 6. Output Generation
Creates both CSV and HTML outputs with formatted, analysis-ready data.

## Important Notes

- **Data Units**: Values are in the units reported by the company (shown in the `scale` column). The toolkit does NOT normalize across companies.
  
- **Gross Profit**: May be blank for retailers or companies that don't report a separate gross profit line item.

- **Operating Income**: Includes both "income from operations" and "income before income taxes" to handle different reporting conventions.

- **YoY Comparisons**: Always compares the same quarter (Q1 vs Q1, not Q1 vs Q4).

- **CAGR**: Shown as N/A if a metric crosses zero during the period (mathematically undefined).

- **Rate Limiting**: Respects SEC EDGAR's rate limits with a 0.15s delay between requests.

- **Verification**: Always verify critical figures against the source SEC filing before using in financial models or presentations.

## Requirements

- Python 3.8+
- requests
- beautifulsoup4
- lxml

## Troubleshooting

### Python not found
Install Python from https://www.python.org/downloads/ and ensure it's added to your PATH.

### Package installation errors
Run: `pip install --upgrade pip` then `pip install -r requirements.txt`

### No data extracted
Some filings have complex layouts that may not parse correctly. Try a different date range or verify the company files standard 10-K/10-Q forms.

### SEC connection errors
Check your internet connection. SEC EDGAR may occasionally be unavailable.

## License

This toolkit is provided as-is for educational and research purposes. Always comply with SEC EDGAR's terms of service when accessing their data.

## Support

For issues or questions, review the error messages carefully. The toolkit prints detailed progress information during execution to help diagnose problems.
