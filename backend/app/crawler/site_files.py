"""Site-level files agents and crawlers read (FR-4): robots.txt, sitemaps, llms.txt, manifests."""

from urllib.parse import urljoin
from urllib.robotparser import RobotFileParser
from xml.etree import ElementTree

import httpx

from app.crawler.http import fetch, is_texty

SITE_FILES = [
    "/robots.txt",
    "/sitemap.xml",
    "/llms.txt",
    "/llms-full.txt",
    "/.well-known/ai-plugin.json",
    "/.well-known/mcp.json",
    "/.well-known/security.txt",
    "/openapi.json",
    "/openapi.yaml",
]

_MAX_STORED_CHARS = 200_000
_SITEMAP_NS = "{http://www.sitemaps.org/schemas/sitemap/0.9}"


def fetch_site_files(client: httpx.Client, base_url: str) -> dict[str, dict]:
    """Fetch each well-known file; record status, content type and body when present."""
    results: dict[str, dict] = {}
    for path in SITE_FILES:
        url = urljoin(base_url, path)
        try:
            resp = fetch(client, url, accept=is_texty, max_bytes=2_000_000)
        except httpx.HTTPError as exc:
            results[path] = {"url": url, "found": False, "error": str(exc)}
            continue
        # Many sites serve their HTML 404 page with status 200; treat HTML for non-HTML files as missing.
        found = resp.status_code == 200 and resp.text is not None and "text/html" not in resp.content_type
        results[path] = {
            "url": resp.url,
            "found": found,
            "status": resp.status_code,
            "content_type": resp.content_type,
            "body": resp.text[:_MAX_STORED_CHARS] if found else None,
        }
    return results


def parse_robots(robots_txt: str | None, robots_url: str) -> RobotFileParser:
    parser = RobotFileParser(robots_url)
    parser.parse((robots_txt or "").splitlines())
    return parser


def sitemaps_from_robots(robots_txt: str | None) -> list[str]:
    urls = []
    for line in (robots_txt or "").splitlines():
        key, _, value = line.partition(":")
        if key.strip().lower() == "sitemap" and value.strip():
            urls.append(value.strip())
    return urls


def parse_sitemap(xml_text: str) -> tuple[list[str], list[str]]:
    """Return (page urls, nested sitemap urls) from a urlset or sitemapindex document."""
    try:
        root = ElementTree.fromstring(xml_text.encode())
    except ElementTree.ParseError:
        return [], []
    locs = [el.text.strip() for el in root.iter(f"{_SITEMAP_NS}loc") if el.text]
    if root.tag == f"{_SITEMAP_NS}sitemapindex":
        return [], locs
    return locs, []


def collect_sitemap_urls(client: httpx.Client, sitemap_urls: list[str], limit: int) -> list[str]:
    """Walk sitemaps (following sitemap indexes) until `limit` page urls are found."""
    pages: list[str] = []
    queue = list(sitemap_urls)
    seen: set[str] = set()
    while queue and len(pages) < limit and len(seen) < 20:
        sm_url = queue.pop(0)
        if sm_url in seen:
            continue
        seen.add(sm_url)
        try:
            resp = fetch(client, sm_url, accept=is_texty, max_bytes=20_000_000)
        except httpx.HTTPError:
            continue
        if resp.status_code != 200 or resp.text is None:
            continue
        found_pages, nested = parse_sitemap(resp.text)
        pages.extend(found_pages)
        queue.extend(nested)
    return pages[:limit]
