"""Deterministic checks. Every finding says what is wrong, why it matters, and how to fix it."""
from __future__ import annotations

import re
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

# BCP 47 as hreflang uses it: language, optional script, optional region ("ar", "zh-Hant", "en-GB", "es-419")
HREFLANG_CODE = re.compile(r"^[a-z]{2,3}(?:-[a-z]{4})?(?:-(?:[a-z]{2}|\d{3}))?$", re.I)


def page_key(url: str) -> tuple[str, str]:
    """The same page whatever the scheme, query, fragment, trailing slash or index.html."""
    parts = urllib.parse.urlsplit(url)
    path = re.sub(r"(?:/index)?\.html?$", "", parts.path).rstrip("/")
    return parts.netloc.lower(), path


def same_language(code: str, lang: str) -> bool:
    return bool(lang) and code.lower().split("-")[0] == lang.lower().split("-")[0]


def _hreflang_page(p: Page, add) -> None:
    """hreflang problems visible on one page; return links and targets need the whole crawl."""
    if not p.hreflang_raw:
        return
    bad = [code for code in p.hreflang_raw if code.lower() != "x-default" and not HREFLANG_CODE.match(code)]
    if bad:
        add("hreflang-invalid-code", "medium", "international", f"invalid hreflang code(s): {', '.join(bad)}",
            'use a language code with an optional region, such as "ar", "ar-SA", "en-GB" or "x-default"')
    relative = [href for href in p.hreflang_raw.values() if not re.match(r"https?://", href, re.I)]
    if relative:
        add("hreflang-relative", "medium", "international",
            f"hreflang URL(s) are not absolute: {relative[0]}",
            "hreflang links must be full URLs, including https:// and the host")
    host = urllib.parse.urlsplit(p.url).netloc.lower()
    other = [href for href in p.hreflang.values() if urllib.parse.urlsplit(href).netloc.lower() != host]
    if other:
        add("hreflang-other-host", "low", "international", f"hreflang points to another site: {other[0]}",
            "fine for separate country domains; otherwise point it to this site's language version")
    if "x-default" not in p.hreflang:
        add("hreflang-no-x-default", "low", "international", "hreflang set has no x-default",
            'add <link rel="alternate" hreflang="x-default" href="..."> for visitors in other languages')


def hreflang_site_checks(pages: list[Page]) -> list[Finding]:
    """Return links and alternates that point to broken pages, among the crawled pages."""
    out: list[Finding] = []
    by_key = {page_key(pg.url): pg for pg in pages}
    for pg in pages:
        if pg.status >= 400 or not pg.hreflang:
            continue
        broken, no_return = [], []
        for href in dict.fromkeys(pg.hreflang.values()):
            target = by_key.get(page_key(href))
            if target is None or target is pg:
                continue
            if target.status >= 400:
                broken.append(f"{href} (HTTP {target.status})")
            elif not any(page_key(h) == page_key(pg.url) for code, h in target.hreflang.items()
                         if code != "x-default"):
                no_return.append(href)
        if broken:
            out.append(Finding("hreflang-broken-target", "high", "international",
                               f"hreflang points to a broken page: {', '.join(broken[:3])}",
                               "point hreflang only to live pages", pg.url))
        if no_return:
            out.append(Finding("hreflang-no-return", "medium", "international",
                               f"no return link from {', '.join(no_return[:3])}: search engines ignore "
                               "hreflang pairs that don't link back",
                               "every language version must list all the others, and itself", pg.url))
    return out


FILE_SUFFIX = re.compile(r"\.[a-z0-9]{1,5}$", re.I)


def link_checks(pages: list[Page], complete: bool) -> list[Finding]:
    """Internal links to pages that return an error, or (when every page is known) don't exist."""
    out: list[Finding] = []
    by_key = {page_key(pg.url): pg for pg in pages}
    for pg in pages:
        if pg.status >= 400:
            continue
        host = urllib.parse.urlsplit(pg.url).netloc.lower()
        broken: list[str] = []
        for href, _ in pg.links:
            parts = urllib.parse.urlsplit(href)
            if parts.scheme not in ("http", "https") or parts.netloc.lower() != host:
                continue
            if FILE_SUFFIX.search(parts.path) and not parts.path.lower().endswith((".html", ".htm")):
                continue   # a file (image, PDF, feed), not a page
            target = by_key.get(page_key(href))
            if target is not None and target.status >= 400:
                broken.append(f"{parts.path or '/'} (HTTP {target.status})")
            elif target is None and complete:
                broken.append(f"{parts.path or '/'} (no such page)")
        if broken:
            unique = list(dict.fromkeys(broken))
            out.append(Finding("broken-internal-link", "high" if len(unique) > 2 else "medium", "technical",
                               f"{len(unique)} broken internal link(s): {', '.join(unique[:5])}",
                               "fix or remove links to pages that don't exist", pg.url))
    return out


# What search engines need to use a schema.org type (one of a tuple is enough).
REQUIRED_PROPERTIES: dict[str, list[str | tuple[str, ...]]] = {
    "Article": ["headline", "author", "datePublished"],
    "BlogPosting": ["headline", "author", "datePublished"],
    "NewsArticle": ["headline", "author", "datePublished"],
    "Organization": ["name", "url"],
    "WebSite": ["name", "url"],
    "Person": ["name"],
    "LocalBusiness": ["name", "address"],
    "Product": ["name", ("offers", "review", "aggregateRating")],
    "SoftwareApplication": ["name", ("offers", "aggregateRating", "review")],
    "FAQPage": ["mainEntity"],
    "BreadcrumbList": ["itemListElement"],
    "HowTo": ["name", "step"],
    "Event": ["name", "startDate", "location"],
    "Recipe": ["name", "image"],
    "VideoObject": ["name", "thumbnailUrl", "uploadDate"],
}


def _schema_items(jsonld: list) -> list[dict]:
    items = []
    for item in jsonld:
        if isinstance(item, dict):
            graph = item.get("@graph")
            items += [g for g in graph if isinstance(g, dict)] if isinstance(graph, list) else [item]
    return items


def _schema_missing(p: Page) -> list[str]:
    problems = []
    for item in _schema_items(p.jsonld):
        types = item.get("@type")
        for t in [types] if isinstance(types, str) else types if isinstance(types, list) else []:
            missing = [need if isinstance(need, str) else " or ".join(need)
                       for need in REQUIRED_PROPERTIES.get(t, [])
                       if not any(item.get(k) for k in ((need,) if isinstance(need, str) else need))]
            if missing:
                problems.append(f"{t} without {', '.join(missing)}")
    return problems


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
    elif page_key(p.canonical) != page_key(p.url):
        languages = [code for code, href in p.hreflang.items() if code != "x-default"
                     and page_key(href) == page_key(p.canonical) and not same_language(code, p.lang)]
        if languages:
            add("canonical-other-language", "high", "international",
                f"canonical points to the {languages[0]} version ({p.canonical}): search engines drop "
                "this page and show the other language instead",
                "point each language version's canonical to itself; hreflang links the versions")
        else:
            add("canonical-other-page", "medium", "indexing",
                f"canonical points to another page: {p.canonical}",
                "search engines index the target instead of this page; point it to this page unless "
                "it is a true duplicate")
    _hreflang_page(p, add)
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
    for problem in _schema_missing(p):
        add("schema-missing-property", "medium", "structured-data", f"JSON-LD {problem}",
            "add the properties search engines need for this type (schema.org and Google's "
            "structured data docs list them)")
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
                sitemap_error: str, llms_txt: str | None, pages: list[Page],
                complete: bool = False) -> list[Finding]:
    """`complete`: pages holds every page of the site (a built folder), so a link to anything else is
    broken; a crawl only knows the pages it fetched."""
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
        paths = [urllib.parse.urlsplit(pg.url).path or "/" for pg in pages]
        partly = aibots.blocked_paths(robots_txt, paths)
        partly.pop("Googlebot", None)
        if partly:
            sample = "; ".join(f"{bot}: {', '.join(p[:3])}" for bot, p in list(partly.items())[:4])
            add("robots-blocks-ai-search-paths", "high", "ai-visibility",
                f"robots.txt blocks AI search/assistant crawlers from parts of the site ({sample})",
                "allow these sections unless they must stay out of AI answers")
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
    out += hreflang_site_checks(pages)
    out += link_checks(pages, complete)
    if sitemap_urls:
        listed = {page_key(u) for u in sitemap_urls}
        missing = [pg.url for pg in pages if pg.status < 400 and page_key(pg.url) not in listed
                   and "noindex" not in pg.meta.get("robots", "").lower()]
        if missing:
            add("sitemap-gaps", "low", "indexing",
                f"{len(missing)} page(s) not in the sitemap: {', '.join(missing[:3])}",
                "list every indexable page in sitemap.xml (manar generate sitemap)")
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
