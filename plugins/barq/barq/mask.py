"""Best-effort secret masking for everything barq prints.

Masks well-known token formats anywhere, private key blocks, passwords in URLs, every value
in .env files, and values assigned to secret-looking keys. Disable with BARQ_NO_MASK=1.
"""
from __future__ import annotations

import os
import re
from pathlib import PurePath

MASK = "[masked]"

TOKENS = [re.compile(p) for p in (
    r"\bgh[pousr]_[A-Za-z0-9]{36,}",
    r"\bgithub_pat_[A-Za-z0-9_]{40,}",
    r"\bglpat-[A-Za-z0-9_-]{20,}",
    r"\bsk-ant-[A-Za-z0-9_-]{20,}",
    r"\bsk-[A-Za-z0-9_-]{20,}",
    r"\bAKIA[0-9A-Z]{16}\b",
    r"\bxox[abprs]-[A-Za-z0-9-]{10,}",
    r"\bAIza[0-9A-Za-z_-]{35}",
    r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}",
)]
BEARER = re.compile(r"(?i)(\bbearer\s+)[A-Za-z0-9._~+/-]{16,}=*")
PRIVATE_KEY = re.compile(
    r"-----BEGIN ([A-Z ]*)PRIVATE KEY-----.*?-----END \1PRIVATE KEY-----", re.S
)
URL_CREDENTIALS = re.compile(r"(\b[a-z][a-z0-9+.-]*://[^:/\s@]+:)([^@\s/]+)(@)", re.I)

_SECRET_WORDS = r"secret|token|pass|pwd|key|connection|connstr|credential"
# Finds candidates only; _secret_key() then decides from the key's last word, so MAX_TOKENS,
# token_type, jsonwebtoken and secret_name stay as written (issue #22).
ASSIGN = re.compile(
    r"""(?P<key>["']?[\w.-]*(?:""" + _SECRET_WORDS + r""")[\w.-]*["']?)"""
    r"""(?P<sep>\s*[:=]\s*)(?P<q>["']?)(?P<val>[^\s"'`,;()\[\]{}]{4,})""",
    re.I,
)
SECRET_NOUNS = {
    "secret", "token", "password", "passwd", "pass", "pwd", "passphrase", "apikey",
    "credential", "credentials", "connstr", "connectionstring",
}
KEY_QUALIFIERS = {"api", "private", "access", "secret", "signing", "encryption", "master", "client"}
STRONG_NOUNS = {"secret", "password", "passwd", "pass", "pwd", "passphrase"}
NOT_SECRETS = {"true", "false", "null", "none", "nil", "undefined", "yes", "no", "on", "off"}
PLACEHOLDER = ("$", "<", "%", "{{", MASK)
VERSION = re.compile(r"[~^>=<v]*\d+(?:\.\d+)+(?:[-+][\w.]+)?")
EXPRESSION = re.compile(r"[A-Za-z_$][\w$]*(?:\??\.[A-Za-z_$][\w$]*)+\??")  # process.env.KEY
ENV_LINE = re.compile(r"^(\s*(?:export\s+)?[A-Za-z_][A-Za-z0-9_.]*\s*=\s*)(.+?)\s*$")

CONFIG_SUFFIXES = {
    ".env", ".ini", ".cfg", ".conf", ".properties", ".yaml", ".yml", ".json", ".toml", ".config",
}
EXAMPLE_HINTS = ("example", "sample", "template", "dist")


def _enabled() -> bool:
    return os.environ.get("BARQ_NO_MASK") != "1"


def is_env_file(filename: str | None) -> bool:
    if not filename:
        return False
    name = PurePath(filename).name.lower()
    if not (name == ".env" or name.startswith(".env.") or name.endswith(".env")):
        return False
    return not any(hint in name for hint in EXAMPLE_HINTS)


def _is_config(filename: str | None) -> bool:
    if not filename:
        return False
    path = PurePath(filename)
    return path.suffix.lower() in CONFIG_SUFFIXES or path.name.lower().startswith(".env")


def _key_words(key: str) -> list[str]:
    key = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", key.strip("\"'"))
    return [w for w in re.split(r"[^A-Za-z0-9]+", key.lower()) if w]


def _secret_key(key: str) -> str | None:
    """'strong' for passwords and secrets, 'weak' for tokens and keys, None for anything else.

    Judged by the last word, which names what the value is: GITHUB_TOKEN holds a token,
    token_type holds a type.
    """
    words = _key_words(key)
    if not words:
        return None
    last = words[-1]
    joined = "".join(words[-2:])
    if last in STRONG_NOUNS:
        return "strong"
    if last in SECRET_NOUNS or joined in SECRET_NOUNS:
        return "weak"
    if last == "key" and len(words) > 1 and words[-2] in KEY_QUALIFIERS:
        return "strong" if words[-2] == "secret" else "weak"
    return None


def _secretish(value: str) -> bool:
    return bool(re.search(r"\d", value) or re.search(r"[^A-Za-z0-9_.]", value))


def mask_text(text: str, filename: str | None = None) -> tuple[str, int]:
    """Return (masked text, number of masked values)."""
    if not _enabled() or not text:
        return text, 0
    count = 0

    def sub(pattern: re.Pattern, repl, s: str) -> str:
        nonlocal count
        s, n = pattern.subn(repl, s)
        count += n
        return s

    text = sub(PRIVATE_KEY, f"-----PRIVATE KEY {MASK}-----", text)
    for token in TOKENS:
        text = sub(token, MASK, text)
    text = sub(BEARER, lambda m: m.group(1) + MASK, text)
    text = sub(URL_CREDENTIALS, lambda m: m.group(1) + MASK + m.group(3), text)

    if is_env_file(filename):
        lines = []
        for line in text.split("\n"):
            m = ENV_LINE.match(line)
            if m and not line.lstrip().startswith("#") and m.group(2) not in ('""', "''", MASK):
                lines.append(m.group(1) + MASK)
                count += 1
            else:
                lines.append(line)
        return "\n".join(lines), count

    config = _is_config(filename)

    def assign(m: re.Match) -> str:
        nonlocal count
        val = m.group("val")
        kind = _secret_key(m.group("key"))
        quote = m.group("q")
        if (kind is None or val.startswith(PLACEHOLDER) or val.lower() in NOT_SECRETS
                or VERSION.fullmatch(val) or val.lower() in _key_words(m.group("key"))
                or (not quote and EXPRESSION.fullmatch(val))
                or (quote and m.string[m.end():m.end() + 1].isspace())):  # prose: "a secret here"
            return m.group(0)
        literal = bool(quote) or config
        if (literal and (kind == "strong" or _secretish(val) or len(val) >= 8)) \
                or (kind == "strong" and _secretish(val)) or (len(val) >= 16 and _secretish(val)):
            count += 1
            return m.group("key") + m.group("sep") + m.group("q") + MASK
        return m.group(0)

    text = ASSIGN.sub(assign, text)
    return text, count
