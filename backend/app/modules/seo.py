"""Classic SEO module (FR-5..FR-7): on-page checks, PageSpeed / Core Web Vitals, indexability."""

import logging
import re
from urllib.parse import urljoin

import httpx

from app.config import settings
from app.crawler.crawl import normalize_url, same_site
from app.crawler.http import fetch
from app.modules.base import AuditContext, Check, ModuleResult, PageData, pct, ratio_status

log = logging.getLogger(__name__)

PAGESPEED_URL = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"


def run(ctx: AuditContext, client: httpx.Client | None = None) -> ModuleResult:
    pages = [p for p in ctx.html_pages if (p.status_code or 0) < 400]
    checks = [
        _titles(pages),
        _meta_descriptions(pages),
        _h1(pages),
        _heading_hierarchy(pages),
        _canonical(pages),
        _alt_text(pages),
        _internal_links(pages, ctx.base_url),
        _broken_links(ctx, client),
        _hreflang(pages),
        _viewport(pages),
        _noindex(pages),
        _robots_txt(ctx),
        _sitemap(ctx),
        _pagespeed(ctx, client),
    ]
    return ModuleResult("seo", checks)


def _per_page(pages: list[PageData], ok, check_id: str, title: str, weight: float, fix_hint: str,
              severity="warning", pass_at=0.9, partial_at=0.5) -> Check:
    if not pages:
        return Check(check_id, title, "na", weight, detail="No HTML pages crawled.")
    failing = [p.url for p in pages if not ok(p)]
    ratio = 1 - pct(len(failing), len(pages))
    return Check(
        check_id, title, ratio_status(ratio, pass_at, partial_at), weight, severity,
        detail=f"{len(pages) - len(failing)}/{len(pages)} pages OK.",
        evidence={"failing_pages": failing[:10]},
        fix_hint=fix_hint,
    )


def _text(tag) -> str:
    return tag.get_text(" ", strip=True) if tag else ""


def _meta(p: PageData, name: str) -> str | None:
    tag = p.soup.find("meta", attrs={"name": re.compile(f"^{name}$", re.I)})
    return tag.get("content", "").strip() if tag else None


def _titles(pages):
    def ok(p):
        return 10 <= len(_text(p.soup.title)) <= 65

    check = _per_page(pages, ok, "seo.title", "Page titles present and 10-65 characters", 3,
                      "Give every page a unique, descriptive <title> of 10-65 characters.", "critical")
    titles = [_text(p.soup.title) for p in pages if _text(p.soup.title)]
    dupes = len(titles) - len(set(titles))
    if dupes and check.status == "pass":
        check.status = "partial"
    if dupes:
        check.detail += f" {dupes} page(s) share a title with another page."
    check.evidence["duplicate_titles"] = dupes
    return check


def _meta_descriptions(pages):
    return _per_page(pages, lambda p: 50 <= len(_meta(p, "description") or "") <= 170,
                     "seo.meta_description", "Meta descriptions present and 50-170 characters", 2,
                     "Add a <meta name=\"description\"> summarising each page in 50-170 characters.")


def _h1(pages):
    return _per_page(pages, lambda p: len(p.soup.find_all("h1")) == 1, "seo.h1", "Exactly one H1 per page", 2,
                     "Use a single <h1> stating the page's main topic.")


def _heading_hierarchy(pages):
    def ok(p):
        levels = [int(h.name[1]) for h in p.soup.find_all(re.compile("^h[1-6]$"))]
        return all(b - a <= 1 for a, b in zip(levels, levels[1:]))

    return _per_page(pages, ok, "seo.heading_hierarchy", "Heading levels are not skipped", 1,
                     "Nest headings in order (h1 > h2 > h3) without skipping levels.", "info")


def _canonical(pages):
    return _per_page(pages, lambda p: p.soup.find("link", rel="canonical", href=True) is not None,
                     "seo.canonical", "Canonical URL declared", 2,
                     "Add <link rel=\"canonical\" href=\"...\"> to every indexable page.")


def _alt_text(pages):
    imgs = [img for p in pages for img in p.soup.find_all("img")]
    if not imgs:
        return Check("seo.alt_text", "Images have alt text", "na", 2, detail="No images found.")
    missing = [img.get("src", "")[:200] for img in imgs if img.get("alt") is None]
    ratio = 1 - pct(len(missing), len(imgs))
    return Check("seo.alt_text", "Images have alt text", ratio_status(ratio, 0.95, 0.7), 2,
                 detail=f"{len(imgs) - len(missing)}/{len(imgs)} images have an alt attribute.",
                 evidence={"missing_alt_src": missing[:15]},
                 fix_hint="Add alt text describing each meaningful image (alt=\"\" for decorative ones).")


def _internal_links(pages, base_url):
    def ok(p):
        links = [urljoin(p.url, a["href"]) for a in p.soup.find_all("a", href=True)]
        return sum(same_site(u, base_url) for u in links) >= 3

    return _per_page(pages, ok, "seo.internal_links", "Pages link to at least 3 internal pages", 1,
                     "Add contextual internal links so crawlers and agents can reach related pages.", "info")


def _broken_links(ctx: AuditContext, client):
    crawled_errors = {p.url: p.status_code for p in ctx.pages if p.status_code and p.status_code >= 400}
    crawled = {p.url for p in ctx.pages}
    candidates: list[str] = []
    for p in ctx.html_pages:
        for a in p.soup.find_all("a", href=True):
            href = a["href"].strip()
            if href.startswith(("mailto:", "tel:", "javascript:", "#")):
                continue
            url = normalize_url(urljoin(p.url, href))
            if same_site(url, ctx.base_url) and url not in crawled and url not in candidates:
                candidates.append(url)

    checked = 0
    broken = dict(crawled_errors)
    if client is not None:
        for url in candidates[: settings.link_check_limit]:
            try:
                resp = client.head(url)
                if resp.status_code in (405, 501):
                    resp = fetch(client, url, accept=lambda _: False)  # status only, no body
                checked += 1
                if resp.status_code >= 400:
                    broken[url] = resp.status_code
            except httpx.HTTPError:
                broken[url] = None
                checked += 1

    total = len(crawled) + checked
    if not total:
        return Check("seo.broken_links", "No broken internal links", "na", 3)
    status = "pass" if not broken else ("partial" if pct(len(broken), total) < 0.05 else "fail")
    return Check("seo.broken_links", "No broken internal links", status, 3, "critical",
                 detail=f"{len(broken)} broken of {total} internal URLs checked.",
                 evidence={"broken": dict(list(broken.items())[:20])},
                 fix_hint="Fix or redirect internal links that return 4xx/5xx.")


def _hreflang(pages):
    tags = [t for p in pages for t in p.soup.find_all("link", rel="alternate", hreflang=True)]
    if not tags:
        return Check("seo.hreflang", "hreflang annotations valid", "na", 1, "info",
                     detail="No hreflang tags (fine for single-language sites).")
    pattern = re.compile(r"^(x-default|[a-z]{2,3}(-[A-Za-z]{2,4})?)$")
    bad = [t["hreflang"] for t in tags if not pattern.match(t["hreflang"])]
    return Check("seo.hreflang", "hreflang annotations valid", "pass" if not bad else "partial", 1, "info",
                 detail=f"{len(tags)} hreflang tags, {len(bad)} with invalid codes.", evidence={"invalid": bad[:10]},
                 fix_hint="Use ISO 639-1 language (and optional ISO 3166 region) codes in hreflang.")


def _viewport(pages):
    return _per_page(pages, lambda p: p.soup.find("meta", attrs={"name": "viewport"}) is not None,
                     "seo.viewport", "Mobile viewport meta tag", 2,
                     "Add <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">.", "critical")


def _noindex(pages):
    def indexable(p):
        robots_meta = (_meta(p, "robots") or "").lower()
        header = (p.metrics.get("x_robots_tag") or "").lower()
        return "noindex" not in robots_meta and "noindex" not in header

    check = _per_page(pages, indexable, "seo.indexable", "Pages are indexable (no noindex)", 3,
                      "Remove noindex from pages that should appear in search and AI answers.", "critical",
                      pass_at=0.95, partial_at=0.7)
    home = pages[0] if pages else None
    if home and not indexable(home):
        check.status = "fail"
        check.detail += " Homepage is noindex."
    return check


def _robots_txt(ctx: AuditContext):
    f = ctx.site_files.get("/robots.txt") or {}
    if f.get("found"):
        return Check("seo.robots_txt", "robots.txt present", "pass", 1, "info")
    return Check("seo.robots_txt", "robots.txt present", "fail", 1, "warning",
                 detail=f"robots.txt returned {f.get('status')}.",
                 fix_hint="Publish /robots.txt with crawl rules and a Sitemap: line.")


def _sitemap(ctx: AuditContext):
    if not ctx.sitemap_urls:
        return Check("seo.sitemap", "XML sitemap covers crawled pages", "fail", 2,
                     detail="No sitemap found via robots.txt or /sitemap.xml.",
                     fix_hint="Publish an XML sitemap and reference it from robots.txt.")
    in_sitemap = {normalize_url(u).rstrip("/") for u in ctx.sitemap_urls}
    pages = [p for p in ctx.html_pages if (p.status_code or 0) < 400]
    missing = [p.url for p in pages if normalize_url(p.url).rstrip("/") not in in_sitemap]
    ratio = 1 - pct(len(missing), len(pages))
    return Check("seo.sitemap", "XML sitemap covers crawled pages", ratio_status(ratio, 0.8, 0.4), 2,
                 detail=f"{len(ctx.sitemap_urls)} URLs in sitemap; {len(pages) - len(missing)}/{len(pages)} crawled pages listed.",
                 evidence={"not_in_sitemap": missing[:10]},
                 fix_hint="Add every indexable page to the XML sitemap.")


def _pagespeed(ctx: AuditContext, client):
    title = "Mobile performance (PageSpeed / Core Web Vitals)"
    if client is None or not settings.pagespeed_enabled or not ctx.home:
        return Check("seo.pagespeed", title, "na", 4, detail="PageSpeed check skipped.")
    params = {"url": ctx.home.url, "strategy": "mobile", "category": "performance"}
    if settings.pagespeed_api_key:
        params["key"] = settings.pagespeed_api_key
    try:
        resp = client.get(PAGESPEED_URL, params=params, timeout=120)
    except httpx.HTTPError as exc:
        return Check("seo.pagespeed", title, "na", 4, detail=f"PageSpeed request failed: {exc}")
    if resp.status_code != 200:
        # Keyless quota is shared and often exhausted (429); report as unknown rather than failing the site.
        return Check("seo.pagespeed", title, "na", 4,
                     detail=f"PageSpeed API returned {resp.status_code}; add AGENTRANK_PAGESPEED_API_KEY for a reliable quota.")

    data = resp.json()
    lh = data.get("lighthouseResult", {})
    perf = (lh.get("categories", {}).get("performance", {}) or {}).get("score")
    audits = lh.get("audits", {})
    field = data.get("loadingExperience", {}).get("metrics", {})
    evidence = {
        "performance_score": perf,
        "lab": {k: audits.get(k, {}).get("displayValue") for k in
                ("largest-contentful-paint", "cumulative-layout-shift", "total-blocking-time", "first-contentful-paint")},
        # Real-user Core Web Vitals (CrUX) when Google has enough traffic data for the URL.
        "field": {k: v.get("percentile") for k, v in field.items()
                  if k in ("LARGEST_CONTENTFUL_PAINT_MS", "INTERACTION_TO_NEXT_PAINT", "CUMULATIVE_LAYOUT_SHIFT_SCORE")},
        "field_overall": data.get("loadingExperience", {}).get("overall_category"),
    }
    if perf is None:
        return Check("seo.pagespeed", title, "na", 4, detail="No performance score returned.", evidence=evidence)
    return Check("seo.pagespeed", title, ratio_status(perf, 0.9, 0.5), 4, "critical" if perf < 0.5 else "warning",
                 detail=f"Lighthouse mobile performance {round(perf * 100)}/100.", evidence=evidence,
                 fix_hint="Reduce LCP (optimise hero image, server response) and blocking JavaScript.")
