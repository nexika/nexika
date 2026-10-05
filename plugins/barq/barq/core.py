"""Shared types: the per-call context, op results and op specs."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from .cache import Cache

READ = "read"   # no side effects: may run in parallel with other read ops
EXEC = "exec"   # runs a program: always sequential


class OpError(Exception):
    """An op failed in a way the caller should read (bad input, nothing found, ...)."""


@dataclass
class Context:
    cwd: Path
    root: Path
    cache: Cache
    config: dict = field(default_factory=dict)
    fresh: bool = False


@dataclass
class Result:
    label: str
    text: str = ""
    ok: bool = True
    baseline: int | None = None  # bytes a plain tool call would have returned
    hit: bool = False            # served (fully or as a diff) from the seen-before cache
    masked: bool = False         # the op already masked its own output


@dataclass
class OpSpec:
    name: str
    func: Callable[..., Result]
    parse: Callable[[list[str]], dict]
    safety: str
    usage: str
    summary: str


def int_arg(value, name: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        raise OpError(f"{name} must be a number, got {value!r}") from None
