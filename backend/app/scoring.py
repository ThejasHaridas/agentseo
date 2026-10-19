"""Scoring rubric v0.1 (requirements doc, section 9).

Overall Agent-Ready = 35% Readability + 30% Actionability + 20% Task Success + 15% AI Visibility,
adjusted by site type. Modules not run yet are left out and the remaining weights renormalised;
the result says which modules it covers so a partial score is never shown as complete.
"""

RUBRIC_VERSION = "0.1"

BASE_WEIGHTS = {"readability": 0.35, "actionability": 0.30, "task_success": 0.20, "visibility": 0.15}

TYPE_WEIGHTS = {
    # Transactional sites: whether an agent can complete the task matters most.
    "ecommerce": {"readability": 0.30, "actionability": 0.35, "task_success": 0.25, "visibility": 0.10},
    "local_business": {"readability": 0.30, "actionability": 0.35, "task_success": 0.20, "visibility": 0.15},
    # Content sites: being read and cited matters most.
    "blog": {"readability": 0.40, "actionability": 0.10, "task_success": 0.10, "visibility": 0.40},
    "docs": {"readability": 0.45, "actionability": 0.15, "task_success": 0.10, "visibility": 0.30},
}


def weights_for(site_type: str | None) -> dict[str, float]:
    return TYPE_WEIGHTS.get(site_type or "", BASE_WEIGHTS)


def overall_agent_ready(module_scores: dict[str, float | None], site_type: str | None) -> dict:
    weights = weights_for(site_type)
    available = {m: s for m, s in module_scores.items() if m in weights and s is not None}
    if not available:
        return {"value": None, "weights": weights, "included": [], "missing": list(weights)}
    total_w = sum(weights[m] for m in available)
    value = round(sum(weights[m] * s for m, s in available.items()) / total_w, 1)
    return {
        "value": value,
        "weights": weights,
        "included": sorted(available),
        "missing": sorted(set(weights) - set(available)),
    }
