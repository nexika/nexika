"""Relevance ranking (BM25), the match rule, summary-vs-full, and the token budget.

An entry matches a prompt when its score passes min_score AND either a term of its own heading
or keywords matched or at least two different terms matched: one shared body word is never
enough. A short prompt needs two matched terms (or a hand-written keyword), and an
acknowledgement ("ok thanks", "تمام") matches nothing.
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


def squeeze(cfg: dict, level: str) -> dict:
    """Load less as the context window fills (mizan's level): normal when fresh, half at mid, only
    the strongest match as a summary when full. An entry marked `inject: full` keeps its level."""
    share = {"mid": 2, "full": 4}.get(level)
    if not share:
        return cfg
    out = {**cfg, "budget_tokens": cfg["budget_tokens"] // share,
           "path_budget_tokens": cfg["path_budget_tokens"] // share, "top_k": max(1, cfg["top_k"] - 1)}
    if level == "full":
        out.update(top_k=1, full_max_chars=0, min_score=cfg["min_score"] * 2)
    return out


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
SHORT_PROMPT = 3      # prompts with at most this many meaningful terms need two hits
ACK_WORDS = set("""
ok okay k yes yep yeah yup sure fine good great nice perfect cool awesome thanks thank thx ty done
merged lgtm continue proceed go ahead sounds right correct exactly agreed approved np alright
تمام شكرا اوكي اوك ممتاز نعم ايوه اكيد طيب حلو كمل تابع موافق صح
""".split())
ACK_MAX_WORDS = 6


def is_acknowledgement(prompt: str) -> bool:
    words = text.normalize(prompt).replace("،", " ").split()
    words = [w.strip(".,!?;:()'\"؟") for w in words]
    words = [w for w in words if w]
    return bool(words) and len(words) <= ACK_MAX_WORDS and words[0] in ACK_WORDS


def qualifies(entry: dict, matched: list[str], value: float, cfg: dict, short: bool = False) -> bool:
    if short and len(matched) < 2 and not any(t in entry.get("key_terms", ()) for t in matched):
        return False
    if any(t in entry["head"] for t in matched):
        return value >= cfg["min_score"]
    return len(matched) >= 2 and value >= cfg["min_score"] * BODY_ONLY_FACTOR


def _blocks(body: str) -> list[tuple[str, str]]:
    """("prose" | "table" | "code", text): code fences and table rows keep their lines."""
    blocks: list[tuple[str, str]] = []
    lines = body.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.lstrip().startswith(("```", "~~~")):
            fence = line.lstrip()[:3]
            end = next((j for j in range(i + 1, len(lines)) if lines[j].lstrip().startswith(fence)),
                       len(lines) - 1)
            blocks.append(("code", "\n".join(lines[i:end + 1])))
            i = end + 1
        elif line.lstrip().startswith("|"):
            end = i
            while end + 1 < len(lines) and lines[end + 1].lstrip().startswith("|"):
                end += 1
            blocks.append(("table", "\n".join(lines[i:end + 1])))
            i = end + 1
        else:
            if line.strip():
                if blocks and blocks[-1][0] == "prose":
                    blocks[-1] = ("prose", blocks[-1][1] + " " + line.strip())
                else:
                    blocks.append(("prose", line.strip()))
            i += 1
    return blocks


def excerpt(body: str, limit: int) -> str:
    """The start of a section: prose on one line, tables and code blocks whole (a cut table or command
    is worse than none). A table or code block may take the excerpt up to twice `limit`."""
    out: list[str] = []
    used = 0
    for kind, block in _blocks(body):
        if kind == "prose":
            flat = re.sub(r"\s+", " ", block).strip()
            if used + len(flat) <= limit:
                out.append(flat)
                used += len(flat)
                continue
            room = limit - used
            if room > 40:
                out.append(flat[:room].rsplit(" ", 1)[0] + " …")
            else:
                out.append("…")
            break
        if used + len(block) > limit * 2:
            out.append("…")
            break
        out.append(block)
        used += len(block)
    return "\n".join(out)


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
    """The top `top_k` candidates, less those Claude already has: a repeat never pulls in weaker ones."""
    picked, used = [], 0
    for entry, level, value, matched in candidates[:top_k]:
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
    return picked


def select_for_prompt(index: dict, prompt: str, cfg: dict, shown: dict) -> list[dict]:
    query = text.tokens(prompt)
    if not query or is_acknowledgement(prompt):
        return []
    unique_q = set(query)
    short = len(unique_q) <= SHORT_PROMPT
    candidates = []
    for value, entry, matched in score(index, query):
        if not qualifies(entry, matched, value, cfg, short):
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
            small = len(entry["body"]) <= min(cfg["summary_chars"] * 2, cfg["full_max_chars"])
            level = entry["inject"] if entry["inject"] != "auto" else ("full" if small else "summary")
            specificity = 0 if entry["kind"] == "manual" else 1
            candidates.append((specificity, len(entry["paths"]), entry, level))
    candidates.sort(key=lambda c: (c[0], c[1], c[2]["id"]))
    packed = [(entry, level, 0.0, []) for _, _, entry, level in candidates]
    return _pack(packed, shown, cfg["path_budget_tokens"] * CHARS_PER_TOKEN, cfg["top_k"], cfg)
