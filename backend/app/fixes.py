"""Fix generation (FR-29..FR-32): ready-to-paste artifacts tied to the finding they resolve.

Deterministic where possible (robots.txt, sitemap, canonical/viewport tags, accessibility lists);
LLM-written where it needs judgment (llms.txt, JSON-LD, titles and descriptions), always grounded in
facts from the crawl, with TODO placeholders instead of invented details.
"""

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from urllib.parse import urlparse
from xml.sax.saxutils import escape

from app import llm
from app.crawler.site_files import parse_robots
from app.modules.base import AuditContext, ModuleResult, PageData
from app.modules.readability import AI_BOTS, ANSWER_BOTS

log = logging.getLogger(__name__)


@dataclass
class GeneratedFix:
    check_ids: list[str]  # findings this fix resolves
    type: str  # llms_txt | json_ld | robots_txt | sitemap_xml | meta_tags | html_snippet | a11y_list
    title: str
    content: str
    meta: dict = field(default_factory=dict)  # filename, where to put it, notes


def generate(ctx: AuditContext, classification: dict, module_results: list[ModuleResult]) -> list[GeneratedFix]:
    failing = {c.id: c for mr in module_results for c in mr.checks if c.status in ("partial", "fail")}
    usage: dict = {}
    fixes: list[GeneratedFix] = []

    def attempt(fn, *args):
        try:
            fix = fn(*args)
            if fix:
                fixes.append(fix)
        except llm.LLMUnavailable as exc:
            log.warning("fix %s skipped: %s", fn.__name__, exc)

    if "readability.ai_bot_access" in failing or "seo.robots_txt" in failing:
        attempt(robots_fix, ctx, [i for i in ("readability.ai_bot_access", "seo.robots_txt") if i in failing])
    if "seo.sitemap" in failing:
        attempt(sitemap_fix, ctx)
    if "seo.canonical" in failing or "seo.viewport" in failing:
        attempt(head_tags_fix, failing)
    if "seo.alt_text" in failing:
        attempt(alt_text_fix, failing["seo.alt_text"].evidence)
    a11y_ids = [i for i in ("readability.accessible_names", "actionability.form_labels") if i in failing]
    if a11y_ids:
        attempt(a11y_fix, ctx, a11y_ids)

    if llm.enabled():
        if "readability.llms_txt" in failing:
            attempt(llms_txt_fix, ctx, classification, usage)
        ld_ids = [i for i in ("readability.structured_data", "readability.key_facts") if i in failing]
        if ld_ids:
            attempt(json_ld_fix, ctx, classification, ld_ids, usage)
        meta_ids = [i for i in ("seo.title", "seo.meta_description") if i in failing]
        if meta_ids:
            attempt(meta_fix, ctx, failing, meta_ids, usage)
    log.info("generated %d fixes (llm tokens %s)", len(fixes), usage.get("total_tokens", 0))
    return fixes


# --- deterministic fixes -------------------------------------------------------------------------------

def robots_fix(ctx: AuditContext, check_ids: list[str]) -> GeneratedFix:
    existing = ctx.file_body("/robots.txt") or ""
    robots = parse_robots(existing, ctx.base_url + "robots.txt")
    blocked_answer = [b for b in sorted(ANSWER_BOTS) if not robots.can_fetch(b, ctx.base_url)]
    blocked_training = [b for b in AI_BOTS if b not in ANSWER_BOTS and not robots.can_fetch(b, ctx.base_url)]

    lines = _strip_bot_groups(existing, set(blocked_answer)) if existing else ["User-agent: *", "Allow: /"]
    lines += ["", "# AI search and answer agents: allowed so the site can appear and be cited in AI answers."]
    for bot in sorted(ANSWER_BOTS):
        lines += [f"User-agent: {bot}", "Allow: /", ""]
    if not any(line.lower().startswith("sitemap:") for line in lines):
        lines.append(f"Sitemap: {ctx.base_url}sitemap.xml")
    note = ("Training crawlers still blocked: " + ", ".join(blocked_training) +
            ". That is a policy choice; it does not stop AI search answers.") if blocked_training else ""
    return GeneratedFix(check_ids, "robots_txt", "Updated robots.txt allowing AI answer agents",
                        "\n".join(lines).strip() + "\n",
                        {"filename": "robots.txt", "location": "site root", "unblocked": blocked_answer, "note": note})


def _strip_bot_groups(robots_txt: str, bots: set[str]) -> list[str]:
    """Drop groups that only target `bots` (they are re-added as Allow groups); keep everything else verbatim."""
    out: list[str] = []
    group: list[str] = []
    agents: list[str] = []
    in_rules = False

    def flush():
        if group and not (agents and all(a in {b.lower() for b in bots} for a in agents)):
            out.extend(group)

    for raw in robots_txt.splitlines():
        key = raw.split(":", 1)[0].strip().lower()
        if key == "user-agent":
            if in_rules:
                flush()
                group, agents, in_rules = [], [], False
            agents.append(raw.split(":", 1)[1].strip().lower())
            group.append(raw)
        else:
            if key in ("allow", "disallow", "crawl-delay"):
                in_rules = True
            group.append(raw)
    flush()
    return out


def sitemap_fix(ctx: AuditContext) -> GeneratedFix:
    urls = [p.metrics.get("final_url") or p.url for p in ctx.html_pages
            if (p.status_code or 0) < 400 and not _is_noindex(p)]
    body = "\n".join(f"  <url><loc>{escape(u)}</loc></url>" for u in dict.fromkeys(urls))
    xml = f'<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n{body}\n</urlset>\n'
    return GeneratedFix(["seo.sitemap"], "sitemap_xml", "XML sitemap of crawled pages", xml,
                        {"filename": "sitemap.xml", "location": "site root",
                         "note": f"Covers the {len(urls)} pages crawled; generate it from your CMS to include every page."})


def _is_noindex(p: PageData) -> bool:
    tag = p.soup.find("meta", attrs={"name": re.compile("^robots$", re.I)})
    return bool(tag and "noindex" in tag.get("content", "").lower())


def head_tags_fix(failing: dict) -> GeneratedFix:
    ids, parts = [], []
    if "seo.canonical" in failing:
        ids.append("seo.canonical")
        parts.append("<!-- On every indexable page, pointing at that page's preferred URL -->\n"
                     '<link rel="canonical" href="https://YOUR-DOMAIN/CURRENT-PAGE-PATH">')
    if "seo.viewport" in failing:
        ids.append("seo.viewport")
        parts.append('<meta name="viewport" content="width=device-width, initial-scale=1">')
    pages = sorted({u for i in ids for u in failing[i].evidence.get("failing_pages", [])})
    return GeneratedFix(ids, "html_snippet", "Missing <head> tags", "\n\n".join(parts),
                        {"location": "<head> of each affected page (usually the shared layout template)", "pages": pages})


def alt_text_fix(evidence: dict) -> GeneratedFix:
    rows = []
    for src in evidence.get("missing_alt_src", []):
        stem = PurePosixPath(urlparse(src).path).stem
        guess = re.sub(r"[-_]+|\d{2,}", " ", stem).strip().capitalize() or "Describe this image"
        rows.append(f'{src}\n  -> alt="{guess}"   (or alt="" if purely decorative)')
    return GeneratedFix(["seo.alt_text"], "a11y_list", "Images missing alt text", "\n".join(rows),
                        {"note": "Suggested alt text is guessed from file names: review before using."})


def a11y_fix(ctx: AuditContext, check_ids: list[str]) -> GeneratedFix | None:
    rows = []
    for p in ctx.html_pages:
        labels_for = {lab.get("for") for lab in p.soup.find_all("label") if lab.get("for")}
        for el in p.soup.find_all(["button", "a", "input", "select", "textarea"]):
            fix = _a11y_suggestion(el, labels_for)
            if fix:
                rows.append(f"{p.url}\n  {str(el)[:150]}\n  -> {fix}")
            if len(rows) >= 40:
                break
        if len(rows) >= 40:
            break
    if not rows:
        return None
    return GeneratedFix(check_ids, "a11y_list", "Unlabelled controls agents cannot identify", "\n\n".join(rows),
                        {"note": "Browser agents find controls by their accessible name; each item lacks one."})


def _a11y_suggestion(el, labels_for: set) -> str | None:
    if el.get("aria-label") or el.get("aria-labelledby") or el.find_parent("label"):
        return None
    if el.name in ("input", "select", "textarea"):
        input_type = el.get("type", "text").lower()
        if input_type in ("hidden", "submit", "button", "reset", "image"):
            return None if el.get("value") or el.get("alt") or input_type == "hidden" else 'add value="<action>"'
        if el.get("id") and el["id"] in labels_for:
            return None
        hint = el.get("placeholder") or el.get("name") or input_type
        field_id = el.get("id") or re.sub(r"\W+", "-", hint.lower()).strip("-") or "field"
        return f'add <label for="{field_id}">{hint.capitalize()}</label>' + ("" if el.get("id") else f' and id="{field_id}"')
    if el.name == "a" and not el.get("href"):
        return None
    img = el.find("img")
    if el.get_text(strip=True) or el.get("title") or (img is not None and img.get("alt")):
        return None
    return 'add aria-label="<what this does>"'


# --- LLM-written fixes -----------------------------------------------------------------------------------

def _page_list(ctx: AuditContext, limit: int = 25) -> str:
    rows = []
    for p in ctx.html_pages[:limit]:
        if (p.status_code or 0) >= 400:
            continue
        title = p.soup.title.get_text(strip=True) if p.soup.title else ""
        desc = p.soup.find("meta", attrs={"name": re.compile("^description$", re.I)})
        rows.append(f"- {p.metrics.get('final_url') or p.url} | {title} | {(desc.get('content', '') if desc else '')[:150]}")
    return "\n".join(rows)


_LLMS_SCHEMA = {"type": "object", "properties": {"llms_txt": {"type": "string"}},
                "required": ["llms_txt"], "additionalProperties": False}


def llms_txt_fix(ctx: AuditContext, classification: dict, usage: dict) -> GeneratedFix:
    system = (
        "Write an llms.txt file (llmstxt.org format) for a website: a '# <name>' H1, a '> ' one-line summary, "
        "an optional short paragraph of key facts, then '## ' sections (e.g. Main pages, Products, Docs, Policies, "
        "Optional) listing '- [Title](absolute URL): one-line description'. Use ONLY the URLs and facts given; "
        "never invent pages, prices or claims."
    )
    user = (f"Site: {ctx.base_url}\nName: {classification.get('brand_name')}\nWhat it is: {classification.get('summary')}\n"
            f"Pages (url | title | description):\n{_page_list(ctx)}")
    content = llm.complete_json(system, user, _LLMS_SCHEMA, name="llms_txt", usage=usage)["llms_txt"].strip()
    if not content.startswith("# "):
        content = f"# {classification.get('brand_name') or ctx.base_url}\n\n{content}"
    return GeneratedFix(["readability.llms_txt"], "llms_txt", "llms.txt for AI agents", content + "\n",
                        {"filename": "llms.txt", "location": "site root"})


_LD_SCHEMA = {
    "type": "object",
    "properties": {
        "json_ld": {"type": "string", "description": "A JSON-LD object or @graph as a JSON string."},
        "missing_facts": {"type": "array", "items": {"type": "string"},
                          "description": "Facts left as TODO because the site does not state them."},
    },
    "required": ["json_ld", "missing_facts"],
    "additionalProperties": False,
}


def json_ld_fix(ctx: AuditContext, classification: dict, check_ids: list[str], usage: dict) -> GeneratedFix | None:
    home = ctx.home
    if not home:
        return None
    contacts = sorted({a["href"] for p in ctx.html_pages[:10] for a in p.soup.find_all("a", href=True)
                       if a["href"].startswith(("tel:", "mailto:"))})[:6]
    addresses = [a.get_text(" ", strip=True) for p in ctx.html_pages[:10] for a in p.soup.find_all("address")][:3]
    existing = [i for i in home.json_ld if not i.get("_invalid")][:3]
    system = (
        "Write schema.org JSON-LD for a website's homepage so AI agents can extract its key facts. Use the most "
        "specific types that fit (e.g. Restaurant, Dentist, Store, SoftwareApplication, Organization + WebSite, "
        "Product/Offer). Use ONLY facts present in the input. Where an important property is unknown, use the "
        "string 'TODO: <what to fill in>' and list it in missing_facts. Never invent URLs; only use URLs from "
        "the input. Do not add a SearchAction. Return compact, valid JSON."
    )
    user = (f"URL: {ctx.base_url}\nName: {classification.get('brand_name')}\nType: {classification.get('site_type')} "
            f"({classification.get('offering')})\nLocation: {classification.get('location')}\n"
            f"Summary: {classification.get('summary')}\nContact links: {contacts}\nAddress blocks: {addresses}\n"
            f"Existing JSON-LD: {json.dumps(existing)[:1500]}\n"
            f"Homepage text: {' '.join(home.soup.get_text(' ').split())[:2500]}")
    result = llm.complete_json(system, user, _LD_SCHEMA, name="json_ld", usage=usage)
    try:
        data = json.loads(result["json_ld"])
    except json.JSONDecodeError:
        log.warning("generated JSON-LD did not parse")
        return None
    _drop_invented(data, known_urls={p.metrics.get("final_url") or p.url for p in ctx.html_pages} | {ctx.base_url})
    snippet = f'<script type="application/ld+json">\n{json.dumps(data, indent=2, ensure_ascii=False)}\n</script>'
    return GeneratedFix(check_ids, "json_ld", "JSON-LD structured data for the homepage", snippet,
                        {"location": "<head> or end of <body> on the homepage", "missing_facts": result["missing_facts"]})


def _drop_invented(obj, known_urls: set[str]) -> None:
    """Remove SearchActions and same-site URLs the crawl never saw (the model's guesses), in place."""
    site = urlparse(next(iter(known_urls))).netloc.removeprefix("www.")
    known = {u.rstrip("/") for u in known_urls}
    if isinstance(obj, dict):
        obj.pop("potentialAction", None)
        for key in list(obj):
            value = obj[key]
            if (isinstance(value, str) and value.startswith("http") and key not in ("@context", "sameAs")
                    and urlparse(value).netloc.removeprefix("www.") == site and value.rstrip("/") not in known
                    and not re.search(r"\.(png|jpe?g|webp|svg|gif)$", value, re.I)):
                obj[key] = f"TODO: confirm URL ({value})"
            else:
                _drop_invented(value, known_urls)
    elif isinstance(obj, list):
        for item in obj:
            _drop_invented(item, known_urls)


_META_SCHEMA = {
    "type": "object",
    "properties": {"pages": {"type": "array", "items": {
        "type": "object",
        "properties": {"url": {"type": "string"}, "title": {"type": "string"}, "description": {"type": "string"}},
        "required": ["url", "title", "description"], "additionalProperties": False}}},
    "required": ["pages"],
    "additionalProperties": False,
}


def meta_fix(ctx: AuditContext, failing: dict, check_ids: list[str], usage: dict) -> GeneratedFix | None:
    urls = list(dict.fromkeys(u for i in check_ids for u in failing[i].evidence.get("failing_pages", [])))[:6]
    pages = [p for p in ctx.html_pages if p.url in urls]
    if not pages:
        return None
    blocks = []
    for p in pages:
        h1 = p.soup.find("h1")
        blocks.append(f"URL: {p.url}\nCurrent title: {p.soup.title.get_text(strip=True) if p.soup.title else ''}\n"
                      f"H1: {h1.get_text(' ', strip=True) if h1 else ''}\n"
                      f"Text: {' '.join(p.soup.get_text(' ').split())[:600]}")
    system = ("Write an SEO title (30-60 characters, unique, front-load the topic) and meta description "
              "(120-160 characters, specific, no hype) for each page, using only what the page says.")
    result = llm.complete_json(system, "\n\n".join(blocks), _META_SCHEMA, name="meta_tags", usage=usage)
    out = []
    for row in result["pages"]:
        out.append(f"<!-- {row['url']} -->\n<title>{escape(row['title'])}</title>\n"
                   f'<meta name="description" content="{escape(row["description"], {chr(34): "&quot;"})}">')
    return GeneratedFix(check_ids, "meta_tags", "Suggested titles and meta descriptions", "\n\n".join(out),
                        {"location": "<head> of each page", "pages": urls})
