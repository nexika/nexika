"""What makes text sound machine-written, in English and Arabic.

FIX rules are safe, mechanical rewrites that `clean` applies on its own. FLAG rules need the
sentence rewritten by a person (or by Claude); `check` reports them with a suggestion.
"""
from __future__ import annotations

import re

# ---------------------------------------------------------------- fixed automatically

# Invisible characters that only get into text by copy-paste or generation.
# Kept on purpose: U+200C/U+200D (joiners: emoji sequences, Persian) and U+200E/U+200F (direction
# marks that Arabic text needs).
HIDDEN = dict.fromkeys(map(ord, "​⁠﻿­᠎⁡⁢⁣⁤"))
HIDDEN.update({0x00A0: " ", 0x202F: " ", 0x2007: " ", 0x2028: "\n", 0x2029: "\n"})

# Bot identities only: human co-authors (even a "Claude Monet" or someone @openai.com) stay.
_BOT = (r"(?:noreply@anthropic\.com|\bclaude (?:opus|sonnet|haiku|fable)\b|copilot@github\.com"
        r"|\bgithub copilot\b|noreply@openai\.com|\bchatgpt\b)")
_SIG = (rf"co-authored-by:[^\n]*{_BOT}[^\n]*"
        r"|(?:🤖[ \t]*)?generated (?:with|by) \[(?:claude code|chatgpt|github copilot|gemini)\]\([^\n]*"
        r"|🤖[ \t]*generated (?:with|by) [^\n]*")
SIGNATURE = re.compile(rf"^[ \t]*(?:{_SIG})(?:\n|$)", re.I | re.M)
# in a shell command the line may start right after the opening quote: --body "🤖 Generated with ..."
SIGNATURE_IN_COMMAND = re.compile(rf"(?:^|[\"'])[ \t]*(?:{_SIG})", re.I | re.M)
ZERO_WIDTH = {0x200B, 0x2060, 0xFEFF, 0x00AD}

# Filler, removed only as a complete sentence (end mark required).
# Openers only at the start of a line; closers at the start of any sentence.
OPENERS = [
    r"(?:great|good|excellent) question[!.]",
    r"(?:certainly|absolutely|of course|sure thing)!",
    r"i(?:'d| would) be (?:happy|glad) to help(?: with that| you)?[!.]",
    r"سؤال (?:رائع|ممتاز|جيد)[!.]",
    r"(?:بالتأكيد|بكل سرور)[!.،]",
]
CLOSERS = [
    r"(?:i )?hope (?:this|that) helps[!.]",
    r"(?:please )?let me know if you have any (?:other |more |further )?questions[!.]",
    r"(?:please )?(?:don't|do not) hesitate to (?:ask|reach out)[!.]",
    r"feel free to (?:ask|reach out)(?: (?:if|with) [^.!\n]{0,40})?[!.]",
    r"happy coding!",
    r"(?:آمل|أتمنى) أن يكون (?:هذا|ذلك) مفيد[اًٌ]*[!.]",
    r"لا تتردد في (?:السؤال|التواصل)[!.]",
]
OPENER_RE = re.compile(r"^[ \t]*(?:" + "|".join(OPENERS) + r")(?=\s|$)[ \t]*", re.I | re.M)
CLOSER_RE = re.compile(r"(?:^|(?<=[.!?؟] ))[ \t]*(?:" + "|".join(CLOSERS) + r")(?=\s|$)[ \t]*", re.I | re.M)

_UTILIZE = {"e": "use", "es": "uses", "ed": "used", "ing": "using"}

# Wordy phrases with a plain equivalent ("" = drop it).
REPLACE: list[tuple[re.Pattern, object]] = [
    (re.compile(r"\bin order to\b", re.I), "to"),
    (re.compile(r"\butili[sz](e|es|ed|ing)\b", re.I), lambda m: _UTILIZE[m.group(1).lower()]),
    (re.compile(r"\bdue to the fact that\b", re.I), "because"),
    (re.compile(r"\bat this point in time\b", re.I), "now"),
    (re.compile(r"\ba (?:plethora|myriad) of\b", re.I), "many"),
    (re.compile(r"\bit(?:'s| is) (?:worth noting|important to note|worth mentioning) that\s+", re.I), ""),
    (re.compile(r"\bneedless to say,\s+", re.I), ""),
    (re.compile(r"\bin today's (?:fast-paced|digital|modern|ever-changing) (?:world|age|landscape),\s*",
                re.I), ""),
    (re.compile(r"من الجدير بالذكر أن(?![\u0600-\u06FF])\s*"), ""),
    (re.compile(r"تجدر الإشارة إلى أن(?![\u0600-\u06FF])\s*"), ""),
    (re.compile(r"(?:مما )?لا شك (?:فيه )?أن(?![\u0600-\u06FF])\s*"), ""),
    (re.compile(r"في عالمنا (?:اليوم )?(?:المتسارع|الحديث)(?: اليوم)?،?\s*"), ""),
]

# ---------------------------------------------------------------- flagged for rewriting

# (word or phrase, plain alternative, weight). Weight 3 = strong tell, 1 = also common in human text.
WORDS = [
    ("delve", "look at / go through", 3), ("tapestry", "say the actual thing", 3),
    ("testament to", "shows", 3), ("realm", "area / field", 3), ("embark", "start", 3),
    ("unleash", "use / release", 3), ("game-changer", "say what changes", 3),
    ("game changer", "say what changes", 3), ("ever-evolving", "changing", 3),
    ("synergy", "say how they work together", 3), ("boasts", "has", 3), ("vibrant", "say what it is like", 3),
    ("showcase", "show", 3), ("underscore", "show / stress", 3), ("nestled", "is in", 3),
    ("in conclusion", "drop it: the last paragraph is already the end", 2),
    ("deep dive", "close look", 2), ("dive into", "look at", 2), ("navigate the complexities", "handle", 3),
    ("crucial", "important / key", 1), ("comprehensive", "full / complete", 1), ("robust", "reliable, or say how", 1),
    ("seamless", "smooth, or say what works", 1), ("leverage", "use", 1), ("furthermore", "also", 1),
    ("moreover", "also", 1), ("additionally", "also", 1), ("foster", "build / encourage", 1),
    ("streamline", "simplify / speed up", 1), ("holistic", "complete / whole", 1), ("pivotal", "key", 1),
    ("elevate", "improve", 1), ("empower", "let / help", 1), ("harness", "use", 1), ("unlock", "get / allow", 1),
    ("journey", "say what actually happens", 1), ("landscape", "field / market, or drop it", 1),
    ("intricate", "complex / detailed", 1), ("meticulous", "careful", 1), ("paramount", "most important", 1),
    ("transformative", "say what changes", 1), ("revolutionize", "change", 1), ("cutting-edge", "new", 1),
    # Arabic
    ("علاوة على ذلك", "كذلك، أو ابدأ جملة جديدة", 2), ("بالإضافة إلى ذلك", "كذلك", 1),
    ("في الختام", "احذفها: آخر فقرة هي الخاتمة", 2), ("حجر الزاوية", "الأساس", 2),
    ("جزء لا يتجزأ", "جزء أساسي", 2), ("نقلة نوعية", "قل ما الذي تغيّر بالضبط", 2),
    ("آفاق جديدة", "قل ما الذي أصبح ممكنًا", 2), ("مما لا شك فيه", "احذفها", 2), ("بلا شك", "احذفها", 1),
    ("على حد سواء", "معًا / كلاهما", 1), ("رحلة", "قل ما يحدث فعلًا", 1),
]
WORD_RES = [(re.compile((r"\b" if w.isascii() else r"(?<![؀-ۿ])") + re.escape(w)
                        + (r"\w*" if " " not in w and w.isascii() else ""), re.I), w, alt, weight)
            for w, alt, weight in WORDS]

PATTERNS = [
    (re.compile(r"\bplays? an? (?:crucial|vital|pivotal|key|important|significant) role\b", re.I),
     "say what it actually does", 2),
    (re.compile(r"\bnot (?:just|only|merely) [^.,;\n]{1,40}?,? but (?:also )?", re.I),
     "say the point directly instead of 'not just X but Y'", 2),
    (re.compile(r"\b(?:may|might|could) (?:potentially|possibly|perhaps)\b", re.I), "use one hedge, not two", 1),
    (re.compile(r"\bin (?:today's|the modern|this digital) (?:world|age|era)\b", re.I), "drop it", 3),
    (re.compile(r"\bwhether you(?:'re| are) an? [^,\n]{1,30} or an? [^,\n]{1,30},", re.I),
     "talk to your actual reader", 2),
    (re.compile(r"[يت]لعب(?: [\u0600-\u06FF]+){0,2} دور[اًا]* (?:محوري|حاسم|حيوي|مهم|أساسي)[اًا]*"), "قل ماذا يفعل بالضبط", 2),
    (re.compile(r"عالم [؀-ۿ]+ (?:المتسارع|المتغير)"), "احذفها", 2),
]

# Technical words a reader without coding experience may not know. Acronyms match case-sensitively.
JARGON = ["API", "CLI", "SDK", "CI", "JSON", "YAML", "JSON-LD", "SSR", "SEO", "LLM", "DNS", "SSRF",
          "regex", "endpoint", "repository", "repo", "commit", "branch", "pull request", "merge",
          "deploy", "pipeline", "crawler", "canonical", "sitemap", "schema", "token", "cache", "runtime",
          "framework", "hook", "webhook", "backend", "frontend", "localhost", "payload"]
ADVANCED = {"SSR", "SSRF", "DNS", "JSON-LD", "runtime", "regex", "payload", "webhook", "endpoint",
            "canonical", "LLM", "SDK", "YAML"}
# a term counts as explained when words that explain it come right after it, or "called" comes before it
EXPLAINED_AFTER = re.compile(
    r"^s?\s*(?:\(|[,:]\s*(?:a|an|the|which|meaning|i\.e\.)\b|[-:–—]\s"
    r"|(?:means?|is an?|are|stands for|refers to)\b|،?\s*(?:أي|يعني|تعني|وهو|وهي|هو|هي)(?![\u0600-\u06FF]))", re.I)
EXPLAINED_BEFORE = re.compile(r"(?:called|known as|named|يسمى|تسمى)\s*[\"'“«]?$", re.I)
