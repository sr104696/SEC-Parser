"""
SEC Financial Data Toolkit - Unified
Fetches 10-K and 10-Q filings from SEC EDGAR, extracts financial metrics,
and generates CSV + HTML table with growth analysis and CAGR.
"""

import os
import sys
import time
import re
import json
from datetime import datetime
from collections import defaultdict

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    print("Missing required packages. Installing...")
    os.system("pip install requests beautifulsoup4 lxml")
    import requests
    from bs4 import BeautifulSoup

# SEC EDGAR requires a user agent header
USER_AGENT = "SEC Financial Toolkit (your@email.com)"
HEADERS = {"User-Agent": USER_AGENT}

def get_cik(ticker):
    """Get CIK number for a ticker symbol."""
    url = "https://www.sec.gov/files/company_tickers.json"
    resp = requests.get(url, headers=HEADERS)
    resp.raise_for_status()
    data = resp.json()
    for item in data.values():
        if item['ticker'].upper() == ticker.upper():
            return str(item['cik_str']).zfill(10)
    raise ValueError(f"Ticker {ticker} not found")

def get_filings(cik, start_year, end_year):
    """Get all 10-K and 10-Q filings for a CIK in date range."""
    filings = []
    
    # Get submissions
    url = f"https://data.sec.gov/submissions/CIK{cik}.json"
    resp = requests.get(url, headers=HEADERS)
    resp.raise_for_status()
    data = resp.json()
    
    # SEC API returns parallel arrays under 'recent'
    recent = data.get('filings', {}).get('recent', {})
    forms = recent.get('form', [])
    filing_dates = recent.get('filingDate', [])
    accession_numbers = recent.get('accessionNumber', [])
    
    for i in range(len(forms)):
        form_type = forms[i] if i < len(forms) else ''
        if form_type not in ['10-K', '10-Q']:
            continue
        
        filing_date = filing_dates[i] if i < len(filing_dates) else ''
        if not filing_date:
            continue
        
        year = int(filing_date.split('-')[0])
        if year < start_year or year > end_year:
            continue
        
        acc_num = accession_numbers[i] if i < len(accession_numbers) else ''
        acc_num = acc_num.replace('-', '')
        filings.append({
            'form': form_type,
            'date': filing_date,
            'year': year,
            'accessionNumber': acc_num
        })
    
    # Sort by date descending (newest first)
    filings.sort(key=lambda x: x['date'], reverse=True)
    return filings

def fetch_filing_html(cik, acc_num):
    """Fetch the primary HTML document for a filing."""
    # Format accession number with dashes if not already
    if '-' not in acc_num and len(acc_num) == 18:
        acc_num_dashed = f"{acc_num[:10]}-{acc_num[10:12]}-{acc_num[12:]}"
    else:
        acc_num_dashed = acc_num
    
    base_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc_num_dashed}"
    
    # Try to get the index file
    urls_to_try = [
        f"{base_url}/{acc_num_dashed}-index.htm",
        f"{base_url}/{acc_num_dashed}-index.html",
    ]
    
    for url in urls_to_try:
        resp = requests.get(url, headers=HEADERS)
        if resp.status_code == 200:
            return resp.text, url
    
    # Fallback: try common patterns - extract document number
    acc_parts = acc_num_dashed.split('-')
    if len(acc_parts) == 3:
        doc_num = acc_parts[2]
        alt_url = f"{base_url}/{doc_num}.htm"
        resp = requests.get(alt_url, headers=HEADERS)
        if resp.status_code == 200:
            return resp.text, alt_url
    
    # Final fallback: SEC viewer
    doc_url = f"https://www.sec.gov/cgi-bin/viewer?action=view&cik={cik}&accession_number={acc_num_dashed}&xbrl_type=v"
    resp = requests.get(doc_url, headers=HEADERS)
    if resp.status_code == 200:
        return resp.text, doc_url
    
    return None, None

def parse_scale(text):
    """Detect scale from text (millions, thousands, billions)."""
    text = text.lower()
    if 'in millions' in text or '(in millions)' in text or '$ in millions' in text:
        return 'millions'
    elif 'in thousands' in text or '(in thousands)' in text or '$ in thousands' in text:
        return 'thousands'
    elif 'in billions' in text or '(in billions)' in text or '$ in billions' in text:
        return 'billions'
    return 'units'

def parse_number(val):
    """Parse a number from string, handling parentheses for negatives."""
    if val is None:
        return None
    val = str(val).strip()
    if not val or val == '—' or val == '-':
        return None
    
    # Remove currency symbols and commas
    val = re.sub(r'[$,]', '', val)
    
    # Handle parentheses for negative
    is_negative = False
    if val.startswith('(') and val.endswith(')'):
        is_negative = True
        val = val[1:-1]
    
    try:
        num = float(val)
        return -num if is_negative else num
    except ValueError:
        return None

def extract_metrics_from_html(html_content, filing_date, form_type):
    """Extract financial metrics from HTML filing."""
    soup = BeautifulSoup(html_content, 'lxml')
    text = soup.get_text().lower()
    
    # Detect scale
    scale = parse_scale(text)
    
    metrics = {
        'filing_date': filing_date,
        'scale': scale,
        'revenue': None,
        'gross_profit': None,
        'operating_income': None,
        'net_income': None,
        'operating_cash_flow': None,
        'capex': None,
    }
    
    # Find all tables
    tables = soup.find_all('table')
    
    revenue_patterns = ['total revenue', 'net sales', 'revenues', 'total net sales', 'net revenues']
    gross_patterns = ['gross profit', 'gross margin']
    operating_patterns = ['operating income', 'income from operations', 'operating earnings', 
                         'income before income taxes', 'income before taxes', 'pretax income']
    net_patterns = ['net income', 'net earnings', 'net loss']
    ocf_patterns = ['operating cash flow', 'cash from operating activities', 
                    'net cash provided by operating activities', 'cash flows from operations']
    capex_patterns = ['capital expenditures', 'capex', 'purchase of property', 'additions to property']
    
    for table in tables:
        rows = table.find_all('tr')
        for row in rows:
            cells = row.find_all(['td', 'th'])
            if len(cells) < 2:
                continue
            
            row_text = ' '.join(cell.get_text().lower().strip() for cell in cells)
            
            # Check for revenue
            if metrics['revenue'] is None:
                for pattern in revenue_patterns:
                    if pattern in row_text:
                        for cell in cells[1:]:
                            val = parse_number(cell.get_text())
                            if val and val > 0:
                                metrics['revenue'] = val
                                break
                        break
            
            # Check for gross profit
            if metrics['gross_profit'] is None:
                for pattern in gross_patterns:
                    if pattern in row_text:
                        for cell in cells[1:]:
                            val = parse_number(cell.get_text())
                            if val is not None:
                                metrics['gross_profit'] = val
                                break
                        break
            
            # Check for operating income
            if metrics['operating_income'] is None:
                for pattern in operating_patterns:
                    if pattern in row_text:
                        for cell in cells[1:]:
                            val = parse_number(cell.get_text())
                            if val is not None:
                                metrics['operating_income'] = val
                                break
                        break
            
            # Check for net income
            if metrics['net_income'] is None:
                for pattern in net_patterns:
                    if pattern in row_text:
                        for cell in cells[1:]:
                            val = parse_number(cell.get_text())
                            if val is not None:
                                metrics['net_income'] = val
                                break
                        break
            
            # Check for operating cash flow
            if metrics['operating_cash_flow'] is None:
                for pattern in ocf_patterns:
                    if pattern in row_text:
                        for cell in cells[1:]:
                            val = parse_number(cell.get_text())
                            if val is not None:
                                metrics['operating_cash_flow'] = val
                                break
                        break
            
            # Check for capex
            if metrics['capex'] is None:
                for pattern in capex_patterns:
                    if pattern in row_text:
                        for cell in cells[1:]:
                            val = parse_number(cell.get_text())
                            if val is not None:
                                metrics['capex'] = -abs(val)  # CapEx is always negative
                                break
                        break
    
    # Calculate derived metrics
    if metrics['revenue'] and metrics['gross_profit']:
        metrics['gross_margin'] = round((metrics['gross_profit'] / metrics['revenue']) * 100, 2)
    else:
        metrics['gross_margin'] = None
    
    if metrics['revenue'] and metrics['operating_income']:
        metrics['operating_margin'] = round((metrics['operating_income'] / metrics['revenue']) * 100, 2)
    else:
        metrics['operating_margin'] = None
    
    if metrics['revenue'] and metrics['net_income']:
        metrics['net_margin'] = round((metrics['net_income'] / metrics['revenue']) * 100, 2)
    else:
        metrics['net_margin'] = None
    
    if metrics['operating_cash_flow'] and metrics['capex']:
        metrics['free_cash_flow'] = metrics['operating_cash_flow'] + metrics['capex']
    else:
        metrics['free_cash_flow'] = None
    
    return metrics

def process_filings(ticker, cik, filings):
    """Process all filings and extract metrics."""
    results = []
    
    for i, filing in enumerate(filings):
        form = filing['form']
        filing_date = filing['date']
        year = filing['year']
        
        # Determine quarter label
        if form == '10-K':
            qlabel = f"FY'{str(year)[-2:]}"
            period_type = 'Annual'
        else:
            # Try to determine quarter from filing date
            month = int(filing_date.split('-')[1])
            if month <= 3:
                quarter = 'Q1'
            elif month <= 6:
                quarter = 'Q2'
            elif month <= 9:
                quarter = 'Q3'
            else:
                quarter = 'Q4'
            qlabel = f"{quarter}'{str(year)[-2:]}"
            period_type = 'Quarterly'
        
        print(f"  [{i+1}/{len(filings)}] Processing {form} filed {filing_date}...", end=" ", flush=True)
        
        html, url = fetch_filing_html(cik, filing['accessionNumber'])
        if html is None:
            print("FAILED to fetch")
            continue
        
        metrics = extract_metrics_from_html(html, filing_date, form)
        metrics['year'] = year
        metrics['qlabel'] = qlabel
        metrics['period_type'] = period_type
        metrics['form'] = form
        
        # Check if we got meaningful data
        if metrics['revenue'] is None and metrics['operating_income'] is None:
            print("NO DATA extracted")
            continue
        
        print(f"Revenue: {metrics['revenue']} ({metrics['scale']})")
        results.append(metrics)
        
        # Rate limiting
        time.sleep(0.15)
    
    return results

def calculate_cagr(start_val, end_val, years):
    """Calculate Compound Annual Growth Rate."""
    if start_val is None or end_val is None or start_val == 0 or years <= 0:
        return None
    if (start_val > 0 and end_val < 0) or (start_val < 0 and end_val > 0):
        return None  # Can't calculate CAGR across zero
    
    try:
        cagr = ((end_val / abs(start_val)) ** (1 / years)) - 1
        return round(cagr * 100, 2)
    except:
        return None

def generate_csv(results, filename):
    """Generate CSV output."""
    columns = ['filing_date', 'year', 'qlabel', 'period_type', 'scale', 
               'revenue', 'gross_profit', 'gross_margin', 
               'operating_income', 'operating_margin', 'net_income', 'net_margin',
               'operating_cash_flow', 'capex', 'free_cash_flow']
    
    with open(filename, 'w') as f:
        f.write(','.join(columns) + '\n')
        for r in results:
            row = []
            for col in columns:
                val = r.get(col)
                if val is None:
                    row.append('')
                elif isinstance(val, float):
                    row.append(str(round(val, 2)))
                else:
                    row.append(str(val))
            f.write(','.join(row) + '\n')
    
    print(f"\nCSV saved: {filename}")

def format_value(val, scale):
    """Format a value with appropriate suffix based on scale."""
    if val is None:
        return '—'
    
    # Normalize to raw number
    multiplier = {'millions': 1e6, 'thousands': 1e3, 'billions': 1e9, 'units': 1}.get(scale, 1)
    raw = val * multiplier
    
    # Format with appropriate suffix
    if abs(raw) >= 1e9:
        return f"{raw/1e9:.2f}B"
    elif abs(raw) >= 1e6:
        return f"{raw/1e6:.2f}M"
    elif abs(raw) >= 1e3:
        return f"{raw/1e3:.2f}K"
    else:
        return f"{raw:.2f}"

def generate_html_table(results, filename, ticker, start_year, end_year):
    """Generate rich HTML table with YoY changes and CAGR."""
    
    # Organize data by period
    periods = sorted(set(r['qlabel'] for r in results), 
                     key=lambda x: (int(x.split("'")[1]) if "'" in x else 99, x.split("'")[0]))
    
    # Build data matrix
    metrics_list = ['revenue', 'gross_profit', 'operating_income', 'net_income', 
                    'operating_cash_flow', 'capex', 'free_cash_flow']
    margins_list = ['gross_margin', 'operating_margin', 'net_margin']
    
    data_matrix = {}
    for metric in metrics_list + margins_list:
        data_matrix[metric] = {}
    
    for r in results:
        qlabel = r['qlabel']
        scale = r.get('scale', 'millions')
        for metric in metrics_list:
            data_matrix[metric][qlabel] = {'value': r.get(metric), 'scale': scale}
        for metric in margins_list:
            data_matrix[metric][qlabel] = {'value': r.get(metric), 'scale': 'percent'}
    
    # Calculate YoY changes
    def get_yoy(metric, qlabel):
        if "'" not in qlabel:
            return None, None
        
        quarter, year_suffix = qlabel.split("'")
        if quarter == 'FY':
            prev_year = str(int(year_suffix) - 1).zfill(2)
            prev_label = f"FY'{prev_year}"
        else:
            prev_year = str(int(year_suffix) - 1).zfill(2)
            prev_label = f"{quarter}'{prev_year}"
        
        curr = data_matrix[metric].get(qlabel, {}).get('value')
        prev = data_matrix[metric].get(prev_label, {}).get('value')
        
        if curr is None or prev is None:
            return None, None
        
        delta = curr - prev
        pct = round((delta / abs(prev)) * 100, 2) if prev != 0 else None
        return delta, pct
    
    # Calculate CAGR
    annual_periods = [p for p in periods if p.startswith('FY')]
    cagr_results = {}
    
    if len(annual_periods) >= 2:
        first_period = annual_periods[0]
        last_period = annual_periods[-1]
        years = len(annual_periods) - 1
        
        for metric in metrics_list:
            start_val = data_matrix[metric].get(first_period, {}).get('value')
            end_val = data_matrix[metric].get(last_period, {}).get('value')
            cagr = calculate_cagr(start_val, end_val, years)
            cagr_results[metric] = cagr
    
    # Generate HTML
    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{ticker} Financial Analysis ({start_year}-{end_year})</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 40px; background: #f5f5f5; }}
        .container {{ max-width: 1400px; margin: 0 auto; background: white; padding: 30px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
        h1 {{ color: #1a1a1a; border-bottom: 3px solid #2563eb; padding-bottom: 15px; }}
        h2 {{ color: #374151; margin-top: 30px; }}
        .subtitle {{ color: #6b7280; margin-bottom: 20px; }}
        table {{ width: 100%; border-collapse: collapse; margin: 20px 0; font-size: 13px; }}
        th, td {{ padding: 10px 8px; text-align: right; border-bottom: 1px solid #e5e7eb; }}
        th {{ background: #f8fafc; font-weight: 600; color: #374151; position: sticky; top: 0; }}
        th.metric {{ text-align: left; min-width: 180px; }}
        tr:hover {{ background: #f9fafb; }}
        .annual {{ background: #fef3c7 !important; }}
        .positive {{ color: #059669; }}
        .negative {{ color: #dc2626; }}
        .neutral {{ color: #6b7280; }}
        .sub-row {{ font-size: 12px; color: #6b7280; }}
        .sub-row-label {{ font-style: italic; padding-left: 25px; }}
        .cagr-section {{ margin-top: 30px; padding: 20px; background: #eff6ff; border-radius: 6px; }}
        .cagr-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin-top: 15px; }}
        .cagr-item {{ background: white; padding: 15px; border-radius: 6px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
        .cagr-label {{ font-size: 12px; color: #6b7280; text-transform: uppercase; }}
        .cagr-value {{ font-size: 24px; font-weight: bold; color: #2563eb; }}
        .legend {{ margin: 20px 0; padding: 15px; background: #f8fafc; border-radius: 6px; font-size: 13px; }}
        .legend-item {{ display: inline-block; margin-right: 20px; }}
        .legend-color {{ display: inline-block; width: 16px; height: 16px; margin-right: 5px; vertical-align: middle; border-radius: 3px; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>{ticker} Financial Analysis</h1>
        <p class="subtitle">Period: {start_year} - {end_year} | Values in reported units (see Scale column)</p>
        
        <div class="legend">
            <strong>Legend:</strong>
            <span class="legend-item"><span class="legend-color" style="background: #fef3c7;"></span>Annual (FY) periods</span>
            <span class="legend-item"><span class="legend-color" style="background: #059669;"></span>Positive growth</span>
            <span class="legend-item"><span class="legend-color" style="background: #dc2626;"></span>Negative growth</span>
        </div>
        
        <h2>Financial Metrics Table</h2>
        <p>Each metric shows: (1) Raw Value, (2) YoY Absolute Change, (3) YoY Percentage Change</p>
        <table>
            <thead>
                <tr>
                    <th class="metric">Metric</th>
'''
    
    # Add period columns
    for period in periods:
        is_annual = period.startswith('FY')
        style = 'class="annual"' if is_annual else ''
        html += f'                    <th {style}>{period}</th>\n'
    
    html += '''                </tr>
            </thead>
            <tbody>
'''
    
    # Add rows for each metric
    metric_labels = {
        'revenue': 'Revenue',
        'gross_profit': 'Gross Profit',
        'operating_income': 'Operating Income',
        'net_income': 'Net Income',
        'operating_cash_flow': 'Operating Cash Flow',
        'capex': 'Capital Expenditures',
        'free_cash_flow': 'Free Cash Flow',
    }
    
    for metric in metrics_list:
        label = metric_labels.get(metric, metric.replace('_', ' ').title())
        
        # Raw values row
        html += f'                <tr>\n                    <td class="metric"><strong>{label}</strong></td>\n'
        for period in periods:
            val = data_matrix[metric].get(period, {}).get('value')
            scale = data_matrix[metric].get(period, {}).get('scale', 'millions')
            formatted = format_value(val, scale)
            is_annual = period.startswith('FY')
            style = 'class="annual"' if is_annual else ''
            html += f'                    <td {style}>{formatted}</td>\n'
        html += '                </tr>\n'
        
        # YoY absolute change row
        html += f'                <tr class="sub-row">\n                    <td class="metric sub-row-label">↳ YoY Δ (abs)</td>\n'
        for period in periods:
            delta, _ = get_yoy(metric, period)
            is_annual = period.startswith('FY')
            style = 'class="annual"' if is_annual else ''
            if delta is None:
                html += f'                    <td {style}>—</td>\n'
            else:
                css_class = 'positive' if delta > 0 else ('negative' if delta < 0 else 'neutral')
                formatted_delta = f"{delta:+,.0f}"
                html += f'                    <td {style}><span class="{css_class}">{formatted_delta}</span></td>\n'
        html += '                </tr>\n'
        
        # YoY percentage change row
        html += f'                <tr class="sub-row">\n                    <td class="metric sub-row-label">↳ YoY Δ (%)</td>\n'
        for period in periods:
            _, pct = get_yoy(metric, period)
            is_annual = period.startswith('FY')
            style = 'class="annual"' if is_annual else ''
            if pct is None:
                html += f'                    <td {style}>—</td>\n'
            else:
                css_class = 'positive' if pct > 0 else ('negative' if pct < 0 else 'neutral')
                html += f'                    <td {style}><span class="{css_class}">{pct:+.2f}%</span></td>\n'
        html += '                </tr>\n'
    
    html += '''            </tbody>
        </table>
        
        <h2>Margins (%)</h2>
        <table>
            <thead>
                <tr>
                    <th class="metric">Margin Type</th>
'''
    
    for period in periods:
        is_annual = period.startswith('FY')
        style = 'class="annual"' if is_annual else ''
        html += f'                    <th {style}>{period}</th>\n'
    
    html += '''                </tr>
            </thead>
            <tbody>
'''
    
    margin_labels = {
        'gross_margin': 'Gross Margin',
        'operating_margin': 'Operating Margin',
        'net_margin': 'Net Margin',
    }
    
    for metric in margins_list:
        label = margin_labels.get(metric, metric.replace('_', ' ').title())
        html += f'                <tr>\n                    <td class="metric"><strong>{label}</strong></td>\n'
        for period in periods:
            val = data_matrix[metric].get(period, {}).get('value')
            is_annual = period.startswith('FY')
            style = 'class="annual"' if is_annual else ''
            if val is None:
                html += f'                    <td {style}>—</td>\n'
            else:
                html += f'                    <td {style}>{val:.2f}%</td>\n'
        html += '                </tr>\n'
    
    html += '''            </tbody>
        </table>
'''
    
    # CAGR Section
    if cagr_results:
        html += f'''
        <div class="cagr-section">
            <h2>CAGR Summary (FY {annual_periods[0]} - FY {annual_periods[-1]})</h2>
            <p>Compound Annual Growth Rate over the full period</p>
            <div class="cagr-grid">
'''
        for metric in metrics_list:
            cagr = cagr_results.get(metric)
            label = metric_labels.get(metric, metric.replace('_', ' ').title())
            if cagr is not None:
                css_class = 'positive' if cagr > 0 else ('negative' if cagr < 0 else 'neutral')
                html += f'''                <div class="cagr-item">
                    <div class="cagr-label">{label}</div>
                    <div class="cagr-value {css_class}">{cagr:+.2f}%</div>
                </div>
'''
            else:
                html += f'''                <div class="cagr-item">
                    <div class="cagr-label">{label}</div>
                    <div class="cagr-value neutral">N/A</div>
                </div>
'''
        html += '''            </div>
        </div>
'''
    
    html += '''
    </div>
</body>
</html>
'''
    
    with open(filename, 'w') as f:
        f.write(html)
    
    print(f"HTML table saved: {filename}")

def main():
    print("=" * 60)
    print("SEC Financial Data Toolkit")
    print("=" * 60)
    
    # Get user input
    ticker = input("\nEnter ticker symbol (e.g., AAPL, MSFT, GOOG): ").strip().upper()
    if not ticker:
        print("No ticker provided. Exiting.")
        return
    
    try:
        start_year = int(input("Enter start year (e.g., 2020): ").strip())
        end_year = int(input("Enter end year (e.g., 2024): ").strip())
    except ValueError:
        print("Invalid year. Exiting.")
        return
    
    if start_year > end_year:
        print("Start year must be <= end year. Exiting.")
        return
    
    print(f"\nFetching data for {ticker} from {start_year} to {end_year}...")
    
    try:
        # Get CIK
        print("Looking up CIK number...")
        cik = get_cik(ticker)
        print(f"CIK for {ticker}: {cik}")
        
        # Get filings
        print("Fetching filing list from SEC EDGAR...")
        filings = get_filings(cik, start_year, end_year)
        print(f"Found {len(filings)} filings (10-K and 10-Q)")
        
        if not filings:
            print("No filings found in the specified date range.")
            return
        
        # Process filings
        print("\nProcessing filings...")
        results = process_filings(ticker, cik, filings)
        
        if not results:
            print("No data could be extracted from filings.")
            return
        
        print(f"\nSuccessfully extracted data from {len(results)} filings")
        
        # Generate outputs
        csv_filename = f"{ticker}_financials_{start_year}_{end_year}.csv"
        html_filename = f"{ticker}_table_{start_year}_{end_year}.html"
        
        generate_csv(results, csv_filename)
        generate_html_table(results, html_filename, ticker, start_year, end_year)
        
        print("\n" + "=" * 60)
        print("COMPLETE!")
        print("=" * 60)
        print(f"Files generated:")
        print(f"  - {csv_filename}")
        print(f"  - {html_filename}")
        print("\nOpen the HTML file in any web browser to view the analysis.")
        
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
