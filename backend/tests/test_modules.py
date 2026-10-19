from app.modules import actionability, readability, seo
from app.modules.base import AuditContext, Check, ModuleResult, PageData
from app.modules.classify import _heuristic
from app.scoring import overall_agent_ready

GOOD_HTML = """<!doctype html><html lang="en"><head>
<title>Rosa's Trattoria - Italian restaurant in Kochi</title>
<meta name="description" content="Family-run Italian restaurant in Kochi serving wood-fired pizza and fresh pasta. Book a table online.">
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="canonical" href="https://rosas.example/">
<script type="application/ld+json">{"@context":"https://schema.org","@graph":[
 {"@type":"Restaurant","name":"Rosa's","telephone":"+91 484 000000",
  "address":{"@type":"PostalAddress","streetAddress":"1 MG Road"},"openingHours":"Mo-Su 12:00-22:00",
  "priceRange":"$$"},
 {"@type":"Organization","name":"Rosa's"}]}</script>
</head><body><header><nav><a href="/">Home</a><a href="/menu">Menu</a><a href="/book">Book</a></nav></header>
<main><h1>Rosa's Trattoria</h1><h2>Menu</h2><p>Margherita pizza $12</p>
<img src="/pizza.jpg" alt="Margherita pizza">
<form id="booking"><label for="date">Date</label><input id="date" name="date" type="date">
<button type="submit">Book a table</button></form></main><footer>1 MG Road</footer></body></html>"""

BAD_HTML = """<html><head></head><body><div id="root"></div>
<script src="https://www.google.com/recaptcha/api.js"></script>
<form><input type="text"><input type="email"><button><svg></svg></button></form>
<img src="a.png"><img src="b.png"></body></html>"""

ROBOTS_BLOCKING = "User-agent: GPTBot\nDisallow: /\nUser-agent: OAI-SearchBot\nDisallow: /\n"


def ctx_for(html: str, robots: str | None = None, llms: str | None = None, rendered: str | None = None) -> AuditContext:
    files = {
        "/robots.txt": {"found": robots is not None, "body": robots, "status": 200 if robots else 404},
        "/llms.txt": {"found": llms is not None, "body": llms},
    }
    raw_len = len(html)
    page = PageData("https://rosas.example/", 200, html, rendered or html,
                    {"no_js_text_ratio": 1.0 if rendered is None else 0.05,
                     "raw_text_chars": raw_len // 10, "rendered_text_chars": raw_len // 10})
    return AuditContext(base_url="https://rosas.example/", site_files=files, pages=[page],
                        sitemap_urls=["https://rosas.example/"])


def checks_by_id(result: ModuleResult) -> dict[str, Check]:
    return {c.id: c for c in result.checks}


def test_module_score_weights_and_impact():
    mr = ModuleResult("x", [Check("a", "a", "pass", 3), Check("b", "b", "partial", 1), Check("c", "c", "na", 5)])
    assert mr.score == 87.5
    assert mr.impact(mr.checks[1]) == 12.5
    assert ModuleResult("x", [Check("a", "a", "na", 1)]).score is None


def test_seo_good_page():
    c = checks_by_id(seo.run(ctx_for(GOOD_HTML, robots="User-agent: *\nAllow: /")))
    for check_id in ("seo.title", "seo.meta_description", "seo.h1", "seo.canonical", "seo.alt_text",
                     "seo.viewport", "seo.indexable", "seo.robots_txt", "seo.sitemap"):
        assert c[check_id].status == "pass", (check_id, c[check_id])
    assert c["seo.pagespeed"].status == "na"  # no client given


def test_seo_noindex_homepage_fails():
    html = GOOD_HTML.replace("<head>", '<head><meta name="robots" content="noindex">')
    assert checks_by_id(seo.run(ctx_for(html)))["seo.indexable"].status == "fail"


def test_readability_good_vs_bad():
    llms = "# Rosa's\n> Italian restaurant\n- [Menu](/menu)\n- [Book](/book)\n- [Contact](/contact)\n"
    good = checks_by_id(readability.run(ctx_for(GOOD_HTML, robots="User-agent: *\nAllow: /", llms=llms)))
    assert good["readability.ai_bot_access"].status == "pass"
    assert good["readability.llms_txt"].status == "pass"
    assert good["readability.structured_data"].status == "pass"
    assert good["readability.key_facts"].status == "pass"
    assert good["readability.semantic_html"].status == "pass"

    bad = checks_by_id(readability.run(ctx_for(BAD_HTML, robots=ROBOTS_BLOCKING, rendered="<p>" + "x" * 500)))
    assert bad["readability.ai_bot_access"].status == "partial"
    assert bad["readability.ai_bot_access"].evidence["blocked_answer_bots"] == ["OAI-SearchBot"]
    assert bad["readability.llms_txt"].status == "fail"
    assert bad["readability.structured_data"].status == "fail"
    assert bad["readability.no_js_content"].status == "fail"


def test_actionability_bad_page():
    c = checks_by_id(actionability.run(ctx_for(BAD_HTML)))
    assert c["actionability.form_labels"].status == "fail"
    assert c["actionability.captcha"].status == "partial"
    assert c["actionability.bot_protection"].status == "pass"


def test_actionability_bot_wall():
    wall = "<html><title>Just a moment...</title><body>cf-chl-bypass</body></html>"
    c = checks_by_id(actionability.run(ctx_for(wall)))
    assert c["actionability.bot_protection"].status == "fail"


def test_heuristic_classifier_and_overall():
    ctx = ctx_for(GOOD_HTML)
    assert _heuristic(ctx)["site_type"] == "local_business"
    overall = overall_agent_ready({"readability": 80, "actionability": 40, "seo": 99}, "local_business")
    assert overall["value"] == round((0.30 * 80 + 0.35 * 40) / 0.65, 1)
    assert overall["missing"] == ["task_success", "visibility"]
