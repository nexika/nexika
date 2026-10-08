"""A shell parser for the commands Claude runs: it finds every command a line would start.

It reads POSIX sh and the bash forms Claude uses: quotes and escapes (`$'...'` included),
`; & && || | |&`, newlines, `( )` and `{ }` groups, if/while/until/for/case bodies, functions,
`$( )` and backticks, `<( )` and `>( )`, arithmetic, heredocs (whose `$( )` also runs),
here-strings and every redirection. Anything it cannot read raises ParseError, which haris turns
into "ask": a command haris cannot read is never approved.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

MAX_DEPTH = 12
MAX_LENGTH = 100_000
NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
ASSIGNMENT = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)(\+?=)")
FD_PREFIX = re.compile(r"\d+(?=[<>])|\{[A-Za-z_][A-Za-z0-9_]*\}(?=[<>])")
TILDE = re.compile(r"~([A-Za-z0-9_.+-]*)")
SPECIAL_VARS = set("@*#?-$!0123456789")
OPERATORS = ("&&", "||", ";;&", ";;", ";&", "|&", "&>>", "&>", "<<<", "<<-", "<<", "<&", "<>", ">>", ">&",
             ">|", "&", "|", ";", "(", ")", "<", ">")
REDIRECTIONS = {"&>>", "&>", "<<<", "<<-", "<<", "<&", "<>", ">>", ">&", ">|", "<", ">"}
CLOSERS = {"then", "elif", "else", "fi", "do", "done", "esac", "}", "in"}
ANSI = {"a": "\a", "b": "\b", "e": "\x1b", "E": "\x1b", "f": "\f", "n": "\n", "r": "\r", "t": "\t",
        "v": "\v", "\\": "\\", "'": "'", '"': '"', "?": "?"}


class ParseError(ValueError):
    pass


@dataclass
class Part:
    kind: str                  # lit | var | sub | arith | tilde
    text: str = ""             # literal text, variable name, or the user after ~
    quoted: bool = False
    script: list | None = None  # the commands of a substitution
    how: str = ""              # $( ` <( >(


@dataclass
class Word:
    parts: list[Part]

    def plain(self) -> str | None:
        """The text of a single unquoted literal (how reserved words look)."""
        if len(self.parts) == 1 and self.parts[0].kind == "lit" and not self.parts[0].quoted:
            return self.parts[0].text
        return None


@dataclass
class Redirect:
    op: str
    fd: str
    target: Word | None
    body: Word | None = None   # heredoc text (its substitutions run)


@dataclass
class Simple:
    words: list[Word]
    assigns: list[tuple[str, Word]] = field(default_factory=list)
    redirects: list[Redirect] = field(default_factory=list)
    data: bool = False         # words that are not run (for-lists, [[ ]], case subjects)


@dataclass
class Pipeline:
    stages: list
    background: bool = False
    joined: str = ""           # "&&" or "||" when it runs only after the pipeline before it


@dataclass
class Group:
    body: list
    subshell: bool
    redirects: list[Redirect] = field(default_factory=list)


@dataclass
class Function:
    name: str
    body: object


@dataclass
class Tok:
    kind: str                  # word | op | redir
    text: str = ""
    word: Word | None = None
    fd: str = ""
    heredoc: dict | None = None


def parse(text: str, depth: int = 0) -> list:
    """The commands of a shell line, as a list of Pipelines."""
    if depth > MAX_DEPTH:
        raise ParseError("commands are nested too deeply")
    if len(text) > MAX_LENGTH:
        raise ParseError("the command is too long to check")
    return Parser(Lexer(text, depth).tokens(), depth).parse()


# ---------------------------------------------------------------- lexer


class Lexer:
    def __init__(self, text: str, depth: int = 0, start: int = 0):
        self.s, self.i, self.depth = text, start, depth
        self.pending: list[dict] = []

    def _peek(self, n: int = 0) -> str:
        j = self.i + n
        return self.s[j] if j < len(self.s) else ""

    def tokens(self, close: bool = False) -> list[Tok]:
        """Tokens up to the end, or (close=True) up to the `)` that ends a `$(`."""
        out: list[Tok] = []
        parens = 0
        while True:
            c = self._peek()
            if c == "":
                if close:
                    raise ParseError("a `$(` is never closed")
                self._heredocs()
                return out
            if c in " \t\r":
                self.i += 1
            elif c == "\\" and self._peek(1) == "\n":
                self.i += 2
            elif c == "\n":
                self.i += 1
                out.append(Tok("op", "\n"))
                self._heredocs()
            elif c == "#":
                while self._peek() not in ("", "\n"):
                    self.i += 1
            elif c == ")" and close and parens == 0:
                self.i += 1
                return out
            elif c in "<>" and self._peek(1) == "(":
                out.append(Tok("word", word=self._word()))
            else:
                fd = FD_PREFIX.match(self.s, self.i)
                at = fd.end() if fd else self.i
                op = self._operator(at)
                if op and (fd is None or op in REDIRECTIONS):
                    self.i = at + len(op)
                    parens += {"(": 1, ")": -1}.get(op, 0)
                    out.append(self._redirect(op, fd.group(0) if fd else "") if op in REDIRECTIONS
                               else Tok("op", op))
                else:
                    out.append(Tok("word", word=self._word()))

    def _operator(self, at: int) -> str:
        for op in OPERATORS:
            if self.s.startswith(op, at):
                if op in ("<", ">") and self.s.startswith("(", at + 1):
                    return ""
                return op
        return ""

    def _redirect(self, op: str, fd: str) -> Tok:
        if op not in ("<<", "<<-"):
            return Tok("redir", op, fd=fd)
        while self._peek() in (" ", "\t"):
            self.i += 1
        delim = self._word()
        if not delim.parts:
            raise ParseError("a heredoc has no end marker")
        doc = {"delim": "".join(p.text for p in delim.parts), "quoted": any(p.quoted for p in delim.parts),
               "strip": op == "<<-", "body": Word([])}
        self.pending.append(doc)
        return Tok("redir", op, word=delim, fd=fd, heredoc=doc)

    def _heredocs(self) -> None:
        for doc in self.pending:
            lines = []
            while self.i < len(self.s):
                end = self.s.find("\n", self.i)
                end = len(self.s) if end < 0 else end
                line = self.s[self.i:end]
                self.i = min(end + 1, len(self.s))
                if (line.lstrip("\t") if doc["strip"] else line) == doc["delim"]:
                    break
                lines.append(line)
            body = "\n".join(lines)
            if doc["quoted"]:
                doc["body"] = Word([Part("lit", body, quoted=True)])
            else:
                doc["body"] = Word(Lexer(body, self.depth + 1).body_parts())
        self.pending = []

    # ---- words

    def _word(self) -> Word:
        parts: list[Part] = []

        def lit(text: str, quoted: bool) -> None:
            if parts and parts[-1].kind == "lit" and parts[-1].quoted == quoted:
                parts[-1].text += text
            else:
                parts.append(Part("lit", text, quoted))

        while self.i < len(self.s):
            c = self.s[self.i]
            if c in " \t\r\n|&;()":
                break
            if c in "<>":
                if self._peek(1) == "(" and not parts:
                    self.i += 2
                    parts.append(Part("sub", script=self._nested(), how=c + "("))
                    continue
                break
            if c == "\\":
                nxt = self._peek(1)
                if nxt == "\n":
                    self.i += 2
                elif nxt == "":
                    lit("\\", True)
                    self.i += 1
                else:
                    lit(nxt, True)
                    self.i += 2
            elif c == "'":
                end = self.s.find("'", self.i + 1)
                if end < 0:
                    raise ParseError("a ' quote is never closed")
                lit(self.s[self.i + 1:end], True)
                self.i = end + 1
            elif c == '"':
                self.i += 1
                self._dquote(parts, lit)
            elif c == "$":
                self._dollar(parts, lit, quoted=False)
            elif c == "`":
                self._backtick(parts)
            elif c == "~" and not parts:
                m = TILDE.match(self.s, self.i)
                parts.append(Part("tilde", m.group(1)))
                self.i = m.end()
            else:
                lit(c, False)
                self.i += 1
        return Word(parts)

    def _dquote(self, parts: list[Part], lit) -> None:
        empty = True
        while True:
            c = self._peek()
            if c == "":
                raise ParseError('a " quote is never closed')
            if c == '"':
                self.i += 1
                if empty:
                    lit("", True)
                return
            empty = False
            if c == "\\" and self._peek(1) in ("$", "`", '"', "\\", "\n"):
                if self._peek(1) != "\n":
                    lit(self._peek(1), True)
                self.i += 2
            elif c == "$":
                self._dollar(parts, lit, quoted=True)
            elif c == "`":
                self._backtick(parts)
            else:
                lit(c, True)
                self.i += 1

    def body_parts(self) -> list[Part]:
        """A heredoc body or the inside of ${...}: literal text and its substitutions."""
        parts: list[Part] = []

        def lit(text: str, quoted: bool = True) -> None:
            if parts and parts[-1].kind == "lit":
                parts[-1].text += text
            else:
                parts.append(Part("lit", text, True))

        while self.i < len(self.s):
            c = self.s[self.i]
            if c == "\\" and self._peek(1) in ("$", "`", "\\"):
                lit(self._peek(1))
                self.i += 2
            elif c == "$":
                self._dollar(parts, lit, quoted=True)
            elif c == "`":
                self._backtick(parts)
            else:
                lit(c)
                self.i += 1
        return parts

    def _nested(self) -> list:
        """The commands of a `$(`, `<(` or `>(` whose opening was just read."""
        if self.depth + 1 > MAX_DEPTH:
            raise ParseError("commands are nested too deeply")
        sub = Lexer(self.s, self.depth + 1, self.i)
        toks = sub.tokens(close=True)
        self.i = sub.i
        return Parser(toks, self.depth + 1).parse()

    def _dollar(self, parts: list[Part], lit, quoted: bool) -> None:
        nxt = self._peek(1)
        if self.s.startswith("$((", self.i):
            depth, j = 2, self.i + 3
            while j < len(self.s) and depth:
                depth += {"(": 1, ")": -1}.get(self.s[j], 0)
                j += 1
            if depth:
                raise ParseError("an arithmetic $(( is never closed")
            parts.append(Part("arith", quoted=quoted))
            inner = self.s[self.i + 3:j - 2]
            parts.extend(p for p in Lexer(inner, self.depth + 1).body_parts() if p.kind == "sub")
            self.i = j
        elif nxt == "(":
            self.i += 2
            parts.append(Part("sub", quoted=quoted, script=self._nested(), how="$("))
        elif nxt == "{":
            depth, j = 1, self.i + 2
            while j < len(self.s) and depth:
                ch = self.s[j]
                if ch == "\\":
                    j += 1
                elif ch == "{" and self.s[j - 1] == "$":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                j += 1
            if depth:
                raise ParseError("a ${ is never closed")
            inner = self.s[self.i + 2:j - 1]
            m = re.match(r"[#!]?([A-Za-z_][A-Za-z0-9_]*|[@*#?$!0-9-])", inner)
            name = m.group(1) if m else ""
            if inner.startswith("!") or not m or len(inner) > m.end():
                name = "?" + name  # indirection, or an operator like ${x:-...}: value unknown
            parts.append(Part("var", name, quoted))
            rest = inner[m.end():] if m else inner
            parts.extend(p for p in Lexer(rest, self.depth + 1).body_parts() if p.kind == "sub")
            self.i = j
        elif nxt and (nxt.isalpha() or nxt == "_"):
            m = NAME.match(self.s, self.i + 1)
            parts.append(Part("var", m.group(0), quoted))
            self.i = m.end()
        elif nxt and nxt in SPECIAL_VARS:
            parts.append(Part("var", nxt, quoted))
            self.i += 2
        elif nxt == "'" and not quoted:
            self.i += 2
            lit(self._ansi(), True)
        elif nxt == '"' and not quoted:
            self.i += 2
            self._dquote(parts, lit)
        else:
            lit("$", quoted)
            self.i += 1

    def _ansi(self) -> str:
        out = []
        while True:
            c = self._peek()
            if c == "":
                raise ParseError("a $' quote is never closed")
            self.i += 1
            if c == "'":
                return "".join(out)
            if c != "\\":
                out.append(c)
                continue
            e = self._peek()
            self.i += 1
            if e in ANSI:
                out.append(ANSI[e])
            elif e and e in "01234567":
                m = re.compile(r"[0-7]{0,2}").match(self.s, self.i)
                out.append(chr(int(e + m.group(0), 8) % 256))
                self.i = m.end()
            elif e and e in "xuU":
                size = {"x": 2, "u": 4, "U": 8}[e]
                m = re.compile(rf"[0-9A-Fa-f]{{1,{size}}}").match(self.s, self.i)
                if m:
                    out.append(chr(min(int(m.group(0), 16), 0x10FFFF)))
                    self.i = m.end()
                else:
                    out.append("\\" + e)
            elif e == "c" and self._peek():
                out.append(chr(ord(self._peek()) & 0x1F))
                self.i += 1
            else:
                out.append("\\" + e)

    def _backtick(self, parts: list[Part]) -> None:
        j, out = self.i + 1, []
        while True:
            if j >= len(self.s):
                raise ParseError("a ` quote is never closed")
            ch = self.s[j]
            if ch == "\\" and j + 1 < len(self.s) and self.s[j + 1] in "`$\\":
                out.append(self.s[j + 1])
                j += 2
            elif ch == "`":
                break
            else:
                out.append(ch)
                j += 1
        self.i = j + 1
        parts.append(Part("sub", script=parse("".join(out), self.depth + 1), how="`"))


# ---------------------------------------------------------------- parser


class Parser:
    def __init__(self, toks: list[Tok], depth: int = 0):
        self.t, self.k, self.depth = toks, 0, depth

    def _peek(self, n: int = 0) -> Tok | None:
        j = self.k + n
        return self.t[j] if j < len(self.t) else None

    @staticmethod
    def _is(tok: Tok | None, kind: str, text: str | None = None) -> bool:
        if tok is None or tok.kind != kind:
            return False
        if text is None:
            return True
        return (tok.word.plain() if kind == "word" else tok.text) == text

    def _expect_word(self, text: str) -> None:
        if not self._is(self._peek(), "word", text):
            raise ParseError(f"`{text}` is missing")
        self.k += 1

    def _newlines(self) -> None:
        while self._is(self._peek(), "op", "\n"):
            self.k += 1

    def parse(self) -> list:
        body = self.list(set())
        tok = self._peek()
        if tok is not None:
            raise ParseError(f"unexpected `{tok.text or (tok.word and tok.word.plain()) or '...'}`")
        return body

    def list(self, stop: set[str]) -> list:
        items: list = []
        while True:
            tok = self._peek()
            if tok is None:
                return items
            if tok.kind == "op" and tok.text in (")", ";;", ";&", ";;&"):
                return items
            if tok.kind == "word" and tok.word.plain() in stop:
                return items
            if tok.kind == "op" and tok.text in ("\n", ";"):
                self.k += 1
                continue
            if tok.kind == "op" and tok.text == "&":
                self.k += 1
                for item in items[-1:]:
                    item.background = True
                continue
            if tok.kind == "op" and tok.text != "(":
                raise ParseError(f"unexpected `{tok.text}`")
            items.append(self.pipeline())
            while self._is(self._peek(), "op", "&&") or self._is(self._peek(), "op", "||"):
                op = self._peek().text
                self.k += 1
                self._newlines()
                items.append(self.pipeline())
                items[-1].joined = op

    def pipeline(self) -> Pipeline:
        while self._is(self._peek(), "word", "!") or self._is(self._peek(), "word", "time"):
            self.k += 1
            if self._is(self._peek(), "word", "-p"):
                self.k += 1
        stages = [self.command()]
        while self._is(self._peek(), "op", "|") or self._is(self._peek(), "op", "|&"):
            self.k += 1
            self._newlines()
            stages.append(self.command())
        return Pipeline(stages)

    def _redirects(self) -> list[Redirect]:
        out = []
        while self._is(self._peek(), "redir"):
            out.append(self._redirect())
        return out

    def _redirect(self) -> Redirect:
        tok = self._peek()
        self.k += 1
        if tok.heredoc is not None:
            return Redirect(tok.text, tok.fd, tok.word, tok.heredoc["body"])
        target = self._peek()
        if not self._is(target, "word"):
            raise ParseError(f"`{tok.text}` has no target")
        self.k += 1
        return Redirect(tok.text, tok.fd, target.word)

    def command(self):
        tok = self._peek()
        if tok is None:
            raise ParseError("a command is missing")
        if self._is(tok, "op", "("):
            self.k += 1
            body = self.list(set())
            if not self._is(self._peek(), "op", ")"):
                raise ParseError("a `(` is never closed")
            if not body:
                raise ParseError("`()` holds no command")
            self.k += 1
            return Group(body, True, self._redirects())
        if tok.kind == "op":
            raise ParseError(f"unexpected `{tok.text}`")
        word = tok.word.plain() if tok.kind == "word" else None
        if word == "{":
            self.k += 1
            body = self.list({"}"})
            self._expect_word("}")
            return Group(body, False, self._redirects())
        if word == "if":
            return self._if()
        if word in ("while", "until"):
            self.k += 1
            body = self.list({"do"})
            self._expect_word("do")
            body += self.list({"done"})
            self._expect_word("done")
            return Group(body, False, self._redirects())
        if word in ("for", "select"):
            return self._for()
        if word == "case":
            return self._case()
        if word == "function":
            self.k += 1
            name = self._peek()
            if not self._is(name, "word"):
                raise ParseError("a function has no name")
            self.k += 1
            if self._is(self._peek(), "op", "(") and self._is(self._peek(1), "op", ")"):
                self.k += 2
            self._newlines()
            return Function(name.word.plain() or "", self.command())
        if (word and self._is(self._peek(1), "op", "(")
                and self._is(self._peek(2), "op", ")")):
            self.k += 3
            self._newlines()
            return Function(word, self.command())
        if word == "[[":
            words = []
            self.k += 1
            while not self._is(self._peek(), "word", "]]"):
                nxt = self._peek()
                if nxt is None:
                    raise ParseError("a `[[` is never closed")
                if nxt.kind == "word":
                    words.append(nxt.word)
                self.k += 1
            self.k += 1
            return Simple(words, data=True)
        if word in CLOSERS:
            raise ParseError(f"unexpected `{word}`")
        return self._simple()

    def _if(self) -> Group:
        self.k += 1
        body = self.list({"then"})
        self._expect_word("then")
        body += self.list({"elif", "else", "fi"})
        while self._is(self._peek(), "word", "elif"):
            self.k += 1
            body += self.list({"then"})
            self._expect_word("then")
            body += self.list({"elif", "else", "fi"})
        if self._is(self._peek(), "word", "else"):
            self.k += 1
            body += self.list({"fi"})
        self._expect_word("fi")
        return Group(body, False, self._redirects())

    def _for(self) -> Group:
        self.k += 1
        body: list = []
        if self._is(self._peek(), "op", "("):
            words = []
            while not (self._is(self._peek(), "op", ")") and self._is(self._peek(1), "op", ")")):
                nxt = self._peek()
                if nxt is None:
                    raise ParseError("a `for ((` is never closed")
                if nxt.kind == "word":
                    words.append(nxt.word)
                self.k += 1
            self.k += 2
            body.append(Pipeline([Simple(words, data=True)]))
        else:
            if not self._is(self._peek(), "word"):
                raise ParseError("a `for` has no variable")
            name = self._peek().word.plain() or ""
            self.k += 1
            self._newlines()
            words: list[Word] = []
            if self._is(self._peek(), "word", "in"):
                self.k += 1
                while self._is(self._peek(), "word"):
                    words.append(self._peek().word)
                    self.k += 1
            body.append(Pipeline([Simple(words, data=True)]))
            if NAME.fullmatch(name):
                # one word (a glob, say) gives the loop variable a known shape; several stay unknown
                value = words[0] if len(words) == 1 else Word([Part("var", "?")])
                body.append(Pipeline([Simple([], assigns=[(name, value)])]))
        while self._is(self._peek(), "op", ";") or self._is(self._peek(), "op", "\n"):
            self.k += 1
        self._expect_word("do")
        body += self.list({"done"})
        self._expect_word("done")
        return Group(body, False, self._redirects())

    def _case(self) -> Group:
        self.k += 1
        subject = self._peek()
        if not self._is(subject, "word"):
            raise ParseError("a `case` has no subject")
        self.k += 1
        body: list = [Pipeline([Simple([subject.word], data=True)])]
        self._newlines()
        self._expect_word("in")
        self._newlines()
        while not self._is(self._peek(), "word", "esac"):
            if self._peek() is None:
                raise ParseError("a `case` is never closed")
            if self._is(self._peek(), "op", "("):
                self.k += 1
            while not self._is(self._peek(), "op", ")"):
                if self._peek() is None:
                    raise ParseError("a `case` pattern is never closed")
                self.k += 1
            self.k += 1
            body += self.list({"esac"})
            tok = self._peek()
            if tok is not None and tok.kind == "op" and tok.text in (";;", ";&", ";;&"):
                self.k += 1
            self._newlines()
        self.k += 1
        return Group(body, False, self._redirects())

    def _simple(self) -> Simple:
        cmd = Simple([])
        while True:
            tok = self._peek()
            if tok is None:
                break
            if tok.kind == "redir":
                cmd.redirects.append(self._redirect())
            elif tok.kind == "word":
                self.k += 1
                first = tok.word.parts[0] if tok.word.parts else None
                m = (ASSIGNMENT.match(first.text) if first and first.kind == "lit" and not first.quoted
                     else None)
                if not cmd.words and m:
                    rest = Part("lit", first.text[m.end():], first.quoted)
                    value = Word(([rest] if rest.text else []) + tok.word.parts[1:])
                    if not value.parts and self._is(self._peek(), "op", "("):
                        value = Word(self._array())  # NAME=(a b c)
                    cmd.assigns.append((m.group(1), value))
                else:
                    cmd.words.append(tok.word)
            else:
                break
        if not (cmd.words or cmd.assigns or cmd.redirects):
            raise ParseError("a command is missing")
        return cmd

    def _array(self) -> list[Part]:
        self.k += 1
        parts: list[Part] = []
        while not self._is(self._peek(), "op", ")"):
            tok = self._peek()
            if tok is None:
                raise ParseError("an array `(` is never closed")
            if tok.kind == "word":
                parts += [p for p in tok.word.parts if p.kind == "sub"]
            self.k += 1
        self.k += 1
        return parts or [Part("lit", "", True)]
