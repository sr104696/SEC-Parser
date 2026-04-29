# SEC Scanner App Patch Notes and Optimization Plan

Target app:

```text
https://sec-scanner-abd-inc22.vybe.build/
```

Primary regression target:

```text
Ticker: BE
```

## Crawler/debug harness goal

The local crawler is built to reproduce the app flow by loading the Vybe app, submitting ticker `BE`, waiting for hydrated SPA/API output, and exporting the resulting DOM to Markdown. If it cannot capture meaningful content, it writes debug HTML, screenshots, and diagnostics so the app can be patched iteratively.

## Likely app failure points to patch

| Area | Symptom | Patch |
|---|---|---|
| Ticker validation | `BE` or dotted tickers fail, empty input crashes | Normalize with `trim().toUpperCase()`, allow `A-Z`, digits, `.`, `-`; show validation errors instead of throwing |
| Ticker to CIK lookup | App cannot find valid company | Use SEC `company_tickers.json`, compare normalized ticker exactly, pad CIK to 10 digits |
| SEC request headers | SEC request blocked or inconsistent | Include clear `User-Agent` on server-side requests |
| Client-side SEC fetch | Browser CORS/rate-limit issues | Proxy SEC API calls through backend/Vybe server action where possible |
| Loading state | UI appears frozen | Add loading spinner/skeleton and disable submit while request is active |
| Error state | Blank page or silent failure | Show structured error panel with HTTP status, endpoint, and retry action |
| Rate limiting | Repeated searches fail | Debounce submit and cache ticker map/filing responses with TTL |
| Filing list | Results stale/confusing | Sort by `filingDate` descending and include accession number, form, report date, primary document |
| Invalid ticker | App throws or shows raw JSON | Return friendly `No SEC company found for ticker` state |
| Dotted ticker | `BRK.B` rejected | Normalize user ticker and SEC ticker consistently; support dot-class shares |
| Accessibility | Crawler/humans cannot target input reliably | Add explicit labels, stable placeholders, `aria-label="Ticker symbol"`, and button text `Search` |

## Recommended app behavior

1. User enters ticker.
2. App normalizes ticker.
3. App validates ticker format.
4. App loads cached SEC company ticker map.
5. App finds exact ticker match and CIK.
6. App fetches recent submissions for padded CIK.
7. App renders:
   - Company name
   - CIK
   - Latest forms table
   - Filing dates
   - Report dates
   - Links to SEC documents
8. App shows raw diagnostics behind a collapsible debug panel.

## Test matrix

| Test | Expected result |
|---|---|
| `BE` | Finds Bloom Energy / correct CIK and recent filings |
| `AAPL` | Finds Apple and renders recent filings |
| `MSFT` | Finds Microsoft and renders recent filings |
| `TSLA` | Finds Tesla and renders recent filings |
| `BRK.B` | Supports dotted ticker or explains normalization limitation |
| `INVALID123` | Friendly no-match error, no crash |
| empty input | Validation message, no network call |
| rapid repeated submits | Debounced, no duplicate request storm |

## Implementation sketch

```ts
type SecCompany = {
  cik_str: number;
  ticker: string;
  title: string;
};

function normalizeTicker(value: string) {
  return value.trim().toUpperCase();
}

function isValidTicker(value: string) {
  return /^[A-Z0-9.-]{1,12}$/.test(value);
}

function padCik(cik: number | string) {
  return String(cik).padStart(10, '0');
}

async function findCompanyByTicker(ticker: string) {
  const normalized = normalizeTicker(ticker);
  if (!isValidTicker(normalized)) throw new Error('Invalid ticker format');

  const companies = await getCachedCompanyTickerMap();
  const match = companies.find((item) => normalizeTicker(item.ticker) === normalized);

  if (!match) throw new Error(`No SEC company found for ticker ${normalized}`);

  return {
    ...match,
    cik: padCik(match.cik_str),
  };
}
```

## UX patch checklist

- [ ] Input has visible label and `aria-label="Ticker symbol"`.
- [ ] Submit button text is stable: `Search` or `Scan`.
- [ ] Loading state appears immediately after submit.
- [ ] Friendly validation errors.
- [ ] Friendly network/API errors.
- [ ] Retry button.
- [ ] Debug details panel for diagnostics.
- [ ] Results are keyboard accessible.
- [ ] Mobile layout does not overflow.
- [ ] Automated/manual tests cover `BE`.

## Crawler-specific next steps

1. Run `run_scrape.bat` from this folder.
2. Review `output/sec_scanner_vybe_full.md`.
3. If output is short/empty, review `debug/root_empty_or_short.png` and `.html`.
4. If the app uses non-standard controls, patch `find_ticker_input()` and `click_likely_submit()`.
5. Re-run with `--headed --settle-ms 5000 --concurrency 1` until the BE result is visible in Markdown.
