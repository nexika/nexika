"""Text that tries to give Claude orders, found in web pages, files and tool output (Arabic too).

A hit does not block anything by itself: Claude is told the text is data, not instructions,
and the session is marked for a few turns so sending data out and irreversible remote actions
need your approval (see policy.py).
"""
from __future__ import annotations

import re

MAX_SCAN = 200_000
QUOTED_MAX = 40  # a short phrase in quotes is a mention ("ignore previous instructions"), not an order
QUOTED = re.compile("|".join(rf"{a}[^{b}\n]{{1,{QUOTED_MAX}}}{b}" for a, b in ('"' * 2, "“”", "``", "«»")))
_VERB = (r"(?:ignore|disregard|forget|override|bypass|discard|abandon|set\s+aside|throw\s+out|"
         r"pay\s+no\s+attention\s+to)")
_RULES = r"(?:instructions?|prompts?|rules|messages|directions|guidelines|guidance|constraints|orders)"
_EARLIER = r"(?:previous|prior|above|earlier|preceding|original|system|safety)"
# An Arabic order verb starts a word: no Arabic letter or vowel mark before it, except a joined
# و or ف ("and"). Without this, تجاهل ("ignore!") matched inside يتجاهل ("he ignores"), a description.
_AR_LETTER = r"\u0621-\u065F\u0670-\u06D3"
_AR_START = rf"(?<![{_AR_LETTER}])(?:[وف][\u064B-\u0652]*)?"
_AR_END = r"(?![\u0621-\u064A])"  # انس and تخط end the word too: not الانسان, تخطيط
PATTERNS = [
    ("asks to ignore earlier instructions",
     re.compile(rf"(?i)\b{_VERB}\b[^.\n]{{0,30}}\b(?:all\s+|any\s+|the\s+|your\s+)?{_EARLIER}\b[^.\n]{{0,20}}"
                rf"\b{_RULES}|"
                rf"\b{_VERB}\s+(?:the|your|all|any)\s+{_RULES}\s+(?:you(?:'ve|\s+have|\s+were)?\s+(?:been\s+)?"
                rf"(?:given|told|received)|above|so\s+far)\b|"
                rf"\b{_VERB}\s+(?:everything|all|anything)\s+(?:that\s+)?you(?:'ve|\s+have|\s+were)?\s+(?:been\s+)?"
                rf"(?:told|given|instructed)|"
                rf"\b(?:{_EARLIER}|old|existing|your)\s+{_RULES}\s+(?:are|is|have\s+been|has\s+been)\s+(?:now\s+)?"
                rf"(?:void|cancell?ed|revoked|obsolete|superseded|replaced|null)\b|"
                rf"\b{_EARLIER}\s+{_RULES}\s+(?:now\s+)?no\s+longer\s+apply\s+to\s+you\b")),
    ("claims to be a new system or developer message",
     re.compile(r"(?i)(?:^|\n)\s*(?:#+\s*)?(?:new|updated|real|actual|hidden)\s+(?:system\s+)?instructions?\s*:|"
                r"<\s*/?\s*(?:system|system-reminder|instructions?|im_start|im_end)\s*>|\[/?INST\]|"
                r"<\|(?:im_start|im_end|system|endoftext|user|assistant)\|>|"
                r"BEGIN\s+(?:SYSTEM|ADMIN|DEVELOPER)\s+(?:PROMPT|MESSAGE|INSTRUCTIONS)|"
                r"(?:^|\n)\s*(?:updated\s+)?(?:system|developer)\s*(?:prompt|message|override|instructions?)\s*:|"
                r"\byour\s+new\s+(?:task|instructions?|role|goal|objective|orders|job)\s+(?:is|are)\b")
     ),
    ("claims to be a new system or developer message (bracketed)",
     re.compile(r"(?:^|\n)\s*\[(?:SYSTEM|ADMIN|DEVELOPER)\s+(?:MESSAGE|OVERRIDE|NOTE|PROMPT|INSTRUCTIONS?)\]|"
                r"(?:^|\n)\s*\[(?:SYSTEM|ADMIN|DEVELOPER)\][^\n]{0,60}"
                r"(?i:\b(?:assistant|claude|ai|you\s+must|you\s+are)\b)")),
    ("tries to change who Claude is",
     re.compile(r"(?i)\byou\s+are\s+now\s+(?:a|an|in|the|no\s+longer)\b|\bact\s+as\s+(?:an?\s+)?(?:unrestricted|"
                r"jailbroken|DAN\b)|\bdeveloper\s+mode\s+(?:enabled|on)\b")),
    ("asks Claude to hide something from you",
     re.compile(r"(?i)\b(?:do\s+not|don'?t|never)\s+(?:tell|inform|alert|show)\s+(?:the\s+)?user\b|"
                r"\bwithout\s+(?:asking|telling|informing|notifying)\s+(?:the\s+)?user\b|"
                r"\bsilently\s+(?:run|execute|send|upload|delete)")),
    ("addresses the AI assistant with commands",
     re.compile(r"(?i)\b(?:claude|ai\s+(?:assistant|agent)|language\s+model|llm|coding\s+agent)\b"
                r"[^.\n]{0,60}\b(?:must|should|need\s+to|are\s+(?:instructed|required)\s+to|shall)\b[^.\n]{0,60}"
                r"\b(?:run|execute|send|upload|post|delete|remove|ignore|reveal|curl|install|push)\b")),
    ("asks to send secrets somewhere",
     re.compile(r"(?i)\b(?:send|upload|post|exfiltrate|leak|forward|email|paste)\b[^\n]{0,60}?"
                r"(?:(?<!\w)\.env\b|\b(?:ssh\s+keys?|id_rsa|credentials|api[\s_-]?keys?|tokens?|secrets?|passwords?|"
                r"private\s+keys?)\b)[^\n]{0,60}?\b(?:to|into|at)\s+(?:https?://|\S+\.\w{2,}|\S+@)")),
    ("asks to ignore earlier instructions (Arabic)",
     re.compile(rf"{_AR_START}(?:تجاهل|تجاوز|(?:انس|تخط){_AR_END})[^.\n]{{0,20}}"
                r"(?:جميع|كل)?\s*(?:التعليمات|الأوامر|التوجيهات|القواعد)|"
                r"لا\s+(?:تلتزم|تتبع|تعمل)\s+(?:ب)?(?:التعليمات|الأوامر|التوجيهات|القواعد)")),
    ("tries to change who Claude is (Arabic)",
     re.compile(r"أنت\s+الآن\s+(?:مساعد|نموذج|في\s+وضع)|تعليمات\s+(?:جديدة|النظام)\s*:|"
                r"(?:مهمتك|تعليماتك|دورك|أوامرك)\s+(?:الجديدة|الجديده)")),
    ("asks Claude to hide something from you (Arabic)",
     re.compile(r"(?:لا|دون\s+أن)\s+(?:تخبر|تُخبر|تبلغ|تُعلم)\s+المستخدم|دون\s+(?:إخبار|علم)\s+المستخدم")),
    ("hides text in invisible characters",
     re.compile(r"[\U000E0000-\U000E007F]{4,}|[​-‏⁠-⁤﻿]{6,}|[‪-‮⁦-⁩]")),
    ("hides instructions in an HTML comment",
     re.compile(r"(?is)<!--(?:(?!-->).){0,400}\b(?:ignore\s+(?:all|previous|the)|instructions?\s+for|"
                r"ai\s+(?:assistant|agent)|claude|system\s+prompt|you\s+must)\b(?:(?!-->).){0,400}-->")),
]


def _unquote(text: str) -> str:
    """Short quoted phrases blanked out: docs that name an attack ("do not tell the user") are not one."""
    return QUOTED.sub(lambda m: " " * len(m.group(0)), text)


def flatten(value, out: list[str] | None = None) -> list[str]:
    """Every string inside a tool result (dicts and lists included)."""
    out = [] if out is None else out
    if isinstance(value, str):
        out.append(value[:MAX_SCAN])
    elif isinstance(value, dict):
        for v in value.values():
            flatten(v, out)
    elif isinstance(value, (list, tuple)):
        for v in value:
            flatten(v, out)
    return out


def scan(value) -> list[str]:
    text = "\n".join(flatten(value))[:MAX_SCAN]
    if not text:
        return []
    words = _unquote(text)
    found = []
    for label, pattern in PATTERNS:
        target = text if label.startswith("hides") else words
        if pattern.search(target):
            found.append(label.replace(" (bracketed)", ""))
    return list(dict.fromkeys(found))
