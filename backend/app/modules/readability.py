"""Agent Readability module (FR-10..FR-16): can AI crawlers and agents read and understand the site?"""

import re

from app.crawler.site_files import parse_robots
from app.modules.base import AuditContext, Check, ModuleResult, PageData, pct, ratio_status, schema_types

# AI crawlers/agents (FR-10). Training crawlers and live-answer fetchers are reported separately in evidence.
AI_BOTS = {
    "GPTBot": "OpenAI training",
    "OAI-SearchBot": "ChatGPT search",
    "ChatGPT-User": "ChatGPT browsing",
    "ClaudeBot": "Anthropic training",
    "Claude-SearchBot": "Claude search",
    "Claude-User": "Claude browsing",
    "PerplexityBot": "Perplexity search",
    "Google-Extended": "Gemini training",
    "CCBot": "Common Crawl",
}
# Bots that put a site into live AI answers; blocking these hurts visibility most.
ANSWER_BOTS = {"OAI-SearchBot", "ChatGPT-User", "Claude-SearchBot", "Claude-User", "PerplexityBot"}

# Schema types that carry facts agents look for, grouped by what they describe.
CORE_TYPES = {"Organization", "LocalBusiness", "WebSite", "Corporation", "Person"}
RICH_TYPES = {
    "Product", "Offer", "AggregateOffer", "LocalBusiness", "Restaurant", "Store", "FAQPage", "Event", "Service",
    "SoftwareApplication", "Article", "BlogPosting", "NewsArticle", "HowTo", "Recipe", "Course", "JobPosting",
    "MedicalBusiness", "Dentist", "Hotel", "BreadcrumbList", "TechArticle",
}

_PRICE_RE = re.compile(r"(?:[$€£₹¥]\s?\d[\d,]*(?:\.\d{2})?|\d[\d,]*(?:\.\d{2})?\s?(?:USD|EUR|GBP|INR|Rs\.?))")
_HOURS_RE = re.compile(r"\b(?:mon|tue|wed|thu|fri|sat|sun)[a-z]*\b.{0,40}\d{1,2}(?::\d{2})?\s?(?:am|pm)?", re.I)


def run(ctx: AuditContext) -> ModuleResult:
    pages = [p for p in ctx.html_pages if (p.status_code or 0) < 400]
    checks = [
        _ai_bot_access(ctx),
        _llms_txt(ctx),
        _structured_data(pages),
        _no_js_content(pages),
        _semantic_html(pages),
        _accessible_names(pages),
        _content_density(pages),
        _key_facts(pages),
    ]
    return ModuleResult("readability", checks)


def _ai_bot_access(ctx: AuditContext) -> Check:
    robots_txt = ctx.file_body("/robots.txt")
    robots = parse_robots(robots_txt, ctx.base_url + "robots.txt")
    home = ctx.base_url
    access = {bot: robots.can_fetch(bot, home) for bot in AI_BOTS}
    blocked = [b for b, ok in access.items() if not ok]
    blocked_answer = [b for b in blocked if b in ANSWER_BOTS]
    if not blocked:
        status = "pass"
    elif blocked_answer and len(blocked_answer) == len(ANSWER_BOTS):
        status = "fail"
    else:
        status = "partial"
    return Check(
        "readability.ai_bot_access", "AI crawlers and agents allowed in robots.txt", status, 4, "critical",
        detail=f"{len(AI_BOTS) - len(blocked)}/{len(AI_BOTS)} AI user agents allowed on the homepage."
        + (" Blocking training bots can be a deliberate choice; blocking search/answer bots removes the site from AI answers."
           if blocked else ""),
        evidence={"access": access, "blocked_answer_bots": blocked_answer, "purpose": AI_BOTS},
        fix_hint="Allow search/answer bots (OAI-SearchBot, ChatGPT-User, Claude-SearchBot, PerplexityBot) in robots.txt.",
    )


def _llms_txt(ctx: AuditContext) -> Check:
    body = ctx.file_body("/llms.txt")
    title = "llms.txt present and well-formed"
    fix = "Publish /llms.txt: an H1 site name, a > summary line, and sections of markdown links to key pages."
    if not body:
        return Check("readability.llms_txt", title, "fail", 2, "warning",
                     detail="No /llms.txt found. Still an emerging convention, but cheap to add.", fix_hint=fix)
    has_h1 = bool(re.search(r"^# \S", body, re.M))
    has_summary = bool(re.search(r"^> \S", body, re.M))
    links = re.findall(r"\[[^\]]+\]\([^)]+\)", body)
    quality = {"h1": has_h1, "summary": has_summary, "links": len(links), "chars": len(body),
               "llms_full_txt": bool(ctx.file_body("/llms-full.txt"))}
    status = "pass" if has_h1 and len(links) >= 3 else "partial"
    return Check("readability.llms_txt", title, status, 2, "warning",
                 detail=f"llms.txt found: H1={has_h1}, summary={has_summary}, {len(links)} links.",
                 evidence=quality, fix_hint=fix)


def _structured_data(pages: list[PageData]) -> Check:
    title = "Structured data (JSON-LD) describes the business and its offerings"
    fix = "Add JSON-LD: Organization/LocalBusiness on the homepage plus Product/Offer, Service, FAQPage or Event where relevant."
    if not pages:
        return Check("readability.structured_data", title, "na", 4)
    all_items = [item for p in pages for item in p.json_ld]
    invalid = sum(1 for i in all_items if i.get("_invalid"))
    types = schema_types(all_items)
    pages_with = sum(1 for p in pages if any(not i.get("_invalid") for i in p.json_ld))
    has_core = bool(types & CORE_TYPES)
    has_rich = bool(types & RICH_TYPES)
    if has_core and has_rich and not invalid:
        status = "pass"
    elif types:
        status = "partial"
    else:
        status = "fail"
    return Check("readability.structured_data", title, status, 4, "critical",
                 detail=f"{pages_with}/{len(pages)} pages have JSON-LD; types: {', '.join(sorted(types)) or 'none'}."
                 + (f" {invalid} blocks fail to parse." if invalid else ""),
                 evidence={"types": sorted(types), "pages_with_json_ld": pages_with, "invalid_blocks": invalid,
                           "has_core_entity": has_core, "has_rich_entity": has_rich},
                 fix_hint=fix)


def _no_js_content(pages: list[PageData]) -> Check:
    ratios = [p.metrics["no_js_text_ratio"] for p in pages if p.metrics.get("no_js_text_ratio") is not None]
    title = "Content readable without JavaScript"
    if not ratios:
        return Check("readability.no_js_content", title, "na", 4, detail="No rendered pages to compare.")
    avg = sum(ratios) / len(ratios)
    worst = sorted(((p.metrics["no_js_text_ratio"], p.url) for p in pages
                    if p.metrics.get("no_js_text_ratio") is not None))[:5]
    return Check("readability.no_js_content", title, ratio_status(avg, 0.8, 0.5), 4, "critical",
                 detail=f"On average {round(avg * 100)}% of rendered text is in the raw HTML. Many AI crawlers do not run JavaScript.",
                 evidence={"average_ratio": round(avg, 3), "lowest_pages": [{"url": u, "ratio": r} for r, u in worst]},
                 fix_hint="Server-render or statically generate primary content instead of loading it client-side.")


def _semantic_html(pages: list[PageData]) -> Check:
    def score(p: PageData) -> float:
        s = p.soup
        html_tag = s.find("html")
        signals = [
            s.find("main") is not None or s.find(attrs={"role": "main"}) is not None,
            s.find("nav") is not None or s.find(attrs={"role": "navigation"}) is not None,
            s.find("header") is not None or s.find("footer") is not None,
            bool(html_tag and html_tag.get("lang")),
        ]
        return sum(signals) / len(signals)

    if not pages:
        return Check("readability.semantic_html", "Semantic landmarks and language", "na", 2)
    avg = sum(score(p) for p in pages) / len(pages)
    return Check("readability.semantic_html", "Semantic landmarks and language", ratio_status(avg, 0.9, 0.5), 2,
                 detail=f"Landmark/lang coverage {round(avg * 100)}% (main, nav, header/footer, html lang).",
                 fix_hint="Wrap content in <main>, navigation in <nav>, and set <html lang>. Agents navigate by these landmarks.")


def _accessible_names(pages: list[PageData]) -> Check:
    """Buttons, links and inputs need names in the accessibility tree, which browser agents act on (FR-14)."""
    total = unnamed = 0
    examples: list[str] = []
    for p in pages:
        labels_for = {lab.get("for") for lab in p.soup.find_all("label") if lab.get("for")}
        for el in p.soup.find_all(["button", "a", "input", "select", "textarea"]):
            input_type = el.get("type", "text").lower() if el.name == "input" else None
            if input_type == "hidden" or (el.name == "a" and not el.get("href")):
                continue
            total += 1
            img = el.find("img")
            named = (
                el.get_text(strip=True)
                or el.get("aria-label") or el.get("aria-labelledby") or el.get("title")
                or (input_type in ("submit", "button", "reset") and el.get("value"))
                or (input_type == "image" and el.get("alt"))
                or (el.get("id") and el.get("id") in labels_for)
                or el.find_parent("label") is not None
                or (img is not None and img.get("alt"))
            )
            if not named:
                unnamed += 1
                if len(examples) < 10:
                    examples.append(str(el)[:160])
    if not total:
        return Check("readability.accessible_names", "Interactive elements have accessible names", "na", 3)
    ratio = 1 - pct(unnamed, total)
    return Check("readability.accessible_names", "Interactive elements have accessible names",
                 ratio_status(ratio, 0.95, 0.8), 3, "warning",
                 detail=f"{unnamed} of {total} links, buttons and fields have no accessible name.",
                 evidence={"examples": examples},
                 fix_hint="Give icon buttons aria-label, associate inputs with <label for>, and add alt to image links.")


def _content_density(pages: list[PageData]) -> Check:
    """Useful text vs page weight: a proxy for how much of an agent's token budget is boilerplate (FR-15)."""
    ratios = []
    for p in pages:
        html_len = len(p.html)
        text_len = p.metrics.get("rendered_text_chars") or p.metrics.get("raw_text_chars") or 0
        if html_len:
            ratios.append((text_len / html_len, p.url))
    if not ratios:
        return Check("readability.content_density", "Low markup noise per page", "na", 1)
    avg = sum(r for r, _ in ratios) / len(ratios)
    return Check("readability.content_density", "Low markup noise per page", ratio_status(avg, 0.1, 0.03), 1, "info",
                 detail=f"Text is {round(avg * 100, 1)}% of HTML size on average.",
                 evidence={"lowest_pages": [{"url": u, "ratio": round(r, 4)} for r, u in sorted(ratios)[:5]]},
                 fix_hint="Trim inline scripts/styles and repeated boilerplate; keep primary content in the HTML body.")


def _key_facts(pages: list[PageData]) -> Check:
    """Prices, hours, contact and location an agent can extract without guessing (FR-16)."""
    items = [i for p in pages for i in p.json_ld]
    text = " ".join(p.soup.get_text(" ") for p in pages)[:500_000]
    hrefs = [a["href"] for p in pages for a in p.soup.find_all("a", href=True)]

    def in_schema(*keys: str) -> bool:
        return any(any(k in i for k in keys) for i in items)

    facts = {
        "contact": in_schema("telephone", "email", "contactPoint")
        or any(h.startswith(("tel:", "mailto:")) for h in hrefs),
        "location": in_schema("address", "geo") or any(p.soup.find("address") for p in pages),
        "hours": in_schema("openingHours", "openingHoursSpecification") or bool(_HOURS_RE.search(text)),
        "prices": in_schema("offers", "price", "priceRange") or bool(_PRICE_RE.search(text)),
    }
    structured = {
        "contact": in_schema("telephone", "email", "contactPoint"),
        "location": in_schema("address", "geo"),
        "hours": in_schema("openingHours", "openingHoursSpecification"),
        "prices": in_schema("offers", "price", "priceRange"),
    }
    found = sum(facts.values())
    in_markup = sum(structured.values())
    status = "pass" if in_markup >= 2 else ("partial" if found >= 2 else "fail")
    return Check("readability.key_facts", "Key facts are machine-extractable", status, 3, "warning",
                 detail=f"{found}/4 fact types found on the site; {in_markup}/4 in structured data.",
                 evidence={"found_anywhere": facts, "in_structured_data": structured},
                 fix_hint="Expose contact, address, opening hours and prices in JSON-LD, not only in prose or images.")
