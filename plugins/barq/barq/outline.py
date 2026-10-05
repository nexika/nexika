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
KEYWORD_FUNC = re.compile(
    r"^\s*" + _MODS + r"(?:function\s*\*?|fun|func|fn|def)\s+(?:<[^>]*>\s*)?(?:[\w.]+\.)?"
    r"(?P<name>[A-Za-z_]\w*)"
)
JS_ARROW = re.compile(
    r"^\s*(?:export\s+)?(?:const|let|var)\s+(?P<name>\w+)\s*(?::[^=]+)?=\s*(?:async\s+)?"
    r"(?:\([^)]*\)|\w+)\s*(?::[^=]+)?=>"
)
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

_STRING = re.compile(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|`(?:\\.|[^`\\])*`')


def _code_only(line: str) -> str:
    """Line without string literals and // comments (enough for brace counting)."""
    line = _STRING.sub('""', line)
    cut = line.find("//")
    return line[:cut] if cut >= 0 else line


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

    def visit(body, prefix: str, depth: int) -> None:
        for node in body:
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            start = min([d.lineno for d in node.decorator_list] + [node.lineno])
            qual = prefix + node.name
            if isinstance(node, ast.ClassDef):
                bases = ", ".join(ast.unparse(b) for b in node.bases)
                sig = f"class {node.name}({bases})" if bases else f"class {node.name}"
                kind = "class"
            else:
                is_async = "async " if isinstance(node, ast.AsyncFunctionDef) else ""
                ret = f" -> {ast.unparse(node.returns)}" if node.returns else ""
                sig = f"{is_async}def {node.name}({ast.unparse(node.args)}){ret}"
                kind = "method" if depth else "def"
            out.append(Symbol(qual, kind, start, node.end_lineno or node.lineno, sig, depth))
            if isinstance(node, ast.ClassDef):
                visit(node.body, qual + ".", depth + 1)

    visit(tree.body, "", 0)
    return out


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
        if m:
            return ("method" if m.group("recv") else "func"), m.group("name")
        return None
    m = TYPE_RE.match(code)
    if m:
        return m.group("kind"), m.group("name")
    m = KEYWORD_FUNC.match(code)
    if m:
        return "func", m.group("name")
    m = METHOD.match(code)
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
        if opens_block and not tail.endswith(";"):
            return "method", m.group("name")
    return None


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


def _block_end(lines: list[str], i: int) -> int:
    """0-based index of the line closing the block that starts at line i."""
    depth, opened = 0, False
    for j in range(i, len(lines)):
        code = _code_only(lines[j])
        if not opened and "{" not in code and code.rstrip().endswith(";"):
            return j  # abstract / interface / expression-bodied member
        for ch in code:
            if ch == "{":
                depth += 1
                opened = True
            elif ch == "}":
                depth -= 1
                if opened and depth <= 0:
                    return j
    return min(i + 50, len(lines) - 1)


def _brace_symbols(text: str, suffix: str) -> list[Symbol]:
    lines = text.split("\n")
    out: list[Symbol] = []
    stack: list[list] = []  # [name, depth_at_declaration, opened]
    depth = 0
    in_block_comment = False
    for i, line in enumerate(lines):
        if in_block_comment:
            if "*/" in line:
                in_block_comment = False
            continue
        if line.strip().startswith("/*") and "*/" not in line:
            in_block_comment = True
            continue
        code = _code_only(line)
        nxt = lines[i + 1] if i + 1 < len(lines) else ""
        decl = _match_decl(code, nxt, suffix) if depth <= 4 else None
        if decl:
            kind, name = decl
            qual = ".".join([s[0] for s in stack] + [name])
            end = _block_end(lines, i)
            out.append(Symbol(qual, kind, _decl_start(lines, i) + 1, end + 1, _signature(line), len(stack)))
            if kind in TYPE_KINDS and end > i:  # a one-line type can't contain anything
                stack.append([name, depth, False])
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
        name = sym.name.lower() if fold else sym.name
        q = q.lower() if fold else q
        return name == q or name.endswith("." + q)

    exact = [s for s in symbols if matches(s, query, fold=False)]
    return exact or [s for s in symbols if matches(s, query, fold=True)]
