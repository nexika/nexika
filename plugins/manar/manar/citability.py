"""How quotable each passage is for an AI answer: an ESTIMATE from simple, transparent rules.

AI answers tend to quote passages that answer one question on their own: a direct statement
first, specific facts, and a size that fits in an answer. English and Arabic are both handled.
"""
from __future__ import annotations

import re

DEFINITION = re.compile(r"\b(is|are|means|refers to|lets you|helps)\b"
                        r"|(?:^|\s)(هو|هي|يعني|تعني|عبارة عن|يساعد)(?:\s|$)", re.I)
QUESTION = re.compile(r"[?؟]\s*$|^(how|what|why|when|which|who|can|does|is)\b"
                      r"|^(كيف|ما|ماذا|لماذا|متى|هل|من)\s", re.I)
VAGUE_START = re.compile(r"^(it|this|that|they|these|those)\b", re.I)
FACT = re.compile(r"\d+(?:[.,]\d+)?\s*%?|\b\d{4}\b")
NAME = re.compile(r"(?<![.!?]\s)(?<!^)\b[A-Z][a-zA-Z0-9]+")
ARABIC_LETTER = re.compile(r"[؀-ۿݐ-ݿ]")
LATIN_LETTER = re.compile(r"[A-Za-z]")


def words(text: str) -> list[str]:
    return re.findall(r"[^\W_]+", text)


def block_score(heading: str, text: str) -> tuple[int, list[str]]:
    """(0-100, reasons it lost points)."""
    count = len(words(text))
    first_sentence = re.split(r"(?<=[.!?؟])\s", text.strip(), maxsplit=1)[0]
    total, missing = 0, []
    if 40 <= count <= 300:
        total += 25
    elif 20 <= count <= 500:
        total += 12
        missing.append(f"{count} words: 40-300 is the easiest size to quote")
    else:
        missing.append(f"{count} words: too {'short' if count < 20 else 'long'} to quote as one answer")
    if DEFINITION.search(" ".join(words(first_sentence)[:30])):
        total += 25
    else:
        missing.append("doesn't start with a direct statement ('X is ...', 'X lets you ...')")
    if heading and QUESTION.search(heading.strip()):
        total += 10
    facts = len(FACT.findall(text))
    total += 20 if facts >= 2 else 10 if facts == 1 else 0
    if facts < 2:
        missing.append("few specifics (numbers, dates, versions, limits)")
    # names are spotted by capital letters, which Arabic doesn't have: score Arabic on the other 90 points
    arabic = len(ARABIC_LETTER.findall(text)) > len(LATIN_LETTER.findall(text))
    names = len(set(NAME.findall(text)))
    total += 10 if names >= 2 and not arabic else 0
    if VAGUE_START.match(text.strip()):
        missing.append("starts with a pronoun ('It', 'This'): name the subject")
    else:
        total += 10
    if arabic:
        total = round(total * 100 / 90)
    return min(total, 100), missing


def page_score(blocks: list[tuple[str, str]]) -> tuple[int, list[tuple[int, str, list[str]]]]:
    """(average of the best 5 blocks, weakest scored blocks with reasons)."""
    scored = [(block_score(h, t), h) for h, t in blocks if len(words(t)) >= 8]
    if not scored:
        return 0, []
    values = sorted((s for (s, _), _ in scored), reverse=True)
    best = values[:5]
    weakest = sorted(((s, h or "(intro)", why) for (s, why), h in scored), key=lambda x: x[0])[:3]
    return round(sum(best) / len(best)), weakest
