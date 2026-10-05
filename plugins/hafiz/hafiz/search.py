"""Find memories: BM25 relevance over language-aware tokens (Arabic and English), plus recency.

A memory matches when its score passes MIN_SCORE; newer memories win ties. Words that only
appear in a file path still count, so "where did we change DiscountService" finds the file.
"""
from __future__ import annotations

import datetime
import math
import re

from . import text

K1, B = 1.2, 0.75
MIN_SCORE = 0.2
RECENCY_DAYS = 30


def _tokens(item: dict) -> list[str]:
    return text.tokens(f"{item['type']} {item['text']} {item.get('branch', '')}")


def _age_days(date: str) -> float:
    try:
        then = datetime.datetime.fromisoformat(date)
    except (ValueError, TypeError):
        return 365.0
    return max(0.0, (datetime.datetime.now() - then).total_seconds() / 86400)


def keep(item: dict, kind: str = "", branch: str = "", days: int = 0, status: str = "") -> bool:
    if kind and item["type"] != kind:
        return False
    if branch and item.get("branch") != branch and item.get("scope") != "project":
        return False
    if status and item.get("status") != status:
        return False
    return not days or _age_days(item.get("date", "")) <= days


def newest_first(items: list[dict]) -> list[dict]:
    return sorted(items, key=lambda i: i.get("date", ""), reverse=True)


def find(items: list[dict], query: str, limit: int = 10, prefer_branch: str = "",
         **filters) -> list[tuple[float, dict]]:
    pool = newest_first([i for i in items if keep(i, **filters)])
    words = list(dict.fromkeys(text.tokens(query)))
    if not words:  # nothing to rank by: newest first
        return [(0.0, i) for i in pool[:limit]]
    docs = [_tokens(i) for i in pool]
    n = len(docs) or 1
    avg = sum(len(d) for d in docs) / n or 1.0
    df: dict[str, int] = {}
    for doc in docs:
        for token in set(doc):
            df[token] = df.get(token, 0) + 1
    exact = [w.lower() for w in re.findall(r"[\w./#-]{4,}", query) if any(c in w for c in "./#_-")]
    results = []
    for item, doc in zip(pool, docs, strict=True):
        score = 0.0
        for word in words:
            tf = doc.count(word)
            if tf:
                idf = math.log(1 + (n - df[word] + 0.5) / (df[word] + 0.5))
                score += idf * tf * (K1 + 1) / (tf + K1 * (1 - B + B * len(doc) / avg))
        lowered = item["text"].lower()
        score += sum(1.5 for e in exact if e in lowered)  # paths, issue numbers, ids typed as-is
        if score < MIN_SCORE:
            continue
        score *= 1 + 0.25 * math.exp(-_age_days(item.get("date", "")) / RECENCY_DAYS)
        if item.get("origin") == "manual":
            score *= 1.2
        if prefer_branch and item.get("branch") == prefer_branch:
            score *= 1.3
        results.append((round(score, 3), item))
    results.sort(key=lambda r: -r[0])  # stable: equal scores stay newest first
    return results[:limit]
