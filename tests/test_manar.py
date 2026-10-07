"""manar: parsing, checks, AI crawlers, generators, citability, crawling, frameworks, visibility, CLI."""
from __future__ import annotations

import functools
import gzip
import http.server
import json
import sys
import threading

import pytest
from conftest import PLUGINS

MANAR_ROOT = PLUGINS / "manar"
if str(MANAR_ROOT) not in sys.path:
    sys.path.insert(0, str(MANAR_ROOT))

from manar import (  # noqa: E402
    aibots,
    checks,
    citability,
    cli,
    crawl,
    fetch,
    framework,
    generate,
    page,
    visibility,
)

GOOD = """<!doctype html><html lang="en"><head>
<title>Nexika - plugins that make Claude Code faster</title>
<meta name="description" content="Nexika is a set of Claude Code plugins for faster, cheaper and safer work, with tutoring and releases.">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta property="og:title" content="Nexika"><meta property="og:description" content="Plugins">
<meta property="og:image" content="https://nexika.dev/og.png">
<link rel="canonical" href="https://nexika.dev/">
<script type="application/ld+json">{"@context":"https://schema.org","@type":"Organization","name":"Nexika",
"url":"https://nexika.dev","sameAs":["https://github.com/nexika"]}</script>
</head><body><nav>Home Docs</nav><h1>Nexika</h1>
<h2>What is Nexika?</h2>
<p>Nexika is a set of six Claude Code plugins that cut token use by up to 50 percent in 2026 tests.
It includes barq for batched reads, itqan for reviews, siyaq for docs, prof for teaching, amin for
releases and manar for search visibility. Each plugin installs in one command from GitHub and works on
Linux, macOS and Windows with Python 3.10 or newer. The project is open source under the MIT licence
and every change is tested in CI before release. """ + "More detail follows here. " * 20 + """</p>
<img src="/a.png" alt="diagram"><a href="/docs/">Docs</a><footer>Footer words</footer></body></html>"""

BAD = """<html><head><script src="a.js"></script><script src="b.js"></script><script src="c.js"></script>
<script type="application/ld+json">{oops</script></head><body><div id="root"></div>
<img src="x.png"><h1>A</h1><h1>B</h1></body></html>"""


def p(html, url="https://nexika.dev/"):
    return page.parse(html, url)


# ---------------------------------------------------------------- parsing and checks


def test_parse_extracts_head_body_and_jsonld():
    pg = p(GOOD)
    assert pg.title.startswith("Nexika - plugins") and pg.lang == "en"
    assert pg.canonical == "https://nexika.dev/" and pg.meta["og:image"].endswith("og.png")
    assert ("https://nexika.dev/docs/", "Docs") in pg.links and pg.images == [("/a.png", "diagram")]
    assert pg.jsonld_types() == {"Organization"} and not pg.jsonld_errors
    assert "Home Docs" not in pg.text and "Footer words" not in pg.text   # nav/footer are not content
    assert pg.blocks[-1][0] == "What is Nexika?" and pg.words > 150


def test_good_page_has_no_serious_findings():
    assert [f.id for f in checks.page_checks(p(GOOD))] == []


def test_bad_page_findings():
    ids = {f.id for f in checks.page_checks(p(BAD))}
    assert {"title-missing", "description-missing", "canonical-missing", "lang-missing", "viewport-missing",
            "jsonld-invalid", "client-rendered", "h1-multiple", "img-alt"} <= ids


def test_noindex_and_arabic_direction():
    ids = {f.id for f in checks.page_checks(p('<html lang="ar"><head><meta name="robots" content="noindex">'
                                              '</head><body>نص</body></html>'))}
    assert {"noindex", "rtl-missing"} <= ids


# ---------------------------------------------------------------- AI crawlers and site checks


def test_ai_bot_access_separates_search_from_training():
    allowed = aibots.access("User-agent: GPTBot\nDisallow: /\n\nUser-agent: *\nAllow: /\n")
    assert not allowed["GPTBot"] and allowed["OAI-SearchBot"] and allowed["Googlebot"]
    assert aibots.blocked_for_visibility(allowed) == []
    assert [b.name for b in aibots.blocked_for_training(allowed)] == ["GPTBot"]
    blocked = aibots.access("User-agent: OAI-SearchBot\nDisallow: /\n")
    assert [b.name for b in aibots.blocked_for_visibility(blocked)] == ["OAI-SearchBot"]


def test_site_checks():
    home = p(BAD)
    robots = "User-agent: *\nDisallow: /\n"
    ids = {f.id for f in checks.site_checks("http://x.dev", home, robots, None, "", "no title", [home, home])}
    assert {"no-https", "robots-blocks-google", "robots-blocks-ai-search", "robots-no-sitemap",
            "sitemap-missing", "llms-format", "entity-schema-missing"} <= ids
    good = p(GOOD)
    ids = {f.id for f in checks.site_checks("https://nexika.dev", good, None, ["https://nexika.dev/"], "",
                                             generate.llms_txt("N", "S", crawl.Site("x", [good])), [good])}
    assert ids == {"robots-missing"}


def test_sitemap_and_llms_parsing():
    assert checks.parse_sitemap(generate.sitemap_xml(["https://a/1", "https://a/1", "https://a/2"])) == (
        ["https://a/1", "https://a/2"], [])
    index = ('<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
             "<sitemap><loc>https://a/s1.xml</loc></sitemap></sitemapindex>")
    assert checks.parse_sitemap(index) == ([], ["https://a/s1.xml"])
    assert len(checks.validate_llms("just text")) == 4


# ---------------------------------------------------------------- generators and citability


def test_generated_robots_keeps_ai_search_open_and_can_block_training():
    text = generate.robots_txt("https://nexika.dev", block_training=True)
    allowed = aibots.access(text)
    assert not aibots.blocked_for_visibility(allowed)
    assert {b.name for b in aibots.blocked_for_training(allowed)} >= {"GPTBot", "ClaudeBot", "CCBot"}
    assert "Sitemap: https://nexika.dev/sitemap.xml" in text


def test_schema_generation():
    data = generate.schema("software", name="Nexika", url="https://nexika.dev", same_as=["https://github.com/x"])
    assert data["@type"] == "SoftwareApplication" and data["sameAs"] == ["https://github.com/x"]
    assert "softwareVersion" not in data   # empty fields are dropped
    with pytest.raises(ValueError):
        generate.schema("recipe", name="x", url="y")


def test_citability_rewards_direct_specific_answers():
    good, _ = citability.block_score("What is Nexika?", p(GOOD).blocks[-1][1])
    vague, why = citability.block_score("Intro", "It is great and you will love it a lot.")
    assert good >= 70 and vague < 40 and any("pronoun" in w for w in why)
    arabic = "نكسيكا هي مجموعة من ست إضافات لـ Claude Code تقلل استهلاك الرموز بنسبة 50 بالمئة في اختبارات 2026 " * 3
    assert citability.block_score("ما هي نكسيكا؟", arabic)[0] >= 70


# ---------------------------------------------------------------- fetching and crawling


@pytest.fixture
def server(tmp_path):
    site = tmp_path / "site"
    (site / "docs").mkdir(parents=True)
    (site / "private").mkdir()
    (site / "index.html").write_text(GOOD.replace("https://nexika.dev", "http://127.0.0.1"))
    (site / "docs" / "index.html").write_text("<html><head><title>Docs</title></head><body><h1>Docs</h1>"
                                              '<a href="/private/">p</a></body></html>')
    (site / "private" / "index.html").write_text("<html><body>secret</body></html>")
    (site / "robots.txt").write_text("User-agent: *\nDisallow: /private/\n")
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(site))
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}", site
    httpd.shutdown()


def test_crawl_follows_links_and_respects_robots(server):
    url, _ = server
    site = crawl.crawl(url + "/", max_pages=10, allow_local=True, delay=0)
    paths = sorted(pg.url.replace(url, "") for pg in site.pages)
    assert paths == ["/", "/docs/"] and any("/private/" in s for s in site.skipped)
    assert site.robots_txt.startswith("User-agent")


def test_fetch_refuses_private_addresses_unless_allowed(server):
    url, _ = server
    with pytest.raises(fetch.FetchError, match="private address"):
        fetch.get(url)
    with pytest.raises(fetch.FetchError, match="only http"):
        fetch.get("file:///etc/passwd")


def test_gzip_bodies_are_decompressed_even_when_unannounced():
    raw = gzip.compress(b"<title>ok</title>")
    assert fetch._decompress(raw, "") == b"<title>ok</title>"
    assert fetch._decompress(b"plain", "") == b"plain"


def test_scan_folder(server):
    _, folder = server
    site = crawl.scan_folder(folder, "https://nexika.dev")
    assert sorted(pg.url for pg in site.pages) == ["https://nexika.dev/", "https://nexika.dev/docs/",
                                                    "https://nexika.dev/private/"]
    assert site.sitemap_urls is None and site.llms_txt is None


# ---------------------------------------------------------------- frameworks


@pytest.mark.parametrize(("files", "expected"), [
    ({"package.json": '{"dependencies": {"next": "15"}}', "app/layout.tsx": ""}, ("nextjs", "app router")),
    ({"package.json": '{"dependencies": {"astro": "5"}}'}, ("astro", "")),
    ({"package.json": '{"dependencies": {"react": "19", "vite": "6"}}'}, ("spa", "client-rendered single-page app")),
    ({"Web/Web.csproj": '<Project Sdk="Microsoft.NET.Sdk.Web"></Project>', "Web/Pages/Shared/_Layout.cshtml": ""},
     ("aspnet", "razor pages / mvc")),
    ({"_config.yml": "title: x"}, ("jekyll", "GitHub Pages / Jekyll")),
    ({"docs/index.html": "<html></html>"}, ("static", "plain HTML")),
    ({"README.md": "x"}, ("unknown", "")),
])
def test_framework_detection(tmp_path, files, expected):
    for rel, text in files.items():
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text(text)
    found = framework.detect(tmp_path)
    assert (found["framework"], found["variant"]) == expected
    if found["framework"] == "aspnet":
        assert found["where"] == "Web/Pages/Shared/_Layout.cshtml"


# ---------------------------------------------------------------- AI visibility


def fake_post(response):
    calls = []

    def post(url, headers, body):
        calls.append((url, headers, body))
        return response
    return post, calls


def test_engine_parsers():
    post, calls = fake_post({"candidates": [{"content": {"parts": [{"text": "Try Nexika."}]},
                                             "groundingMetadata": {"groundingChunks": [
                                                 {"web": {"uri": "https://vertexaisearch/x", "title": "github.com"}}],
                                                 "groundingSupports": [{"groundingChunkIndices": [0]}]}}]})
    ans = visibility.ask_gemini("q", "K", "m", post, resolve=lambda url: None)   # unresolved: the title
    assert ans.text == "Try Nexika." and "github.com" in ans.citations
    assert calls[0][1] == {"x-goog-api-key": "K"} and calls[0][2]["tools"] == [{"google_search": {}}]
    post, _ = fake_post({"choices": [{"message": {"content": "A"}}], "citations": ["https://a.com"],
                         "search_results": [{"url": "https://b.com"}]})
    assert visibility.ask_perplexity("q", "K", "sonar", post).citations == ["https://a.com"]
    post, _ = fake_post({"output": [{"type": "message", "content": [{"text": "B", "annotations": [
        {"type": "url_citation", "url": "https://c.com"}]}]}]})
    assert visibility.ask_openai("q", "K", "m", post).citations == ["https://c.com"]
    post, _ = fake_post({"content": [{"type": "web_search_tool_result", "content": [{"url": "https://d.com"}]},
                                     {"type": "text", "text": "C", "citations": [{"url": "https://e.com"}]}]})
    ans = visibility.ask_anthropic("q", "K", "m", post)
    assert ans.text == "C" and ans.citations == ["https://e.com"]


def test_mentions_and_citations():
    assert visibility.mentions("Use NEXIKA today", ["Nexika"]) and not visibility.mentions("nexikaX", ["Nexika"])
    assert visibility.is_cited(["https://x.com", "https://github.com/nexika/nexika#readme"],
                               ["https://github.com/nexika/nexika"]) == 2
    assert visibility.available({"GEMINI_API_KEY": "k", "MANAR_GEMINI_MODEL": "g"}) == {"gemini": ("k", "g")}


def test_run_report_and_ledger(tmp_path):
    panel = visibility.panel_template("Nexika", ["github.com/nexika"])
    panel["samples"] = 2

    def ok(prompt, key, model):
        return visibility.Answer("Nexika is great", ["https://github.com/nexika/nexika", "https://other.dev/x"])

    def broken(prompt, key, model):
        raise RuntimeError("HTTP 429: quota")

    records = visibility.run(panel, {"gemini": ("k", "m"), "openai": ("k", "m")},
                             ask={"gemini": ok, "openai": broken}, ref="amin-v0.1.0")
    assert len(records) == 12 and sum(r["cited"] for r in records) == 6
    text = visibility.report(records, domains=["github.com/nexika"])
    assert "gemini      mentioned in 100% of answers, cited (linked) in 100%" in text
    assert "openai      all calls failed: HTTP 429: quota" in text and "other.dev 6" in text
    ledger = tmp_path / "v.jsonl"
    visibility.save(ledger, records)
    assert len(visibility.load_runs(ledger)) == 1


# ---------------------------------------------------------------- CLI


def test_cli_audit_diff_generate_visibility(server, tmp_path, monkeypatch, capsys):
    _, folder = server
    monkeypatch.setattr(cli, "project_root", lambda: tmp_path)
    assert cli.main(["audit", str(folder), "--base-url", "https://nexika.dev"]) == 0
    out = capsys.readouterr().out
    assert "manar audit: https://nexika.dev  (3 pages)" in out and "checklist score:" in out
    (folder / "sitemap.xml").write_text(generate.sitemap_xml(["https://nexika.dev/"]))
    cli.main(["audit", str(folder), "--base-url", "https://nexika.dev"])
    capsys.readouterr()
    assert cli.main(["diff"]) == 0 and "sitemap-missing" in capsys.readouterr().out.split("fixed")[1]
    assert cli.main(["generate", "schema", "website", "name=Nexika", "url=https://nexika.dev"]) == 0
    assert '"@type": "WebSite"' in capsys.readouterr().out
    for var in ("GEMINI_API_KEY", "PERPLEXITY_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    assert cli.main(["visibility", "init"]) == 0
    capsys.readouterr()
    assert cli.main(["visibility", "run"]) == 1 and "no AI engine key set" in capsys.readouterr().out
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    assert cli.main(["visibility", "plan"]) == 0 and "= 9 API calls" in capsys.readouterr().out
    assert cli.main(["visibility", "run", "--max-calls", "5"]) == 1
    assert "exceeds --max-calls 5" in capsys.readouterr().out
    assert json.loads((tmp_path / ".manar" / "panel.json").read_text())["brand"] == tmp_path.name
    assert (tmp_path / ".manar" / ".gitignore").read_text() == "audits/\n"   # crawled data stays out of git


# ---------------------------------------------------------------- regressions from the itqan review


def test_decompression_is_capped():
    bomb = gzip.compress(b"\0" * (fetch.MAX_BYTES * 4))
    assert len(fetch._decompress(bomb, "gzip")) == fetch.MAX_BYTES


def test_hostile_pages_do_not_crash():
    assert fetch._text(b"caf\xc3\xa9", "no-such-charset") == "café"
    deep = '<script type="application/ld+json">' + "[" * 200_000 + "]" * 200_000 + "</script>"
    assert page.parse(deep, "https://x/").jsonld_errors
    odd = p('<script type="application/ld+json">{"@context": "https://schema.org", "@type": 5}</script>')
    assert odd.jsonld_types() == set()
    with pytest.raises(ValueError, match="DTD"):
        checks.parse_sitemap('<!DOCTYPE x [<!ENTITY a "aaaa">]><urlset><url><loc>&a;</loc></url></urlset>')


def test_private_shared_and_multicast_addresses_are_blocked():
    import ipaddress
    for ip in ("100.64.0.1", "169.254.169.254", "127.0.0.1", "10.0.0.1", "224.0.0.1", "0.0.0.0"):
        assert fetch._blocked(ipaddress.ip_address(ip)), ip
    assert not fetch._blocked(ipaddress.ip_address("93.184.216.34"))


def test_crawl_follows_a_redirect_to_another_host(tmp_path):
    class Handler(http.server.SimpleHTTPRequestHandler):
        def do_GET(self):
            if self.headers["Host"].startswith("127.0.0.1"):
                self.send_response(301)
                self.send_header("Location", f"http://localhost:{self.server.server_address[1]}{self.path}")
                self.end_headers()
                return
            super().do_GET()

    (tmp_path / "index.html").write_text('<html><body><a href="/b.html">b</a></body></html>')
    (tmp_path / "b.html").write_text("<html><body>b</body></html>")
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Handler, directory=str(tmp_path)))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        site = crawl.crawl(f"http://127.0.0.1:{httpd.server_address[1]}/", allow_local=True, delay=0)
    finally:
        httpd.shutdown()
    assert site.origin.startswith("http://localhost:") and len(site.pages) == 2


def test_git_credentials_never_reach_the_panel():
    assert cli.repo_domain("https://user:ghp_secret@github.com/o/r.git\n") == "github.com/o/r"
    assert cli.repo_domain("git@github.com:o/r.git") == "github.com/o/r"


def test_citations_match_exact_hosts_and_paths():
    assert visibility.is_cited(["https://notnexika.dev/x"], ["nexika.dev"]) is None
    assert visibility.is_cited(["https://docs.nexika.dev/x"], ["nexika.dev"]) == 1
    assert visibility.is_cited(["https://github.com/o/nexika-fork"], ["github.com/o/nexika"]) is None
    assert visibility.is_cited(["https://github.com/o/nexika/tree/main"], ["github.com/o/nexika"]) == 1


def test_generated_markup_cannot_break_out_of_script_or_markdown():
    script = generate.jsonld_script(generate.schema("website", name="</script><script>alert(1)</script>",
                                                    url="https://x"))
    assert script.count("</script>") == 1
    hostile = p("<html><head><title>Hi](http://evil)\n# injected</title></head><body>x</body></html>")
    text = generate.llms_txt("N", "S", crawl.Site("https://x", [hostile]))
    assert "\n# injected" not in text and "](http://evil)" not in text


# ---------------------------------------------------------------- issue #41: hreflang and canonicals


def _alt_page(url, lang, alternates, canonical=None):
    links = "".join(f'<link rel="alternate" hreflang="{code}" href="{href}">' for code, href in alternates)
    return p(f'<html lang="{lang}"><head><link rel="canonical" href="{canonical or url}">{links}</head>'
             f'<body>x</body></html>', url)


HREFLANG_IDS = {"hreflang-invalid-code", "hreflang-relative", "hreflang-other-host", "hreflang-no-x-default"}


def test_hreflang_codes_urls_and_x_default_are_checked():
    pg = _alt_page("https://x.dev/ar/", "ar", [("arabic", "https://x.dev/ar/"), ("en", "/en/"),
                                               ("fr", "https://other.dev/fr/")])
    assert HREFLANG_IDS <= {f.id for f in checks.page_checks(pg)}
    ok = _alt_page("https://x.dev/ar/", "ar", [("ar", "https://x.dev/ar/"), ("en-GB", "https://x.dev/en/"),
                                               ("x-default", "https://x.dev/en/")])
    assert not {f.id for f in checks.page_checks(ok)} & HREFLANG_IDS


def test_canonical_to_another_language_or_page_is_flagged():
    # the Arabic page says its canonical is the English home: search engines drop the Arabic page
    ar = _alt_page("https://x.dev/ar/", "ar", [("ar", "https://x.dev/ar/"), ("en", "https://x.dev/"),
                                               ("x-default", "https://x.dev/")], canonical="https://x.dev/")
    assert "canonical-other-language" in {f.id for f in checks.page_checks(ar)}
    other = _alt_page("https://x.dev/blog/a", "en", [], canonical="https://x.dev/blog/")
    assert "canonical-other-page" in {f.id for f in checks.page_checks(other)}
    same = _alt_page("https://x.dev/blog/a?utm=1", "en", [], canonical="https://x.dev/blog/a/")
    assert not {f.id for f in checks.page_checks(same)} & {"canonical-other-page", "canonical-other-language"}


def test_hreflang_return_links_and_targets_are_checked_across_pages():
    en = _alt_page("https://x.dev/", "en", [("en", "https://x.dev/"), ("ar", "https://x.dev/ar/"),
                                            ("fr", "https://x.dev/fr/"), ("x-default", "https://x.dev/")])
    ar = _alt_page("https://x.dev/ar/", "ar", [("ar", "https://x.dev/ar/"), ("x-default", "https://x.dev/")])
    fr = page.parse("<html><body>gone</body></html>", "https://x.dev/fr/", status=404)
    found = {(f.id, f.url) for f in checks.site_checks("https://x.dev", en, None, None, "", None, [en, ar, fr])}
    assert ("hreflang-no-return", "https://x.dev/") in found
    assert ("hreflang-broken-target", "https://x.dev/") in found


# ---------------------------------------------------------------- issue #42: numbers that support before/after


def _records(cited_prompts, prompts=10, samples=3, model="m", engine="gemini", run="r"):
    return [{"run": run, "ref": "v1", "engine": engine, "model": model, "prompt": f"q{i}", "lang": "en",
             "sample": s, "mentioned": i < cited_prompts, "cited": i < cited_prompts, "position": None,
             "citations": [], "error": ""} for i in range(prompts) for s in range(samples)]


def test_wilson_interval():
    lo, hi = visibility.wilson(6, 30)
    assert 0.09 < lo < 0.11 and 0.37 < hi < 0.40
    assert visibility.wilson(0, 0) == (0.0, 1.0)


def test_report_shows_ranges_and_only_compares_like_with_like():
    # 2 of 10 prompts cited, 3 correlated samples each: the range is wide, and it says so
    text = visibility.report(_records(2))
    assert "10 prompts" in text and "95% range" in text
    # a run with another model is not a before/after
    text = visibility.report(_records(2), _records(5, model="other"))
    assert "not comparable" in text and "model" in text
    text = visibility.report(_records(2), _records(5, prompts=9))
    assert "not comparable" in text and "prompts" in text
    # same setup: a small change is within noise, a large one is a real change
    assert "within noise" in visibility.report(_records(3), _records(2))
    assert "real change" in visibility.report(_records(9), _records(0))


# ---------------------------------------------------------------- issue #62: one meaning of "cited"


def test_cited_means_linked_in_the_answer_for_every_engine():
    # sources an engine only retrieved are not citations, for any engine
    post, _ = fake_post({"choices": [{"message": {"content": "A [1]"}}], "citations": ["https://a.com"],
                         "search_results": [{"url": "https://a.com"}, {"url": "https://b.com"}]})
    ans = visibility.ask_perplexity("q", "K", "sonar", post)
    assert ans.citations == ["https://a.com"] and "https://b.com" in ans.retrieved
    post, _ = fake_post({"content": [{"type": "web_search_tool_result", "content": [{"url": "https://d.com"}]},
                                     {"type": "text", "text": "C", "citations": [{"url": "https://e.com"}]}]})
    ans = visibility.ask_anthropic("q", "K", "m", post)
    assert ans.citations == ["https://e.com"] and ans.retrieved == ["https://d.com"]
    post, _ = fake_post({"candidates": [{"content": {"parts": [{"text": "Use X."}]}, "groundingMetadata": {
        "groundingChunks": [{"web": {"uri": "https://vertexaisearch.cloud.google.com/grounding-api-redirect/1",
                                     "title": "github.com"}},
                            {"web": {"uri": "https://vertexaisearch.cloud.google.com/grounding-api-redirect/2",
                                     "title": "other.dev"}}],
        "groundingSupports": [{"segment": {"text": "Use X."}, "groundingChunkIndices": [0]}]}}]})
    resolved = {"https://vertexaisearch.cloud.google.com/grounding-api-redirect/1": "https://github.com/o/nexika/blob/main/README.md"}
    ans = visibility.ask_gemini("q", "K", "m", post, resolve=resolved.get)
    # the redirect is resolved, so a path-scoped domain (github.com/o/nexika) can match
    assert ans.citations == ["https://github.com/o/nexika/blob/main/README.md"]
    assert visibility.is_cited(ans.citations, ["github.com/o/nexika"]) == 1
    assert "other.dev" in ans.retrieved


def test_plan_shows_a_cost_estimate(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "project_root", lambda: tmp_path)
    for var in ("GEMINI_API_KEY", "PERPLEXITY_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    cli.main(["visibility", "init"])
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    capsys.readouterr()
    assert cli.main(["visibility", "plan"]) == 0
    out = capsys.readouterr().out
    assert "= 9 API calls" in out and "about $" in out and "estimate" in out


# ---------------------------------------------------------------- issue #84: diff, robots paths, base URL


def test_diff_compares_audits_of_the_same_site(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "project_root", lambda: tmp_path)
    folder = tmp_path / ".manar" / "audits"
    folder.mkdir(parents=True)

    def audit(name, target, score, ids):
        (folder / name).write_text(json.dumps({"target": target, "score": score, "date": "2026-10-07T10:00:00",
                                               "site": [{"id": i, "url": target} for i in ids], "pages": []}))
    audit("1-a.json", "https://a.dev", 50, ["sitemap-missing"])
    audit("2-b.json", "https://b.dev", 90, [])
    audit("3-a.json", "https://a.dev", 60, [])
    assert cli.main(["diff"]) == 0
    out = capsys.readouterr().out
    assert "score 50 -> 60" in out and "https://a.dev" in out
    audit("4-b.json", "https://b.dev", 95, [])
    assert cli.main(["diff", "https://a.dev"]) == 0 and "score 50 -> 60" in capsys.readouterr().out


def test_robots_blocking_a_section_for_ai_search_is_reported():
    robots = "User-agent: OAI-SearchBot\nDisallow: /docs/\n\nUser-agent: *\nAllow: /\nSitemap: https://x.dev/s.xml\n"
    home = p(GOOD, "https://x.dev/")
    docs = p(GOOD, "https://x.dev/docs/guide")
    findings = checks.site_checks("https://x.dev", home, robots, ["https://x.dev/"], "", None, [home, docs])
    blocked = [f for f in findings if f.id == "robots-blocks-ai-search-paths"]
    assert blocked and "OAI-SearchBot" in blocked[0].message and "/docs/" in blocked[0].message
    assert "robots-blocks-ai-search" not in {f.id for f in findings}


def test_folder_base_url_is_inferred_or_required(tmp_path):
    (tmp_path / "index.html").write_text('<html><head><link rel="canonical" href="https://nexika.dev/">'
                                         "</head><body>x</body></html>")
    assert crawl.scan_folder(tmp_path).origin == "https://nexika.dev"
    (tmp_path / "CNAME").write_text("docs.nexika.dev\n")
    assert crawl.scan_folder(tmp_path).origin == "https://docs.nexika.dev"
    bare = tmp_path / "bare"
    bare.mkdir()
    (bare / "index.html").write_text("<html><body>x</body></html>")
    with pytest.raises(ValueError, match="--base-url"):
        crawl.scan_folder(bare)


def test_arabic_passages_are_not_scored_lower_for_having_no_capital_letters():
    english = ("Riyadh Metro is a network of six lines that opened in 2024 and carries 3.6 million riders "
               "a day across 85 stations, run by the Royal Commission for Riyadh City.")
    arabic = ("مترو الرياض هو شبكة من ست خطوط افتتحت في 2024 وتنقل 3.6 مليون راكب يوميًا عبر 85 محطة، "
              "وتديرها الهيئة الملكية لمدينة الرياض بعد سنوات من البناء والتجارب.")
    gap = citability.block_score("What is Riyadh Metro?", english)[0] - \
        citability.block_score("ما هو مترو الرياض؟", arabic)[0]
    assert abs(gap) <= 2    # was 10: the Arabic passage could never earn the "names" points


# ---------------------------------------------------------------- issue #74: links, schema, CI mode


def test_broken_internal_links_and_sitemap_gaps(tmp_path):
    (tmp_path / "index.html").write_text('<html><body><a href="/docs/">d</a> <a href="/gone/">g</a>'
                                         '<a href="/logo.png">l</a><a href="https://elsewhere.dev/x">e</a></body></html>')
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "index.html").write_text("<html><body>docs</body></html>")
    (tmp_path / "sitemap.xml").write_text(generate.sitemap_xml(["https://x.dev/"]))
    site = crawl.scan_folder(tmp_path, "https://x.dev")
    found = {(f.id, f.url): f for f in checks.site_checks(site.origin, site.home, site.robots_txt, site.sitemap_urls,
                                                          site.sitemap_error, site.llms_txt, site.pages,
                                                          complete=site.complete)}
    broken = found[("broken-internal-link", "https://x.dev/")]
    assert "/gone/" in broken.message and "/docs/" not in broken.message and "logo" not in broken.message
    assert "https://x.dev/docs/" in found[("sitemap-gaps", "https://x.dev")].message
    # a crawled 404 is broken even when the crawl was partial
    home = p('<html><body><a href="/old">o</a></body></html>', "https://x.dev/")
    old = page.parse("<html></html>", "https://x.dev/old", status=404)
    ids = {f.id for f in checks.site_checks("https://x.dev", home, None, None, "", None, [home, old])}
    assert "broken-internal-link" in ids


def test_required_schema_properties_per_type():
    article = p('<html><head><script type="application/ld+json">{"@context":"https://schema.org",'
                '"@type":"Article","headline":"H"}</script></head><body>x</body></html>')
    msgs = [f.message for f in checks.page_checks(article) if f.id == "schema-missing-property"]
    assert msgs and "Article" in msgs[0] and "author" in msgs[0] and "datePublished" in msgs[0]
    graph = p('<html><head><script type="application/ld+json">{"@context":"https://schema.org","@graph":['
              '{"@type":"Organization","name":"N","url":"https://n.dev"},{"@type":"FAQPage"}]}</script></head>'
              "<body>x</body></html>")
    msgs = [f.message for f in checks.page_checks(graph) if f.id == "schema-missing-property"]
    assert len(msgs) == 1 and "FAQPage" in msgs[0] and "mainEntity" in msgs[0]
    assert "schema-missing-property" not in {f.id for f in checks.page_checks(p(GOOD))}


def test_audit_fail_on_sets_the_exit_code(server, tmp_path, monkeypatch, capsys):
    _, folder = server
    monkeypatch.setattr(cli, "project_root", lambda: tmp_path)
    args = ["audit", str(folder), "--base-url", "https://nexika.dev"]
    assert cli.main(args) == 0
    assert cli.main([*args, "--fail-on", "low"]) == 1
    assert "fail-on low" in capsys.readouterr().out
    assert cli.main([*args, "--fail-on", "critical"]) == 0
    assert cli.main([*args, "--fail-on", "bogus"]) == 2
