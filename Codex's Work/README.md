# Codex's Work: SEC 10-Q / 10-K Unified Extractor

## What this does

This package:
1. Prompts for **ticker**, **start year**, and **end year**.
2. Pulls all **10-Q** and **10-K** filings for that range from SEC submissions.
3. Extracts financial metrics from SEC company facts, matching each filing to nearby reported values:
   - revenue
   - profit (net income)
   - operating income
   - operating cash flow
4. Builds one combined CSV with raw metrics plus:
   - sequential absolute and % change (vs prior filing)
   - YoY absolute and % change (same quarter/fiscal period prior year)
5. Generates a styled HTML table with a CAGR summary (overall, annual-only, quarterly-only).

## Files

- `sec_filing_financials.py` — main Python script.
- `start_sec_financials.bat` — Windows launcher that asks for inputs and runs the script.

## Run

### Windows
Double-click `start_sec_financials.bat`.

### Terminal
```bash
python sec_filing_financials.py
```
Or non-interactive:
```bash
python sec_filing_financials.py AAPL 2020 2025
```

## Output

For ticker/range, outputs:
- `{TICKER}_financials_{START}_{END}.csv`
- `{TICKER}_financials_{START}_{END}.html`

## SEC user-agent

SEC recommends identifying requests. Optionally set:

```bash
export SEC_USER_AGENT="YourName your.email@domain.com"
```

On Windows PowerShell:

```powershell
$env:SEC_USER_AGENT = "YourName your.email@domain.com"
```
