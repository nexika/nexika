"""read: full file (with the seen-before cache), line range, one symbol, or an outline."""
from __future__ import annotations

from pathlib import Path

from . import files
from .core import READ, Context, OpError, OpSpec, Result, int_arg
from .mask import mask_text
from .outline import SUPPORTED, find_symbol, outline

MAX_LINES = 1500
MAX_BYTES = 25_000   # Claude Code cuts tool output at about 30K characters: Claude never sees the rest
RANGE_DEFAULT = 200


def numbered(lines: list[str], first: int) -> str:
    return "\n".join(f"{n}\t{line}" for n, line in enumerate(lines, first))


def _split_lines(text: str) -> list[str]:
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    return lines


def _fits(lines: list[str]) -> int:
    """How many lines a full read can show: at most MAX_LINES and about MAX_BYTES of numbered text."""
    size = 0
    for n, line in enumerate(lines[:MAX_LINES]):
        size += len(line.encode("utf-8")) + len(str(n + 1)) + 2
        if size > MAX_BYTES:
            return max(n, 1)
    return min(len(lines), MAX_LINES)


def op_read(ctx: Context, path: str, start=None, end=None, symbol: str | None = None,
            mode: str | None = None) -> Result:
    p = files.resolve(path, ctx.cwd, ctx.root)
    try:
        raw = files.read_text(p)
    except files.FileError as exc:
        raise OpError(str(exc)) from None
    shown = files.rel(p, ctx.cwd)
    # raw: exact bytes, for editing (issue #22)
    text, n_masked = (raw, 0) if mode == "raw" else mask_text(raw, p.name)
    lines = _split_lines(text)
    total = len(lines)
    # what the built-in Read would have returned: the whole file, but capped like any tool output
    baseline = min(len(raw.encode("utf-8")), MAX_BYTES)
    masked_note = (f", {n_masked} secret(s) masked: don't copy [masked] lines into an edit,"
                   f" use read:{shown}:raw for exact text" if n_masked else "")

    if mode == "outline":
        symbols = outline(raw, p.suffix)
        if symbols is None:
            raise OpError(f"no outline support for '{p.suffix or p.name}' "
                          f"(supported: {' '.join(sorted(SUPPORTED))})")
        body = "\n".join(f"{s.line:>5}-{s.end:<5} {'  ' * s.depth}{s.signature}" for s in symbols)
        return Result(f"read {shown} (outline: {len(symbols)} symbols, {total} lines)",
                      body or "(no symbols found)", baseline=baseline, masked=True)

    if symbol:
        found = find_symbol(raw, p.suffix, symbol)
        if not found:
            names = [s.name for s in (outline(raw, p.suffix) or [])]
            hint = ", ".join(names[:30]) + (" ..." if len(names) > 30 else "")
            raise OpError(f"no symbol '{symbol}' in {shown}. Symbols: {hint or 'none found'}")
        parts = [numbered(lines[s.line - 1:s.end], s.line) for s in found]
        spans = ", ".join(f"{s.line}-{s.end}" for s in found)
        return Result(f"read {shown}@{symbol} (lines {spans} of {total}{masked_note})",
                      "\n...\n".join(parts), baseline=baseline, masked=True)

    if start is not None:
        first = max(1, int_arg(start, "start"))
        last = min(total, int_arg(end, "end") if end is not None else first + RANGE_DEFAULT - 1)
        if first > total:
            raise OpError(f"{shown} has only {total} lines")
        body = numbered(lines[first - 1:last], first)
        # Read with offset/limit returns the same lines: no saving beyond the round-trip
        return Result(f"read {shown} (lines {first}-{last} of {total}{masked_note})",
                      body, baseline=len(body.encode("utf-8")), masked=True)

    cut = _fits(lines)
    if cut < total:
        return Result(
            f"read {shown} (lines 1-{cut} of {total}{masked_note}, truncated)",
            numbered(lines[:cut], 1)
            + f"\n... {total - cut} more lines. Next: read:{shown}:{cut + 1}:{2 * cut}"
            f" or read:{shown}:outline",
            baseline=baseline, masked=True,
        )

    key = str(p)
    seen = mask_text(raw, p.name)[0]  # the cache compares masked text, whichever way it was read
    state, extra = ("new", None) if ctx.fresh or mode in ("full", "raw") else ctx.cache.check(key, seen)
    ctx.cache.remember(key, seen)
    if state == "unchanged":
        return Result(
            f"read {shown} (unchanged, {total} lines)",
            f"Unchanged since your read at {extra}. If that content is no longer in your context, "
            f"use read:{shown}:full",
            baseline=baseline, hit=True, masked=True,
        )
    if state == "changed" and extra:
        return Result(f"read {shown} (changed since your last read: diff, {total} lines now)",
                      extra.rstrip("\n"), baseline=baseline, hit=True, masked=True)
    return Result(f"read {shown} ({total} lines{masked_note})", numbered(lines, 1),
                  baseline=baseline, masked=True)


def parse_read(parts: list[str]) -> dict:
    if not parts or not parts[0]:
        raise OpError("usage: read:PATH[:START[:END]] | read:PATH@SYMBOL | read:PATH:outline|full|raw")
    path, rest = parts[0], parts[1:]
    out: dict = {"path": path}
    if "@" in path and not Path(path).exists():
        base, _, sym = path.rpartition("@")
        if base and sym:
            out.update(path=base, symbol=sym)
    if rest and rest[0] in ("outline", "full", "raw"):
        out["mode"] = rest[0]
    elif rest and rest[0]:
        out["start"] = rest[0]
        if len(rest) > 1 and rest[1]:
            out["end"] = rest[1]
    return out


OPS = [
    OpSpec("read", op_read, parse_read, READ,
           "read:PATH  read:PATH:START[:END]  read:PATH@SYMBOL  read:PATH:outline  read:PATH:full"
           "  read:PATH:raw",
           "Read a file. Repeated reads of unchanged files return a short notice, changed files "
           "a diff. @SYMBOL returns one class/function; outline returns signatures only; raw returns "
           "the exact text without secret masking."),
]
