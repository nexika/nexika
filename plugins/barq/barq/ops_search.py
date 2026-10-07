"""grep, glob, tree and map: find things across the project in one call."""
from __future__ import annotations

import fnmatch
import re
from pathlib import Path

from . import files
from .core import READ, Context, OpError, OpSpec, Result, int_arg
from .mask import mask_text
from .outline import SUPPORTED, outline

GREP_MAX_FILE = 2 * 1024 * 1024
GREP_SCAN_LIMIT = 20_000
TREE_MAX_LINES = 400


def _glob_match(relpath: str, pattern: str) -> bool:
    if fnmatch.fnmatch(relpath, pattern):
        return True
    if pattern.startswith("**/") and fnmatch.fnmatch(relpath, pattern[3:]):
        return True
    return "/" not in pattern and fnmatch.fnmatch(relpath.rsplit("/", 1)[-1], pattern)


def _files_under(ctx: Context, path: str, glob: str | None = None) -> tuple[Path, list[Path]]:
    base = files.resolve(path, ctx.cwd, ctx.root)
    if not base.exists():
        raise OpError(f"{path}: no such file or directory")
    found = files.list_files(base)
    if glob:
        found = [f for f in found if _glob_match(files.rel(f, base), glob)]
    return base, found


# ---------------------------------------------------------------- grep


def op_grep(ctx: Context, pattern: str, path: str = ".", max=50, ignore_case=False,
            glob: str | None = None) -> Result:
    limit = int_arg(max, "max")
    flags = re.IGNORECASE if ignore_case in (True, "i", "true", "1") else 0
    note = ""
    try:
        rx = re.compile(pattern, flags)
    except re.error as exc:
        rx = re.compile(re.escape(pattern), flags)
        note = f" (invalid regex: {exc}; searched as plain text)"
    _, candidates = _files_under(ctx, path, glob)
    hits: list[str] = []
    total = 0
    matched_files = 0
    baseline = 0
    for f in candidates:
        try:
            if f.stat().st_size > GREP_MAX_FILE:
                continue
            data = f.read_bytes()
        except OSError:
            continue
        if b"\0" in data[:8000]:
            continue
        shown = files.rel(f, ctx.cwd)
        file_hit = False
        for n, line in enumerate(data.decode("utf-8", "replace").split("\n"), 1):
            if rx.search(line):
                total += 1
                file_hit = True
                entry = f"{shown}:{n}: {line.strip()}"
                if len(hits) < limit:
                    shortened = entry if len(entry) <= 240 else entry[:237] + "..."
                    hits.append(mask_text(shortened, f.name)[0])
        matched_files += file_hit
        if file_hit:   # the built-in Grep returns matching file names by default
            baseline += len(shown) + 1
        if total >= GREP_SCAN_LIMIT:
            break
    label = f"grep /{pattern}/ in {path}: {total} matches in {matched_files} files{note}"
    if not hits:
        return Result(label, "(no matches)", baseline=baseline, masked=True)
    body = "\n".join(hits)
    if total > len(hits):
        body += f"\n... {total - len(hits)} more matches (narrow the path/glob or raise max)"
    return Result(label, body, baseline=baseline, masked=True)


def parse_grep(parts: list[str]) -> dict:
    if not parts or not parts[0]:
        raise OpError("usage: grep:REGEX[:PATH[:MAX]]  (use the JSON form for patterns with ':')")
    out: dict = {"pattern": parts[0]}
    if len(parts) > 1 and parts[1]:
        out["path"] = parts[1]
    if len(parts) > 2 and parts[2]:
        out["max"] = parts[2]
    return out


# ---------------------------------------------------------------- glob


def op_glob(ctx: Context, pattern: str, path: str = ".", max=200) -> Result:
    limit = int_arg(max, "max")
    base, found = _files_under(ctx, path, pattern)
    shown = [files.rel(f, ctx.cwd) for f in found]
    body = "\n".join(shown[:limit]) or "(no files)"
    if len(shown) > limit:
        body += f"\n... {len(shown) - limit} more"
    return Result(f"glob {pattern} in {path}: {len(shown)} files", body)


def parse_glob(parts: list[str]) -> dict:
    if not parts or not parts[0]:
        raise OpError("usage: glob:PATTERN[:PATH]   e.g. glob:**/*.cs")
    out: dict = {"pattern": parts[0]}
    if len(parts) > 1 and parts[1]:
        out["path"] = parts[1]
    return out


# ---------------------------------------------------------------- tree


def op_tree(ctx: Context, path: str = ".", depth=3) -> Result:
    max_depth = int_arg(depth, "depth")
    base, found = _files_under(ctx, path)
    root: dict = {}
    for f in found:
        node = root
        parts = files.rel(f, base).split("/")
        for part in parts[:-1]:
            node = node.setdefault(part + "/", {})
        node[parts[-1]] = None

    def count(node: dict) -> int:
        return sum(1 if v is None else count(v) for v in node.values())

    lines: list[str] = []

    def walk(node: dict, level: int) -> None:
        dirs = sorted(k for k, v in node.items() if v is not None)
        leaves = sorted(k for k, v in node.items() if v is None)
        for d in dirs:
            if level + 1 >= max_depth:
                lines.append(f"{'  ' * level}{d} ({count(node[d])} files)")
            else:
                lines.append(f"{'  ' * level}{d}")
                walk(node[d], level + 1)
        for leaf in leaves:
            lines.append(f"{'  ' * level}{leaf}")

    walk(root, 0)
    body = "\n".join(lines[:TREE_MAX_LINES]) or "(empty)"
    if len(lines) > TREE_MAX_LINES:
        body += f"\n... {len(lines) - TREE_MAX_LINES} more lines (lower depth or pick a subfolder)"
    return Result(f"tree {path} (depth {max_depth}, {len(found)} files)", body)


def parse_tree(parts: list[str]) -> dict:
    out: dict = {}
    if parts and parts[0]:
        out["path"] = parts[0]
    if len(parts) > 1 and parts[1]:
        out["depth"] = parts[1]
    return out


def parse_map(parts: list[str]) -> dict:
    return {"path": parts[0]} if parts and parts[0] else {}


# ---------------------------------------------------------------- map


def op_map(ctx: Context, path: str = ".", max_files=80, per_file=40) -> Result:
    limit, per = int_arg(max_files, "max_files"), int_arg(per_file, "per_file")
    _, found = _files_under(ctx, path)
    code = [f for f in found if f.suffix.lower() in SUPPORTED]
    lines: list[str] = []
    baseline = 0
    for f in code[:limit]:
        try:
            text = files.read_text(f)
        except files.FileError:
            continue
        baseline += len(text.encode("utf-8"))
        symbols = outline(text, f.suffix) or []
        if not symbols:
            continue
        lines.append(files.rel(f, ctx.cwd))
        for s in symbols[:per]:
            lines.append(f"  L{s.line} {'  ' * s.depth}{s.signature}")
        if len(symbols) > per:
            lines.append(f"  ... {len(symbols) - per} more symbols (read:{files.rel(f, ctx.cwd)}:outline)")
    body = "\n".join(lines) or "(no supported source files)"
    if len(code) > limit:
        body += f"\n... {len(code) - limit} more files (map a subfolder)"
    return Result(f"map {path}: {min(len(code), limit)} of {len(code)} source files", body,
                  baseline=baseline)


OPS = [
    OpSpec("grep", op_grep, parse_grep, READ, "grep:REGEX[:PATH[:MAX]]",
           "Regex search across the project (respects .gitignore). JSON form adds ignore_case, glob."),
    OpSpec("glob", op_glob, parse_glob, READ, "glob:PATTERN[:PATH]",
           "List files matching a pattern, e.g. glob:**/*.cs"),
    OpSpec("tree", op_tree, parse_tree, READ, "tree[:PATH[:DEPTH]]",
           "Directory tree; folders deeper than DEPTH (default 3) are summarized with file counts."),
    OpSpec("map", op_map, parse_map, READ, "map[:PATH]",
           "Outline of every source file under PATH: classes, functions and methods with line numbers."),
]
