"""Measure what barq saves: round-trips, bytes and (estimated) tokens."""
from __future__ import annotations

import datetime
import json
from collections import Counter
from pathlib import Path

from .cache import data_home
from .core import READ, Context, OpError, OpSpec, Result

BYTES_PER_TOKEN = 4
PERIODS = ("today", "week", "month", "all")


def log_path() -> Path:
    return data_home() / "stats.jsonl"


def record(ops: list[dict], ms: int, session: str, cwd: str) -> None:
    entry = {
        "ts": datetime.datetime.now().isoformat(timespec="seconds"),
        "session": session[:8], "cwd": cwd, "ms": ms, "ops": ops,
    }
    path = log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry) + "\n")


def _since(period: str) -> str:
    today = datetime.date.today()
    days = {"today": 0, "week": 6, "month": 29}.get(period)
    return "" if days is None else (today - datetime.timedelta(days=days)).isoformat()


def _kb(n: float) -> str:
    return f"{n / 1024 / 1024:.1f} MB" if abs(n) >= 1024 * 1024 else f"{n / 1024:.1f} KB"


def op_stats(ctx: Context, period: str = "today") -> Result:
    if period not in PERIODS:
        raise OpError(f"period must be one of: {', '.join(PERIODS)}")
    since = _since(period)
    calls = ops = trips = sent = saved = hits = 0
    by_op: Counter = Counter()
    try:
        lines = log_path().read_text(encoding="utf-8").splitlines()
    except OSError:
        lines = []
    for raw in lines:
        try:
            entry = json.loads(raw)
        except ValueError:
            continue
        if entry.get("ts", "")[:10] < since:
            continue
        calls += 1
        entry_ops = entry.get("ops") or []
        ops += len(entry_ops)
        trips += max(len(entry_ops) - 1, 0)
        for op in entry_ops:
            out = op.get("out", 0)
            sent += out
            if op.get("baseline") is not None:
                gain = op["baseline"] - out   # negative when barq sent more than the built-in tool would
                saved += gain
                by_op[op.get("op", "?")] += gain
            hits += bool(op.get("hit"))
    if not calls:
        return Result(f"stats ({period})", "no barq calls recorded yet for this period")
    body = [
        f"calls: {calls}, ops: {ops} ({ops / calls:.1f} per call)",
        f"round-trips saved: {trips}",
        f"output sent: {_kb(sent)}; avoided: {_kb(saved)} "
        f"(~{int(saved / BYTES_PER_TOKEN):,} tokens, estimated at {BYTES_PER_TOKEN} bytes/token)",
        f"seen-before cache: {hits} read(s) answered as unchanged or as a diff",
    ]
    if by_op:
        body.append("savings by op: " + ", ".join(f"{name} {_kb(v)}" for name, v in by_op.most_common(6)))
    return Result(f"stats ({period})", "\n".join(body))


OPS = [
    OpSpec("stats", op_stats, lambda parts: {"period": parts[0]} if parts and parts[0] else {},
           READ, "stats[:today|week|month|all]",
           "What barq saved: calls, round-trips, bytes and estimated tokens."),
]
