"""Relevance ranking (BM25), the match rule, summary-vs-full, and the token budget.

An entry matches a prompt when its score passes min_score AND either a title/keyword term
matched or at least two different terms matched: one shared body word is never enough.
"""
from __future__ import annotations

import math
import re

from . import index as idx
from . import text

K1, B = 1.4, 0.75
CHARS_PER_TOKEN = 4
DEFAULTS = {
    "min_score": 1.0,          # BM25 floor
    "top_k": 3,                # entries per prompt
    "budget_tokens": 1200,     # per prompt
    "path_budget_tokens": 600, # per file touched
    "full_max_chars": 1800,    # larger entries are summarized unless inject: full
    "summary_chars": 300,
}


def settings(config: dict) -> dict:
    return {**DEFAULTS, **{k: config[k] for k in DEFAULTS if k in config}}


def score(index: dict, query: list[str]) -> list[tuple[float, dict, list[str]]]:
    n, avg, df = index["n"], index["avglen"] or 1.0, index["df"]
    q = list(dict.fromkeys(query))
    results = []
    for entry in index["entries"]:
        terms, total, matched = entry["terms"], 0.0, []
        for t in q:
            tf = terms.get(t)
            if not tf:
                continue
            idf = math.log(1 + (n - df[t] + 0.5) / (df[t] + 0.5))
            total += idf * tf * (K1 + 1) / (tf + K1 * (1 - B + B * entry["length"] / avg))
            matched.append(t)
        if matched:
            results.append((total, entry, matched))
    results.sort(key=lambda r: (-r[0], r[1]["id"]))
    return results


BODY_ONLY_FACTOR = 3  # without a title/keyword hit, the score must clear a higher bar


def qualifies(entry: dict, matched: list[str], value: float, cfg: dict) -> bool:
    if any(t in entry["head"] for t in matched):
        return value >= cfg["min_score"]
    return len(matched) >= 2 and value >= cfg["min_score"] * BODY_ONLY_FACTOR


def excerpt(body: str, limit: int) -> str:
    flat = re.sub(r"\s+", " ", body).strip()
    if len(flat) <= limit:
        return flat
    cut = flat[:limit].rsplit(" ", 1)[0]
    return cut + " …"


def render(entry: dict, level: str, cfg: dict) -> str:
    where = f"{entry['source']}:{entry['start']}-{entry['end']}"
    head = f"### {entry['title']}  ({where})"
    if level == "full":
        return f"{head}\n{entry['body']}"
    return (f"{head}\n{excerpt(entry['body'], cfg['summary_chars'])}\n"
            f"(more: read {entry['source']} lines {entry['start']}-{entry['end']})")


def _level(entry: dict, strong: bool, cfg: dict) -> str:
    if entry["inject"] in ("summary", "full"):
        return entry["inject"]
    return "full" if strong and len(entry["body"]) <= cfg["full_max_chars"] else "summary"


def _pack(candidates: list[tuple[dict, str, float, list[str]]], shown: dict, budget_chars: int,
          top_k: int, cfg: dict) -> list[dict]:
    picked, used = [], 0
    for entry, level, value, matched in candidates:
        before = shown.get(entry["id"])
        if before == "full" or (before == "summary" and level == "summary"):
            continue  # Claude already has it
        body = render(entry, level, cfg)
        if used + len(body) > budget_chars and level == "full":
            level, body = "summary", render(entry, "summary", cfg)
            if before == "summary":
                continue
        if used + len(body) > budget_chars:
            continue
        picked.append({"entry": entry, "level": level, "score": round(value, 2), "matched": matched,
                       "text": body})
        used += len(body)
        if len(picked) >= top_k:
            break
    return picked


def select_for_prompt(index: dict, prompt: str, cfg: dict, shown: dict) -> list[dict]:
    query = text.tokens(prompt)
    if not query:
        return []
    unique_q = set(query)
    candidates = []
    for value, entry, matched in score(index, query):
        if not qualifies(entry, matched, value, cfg):
            continue
        head_hits = sum(1 for t in matched if t in entry["head"])
        strong = head_hits >= 1 and len(matched) >= max(1, math.ceil(len(unique_q) * 0.5))
        candidates.append((entry, _level(entry, strong, cfg), value, matched))
    return _pack(candidates, shown, cfg["budget_tokens"] * CHARS_PER_TOKEN, cfg["top_k"], cfg)


def select_for_path(index: dict, rel_path: str, cfg: dict, shown: dict) -> list[dict]:
    candidates = []
    for entry in index["entries"]:
        if entry["source"] == rel_path or not entry["paths"]:
            continue
        if idx.matches_any(rel_path, entry["paths"]):
            small = len(entry["body"]) <= cfg["summary_chars"] * 2
            level = entry["inject"] if entry["inject"] != "auto" else ("full" if small else "summary")
            specificity = 0 if entry["kind"] == "manual" else 1
            candidates.append((specificity, len(entry["paths"]), entry, level))
    candidates.sort(key=lambda c: (c[0], c[1], c[2]["id"]))
    packed = [(entry, level, 0.0, []) for _, _, entry, level in candidates]
    return _pack(packed, shown, cfg["path_budget_tokens"] * CHARS_PER_TOKEN, cfg["top_k"], cfg)
