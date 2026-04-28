#!/usr/bin/env python3
"""SEC 10-Q/10-K financial extractor.

Prompts for ticker and year range, pulls all 10-Q and 10-K filings,
extracts core metrics via SEC company facts, writes CSV, and renders a rich HTML table.
"""

from __future__ import annotations

import csv
import datetime as dt
import json
import math
import os
import re
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple

SEC_BASE = "https://data.sec.gov"
USER_AGENT = os.getenv(
    "SEC_USER_AGENT", "FinancialParser/1.0 (email@example.com)"
)
REQUEST_DELAY_SECONDS = 0.2

METRIC_MAP = {
    "revenue": [
        "Revenues",
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "SalesRevenueNet",
        "RevenueFromContractWithCustomerIncludingAssessedTax",
    ],
    "profit": ["NetIncomeLoss", "ProfitLoss"],
    "operating_income": ["OperatingIncomeLoss", "IncomeLossFromOperations"],
    "operating_cash_flow": [
        "NetCashProvidedByUsedInOperatingActivities",
        "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
    ],
}


@dataclass
class Filing:
    form: str
    filing_date: dt.date
    report_date: Optional[dt.date]
    accession_number: str
    fiscal_period: str


@dataclass
class FactPoint:
    concept: str
    form: str
    end: Optional[dt.date]
    filed: Optional[dt.date]
    fp: str
    value: float


def get_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"HTTP error {exc.code} for URL: {url}") from exc


def parse_date(value: Optional[str]) -> Optional[dt.date]:
    if not value:
        return None
    try:
        return dt.date.fromisoformat(value)
    except ValueError:
        return None


def to_float(value) -> Optional[float]:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def ticker_to_cik(ticker: str) -> str:
    tickers = get_json(f"{SEC_BASE}/files/company_tickers.json")
    wanted = ticker.upper().strip()
    for row in tickers.values():
        if row.get("ticker", "").upper() == wanted:
            return f"{int(row['cik_str']):010d}"
    raise ValueError(f"Ticker '{ticker}' not found in SEC ticker list.")


def infer_period_label(form: str, fp: str, report_date: Optional[dt.date]) -> str:
    if form == "10-K":
        year = report_date.year if report_date else dt.date.today().year
        return f"FY{str(year)[-2:]}"
    if fp and re.fullmatch(r"Q[1-4]", fp):
        year = report_date.year if report_date else dt.date.today().year
        return f"{fp}{str(year)[-2:]}"
    if fp:
        year = report_date.year if report_date else dt.date.today().year
        return f"{fp}{str(year)[-2:]}"
    year = report_date.year if report_date else dt.date.today().year
    return f"Q?{str(year)[-2:]}"


def fetch_filings(cik: str, start_year: int, end_year: int) -> List[Filing]:
    data = get_json(f"{SEC_BASE}/submissions/CIK{cik}.json")
    recent = data.get("filings", {}).get("recent", {})

    forms = recent.get("form", [])
    filing_dates = recent.get("filingDate", [])
    report_dates = recent.get("reportDate", [])
    accessions = recent.get("accessionNumber", [])
    fiscal_periods = recent.get("fiscalPeriod", [])

    out: List[Filing] = []
    for idx, form in enumerate(forms):
        if form not in {"10-Q", "10-K"}:
            continue

        filing_date = parse_date(filing_dates[idx])
        if not filing_date:
            continue
        if filing_date.year < start_year or filing_date.year > end_year:
            continue

        out.append(
            Filing(
                form=form,
                filing_date=filing_date,
                report_date=parse_date(report_dates[idx]) if idx < len(report_dates) else None,
                accession_number=accessions[idx] if idx < len(accessions) else "",
                fiscal_period=fiscal_periods[idx] if idx < len(fiscal_periods) else "",
            )
        )

    out.sort(key=lambda f: (f.filing_date, f.form))
    return out


def load_company_facts(cik: str) -> Dict[str, List[FactPoint]]:
    facts_json = get_json(f"{SEC_BASE}/api/xbrl/companyfacts/CIK{cik}.json")
    gaap = facts_json.get("facts", {}).get("us-gaap", {})

    points: Dict[str, List[FactPoint]] = {}
    for metric, concepts in METRIC_MAP.items():
        metric_points: List[FactPoint] = []
        for concept in concepts:
            node = gaap.get(concept)
            if not node:
                continue
            units = node.get("units", {})
            for unit_name, arr in units.items():
                if unit_name not in {"USD", "USDm", "USDth"}:
                    continue
                for item in arr:
                    val = to_float(item.get("val"))
                    if val is None:
                        continue
                    metric_points.append(
                        FactPoint(
                            concept=concept,
                            form=item.get("form", ""),
                            end=parse_date(item.get("end")),
                            filed=parse_date(item.get("filed")),
                            fp=item.get("fp", ""),
                            value=val,
                        )
                    )
        points[metric] = metric_points
    return points


def closest_point(points: Iterable[FactPoint], filing: Filing) -> Optional[FactPoint]:
    report_date = filing.report_date or filing.filing_date
    candidates = [p for p in points if p.form == filing.form]
    if not candidates:
        return None

    def score(p: FactPoint) -> Tuple[int, int, int, int]:
        end_gap = abs((p.end - report_date).days) if p.end else 3650
        filed_gap = abs((p.filed - filing.filing_date).days) if p.filed else 3650
        fp_mismatch = 0 if (filing.fiscal_period and p.fp == filing.fiscal_period) else 1
        form_mismatch = 0 if p.form == filing.form else 1
        return (fp_mismatch, end_gap, filed_gap, form_mismatch)

    best = min(candidates, key=score)
    best_end_gap = abs((best.end - report_date).days) if best.end else 3650
    if best_end_gap > 190:
        return None
    return best


def pct_change(cur: Optional[float], prev: Optional[float]) -> Optional[float]:
    if cur is None or prev is None or prev == 0:
        return None
    return ((cur - prev) / abs(prev)) * 100.0


def calc_cagr(start: Optional[float], end: Optional[float], periods: float) -> Optional[float]:
    if start is None or end is None or periods <= 0 or start <= 0 or end <= 0:
        return None
    return (end / start) ** (1 / periods) - 1


def format_num(value: Optional[float]) -> str:
    if value is None:
        return ""
    return f"{value:,.0f}"


def format_pct(value: Optional[float]) -> str:
    if value is None or math.isinf(value) or math.isnan(value):
        return ""
    return f"{value:.2f}%"


def derive_rows(filings: List[Filing], facts: Dict[str, List[FactPoint]]) -> List[dict]:
    rows: List[dict] = []
    for filing in filings:
        row = {
            "filing_date": filing.filing_date.isoformat(),
            "report_date": filing.report_date.isoformat() if filing.report_date else "",
            "form": filing.form,
            "period_label": infer_period_label(
                filing.form, filing.fiscal_period, filing.report_date
            ),
            "year": filing.report_date.year if filing.report_date else filing.filing_date.year,
        }

        for metric, points in facts.items():
            p = closest_point(points, filing)
            row[metric] = p.value if p else None
            row[f"{metric}_concept"] = p.concept if p else ""

        rows.append(row)

    rows.sort(key=lambda r: (r["filing_date"], r["form"]))

    # compute deltas
    index_by_key: Dict[Tuple[str, int], dict] = {}
    prev_row: Optional[dict] = None
    for row in rows:
        yr = int(row["year"])
        q = row["period_label"][:2] if row["period_label"].startswith("Q") else "FY"
        index_by_key[(q, yr)] = row

        for metric in METRIC_MAP.keys():
            cur = row.get(metric)
            prev = prev_row.get(metric) if prev_row else None
            row[f"{metric}_delta_prev"] = (cur - prev) if cur is not None and prev is not None else None
            row[f"{metric}_pct_prev"] = pct_change(cur, prev)

            yoy_row = index_by_key.get((q, yr - 1))
            yoy_val = yoy_row.get(metric) if yoy_row else None
            row[f"{metric}_delta_yoy"] = (cur - yoy_val) if cur is not None and yoy_val is not None else None
            row[f"{metric}_pct_yoy"] = pct_change(cur, yoy_val)

        prev_row = row

    return rows


def write_csv(path: str, rows: List[dict]) -> None:
    fields = [
        "filing_date",
        "report_date",
        "form",
        "period_label",
        "year",
    ]
    for metric in METRIC_MAP.keys():
        fields.extend(
            [
                metric,
                f"{metric}_concept",
                f"{metric}_delta_prev",
                f"{metric}_pct_prev",
                f"{metric}_delta_yoy",
                f"{metric}_pct_yoy",
            ]
        )

    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def build_cagr_summary(rows: List[dict]) -> List[Tuple[str, str, Optional[float]]]:
    summary: List[Tuple[str, str, Optional[float]]] = []

    for metric in METRIC_MAP.keys():
        vals = [(idx, r.get(metric)) for idx, r in enumerate(rows) if r.get(metric) is not None]
        if len(vals) < 2:
            summary.append((metric, "Overall", None))
            continue

        (i0, v0), (i1, v1) = vals[0], vals[-1]
        years = max((i1 - i0) / 4.0, 0.25)
        summary.append((metric, "Overall", calc_cagr(v0, v1, years)))

        annual = [r for r in rows if r["form"] == "10-K" and r.get(metric) is not None]
        if len(annual) >= 2:
            y0, y1 = annual[0], annual[-1]
            periods = max(int(y1["year"]) - int(y0["year"]), 1)
            summary.append((metric, "Annual", calc_cagr(y0[metric], y1[metric], periods)))
        else:
            summary.append((metric, "Annual", None))

        quarterly = [r for r in rows if r["form"] == "10-Q" and r.get(metric) is not None]
        if len(quarterly) >= 2:
            q0, q1 = quarterly[0], quarterly[-1]
            periods = max((len(quarterly) - 1) / 4.0, 0.25)
            summary.append((metric, "Quarterly", calc_cagr(q0[metric], q1[metric], periods)))
        else:
            summary.append((metric, "Quarterly", None))

    return summary


def write_html(path: str, ticker: str, rows: List[dict], cagr_summary: List[Tuple[str, str, Optional[float]]]) -> None:
    headers = [
        "filing_date",
        "report_date",
        "form",
        "period_label",
        "year",
    ]
    for metric in METRIC_MAP.keys():
        headers.extend(
            [
                metric,
                f"{metric}_delta_prev",
                f"{metric}_pct_prev",
                f"{metric}_delta_yoy",
                f"{metric}_pct_yoy",
            ]
        )

    def cell(h: str, val) -> str:
        if isinstance(val, str):
            return val
        if h.endswith("_pct_prev") or h.endswith("_pct_yoy"):
            return format_pct(val)
        if h in {"year"}:
            return str(val)
        return format_num(val)

    table_rows = []
    for row in rows:
        cls = "annual" if row.get("form") == "10-K" else "quarterly"
        tds = "".join(f"<td>{cell(h, row.get(h))}</td>" for h in headers)
        table_rows.append(f"<tr class='{cls}'>{tds}</tr>")

    cagr_rows = "\n".join(
        f"<tr><td>{metric}</td><td>{scope}</td><td>{format_pct(val * 100 if val is not None else None)}</td></tr>"
        for metric, scope, val in cagr_summary
    )

    html = f"""<!doctype html>
<html>
<head>
  <meta charset='utf-8' />
  <title>{ticker} SEC Financial Summary</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 20px; background:#f6f8fb; color:#1a1f2e; }}
    h1 {{ margin-bottom: 4px; }}
    .subtitle {{ margin-top:0; color:#445; }}
    table {{ border-collapse: collapse; width: 100%; background:white; }}
    th, td {{ border: 1px solid #dde4f0; padding: 6px 8px; font-size: 12px; text-align: right; }}
    th {{ position: sticky; top:0; background:#132238; color:#fff; z-index:2; }}
    td:first-child, td:nth-child(2), td:nth-child(3), td:nth-child(4) {{ text-align:left; }}
    tr.annual {{ background:#fff9e6; }}
    tr:hover {{ background:#eef4ff; }}
    .wrap {{ overflow:auto; max-height: 68vh; border:1px solid #ccd8ea; }}
    .cards {{ display:grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap:12px; margin:14px 0; }}
    .card {{ background:white; border:1px solid #ccd8ea; border-radius:8px; padding:10px; }}
    .small {{ color:#556; font-size:12px; margin:0; }}
  </style>
</head>
<body>
  <h1>{ticker} 10-Q / 10-K Financial Extraction</h1>
  <p class='subtitle'>Metrics include raw values, sequential and YoY changes, plus CAGRs.</p>
  <div class='cards'>
    <div class='card'><p class='small'>Filings pulled</p><h3>{len(rows)}</h3></div>
    <div class='card'><p class='small'>Quarterly filings</p><h3>{sum(1 for r in rows if r['form']=='10-Q')}</h3></div>
    <div class='card'><p class='small'>Annual filings</p><h3>{sum(1 for r in rows if r['form']=='10-K')}</h3></div>
  </div>
  <div class='wrap'>
    <table>
      <thead><tr>{''.join(f'<th>{h}</th>' for h in headers)}</tr></thead>
      <tbody>
        {''.join(table_rows)}
      </tbody>
    </table>
  </div>
  <h2>CAGR Summary</h2>
  <table>
    <thead><tr><th>Metric</th><th>Scope</th><th>CAGR</th></tr></thead>
    <tbody>{cagr_rows}</tbody>
  </table>
</body>
</html>
"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)


def ask_inputs() -> Tuple[str, int, int]:
    if len(sys.argv) >= 4:
        ticker = sys.argv[1].strip().upper()
        start = int(sys.argv[2])
        end = int(sys.argv[3])
    else:
        ticker = input("Enter ticker (e.g., AAPL): ").strip().upper()
        if not ticker:
            raise ValueError("Ticker is required.")
        start = int(input("Enter start year (e.g., 2020): ").strip())
        end = int(input("Enter end year (e.g., 2025): ").strip())

    if end < start:
        raise ValueError("End year must be >= start year.")
    return ticker, start, end


def main() -> int:
    try:
        ticker, start_year, end_year = ask_inputs()
        print(f"Resolving CIK for {ticker}...")
        cik = ticker_to_cik(ticker)
        time.sleep(REQUEST_DELAY_SECONDS)

        print(f"Fetching filings ({start_year}-{end_year})...")
        filings = fetch_filings(cik, start_year, end_year)
        if not filings:
            print("No 10-Q or 10-K filings found in that year range.")
            return 1

        print(f"Found {len(filings)} filings. Fetching company facts...")
        time.sleep(REQUEST_DELAY_SECONDS)
        facts = load_company_facts(cik)

        print("Matching metrics to filings...")
        rows = derive_rows(filings, facts)

        out_base = f"{ticker}_financials_{start_year}_{end_year}"
        csv_path = f"{out_base}.csv"
        html_path = f"{out_base}.html"

        write_csv(csv_path, rows)
        write_html(html_path, ticker, rows, build_cagr_summary(rows))

        print(f"Done. CSV: {csv_path}")
        print(f"Done. HTML: {html_path}")
        return 0
    except Exception as exc:  # keep UX friendly for .bat launch
        print(f"Error: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
