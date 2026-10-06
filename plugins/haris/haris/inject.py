"""Text that tries to give Claude orders, found in web pages, files and tool output (Arabic too).

A hit does not block anything by itself: Claude is told the text is data, not instructions,
and the session is marked for a few turns so sending data out and irreversible remote actions
need your approval (see policy.py).
"""
from __future__ import annotations

import re

MAX_SCAN = 200_000
PATTERNS = [
    ("asks to ignore earlier instructions",
     re.compile(r"(?i)\b(?:ignore|disregard|forget|override|bypass)\b[^.\n]{0,30}\b(?:all\s+|any\s+|the\s+|your\s+)?"
                r"(?:previous|prior|above|earlier|preceding|original|system|safety)\b[^.\n]{0,20}"
                r"\b(?:instructions?|prompts?|rules|messages|directions|guidelines|constraints)")),
    ("claims to be a new system or developer message",
     re.compile(r"(?i)(?:^|\n)\s*(?:#+\s*)?(?:new|updated|real|actual|hidden)\s+(?:system\s+)?instructions?\s*:|"
                r"<\s*/?\s*(?:system|instructions?|im_start|im_end)\s*>|\[/?INST\]|"
                r"BEGIN\s+(?:SYSTEM|ADMIN|DEVELOPER)\s+(?:PROMPT|MESSAGE|INSTRUCTIONS)|"
                r"(?:^|\n)\s*(?:system|developer)\s*(?:prompt|message|override)\s*:")),
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
     re.compile(r"(?i)\b(?:send|upload|post|exfiltrate|leak|forward|email|paste)\b[^.\n]{0,60}\b(?:\.env|ssh\s+keys?|"
                r"id_rsa|credentials|api[\s_-]?keys?|tokens?|secrets?|passwords?|private\s+keys?)\b[^.\n]{0,60}"
                r"\b(?:to|into|at)\s+(?:https?://|\S+\.\w{2,}|\S+@)")),
    ("asks to ignore earlier instructions (Arabic)",
     re.compile(r"(?:تجاهل|انس|تخط|تجاوز)[^.\n]{0,20}(?:جميع|كل)?\s*(?:التعليمات|الأوامر|التوجيهات|القواعد)")),
    ("tries to change who Claude is (Arabic)",
     re.compile(r"أنت\s+الآن\s+(?:مساعد|نموذج|في\s+وضع)|تعليمات\s+(?:جديدة|النظام)\s*:")),
    ("asks Claude to hide something from you (Arabic)",
     re.compile(r"(?:لا|دون\s+أن)\s+(?:تخبر|تُخبر|تبلغ|تُعلم)\s+المستخدم|دون\s+(?:إخبار|علم)\s+المستخدم")),
    ("hides text in invisible characters",
     re.compile(r"[\U000E0000-\U000E007F]{4,}|[​-‏⁠-⁤﻿]{6,}|[‪-‮⁦-⁩]")),
    ("hides instructions in an HTML comment",
     re.compile(r"(?is)<!--(?:(?!-->).){0,400}\b(?:ignore\s+(?:all|previous|the)|instructions?\s+for|"
                r"ai\s+(?:assistant|agent)|claude|system\s+prompt|you\s+must)\b(?:(?!-->).){0,400}-->")),
]


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
    return [label for label, pattern in PATTERNS if pattern.search(text)]
