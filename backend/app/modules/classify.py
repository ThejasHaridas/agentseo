"""Site-type classifier (FR-26): LLM over a compact summary of the site, with a schema-based fallback."""

import logging
import re

from app import llm
from app.modules.base import AuditContext, schema_types

log = logging.getLogger(__name__)

SITE_TYPES = ["ecommerce", "local_business", "saas", "docs", "blog", "portfolio", "government", "other"]

_SCHEMA = {
    "type": "object",
    "properties": {
        "site_type": {"type": "string", "enum": SITE_TYPES},
        "confidence": {"type": "number"},
        "summary": {"type": "string", "description": "One sentence on what the site offers."},
        "brand_name": {"type": "string", "description": "The business or product name as customers would say it."},
        "location": {"type": "string", "description": "City/region served if it is a local business or clearly local; empty string otherwise."},
        "offering": {"type": "string", "description": "Short generic category of what is offered, e.g. 'Italian restaurant', 'used books', 'project management software'."},
        "key_tasks": {
            "type": "array",
            "items": {"type": "string"},
            "description": (
                "2-4 concrete requests a customer would give their AI agent for this site, each with a clear, "
                "checkable end state. First: the site's core transaction if it has one (e.g. 'Add a poetry book "
                "to the basket and open the basket'). Second: the most important fact lookup (e.g. 'Find the "
                "opening hours on Saturday'). Never vague browsing tasks like 'browse products'. Only name items "
                "or facts visible in the summary; otherwise describe them generically."
            ),
        },
        "task_heaviness": {
            "type": "string",
            "enum": ["high", "medium", "low"],
            "description": "How much users come to DO things (buy, book, sign up) vs only read.",
        },
    },
    "required": ["site_type", "confidence", "summary", "brand_name", "location", "offering", "key_tasks", "task_heaviness"],
    "additionalProperties": False,
}

_SYSTEM = (
    "You classify websites for an audit tool. Given a summary of a crawled site, return its type, "
    "what it offers, and the tasks an AI agent acting for a customer would most likely attempt there. "
    "Types: ecommerce (sells products online), local_business (physical location: restaurant, clinic, salon, "
    "hotel), saas (software product), docs (developer or product documentation), blog (articles/news), "
    "portfolio (individual or agency showcase), government (public sector), other."
)

_TYPE_HINTS = {
    "ecommerce": {"Product", "Offer", "AggregateOffer", "Store"},
    "local_business": {"LocalBusiness", "Restaurant", "Dentist", "MedicalBusiness", "Hotel", "Store"},
    "saas": {"SoftwareApplication", "WebApplication"},
    "docs": {"TechArticle", "APIReference"},
    "blog": {"BlogPosting", "Article", "NewsArticle", "Blog"},
}


def site_summary(ctx: AuditContext, max_chars: int = 6000) -> str:
    lines = [f"URL: {ctx.base_url}"]
    if ctx.business_type:
        lines.append(f"Owner-stated business type: {ctx.business_type}")
    types = schema_types([i for p in ctx.html_pages for i in p.json_ld])
    if types:
        lines.append(f"Schema.org types: {', '.join(sorted(types))}")
    home = ctx.home
    if home:
        s = home.soup
        desc = s.find("meta", attrs={"name": re.compile("^description$", re.I)})
        lines.append(f"Home title: {s.title.get_text(strip=True) if s.title else ''}")
        lines.append(f"Home description: {desc.get('content', '') if desc else ''}")
        nav = [a.get_text(' ', strip=True) for a in s.select("nav a")][:30]
        lines.append(f"Navigation: {' | '.join(t for t in nav if t)}")
        heads = [h.get_text(' ', strip=True) for h in s.find_all(["h1", "h2"])][:15]
        lines.append(f"Headings: {' | '.join(heads)}")
    lines.append("Other page titles: " + " | ".join(
        p.soup.title.get_text(strip=True) for p in ctx.html_pages[1:20] if p.soup.title))
    if home:
        lines.append("Home text excerpt: " + " ".join(home.soup.get_text(" ").split())[:1500])
    return "\n".join(lines)[:max_chars]


def classify(ctx: AuditContext) -> dict:
    if llm.enabled():
        try:
            result = llm.complete_json(_SYSTEM, site_summary(ctx), _SCHEMA, name="site_classification")
            result["source"] = "llm"
            return result
        except (llm.LLMUnavailable, ValueError, KeyError) as exc:
            log.warning("LLM classification failed, using heuristic: %s", exc)
    return _heuristic(ctx)


def brand_from_html(ctx: AuditContext) -> str:
    """Best-effort brand name: og:site_name, then the first segment of the home title, then the domain."""
    home = ctx.home
    if home:
        og = home.soup.find("meta", attrs={"property": "og:site_name"})
        if og and og.get("content", "").strip():
            return og["content"].strip()
        if home.soup.title:
            first = re.split(r"\s[|\-\u2013\u2014:\u00b7]\s", home.soup.title.get_text(strip=True))[0].strip()
            if first:
                return first
    host = ctx.base_url.split("//")[-1].strip("/").removeprefix("www.")
    return host.split(".")[0]


def _heuristic(ctx: AuditContext) -> dict:
    types = schema_types([i for p in ctx.html_pages for i in p.json_ld])
    base = {"confidence": 0.5, "summary": "", "brand_name": brand_from_html(ctx), "location": "", "offering": "",
            "key_tasks": [], "source": "heuristic"}
    for site_type, hints in _TYPE_HINTS.items():
        if types & hints:
            return {**base, "site_type": site_type,
                    "task_heaviness": "high" if site_type in ("ecommerce", "local_business") else "low"}
    return {**base, "site_type": "other", "confidence": 0.2, "task_heaviness": "medium"}
