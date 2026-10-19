"""AI Visibility module (FR-23..FR-25): do AI assistants mention or cite the site when customers ask?

1. Generate customer prompts that do not name the brand (how people discover businesses).
2. Ask each model with its built-in web search, like a consumer assistant would.
3. Record whether the brand is mentioned, whether the site is cited/linked, and which other sites appear.
Answers vary run to run, so rates come with a 95% interval rather than as single numbers.
"""

import logging
import math
import re
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from urllib.parse import urlparse

from app import llm
from app.config import settings
from app.modules.base import AuditContext, Check, ModuleResult

log = logging.getLogger(__name__)

# Domains that show up in many answers but are not competitors.
_NOT_COMPETITORS = {
    "wikipedia.org", "reddit.com", "youtube.com", "google.com", "facebook.com", "instagram.com", "x.com",
    "twitter.com", "linkedin.com", "quora.com", "medium.com", "tripadvisor.com", "yelp.com", "exa.ai",
    "bing.com", "duckduckgo.com", "pinterest.com", "tiktok.com", "github.com", "amazon.com",
}

_PROMPT_SCHEMA = {
    "type": "object",
    "properties": {
        "prompts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "intent": {"type": "string", "enum": ["discovery", "comparison", "problem", "branded"]},
                },
                "required": ["text", "intent"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["prompts"],
    "additionalProperties": False,
}

_PROMPT_SYSTEM = (
    "You write the questions real customers type into AI assistants (ChatGPT, Claude, Perplexity) when looking "
    "for a business, product or resource like the one described. Write natural, specific questions. "
    "Most must NOT mention the brand: they test whether the assistant discovers it ('best Italian restaurant "
    "in Kochi for a family dinner', 'cheapest place to buy used textbooks online'). Mix intents: discovery, "
    "comparison ('X vs alternatives'), problem-led ('how do I ...'). Exactly one may be branded "
    "('is <brand> any good?'). Include the location in local questions."
)

_DOMAIN_RE = re.compile(r"\b((?:[a-z0-9-]+\.)+(?:com|org|net|io|co|ai|app|dev|in|uk|de|fr|au|ca|shop|store|edu|gov)"
                        r"(?:\.[a-z]{2})?)\b", re.I)
_LINK_RE = re.compile(r"\]\((https?://[^)\s]+)\)|(?<![\w/])(https?://[^\s)\]>\"']+)")


@dataclass
class VisibilityAnswer:
    prompt: str
    intent: str
    provider: str
    sample: int
    mentioned: bool = False
    cited_url: str | None = None
    in_sources: bool = False
    competitors: list[str] = field(default_factory=list)
    answer: str = ""
    source_urls: list[str] = field(default_factory=list)
    searched: bool = False
    error: str | None = None


def registrable_domain(url_or_host: str) -> str:
    host = urlparse(url_or_host).netloc or url_or_host
    host = host.lower().split(":")[0].removeprefix("www.")
    parts = host.split(".")
    # Keep 3 labels for second-level country domains like example.co.uk / example.com.au.
    if len(parts) >= 3 and parts[-2] in ("co", "com", "org", "net", "ac", "gov") and len(parts[-1]) == 2:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


def generate_prompts(classification: dict, n: int, usage: dict) -> list[dict]:
    facts = "\n".join(f"{k}: {classification.get(k)}" for k in ("brand_name", "site_type", "offering", "location", "summary")
                      if classification.get(k))
    result = llm.complete_json(_PROMPT_SYSTEM, f"Write exactly {n} questions for this business:\n{facts}",
                               _PROMPT_SCHEMA, name="visibility_prompts", usage=usage)
    prompts = result["prompts"][:n]
    brand = (classification.get("brand_name") or "").lower()
    for p in prompts:
        if brand and brand in p["text"].lower():
            p["intent"] = "branded"
    return prompts


def analyse_answer(answer: llm.SearchAnswer, brand: str, domain: str) -> dict:
    text = answer.content
    links = [a or b for a, b in _LINK_RE.findall(text)]
    cited = next((u for u in links if registrable_domain(u) == domain), None)
    brand_hit = bool(brand) and len(brand) >= 3 and re.search(rf"(?<!\w){re.escape(brand)}(?!\w)", text, re.I)
    mentioned = bool(brand_hit or cited or re.search(re.escape(domain), text, re.I))

    others: list[str] = []
    for d in [registrable_domain(u) for u in links] + [registrable_domain(m) for m in _DOMAIN_RE.findall(text)]:
        if d != domain and d not in _NOT_COMPETITORS and d not in others:
            others.append(d)
    return {
        "mentioned": mentioned,
        "cited_url": cited,
        "in_sources": any(registrable_domain(u) == domain for u in answer.source_urls),
        "competitors": others[:10],
    }


def wilson_interval(hits: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if not n:
        return 0.0, 0.0
    p = hits / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return round(max(0.0, centre - half), 3), round(min(1.0, centre + half), 3)


def run(ctx: AuditContext, classification: dict) -> tuple[list[VisibilityAnswer], ModuleResult, dict]:
    usage: dict = {}
    title = "Site appears in AI assistant answers"
    if not llm.enabled() or not settings.visibility_enabled:
        check = Check("visibility.mention_rate", title, "na", 1, detail="Skipped: no LLM key configured or disabled.")
        return [], ModuleResult("visibility", [check]), {}

    brand = classification.get("brand_name") or ""
    domain = registrable_domain(ctx.base_url)
    try:
        prompts = generate_prompts(classification, settings.visibility_prompts, usage)
    except llm.LLMUnavailable as exc:
        check = Check("visibility.mention_rate", title, "na", 1, detail=f"Skipped: {exc}")
        return [], ModuleResult("visibility", [check]), {}

    def ask_all(model: str) -> list[VisibilityAnswer]:
        out, spent, stop_reason = [], 0, None
        for p in prompts:
            for sample in range(1, settings.visibility_samples + 1):
                va = VisibilityAnswer(prompt=p["text"], intent=p["intent"], provider=model, sample=sample)
                if stop_reason:
                    va.error = stop_reason
                    out.append(va)
                    continue
                try:
                    answer = llm.answer_with_search(p["text"], model, usage=usage)
                    spent += answer.tokens
                    va.answer = answer.content[:4000]
                    va.source_urls = answer.source_urls[:20]
                    va.searched = answer.searched
                    for k, v in analyse_answer(answer, brand, domain).items():
                        setattr(va, k, v)
                except llm.LLMBudgetExhausted as exc:
                    va.error = stop_reason = f"skipped: {exc}"[:300]
                except llm.LLMUnavailable as exc:
                    va.error = str(exc)[:300]
                except Exception as exc:  # noqa: BLE001  one malformed response must not sink the audit
                    log.exception("visibility answer failed")
                    va.error = f"unexpected: {exc}"[:300]
                if spent >= settings.visibility_token_budget and not stop_reason:
                    stop_reason = f"skipped: per-audit token budget ({settings.visibility_token_budget}) reached"
                log.info("visibility %s | %s | mentioned=%s tokens=%d", model, p["text"][:60], va.mentioned, spent)
                out.append(va)
        return out

    with ThreadPoolExecutor(max_workers=len(settings.visibility_models)) as pool:
        answers = [a for batch in pool.map(ask_all, settings.visibility_models) for a in batch]

    summary = summarise(answers, brand, domain)
    summary["usage"] = usage
    return answers, ModuleResult("visibility", _checks(summary), score_override=summary.get("score")), summary


def summarise(answers: list[VisibilityAnswer], brand: str, domain: str) -> dict:
    ok = [a for a in answers if not a.error]
    unbranded = [a for a in ok if a.intent != "branded"]
    n = len(ok)
    mentions = sum(a.mentioned for a in ok)
    citations = sum(bool(a.cited_url) for a in ok)
    competitor_counts = Counter(d for a in unbranded for d in set(a.competitors))
    # Share of voice: answers mentioning us vs answers mentioning the most frequent competitors.
    top = competitor_counts.most_common(5)
    sov_denominator = sum(a.mentioned for a in unbranded) + sum(c for _, c in top)
    per_provider = {}
    for provider in sorted({a.provider for a in ok}):
        mine = [a for a in ok if a.provider == provider]
        hits = sum(a.mentioned for a in mine)
        per_provider[provider] = {"answers": len(mine), "mentions": hits, "mention_rate": round(hits / len(mine), 3),
                                  "interval_95": wilson_interval(hits, len(mine))}
    mention_rate = mentions / n if n else 0.0
    citation_rate = citations / n if n else 0.0
    unbranded_rate = sum(a.mentioned for a in unbranded) / len(unbranded) if unbranded else 0.0
    return {
        "brand": brand,
        "domain": domain,
        "answers": n,
        "errors": len(answers) - n,
        "mention_rate": round(mention_rate, 3),
        "mention_interval_95": wilson_interval(mentions, n),
        "unbranded_mention_rate": round(unbranded_rate, 3),
        "citation_rate": round(citation_rate, 3),
        "share_of_voice": round(sum(a.mentioned for a in unbranded) / sov_denominator, 3) if sov_denominator else 0.0,
        "per_provider": per_provider,
        "top_competitors": [{"domain": d, "answers": c} for d, c in competitor_counts.most_common(10)],
        # Discovery matters most: unbranded mentions weigh more than branded ones and links.
        "score": round(100 * (0.6 * unbranded_rate + 0.2 * mention_rate + 0.2 * citation_rate), 1) if n else None,
    }


def _checks(s: dict) -> list[Check]:
    if not s.get("answers"):
        return [Check("visibility.mention_rate", "Site appears in AI assistant answers", "na", 1,
                      detail="All visibility queries failed.")]
    lo, hi = s["mention_interval_95"]
    competitors = ", ".join(c["domain"] for c in s["top_competitors"][:5]) or "none"
    return [
        Check("visibility.unbranded_mentions", "Mentioned when customers ask without naming the brand",
              "pass" if s["unbranded_mention_rate"] >= 0.5 else "partial" if s["unbranded_mention_rate"] > 0 else "fail",
              3, "critical",
              detail=f"Mentioned in {round(s['unbranded_mention_rate'] * 100)}% of unbranded answers "
                     f"(all answers: {round(s['mention_rate'] * 100)}%, 95% range {round(lo * 100)}-{round(hi * 100)}%). "
                     f"Sites recommended instead: {competitors}.",
              evidence={k: s[k] for k in ("per_provider", "top_competitors", "share_of_voice")},
              fix_hint="Publish clear, crawlable pages answering these questions, add structured data, and get listed "
                       "on the third-party sites AI answers cite."),
        Check("visibility.citations", "Linked as a source in AI answers",
              "pass" if s["citation_rate"] >= 0.3 else "partial" if s["citation_rate"] > 0 else "fail", 1, "warning",
              detail=f"Linked in {round(s['citation_rate'] * 100)}% of answers.",
              fix_hint="Allow AI search bots in robots.txt and make key facts quotable on your own pages."),
    ]
