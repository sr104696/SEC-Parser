# Goog Data — Combined Documentation

---

# SEC Financial Data Extractor

## Essential Files
- `sec_parser_smart.py` - Main script that extracts clean financial data
- `parse_sec.bat` - Double-click to run the parser
- `requirements.txt` - Python dependencies

## Setup (One-time)
```
pip install -r requirements.txt
```

## Usage
1. Double-click `parse_sec.bat`
2. Enter ticker (e.g., GOOG, AAPL, CASY)
3. Enter start year (e.g., 2021)
4. Enter end year (e.g., 2025)
5. Wait for processing
6. Get clean CSV: `{TICKER}_financials_{START}_{END}.csv`

## Output Format
The CSV contains these columns:
- `filing_date` - Date of SEC filing
- `year` - Fiscal year
- `quarter` - Q1/Q2/Q3/Q4 or FY (annual)
- `period_type` - "Quarterly" or "Annual"
- `revenue` - Total revenue
- `gross_profit` - Gross profit
- `gross_margin` - Gross margin %
- `operating_income` - Operating income
- `operating_margin` - Operating margin %
- `net_income` - Net income
- `net_margin` - Net margin %
- `operating_cash_flow` - Cash from operations
- `capex` - Capital expenditures (negative)
- `free_cash_flow` - OCF + CapEx

All monetary values are in thousands (as reported in SEC filings).

## Example Output
```
filing_date  year quarter period_type  revenue  operating_income  net_income  ...
2021-02-02   2021 FY      Annual       182527   41224            40269       ...
2021-04-27   2021 Q1      Quarterly    55314    16437            17930       ...
2021-07-27   2021 Q2      Quarterly    61983    19361            18525       ...
```

## Notes
- Automatically handles 10-Q (quarterly) and 10-K (annual) filings
- Extracts data from HTML tables in SEC filings
- Calculates margins automatically
- Handles negative numbers (parentheses notation)
- Respects SEC rate limits (0.15s delay between requests)

---

# Dashboard Changes Summary

## 1. Wired in JSON Data Source
- **Changed**: Data now loads from `alphabet_unified_data.json` instead of hardcoded arrays
- **Location**: Beginning of script section
- **Benefit**: Single source of truth, easier to update data

## 2. Fixed Empty Rows Bug in Drag Panel
**Root Cause**: The `computeStats` function was filtering out datasets where either the start OR end value was null/undefined. This caused all datasets to be filtered out when dragging across quarters with null values (e.g., YoY growth for Q1-Q3 2021).

**Original Code** (line 609):
```javascript
if(v0===null||v0===undefined||v1===null||v1===undefined||isNaN(v0)||isNaN(v1)) return;
```

**Fixed Code**:
```javascript
// Skip only if BOTH values are null/undefined, or if they're invalid numbers
if((v0===null||v0===undefined) && (v1===null||v1===undefined)) return;
if(v0!==null && v0!==undefined && isNaN(v0)) return;
if(v1!==null && v1!==undefined && isNaN(v1)) return;
```

**Additional Fixes**:
- Updated `delta` calculation to handle null values
- Updated `pctChg` calculation to check for null delta
- Updated `cagr` calculation to check for null values before computing

## 3. Restructured Code for Async Data Loading
- Wrapped all chart initialization in `initCharts()` function
- Wrapped trend bars in `initTrendBars()` function
- Wrapped raw data table in `initRawTable()` function
- All three functions called after data loads successfully
- Fallback to hardcoded data if JSON fetch fails

## 4. Optimizations Applied
- Removed duplicate `DR` (derived series) definition
- Moved derived series calculation inside `initCharts()` to use loaded data
- Maintained all existing functionality while fixing the core bug

## Testing Checklist
- [ ] Dashboard loads with JSON data
- [ ] All charts render correctly
- [ ] Drag-to-analyze works on all charts
- [ ] Panel shows data even when dragging across quarters with null values
- [ ] Trend bars populate correctly
- [ ] Raw data table populates correctly
- [ ] Fallback to hardcoded data works if JSON fails to load

---

# Dashboard Adaptation Prompt for LLM

## Your Task
You are an expert financial analyst and web developer. I need you to adapt the Google (GOOG) earnings dashboard to work with data from a different company. You will receive company financial data and must create a fully functional, customized HTML dashboard.

## What You'll Receive
I will provide you with:
1. **Company name and ticker symbol**
2. **Quarterly financial data** (20 quarters minimum) including:
   - Revenue segments (by business line/product)
   - Operating income by segment
   - Net income
   - Operating cash flow (OCF)
   - Capital expenditures (CapEx)
   - Free cash flow (FCF)
   - Any other relevant metrics

## What You Must Do

### Step 1: Data Mapping
1. **Identify the company's revenue segments** and map them to appropriate variable names
2. **Determine which metrics are available** (some companies may not have all metrics)
3. **Create the data structure** matching the format in the reference dashboard

### Step 2: Customize the Dashboard
1. **Update all branding**:
   - Company name and ticker
   - Title and subtitle
   - Color scheme (use company brand colors if known)

2. **Adapt revenue segments**:
   - Replace Google's segments (Search, YouTube, Network, Cloud, etc.) with the company's actual business segments
   - Update all chart labels and legends
   - Modify the segment colors to be visually distinct

3. **Adjust KPIs**:
   - Update the overview KPIs to reflect the most important metrics for this company
   - Calculate year-over-year growth rates
   - Compute margins and other derived metrics

4. **Customize insights**:
   - Replace the Google-specific insights with relevant analysis for the new company
   - Identify acceleration/deceleration trends
   - Highlight key business drivers and risks
   - Use appropriate badges (ACCELERATING, DECELERATING, PLATEAU, WATCH, RISK)

5. **Adapt tabs**:
   - Keep relevant tabs (Overview, Revenue Segments, Operating Income, Cash Flow)
   - Remove or modify tabs that don't apply (e.g., "Cloud Deep-Dive" if not a cloud company)
   - Add new tabs if the company has unique business characteristics

6. **Update forecast section** (if applicable):
   - Create scenario-based projections based on historical growth rates
   - Adjust assumptions to reflect the company's business model
   - Update the projection table with realistic estimates

### Step 3: Ensure Functionality
1. **Verify all charts render correctly** with the new data
2. **Test the drag-to-analyze feature** works on all charts
3. **Ensure tab switching** functions properly
4. **Validate all calculations** (YoY growth, margins, CAGR, etc.)
5. **Check responsive design** works on different screen sizes

### Step 4: Data Validation
Before finalizing, verify:
- All numbers are in the correct units (millions, billions, percentages)
- Quarterly labels match the actual reporting periods
- Year-over-year calculations use the correct quarters (Q1 vs Q1, not Q1 vs Q4)
- Margins are calculated correctly (operating income / revenue, etc.)
- Free cash flow = Operating cash flow - CapEx

## Output Format
Provide a complete, standalone HTML file that:
1. **Requires no external dependencies** except Chart.js CDN (already included)
2. **Is fully self-contained** with all data, styles, and scripts inline
3. **Matches the structure** of the reference dashboard
4. **Is production-ready** and can be opened directly in a browser

## Example Data Format You'll Receive

```javascript
// Example for a hypothetical company
const companyData = {
  ticker: "ACME",
  name: "Acme Corporation",
  quarters: ['Q1\'21', 'Q2\'21', 'Q3\'21', 'Q4\'21', ...],
  segments: {
    productA: [1200, 1350, 1420, 1580, ...],
    productB: [800, 850, 920, 1050, ...],
    services: [400, 450, 480, 520, ...],
  },
  operatingIncome: {
    productA: [300, 340, 360, 400, ...],
    productB: [150, 160, 180, 210, ...],
    services: [80, 90, 95, 105, ...],
    corporate: [-50, -55, -60, -65, ...],
  },
  totalRevenue: [2400, 2650, 2820, 3150, ...],
  totalOpIncome: [480, 535, 575, 650, ...],
  netIncome: [380, 425, 460, 520, ...],
  ocf: [500, 550, 600, 680, ...],
  capex: [-100, -110, -120, -130, ...],
  fcf: [400, 440, 480, 550, ...],
};
```

## Quality Checklist
Before submitting, ensure:
- [ ] All company-specific branding is updated
- [ ] All data series are correctly mapped
- [ ] All charts display properly
- [ ] Insights are relevant and accurate
- [ ] Color scheme is professional and accessible
- [ ] Drag-to-analyze feature works on all charts
- [ ] Tab navigation functions correctly
- [ ] Raw data table displays all metrics
- [ ] Forecast section (if included) has realistic assumptions
- [ ] No Google/GOOG references remain (except in comments)
- [ ] File opens and works in Chrome, Firefox, Safari, Edge

## Debugging Mode
If you encounter issues or the data doesn't fit the expected format, please:
1. **Ask clarifying questions** about the data structure
2. **Request missing data** if critical metrics are unavailable
3. **Suggest alternative visualizations** if the original charts don't suit the data
4. **Explain any assumptions** you make during adaptation
5. **Provide a summary** of what was changed and why

## Special Cases to Handle

### If the company has fewer segments:
- Simplify the segment charts
- Remove unused color variables
- Adjust the segment mix chart

### If the company has more segments:
- Add additional color variables
- Expand the stacked bar charts
- Consider grouping minor segments into "Other"

### If certain metrics are unavailable:
- Remove or hide those charts
- Update the tab structure
- Add a note explaining missing data

### If the company is not profitable:
- Adjust margin charts to handle negative values
- Update insights to focus on path to profitability
- Modify KPI cards to highlight relevant metrics (e.g., revenue growth, cash burn rate)

### If the company has different reporting periods:
- Adjust quarter labels (e.g., fiscal year vs calendar year)
- Update YoY calculations to match reporting cadence
- Clarify fiscal year in subtitle

## Now Provide Your Data
Please provide the company data in the format described above, and I will create a fully customized dashboard for you.

---

## Alternative: Debug Existing Dashboard
If you already have a dashboard that's not working correctly, provide:
1. The HTML file or relevant code sections
2. Description of the issue (charts not rendering, data errors, etc.)
3. The data you're trying to visualize
4. Any error messages from the browser console

I will diagnose and fix the issues.
