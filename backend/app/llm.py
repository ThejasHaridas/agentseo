"""Thin client for an OpenAI-compatible chat completions API (Groq for now).

Kept provider-agnostic on purpose: swapping providers means changing llm_base_url / llm_model / llm_api_key.
"""

import json
import logging
import time
from dataclasses import dataclass, field

import httpx

from app.config import settings

log = logging.getLogger(__name__)

_MAX_ATTEMPTS = 6
_MAX_WAIT_S = 60.0


class LLMUnavailable(RuntimeError):
    pass


class LLMBudgetExhausted(LLMUnavailable):
    """The provider's daily quota is used up: retrying within this audit is pointless."""


def enabled() -> bool:
    return bool(settings.llm_api_key)


def _post(body: dict, usage: dict | None, timeout: float = 90) -> dict:
    """POST a chat completion, retrying 429s after the server's retry-after. Adds token counts into `usage`."""
    if not enabled():
        raise LLMUnavailable("no LLM API key configured (set GROQ_API_KEY)")
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            resp = httpx.post(
                f"{settings.llm_base_url}/chat/completions",
                json=body,
                headers={"Authorization": f"Bearer {settings.llm_api_key}"},
                timeout=timeout,
            )
        except httpx.HTTPError as exc:
            if attempt == _MAX_ATTEMPTS:
                raise LLMUnavailable(f"LLM request failed: {exc}") from exc
            time.sleep(2 * attempt)
            continue
        if resp.status_code == 429 and "per day" in resp.text:
            raise LLMBudgetExhausted(f"{body['model']}: daily token limit reached ({resp.text[:200]})")
        if resp.status_code in (429, 503) and attempt < _MAX_ATTEMPTS:
            wait = min(float(resp.headers.get("retry-after", 5 * attempt)), _MAX_WAIT_S)
            log.info("llm %s rate limited, retrying in %.0fs", body["model"], wait)
            time.sleep(wait)
            continue
        if resp.status_code != 200:
            raise LLMUnavailable(f"LLM call failed: {resp.status_code} {resp.text[:300]}")
        break

    data = resp.json()
    tokens = data.get("usage", {})
    if usage is not None:
        for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
            usage[key] = usage.get(key, 0) + (tokens.get(key) or 0)
    log.info("llm %s tokens in=%s out=%s", body["model"], tokens.get("prompt_tokens"), tokens.get("completion_tokens"))
    return data


def complete_json(system: str, user: str, schema: dict, name: str = "result", reasoning_effort: str = "low",
                  model: str | None = None, usage: dict | None = None) -> dict:
    """One chat completion constrained to `schema` (strict JSON schema). Returns the parsed object."""
    body = {
        "model": model or settings.llm_model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "response_format": {"type": "json_schema", "json_schema": {"name": name, "strict": True, "schema": schema}},
        "reasoning_effort": reasoning_effort,
        "temperature": 0,
    }
    try:
        data = _post(body, usage)
    except LLMBudgetExhausted:
        # Each model has its own daily quota; fall back rather than fail the audit stage.
        if not settings.llm_fallback_model or body["model"] == settings.llm_fallback_model:
            raise
        log.warning("%s out of daily tokens, falling back to %s", body["model"], settings.llm_fallback_model)
        data = _post({**body, "model": settings.llm_fallback_model}, usage)
    try:
        return json.loads(data["choices"][0]["message"]["content"])
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
        raise LLMUnavailable(f"LLM returned unparseable output: {exc}") from exc


@dataclass
class SearchAnswer:
    content: str
    source_urls: list[str] = field(default_factory=list)
    queries: list[str] = field(default_factory=list)
    searched: bool = True
    tokens: int = 0


_SEARCH_SYSTEM = ("You are a helpful consumer AI assistant. Search the web once to ground your answer, open a "
                  "page only if essential, then answer concisely, naming specific businesses or sites with links.")


def answer_with_search(prompt: str, model: str, usage: dict | None = None) -> SearchAnswer:
    """Ask `model` a question with its built-in web search, as a consumer AI assistant would answer it.

    Groq's browser_search tool (gpt-oss models) is incompatible with structured outputs, so this returns
    free text plus the URLs the search surfaced.
    """
    body = {
        "model": model,
        "messages": [{"role": "system", "content": _SEARCH_SYSTEM}, {"role": "user", "content": prompt}],
        "tools": [{"type": "browser_search"}],
        # "required" makes the API reject answers given from memory; those are still real assistant answers.
        "tool_choice": "auto",
        "reasoning_effort": "low",
    }
    call_usage: dict = {}
    data = _post(body, call_usage, timeout=120)
    if usage is not None:
        for key, value in call_usage.items():
            usage[key] = usage.get(key, 0) + value
    try:
        message = data["choices"][0]["message"]
    except (KeyError, IndexError) as exc:
        raise LLMUnavailable(f"LLM returned no message: {exc}") from exc
    urls, queries = [], []
    for tool in message.get("executed_tools") or []:
        for result in (tool.get("search_results") or {}).get("results") or []:
            if isinstance(result, dict) and result.get("url"):
                urls.append(result["url"])
        try:
            queries.append(json.loads(tool.get("arguments") or "{}").get("query", ""))
        except json.JSONDecodeError:
            pass
    return SearchAnswer(content=message.get("content") or "", source_urls=urls, queries=[q for q in queries if q],
                        searched=bool(message.get("executed_tools")), tokens=call_usage.get("total_tokens", 0))
