from app.crawler.crawl import extract_links, normalize_url, page_metrics, same_site
from app.crawler.site_files import parse_robots, parse_sitemap, sitemaps_from_robots

ROBOTS = """
User-agent: GPTBot
Disallow: /

User-agent: *
Disallow: /admin
Sitemap: https://example.com/sitemap_index.xml
"""


def test_robots_rules_and_sitemaps():
    robots = parse_robots(ROBOTS, "https://example.com/robots.txt")
    assert not robots.can_fetch("GPTBot", "https://example.com/")
    assert robots.can_fetch("AgentRankBot", "https://example.com/menu")
    assert not robots.can_fetch("AgentRankBot", "https://example.com/admin/users")
    assert sitemaps_from_robots(ROBOTS) == ["https://example.com/sitemap_index.xml"]


def test_parse_sitemap_urlset_and_index():
    urlset = """<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
      <url><loc>https://example.com/a</loc></url><url><loc> https://example.com/b </loc></url></urlset>"""
    index = """<?xml version="1.0"?><sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
      <sitemap><loc>https://example.com/s1.xml</loc></sitemap></sitemapindex>"""
    assert parse_sitemap(urlset) == (["https://example.com/a", "https://example.com/b"], [])
    assert parse_sitemap(index) == ([], ["https://example.com/s1.xml"])
    assert parse_sitemap("not xml") == ([], [])


def test_url_helpers():
    assert normalize_url("https://Example.com#top") == "https://example.com/"
    assert same_site("https://www.example.com/x", "https://example.com/")
    assert not same_site("https://other.com/", "https://example.com/")
    html = '<a href="/menu">Menu</a><a href="mailto:a@b.c">x</a><a href="https://other.com/">o</a>'
    assert extract_links(html, "https://example.com/") == ["https://example.com/menu", "https://other.com/"]


def test_no_js_text_ratio():
    raw = "<html><title>T</title><body><div id=app></div><script>render()</script></body></html>"
    rendered = "<html><title>T</title><body><div id=app><p>Open daily 9 to 5</p></div></body></html>"
    m = page_metrics(raw, rendered)
    assert m["raw_text_chars"] == 1  # just the title
    assert m["no_js_text_ratio"] < 0.1
    assert m["title"] == "T"
