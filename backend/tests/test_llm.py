import json

import httpx
import pytest

from app import llm

SCHEMA = {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"], "additionalProperties": False}
DAILY_429 = '{"error":{"message":"Rate limit reached ... on tokens per day (TPD): Limit 200000"}}'


def ok_response(model: str) -> httpx.Response:
    body = {"model": model, "choices": [{"message": {"content": json.dumps({"ok": True})}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12}}
    return httpx.Response(200, json=body)


@pytest.fixture(autouse=True)
def key(monkeypatch):
    monkeypatch.setattr("app.config.settings.llm_api_key", "test")
    monkeypatch.setattr("app.llm.time.sleep", lambda s: None)


def test_daily_limit_falls_back_to_other_model(monkeypatch):
    calls = []

    def fake_post(url, json, headers, timeout):
        calls.append(json["model"])
        if json["model"] == "openai/gpt-oss-120b":
            return httpx.Response(429, text=DAILY_429, headers={"retry-after": "59"})
        return ok_response(json["model"])

    monkeypatch.setattr("app.llm.httpx.post", fake_post)
    usage: dict = {}
    assert llm.complete_json("s", "u", SCHEMA, usage=usage) == {"ok": True}
    assert calls == ["openai/gpt-oss-120b", "openai/gpt-oss-20b"]  # no retry loop on a daily limit
    assert usage["total_tokens"] == 12


def test_daily_limit_on_search_raises_immediately(monkeypatch):
    calls = []
    monkeypatch.setattr("app.llm.httpx.post",
                        lambda url, json, headers, timeout: calls.append(1) or httpx.Response(429, text=DAILY_429))
    with pytest.raises(llm.LLMBudgetExhausted):
        llm.answer_with_search("q", "openai/gpt-oss-20b")
    assert len(calls) == 1


def test_per_minute_limit_is_retried(monkeypatch):
    responses = iter([httpx.Response(429, text="tokens per minute", headers={"retry-after": "2"}),
                      ok_response("openai/gpt-oss-120b")])
    monkeypatch.setattr("app.llm.httpx.post", lambda url, json, headers, timeout: next(responses))
    assert llm.complete_json("s", "u", SCHEMA) == {"ok": True}


def test_search_answer_tolerates_null_results(monkeypatch):
    message = {"content": "Try [Shop](https://shop.example).", "executed_tools": [
        {"name": "browser.open", "arguments": "{}", "search_results": {"results": None}},
        {"name": "browser.search", "arguments": '{"query": "q"}', "search_results": None},
        {"name": "browser.search", "arguments": '{"query": "q2"}',
         "search_results": {"results": [{"url": "https://a.example"}, "junk"]}}]}
    body = {"choices": [{"message": message}], "usage": {"total_tokens": 5}}
    monkeypatch.setattr("app.llm.httpx.post", lambda url, json, headers, timeout: httpx.Response(200, json=body))
    answer = llm.answer_with_search("q", "m")
    assert answer.source_urls == ["https://a.example"]
    assert answer.queries == ["q", "q2"] and answer.searched and answer.tokens == 5
