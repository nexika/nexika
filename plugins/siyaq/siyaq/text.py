"""Language-aware tokens: the same word in different forms becomes the same token.

- Unicode letters and digits of any script are kept (Arabic, Cyrillic, CJK, ...).
- CamelCase and snake_case are split: OrderService -> order service.
- Accents and Arabic diacritics (harakat) are removed; Arabic letter variants are unified
  (أ إ آ ٱ -> ا, ى -> ي, ة -> ه, ؤ -> و, ئ -> ي) and tatweel is dropped.
- Light stemming for English (validation / validating / validated -> validat) and Arabic
  (prefixes ال وال بال كال فال لل, common suffixes).
- Stop words and generic development words are ignored: they match everything. Words that say
  what the work is about (test, fix, index, docs, spec, readme) are kept.
"""
from __future__ import annotations

import re
import unicodedata

CAMEL = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")
WORD = re.compile(r"[^\W_]+")
ARABIC_LETTERS = str.maketrans({"ى": "ي", "ة": "ه", "ؤ": "و", "ئ": "ي", "ـ": None})
ARABIC_BLOCK = re.compile(r"[؀-ۿ]")

STOP_EN = set("""
a an the and or but if then else of to in on at by for from with without into onto over under about
as is are was were be been being am do does did done have has had having can could should would will
shall may might must this that these those it its i me my we our you your he she they them their his her
what which who whom whose why how when where there here not no yes so than too very just also only
all any some each every both either neither more most less least much many few one two
please thanks thank hi hello ok okay let lets want need like get got make made use used using
add change update create new file files code thing things way something work works
src lib libs dist bin obj app apps pkg internal cmd main
md txt json yaml yml toml xml html css scss cs py js jsx ts tsx go rs java kt rb php sh ps1 sql csproj sln
""".split())
STOP_AR = {
    "في", "من", "الي", "علي", "عن", "هذا", "هذه", "ذلك", "تلك", "التي", "الذي", "الذين", "ما", "ماذا",
    "كيف", "هل", "او", "ان", "لا", "انا", "نحن", "انت", "هو", "هي", "هم", "مع", "ثم", "بعد", "قبل",
    "كل", "قد", "لقد", "عند", "حتي", "اذا", "لكن", "بين", "ايضا", "فقط", "يا", "لو", "اي", "به", "بها",
    "له", "لها", "لي", "الان", "هنا", "هناك", "اريد", "ابغي", "عايز", "ممكن", "شكرا",
}

# Messages Claude Code or another tool sends in the user's place (#118): a background task's report,
# the compaction prompt. They get no knowledge, and neither does pasted text (only the words around it).
MACHINE_TAGS = ("<task-notification>", "<local-command-", "<command-name>", "<system-reminder>")
MACHINE_STARTS = ("Below is a conversation log from a Claude Code",)
PASTED = re.compile(r"<pasted_content\b[^>]*>.*?(?:</pasted_content\b[^>]*>|\Z)", re.S)


def typed_words(prompt: str) -> str:
    """The part of a prompt the user typed: '' for machine messages, pasted blocks removed."""
    prompt = prompt.strip()
    if prompt.startswith(MACHINE_TAGS + MACHINE_STARTS):
        return ""
    return PASTED.sub(" ", prompt).strip()


EN_SUFFIXES = (
    ("ational", "ate"), ("ations", "ate"), ("ation", "ate"), ("sses", "ss"), ("ies", "y"), ("ied", "y"),
    ("ings", ""), ("ing", ""), ("edly", ""), ("ed", ""), ("ers", "er"), ("ments", "ment"),
    ("ness", ""), ("ly", ""), ("es", ""), ("s", ""),
)
AR_PREFIXES = ("وال", "بال", "كال", "فال", "لل", "ال", "و")
AR_SUFFIXES = ("هما", "ات", "ان", "ون", "ين", "يه", "ها", "ه", "ي")


def normalize(text: str) -> str:
    text = CAMEL.sub(" ", text).replace("_", " ")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return text.translate(ARABIC_LETTERS).lower()


def stem(word: str) -> str:
    if ARABIC_BLOCK.search(word):
        for prefix in AR_PREFIXES:
            if word.startswith(prefix) and len(word) - len(prefix) >= 3:
                word = word[len(prefix):]
                break
        for suffix in AR_SUFFIXES:
            if word.endswith(suffix) and len(word) - len(suffix) >= 3:
                return word[: -len(suffix)]
        return word
    if not word.isascii() or not word.isalpha() or len(word) <= 3:
        return word
    for suffix, repl in EN_SUFFIXES:
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            if suffix == "s" and word.endswith(("ss", "us", "is")):
                break
            word = word[: -len(suffix)] + repl
            break
    if word.endswith("e") and len(word) > 4:
        word = word[:-1]
    return word


def is_stop(word: str) -> bool:
    return word in STOP_EN or word in STOP_AR


def tokens(text: str) -> list[str]:
    """Stemmed, meaningful tokens of a text, in order (duplicates kept)."""
    out = []
    for raw in WORD.findall(normalize(text)):
        if len(raw) < 2 or raw.isdigit() or is_stop(raw):
            continue
        token = stem(raw)
        if not is_stop(token):
            out.append(token)
    return out
