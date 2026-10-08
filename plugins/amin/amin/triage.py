"""Issue triage support: what needs labels, likely duplicates, stale issues. amin suggests; you decide."""
from __future__ import annotations

import datetime
import math
import re

STOP = {
    "the", "and", "for", "with", "when", "not", "does", "doesn", "can", "cannot", "from", "into", "should",
    "this", "that", "are", "was", "have", "has", "but", "after", "before", "use", "using", "add", "support",
    "error", "issue", "bug", "feature", "request", "fix", "make", "new", "need", "work", "working",
}
SIMILARITY = 0.3     # lowest weighted score listed; candidates are ranked, the reader decides
MAX_PAIRS = 20
TEMPLATE_MIN = 3     # a title opening shared by this many issues is a template, not content
STALE_DAYS = 90
# issues kept open on purpose: an old update date is expected there
KEEP_OPEN = re.compile(r"accepted|discussion|design|roadmap|long[- ]?term|help wanted|up for grabs|"
                       r"good (?:first|second) issue|blocked|confirmed|planned", re.I)


def title_words(title: str) -> set[str]:
    return {w for w in re.findall(r"[^\W_]+", title.lower()) if len(w) > 2 and w not in STOP}


def similarity(a: str, b: str) -> float:
    wa, wb = title_words(a), title_words(b)
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / len(wa | wb)


def _ordered_words(title: str, ignore: set[str]) -> list[str]:
    words = [w for w in re.findall(r"[^\W_]+", title.lower()) if len(w) > 2 and w not in STOP | ignore]
    return list(dict.fromkeys(words))


def duplicate_candidates(issues: list[dict], closed: list[dict], repo: str | None = None
                         ) -> list[tuple[float, dict, dict]]:
    """Pairs of (open, open or recently closed) issues with similar titles, most similar first.

    A title template shared by several issues ("INTERNAL ERROR: Black produced different code on the
    second pass...", "Line too long: ...") and the repo name are left out, and a word counts more when
    few titles use it. The score only ranks candidates for a reader: it proves nothing."""
    pool = issues + [dict(i, closed=True) for i in closed]
    ignore = set(_ordered_words(repo or "", set()))
    ordered = [_ordered_words(i["title"], ignore) for i in pool]
    prefixes: dict[tuple[str, ...], int] = {}
    for words in ordered:
        for k in range(2, len(words)):
            prefixes[tuple(words[:k])] = prefixes.get(tuple(words[:k]), 0) + 1
    sets = []
    for words in ordered:
        shared = [k for k in range(2, len(words)) if prefixes.get(tuple(words[:k]), 0) >= TEMPLATE_MIN]
        sets.append(set(words[max(shared, default=0):]))
    df: dict[str, int] = {}
    for words in sets:
        for w in words:
            df[w] = df.get(w, 0) + 1
    weight = {w: math.log(1 + len(pool) / n) for w, n in df.items()}
    pairs = []
    for n, a in enumerate(issues):
        for m in range(n + 1, len(pool)):
            shared = sets[n] & sets[m]
            if not shared:
                continue
            score = sum(weight[w] for w in shared) / sum(weight[w] for w in sets[n] | sets[m])
            if score >= SIMILARITY:
                pairs.append((score, a, pool[m]))
    pairs.sort(key=lambda p: -p[0])
    return pairs


def scan(issues: list[dict], labels: list[str], today: datetime.date | None = None,
         keep_labels: list[str] | None = None, closed: list[dict] | None = None,
         repo: str | None = None) -> str:
    """The triage report. keep_labels (.amin.json "triage": {"keep_labels": [...]}) are more labels,
    besides accepted or discussion ones, whose stale issues need no "any update?". closed: recently
    closed issues, also compared for duplicates; repo: the repo name, left out of titles."""
    today = today or datetime.date.today()
    lines = [f"open issues: {len(issues)}", f"labels available: {', '.join(labels) or 'none'}"]
    unlabeled = [i for i in issues if not i.get("labels")]
    lines.append(f"\nwithout labels ({len(unlabeled)}):")
    lines += [f"  #{i['number']} {i['title']}" for i in unlabeled[:40]] or ["  none"]

    pairs = duplicate_candidates(issues, closed or [], repo)
    lines.append(f"\npossible duplicates, most similar first ({len(pairs)}; titles only, read both):")
    lines += [f"  #{a['number']} ~ #{b['number']}{' (closed)' if b.get('closed') else ''} ({score:.0%}): "
              f"{a['title']} | {b['title']}" for score, a, b in pairs[:MAX_PAIRS]] or ["  none"]

    stale, kept = [], 0
    keep = {name.lower() for name in keep_labels or []}
    for i in sorted(issues, key=lambda x: x.get("updatedAt") or ""):   # oldest first
        updated = (i.get("updatedAt") or "")[:10]
        if not updated or (today - datetime.date.fromisoformat(updated)).days < STALE_DAYS:
            continue
        names = [str(lb.get("name", "")) for lb in i.get("labels") or []]
        if any(KEEP_OPEN.search(n) or n.lower() in keep for n in names):
            kept += 1    # accepted or under discussion: waiting is expected, not a reason to ask
        else:
            stale.append(i)
    lines.append(f"\nno activity for {STALE_DAYS}+ days ({len(stale)}), oldest first:")
    lines += [f"  #{i['number']} {i['title']} (last update {i['updatedAt'][:10]})"
              for i in stale[:20]] or ["  none"]
    if kept:
        lines.append(f"  ({kept} more labelled accepted or for discussion: not listed)")
    return "\n".join(lines)
