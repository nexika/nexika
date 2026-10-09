"""Outlines and symbol extraction without third-party parsers.

Python uses the stdlib ast (exact). Brace languages (C#, Java, Kotlin, JS/TS, Go, Rust, C/C++,
PHP, Swift, Dart, Scala) use declaration regexes plus brace matching (good, not perfect).
Markdown uses headings.
"""
from __future__ import annotations

import ast
import re
from dataclasses import dataclass


@dataclass
class Symbol:
    name: str        # qualified, e.g. UserService.Login
    kind: str        # class, def, method, heading, ...
    line: int        # 1-based first line (decorators / attributes / doc comments included)
    end: int         # 1-based last line
    signature: str
    depth: int
    partial: bool = False   # the end could not be found for sure: the symbol may be cut short


PY_EXT = {".py", ".pyi"}
BRACE_EXT = {
    ".cs", ".java", ".kt", ".kts", ".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".go", ".rs",
    ".c", ".h", ".cc", ".cpp", ".cxx", ".hpp", ".hh", ".php", ".swift", ".dart", ".scala",
}
MD_EXT = {".md", ".markdown"}
SUPPORTED = PY_EXT | BRACE_EXT | MD_EXT

TYPE_KINDS = {"class", "interface", "struct", "enum", "record", "namespace", "trait", "impl",
              "object", "module", "type"}

_MODS = (
    r"(?:(?:public|private|protected|internal|static|abstract|sealed|partial|override|virtual|"
    r"async|export|default|final|readonly|unsafe|extern|inline|const|constexpr|new|open|data|"
    r"suspend|synchronized|declare|pub(?:\([^)]*\))?)\s+)*"
)
TYPE_RE = re.compile(
    r"^\s*" + _MODS + r"(?P<kind>class|interface|struct|enum|record|namespace|trait|impl|object|"
    r"module)\s+(?P<name>[A-Za-z_]\w*)"
)
GO_TYPE = re.compile(r"^\s*type\s+(?P<name>\w+)\s+(?:\[[^\]]*\]\s*)?(?P<kind>struct|interface)\b")
GO_FUNC = re.compile(r"^\s*func\s+(?:\((?P<recv>[^)]*)\)\s*)?(?P<name>\w+)\s*[\[(]")
GO_RECV_TYPE = re.compile(r"(\w+)\s*(?:\[[^\]]*\])?\s*$")   # (s *Server) -> Server, (l List[T]) -> List
KEYWORD_FUNC = re.compile(
    r"^\s*" + _MODS + r"(?:function\s*\*?|fun|func|fn|def)\s+(?:<[^>]*>\s*)?(?:[\w.]+\.)?"
    r"(?P<name>[A-Za-z_]\w*)"
)
JS_ARROW = re.compile(
    r"^\s*(?:export\s+)?(?:const|let|var)\s+(?P<name>\w+)\s*(?::[^=]+)?=\s*(?:async\s+)?"
    r"(?:\([^)]*\)|\w+)\s*(?::[^=]+)?=>"
)
JS_EXT = {".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx"}
# a function assigned to a property at the top level: Reply.prototype.send = function (payload) {,
# module.exports = function noopSet () {, X.prototype['y'] = async (a) => { (#272)
JS_ASSIGN_FUNC = re.compile(
    r"^(?P<target>[A-Za-z_$][\w$]*(?:\.[\w$]+|\[\s*['\"][^'\"\]]+['\"]\s*\])+)\s*=\s*(?:async\s+)?"
    r"(?:function\b\s*\*?\s*(?P<fname>[\w$]+)?|\([^)]*\)\s*=>|[\w$]+\s*=>)"
)
# class fields holding an arrow function: handleClick = (e) => {, private load = async () => {
JS_FIELD_ARROW = re.compile(
    r"^\s*" + _MODS + r"(?P<name>[A-Za-z_$][\w$]*)\s*(?::[^=]+)?=\s*(?:async\s+)?"
    r"(?:\([^)]*\)|\w+)\s*(?::[^=]+)?=>"
)
TS_TYPE_ALIAS = re.compile(
    r"^\s*(?:export\s+)?(?:declare\s+)?type\s+(?P<name>[A-Za-z_$][\w$]*)\s*(?:<.*>)?\s*="
)
# a generic alias whose parameters continue on the next lines: export type X<\n  A\n> = ... (#276)
TS_TYPE_ALIAS_OPEN = re.compile(
    r"^\s*(?:export\s+)?(?:declare\s+)?type\s+(?P<name>[A-Za-z_$][\w$]*)\s*<[^=]*$"
)
TS_EXT = {".ts", ".tsx", ".mts", ".cts"}
TS_BODYLESS_FUNC = re.compile(r"^\s*(?:export\s+)?declare\s+function\b")
# an interface member: a method signature (name(, name<T>(, [Symbol.x]() or a property (name?: T) (#277)
TS_MEMBER = re.compile(
    r"^\s*(?:readonly\s+)?(?P<name>[A-Za-z_$][\w$]*|\[[\w$.]+\])\s*\??\s*(?P<kind>[(<:])"
)
# a type goes on when a line ends with an operator, or the next line starts with one
_ENDS_OPEN = ("|", "&", "?", ":", "=", "=>", ",", "(", "[", "{", "<", "extends", "keyof")
_STARTS_MORE = ("|", "&", "?", ":", ".", "=", ">", "extends")
METHOD = re.compile(
    r"^\s*" + _MODS + r"(?:[\w<>\[\],.?:*&]+\s+)+(?P<name>[A-Za-z_]\w*)\s*(?:<[^>()]*>)?\s*\("
)
BARE_METHOD = re.compile(
    r"^\s*" + _MODS + r"(?:(?:get|set|static|async)\s+)*(?P<name>[A-Za-z_]\w*)\s*(?:<[^>()]*>)?\s*\("
)
NOT_NAMES = {
    "if", "for", "while", "switch", "catch", "using", "return", "foreach", "lock", "new", "else",
    "when", "sizeof", "typeof", "nameof", "fixed", "checked", "unchecked", "await", "throw",
    "yield", "case", "do", "try", "default", "super", "this", "base", "function", "delete",
    "import", "require", "match", "with", "var", "let", "const", "goto", "print", "assert",
}
STATEMENT_STARTS = ("return ", "await ", "throw ", "yield ", "else", "var ", "let ", "const ",
                    "new ", "case ", "using (", "using(", "#", "@", "[")

def _skip_quoted(line: str, k: int) -> int:
    """Index after the string starting at line[k], or k + 1 when it doesn't close on this line
    (a Rust lifetime, an apostrophe)."""
    quote, j = line[k], k + 1
    while j < len(line):
        if line[j] == "\\":
            j += 2
        elif line[j] == quote:
            return j + 1
        else:
            j += 1
    return k + 1


_REGEX_BEFORE = set("=(,:[!&|?{};+-*%~^")


def _regex_end(line: str, k: int, kept: list[str]) -> int:
    """Index after a JS regex literal starting at line[k], or -1 when the `/` is a division:
    a regex follows an operator, an opening bracket, `return`/`typeof`, or starts the line (#274)."""
    before = "".join(kept).rstrip()
    if before and before[-1] not in _REGEX_BEFORE and not re.search(r"\b(?:return|typeof)$", before):
        return -1
    j, in_class = k + 1, False
    while j < len(line):
        c = line[j]
        if c == "\\":
            j += 2
            continue
        if c == "[":
            in_class = True
        elif c == "]":
            in_class = False
        elif c == "/" and not in_class:
            j += 1
            while j < len(line) and line[j].isalpha():
                j += 1  # flags
            return j
        j += 1
    return -1


def _code_lines(lines: list[str], js: bool = False) -> list[str]:
    """Each line with strings as "", and comments and template literal text (also across lines,
    with their ${...} parts) removed: enough for brace counting and declaration matching."""
    out = []
    nest: list = []      # open template literals ("T") and ${...} parts (count of their own open braces)
    in_comment = False
    for line in lines:
        kept, k = [], 0
        while k < len(line):
            c = line[k]
            if in_comment:
                if line.startswith("*/", k):
                    in_comment, k = False, k + 2
                else:
                    k += 1
                continue
            if nest and nest[-1] == "T":
                if c == "\\":
                    k += 2
                elif c == "`":
                    nest.pop()
                    k += 1
                elif line.startswith("${", k):
                    nest.append(0)
                    k += 2
                else:
                    k += 1
                continue
            visible = not nest
            if c in "\"'":
                end = _skip_quoted(line, k)
                if visible:
                    kept.append('""' if end > k + 1 else c)
                k = end
                continue
            if line.startswith("//", k):
                break
            if line.startswith("/*", k):
                in_comment, k = True, k + 2
                continue
            if js and c == "/" and visible:
                end = _regex_end(line, k, kept)
                if end > 0:
                    kept.append('""')
                    k = end
                    continue
            if c == "`":
                if visible:
                    kept.append('""')
                nest.append("T")
            elif nest and c == "{":
                nest[-1] += 1
            elif nest and c == "}":
                if nest[-1]:
                    nest[-1] -= 1
                else:
                    nest.pop()   # back in the template text
            elif visible:
                kept.append(c)
            k += 1
        out.append("".join(kept))
    return out


def _signature(line: str) -> str:
    sig = line.strip().rstrip("{").rstrip()
    return sig if len(sig) <= 140 else sig[:137] + "..."


# ---------------------------------------------------------------- python


def _py_symbols(text: str) -> list[Symbol]:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return _indent_symbols(text)
    out: list[Symbol] = []

    def visit(body, prefix: str, depth: int, in_class: bool) -> None:
        for node in _py_defs(body):
            start = min([d.lineno for d in node.decorator_list] + [node.lineno])
            qual = prefix + node.name
            if isinstance(node, ast.ClassDef):
                bases = ", ".join(ast.unparse(b) for b in node.bases)
                sig = f"class {node.name}({bases})" if bases else f"class {node.name}"
                kind = "class"
            else:
                is_async = "async " if isinstance(node, ast.AsyncFunctionDef) else ""
                ret = f" -> {ast.unparse(node.returns)}" if node.returns else ""
                sig = f"{is_async}def {node.name}({_py_args(node.args)}){ret}"
                kind = "method" if in_class else "def"
            sig = _py_decorators(node.decorator_list) + sig
            out.append(Symbol(qual, kind, start, node.end_lineno or node.lineno, sig, depth))
            # nested functions and classes too: delimiter_split.append_to_line (#168)
            visit(node.body, qual + ".", depth + 1, isinstance(node, ast.ClassDef))

    visit(tree.body, "", 0, False)
    return out


def _py_defs(body):
    """def/class nodes in a body, also inside if/for/while/with/try blocks, in source order."""
    for node in body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            yield node
            continue
        for field in ("body", "orelse", "finalbody", "handlers", "cases"):
            inner = getattr(node, field, None)
            if isinstance(inner, list):
                yield from _py_defs(inner)


def _py_decorators(decorators) -> str:
    """A short tag: '@property ', '@click.command @click.option x27 +2 ' (#168)."""
    if not decorators:
        return ""
    counts: dict[str, int] = {}
    for d in decorators:
        name = ast.unparse(d.func if isinstance(d, ast.Call) else d)
        counts[name] = counts.get(name, 0) + 1
    shown = list(counts.items())[:3]
    tags = [f"@{name}" + (f" x{n}" if n > 1 else "") for name, n in shown]
    rest = len(decorators) - sum(n for _, n in shown)
    return " ".join(tags) + (f" +{rest}" if rest else "") + " "


def _py_args(args: ast.arguments) -> str:
    """Arguments as written in PEP 8 style: 'x=1', but 'color: bool = False'."""
    def one(arg: ast.arg, default) -> str:
        text = arg.arg + (f": {ast.unparse(arg.annotation)}" if arg.annotation else "")
        if default is not None:
            text += (" = " if arg.annotation else "=") + ast.unparse(default)
        return text

    positional = args.posonlyargs + args.args
    defaults = [None] * (len(positional) - len(args.defaults)) + list(args.defaults)
    parts = [one(a, d) for a, d in zip(positional, defaults, strict=True)]
    if args.posonlyargs:
        parts.insert(len(args.posonlyargs), "/")
    if args.vararg:
        parts.append("*" + one(args.vararg, None))
    elif args.kwonlyargs:
        parts.append("*")
    parts += [one(a, d) for a, d in zip(args.kwonlyargs, args.kw_defaults, strict=True)]
    if args.kwarg:
        parts.append("**" + one(args.kwarg, None))
    return ", ".join(parts)


_PY_DECL = re.compile(r"^(?P<indent>\s*)(?:async\s+)?(?P<kind>def|class)\s+(?P<name>\w+)")


def _indent_symbols(text: str) -> list[Symbol]:
    """Fallback for Python that doesn't parse: indentation decides where a block ends."""
    lines = text.split("\n")
    found = []
    for i, line in enumerate(lines):
        m = _PY_DECL.match(line)
        if m:
            found.append((i, len(m.group("indent")), m.group("kind"), m.group("name"), line))
    out = []
    for i, indent, kind, name, line in found:
        end = len(lines)
        for j in range(i + 1, len(lines)):
            stripped = lines[j].strip()
            if stripped and len(lines[j]) - len(lines[j].lstrip()) <= indent:
                end = j
                break
        while end > i + 1 and not lines[end - 1].strip():
            end -= 1
        out.append(Symbol(name, kind, i + 1, end, _signature(line), indent // 4))
    return out


# ---------------------------------------------------------------- brace languages


def _match_decl(code: str, nxt: str, suffix: str) -> tuple[str, str] | None:
    stripped = code.strip()
    m = JS_ARROW.match(code)
    if m:
        return "func", m.group("name")
    if not stripped or stripped.startswith(STATEMENT_STARTS):
        return None
    if suffix == ".go":
        m = GO_TYPE.match(code)
        if m:
            return m.group("kind"), m.group("name")
        m = GO_FUNC.match(code)
        if m and m.group("recv"):
            recv = GO_RECV_TYPE.search(m.group("recv").strip())
            return "method", (f"{recv.group(1)}." if recv else "") + m.group("name")
        if m:
            return "func", m.group("name")
        return None
    if suffix in JS_EXT:
        if stripped.startswith(("?", ":", ".")):
            return None  # a ternary branch or a chained call continues an expression
        m = TS_TYPE_ALIAS.match(code) or TS_TYPE_ALIAS_OPEN.match(code)
        if m:
            return "alias", m.group("name")
        m = JS_FIELD_ARROW.match(code)
        if m and m.group("name") not in NOT_NAMES:
            return "func", m.group("name")
        m = JS_PROP_FUNC.match(code)
        if m and (not m.group("arrow") or "{" in code[m.end():]):
            return "func", m.group("name")
    m = TYPE_RE.match(code)
    if m:
        return m.group("kind"), m.group("name")
    m = KEYWORD_FUNC.match(code)
    if m:
        return "func", m.group("name")
    m = None if suffix in JS_EXT else METHOD.match(code)  # `Type name(` is not JS (#275)
    if m and m.group("name") not in NOT_NAMES:
        before_paren = code[: code.index("(")]
        first_word = stripped.split()[0]
        if "=" not in before_paren and first_word not in NOT_NAMES:
            return "method", m.group("name")
    m = BARE_METHOD.match(code)
    if m and m.group("name") not in NOT_NAMES:
        tail = code.rstrip()
        opens_block = (tail.endswith(("{", "{}"))
                       or (tail.endswith(")") and nxt.strip().startswith("{")))
        if suffix in JS_EXT:
            opens_block = _js_body_follows(code) or (tail.endswith(")") and nxt.strip().startswith("{"))
        if opens_block and not tail.endswith(";"):
            return "method", m.group("name")
    return None


# an object-literal function property, named by its key: delete: function _delete (, closeRoutes: () => {
JS_PROP_FUNC = re.compile(
    r"^\s*(?P<name>[A-Za-z_$][\w$]*)\s*:\s*(?:async\s+)?(?:function\b|(?P<arrow>\([^)]*\)|[\w$]+)\s*=>)"
)


def _js_body_follows(code: str) -> bool:
    """A JS method head: the `(` after the name closes on this line and is followed (after a TS
    return type) by its body's `{`, so calls like `eos(res, function () {` are not taken (#275)."""
    k = code.find("(")
    depth = 0
    for c in range(k, len(code)):
        if code[c] == "(":
            depth += 1
        elif code[c] == ")":
            depth -= 1
            if depth == 0:
                return re.match(r"^\s*(?::[^{=;]+)?\{", code[c + 1:]) is not None
    return False


def _js_assigned(line: str) -> str | None:
    """The name of a top-level `a.b.c = function` assignment, with ['x'] written as .x."""
    m = JS_ASSIGN_FUNC.match(line)
    if not m:
        return None
    target = re.sub(r"\[\s*['\"]([^'\"\]]+)['\"]\s*\]", r".\1", m.group("target"))
    if target in ("module.exports", "exports.default") and m.group("fname"):
        return m.group("fname")
    return target


def _decl_start(lines: list[str], i: int) -> int:
    """Include attributes, decorators and doc comments directly above a declaration."""
    j = i
    while j > 0:
        prev = lines[j - 1].strip()
        if prev.startswith(("[", "@", "///", "/**", "*", "*/", "#[", "//")):
            j -= 1
        else:
            break
    return j


def _after_params(code: list[str], i: int) -> tuple[int, int]:
    """(line, column) just after the balanced parameter list that starts on line i, so a
    destructured or default-object parameter's braces are not taken for the body (#273)."""
    k = code[i].find("(")
    if k < 0 or ("{" in code[i][:k] and "=" not in code[i][:k]):
        return i, 0
    depth = 0
    for j in range(i, min(i + 30, len(code))):
        for c in range(k if j == i else 0, len(code[j])):
            ch = code[j][c]
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    return j, c + 1
    return i, 0


def _block_end(code: list[str], i: int, func: bool = False) -> tuple[int, bool]:
    """(0-based index of the line closing the block that starts at line i, sure)."""
    depth, opened = 0, False
    first, col = _after_params(code, i) if func else (i, 0)
    for j in range(first, len(code)):
        text = code[j][col:] if j == first else code[j]
        if not opened and "{" not in text and text.rstrip().endswith(";"):
            return j, True  # abstract / interface / expression-bodied member
        for ch in text:
            if ch == "{":
                depth += 1
                opened = True
            elif ch == "}":
                depth -= 1
                if opened and depth <= 0:
                    return j, True
    return min(i + 50, len(code) - 1), False


def _ts_expr_end(code: list[str], i: int, member: bool = False) -> tuple[int, bool]:
    """End line of a TS type alias or bodyless declaration starting at line i: the line where its
    brackets are balanced again and the next line does not continue the type, or a `;` (#276).
    An interface member also ends at a `,` outside brackets (#277)."""
    depth = 0
    for j in range(i, len(code)):
        text = code[j].replace("=>", "  ")
        for k, ch in enumerate(text):
            if ch in "([{":
                depth += 1
            elif ch in ")]}":
                depth -= 1
            elif ch == "<" and text[k + 1:k + 2] != "=":
                depth += 1
            elif ch == ">" and text[k + 1:k + 2] != "=" and depth > 0:
                depth -= 1
            elif (ch == ";" or (member and ch == ",")) and depth <= 0:
                return j, True
        tail = code[j].rstrip()
        if depth > 0 or not tail or tail.endswith(_ENDS_OPEN):
            continue
        nxt = next((c.strip() for c in code[j + 1:] if c.strip()), "")
        if not nxt.startswith(_STARTS_MORE):
            return j, True
    return min(i + 50, len(code) - 1), False


def _brace_symbols(text: str, suffix: str) -> list[Symbol]:
    lines = text.split("\n")
    out: list[Symbol] = []
    stack: list[list] = []  # [name, depth_at_declaration, opened, kind]
    depth = 0
    member_end = -1
    codes = _code_lines(lines, js=suffix in JS_EXT)
    for i, line in enumerate(lines):
        code = codes[i]
        nxt = codes[i + 1] if i + 1 < len(lines) else ""
        decl = None
        in_interface = (suffix in TS_EXT and stack and stack[-1][3] == "interface" and stack[-1][2]
                        and depth == stack[-1][1] + 1)
        if in_interface and i <= member_end:
            pass  # still inside the previous member or call signature: its parameters are not members
        elif in_interface and code.strip():
            m = TS_MEMBER.match(code)
            decl = (("property" if m.group("kind") == ":" else "method"), m.group("name")) if m else None
            member_end = _ts_expr_end(codes, i, member=True)[0]
        elif suffix in JS_EXT and depth == 0 and not stack:
            assigned = _js_assigned(line)
            decl = ("func", assigned) if assigned else None
        if decl is None and not in_interface and depth <= 4 and code.strip():
            decl = _match_decl(code, nxt, suffix)
        if decl:
            kind, name = decl
            qual = ".".join([s[0] for s in stack] + [name])
            if in_interface:
                end, sure = _ts_expr_end(codes, i, member=True)
            elif suffix in TS_EXT and (kind == "alias" or TS_BODYLESS_FUNC.match(code)):
                end, sure = _ts_expr_end(codes, i)
            else:
                end, sure = _block_end(codes, i, func=kind in ("func", "method"))
            out.append(Symbol(qual, kind, _decl_start(lines, i) + 1, end + 1, _signature(line), len(stack),
                              partial=not sure))
            if kind in TYPE_KINDS and end > i:  # a one-line type can't contain anything
                stack.append([name, depth, False, kind])
        depth += code.count("{") - code.count("}")
        for entry in stack:
            if depth > entry[1]:
                entry[2] = True
        while stack and stack[-1][2] and depth <= stack[-1][1]:
            stack.pop()
    return out


# ---------------------------------------------------------------- markdown


_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")


def _md_symbols(text: str) -> list[Symbol]:
    lines = text.split("\n")
    heads = []
    fence = False
    for i, line in enumerate(lines):
        if line.lstrip().startswith(("```", "~~~")):
            fence = not fence
            continue
        m = None if fence else _HEADING.match(line)
        if m:
            heads.append((i, len(m.group(1)), m.group(2)))
    out = []
    for n, (i, level, title) in enumerate(heads):
        end = len(lines)
        for j, lvl, _ in heads[n + 1:]:
            if lvl <= level:
                end = j
                break
        while end > i + 1 and not lines[end - 1].strip():
            end -= 1
        out.append(Symbol(title, "heading", i + 1, end, "#" * level + " " + title, level - 1))
    return out


# ---------------------------------------------------------------- public API


def outline(text: str, suffix: str) -> list[Symbol] | None:
    """Symbols of a file, or None when the language is not supported."""
    suffix = suffix.lower()
    if suffix in PY_EXT:
        return _py_symbols(text)
    if suffix in BRACE_EXT:
        return _brace_symbols(text, suffix)
    if suffix in MD_EXT:
        return _md_symbols(text)
    return None


def find_symbol(text: str, suffix: str, query: str) -> list[Symbol]:
    """Symbols matching query: exact qualified name, a dotted suffix, or a bare name."""
    symbols = outline(text, suffix) or []

    def matches(sym: Symbol, q: str, fold: bool) -> bool:
        names = {sym.name, sym.name.replace(".prototype.", ".")}  # @Reply.send finds Reply.prototype.send
        if fold:
            names, q = {n.lower() for n in names}, q.lower()
        return any(name == q or name.endswith("." + q) for name in names)

    exact = [s for s in symbols if matches(s, query, fold=False)]
    return exact or [s for s in symbols if matches(s, query, fold=True)]
