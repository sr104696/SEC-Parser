import argparse
import asyncio
import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urljoin, urlparse, urlunparse

from markdownify import markdownify as md
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout


DEFAULT_BASE_URL = "https://sec-scanner-abd-inc22.vybe.build/"
DEFAULT_OUTPUT_MD = "output/sec_scanner_vybe_full.md"
DEFAULT_DEBUG_DIR = "debug"
DEFAULT_MAX_PAGES = 50
DEFAULT_CONCURRENCY = 4

CONTENT_SELECTORS = [
    "main",
    "[role='main']",
    "#root",
    "#__next",
    "[data-vybe-root]",
    "body",
]

NAV_SELECTORS = [
    "nav",
    "header",
    "footer",
    "[aria-label='navigation']",
    "[aria-label='Navigation']",
    "[role='navigation']",
]

SKIP_PATH_PREFIXES = (
    "/api/",
    "/_next/",
    "/assets/",
    "/static/",
    "/node_modules/",
    "/.well-known/",
)

SKIP_EXTENSIONS = (
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".ico",
    ".css", ".js", ".map", ".woff", ".woff2", ".ttf", ".eot",
    ".pdf", ".zip", ".gz", ".mp4", ".webm", ".mov", ".mp3", ".wav",
)

BUTTON_RE = re.compile(r"search|scan|analy[sz]e|submit|run|query|lookup|get filings", re.I)
INPUT_HINT_RE = re.compile(r"ticker|symbol|stock|company|cik|search", re.I)


@dataclass
class CrawlState:
    visited: set[str] = field(default_factory=set)
    order: dict[str, int] = field(default_factory=dict)
    results: list[tuple[int, str]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    console_errors: list[str] = field(default_factory=list)
    request_failures: list[str] = field(default_factory=list)
    interactions: list[str] = field(default_factory=list)


def is_route_fragment(fragment: str) -> bool:
    """Keep hash-router fragments, drop plain page anchors."""
    return fragment.startswith("/") or fragment.startswith("!/")


def normalize_url(url: str) -> str:
    """Normalize URLs while preserving query strings and SPA route fragments."""
    p = urlparse(url)
    fragment = p.fragment if is_route_fragment(p.fragment) else ""
    path = p.path.rstrip("/") or "/"
    return urlunparse((p.scheme.lower(), p.netloc.lower(), path, p.params, p.query, fragment))


def should_skip_url(url: str, base_netloc: str) -> bool:
    p = urlparse(url)

    if p.scheme not in {"http", "https"}:
        return True
    if p.netloc.lower() != base_netloc.lower():
        return True

    path_lower = p.path.lower()
    if any(path_lower.startswith(prefix) for prefix in SKIP_PATH_PREFIXES):
        return True
    if path_lower.endswith(SKIP_EXTENSIONS):
        return True
    if any(part in path_lower for part in ["/logout", "/signout", "/delete"]):
        return True

    return False


def clean_text(html: str) -> str:
    text = md(
        html,
        heading_style="ATX",
        code_language_detection=True,
        strip=["script", "style", "noscript"],
    )
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()


def safe_debug_name(url: str, suffix: str = "") -> str:
    parsed = urlparse(url)
    raw = (parsed.path.strip("/") or "root") + ("_" + parsed.fragment if parsed.fragment else "")
    safe = re.sub(r"[^a-zA-Z0-9._-]+", "_", raw).strip("_")[:90] or "root"
    return f"{safe}{suffix}"


async def wait_for_text_stability(page, max_wait_ms: int = 5000, interval_ms: int = 300) -> None:
    """Wait until body text length stabilizes, useful for hydrated SPA/API content."""
    deadline = time.perf_counter() + max_wait_ms / 1000
    last_len = -1
    stable_ticks = 0

    while time.perf_counter() < deadline:
        try:
            text_len = await page.evaluate("() => (document.body?.innerText || '').length")
        except Exception:
            text_len = 0

        if text_len == last_len and text_len > 0:
            stable_ticks += 1
            if stable_ticks >= 3:
                return
        else:
            stable_ticks = 0
            last_len = text_len

        await page.wait_for_timeout(interval_ms)


async def wait_for_app_content(page, settle_ms: int) -> None:
    found = False
    for selector in CONTENT_SELECTORS:
        try:
            await page.wait_for_selector(selector, state="attached", timeout=2500)
            found = True
            break
        except PlaywrightTimeout:
            continue

    try:
        await page.wait_for_load_state("networkidle", timeout=4000)
    except PlaywrightTimeout:
        pass

    await wait_for_text_stability(page, max_wait_ms=max(1500, settle_ms))
    await page.wait_for_timeout(settle_ms)

    if not found:
        await page.wait_for_timeout(1000)


async def attach_diagnostics(page, state: CrawlState, url: str) -> None:
    page.on("console", lambda msg: state.console_errors.append(f"{url} :: {msg.type}: {msg.text}") if msg.type in {"error", "warning"} else None)
    page.on("requestfailed", lambda req: state.request_failures.append(f"{url} :: {req.method} {req.url} :: {req.failure}"))


async def extract_raw_links_from_frame(frame) -> list[str]:
    js = """
    () => {
      const values = new Set();

      for (const el of document.querySelectorAll('a[href], area[href]')) {
        const href = el.getAttribute('href');
        if (href) values.add(href);
        if (el.href) values.add(el.href);
      }

      const attrs = ['to', 'data-href', 'data-url', 'data-path', 'data-route'];
      for (const el of document.querySelectorAll('*')) {
        for (const attr of attrs) {
          const value = el.getAttribute(attr);
          if (value) values.add(value);
        }
      }

      return Array.from(values);
    }
    """
    try:
        return await frame.evaluate(js)
    except Exception:
        return []


async def get_internal_links(page, current_url: str, base_netloc: str) -> set[str]:
    raw_links: list[str] = []
    for frame in page.frames:
        raw_links.extend(await extract_raw_links_from_frame(frame))

    result: set[str] = set()
    for raw in raw_links:
        if not raw:
            continue
        raw = raw.strip()
        if raw.startswith(("mailto:", "tel:", "sms:", "javascript:", "data:", "blob:")):
            continue

        normalized = normalize_url(urljoin(current_url, raw))
        if should_skip_url(normalized, base_netloc):
            continue
        result.add(normalized)

    return result


async def remove_boilerplate(page) -> None:
    selector_string = ", ".join(["script", "style", "noscript", "svg", *NAV_SELECTORS])
    try:
        await page.evaluate(
            """
            (sel) => document.querySelectorAll(sel).forEach((el) => el.remove())
            """,
            selector_string,
        )
    except Exception:
        pass


async def get_best_content_html(page) -> str:
    for selector in CONTENT_SELECTORS:
        try:
            el = await page.query_selector(selector)
            if not el:
                continue
            text = await el.inner_text(timeout=5000)
            if text and text.strip():
                return await el.inner_html(timeout=5000)
        except Exception:
            continue
    return await page.content()


async def save_debug_artifacts(page, debug_dir: Path, url: str, label: str) -> None:
    debug_dir.mkdir(parents=True, exist_ok=True)
    stem = safe_debug_name(url, f"_{label}")

    try:
        (debug_dir / f"{stem}.html").write_text(await page.content(), encoding="utf-8")
    except Exception:
        pass

    try:
        await page.screenshot(path=str(debug_dir / f"{stem}.png"), full_page=True)
    except Exception:
        pass


async def find_ticker_input(page):
    candidates = await page.locator("input:not([type='hidden']):not([disabled]), textarea:not([disabled])").all()
    fallback = None

    for candidate in candidates:
        try:
            if not await candidate.is_visible(timeout=1000):
                continue
            meta = await candidate.evaluate(
                """
                (el) => [
                  el.getAttribute('placeholder') || '',
                  el.getAttribute('aria-label') || '',
                  el.getAttribute('name') || '',
                  el.getAttribute('id') || '',
                  el.getAttribute('type') || '',
                ].join(' ')
                """
            )
            if fallback is None:
                fallback = candidate
            if INPUT_HINT_RE.search(meta):
                return candidate
        except Exception:
            continue

    return fallback


async def click_likely_submit(page) -> bool:
    try:
        button = page.get_by_role("button", name=BUTTON_RE).first
        if await button.is_visible(timeout=1500):
            await button.click(timeout=3000)
            return True
    except Exception:
        pass

    try:
        clicked = await page.evaluate(
            """
            (pattern) => {
              const re = new RegExp(pattern, 'i');
              const els = Array.from(document.querySelectorAll('button, [role="button"], input[type="submit"]'));
              const target = els.find((el) => re.test(el.innerText || el.value || el.getAttribute('aria-label') || ''));
              if (target) {
                target.click();
                return true;
              }
              return false;
            }
            """,
            BUTTON_RE.pattern,
        )
        return bool(clicked)
    except Exception:
        return False


async def interact_with_ticker_search(page, ticker: str, settle_ms: int, state: CrawlState) -> bool:
    """Fill a ticker/symbol input and trigger the scan. Returns True if an input was found."""
    ticker = ticker.strip().upper()
    if not ticker:
        return False

    input_el = await find_ticker_input(page)
    if input_el is None:
        state.interactions.append(f"No visible ticker/search input found for ticker {ticker}.")
        return False

    try:
        await input_el.click(timeout=3000)
        await input_el.fill(ticker, timeout=5000)
        await page.keyboard.press("Enter")
        clicked = await click_likely_submit(page)
        await wait_for_app_content(page, settle_ms=max(settle_ms, 2000))
        state.interactions.append(f"Submitted ticker {ticker}; clicked_button={clicked}.")
        return True
    except Exception as exc:
        state.interactions.append(f"Ticker interaction failed for {ticker}: {type(exc).__name__}: {exc}")
        return False


async def enqueue_url(url: str, queue: asyncio.Queue, state: CrawlState, lock: asyncio.Lock, max_pages: int) -> bool:
    async with lock:
        if url in state.visited:
            return False
        if len(state.visited) >= max_pages:
            return False
        state.visited.add(url)
        state.order[url] = len(state.order)
        await queue.put(url)
        return True


async def scrape_page(
    context,
    url: str,
    base_netloc: str,
    queue: asyncio.Queue,
    state: CrawlState,
    lock: asyncio.Lock,
    max_pages: int,
    settle_ms: int,
    timeout_ms: int,
    debug_dir: Path,
    ticker: str | None,
    min_markdown_chars: int,
) -> None:
    page = await context.new_page()
    await attach_diagnostics(page, state, url)
    page_order = state.order.get(url, 0) + 1
    print(f"[{page_order:>3}] Scraping: {url}")

    try:
        response_status = "unknown"
        try:
            response = await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            if response:
                response_status = str(response.status)
        except PlaywrightTimeout:
            print("      ! Navigation timeout; attempting DOM scrape anyway")

        await wait_for_app_content(page, settle_ms=settle_ms)

        if ticker and state.order.get(url, 0) == 0:
            await interact_with_ticker_search(page, ticker=ticker, settle_ms=settle_ms, state=state)

        # Discover links before removing nav/header/footer.
        new_links = await get_internal_links(page, url, base_netloc)
        for link in sorted(new_links):
            await enqueue_url(link, queue=queue, state=state, lock=lock, max_pages=max_pages)

        await remove_boilerplate(page)
        html = await get_best_content_html(page)
        markdown = clean_text(html)

        title = await page.title()
        path = urlparse(url).path or "/"
        label = f" ticker `{ticker.strip().upper()}`" if ticker and state.order.get(url, 0) == 0 else ""

        if len(markdown) >= min_markdown_chars:
            block = (
                f"## {title or path}{label}\n\n"
                f"URL: `{url}`\n\n"
                f"HTTP status: `{response_status}`\n\n"
                f"{markdown}\n\n"
                "---\n"
            )
            state.results.append((state.order.get(url, 0), block))
        else:
            await save_debug_artifacts(page, debug_dir, url, "empty_or_short")
            state.errors.append(f"Markdown too short on {url}: {len(markdown)} chars")

    except Exception as exc:
        message = f"Error on {url}: {type(exc).__name__}: {exc}"
        print(f"      ✗ {message}")
        state.errors.append(message)
        await save_debug_artifacts(page, debug_dir, url, "error")
    finally:
        await page.close()


async def worker(
    context,
    base_netloc: str,
    queue: asyncio.Queue,
    state: CrawlState,
    lock: asyncio.Lock,
    max_pages: int,
    settle_ms: int,
    timeout_ms: int,
    debug_dir: Path,
    ticker: str | None,
    min_markdown_chars: int,
) -> None:
    while True:
        url = await queue.get()
        try:
            await scrape_page(
                context=context,
                url=url,
                base_netloc=base_netloc,
                queue=queue,
                state=state,
                lock=lock,
                max_pages=max_pages,
                settle_ms=settle_ms,
                timeout_ms=timeout_ms,
                debug_dir=debug_dir,
                ticker=ticker,
                min_markdown_chars=min_markdown_chars,
            )
        finally:
            queue.task_done()


async def crawl(
    base_url: str,
    output_md: Path,
    max_pages: int,
    concurrency: int,
    settle_ms: int,
    timeout_ms: int,
    debug_dir: Path,
    headed: bool,
    ticker: str | None,
    min_markdown_chars: int,
) -> None:
    start = time.perf_counter()
    output_md.parent.mkdir(parents=True, exist_ok=True)
    debug_dir.mkdir(parents=True, exist_ok=True)

    seed = normalize_url(base_url)
    base_netloc = urlparse(seed).netloc

    state = CrawlState(visited={seed}, order={seed: 0})
    queue: asyncio.Queue = asyncio.Queue()
    lock = asyncio.Lock()
    await queue.put(seed)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=not headed)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (compatible; VybeDocBot/1.0; +https://vybe.build)",
            java_script_enabled=True,
            ignore_https_errors=True,
            viewport={"width": 1440, "height": 1200},
        )

        workers = [
            asyncio.create_task(
                worker(
                    context=context,
                    base_netloc=base_netloc,
                    queue=queue,
                    state=state,
                    lock=lock,
                    max_pages=max_pages,
                    settle_ms=settle_ms,
                    timeout_ms=timeout_ms,
                    debug_dir=debug_dir,
                    ticker=ticker,
                    min_markdown_chars=min_markdown_chars,
                )
            )
            for _ in range(max(1, concurrency))
        ]

        await queue.join()

        for task in workers:
            task.cancel()
        await asyncio.gather(*workers, return_exceptions=True)

        await context.close()
        await browser.close()

    state.results.sort(key=lambda item: item[0])
    elapsed = time.perf_counter() - start

    output = [
        "# Vybe App — Full Site Dump",
        "",
        f"Base URL: `{seed}`",
        f"Ticker submitted: `{ticker.strip().upper() if ticker else 'none'}`",
        f"Pages discovered: `{len(state.visited)}`",
        f"Pages captured: `{len(state.results)}`",
        f"Elapsed seconds: `{elapsed:.1f}`",
        "",
        "---",
        "",
    ]
    output.extend(block for _, block in state.results)

    if state.interactions:
        output.extend(["", "## Interaction Log", "", *[f"- {item}" for item in state.interactions], ""])
    if state.errors:
        output.extend(["", "## Crawl Errors", "", *[f"- {err}" for err in state.errors], ""])
    if state.console_errors:
        output.extend(["", "## Browser Console Warnings/Errors", "", *[f"- {err}" for err in state.console_errors[:100]], ""])
    if state.request_failures:
        output.extend(["", "## Request Failures", "", *[f"- {err}" for err in state.request_failures[:100]], ""])

    output_md.write_text("\n".join(output), encoding="utf-8")

    diagnostics = {
        "base_url": seed,
        "ticker": ticker.strip().upper() if ticker else None,
        "visited": sorted(state.visited, key=lambda u: state.order.get(u, 999999)),
        "pages_captured": len(state.results),
        "errors": state.errors,
        "console_errors": state.console_errors[:200],
        "request_failures": state.request_failures[:200],
        "interactions": state.interactions,
        "elapsed_seconds": round(elapsed, 2),
    }
    (debug_dir / "diagnostics.json").write_text(json.dumps(diagnostics, indent=2), encoding="utf-8")

    print()
    print(f"✓ Done. Discovered {len(state.visited)} page(s)")
    print(f"✓ Captured {len(state.results)} page(s)")
    print(f"✓ Elapsed: {elapsed:.1f}s")
    print(f"✓ Output: {output_md}")
    print(f"✓ Diagnostics: {debug_dir / 'diagnostics.json'}")
    if state.errors:
        print(f"! Errors/warnings: {len(state.errors)}")
        print(f"! Debug artifacts: {debug_dir}")


def parse_args():
    parser = argparse.ArgumentParser(description="Crawl a Vybe app and export hydrated SPA content to Markdown.")
    parser.add_argument("base_url", nargs="?", default=DEFAULT_BASE_URL, help="Vybe app URL to crawl.")
    parser.add_argument("-o", "--output", default=DEFAULT_OUTPUT_MD, help="Markdown output file.")
    parser.add_argument("--max-pages", type=int, default=DEFAULT_MAX_PAGES, help="Maximum pages/routes to crawl.")
    parser.add_argument("--concurrency", type=int, default=DEFAULT_CONCURRENCY, help="Concurrent browser pages.")
    parser.add_argument("--settle-ms", type=int, default=2000, help="Extra wait after app content appears.")
    parser.add_argument("--timeout-ms", type=int, default=30000, help="Navigation timeout.")
    parser.add_argument("--debug-dir", default=DEFAULT_DEBUG_DIR, help="Directory for debug screenshots/HTML/JSON.")
    parser.add_argument("--headed", action="store_true", help="Run browser visibly for debugging.")
    parser.add_argument("--ticker", default="BE", help="Ticker to submit into the app before scraping the landing page. Use empty string to disable.")
    parser.add_argument("--min-markdown-chars", type=int, default=30, help="Save debug artifacts if captured markdown is shorter than this.")
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    ticker = args.ticker.strip() or None
    await crawl(
        base_url=args.base_url,
        output_md=Path(args.output),
        max_pages=args.max_pages,
        concurrency=args.concurrency,
        settle_ms=args.settle_ms,
        timeout_ms=args.timeout_ms,
        debug_dir=Path(args.debug_dir),
        headed=args.headed,
        ticker=ticker,
        min_markdown_chars=args.min_markdown_chars,
    )


if __name__ == "__main__":
    asyncio.run(main())
