"""Separate prose (which bayan may change) from code, links and comments (which it never touches)."""
from __future__ import annotations

import re

# Never changed. An unclosed fence or comment protects the rest of the file (also keeps matching linear).
PROTECTED = re.compile(
    r"\A---[ \t]*\n.*?\n---[ \t]*(?:\n|\Z)"                    # YAML front matter
    r"|^[ \t]*(?P<fence>`{3,}|~{3,})[^\n]*\n.*?(?:^[ \t]*(?P=fence)[ \t]*$|\Z)"   # fenced code
    r"|^(?: {4}|\t)[^\n]*"                                          # indented code
    r"|``[^\n]*?``|`[^`\n]+`"                                      # inline code
    r"|<!--.*?(?:-->|\Z)"                                           # HTML comments
    r"|<[A-Za-z/!][^>\n]*>"                                         # HTML tags
    r"|\]\([^)\n]*\)|^[ \t]*\[[^\]\n]+\]:[^\n]*"                # link targets and reference links
    r"|https?://[^\s)>\]]+",
    re.S | re.M)
ARABIC = re.compile(r"[؀-ۿ]")
WORD = re.compile(r"[\w؀-ۿ]+(?:['’-][\w؀-ۿ]+)*")
LIST_ITEM = re.compile(r"^(?:[-*+]|\d+[.)])\s+")
RULE = re.compile(r"[-*_=|:\s]+")
SENTENCE_SPLIT = re.compile(r"(?<=[.!?؟])\s+")


def segments(text: str) -> list[tuple[bool, str]]:
    """[(is_prose, chunk)] in order; joining the chunks gives back the text."""
    out, pos = [], 0
    for m in PROTECTED.finditer(text):
        if m.end() == m.start():
            continue
        if m.start() > pos:
            out.append((True, text[pos:m.start()]))
        out.append((False, m.group(0)))
        pos = m.end()
    if pos < len(text):
        out.append((True, text[pos:]))
    return out


def map_prose(text: str, fn) -> str:
    return "".join(fn(chunk) if prose else chunk for prose, chunk in segments(text))


def prose_only(text: str) -> str:
    """The text with code and links blanked out; offsets and line numbers stay the same."""
    return "".join(chunk if prose else re.sub(r"[^\n]", " ", chunk) for prose, chunk in segments(text))


def words(text: str) -> int:
    return len(WORD.findall(text))


def is_arabic(text: str) -> bool:
    letters = re.findall(r"[^\W\d_]", text)
    return bool(letters) and sum(bool(ARABIC.match(c)) for c in letters) / len(letters) > 0.3


def sentences(text: str) -> list[str]:
    """Sentences of the prose: wrapped lines joined, list items separate, headings and tables skipped."""
    units: list[str] = []
    current: list[str] = []
    for line in prose_only(text).splitlines():
        s = line.strip()
        item = LIST_ITEM.match(s)
        if not s or s.startswith(("#", "|")) or RULE.fullmatch(s) or item:
            if current:
                units.append(" ".join(current))
                current = []
            if item:
                current = [s[item.end():]]
            continue
        current.append(s.lstrip("> "))
    if current:
        units.append(" ".join(current))
    return [p.strip() for u in units for p in SENTENCE_SPLIT.split(u) if words(p) >= 3]


def line_of(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1
