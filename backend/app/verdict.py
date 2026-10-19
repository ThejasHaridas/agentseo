"""'Do you need this?' verdict (FR-26..FR-28).

A transparent rule-based rating (every factor and its points are returned), a plain-language explanation
(LLM, with a template fallback), and a projected score if the generated fixes are applied.
"""

import logging
import math

from app import llm
from app.modules.base import ModuleResult
from app.scoring import overall_agent_ready

log = logging.getLogger(__name__)

# How much agent traffic matters by site type: people delegate buying, booking and product research
# to agents far more than reading a portfolio.
TYPE_NEED = {"ecommerce": 2, "local_business": 2, "saas": 2, "docs": 1, "blog": 1,
             "portfolio": 0, "government": 1, "other": 1}

TYPE_LABEL = {"ecommerce": "E-commerce", "local_business": "Local business", "saas": "SaaS", "docs": "Documentation",
              "blog": "Blog", "portfolio": "Portfolio", "government": "Government", "other": "Other"}

_SCHEMA = {
    "type": "object",
    "properties": {
        "headline": {"type": "string", "description": "One sentence verdict a site owner understands."},
        "explanation": {"type": "string", "description": "2-4 plain sentences: why, using the numbers given."},
    },
    "required": ["headline", "explanation"],
    "additionalProperties": False,
}


def build(classification: dict, module_results: list[ModuleResult], visibility: dict,
          fixed_check_ids: set[str]) -> dict:
    scores = {mr.module: mr.score for mr in module_results}
    site_type = classification.get("site_type") or "other"
    overall = overall_agent_ready(scores, site_type)["value"]

    factors: list[dict] = []

    def factor(name: str, points: int, why: str):
        factors.append({"factor": name, "points": points, "why": why})

    need = TYPE_NEED.get(site_type, 1)
    factor("site_type", need, f"{TYPE_LABEL.get(site_type, 'Other')} sites: "
           + {2: "customers increasingly ask agents to find, compare and transact here.",
              1: "agents mainly read and cite this kind of site.",
              0: "agents rarely act on this kind of site."}[need])
    heaviness = classification.get("task_heaviness")
    if heaviness == "high":
        factor("task_heaviness", 1, "Visitors come to do things (buy, book, sign up), which agents now attempt for them.")
    if overall is not None:
        if overall < 40:
            factor("readiness_gap", 2, f"Agent-Ready score is {overall}/100: agents struggle to read or use the site.")
        elif overall < 60:
            factor("readiness_gap", 1, f"Agent-Ready score is {overall}/100: notable gaps for agents.")
    if visibility.get("answers"):
        rate = visibility.get("unbranded_mention_rate", 0)
        competitors = [c["domain"] for c in visibility.get("top_competitors", [])[:3]]
        if rate < 0.3 and competitors:
            factor("competitors_visible", 1,
                   f"AI assistants mention you in {round(rate * 100)}% of discovery questions, "
                   f"while recommending {', '.join(competitors)}.")
    task = scores.get("task_success")
    if task is not None and task < 50:
        factor("agent_failures", 1, f"Test agents completed only {task:.0f}% of key tasks.")

    points = sum(f["points"] for f in factors)
    priority = "Critical" if points >= 4 else "Recommended" if points >= 2 else "Low priority"
    projection = project(module_results, fixed_check_ids, site_type)

    explanation = _explain(classification, priority, factors, scores, projection)
    return {
        "priority": priority,
        "points": points,
        "factors": factors,
        "headline": explanation["headline"],
        "explanation": explanation["explanation"],
        "explanation_source": explanation["source"],
        "projection": projection,
    }


def project(module_results: list[ModuleResult], fixed_check_ids: set[str], site_type: str | None) -> dict:
    """Estimated scores if every generated fix is applied: each fixed check is assumed to then pass.

    Rule-based estimate, not a prediction: agent task and visibility scores are left unchanged because
    fixes affect them only indirectly.
    """
    current, projected = {}, {}
    for mr in module_results:
        current[mr.module] = mr.score
        gain = sum(mr.impact(c) for c in mr.checks if c.id in fixed_check_ids)
        projected[mr.module] = None if mr.score is None else round(min(100.0, mr.score + gain), 1)
    return {
        "label": "Estimate: assumes each generated fix makes its check pass; agent tests and AI visibility unchanged.",
        "current": {**current, "agent_ready": overall_agent_ready(current, site_type)["value"]},
        "projected": {**projected, "agent_ready": overall_agent_ready(projected, site_type)["value"]},
    }


def _r(value: float | None) -> str:
    """Whole points, rounded half-up exactly as the dashboard shows them (Python's round() is half-even)."""
    return "unknown" if value is None else str(math.floor(value + 0.5))


MODULE_LABEL = {"seo": "classic SEO", "readability": "agent readability", "actionability": "actionability",
                "task_success": "agent task success", "visibility": "AI visibility"}


def _with_priority(headline: str, priority: str) -> str:
    return headline if headline.lower().startswith(priority.lower()) else f"{priority}: {headline}"


def _explain(classification: dict, priority: str, factors: list[dict], scores: dict, projection: dict) -> dict:
    facts = (f"Site: {classification.get('brand_name')} ({classification.get('site_type')}, "
             f"{classification.get('offering')})\nPriority: {priority}\n"
             + "\n".join(f"- {f['why']}" for f in factors)
             + "\nScores out of 100, as the owner sees them: "
             + ", ".join(f"{MODULE_LABEL.get(k, k)} {_r(v)}" for k, v in scores.items() if v is not None)
             + f"\nAgent-Ready now {_r(projection['current']['agent_ready'])}, "
               f"estimated after fixes {_r(projection['projected']['agent_ready'])}")
    if llm.enabled():
        try:
            out = llm.complete_json(
                "You explain to a small-business owner, in plain words and without jargon or hype, whether "
                "optimising their website for AI agents is worth doing now. The priority has already been decided; "
                "your headline and explanation must agree with it (Critical = act now; Recommended = worth doing "
                "in the next few months; Low priority = not urgent, cheap fixes only). Use only the facts and "
                "numbers given, exactly as written (whole numbers); never introduce thresholds, benchmarks or "
                "predictions that are not in the input.",
                facts, _SCHEMA, name="verdict")
            return {**out, "headline": _with_priority(out["headline"], priority), "source": "llm"}
        except llm.LLMUnavailable as exc:
            log.warning("verdict explanation fell back to template: %s", exc)
    reasons = " ".join(f["why"] for f in factors)
    return {"headline": f"Agent optimisation: {priority}.", "explanation": reasons, "source": "template"}
