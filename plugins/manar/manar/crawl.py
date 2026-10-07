"""Collect a site: crawl it over HTTP (bounded, same host, polite) or read a built folder offline."""
from __future__ import annotations

import time
import urllib.parse
import urllib.robotparser
from dataclasses import dataclass, field
from pathlib import Path

from . import USER_AGENT, fetch, page
from .checks import parse_sitemap

SKIP_DIRS = {"node_modules", ".git", ".next", ".astro", "bin", "obj"}
NON_HTML = (".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".pdf", ".zip", ".css", ".js", ".json", ".xml",
            ".ico", ".mp4", ".woff", ".woff2")


@dataclass
class Site:
    origin: str
    pages: list[page.Page] = field(default_factory=list)
    robots_txt: str | None = None
    sitemap_urls: list[str] | None = None
    sitemap_error: str = ""
    llms_txt: str | None = None
    skipped: list[str] = field(default_factory=list)   # robots-disallowed or failed, with reason

    @property
    def home(self) -> page.Page | None:
        for p in self.pages:
            if urllib.parse.urlsplit(p.url).path in ("", "/", "/index.html"):
                return p
        return self.pages[0] if self.pages else None


def _clean(url: str) -> str:
    return urllib.parse.urldefrag(url)[0]


def _same_site(url: str, origin: str) -> bool:
    return fetch.origin(url) == origin and not urllib.parse.urlsplit(url).path.lower().endswith(NON_HTML)


def _text_or_none(url: str, allow_local: bool) -> str | None:
    try:
        resp = fetch.get(url, allow_local=allow_local, accept="text/plain,*/*;q=0.5")
    except fetch.FetchError:
        return None
    return resp.body if resp.status == 200 else None


def crawl(start: str, max_pages: int = 50, allow_local: bool = False, delay: float = 0.2) -> Site:
    try:
        first = fetch.get(start, allow_local=allow_local)
    except fetch.FetchError as exc:
        site = Site(fetch.origin(start))
        site.skipped.append(f"{start} ({exc})")
        return site
    origin = fetch.origin(first.url)   # follow example.com -> www.example.com
    site = Site(origin)
    site.robots_txt = _text_or_none(f"{origin}/robots.txt", allow_local)
    rules = urllib.robotparser.RobotFileParser()
    rules.parse((site.robots_txt or "").splitlines())

    declared = [ln.split(":", 1)[1].strip() for ln in (site.robots_txt or "").splitlines()
                if ln.lower().startswith("sitemap:")]
    # only the audited site's own sitemaps: robots.txt must not send the crawler elsewhere
    sitemap_locs = [u for u in declared if fetch.origin(u) == origin] or [f"{origin}/sitemap.xml"]
    collected: list[str] = []
    for loc in sitemap_locs[:3]:
        xml_text = _text_or_none(loc, allow_local)
        if xml_text is None:
            continue
        try:
            pages, children = parse_sitemap(xml_text)
            for child in [c for c in children if fetch.origin(c) == origin][:10]:
                child_xml = _text_or_none(child, allow_local)
                if child_xml:
                    pages += parse_sitemap(child_xml)[0]
            collected += pages
            site.sitemap_urls = collected
        except Exception as exc:  # malformed XML of any kind
            site.sitemap_error = f"{loc}: {exc}"
    site.llms_txt = _text_or_none(f"{origin}/llms.txt", allow_local)

    queue = [_clean(first.url)] + [_clean(u) for u in collected if _same_site(u, origin)]
    seen: set[str] = set()
    attempts = 0
    while queue and len(site.pages) < max_pages and attempts < max_pages * 2:
        url = queue.pop(0)
        if url in seen:
            continue
        seen.add(url)
        if not rules.can_fetch(USER_AGENT, url):
            site.skipped.append(f"{url} (disallowed by robots.txt)")
            continue
        attempts += 1
        try:
            resp = first if url == _clean(first.url) else fetch.get(url, allow_local=allow_local)
        except fetch.FetchError as exc:
            site.skipped.append(f"{url} ({exc})")
            continue
        if "html" not in resp.content_type and resp.status < 400:
            continue
        parsed = page.parse(resp.body, resp.url, resp.status)
        site.pages.append(parsed)
        for href, _ in parsed.links:
            href = _clean(href)
            if _same_site(href, origin) and href not in seen:
                queue.append(href)
        if delay:
            time.sleep(delay)
    return site


def infer_base_url(folder: Path) -> str | None:
    """The site's address from a built folder: a CNAME file (GitHub Pages), else the home page's
    canonical or og:url."""
    cname = folder / "CNAME"
    if cname.is_file():
        host = cname.read_text(encoding="utf-8", errors="replace").strip().splitlines()
        if host and host[0].strip():
            return "https://" + host[0].strip().removeprefix("https://").removeprefix("http://").rstrip("/")
    index = folder / "index.html"
    if index.is_file():
        home = page.parse(index.read_text(encoding="utf-8", errors="replace"), "https://placeholder.invalid/")
        for url in (home.canonical, home.meta.get("og:url", "")):
            parts = urllib.parse.urlsplit(url)
            if parts.scheme in ("http", "https") and parts.netloc and parts.netloc != "placeholder.invalid":
                return f"{parts.scheme}://{parts.netloc}"
    return None


def scan_folder(folder: Path, base_url: str | None = None) -> Site:
    """A built site on disk (dist/, _site/, out/, wwwroot/): no network needed. Without base_url the
    address is inferred; a wrong guess would turn every canonical into a false warning, so no guess
    means an error."""
    base_url = base_url or infer_base_url(folder)
    if not base_url:
        raise ValueError(f"can't tell the address of the site in {folder}: pass --base-url https://your.site")
    base_url = base_url.rstrip("/")
    site = Site(base_url)
    robots = folder / "robots.txt"
    site.robots_txt = robots.read_text(encoding="utf-8", errors="replace") if robots.is_file() else None
    sitemap = folder / "sitemap.xml"
    if sitemap.is_file():
        try:
            site.sitemap_urls = parse_sitemap(sitemap.read_text(encoding="utf-8", errors="replace"))[0]
        except Exception as exc:
            site.sitemap_error = f"sitemap.xml: {exc}"
    llms = folder / "llms.txt"
    site.llms_txt = llms.read_text(encoding="utf-8", errors="replace") if llms.is_file() else None
    files = sorted(p for p in folder.rglob("*.html") if not set(p.relative_to(folder).parts) & SKIP_DIRS)
    for path in files:
        rel = path.relative_to(folder).as_posix()
        if rel.endswith("index.html"):
            rel = rel[: -len("index.html")]
        site.pages.append(page.parse(path.read_text(encoding="utf-8", errors="replace"), f"{base_url}/{rel}"))
    return site
