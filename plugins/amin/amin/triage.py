"""Issue triage support: what needs labels, likely duplicates, stale issues. amin suggests; you decide."""
from __future__ import annotations

import datetime
import re

STOP = {
    "the", "and", "for", "with", "when", "not", "does", "doesn", "can", "cannot", "from", "into", "should",
    "this", "that", "are", "was", "have", "has", "but", "after", "before", "use", "using", "add", "support",
    "error", "issue", "bug", "feature", "request", "fix", "make", "new", "need", "work", "working",
}
SIMILARITY = 0.5
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


def scan(issues: list[dict], labels: list[str], today: datetime.date | None = None,
         keep_labels: list[str] | None = None) -> str:
    """The triage report. keep_labels (.amin.json "triage": {"keep_labels": [...]}) are more labels,
    besides accepted or discussion ones, whose stale issues need no "any update?"."""
    today = today or datetime.date.today()
    lines = [f"open issues: {len(issues)}", f"labels available: {', '.join(labels) or 'none'}"]
    unlabeled = [i for i in issues if not i.get("labels")]
    lines.append(f"\nwithout labels ({len(unlabeled)}):")
    lines += [f"  #{i['number']} {i['title']}" for i in unlabeled[:40]] or ["  none"]

    pairs = []
    for n, a in enumerate(issues):
        for b in issues[n + 1:]:
            score = similarity(a["title"], b["title"])
            if score >= SIMILARITY:
                pairs.append((score, a, b))
    pairs.sort(key=lambda p: -p[0])
    lines.append(f"\npossible duplicates ({len(pairs)}):")
    lines += [f"  #{a['number']} ~ #{b['number']} ({score:.0%}): {a['title']} | {b['title']}"
              for score, a, b in pairs[:20]] or ["  none"]

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
