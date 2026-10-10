"""manar command line."""
from __future__ import annotations

import datetime
import json
import os
import re
import subprocess
import sys
import urllib.parse
from pathlib import Path

from . import __version__, aibots, checks, citability, crawl, fetch, framework, generate, status, visibility
from .checks import ORDER

USAGE = f"""manar {__version__} - be found by search engines and AI assistants, and measure it (Nexika)

  manar audit URL|FOLDER [--max-pages N] [--allow-local] [--base-url URL] [--json] [--fail-on SEVERITY]
  manar diff [TARGET]                          compare the last two audits of one site
  manar detect                                 web framework and where fixes go
  manar generate robots --origin URL [--block-training]
  manar generate sitemap|llms URL|FOLDER [--name N --summary S] [--base-url URL] [--allow-local]
  manar generate schema organization|website|software|sourcecode|article name=.. url=.. [same_as=a,b ...]
  manar visibility init|plan|run|report [--engines a,b] [--max-calls N]
"""


def project_root() -> Path:
    res = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True)
    return Path(res.stdout.strip()) if res.returncode == 0 else Path.cwd()


def repo_domain(remote: str) -> str:
    """host/path of a git remote, without credentials (https://user:token@host/... or git@host:...)."""
    remote = remote.strip().removesuffix(".git")
    if "://" not in remote and "@" in remote and ":" in remote:   # scp-like git@github.com:o/r
        host, _, path = remote.split("@", 1)[1].partition(":")
        return f"{host}/{path}".rstrip("/")
    parts = urllib.parse.urlsplit(remote)
    return f"{parts.hostname or ''}{parts.path}".rstrip("/")


def _flag(args: list[str], name: str, default: str | None = None) -> str | None:
    if name in args:
        i = args.index(name)
        if i + 1 < len(args):
            value = args[i + 1]
            del args[i:i + 2]
            return value
    return default


def _collect(target: str, args: list[str]) -> crawl.Site:
    base_url = _flag(args, "--base-url")
    allow_local = "--allow-local" in args
    max_pages = int(_flag(args, "--max-pages", "50"))
    if re.match(r"https?://", target):
        return crawl.crawl(target, max_pages=max_pages, allow_local=allow_local)
    folder = Path(target)
    if not folder.is_dir():
        raise SystemExit(f"manar: {target} is neither a URL nor a folder")
    return crawl.scan_folder(folder, base_url)


def run_audit(site: crawl.Site) -> dict:
    per_page = [checks.page_checks(p) for p in site.pages]
    site_findings = checks.site_checks(site.origin, site.home, site.robots_txt, site.sitemap_urls,
                                       site.sitemap_error, site.llms_txt, site.pages, complete=site.complete)
    allowed = aibots.access(site.robots_txt)
    pages = []
    for i, p in enumerate(site.pages):
        findings = per_page[i]
        cite, weakest = citability.page_score(p.blocks)
        pages.append({"url": p.url, "status": p.status, "title": p.title, "words": p.words,
                      "citability": cite, "weakest": weakest,
                      "issues": [{**f.to_dict(), "scope": "page"} for f in findings]})
    return {
        "version": __version__, "date": datetime.datetime.now().isoformat(timespec="seconds"),
        "target": site.origin, "score": checks.score(site_findings, per_page),
        "site": [{**f.to_dict(), "scope": "site"} for f in site_findings], "pages": pages,
        "skipped": site.skipped,
        "ai_bots": {b.name: {"kind": b.kind, "allowed": allowed[b.name]} for b in aibots.BOTS},
    }


def render(audit: dict) -> str:
    all_issues = audit["site"] + [i for p in audit["pages"] for i in p["issues"]]
    counts = {s: sum(1 for i in all_issues if i["severity"] == s) for s in ORDER}
    cites = [p["citability"] for p in audit["pages"] if p["words"] >= 50]
    lines = [
        f"manar audit: {audit['target']}  ({len(audit['pages'])} pages)",
        f"checklist score: {audit['score']}/100 (100 = no known problems; not a ranking prediction)",
        "issues: " + (", ".join(f"{n} {s}" for s, n in counts.items() if n) or "none"),
        f"citability (Estimated): average {round(sum(cites) / len(cites)) if cites else 0}/100 over "
        f"{len(cites)} content pages",
        "", "AI crawlers:",
    ]
    for kind, title in (("search+ai", "search engines"), ("search", "AI search"), ("user", "AI assistants"),
                        ("training", "AI training")):
        bots = [(n, b["allowed"]) for n, b in audit["ai_bots"].items() if b["kind"] == kind]
        lines.append(f"  {title:<15} " + "  ".join(f"{n} {'ok' if ok else 'BLOCKED'}" for n, ok in bots))
    by_id: dict[str, list[dict]] = {}
    for issue in sorted(all_issues, key=lambda i: ORDER.index(i["severity"])):
        by_id.setdefault(issue["id"], []).append(issue)
    lines += ["", "fix first:"]
    for items in list(by_id.values())[:15]:
        first = items[0]
        where = "site" if first.get("scope") == "site" else (
            f"{len(items)} page(s), e.g. {first['url']}" if len(items) > 1 else first["url"])
        lines.append(f"  [{first['severity']}] {first['message']}  ({where})\n      -> {first['fix']}")
    weak = [(p["url"], w) for p in audit["pages"] for w in p["weakest"] if w[0] < 50][:4]
    if weak:
        lines += ["", "least quotable passages (Estimated):"]
        lines += [f"  {s}/100 {url} > {h}: {'; '.join(why[:2])}" for url, (s, h, why) in weak]
    if audit["skipped"]:
        lines += ["", f"skipped {len(audit['skipped'])}: " + "; ".join(audit["skipped"][:3])]
    return "\n".join(lines)


def publish_score(root: Path, audit: dict, path: Path) -> None:
    """status/manar.json (nexika.manar/1): the last audit score per project, for mizan."""
    audits = status.read("manar").get("audits")
    audits = {k: v for k, v in audits.items() if os.path.isdir(k)} if isinstance(audits, dict) else {}
    audits[str(root)] = {"target": audit["target"], "score": audit["score"], "date": audit["date"],
                         "path": str(path)}
    status.publish("manar", {"audits": audits})


def cmd_audit(args: list[str]) -> int:
    as_json = "--json" in args
    args = [a for a in args if a != "--json"]
    fail_on = _flag(args, "--fail-on")
    if fail_on is not None and fail_on not in ORDER:
        print(f"manar: --fail-on takes one of {', '.join(ORDER)}")
        return 2
    site = _collect(args[0], args)
    if not site.pages:
        reason = f" ({site.skipped[0]})" if site.skipped else ""
        print(f"manar: no pages could be read from {args[0]}{reason}")
        return 1
    audit = run_audit(site)
    folder = project_root() / ".manar" / "audits"
    folder.mkdir(parents=True, exist_ok=True)
    ignore = folder.parent / ".gitignore"
    if not ignore.exists():  # audits hold crawled page data: keep them out of git by default
        ignore.write_text("audits/\n", encoding="utf-8")
    slug = re.sub(r"[^a-z0-9]+", "-", audit["target"].lower()).strip("-")
    stem = f"{audit['date'][:19].replace(':', '')}-{slug}"
    path, n = folder / f"{stem}.json", 2
    while path.exists():  # two audits in the same second must not overwrite each other
        path, n = folder / f"{stem}-{n}.json", n + 1
    path.write_text(json.dumps(audit, indent=1, ensure_ascii=False), encoding="utf-8")
    publish_score(project_root(), audit, path)
    print(json.dumps(audit, ensure_ascii=False) if as_json else render(audit) + f"\n\nsaved: {path}")
    if fail_on:   # CI mode: fail on findings this severe or worse
        worse = ORDER[: ORDER.index(fail_on) + 1]
        found = [i for i in audit["site"] + [i for p in audit["pages"] for i in p["issues"]]
                 if i["severity"] in worse]
        if found:
            if not as_json:
                print(f"manar: {len(found)} finding(s) at fail-on {fail_on} or worse")
            return 1
    return 0


def cmd_diff(args: list[str] | None = None) -> int:
    """The newest two audits of one site: the TARGET given, else the site audited last."""
    files = sorted((project_root() / ".manar" / "audits").glob("*.json"),
                   key=lambda f: (f.stat().st_mtime_ns, f.name))
    audits = []
    for f in files:
        try:
            audits.append(json.loads(f.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            continue
    target = (args[0] if args else audits[-1]["target"] if audits else "").rstrip("/")
    same = [a for a in audits if str(a.get("target", "")).rstrip("/") == target]
    if len(same) < 2:
        print(f"manar: need two audits of {target or 'the same site'} to compare (run manar audit twice)")
        return 1
    old, new = same[-2:]
    print(f"site: {target}")

    def keys(audit):
        return {(i["id"], i["url"]) for i in audit["site"] + [i for p in audit["pages"] for i in p["issues"]]}

    fixed, added = keys(old) - keys(new), keys(new) - keys(old)
    print(f"score {old['score']} -> {new['score']} ({new['score'] - old['score']:+d})  "
          f"[{old['date'][:10]} -> {new['date'][:10]}]")
    print(f"fixed {len(fixed)}: " + ", ".join(sorted({i for i, _ in fixed})[:10]))
    print(f"new {len(added)}: " + ", ".join(sorted({i for i, _ in added})[:10]))
    return 0


def cmd_generate(args: list[str]) -> int:
    kind = args[0] if args else ""
    rest = args[1:]
    if kind == "robots":
        origin = _flag(rest, "--origin") or "https://example.com"
        print(generate.robots_txt(origin, block_training="--block-training" in rest), end="")
    elif kind in ("sitemap", "llms") and rest:
        name = _flag(rest, "--name") or project_root().name
        summary = _flag(rest, "--summary") or "One-sentence description of what this is and who it is for."
        site = _collect(rest[0], rest)
        if kind == "sitemap":
            print(generate.sitemap_xml([p.url for p in site.pages if p.status < 400]), end="")
        else:
            print(generate.llms_txt(name, summary, site), end="")
    elif kind == "schema" and rest:
        fields = dict(a.split("=", 1) for a in rest[1:] if "=" in a)
        if "same_as" in fields:
            fields["same_as"] = [s.strip() for s in fields["same_as"].split(",")]
        print(generate.jsonld_script(generate.schema(rest[0], **fields)))
    else:
        print(USAGE)
        return 2
    return 0


def cmd_visibility(args: list[str]) -> int:
    action = args[0] if args else "report"
    root = project_root()
    panel_path, ledger = root / ".manar" / "panel.json", root / ".manar" / "visibility.jsonl"
    if action == "init":
        if panel_path.exists():
            print(f"{panel_path} already exists")
            return 0
        remote = subprocess.run(["git", "remote", "get-url", "origin"], capture_output=True, text=True,
                                cwd=root)
        domains = [repo_domain(remote.stdout)] if remote.stdout.strip() else []
        panel_path.parent.mkdir(parents=True, exist_ok=True)
        panel_path.write_text(json.dumps(visibility.panel_template(root.name, domains), indent=2,
                                         ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"wrote {panel_path}: set brand, aliases, domains and real customer questions")
        return 0
    if action == "report":
        runs = visibility.load_runs(ledger)
        if not runs:
            print("no measurements yet: manar visibility run")
            return 1
        panel = json.loads(panel_path.read_text(encoding="utf-8")) if panel_path.exists() else {}
        print(visibility.report(runs[-1], runs[-2] if len(runs) > 1 else None, panel.get("domains")))
        return 0
    if not panel_path.exists():
        print("manar: no .manar/panel.json yet: run manar visibility init")
        return 1
    panel = json.loads(panel_path.read_text(encoding="utf-8"))
    engines = visibility.available()
    wanted = _flag(args, "--engines")
    if wanted:
        engines = {k: v for k, v in engines.items() if k in wanted.split(",")}
    if not engines:
        print("manar: no AI engine key set. Set at least one: GEMINI_API_KEY (free tier, Google Search "
              "citations), PERPLEXITY_API_KEY, OPENAI_API_KEY or ANTHROPIC_API_KEY")
        return 1
    calls = len(panel["prompts"]) * len(engines) * int(panel.get("samples", 3))
    max_calls = int(_flag(args, "--max-calls", str(visibility.DEFAULT_MAX_CALLS)))
    plan = (f"{len(panel['prompts'])} prompts x {len(engines)} engines ({', '.join(engines)}) x "
            f"{panel.get('samples', 3)} samples = {calls} API calls")
    cost = calls / len(engines) * sum(visibility.COST_PER_CALL.get(e, 0.03) for e in engines)
    plan += f" (about ${cost:.2f}, a rough estimate: check each provider's prices)"
    if action == "plan":
        print(plan)
        return 0
    if calls > max_calls:
        print(f"manar: {plan} exceeds --max-calls {max_calls}; lower samples/prompts or raise the cap")
        return 1
    records = visibility.run(panel, engines, ref=visibility.git_ref(root))
    previous = visibility.load_runs(ledger)
    visibility.save(ledger, records)
    print(plan + "\n" + visibility.report(records, previous[-1] if previous else None, panel.get("domains")))
    return 0


def main(argv: list[str]) -> int:
    cmd, args = (argv[0], argv[1:]) if argv else ("", [])
    if cmd == "hook":
        from . import hook
        return hook.main(sys.stdin.read(), dict(os.environ))
    try:
        if cmd == "audit" and args:
            return cmd_audit(args)
        if cmd == "diff":
            return cmd_diff(args)
        if cmd == "detect":
            print(json.dumps(framework.detect(project_root()), indent=1))
            return 0
        if cmd == "generate":
            return cmd_generate(args)
        if cmd == "visibility":
            return cmd_visibility(args)
    except (ValueError, KeyError, fetch.FetchError) as exc:
        print(f"manar: {exc}", file=sys.stderr)
        return 1
    print(USAGE)
    return 0 if cmd in ("-h", "--help", "help") else 2


def entry() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass
    sys.exit(main(sys.argv[1:]))
