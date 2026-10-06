"""PowerShell, lightly: statements and cmdlets mapped to the same action-and-target checks.

Not a full PowerShell parser (that is planned later). Statements are split on `;`, `|`, `&&`,
`||` and new lines outside quotes; known cmdlets and their aliases are checked like their shell
counterparts; anything unknown is left to Claude Code's own permission rules, and anything that
hides what it runs (Invoke-Expression, encoded commands) is asked about.
"""
from __future__ import annotations

import re

from . import classify as c

ALIASES = {
    "rm": "remove-item", "del": "remove-item", "erase": "remove-item", "rd": "remove-item",
    "ri": "remove-item",
    "rmdir": "remove-item", "cat": "get-content", "gc": "get-content", "type": "get-content",
    "ls": "get-childitem", "dir": "get-childitem", "gci": "get-childitem", "cp": "copy-item",
    "copy": "copy-item",
    "cpi": "copy-item", "mv": "move-item", "move": "move-item", "mi": "move-item", "iex": "invoke-expression",
    "iwr": "invoke-webrequest", "irm": "invoke-restmethod", "curl": "invoke-webrequest",
    "wget": "invoke-webrequest", "sc": "set-content", "ac": "add-content", "ni": "new-item",
    "echo": "write-output",
    "write": "write-output", "saps": "start-process", "start": "start-process", "icm": "invoke-command",
    "cd": "set-location", "sl": "set-location", "pwd": "get-location", "gl": "get-location",
}
READS = {"get-childitem", "get-item", "test-path", "select-string", "get-location", "write-output",
         "write-host", "get-process", "get-service", "get-command", "get-help", "select-object",
         "where-object",
         "foreach-object", "sort-object", "measure-object", "format-table", "format-list", "out-string",
         "convertto-json", "convertfrom-json", "get-date", "resolve-path", "split-path", "join-path",
         "get-filehash", "compare-object", "get-member", "out-host", "get-itemproperty"}
WRITES = {"set-content", "add-content", "out-file", "new-item", "copy-item", "move-item", "rename-item",
          "export-csv", "export-clixml", "set-itemproperty", "new-itemproperty"}
PATH_PARAMS = ("-path", "-literalpath", "-destination", "-filepath", "-outfile", "-target")
SWITCHES = ("-recurse", "-force", "-whatif", "-confirm", "-raw", "-append", "-nonewline", "-usebasicparsing")
TOKEN = re.compile(r"'(?:[^']|'')*'|\"(?:`.|[^\"`])*\"|[^\s'\";|]+")


def split_statements(text: str) -> list[str]:
    out, cur, quote, i = [], [], "", 0
    while i < len(text):
        ch = text[i]
        if quote:
            cur.append(ch)
            if ch == "`" and quote == '"' and i + 1 < len(text):
                cur.append(text[i + 1])
                i += 1
            elif ch == quote:
                quote = ""
        elif ch in "'\"":
            quote = ch
            cur.append(ch)
        elif ch in ";|\n" or text.startswith(("&&", "||"), i):
            out.append("".join(cur))
            cur = []
            if text.startswith(("&&", "||"), i):
                i += 1
        else:
            cur.append(ch)
        i += 1
    if quote:
        raise ValueError("a quote is never closed")
    out.append("".join(cur))
    return [s.strip() for s in out if s.strip()]


def unquote(word: str) -> str:
    if len(word) > 1 and word[0] == word[-1] == "'":
        return word[1:-1].replace("''", "'")
    if len(word) > 1 and word[0] == word[-1] == '"':
        return word[1:-1]
    return word


def expand_path(value: str, ctx: c.Ctx) -> c.Arg:
    value = re.sub(r"(?i)^(?:\$env:USERPROFILE|\$HOME|\$env:HOME|~)", ctx.where.home, value)
    if "$" in value or "(" in value:
        return c.arg(c.UNKNOWN)
    return c.arg(value.replace("\\", "/"))


def classify(text: str, ctx: c.Ctx) -> None:
    try:
        statements = split_statements(text)
    except ValueError as exc:
        ctx.add("unparsed", f"haris could not read this PowerShell command ({exc}).")
        return
    downloaded = False
    for statement in statements:
        words = [unquote(w) for w in TOKEN.findall(statement)]
        if words and words[0] in ("&", "."):
            words = words[1:]
        if not words:
            continue
        name = ALIASES.get(words[0].lower(), words[0].lower())
        lower = statement.lower()
        params: dict[str, str] = {}
        positional: list[str] = []
        i = 1
        while i < len(words):
            w = words[i]
            if w.startswith("-") and w.lower() not in SWITCHES and i + 1 < len(words):
                params[w.lower()] = words[i + 1]
                i += 2
                continue
            if not w.startswith("-"):
                positional.append(w)
            i += 1
        paths = [expand_path(params[p], ctx) for p in PATH_PARAMS if p in params]
        paths += [expand_path(p, ctx) for p in positional]
        fetches = bool(re.search(r"invoke-(?:webrequest|restmethod)|\biwr\b|\birm\b|downloadstring"
                                 r"|net\.webclient",
                                 lower))
        if re.search(r"\$profile\b", lower) and name in WRITES:
            ctx.add("persistence", "Changes your PowerShell profile, which runs on every start.")
        elif name == "invoke-expression" or re.search(r"\[scriptblock\]::create|frombase64string", lower):
            if downloaded or fetches:
                ctx.add("download-run", "Runs PowerShell code it downloads, without you seeing it first.")
            else:
                ctx.add("dynamic", "Runs PowerShell code that is only known when it runs.")
        elif name in ("invoke-webrequest", "invoke-restmethod") or fetches:
            downloaded = True
            if "-infile" in params:
                c.egress_payload(ctx, name, [], [expand_path(params["-infile"], ctx)],
                                 [c.arg(p) for p in positional[:1]],
                                 None, True)
            elif "-body" in params:
                c.egress_payload(ctx, name, [c.arg(params["-body"])], [],
                                 [c.arg(p) for p in positional[:1]], None,
                                 True)
            else:
                ctx.add("egress", "Downloads from the internet.")
            if "-outfile" in params:
                c.write_paths([expand_path(params["-outfile"], ctx)], ctx, "saves a download to")
        elif name == "remove-item":
            c.delete_paths(paths or [c.arg(c.UNKNOWN)], ctx)
        elif name in WRITES:
            if name in ("copy-item", "move-item") and len(paths) > 1:
                if name == "move-item":
                    c.delete_paths(paths[:1], ctx, "moves away")
                else:
                    c.read_paths(paths[:1], ctx, "copies")
            if re.search(r"\\run\b|runonce|startup", lower) and "itemproperty" in name:
                ctx.add("persistence", "Makes Windows start a program on its own.")
            else:
                c.write_paths(paths[-1:] or [c.arg(c.UNKNOWN)], ctx)
        elif name == "set-location":
            ctx.cwd = ctx.where.resolve(paths[0], ctx.cwd) if paths else ctx.where.home
            ctx.add("read", "Changes the current folder.")
        elif name == "get-content":
            c.read_paths(paths or [c.arg(c.UNKNOWN)], ctx)
        elif name in READS:
            ctx.add("read", f"Only shows information ({words[0]}).")
        elif name == "start-process" and re.search(r"-verb\s+runas", lower):
            ctx.add("privileged", "Starts a program with administrator rights.")
        elif name in ("set-executionpolicy", "set-mppreference", "add-mppreference", "set-netfirewallprofile",
                      "disable-windowsoptionalfeature"):
            ctx.add("risky", f"`{words[0]}` weakens Windows security settings.")
        elif name in ("register-scheduledtask", "new-scheduledtask", "new-service"):
            ctx.add("persistence", "Makes Windows start a program on its own.")
        elif name in ("stop-computer", "restart-computer"):
            ctx.add("risky", "Shuts down or restarts the computer.")
        elif name in ("format-volume", "clear-disk", "initialize-disk", "remove-partition"):
            ctx.add("system", "Formats or wipes a disk.")
        else:
            c.run([c.arg(w) for w in words], ctx, None)
