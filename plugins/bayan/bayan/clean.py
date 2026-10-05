"""Safe, mechanical clean-up: hidden characters, AI signature lines, filler sentences, wordy phrases,
and em dashes between words. Code, front matter, HTML, link targets and comments are never changed.
With `region`, only that part of the text is touched (the part Claude just wrote)."""
from __future__ import annotations

import re
from collections import Counter

from . import prose, rules

_MARK = "\x00"   # where a phrase was dropped at the start of a sentence: capitalise what follows
_LETTER = r"[^\W\d_]"
# only between two letters: tables (| — |), quotes (> — Name) and ranges (10 – 20) stay
_DASH = re.compile(rf"(?<={_LETTER})[ \t]*—[ \t]*(?={_LETTER})|(?<={_LETTER})[ \t]+–[ \t]+(?={_LETTER})")


def _at_sentence_start(text: str, pos: int) -> bool:
    before = text[:pos].rstrip(" \t")
    return not before or before[-1] in ".!?؟\n:*#>-"


def _replace(text: str, pattern: re.Pattern, repl, changes: Counter) -> str:
    def sub(m: re.Match) -> str:
        new = repl(m) if callable(repl) else repl
        changes["wordy phrase"] += 1
        if not new:
            return _MARK if _at_sentence_start(m.string, m.start()) else ""
        if m.group(0)[:1].isupper():
            new = new[:1].upper() + new[1:]
        return new
    return pattern.sub(sub, text)


def _prose(chunk: str, changes: Counter, dashes: bool) -> str:
    fixed = chunk.translate(rules.HIDDEN)
    if fixed != chunk:
        changes["hidden character"] += sum(1 for c in chunk if ord(c) in rules.HIDDEN)

    def filler(m: re.Match) -> str:
        changes["filler sentence"] += 1
        return _MARK
    fixed = rules.CLOSER_RE.sub(filler, rules.OPENER_RE.sub(filler, fixed))
    for pattern, repl in rules.REPLACE:
        fixed = _replace(fixed, pattern, repl, changes)
    fixed = re.sub(_MARK + r"([ \t]*)([a-z])", lambda m: m.group(1) + m.group(2).upper(), fixed)
    fixed = fixed.replace(_MARK, "")
    if dashes:
        def dash(m: re.Match) -> str:
            changes["em dash"] += 1
            return "، " if prose.ARABIC.search(fixed[max(0, m.start() - 20):m.start()]) else ", "
        fixed = _DASH.sub(dash, fixed)
    if fixed != chunk:
        fixed = re.sub(r"^[ \t]+(?=\r?$)", "", fixed, flags=re.M)
        fixed = re.sub(r"(?:\r?\n){3,}", lambda m: "\r\n\r\n" if "\r" in m.group(0) else "\n\n", fixed)
    return fixed


def _drop_signatures(text: str, region, changes: Counter):
    """Remove whole AI signature lines (they contain <email> and (links), so this runs on lines, not on
    prose chunks). Lines inside code blocks, front matter or comments stay."""
    blocks = [(m.start(), m.end()) for m in prose.PROTECTED.finditer(text) if "\n" in m.group(0)]
    lo, hi = region if region else (0, len(text))
    kept, pos, removed_in_region = [], 0, 0
    for m in rules.SIGNATURE.finditer(text):
        if m.start() < lo or m.end() > hi or any(a <= m.start() < b for a, b in blocks):
            continue
        kept.append(text[pos:m.start()])
        pos = m.end()
        removed_in_region += m.end() - m.start()
        changes["AI signature line"] += 1
    if not removed_in_region:
        return text, region
    kept.append(text[pos:])
    return "".join(kept), (lo, hi - removed_in_region) if region else None


def clean(text: str, dashes: bool = True, region: tuple[int, int] | None = None) -> tuple[str, Counter]:
    """(cleaned text, what was changed)."""
    changes: Counter = Counter()
    text, region = _drop_signatures(text, region, changes)
    out, pos = [], 0
    for is_prose, chunk in prose.segments(text):
        start, end = pos, pos + len(chunk)
        pos = end
        if not is_prose:
            out.append(chunk)
        elif region is None:
            out.append(_prose(chunk, changes, dashes))
        else:
            a, b = max(start, region[0]), min(end, region[1])
            if a >= b:
                out.append(chunk)
            else:
                out.append(chunk[:a - start] + _prose(chunk[a - start:b - start], changes, dashes)
                           + chunk[b - start:])
    fixed = "".join(out)
    changes = +changes
    if changes and region is None and text.endswith("\n"):
        newline = "\r\n" if text.endswith("\r\n") else "\n"
        fixed = fixed.rstrip() + newline   # removed closing lines must not leave blank lines behind
    return fixed, changes


def plural(n: int, kind: str) -> str:
    return f"{n} {kind}" if n == 1 else f"{n} {kind}{'es' if kind.endswith(('sh', 's')) else 's'}"


def summary(changes: Counter) -> str:
    return ", ".join(plural(n, kind) for kind, n in changes.most_common())
