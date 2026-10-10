"""amin command line. There is deliberately no merge command: a human always merges."""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

from . import __version__, check, fragments, gitops, release, status, triage
from . import project as proj

USAGE = f"""amin {__version__} - repository maintainer; you always merge (Nexika)

  amin projects                          projects, versions, version files, last tags
  amin plan                              what would be released, from the change notes
  amin prepare [NAME[=VERSION] ...] [--rc | --pre[=LABEL]] [--umbrella] [--dry-run] [--allow-lower]
                                         bump versions, write CHANGELOGs, consume notes (then: a PR);
                                         --pre: the next alpha/beta/... (default: the project's own)
  amin publish NAME [--dry-run]          after the release PR is merged: checks, tag, GitHub Release
  amin fragment add NAME TYPE TEXT [--id ID]   add a change note (TYPE: {', '.join(proj.TYPES)})
  amin fragment list                     notes waiting to be released
  amin history NAME [--from TAG] [--to TAG]
                                         merged PRs touching NAME since its last tag (or between tags)
  amin triage                            unlabeled issues, possible duplicates, stale issues
  amin work start ISSUE                  branch + isolated worktree for an issue
  amin check-fragment --base REF [--labels a,b]   CI rule: changed projects need a note
  amin copies [--check]                  refresh shared-file copies (.amin.json "copies");
                                         --check only lists stale ones
"""


# Read again on every turn (#345): the skills list themselves, so the note keeps the helper they run
# and the one rule that holds in any session.
SESSION_NOTE = "amin (Nexika): a human merges every PR; never merge one yourself. amin helper: {helper}"


def helper_command() -> str:
    return f"python3 {Path(__file__).resolve().parent.parent / 'bin' / 'amin'}"


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40] or "issue"


def find_project(root: Path, projects: list[proj.Project], name: str) -> proj.Project:
    """A project, or the whole repo (the umbrella release) by its name."""
    whole = proj.umbrella(root)
    if whole and whole.name == name and name not in {p.name for p in projects}:
        return whole
    return proj.find(projects, name)


def publish_ready(root: Path, runner: gitops.Runner, plans: list[release.Plan] | None = None) -> None:
    """status/amin.json (nexika.amin/1): the projects of each repo ready to release, for mizan."""
    try:
        plans = plans if plans is not None else release.plan(root, runner, proj.detect(root))
    except (gitops.CommandError, OSError, ValueError):
        return
    ready = [{"name": pl.project.name, "next": pl.next} for pl in plans
             if pl.status in ("release", "first-release")]
    repos = status.read("amin").get("repos")
    repos = {k: v for k, v in repos.items() if os.path.isdir(k)} if isinstance(repos, dict) else {}
    repos[str(root)] = {"ready": ready}
    status.publish("amin", {"repos": repos})


def cmd_projects(root: Path, runner: gitops.Runner) -> str:
    projects = proj.detect(root)
    if not projects:
        return "no projects detected: add .amin.json (see /amin:setup)"
    rows = []
    for p in projects:
        tag = gitops.last_tag(runner, p.tag_prefix())
        if p.version_files:
            version = p.read_version(root, p.version_files[0])
        else:
            version = tag[len(p.tag_prefix()):] if tag else None
        if p.github_changelog:
            log = "GitHub releases"
        elif (root / p.changelog).is_file():
            log = p.changelog
        else:
            log = (f"{p.changelog} (missing: prepare creates it; if the notes live in GitHub releases, "
                   f"set \"changelog\": \"github\" in .amin.json)")
        rows.append(f"{p.name:<12} {version or '?':<8} path={p.path} "
                    f"version={','.join(p.version_files) or 'from tags'} "
                    f"changelog={log} notes={p.fragments}/ last tag={tag or 'none'}")
        rows += [f"    ! {line}" for line in release._unlisted(root, p, version)] if version else []
    return "\n".join(rows)


def cmd_prepare(root: Path, runner: gitops.Runner, args: list[str]) -> str:
    projects = proj.detect(root)
    plans = {pl.project.name: pl for pl in release.plan(root, runner, projects)}
    flags = {a for a in args if a.startswith("--")}
    unknown = {f for f in flags if not f.startswith("--pre=")} - {
        "--allow-lower", "--umbrella", "--dry-run", "--rc", "--pre"}
    if unknown:
        raise ValueError(f"unknown option {sorted(unknown)[0]}")
    args = [a for a in args if not a.startswith("--")]
    wanted: dict[str, str | None] = {}
    for arg in args:
        name, _, version = arg.partition("=")
        if name not in plans:
            raise KeyError(f"unknown project '{name}'")
        wanted[name] = version or None
    if not wanted:
        wanted = {n: None for n, pl in plans.items() if pl.status in ("release", "first-release")}
    if not wanted:
        return "nothing to release: no project has notes (amin plan)"
    chosen = []
    for name, version in wanted.items():
        pl = plans[name]
        if not (version or pl.next):
            raise release.ReleaseError(f"{name}: no proposed version ({pl.reason})")
        pre = next((f.partition("=")[2] or None for f in flags if f == "--pre" or f.startswith("--pre=")),
                   "rc" if "--rc" in flags else "")
        if pre != "" and not version:
            version = release.prerelease_version(runner, pl, pre)
        chosen.append((pl, version or pl.next))
    release.preflight(runner)
    dry_run, blocks = "--dry-run" in flags, []
    changed = release.prepare(root, chosen, allow_lower="--allow-lower" in flags, runner=runner,
                              umbrella="--umbrella" in flags, dry_run=dry_run, blocks=blocks)
    summary = ", ".join(block.split("\n", 1)[0] for block in blocks)
    if dry_run:
        return (f"dry run, nothing was changed. Would prepare: {summary}\nfiles:\n"
                + "\n".join(f"  {c}" for c in changed) + "\n\n" + "\n".join(blocks))
    out = f"prepared: {summary}\nchanged files:\n" + "\n".join(f"  {c}" for c in changed)
    if any(pl.project.github_changelog for pl, _ in chosen):
        out += ("\n\nrelease notes (no changelog file: put them in the release PR body; publish rebuilds "
                "them from the consumed notes):\n\n" + "\n".join(blocks))
    return out


def cmd_work_start(root: Path, runner: gitops.Runner, number: str) -> str:
    issue = runner.gh_json("issue", "view", number, "--json", "number,title,body,labels,state,url")
    if issue["state"] != "OPEN":
        raise gitops.CommandError(f"issue #{number} is {issue['state'].lower()}")
    labels = [lb["name"] for lb in issue.get("labels") or []]
    prefix = "fix" if "bug" in labels else "feat"
    branch = f"{prefix}/{issue['number']}-{_slug(issue['title'])}"
    default = gitops.default_branch(runner)
    worktree = root.parent / f"{root.name}-amin" / str(issue["number"])
    runner.git("fetch", "--quiet", "origin", default)
    runner.git("worktree", "add", "-b", branch, str(worktree), f"origin/{default}")
    body = (issue.get("body") or "").strip()
    return "\n".join([
        f"issue #{issue['number']}: {issue['title']}  ({issue['url']})",
        f"labels: {', '.join(labels) or 'none'}",
        f"branch: {branch}",
        f"worktree: {worktree}   (work there; your main checkout is untouched)",
        "", body[:3000] or "(no description)",
    ])


def run(argv: list[str]) -> int:
    cmd = argv[0] if argv else ""
    if cmd in ("", "-h", "--help", "help"):
        print(USAGE)
        return 0 if cmd else 2
    if cmd == "hook":
        if argv[1:2] == ["session-start"]:
            print(SESSION_NOTE.format(helper=helper_command()))
        return 0
    root = gitops.repo_root(Path.cwd())
    runner = gitops.Runner(root)
    projects = proj.detect(root)
    if cmd == "projects":
        print(cmd_projects(root, runner))
    elif cmd == "plan":
        plans = release.plan(root, runner, projects)
        print(release.render_plan(plans))
        publish_ready(root, runner, plans)
    elif cmd == "prepare":
        print(cmd_prepare(root, runner, argv[1:]))
        publish_ready(root, runner)
    elif cmd == "copies":
        check_only = "--check" in argv[1:]
        changed = release.stale_copies(root) if check_only else release.sync_copies(root)
        if not changed:
            print("all copies match their source")
        else:
            verb = "stale (run amin copies)" if check_only else "refreshed"
            print(f"{verb}:\n" + "\n".join(f"  {c}" for c in changed))
            if check_only:
                return 1
    elif cmd == "publish" and len(argv) > 1:
        print("\n".join(release.publish(root, runner, find_project(root, projects, argv[1]),
                                        "--dry-run" in argv)))
        publish_ready(root, runner)
    elif cmd == "fragment" and argv[1:2] == ["add"] and len(argv) >= 5:
        rest = argv[2:]
        note_id = "note"
        if "--id" in rest:
            i = rest.index("--id")
            note_id = rest[i + 1]
            rest = rest[:i] + rest[i + 2:]
        path = fragments.add(root, proj.find(projects, rest[0]), rest[1], " ".join(rest[2:]), note_id)
        print(f"added {path.relative_to(root).as_posix()}")
        publish_ready(root, runner)
    elif cmd == "fragment" and argv[1:2] == ["list"]:
        for p in projects:
            notes, problems = fragments.pending(root, p)
            for n in notes:
                print(f"{p.name:<12} {n.type:<10} {n.path}: {n.text.splitlines()[0][:80]}")
            for problem in problems:
                print(f"{p.name:<12} PROBLEM    {problem}")
    elif cmd == "history" and len(argv) > 1:
        p = proj.find(projects, argv[1])
        to = argv[argv.index("--to") + 1] if "--to" in argv[2:-1] else None
        if "--from" in argv[2:-1]:
            tag = argv[argv.index("--from") + 1]
        elif to:   # the release before `to`
            tag = runner.git("describe", "--tags", "--abbrev=0", "--match", f"{p.tag_prefix()}*", f"{to}^",
                             check=False).strip() or None
        else:
            tag = gitops.last_tag(runner, p.tag_prefix())
        lines = release.history(root, runner, p, tag, to)
        print("\n".join(lines) or "no merged PRs found for this project")
        if not tag:
            print(f"(no {p.tag('X.Y.Z')} tag found: only the latest {release.UNTAGGED_LIMIT} merged PRs "
                  "were read)")
    elif cmd == "triage":
        issues = runner.gh_json("issue", "list", "--state", "open", "--limit", "300",
                                "--json", "number,title,labels,updatedAt") or []
        label_data = runner.gh_json("label", "list", "--limit", "200", "--json", "name") or []
        labels = [lb["name"] for lb in label_data]
        settings = proj.load_config(root).get("triage")
        keep = settings.get("keep_labels") if isinstance(settings, dict) else None
        keep = [str(x) for x in keep] if isinstance(keep, list) else None
        closed = runner.gh_json("issue", "list", "--state", "closed", "--limit", "200",
                                "--json", "number,title,labels,updatedAt") or []
        try:
            repo = runner.gh_json("repo", "view", "--json", "name")["name"]
        except (gitops.CommandError, ValueError, KeyError, TypeError):
            repo = root.name
        print(triage.scan(issues, labels, keep_labels=keep, closed=closed, repo=repo))
    elif cmd == "work" and argv[1:2] == ["start"] and len(argv) > 2:
        print(cmd_work_start(root, runner, argv[2].lstrip("#")))
    elif cmd == "check-fragment":
        base = argv[argv.index("--base") + 1] if "--base" in argv else "origin/main"
        labels = argv[argv.index("--labels") + 1].split(",") if "--labels" in argv else []
        ok, lines = check.check(root, runner, projects, base, [x.strip() for x in labels if x.strip()])
        print("\n".join(lines))
        return 0 if ok else 1
    else:
        print(USAGE)
        return 2
    return 0


def main(argv: list[str]) -> int:
    try:
        return run(argv)
    except (gitops.CommandError, release.ReleaseError, KeyError, ValueError) as exc:
        message = exc.args[0] if isinstance(exc, KeyError) and exc.args else exc
        print(f"amin: {message}", file=sys.stderr)
        return 1
    except json.JSONDecodeError as exc:
        print(f"amin: unexpected gh output: {exc}", file=sys.stderr)
        return 1


def entry() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass
    sys.exit(main(sys.argv[1:]))
