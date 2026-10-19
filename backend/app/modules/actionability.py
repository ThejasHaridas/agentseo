"""Agent Actionability module (FR-17..FR-19): can an agent *do* things here, through the UI or an API?"""

import re

from app.modules.base import AuditContext, Check, ModuleResult, PageData, pct, ratio_status

CAPTCHA_MARKERS = {
    "reCAPTCHA": re.compile(r"google\.com/recaptcha|grecaptcha|g-recaptcha", re.I),
    "hCaptcha": re.compile(r"hcaptcha\.com|h-captcha", re.I),
    "Cloudflare Turnstile": re.compile(r"challenges\.cloudflare\.com/turnstile|cf-turnstile", re.I),
}
BOT_WALL_MARKERS = re.compile(
    r"cf-chl-|challenge-platform|Just a moment\.\.\.|Attention Required! \| Cloudflare|_Incapsula_Resource|"
    r"px-captcha|perimeterx|datadome|Access Denied.{0,80}Reference #",
    re.I,
)
# Phrases (not bare nouns like "book" or "order") that signal a transaction an agent might complete.
FLOW_WORDS = re.compile(
    r"\b(book now|book a (?:table|room|call|demo|appointment)|booking|reserve now|make a reservation|"
    r"appointment|checkout|add to (?:cart|bag|basket)|buy now|order now|order online|request a quote|"
    r"get a quote|start free trial|free trial)\b",
    re.I,
)


def run(ctx: AuditContext) -> ModuleResult:
    pages = ctx.html_pages
    checks = [
        _form_labels(pages),
        _stable_selectors(pages),
        _captcha(pages),
        _login_walls(pages),
        _bot_protection(ctx),
        _visual_only_content(pages),
        _pagination(pages),
        _machine_interfaces(ctx),
    ]
    return ModuleResult("actionability", checks)


def _fields(p: PageData):
    for form in p.soup.find_all("form"):
        for el in form.find_all(["input", "select", "textarea"]):
            if el.name == "input" and el.get("type", "text").lower() in ("hidden", "submit", "button", "image", "reset"):
                continue
            yield form, el


def _form_labels(pages: list[PageData]) -> Check:
    title = "Form fields are labelled"
    total = labelled = placeholder_only = 0
    unlabelled: list[str] = []
    for p in pages:
        labels_for = {lab.get("for") for lab in p.soup.find_all("label") if lab.get("for")}
        for _, el in _fields(p):
            total += 1
            if (el.get("id") and el["id"] in labels_for) or el.find_parent("label") or el.get("aria-label") or el.get("aria-labelledby"):
                labelled += 1
            elif el.get("placeholder"):
                placeholder_only += 1
            elif len(unlabelled) < 10:
                unlabelled.append(f"{p.url} :: {str(el)[:140]}")
    if not total:
        return Check("actionability.form_labels", title, "na", 3, detail="No forms found.")
    # A placeholder is a weak label: agents often see it, but it disappears once filled.
    ratio = pct(labelled + 0.5 * placeholder_only, total)
    return Check("actionability.form_labels", title, ratio_status(ratio, 0.9, 0.6), 3, "critical",
                 detail=f"{labelled}/{total} fields properly labelled, {placeholder_only} placeholder-only.",
                 evidence={"unlabelled": unlabelled},
                 fix_hint="Associate every field with a <label for=...> or aria-label describing what to enter.")


def _stable_selectors(pages: list[PageData]) -> Check:
    title = "Interactive elements have stable identifiers"
    total = stable = 0
    for p in pages:
        for el in p.soup.find_all(["button", "input", "select", "textarea", "form"]):
            if el.name == "input" and el.get("type", "").lower() == "hidden":
                continue
            total += 1
            if el.get("id") or el.get("name") or any(k.startswith("data-test") for k in el.attrs):
                stable += 1
    if not total:
        return Check("actionability.stable_selectors", title, "na", 1)
    ratio = pct(stable, total)
    return Check("actionability.stable_selectors", title, ratio_status(ratio, 0.8, 0.5), 1, "info",
                 detail=f"{stable}/{total} controls have an id, name or data-test attribute.",
                 fix_hint="Give forms and controls stable id/name attributes so scripted agents can target them reliably.")


def _captcha(pages: list[PageData]) -> Check:
    title = "No CAPTCHA on key flows"
    found: dict[str, list[str]] = {}
    for p in pages:
        for name, rx in CAPTCHA_MARKERS.items():
            if rx.search(p.html):
                found.setdefault(name, []).append(p.url)
    if not found:
        return Check("actionability.captcha", title, "pass", 2, "warning", detail="No CAPTCHA widgets detected.")
    n_pages = len({u for urls in found.values() for u in urls})
    return Check("actionability.captcha", title, "partial" if n_pages <= 2 else "fail", 2, "warning",
                 detail=f"CAPTCHA detected on {n_pages} page(s): {', '.join(found)}.",
                 evidence={k: v[:5] for k, v in found.items()},
                 fix_hint="Use invisible/risk-based challenges, or offer an authenticated API path for legitimate agents.")


def _login_walls(pages: list[PageData]) -> Check:
    title = "Core content not behind a login"
    login_pages = [p.url for p in pages if p.soup.find("input", attrs={"type": "password"})]
    if not pages:
        return Check("actionability.login_walls", title, "na", 1)
    ratio = pct(len(login_pages), len(pages))
    status = "pass" if ratio <= 0.1 else ("partial" if ratio <= 0.4 else "fail")
    return Check("actionability.login_walls", title, status, 1, "info",
                 detail=f"{len(login_pages)}/{len(pages)} crawled pages show a password field.",
                 evidence={"pages": login_pages[:10]},
                 fix_hint="Keep product, pricing and booking information public; require login only to complete account actions.")


def _bot_protection(ctx: AuditContext) -> Check:
    title = "Not blocking automated agents"
    walled = [p.url for p in ctx.pages if p.raw_html and BOT_WALL_MARKERS.search(p.raw_html[:20000])]
    forbidden = [p.url for p in ctx.pages if p.status_code in (401, 403, 429, 503)]
    hits = sorted(set(walled + forbidden))
    if not hits:
        return Check("actionability.bot_protection", title, "pass", 4, "critical",
                     detail="No bot challenges or 401/403/429/503 responses to the crawler.")
    home_blocked = bool(ctx.pages) and ctx.pages[0].url in hits
    return Check("actionability.bot_protection", title, "fail" if home_blocked else "partial", 4, "critical",
                 detail=f"{len(hits)} page(s) returned a bot challenge or access error to an identified crawler.",
                 evidence={"pages": hits[:10], "challenge_markup": walled[:5], "status_blocked": forbidden[:5]},
                 fix_hint="Allow-list verified AI agents in your WAF/bot manager rather than challenging all automation.")


def _visual_only_content(pages: list[PageData]) -> Check:
    """Content locked in canvas or text-less image-heavy pages is invisible to text-based agents (FR-19)."""
    title = "Content is text, not canvas or images"
    flagged = []
    for p in pages:
        canvases = len(p.soup.find_all("canvas"))
        imgs = len(p.soup.find_all("img"))
        text = p.metrics.get("rendered_text_chars") or p.metrics.get("raw_text_chars") or 0
        if (canvases and text < 300) or (imgs >= 5 and text < 200):
            flagged.append({"url": p.url, "canvas": canvases, "images": imgs, "text_chars": text})
    if not pages:
        return Check("actionability.visual_only", title, "na", 2)
    ratio = 1 - pct(len(flagged), len(pages))
    return Check("actionability.visual_only", title, ratio_status(ratio, 0.95, 0.75), 2, "warning",
                 detail=f"{len(flagged)} page(s) carry their content mainly in canvas or images.",
                 evidence={"pages": flagged[:10]},
                 fix_hint="Put key information in HTML text; use images for illustration, with alt text.")


def _pagination(pages: list[PageData]) -> Check:
    """Infinite scroll without crawlable pagination hides listings from agents (FR-19)."""
    title = "Listings reachable via links, not only infinite scroll"
    infinite = [p.url for p in pages if re.search(r"infinite[-_ ]?scroll|IntersectionObserver.{0,200}load", p.html, re.I)]
    if not infinite:
        return Check("actionability.pagination", title, "na", 1, "info", detail="No infinite-scroll patterns detected.")
    linked = [u for u in infinite if _has_pagination(next(p for p in pages if p.url == u))]
    status = "pass" if len(linked) == len(infinite) else "partial" if linked else "fail"
    return Check("actionability.pagination", title, status, 1, "warning",
                 detail=f"{len(infinite)} page(s) use infinite scroll; {len(linked)} also expose page links.",
                 evidence={"infinite_scroll_pages": infinite[:10]},
                 fix_hint="Add rel=\"next\" or numbered page links alongside infinite scroll.")


def _has_pagination(p: PageData) -> bool:
    if p.soup.find("link", rel="next") or p.soup.find("a", rel="next"):
        return True
    return any(re.search(r"[?&/]page[=/]?\d", a["href"]) for a in p.soup.find_all("a", href=True))


def _machine_interfaces(ctx: AuditContext) -> Check:
    """Public APIs, OpenAPI specs or MCP manifests let agents act without driving the UI (FR-18)."""
    title = "Machine interface for agents (OpenAPI / MCP / API)"
    found = {path: True for path in ("/openapi.json", "/openapi.yaml", "/.well-known/mcp.json", "/.well-known/ai-plugin.json")
             if ctx.file_body(path)}
    for p in ctx.html_pages:
        for link in p.soup.find_all("link", href=True):
            rel = " ".join(link.get("rel", [])).lower()
            if "api" in rel or "service-desc" in rel or "mcp" in rel:
                found[link["href"]] = True
        for a in p.soup.find_all("a", href=True):
            if re.search(r"/(api|developers?|docs/api)(/|$)", a["href"], re.I):
                found.setdefault("api_docs_links", True)
    flows = sorted({m.lower() for p in ctx.html_pages for m in FLOW_WORDS.findall(p.soup.get_text(" ")[:50000])})
    if found:
        return Check("actionability.machine_interface", title, "pass", 2, "info",
                     detail=f"Found: {', '.join(found)}.", evidence={"found": list(found), "flows_detected": flows})
    # Only a real gap when the site has transactional flows an agent might want to complete.
    status = "fail" if flows else "na"
    return Check("actionability.machine_interface", title, status, 2, "info",
                 detail="No OpenAPI spec, MCP manifest or API docs found."
                 + (f" Site has flows agents may want to complete: {', '.join(flows[:6])}." if flows else ""),
                 evidence={"flows_detected": flows},
                 fix_hint="Expose key actions (search, availability, booking, ordering) via a documented API or MCP server.")
