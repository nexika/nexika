"""Deterministic checks. Every finding says what is wrong, why it matters, and how to fix it."""
from __future__ import annotations

import urllib.parse
import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import asdict, dataclass

from . import aibots
from .page import Page

WEIGHT = {"critical": 15, "high": 8, "medium": 3, "low": 1}
ORDER = list(WEIGHT)


@dataclass
class Finding:
    id: str
    severity: str
    category: str
    message: str
    fix: str
    url: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------- pages


def page_checks(p: Page) -> list[Finding]:
    out: list[Finding] = []

    def add(fid, sev, cat, msg, fix):
        out.append(Finding(fid, sev, cat, msg, fix, p.url))

    if p.status >= 400:
        add("http-error", "critical", "technical", f"returns HTTP {p.status}",
            "fix the page or remove the links pointing to it")
        return out
    robots_meta = f"{p.meta.get('robots', '')} {p.meta.get('googlebot', '')}".lower()
    if "noindex" in robots_meta:
        add("noindex", "critical", "indexing", "the page tells search engines not to index it (noindex)",
            "remove noindex if this page should appear in search and AI answers")
    if not p.title:
        add("title-missing", "high", "content", "no <title>", "add a unique title of 30-60 characters "
            "that names the page's topic")
    elif len(p.title) < 20:
        add("title-short", "medium", "content", f"title is very short ({len(p.title)} chars): {p.title!r}",
            "describe the page in 30-60 characters, main keyword first")
    elif len(p.title) > 65:
        add("title-long", "low", "content", f"title is {len(p.title)} chars; search results cut it",
            "keep titles under ~60 characters")
    desc = p.meta.get("description", "")
    if not desc:
        add("description-missing", "medium", "content", "no meta description",
            "add a 70-160 character summary; search engines and AI tools often show it")
    elif not 70 <= len(desc) <= 170:
        add("description-length", "low", "content", f"meta description is {len(desc)} chars",
            "aim for 70-160 characters")
    h1 = [h for lvl, h in p.headings if lvl == 1]
    if not h1:
        add("h1-missing", "medium", "content", "no <h1>", "add one <h1> stating what the page is about")
    elif len(h1) > 1:
        add("h1-multiple", "low", "content", f"{len(h1)} <h1> headings",
            "use a single <h1>; use <h2> below it")
    if not p.canonical:
        add("canonical-missing", "medium", "indexing", "no canonical URL",
            'add <link rel="canonical" href="..."> with the preferred absolute URL')
    elif urllib.parse.urlsplit(p.canonical).netloc.lower() != urllib.parse.urlsplit(p.url).netloc.lower():
        add("canonical-other-host", "medium", "indexing", f"canonical points to another site: {p.canonical}",
            "make sure this is intended; otherwise point it to this page")
    if not p.lang:
        add("lang-missing", "medium", "international", "no lang attribute on <html>",
            'set <html lang="en"> (or "ar" with dir="rtl" for Arabic) so engines know the language')
    elif p.lang.lower().startswith("ar") and p.dir.lower() != "rtl":
        add("rtl-missing", "low", "international", 'Arabic page without dir="rtl"', 'add dir="rtl" to <html>')
    if "viewport" not in p.meta:
        add("viewport-missing", "medium", "technical", "no viewport meta (not mobile friendly)",
            '<meta name="viewport" content="width=device-width, initial-scale=1">')
    missing_og = [k for k in ("og:title", "og:description", "og:image") if k not in p.meta]
    if missing_og:
        add("open-graph", "low", "social", f"missing {', '.join(missing_og)}",
            "add Open Graph tags so shared links and AI tools show a proper title, summary and image")
    no_alt = [src for src, alt in p.images if alt is None]
    if no_alt:
        add("img-alt", "low" if len(no_alt) < 3 else "medium", "accessibility",
            f"{len(no_alt)} image(s) without alt text",
            'describe each image in alt (alt="" for decorative ones)')
    for err in p.jsonld_errors:
        add("jsonld-invalid", "high", "structured-data", err, "fix the JSON in the ld+json script")
    for item in p.jsonld:
        if isinstance(item, dict) and ("@context" not in item or "@type" not in item):
            add("jsonld-incomplete", "medium", "structured-data", "JSON-LD item without @context or @type",
                'every top-level item needs "@context": "https://schema.org" and "@type"')
    if p.words < 50 and p.scripts >= 3:
        add("client-rendered", "high", "technical",
            f"only {p.words} words in the raw HTML but {p.scripts} scripts: "
            "content seems rendered by JavaScript",
            "crawlers and AI fetchers often don't run JavaScript: render on the server or pre-render (SSG)")
    elif p.words < 150:
        add("thin-content", "medium", "content", f"only {p.words} words of main content",
            "pages that answer a question clearly, with specifics, are the ones that get cited")
    return out


# ---------------------------------------------------------------- site


def parse_sitemap(xml_text: str) -> tuple[list[str], list[str]]:
    """(page URLs, child sitemap URLs) from a sitemap or sitemap index (untrusted XML: no DTDs)."""
    if "<!doctype" in xml_text.lower() or "<!entity" in xml_text.lower():
        raise ValueError("sitemap contains a DTD/entity declaration; refused")
    root = ET.fromstring(xml_text)
    tag = root.tag.rsplit("}", 1)[-1]
    locs = [el.text.strip() for el in root.iter() if el.tag.rsplit("}", 1)[-1] == "loc" and el.text]
    return ([], locs) if tag == "sitemapindex" else (locs, [])


def validate_llms(text: str) -> list[str]:
    """Problems with an llms.txt (https://llmstxt.org): H1 first, optional > summary, ## link lists."""
    lines = [ln for ln in text.splitlines() if ln.strip()]
    problems = []
    if not lines or not lines[0].startswith("# "):
        problems.append("the first line must be an H1 with the site or project name ('# Name')")
    if not any(ln.startswith("> ") for ln in lines[:4]):
        problems.append("no '> summary' line under the title")
    if not any(ln.startswith("## ") for ln in lines):
        problems.append("no '## Section' headings")
    if not any("](" in ln and ln.lstrip().startswith("- [") for ln in lines):
        problems.append("no '- [title](url): description' links")
    return problems


def site_checks(origin: str, home: Page | None, robots_txt: str | None, sitemap_urls: list[str] | None,
                sitemap_error: str, llms_txt: str | None, pages: list[Page]) -> list[Finding]:
    out: list[Finding] = []

    def add(fid, sev, cat, msg, fix):
        out.append(Finding(fid, sev, cat, msg, fix, origin))

    if origin.startswith("http://"):
        add("no-https", "high", "technical", "site is served over http", "serve everything over https")
    allowed = aibots.access(robots_txt)
    if robots_txt is None:
        add("robots-missing", "low", "indexing", "no robots.txt (everything allowed)",
            "add one with a Sitemap line (manar generate robots)")
    else:
        if not allowed.get("Googlebot", True):
            add("robots-blocks-google", "critical", "indexing", "robots.txt blocks Googlebot from the site",
                "allow Googlebot unless the site must stay out of Google")
        blocked = [b.name for b in aibots.blocked_for_visibility(allowed) if b.name != "Googlebot"]
        if blocked:
            add("robots-blocks-ai-search", "high", "ai-visibility",
                f"robots.txt blocks AI search/assistant crawlers: {', '.join(blocked)}",
                "allow them so AI answers can read and cite the site (training bots can stay blocked)")
        if "sitemap:" not in robots_txt.lower():
            add("robots-no-sitemap", "low", "indexing", "robots.txt has no Sitemap line",
                "add 'Sitemap: <absolute URL of sitemap.xml>'")
    if sitemap_error:
        add("sitemap-invalid", "medium", "indexing", f"sitemap problem: {sitemap_error}",
            "publish a valid sitemap.xml listing every page (manar generate sitemap)")
    elif sitemap_urls is None:
        add("sitemap-missing", "medium", "indexing", "no sitemap.xml found",
            "publish sitemap.xml and reference it from robots.txt (manar generate sitemap)")
    elif not sitemap_urls:
        add("sitemap-empty", "medium", "indexing", "sitemap.xml lists no pages", "list every indexable page")
    if llms_txt is None:
        add("llms-missing", "low", "ai-visibility", "no /llms.txt",
            "optional and unproven for ranking, but it gives AI agents a clean map of the site "
            "(manar generate llms)")
    else:
        for problem in validate_llms(llms_txt):
            add("llms-format", "low", "ai-visibility", f"llms.txt: {problem}", "follow https://llmstxt.org")
    if home is not None:
        types = home.jsonld_types()
        if not types & {"Organization", "WebSite", "SoftwareApplication", "Person", "LocalBusiness"}:
            add("entity-schema-missing", "medium", "structured-data",
                "home page has no Organization / WebSite / SoftwareApplication JSON-LD",
                "describe who you are in JSON-LD so engines connect the site to one clear entity "
                "(manar generate schema)")
        orgs = [i for i in home.jsonld if isinstance(i, dict) and i.get("@type") == "Organization"]
        if orgs and not any(o.get("sameAs") for o in orgs):
            add("entity-no-sameas", "low", "structured-data", "Organization has no sameAs links",
                "list official profiles (GitHub, LinkedIn, X...) in sameAs: it ties mentions to you")
    titles = Counter(p.title for p in pages if p.title and p.status < 400)
    dupes = [t for t, n in titles.items() if n > 1]
    if dupes:
        add("duplicate-titles", "medium", "content",
            f"{len(dupes)} title(s) used on several pages: {dupes[0]!r}",
            "give every page its own title")
    return out


def score(site: list[Finding], per_page: list[list[Finding]]) -> int:
    """A checklist score (100 = no known problems). Not a prediction of rankings."""
    site_penalty = sum(WEIGHT[f.severity] for f in site)
    page_totals = [sum(WEIGHT[f.severity] for f in fs) for fs in per_page]
    page_penalty = sum(page_totals) / len(page_totals) if page_totals else 0
    return max(0, round(100 - site_penalty - page_penalty))
