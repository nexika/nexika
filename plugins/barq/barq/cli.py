"""barq command line: parse short or JSON requests, run them (in parallel when safe), render."""
from __future__ import annotations

import difflib
import inspect
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import __version__, files, ops_git, ops_project, ops_read, ops_search, stats
from .cache import Cache
from .core import READ, Context, OpError, OpSpec, Result
from .mask import mask_text

BUILTIN: list[OpSpec] = [*ops_read.OPS, *ops_search.OPS, *ops_project.OPS, *ops_git.OPS, *stats.OPS]
UNLOGGED = {"stats"}
MAX_WORKERS = 8

USAGE = """barq {version} - many file/project operations in one call (Nexika)

usage:
  barq OP [OP ...]                       short form: op:arg:arg
  barq '[{{"op":"grep","pattern":"a:b"}}]'  JSON form (args with ':' or spaces), or - for stdin
  barq ops | barq help OP | barq version
options:
  --json    machine-readable output     --fresh   ignore the seen-before cache

examples:
  barq read:src/app.py grep:TODO:src git-status
  barq read:Services/Auth.cs@Login map:src/Api run:test
"""


def load_config(root: Path) -> tuple[dict, str]:
    path = root / ".barq.json"
    if not path.exists():
        return {}, ""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return (data if isinstance(data, dict) else {}), ""
    except (OSError, ValueError) as exc:
        return {}, f"warning: ignoring invalid .barq.json ({exc})"


def registry(config: dict) -> dict[str, OpSpec]:
    specs = {s.name: s for s in BUILTIN}
    for spec in ops_project.custom_specs(config, set(specs)):
        specs[spec.name] = spec
    return specs


def parse_requests(args: list[str], specs: dict[str, OpSpec]) -> list[tuple[str, dict] | Result]:
    """Each item is (op name, kwargs) or an error Result for a request that can't run."""
    if len(args) == 1 and args[0] == "-":
        args = [sys.stdin.read()]
    if len(args) == 1 and args[0].lstrip()[:1] in ("[", "{"):
        try:
            data = json.loads(args[0])
        except ValueError as exc:
            return [Result("json", f"invalid JSON input: {exc}", ok=False)]
        items = data if isinstance(data, list) else [data]
        out: list = []
        for item in items:
            if not isinstance(item, dict) or "op" not in item:
                out.append(Result("json", f'each request needs an "op": {item!r}', ok=False))
                continue
            kwargs = {k: v for k, v in item.items() if k != "op"}
            out.append((str(item["op"]), kwargs))
        return out
    out = []
    for arg in args:
        name, *parts = arg.split(":")
        spec = specs.get(name)
        if spec is None:
            out.append((name, {}))  # reported as unknown at run time
            continue
        try:
            out.append((name, spec.parse(parts)))
        except OpError as exc:
            out.append(Result(name, str(exc), ok=False))
    return out


def _unknown(name: str, specs: dict[str, OpSpec]) -> Result:
    close = difflib.get_close_matches(name, specs, n=3)
    hint = f" Did you mean: {', '.join(close)}?" if close else " Run `barq ops` to list ops."
    return Result(name, f"unknown op '{name}'.{hint}", ok=False)


def run_one(spec: OpSpec, kwargs: dict, ctx: Context) -> Result:
    try:
        inspect.signature(spec.func).bind(ctx, **kwargs)
    except TypeError as exc:
        return Result(spec.name, f"bad arguments for {spec.name}: {exc}. Usage: {spec.usage}", ok=False)
    try:
        result = spec.func(ctx, **kwargs)
    except (OpError, files.FenceError) as exc:
        return Result(spec.name, str(exc), ok=False)
    except Exception as exc:  # an op bug must not hide the other ops' results
        if os.environ.get("BARQ_DEBUG"):
            raise
        return Result(spec.name, f"internal error: {type(exc).__name__}: {exc}", ok=False)
    if not result.masked:
        result.text = mask_text(result.text)[0]
    return result


def execute(requests: list, specs: dict[str, OpSpec], ctx: Context) -> list[Result]:
    jobs: list = []
    for req in requests:
        if isinstance(req, Result):
            jobs.append(req)
        elif req[0] not in specs:
            jobs.append(_unknown(req[0], specs))
        else:
            jobs.append((specs[req[0]], req[1]))
    runnable = [j for j in jobs if not isinstance(j, Result)]
    parallel = len(runnable) > 1 and all(spec.safety == READ for spec, _ in runnable)
    if parallel:
        with ThreadPoolExecutor(max_workers=min(MAX_WORKERS, len(runnable))) as pool:
            futures = {id(j): pool.submit(run_one, j[0], j[1], ctx) for j in runnable}
            return [j if isinstance(j, Result) else futures[id(j)].result() for j in jobs]
    return [j if isinstance(j, Result) else run_one(j[0], j[1], ctx) for j in jobs]


def render(results: list[Result], as_json: bool) -> str:
    if as_json:
        return json.dumps([{"label": r.label, "ok": r.ok, "hit": r.hit, "text": r.text}
                           for r in results], ensure_ascii=False, indent=1)
    blocks = []
    for r in results:
        title = r.label if r.ok else f"{r.label} [ERROR]"
        blocks.append(f"=== {title} ===\n{r.text}")
    return "\n\n".join(blocks)


def _list_ops(specs: dict[str, OpSpec]) -> str:
    width = max(len(s.usage) for s in specs.values())
    return "\n".join(f"{s.usage:<{width}}  {s.summary}" for s in specs.values())


def main(argv: list[str]) -> int:
    as_json = "--json" in argv
    fresh = "--fresh" in argv
    args = [a for a in argv if a not in ("--json", "--fresh")]
    cwd = Path.cwd()
    root = files.project_root(str(cwd))
    config, warning = load_config(root)
    specs = registry(config)

    if not args or args[0] in ("-h", "--help"):
        print(USAGE.format(version=__version__))
        return 0 if args else 2
    if args[0] in ("version", "--version"):
        print(f"barq {__version__}")
        return 0
    if args[0] == "ops":
        print(_list_ops(specs))
        return 0
    if args[0] == "help":
        name = args[1] if len(args) > 1 else ""
        spec = specs.get(name)
        print(f"{spec.usage}\n  {spec.summary}" if spec else _unknown(name, specs).text)
        return 0 if spec else 2

    session = os.environ.get("BARQ_SESSION", "")
    ctx = Context(cwd=cwd, root=root, cache=Cache(session), config=config, fresh=fresh)
    started = time.monotonic()
    requests = parse_requests(args, specs)
    results = execute(requests, specs, ctx)
    ctx.cache.save()

    output = render(results, as_json)
    if warning:
        output = f"{warning}\n\n{output}"
    sys.stdout.write(output + "\n")

    names = [req.label if isinstance(req, Result) else req[0] for req in requests]
    logged = [
        {"op": names[i], "out": len(r.text.encode("utf-8")), "baseline": r.baseline, "hit": r.hit}
        for i, r in enumerate(results) if names[i] not in UNLOGGED
    ]
    if logged:
        try:
            stats.record(logged, int((time.monotonic() - started) * 1000), session, str(cwd))
        except OSError:
            pass
    return 0 if all(r.ok for r in results) else 1


def entry() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass
    sys.exit(main(sys.argv[1:]))
