import json

from app import fixes, verdict
from app.llm import SearchAnswer
from app.modules.base import AuditContext, Check, ModuleResult, PageData
from app.modules.visibility import VisibilityAnswer, analyse_answer, registrable_domain, summarise, wilson_interval

ANSWER = """Here are good options:
| Site | Why |
|---|---|
| **ThriftBooks** – [thriftbooks.com](https://www.thriftbooks.com) | cheap |
| **Rosa's Books** – [rosasbooks.co.uk](https://shop.rosasbooks.co.uk/used) | local |
Also see abebooks.com and https://www.reddit.com/r/books."""


def test_registrable_domain():
    assert registrable_domain("https://www.shop.example.com/x") == "example.com"
    assert registrable_domain("https://shop.rosasbooks.co.uk/") == "rosasbooks.co.uk"
    assert registrable_domain("example.org") == "example.org"


def test_analyse_answer_mention_citation_competitors():
    result = analyse_answer(SearchAnswer(ANSWER, ["https://rosasbooks.co.uk/about"]), "Rosa's Books", "rosasbooks.co.uk")
    assert result["mentioned"] and result["cited_url"] == "https://shop.rosasbooks.co.uk/used"
    assert result["in_sources"]
    assert result["competitors"] == ["thriftbooks.com", "abebooks.com"]  # reddit excluded, own domain excluded

    miss = analyse_answer(SearchAnswer(ANSWER, []), "Bookworm", "bookworm.in")
    assert not miss["mentioned"] and miss["cited_url"] is None


def test_wilson_interval_bounds():
    assert wilson_interval(0, 0) == (0.0, 0.0)
    lo, hi = wilson_interval(3, 6)
    assert 0.1 < lo < 0.5 < hi < 0.9
    assert wilson_interval(6, 6)[1] == 1.0


def test_summarise_rates_and_score():
    answers = [
        VisibilityAnswer("q1", "discovery", "m1", 1, mentioned=True, cited_url="https://me.com", competitors=["a.com"]),
        VisibilityAnswer("q2", "discovery", "m1", 1, mentioned=False, competitors=["a.com", "b.com"]),
        VisibilityAnswer("q3", "branded", "m2", 1, mentioned=True),
        VisibilityAnswer("q4", "discovery", "m2", 1, error="429"),
    ]
    s = summarise(answers, "Me", "me.com")
    assert s["answers"] == 3 and s["errors"] == 1
    assert s["unbranded_mention_rate"] == 0.5
    assert s["top_competitors"][0] == {"domain": "a.com", "answers": 2}
    assert s["score"] == round(100 * (0.6 * 0.5 + 0.2 * (2 / 3) + 0.2 * (1 / 3)), 1)


def ctx_with(robots: str | None, pages=None) -> AuditContext:
    files = {"/robots.txt": {"found": robots is not None, "body": robots}}
    pages = pages or [PageData("https://me.com/", 200, "<html><title>Me</title></html>", None, {})]
    return AuditContext("https://me.com/", files, pages)


def test_robots_fix_unblocks_answer_bots_keeps_rest():
    robots = "User-agent: *\nDisallow: /admin\n\nUser-agent: OAI-SearchBot\nDisallow: /\n\nUser-agent: GPTBot\nDisallow: /\n"
    fix = fixes.robots_fix(ctx_with(robots), ["readability.ai_bot_access"])
    assert "Disallow: /admin" in fix.content
    assert "User-agent: GPTBot\nDisallow: /" in fix.content  # training-bot policy left to the owner
    assert "User-agent: OAI-SearchBot\nAllow: /" in fix.content
    assert fix.content.count("OAI-SearchBot") == 1
    assert "Sitemap: https://me.com/sitemap.xml" in fix.content
    assert fix.meta["unblocked"] == ["OAI-SearchBot"] and "GPTBot" in fix.meta["note"]


def test_sitemap_fix_skips_noindex_and_errors():
    pages = [
        PageData("https://me.com/", 200, "<html></html>", None, {}),
        PageData("https://me.com/a&b", 200, "<html></html>", None, {}),
        PageData("https://me.com/hidden", 200, '<meta name="robots" content="noindex">', None, {}),
        PageData("https://me.com/gone", 404, "<html></html>", None, {}),
    ]
    xml = fixes.sitemap_fix(ctx_with(None, pages)).content
    assert "<loc>https://me.com/a&amp;b</loc>" in xml
    assert "hidden" not in xml and "gone" not in xml


def test_a11y_suggestions():
    from bs4 import BeautifulSoup
    soup = BeautifulSoup('<input name="email" placeholder="Email"><button><svg/></button><button>OK</button>', "lxml")
    inp, icon, ok = soup.find("input"), *soup.find_all("button")
    assert fixes._a11y_suggestion(inp, set()) == 'add <label for="email">Email</label> and id="email"'
    assert fixes._a11y_suggestion(icon, set()) == 'add aria-label="<what this does>"'
    assert fixes._a11y_suggestion(ok, set()) is None


def test_verdict_rules_and_projection(monkeypatch):
    monkeypatch.setattr("app.config.settings.llm_api_key", None)
    readability = ModuleResult("readability", [Check("readability.llms_txt", "x", "fail", 1),
                                               Check("readability.semantic_html", "y", "pass", 1)])
    actionability = ModuleResult("actionability", [Check("actionability.captcha", "z", "fail", 1)])
    tasks = ModuleResult("task_success", [], score_override=25.0)
    vis = {"answers": 6, "unbranded_mention_rate": 0.0, "top_competitors": [{"domain": "rival.com", "answers": 4}]}
    v = verdict.build({"site_type": "local_business", "task_heaviness": "high", "brand_name": "Me"},
                      [readability, actionability, tasks], vis, {"readability.llms_txt"})
    names = {f["factor"] for f in v["factors"]}
    assert {"site_type", "task_heaviness", "readiness_gap", "competitors_visible", "agent_failures"} <= names
    assert v["priority"] == "Critical"
    assert v["projection"]["current"]["readability"] == 50.0
    assert v["projection"]["projected"]["readability"] == 100.0
    assert v["projection"]["projected"]["actionability"] == 0.0  # no fix generated for captcha
    assert v["explanation_source"] == "template"

    low = verdict.build({"site_type": "portfolio"}, [ModuleResult("readability", [Check("a", "a", "pass", 1)])], {}, set())
    assert low["priority"] == "Low priority"
    json.dumps(low)  # stored as JSON


def test_drop_invented_urls_and_search_action():
    data = {"@type": "WebSite", "url": "https://me.com/", "logo": "https://me.com/logo.png",
            "potentialAction": {"@type": "SearchAction", "target": "https://me.com/search?q={q}"},
            "sameAs": ["https://facebook.com/me"],
            "hasMenu": "https://me.com/menu-invented", "subOrganization": [{"url": "https://me.com/about"}]}
    fixes._drop_invented(data, {"https://me.com/", "https://me.com/about"})
    assert "potentialAction" not in data
    assert data["hasMenu"].startswith("TODO: confirm URL")
    assert data["url"] == "https://me.com/" and data["logo"] == "https://me.com/logo.png"
    assert data["subOrganization"][0]["url"] == "https://me.com/about"


def test_branded_prompts_reclassified(monkeypatch):
    from app.modules import visibility
    monkeypatch.setattr("app.llm.complete_json", lambda *a, **k: {"prompts": [
        {"text": "Is Rosa's any good?", "intent": "branded"},
        {"text": "best pizza near rosa's place", "intent": "discovery"},
        {"text": "best pizza in Kochi", "intent": "discovery"}]})
    prompts = visibility.generate_prompts({"brand_name": "Rosa's"}, 3, {})
    assert [p["intent"] for p in prompts] == ["branded", "branded", "discovery"]


def test_verdict_headline_carries_priority():
    assert verdict._with_priority("Worth fixing soon.", "Recommended") == "Recommended: Worth fixing soon."
    assert verdict._with_priority("Low priority: fine as is.", "Low priority") == "Low priority: fine as is."
