"""Find what makes a text hard to read or machine-sounding, with a suggestion for each line.

The plainness score is a style heuristic. It is not an AI detector and does not predict what
GPTZero, Copyleaks or any other detector will say.
"""
from __future__ import annotations

import re
import statistics
from dataclasses import asdict, dataclass

from . import clean as cleaner
from . import prose, rules

LONG_SENTENCE = {"no-code": 25, "junior": 30, "developer": 40}
EMOJI = re.compile(r"[\U0001F300-\U0001FAFF☀-➿]")
BOLD_BULLET = re.compile(r"^\s*[-*+]\s+\*\*[^*\n]+\*\*", re.M)
BULLET = re.compile(r"^\s*[-*+]\s+", re.M)
TRIPLE = re.compile(r"\b\w+(?: \w+)?, \w+(?: \w+)?,? and \w+"
                    r"|[؀-ۿ]+، [؀-ۿ]+،? و[؀-ۿ]+")


@dataclass
class Finding:
    kind: str          # "fix" (bayan clean does it) or "rewrite" (needs a person or Claude)
    weight: int
    line: int          # 0 = about the whole text
    text: str
    advice: str

    def to_dict(self) -> dict:
        return asdict(self)


def _snippet(text: str, start: int, end: int) -> str:
    return re.sub(r"\s+", " ", text[max(0, start - 25):end + 25]).strip()


def _jargon(text: str, body: str, level: str) -> list[Finding]:
    if level == "developer":
        return []
    out = []
    for term in rules.JARGON:
        if level == "junior" and term not in rules.ADVANCED:
            continue
        flags = 0 if term.isupper() or "-" in term else re.I
        m = re.search(r"(?<![\w-])" + re.escape(term) + r"(?![\w-])", body, flags)
        if not m or rules.EXPLAINED_AFTER.search(body[m.end():m.end() + 60]) \
                or rules.EXPLAINED_BEFORE.search(body[max(0, m.start() - 30):m.start()]):
            continue
        out.append(Finding("rewrite", 1, prose.line_of(text, m.start()), _snippet(body, m.start(), m.end()),
                           f"'{term}' is not explained: add a few plain words the first time it appears"))
    return out[:6]


def check(text: str, level: str = "no-code") -> list[Finding]:
    out: list[Finding] = []
    _, fixable = cleaner.clean(text)
    per_item = {"hidden character": 3, "AI signature line": 3, "filler sentence": 2}
    for kind, n in fixable.items():
        out.append(Finding("fix", n * per_item.get(kind, 1), 0,
                           cleaner.plural(n, kind), "bayan clean --write fixes this"))
    body = prose.prose_only(text)
    for pattern, word, alt, weight in rules.WORD_RES:
        for m in list(pattern.finditer(body))[:3]:
            out.append(Finding("rewrite", weight, prose.line_of(text, m.start()),
                               _snippet(body, m.start(), m.end()), f"'{word}' -> {alt}"))
    for pattern, advice, weight in rules.PATTERNS:
        for m in list(pattern.finditer(body))[:3]:
            out.append(Finding("rewrite", weight, prose.line_of(text, m.start()),
                               _snippet(body, m.start(), m.end()), advice))

    sents = prose.sentences(text)
    lengths = [prose.words(s) for s in sents]
    limit = LONG_SENTENCE.get(level, 25)
    long_ones = [i for i, n in enumerate(lengths) if n > limit]
    for i in long_ones[:5]:
        where = body.find(sents[i][:30])
        line = prose.line_of(text, where) if where >= 0 else 0
        out.append(Finding("rewrite", 1, line, sents[i][:90] + "...",
                           f"{lengths[i]} words: split it (aim for under {limit})"))
    if len(lengths) >= 8 and statistics.pstdev(lengths) / statistics.mean(lengths) < 0.35:
        out.append(Finding("rewrite", 3, 0, f"{len(lengths)} sentences of about "
                           f"{round(statistics.mean(lengths))} words each",
                           "sentences all have the same length: mix short ones with longer ones"))
    triples = TRIPLE.findall(body)
    if len(triples) >= 3 and len(triples) >= 0.2 * max(len(sents), 1):
        out.append(Finding("rewrite", 2, 0, f"{len(triples)} lists of three, e.g. '{triples[0]}'",
                           "not every list needs three items: keep the ones that matter"))
    bullets, bold = len(BULLET.findall(body)), len(BOLD_BULLET.findall(body))
    if bold >= 6 and bold >= 0.6 * bullets:
        out.append(Finding("rewrite", 1, 0, f"{bold} of {bullets} bullets start with a bold label",
                           "write some bullets as plain sentences"))
    for m in re.finditer(r"^#{1,6} [^\n]*", body, re.M):
        if EMOJI.search(m.group(0)):
            out.append(Finding("rewrite", 1, prose.line_of(text, m.start()), m.group(0)[:80],
                               "drop the emoji from the heading"))
    exclaims = sum(s.endswith("!") for s in sents)
    if exclaims > 3 and exclaims > 0.15 * len(sents):
        out.append(Finding("rewrite", 1, 0, f"{exclaims} sentences end with '!'",
                           "keep the excitement for one"))
    out += _jargon(text, body, level)
    return out


def score(text: str, findings: list[Finding]) -> int:
    """100 = nothing found. Each weight point costs 3, scaled down for texts longer than 300 words."""
    penalty = 3 * sum(f.weight for f in findings)
    return max(0, round(100 - penalty * 300 / max(prose.words(text), 300)))
