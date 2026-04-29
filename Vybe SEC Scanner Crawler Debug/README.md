# Vybe SEC Scanner Crawler Debug

This folder contains a hardened crawler/debug harness for the Vybe SEC Scanner app:

```text
https://sec-scanner-abd-inc22.vybe.build/
```

It is designed to scrape hydrated Vybe/SPA pages, submit a ticker query before capture, and write both Markdown output and diagnostic artifacts.

## What was fixed from the pasted script

- Fixed the Python entrypoint: `if __name__ == "__main__":`.
- Fixed broken multiline f-string generation.
- Avoids relying on `networkidle` as the only readiness condition.
- Waits for SPA hydration and body-text stability.
- Preserves SPA hash routes such as `#/dashboard` while dropping plain anchors.
- Collects links before removing nav/header/footer.
- Filters asset/API/logout links.
- Captures browser console warnings/errors.
- Captures failed network requests.
- Saves debug HTML/screenshots when output is empty or too short.
- Adds ticker form interaction, defaulting to `BE`, so the crawler tests the stock-query flow rather than just the landing page.

## Files

| File | Purpose |
|---|---|
| `crawl_vybe_app.py` | Main Playwright crawler and debug harness |
| `run_scrape.bat` | Windows one-click runner with venv/dependency setup |
| `requirements.txt` | Python dependencies |
| `APP_PATCH_NOTES.md` | Findings and app optimization plan |

Generated local folders after running:

| Folder | Purpose |
|---|---|
| `output/` | Markdown crawl result |
| `debug/` | HTML, screenshots, diagnostics JSON |
| `.venv/` | Local Python virtual environment |

## Windows quick start

From this folder:

```bat
run_scrape.bat
```

Default behavior:

- URL: `https://sec-scanner-abd-inc22.vybe.build/`
- Ticker: `BE`
- Output: `output\sec_scanner_vybe_full.md`
- Diagnostics: `debug\diagnostics.json`

## Run another ticker

```bat
set TICKER=AAPL
run_scrape.bat
```

Or:

```bat
set TICKER=BRK.B
run_scrape.bat
```

## Run any Vybe app URL

```bat
run_scrape.bat https://your-app.vybe.build/
```

## Headed debug mode

Use this if the app still does not scrape correctly or if you want to watch the browser:

```bat
set TICKER=BE
run_scrape.bat https://sec-scanner-abd-inc22.vybe.build/ --headed --settle-ms 5000 --concurrency 1
```

## Manual Python usage

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium
python crawl_vybe_app.py https://sec-scanner-abd-inc22.vybe.build/ --ticker BE --output output/sec_scanner_vybe_full.md --debug-dir debug
```

## Debug checklist

After each run, inspect:

1. `output/sec_scanner_vybe_full.md` — scraped app content and ticker result.
2. `debug/diagnostics.json` — visited routes, interaction log, console errors, request failures.
3. `debug/*.png` — screenshots for short/empty/error captures.
4. `debug/*.html` — raw DOM for failed captures.

## Test ticker matrix

Recommended manual tests:

| Ticker | Why |
|---|---|
| `BE` | Original failing/requested test ticker |
| `AAPL` | Common large-cap baseline |
| `MSFT` | Common large-cap baseline |
| `TSLA` | High-volume filings/news baseline |
| `BRK.B` | Dot-class ticker support |
| `INVALID123` | Error handling / invalid input |
| empty input | Required-field validation |

## Notes

If the app uses custom controls that are not real `input`, `textarea`, or button elements, inspect `debug/root_empty_or_short.html` and adjust `find_ticker_input()` / `click_likely_submit()` in `crawl_vybe_app.py`.
