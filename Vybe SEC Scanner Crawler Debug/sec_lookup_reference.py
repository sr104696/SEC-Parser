import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

COMPANY_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
USER_AGENT = "SEC-Parser Reference/1.0 contact@example.com"


def normalize_ticker(value: str) -> str:
    return value.strip().upper()


def ticker_variants(value: str) -> set[str]:
    ticker = normalize_ticker(value)
    return {ticker, ticker.replace(".", "-"), ticker.replace("-", ".")}


def sec_get_json(url: str) -> dict:
    request = Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept-Encoding": "gzip, deflate",
            "Accept": "application/json,text/plain,*/*",
        },
    )
    try:
        with urlopen(request, timeout=30) as response:
            raw = response.read()
            encoding = response.headers.get_content_charset() or "utf-8"
            return json.loads(raw.decode(encoding))
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:1000]
        raise RuntimeError(f"SEC HTTP {exc.code} for {url}: {body}") from exc
    except URLError as exc:
        raise RuntimeError(f"Network error for {url}: {exc}") from exc


def load_companies() -> list[dict]:
    data = sec_get_json(COMPANY_TICKERS_URL)
    return list(data.values())


def find_company(ticker: str, companies: list[dict]) -> dict:
    wanted = ticker_variants(ticker)
    for company in companies:
        sec_ticker = normalize_ticker(str(company.get("ticker", "")))
        if sec_ticker in wanted or sec_ticker.replace("-", ".") in wanted or sec_ticker.replace(".", "-") in wanted:
            cik = str(company["cik_str"]).zfill(10)
            return {
                "cik": cik,
                "ticker": sec_ticker,
                "title": company.get("title", ""),
                "raw": company,
            }
    raise ValueError(f"No SEC company found for ticker: {ticker}")


def fetch_recent_filings(cik: str) -> dict:
    return sec_get_json(SUBMISSIONS_URL.format(cik=cik))


def recent_filings_table(submissions: dict, limit: int) -> list[dict]:
    recent = submissions.get("filings", {}).get("recent", {})
    rows = []

    forms = recent.get("form", [])
    filing_dates = recent.get("filingDate", [])
    report_dates = recent.get("reportDate", [])
    accession_numbers = recent.get("accessionNumber", [])
    primary_docs = recent.get("primaryDocument", [])

    for idx, form in enumerate(forms[:limit]):
        accession = accession_numbers[idx] if idx < len(accession_numbers) else ""
        doc = primary_docs[idx] if idx < len(primary_docs) else ""
        rows.append(
            {
                "form": form,
                "filingDate": filing_dates[idx] if idx < len(filing_dates) else "",
                "reportDate": report_dates[idx] if idx < len(report_dates) else "",
                "accessionNumber": accession,
                "primaryDocument": doc,
            }
        )
    return rows


def to_markdown(ticker: str, company: dict, submissions: dict, rows: list[dict]) -> str:
    generated = datetime.now(timezone.utc).isoformat()
    lines = [
        f"# SEC Lookup Reference — {normalize_ticker(ticker)}",
        "",
        f"Generated: `{generated}`",
        "",
        f"Company: **{company['title']}**",
        f"Ticker: `{company['ticker']}`",
        f"CIK: `{company['cik']}`",
        f"Entity type: `{submissions.get('entityType', '')}`",
        f"SIC: `{submissions.get('sic', '')}` {submissions.get('sicDescription', '')}",
        "",
        "## Recent Filings",
        "",
        "| Form | Filing Date | Report Date | Accession | Primary Document |",
        "|---|---:|---:|---|---|",
    ]

    for row in rows:
        lines.append(
            f"| {row['form']} | {row['filingDate']} | {row['reportDate']} | `{row['accessionNumber']}` | {row['primaryDocument']} |"
        )

    if not rows:
        lines.append("| _No recent filings returned_ |  |  |  |  |")

    lines.append("")
    return "\n".join(lines)


def parse_args():
    parser = argparse.ArgumentParser(description="Reference SEC ticker lookup and filings fetch.")
    parser.add_argument("ticker", nargs="?", default="BE", help="Ticker to query, default BE.")
    parser.add_argument("--limit", type=int, default=20, help="Number of recent filings to show.")
    parser.add_argument("--output", default="output/sec_lookup_reference.md", help="Markdown output file.")
    parser.add_argument("--json", action="store_true", help="Print compact JSON instead of Markdown.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    companies = load_companies()
    company = find_company(args.ticker, companies)
    submissions = fetch_recent_filings(company["cik"])
    rows = recent_filings_table(submissions, limit=args.limit)

    if args.json:
        print(json.dumps({"company": company, "recentFilings": rows}, indent=2))
        return

    markdown = to_markdown(args.ticker, company, submissions, rows)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(markdown, encoding="utf-8")
    print(markdown)
    print(f"\nWrote: {out}")


if __name__ == "__main__":
    main()
