"""Polite same-site crawler capturing raw HTML (httpx) and JS-rendered DOM (Playwright). FR-2, FR-3."""

import logging
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urldefrag, urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from app.config import settings
from app.crawler.http import fetch, is_html
from app.crawler.site_files import (
    collect_sitemap_urls,
    fetch_site_files,
    parse_robots,
    sitemaps_from_robots,
)

log = logging.getLogger(__name__)

_SKIP_EXTENSIONS = (
    ".pdf", ".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".ico", ".css", ".js", ".xml", ".json",
    ".zip", ".gz", ".tgz", ".bz2", ".xz", ".7z", ".rar", ".tar", ".exe", ".msi", ".dmg", ".pkg", ".deb", ".rpm",
    ".whl", ".apk", ".iso", ".mp4", ".mp3", ".mov", ".avi", ".webm", ".wav",
)


@dataclass
class CrawledPage:
    url: str
    status_code: int | None
    raw_html_path: Path | None = None
    rendered_html_path: Path | None = None
    metrics: dict = field(default_factory=dict)


@dataclass
class CrawlResult:
    site_files: dict
    pages: list[CrawledPage]
    sitemap_urls: list[str] = field(default_factory=list)


def normalize_url(url: str) -> str:
    url, _ = urldefrag(url)
    parsed = urlparse(url)
    path = parsed.path or "/"
    return parsed._replace(path=path, netloc=parsed.netloc.lower()).geturl()


def same_site(url: str, base: str) -> bool:
    strip = lambda host: host.lower().removeprefix("www.")  # noqa: E731
    return strip(urlparse(url).netloc) == strip(urlparse(base).netloc)


def visible_text(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript", "template"]):
        tag.decompose()
    return " ".join(soup.get_text(" ").split())


def extract_links(html: str, page_url: str) -> list[str]:
    soup = BeautifulSoup(html, "lxml")
    links = []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if href.startswith(("mailto:", "tel:", "javascript:", "#")):
            continue
        links.append(normalize_url(urljoin(page_url, href)))
    return links


def page_metrics(raw_html: str | None, rendered_html: str | None) -> dict:
    raw_text = visible_text(raw_html) if raw_html else ""
    rendered_text = visible_text(rendered_html) if rendered_html else ""
    metrics = {"raw_text_chars": len(raw_text), "rendered_text_chars": len(rendered_text)}
    if rendered_html is not None:
        # Share of meaningful text an agent gets without running JS (input to FR-13).
        metrics["no_js_text_ratio"] = round(min(1.0, len(raw_text) / len(rendered_text)), 3) if rendered_text else None
    soup = BeautifulSoup(rendered_html or raw_html or "", "lxml")
    metrics["title"] = soup.title.get_text(strip=True) if soup.title else None
    return metrics


class _Renderer:
    """One headless Chromium shared across all pages of a crawl."""

    def __init__(self) -> None:
        from playwright.sync_api import sync_playwright

        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch()
        self._context = self._browser.new_context(user_agent=settings.user_agent,
                                                  viewport={"width": 1280, "height": 900})

    def render(self, url: str, screenshot: Path | None = None) -> str | None:
        page = self._context.new_page()
        try:
            page.goto(url, wait_until="load", timeout=settings.request_timeout_s * 1000)
            # Give client-side rendering a moment, but don't wait on analytics/long-poll connections.
            try:
                page.wait_for_load_state("networkidle", timeout=3000)
            except Exception:  # noqa: BLE001
                pass
            if screenshot is not None:
                page.screenshot(path=str(screenshot), type="jpeg", quality=60)
            return page.content()
        except Exception as exc:  # noqa: BLE001  rendering failures are findings, not crashes
            log.warning("render failed for %s: %s", url, exc)
            return None
        finally:
            page.close()

    def close(self) -> None:
        self._browser.close()
        self._pw.stop()


def crawl(start_url: str, out_dir: Path, max_pages: int | None = None, render_js: bool | None = None) -> CrawlResult:
    max_pages = max_pages or settings.max_pages
    render_js = settings.render_js if render_js is None else render_js
    out_dir.mkdir(parents=True, exist_ok=True)
    start_url = normalize_url(start_url)
    base = f"{urlparse(start_url).scheme}://{urlparse(start_url).netloc}/"

    with httpx.Client(
        headers={"User-Agent": settings.user_agent},
        timeout=settings.request_timeout_s,
        follow_redirects=True,
    ) as client:
        site_files = fetch_site_files(client, base)
        robots_txt = site_files["/robots.txt"].get("body")
        robots = parse_robots(robots_txt, urljoin(base, "/robots.txt"))

        sitemap_urls = sitemaps_from_robots(robots_txt) or [urljoin(base, "/sitemap.xml")]
        sitemap_pages = collect_sitemap_urls(client, sitemap_urls, 500)
        seeds = [start_url] + sitemap_pages[:max_pages]

        renderer = _Renderer() if render_js else None
        try:
            pages = _crawl_pages(client, renderer, robots, seeds, base, out_dir, max_pages)
        finally:
            if renderer:
                renderer.close()

    return CrawlResult(site_files=site_files, pages=pages, sitemap_urls=sitemap_pages)


def _crawl_pages(client, renderer, robots, seeds, base, out_dir, max_pages) -> list[CrawledPage]:
    queue = deque(normalize_url(u) for u in seeds)
    seen: set[str] = set()
    pages: list[CrawledPage] = []

    while queue and len(pages) < max_pages:
        url = queue.popleft()
        if url in seen or not same_site(url, base) or url.lower().endswith(_SKIP_EXTENSIONS):
            continue
        seen.add(url)
        if not robots.can_fetch(settings.user_agent, url):
            pages.append(CrawledPage(url=url, status_code=None, metrics={"blocked_by_robots": True}))
            continue

        try:
            resp = fetch(client, url, accept=is_html)
        except httpx.HTTPError as exc:
            pages.append(CrawledPage(url=url, status_code=None, metrics={"error": str(exc)}))
            continue

        if resp.text is None:
            # Not HTML (downloads, images, feeds) or over the size cap: record errors, otherwise skip.
            if resp.status_code >= 400:
                pages.append(CrawledPage(url=url, status_code=resp.status_code))
            continue

        n = len(pages)
        raw_html = resp.text
        raw_path = out_dir / f"{n:03d}.raw.html"
        raw_path.write_text(raw_html, encoding="utf-8")

        # The homepage's first screen doubles as the audit's thumbnail.
        shot = out_dir / "home.jpg" if n == 0 else None
        rendered_html = renderer.render(url, shot) if renderer else None
        rendered_path = None
        if rendered_html is not None:
            rendered_path = out_dir / f"{n:03d}.rendered.html"
            rendered_path.write_text(rendered_html, encoding="utf-8")

        metrics = page_metrics(raw_html, rendered_html)
        metrics["final_url"] = str(resp.url)
        metrics["x_robots_tag"] = resp.headers.get("x-robots-tag")
        metrics["server"] = resp.headers.get("server")
        if shot is not None and shot.exists():
            metrics["screenshot"] = str(shot)
        pages.append(CrawledPage(url, resp.status_code, raw_path, rendered_path, metrics))

        for link in extract_links(rendered_html or raw_html, str(resp.url)):
            if link not in seen:
                queue.append(link)
        time.sleep(settings.crawl_delay_s)

    return pages
