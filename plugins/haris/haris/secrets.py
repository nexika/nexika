"""Nothing secret is ever written to disk: private spans are dropped, secrets are replaced.

`<private>...</private>` (also an unclosed `<private>` up to the end) is removed before any text
is stored or summarized, and the words inside it are remembered only as salted hashes so they
are masked when Claude reuses them later (in a command, a task, a plan). Known secret shapes are
replaced with `[secret]`. Redaction errs on the side of hiding: a lost word is cheaper than a
leaked key.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import re

PRIVATE = re.compile(r"<private>(.*?)(?:</private>|\Z)", re.S | re.I)
MARK = "[secret]"
TYPE_WORDS = {"string", "number", "boolean", "bool", "true", "false", "null", "none", "undefined", "include",
              "omit", "same-origin", "str", "int", "bytes", "optional", "required", "redacted", "[secret]",
              "secret", "password", "token", "xxxx", "xxxxxxxx", "changeme", "example"}

PATTERNS = [
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?(?:-----END [A-Z ]*PRIVATE KEY-----|\Z)", re.S),
    re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),                       # AWS access key id
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b"),                     # GitHub tokens
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{40,}\b"),
    re.compile(r"\bsk-(?:ant-|proj-)?[A-Za-z0-9_-]{20,}"),              # Anthropic / OpenAI keys
    re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}"),                      # Slack
    re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b"),                          # Google API key
    re.compile(r"\b(?:sk|rk|pk)_(?:live|test)_[A-Za-z0-9]{16,}\b"),    # Stripe
    re.compile(r"\bglpat-[A-Za-z0-9_-]{20,}"),                         # GitLab
    re.compile(r"\bnpm_[A-Za-z0-9]{36}\b"),
    re.compile(r"\bhf_[A-Za-z0-9]{30,}\b"),                            # Hugging Face
    re.compile(r"\bSG\.[A-Za-z0-9_-]{16,}\.[A-Za-z0-9_-]{16,}"),       # SendGrid
    re.compile(r"\bpypi-[A-Za-z0-9_-]{40,}"),
    re.compile(r"\bdo[por]_v1_[a-f0-9]{40,}\b"),                       # DigitalOcean
    re.compile(r"\bATATT[A-Za-z0-9_=-]{40,}"),                         # Atlassian
    re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"),  # JWT
    re.compile(r"https://hooks\.slack\.com/services/[A-Za-z0-9/_-]+"),
    re.compile(r"https://(?:discord(?:app)?\.com)/api/webhooks/[A-Za-z0-9/_-]+"),
]
NAME = (r"[\w.-]*(?:password|passwd|passphrase|pwd|pass|secret|token|auth|api[_-]?key|apikey|access[_-]?key"
        r"|accountkey|private[_-]?key|client[_-]?secret|credentials?|connection[_-]?string|dsn|cookie|sas"
        r"|signature|[_.-]key)")
# name = value / name: value / "name": "value" / NAME='a b c'
ASSIGNMENT = re.compile(
    rf"""(?ix)(\b{NAME}["']?\s*[:=]\s*)
    (?:"([^"\n]{{1,300}})"|'([^'\n]{{1,300}})'|([^\s"',;]{{3,}}))""")
FLAG = re.compile(r"(?i)((?:^|\s)--?(?:password|passwd|pass|token|secret|api-?key|auth(?:-token)?)(?:=|\s+))"
                  r"([^\s\"']+|\"[^\"\n]*\"|'[^'\n]*')")
MYSQL_P = re.compile(r"(\b(?:mysql|mysqldump|mariadb|mysqladmin)\b[^\n|;&]*?\s-p)([^\s-][^\s]*)")
AZ_P = re.compile(r"(\baz\b[^\n|;&]*?\s(?:-p|--password)\s+)(\S+)")
CONFIG_SET = re.compile(rf"(?i)(\bconfig\s+set\s+\S*{NAME}\S*\s+)(\S+)")
USER_PASS = re.compile(r"((?:^|\s)(?:-u|--user)\s+[^\s:]+:)(\S+)")
HEADER = re.compile(r"(?i)\b((?:proxy-)?authorization\s*:\s*|(?:set-)?cookie\s*:\s*|x-api-key\s*:\s*)"
                    r"[^\n\"']+")
BEARER = re.compile(r"(?i)\b(bearer|token)\s+([A-Za-z0-9._~+/=-]{20,})")
BASIC = re.compile(r"(?i)\bbasic\s+([A-Za-z0-9+/=]{8,})")
URL_CREDENTIALS = re.compile(r"(\b[a-z][a-z0-9+.-]*://)[^\s/:@]*:[^\s/@]+@", re.I)
URL_KEY_USER = re.compile(r"(\b[a-z][a-z0-9+.-]*://)[A-Za-z0-9_-]{16,}@", re.I)   # e.g. Sentry DSN
QUERY_SECRET = re.compile(r"(?i)([?&](?:token|key|apikey|api_key|access_token|sig|signature|secret|sv|se)=)"
                          r"[^&\s]+")
SAID = re.compile(r"(?i)\b((?:password|passcode|passphrase|pwd|pin|token)\s+(?:is|was|:|=)\s+)(\S{4,})")
SAID_AR = re.compile(r"((?:كلمة|كلمه) (?:السر|المرور)\s*(?:هي|هى|:)?\s*)(\S{4,})")
PRIVATE_WORD = re.compile(r"[^\s\"'`=:,;()<>\[\]{}]{6,}")


def drop_private(text: str) -> str:
    return PRIVATE.sub("", text)


def _value(match: re.Match) -> str:
    value = next((g for g in match.groups()[1:] if g is not None), "")
    if value.lower() in TYPE_WORDS or value.startswith(("$", "{{", "<", "process.env", "os.environ")):
        return match.group(0)  # a type, a placeholder or a reference to a variable, not a value
    return match.group(1) + MARK


def _basic(match: re.Match) -> str:
    try:
        decoded = base64.b64decode(match.group(1) + "===", validate=False).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError, ValueError):
        return match.group(0)
    return f"Basic {MARK}" if ":" in decoded else match.group(0)


def _bearer(match: re.Match) -> str:
    return f"{match.group(1)} {MARK}" if re.search(r"\d", match.group(2)) else match.group(0)


def redact(text: str) -> str:
    """Private spans removed and secrets replaced: the only form of text hafiz stores."""
    if not text:
        return text
    text = drop_private(text)
    for pattern in PATTERNS:
        text = pattern.sub(MARK, text)
    text = HEADER.sub(lambda m: m.group(1) + MARK, text)
    text = URL_CREDENTIALS.sub(lambda m: f"{m.group(1)}{MARK}@", text)
    text = URL_KEY_USER.sub(lambda m: f"{m.group(1)}{MARK}@", text)
    text = ASSIGNMENT.sub(_value, text)
    for pattern in (FLAG, MYSQL_P, AZ_P, CONFIG_SET, USER_PASS, SAID, SAID_AR):
        text = pattern.sub(lambda m: m.group(1) + MARK, text)
    text = BEARER.sub(_bearer, text)
    text = BASIC.sub(_basic, text)
    return QUERY_SECRET.sub(lambda m: m.group(1) + MARK, text)


def has_secret(text: str) -> bool:
    clean = drop_private(text)
    return redact(clean) != clean


# ---------------------------------------------------------------- private words reused later


def private_words(text: str) -> list[str]:
    """Words (6+ characters) inside <private> spans: a password pasted for Claude to use, say."""
    return [w for span in PRIVATE.findall(text) for w in PRIVATE_WORD.findall(span)]


def word_hash(word: str, salt: str) -> str:
    return hashlib.sha256(f"{salt}|{word}".encode()).hexdigest()[:20]


def mask(text: str, hashes: set[str], salt: str) -> str:
    """Replace words whose salted hash is known private (also after a flag prefix like -p or --)."""
    if not hashes or not text:
        return text

    def check(match: re.Match) -> str:
        word = match.group(0)
        for cut in range(0, min(3, len(word) - 5)):
            if word_hash(word[cut:], salt) in hashes:
                return word[:cut] + MARK
        return word

    return PRIVATE_WORD.sub(check, text)


def mask_literal(text: str, words: list[str]) -> str:
    """Replace known private words anywhere in the text (used where the words are in memory)."""
    for word in sorted(set(words), key=len, reverse=True):
        text = text.replace(word, MARK)
    return text
