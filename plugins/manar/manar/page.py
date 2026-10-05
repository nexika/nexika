"""Parse raw HTML into the facts SEO and AI engines use. Nothing is rendered or stripped first."""
from __future__ import annotations

import json
import re
import urllib.parse
from dataclasses import dataclass, field
from html.parser import HTMLParser

SKIP_TEXT = {"script", "style", "noscript", "template", "svg"}
CHROME = {"nav", "header", "footer", "aside"}
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}


@dataclass
class Page:
    url: str
    status: int = 200
    lang: str = ""
    dir: str = ""
    title: str = ""
    meta: dict[str, str] = field(default_factory=dict)         # name/property -> content (lowercased keys)
    canonical: str = ""
    hreflang: dict[str, str] = field(default_factory=dict)
    headings: list[tuple[int, str]] = field(default_factory=list)
    links: list[tuple[str, str]] = field(default_factory=list)  # (absolute url, anchor text)
    images: list[tuple[str, str | None]] = field(default_factory=list)  # (src, alt or None)
    jsonld: list[dict] = field(default_factory=list)
    jsonld_errors: list[str] = field(default_factory=list)
    text: str = ""            # main text (without nav/header/footer/aside)
    blocks: list[tuple[str, str]] = field(default_factory=list)  # (heading, text under it)
    scripts: int = 0

    @property
    def words(self) -> int:
        return len(re.findall(r"[^\W_]+", self.text))

    def jsonld_types(self) -> set[str]:
        types: set[str] = set()

        def walk(node):
            if isinstance(node, dict):
                t = node.get("@type")
                if isinstance(t, str):
                    types.add(t)
                elif isinstance(t, list):
                    types.update(x for x in t if isinstance(x, str))
                for value in node.values():
                    walk(value)
            elif isinstance(node, list):
                for value in node:
                    walk(value)

        walk(self.jsonld)
        return types


class _Parser(HTMLParser):
    def __init__(self, page: Page):
        super().__init__(convert_charrefs=True)
        self.page = page
        self.stack: list[str] = []
        self.skip = 0
        self.chrome = 0
        self.in_title = False
        self.heading: tuple[int, list[str]] | None = None
        self.link: tuple[str, list[str]] | None = None
        self.jsonld: list[str] | None = None
        self.text: list[str] = []
        self.current_heading = ""
        self.block: list[str] = []

    def _abs(self, href: str) -> str:
        return urllib.parse.urljoin(self.page.url, href.strip())

    def _flush_block(self) -> None:
        body = re.sub(r"\s+", " ", " ".join(self.block)).strip()
        if body:
            self.page.blocks.append((self.current_heading, body))
        self.block = []

    def handle_starttag(self, tag, attrs):
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag not in VOID:
            self.stack.append(tag)
        if tag == "html":
            self.page.lang, self.page.dir = a.get("lang", ""), a.get("dir", "")
        elif tag == "title":
            self.in_title = True
        elif tag == "meta":
            key = (a.get("name") or a.get("property") or a.get("http-equiv") or "").lower()
            if key:
                self.page.meta[key] = a.get("content", "").strip()
        elif tag == "link":
            rel = a.get("rel", "").lower().split()
            if "canonical" in rel and a.get("href"):
                self.page.canonical = self._abs(a["href"])
            if "alternate" in rel and a.get("hreflang") and a.get("href"):
                self.page.hreflang[a["hreflang"].lower()] = self._abs(a["href"])
        elif tag == "script":
            self.page.scripts += 1
            if a.get("type", "").lower() == "application/ld+json":
                self.jsonld = []
            else:
                self.skip += 1
        elif tag in SKIP_TEXT:
            self.skip += 1
        elif tag in CHROME:
            self.chrome += 1
        elif re.fullmatch(r"h[1-6]", tag):
            self.heading = (int(tag[1]), [])
        elif tag == "a" and a.get("href"):
            self.link = (self._abs(a["href"]), [])
        elif tag == "img":
            self.page.images.append((a.get("src", ""), a.get("alt") if "alt" in a else None))

    def handle_endtag(self, tag):
        if tag in self.stack:
            while self.stack and self.stack.pop() != tag:
                pass
        if tag == "title":
            self.in_title = False
        elif tag == "script":
            if self.jsonld is not None:
                raw = "".join(self.jsonld).strip()
                try:
                    data = json.loads(raw)
                    self.page.jsonld.extend(data if isinstance(data, list) else [data])
                except (ValueError, RecursionError) as exc:
                    self.page.jsonld_errors.append(f"invalid JSON-LD: {str(exc)[:120]}")
                self.jsonld = None
            else:
                self.skip = max(0, self.skip - 1)
        elif tag in SKIP_TEXT:
            self.skip = max(0, self.skip - 1)
        elif tag in CHROME:
            self.chrome = max(0, self.chrome - 1)
        elif re.fullmatch(r"h[1-6]", tag) and self.heading:
            level, parts = self.heading
            heading = re.sub(r"\s+", " ", "".join(parts)).strip()
            self.page.headings.append((level, heading))
            if not self.chrome:
                self._flush_block()
                self.current_heading = heading
            self.heading = None
        elif tag == "a" and self.link:
            href, parts = self.link
            self.page.links.append((href, re.sub(r"\s+", " ", "".join(parts)).strip()))
            self.link = None

    def handle_data(self, data):
        if self.jsonld is not None:
            self.jsonld.append(data)
            return
        if self.in_title:
            self.page.title += data
            return
        if self.skip:
            return
        if self.heading:
            self.heading[1].append(data)
        if self.link:
            self.link[1].append(data)
        if not self.chrome and not self.heading:
            self.text.append(data)
            self.block.append(data)


def parse(html: str, url: str, status: int = 200) -> Page:
    page = Page(url=url, status=status)
    parser = _Parser(page)
    parser.feed(html)
    parser.close()
    parser._flush_block()
    page.title = re.sub(r"\s+", " ", page.title).strip()
    page.text = re.sub(r"\s+", " ", " ".join(parser.text)).strip()
    return page
