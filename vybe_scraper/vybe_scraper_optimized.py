#!/usr/bin/env python3
"""
Vybe App Scraper - Optimized Version
Uses requests + BeautifulSoup for efficiency.
Since this is a Next.js app, we extract content from the streamed React data.
"""

import argparse
import json
import re
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse, urlunparse
from markdownify import markdownify as md

try:
    import requests
    from bs4 import BeautifulSoup
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False
    print("Error: requests not installed. Run: pip install requests beautifulsoup4")

DEFAULT_BASE_URL = "https://sec-scanner-abd-inc22.vybe.build/"
DEFAULT_OUTPUT_MD = "vybe_app_full.md"
DEFAULT_MAX_PAGES = 50

CONTENT_SELECTORS = [
    "main",
    "[role='main']",
    "#root",
    "#__next",
    "[data-vybe-root]",
    ".content",
    ".main-content",
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


def is_route_fragment(fragment: str) -> bool:
    """Keep SPA route fragments like #/dashboard, drop simple anchor fragments."""
    return fragment.startswith("/") or fragment.startswith("!/")


def normalize_url(url: str) -> str:
    """Normalize URLs for deduplication."""
    p = urlparse(url)
    fragment = p.fragment if is_route_fragment(p.fragment) else ""
    path = p.path.rstrip("/") or "/"
    return urlunparse((p.scheme.lower(), p.netloc.lower(), path, p.params, p.query, fragment))


def should_skip_url(url: str, base_netloc: str) -> bool:
    """Check if URL should be skipped."""
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
    if any(part in path_lower for part in ["/logout", "/signout"]):
        return True
    return False


def clean_text(html: str) -> str:
    """Convert HTML to compact markdown."""
    text = md(
        html,
        heading_style="ATX",
        code_language_detection=True,
        strip=["script", "style", "noscript"],
    )
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    return text.strip()


def remove_boilerplate(soup: BeautifulSoup) -> None:
    """Remove navigation and boilerplate elements."""
    selectors = NAV_SELECTORS + ["script", "style", "noscript", "svg"]
    for selector in selectors:
        for el in soup.select(selector):
            el.decompose()


def get_best_content_html(soup: BeautifulSoup) -> str:
    """Get the best content from the page."""
    for selector in CONTENT_SELECTORS:
        try:
            el = soup.select_one(selector)
            if el:
                text = el.get_text(strip=True)
                if text:
                    return str(el)
        except Exception:
            continue
    return str(soup)


def extract_links_from_soup(soup: BeautifulSoup, current_url: str, base_netloc: str) -> set:
    """Extract internal links from BeautifulSoup object."""
    result = set()
    
    # Extract from <a> tags
    for link in soup.find_all("a", href=True):
        raw = link["href"].strip()
        if raw.startswith(("mailto:", "tel:", "sms:", "javascript:", "data:", "blob:")):
            continue
        
        absolute = urljoin(current_url, raw)
        normalized = normalize_url(absolute)
        
        if not should_skip_url(normalized, base_netloc):
            result.add(normalized)
    
    # Extract from common SPA attributes
    spa_attrs = ["to", "data-href", "data-url", "data-path", "data-route"]
    for el in soup.find_all(True):
        for attr in spa_attrs:
            value = el.get(attr)
            if value:
                value = value.strip()
                absolute = urljoin(current_url, value)
                normalized = normalize_url(absolute)
                if not should_skip_url(normalized, base_netloc):
                    result.add(normalized)
    
    return result


def extract_nextjs_content(html: str) -> tuple[str, list[str]]:
    """
    Extract content from Next.js React Server Components streaming format.
    Returns (text_content, links_found)
    """
    content_parts = []
    links = set()
    
    # Find all the self.__next_f.push calls which contain the streamed data
    next_f_pattern = r'self\.__next_f\.push\(\[1,"([^"]+)"\]\)'
    matches = re.findall(next_f_pattern, html)
    
    for match in matches:
        try:
            # Decode escaped characters  
            decoded = bytes(match, "utf-8").decode("unicode_escape")
            
            # Extract readable text - look for human-readable strings
            # Match quoted strings that look like actual content
            text_matches = re.findall(r'"([^"\\]{3,200}(?:\\.[^"\\]{0,200})*)"', decoded)
            for text in text_matches:
                # Clean up escaped characters
                text = text.replace('\\"', '"').replace('\\n', ' ').replace('\\t', ' ')
                text = re.sub(r'\s+', ' ', text).strip()
                
                # Skip technical/internal strings
                if not text or len(text) < 2:
                    continue
                if any(skip in text.lower() for skip in ['static/', '.js', '.css', 'chunks/', '$sreact', '$l', 'webpack']):
                    continue
                if text.startswith('$') or text.startswith('I['):
                    continue
                # Skip URLs and paths
                if text.startswith('/') or text.startswith('http'):
                    continue
                    
                content_parts.append(text)
            
            # Extract URLs from href/src attributes
            url_patterns = [
                r'href["\s:=]+["\\]?\s*([^"\\\'\\s>]+)',
                r'src["\s:=]+["\\]?\s*([^"\\\'\\s>]+)',
                r'"(https?://[^"\\s]+)"',
            ]
            for pattern in url_patterns:
                for url_match in re.finditer(pattern, decoded):
                    url = url_match.group(1).rstrip('"\'')
                    if url and not url.startswith(('/_next/', 'data:', 'javascript:', 'blob:')):
                        links.add(url)
                    
        except Exception as e:
            continue
    
    # Also extract from regular HTML for additional content
    soup = BeautifulSoup(html, 'html.parser')
    
    # Get title
    title_tag = soup.find('title')
    if title_tag and title_tag.get_text(strip=True):
        content_parts.insert(0, title_tag.get_text(strip=True))
    
    # Get meta description
    desc_tag = soup.find('meta', attrs={'name': 'description'})
    if desc_tag and desc_tag.get('content'):
        content_parts.insert(1, desc_tag['content'])
    
    # Get og:title and og:description
    for prop in ['og:title', 'og:description']:
        tag = soup.find('meta', attrs={'property': prop})
        if tag and tag.get('content'):
            content_parts.append(tag['content'])
    
    # Extract links from anchor tags
    for link in soup.find_all('a', href=True):
        href = link['href']
        if href and not href.startswith(('/_next/', 'data:', 'javascript:', 'mailto:', 'tel:', '#')):
            links.add(href)
        
        # Get link text
        link_text = link.get_text(strip=True)
        if link_text and len(link_text) > 1:
            content_parts.append(link_text)
    
    # Remove duplicates while preserving order
    seen = set()
    unique_content = []
    for item in content_parts:
        item_lower = item.lower()
        if item_lower not in seen and len(item) > 1:
            seen.add(item_lower)
            unique_content.append(item)
    
    return '\n'.join(unique_content), list(links)


def scrape_page(url: str, session: requests.Session) -> tuple:
    """Scrape a page and extract content."""
    if not REQUESTS_AVAILABLE:
        print("      ! requests not available")
        return None, None, None
    
    try:
        response = session.get(url, timeout=15, allow_redirects=True)
        response.raise_for_status()
        html = response.text
        
        # Extract content and links from Next.js format
        text_content, raw_links = extract_nextjs_content(html)
        
        return html, text_content, raw_links
    except Exception as e:
        print(f"      ✗ Request failed: {type(e).__name__}: {e}")
        return None, None, None


def crawl(base_url: str, output_md: Path, max_pages: int) -> None:
    """Main crawl function."""
    if not REQUESTS_AVAILABLE:
        print("Error: requests is not available. Please install: pip install requests beautifulsoup4")
        return
    
    start = time.perf_counter()
    seed = normalize_url(base_url)
    base_netloc = urlparse(seed).netloc
    
    visited = {seed}
    order = {seed: 0}
    queue = [seed]
    results = []
    errors = []
    
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (compatible; VybeDocBot/1.0; +https://vybe.build)",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    })
    
    pages_processed = 0
    
    while queue and len(visited) <= max_pages:
        url = queue.pop(0)
        page_order = order.get(url, 0) + 1
        print(f"[{page_order:>3}] Scraping: {url}")
        
        html, text_content, raw_links = scrape_page(url, session)
        
        if html is None:
            errors.append(f"Failed to fetch {url}")
            continue
        
        # Process discovered links
        for raw in raw_links:
            if not raw or raw.startswith('#'):
                continue
            absolute = urljoin(url, raw)
            normalized = normalize_url(absolute)
            if not should_skip_url(normalized, base_netloc):
                if normalized not in visited and len(visited) < max_pages:
                    visited.add(normalized)
                    order[normalized] = len(order)
                    queue.append(normalized)
        
        # Create markdown from extracted content
        markdown = clean_text(f"<div>{text_content}</div>") if text_content else ""
        
        # Get title from the first line of content or URL path
        title = text_content.split('\n')[0].strip() if text_content else urlparse(url).path or "/"
        if len(title) > 100:
            title = title[:100] + "..."
        
        if markdown:
            block = f"## {title}\nURL: `{url}`\n{markdown}\n\n---\n"
            results.append((order.get(url, 0), block))
        
        pages_processed += 1
        print(f"      ✓ Captured {len(markdown)} chars")
    
    # Sort results by order
    results.sort(key=lambda item: item[0])
    
    # Build output
    output = [
        "# Vybe App — Full Site Dump",
        "",
        f"Base URL: `{seed}`",
        f"Pages discovered: `{len(visited)}`",
        f"Pages captured: `{len(results)}`",
        "",
        "---",
        "",
    ]
    output.extend(block for _, block in results)
    
    if errors:
        output.extend(["", "## Crawl Errors", "", *[f"- {err}" for err in errors], ""])
    
    output_md.write_text("\n".join(output), encoding="utf-8")
    
    elapsed = time.perf_counter() - start
    print(f"\n✓ Done. Processed {pages_processed} page(s), discovered {len(visited)} total in {elapsed:.1f}s → {output_md}")


def parse_args():
    parser = argparse.ArgumentParser(description="Crawl a Vybe app and export content to Markdown.")
    parser.add_argument(
        "base_url",
        nargs="?",
        default=DEFAULT_BASE_URL,
        help="Vybe app URL to crawl.",
    )
    parser.add_argument(
        "-o", "--output",
        default=DEFAULT_OUTPUT_MD,
        help="Markdown output file.",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=DEFAULT_MAX_PAGES,
        help="Maximum pages/routes to crawl.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    crawl(
        base_url=args.base_url,
        output_md=Path(args.output),
        max_pages=args.max_pages,
    )


if __name__ == "__main__":
    # Requirements: pip install requests beautifulsoup4 markdownify
    main()
