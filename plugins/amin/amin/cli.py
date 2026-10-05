"""amin command line. There is deliberately no merge command: a human always merges."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from . import __version__, check, fragments, gitops, release, triage
from . import project as proj

USAGE = f"""amin {__version__} - repository maintainer; you always merge (Nexika)

  amin projects                          projects, versions, version files, last tags
  amin plan                              what would be released, from the change notes
  amin prepare [NAME[=VERSION] ...]      bump versions, write CHANGELOGs, consume notes (then: a PR)
  amin publish NAME [--dry-run]          after the release PR is merged: checks, tag, GitHub Release
  amin fragment add NAME TYPE TEXT [--id ID]   add a change note (TYPE: {', '.join(proj.TYPES)})
  amin fragment list                     notes waiting to be released
  amin history NAME                      merged PRs touching NAME since its last tag
  amin triage                            unlabeled issues, possible duplicates, stale issues
  amin work start ISSUE                  branch + isolated worktree for an issue
  amin check-fragment --base REF [--labels a,b]   CI rule: changed projects need a note
"""


def helper_command() -> str:
    return f"python3 {Path(__file__).resolve().parent.parent / 'bin' / 'amin'}"


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40] or "issue"


def cmd_projects(root: Path, runner: gitops.Runner) -> str:
    projects = proj.detect(root)
    if not projects:
        return "no projects detected: add .amin.json (see /amin:setup)"
    rows = []
    for p in projects:
        version = proj.read_version(root, p.version_files[0])
        tag = gitops.last_tag(runner, p.tag_prefix())
        rows.append(f"{p.name:<12} {version or '?':<8} path={p.path} version={','.join(p.version_files)} "
                    f"changelog={p.changelog} notes={p.fragments}/ last tag={tag or 'none'}")
    return "\n".join(rows)


def cmd_prepare(root: Path, runner: gitops.Runner, args: list[str]) -> str:
    projects = proj.detect(root)
    plans = {pl.project.name: pl for pl in release.plan(root, runner, projects)}
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
        chosen.append((pl, version or pl.next))
    changed = release.prepare(root, chosen)
    summary = ", ".join(f"{pl.project.name} {v}" for pl, v in chosen)
    return f"prepared: {summary}\nchanged files:\n" + "\n".join(f"  {c}" for c in changed)


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
            print("## amin (Nexika): maintain this repo; you always merge\n"
                  "/amin:triage, /amin:work <issue>, /amin:release, /amin:setup. "
                  f"amin helper: {helper_command()}")
        return 0
    root = gitops.repo_root(Path.cwd())
    runner = gitops.Runner(root)
    projects = proj.detect(root)
    if cmd == "projects":
        print(cmd_projects(root, runner))
    elif cmd == "plan":
        print(release.render_plan(release.plan(root, runner, projects)))
    elif cmd == "prepare":
        print(cmd_prepare(root, runner, argv[1:]))
    elif cmd == "publish" and len(argv) > 1:
        print("\n".join(release.publish(root, runner, proj.find(projects, argv[1]), "--dry-run" in argv)))
    elif cmd == "fragment" and argv[1:2] == ["add"] and len(argv) >= 5:
        rest = argv[2:]
        note_id = "note"
        if "--id" in rest:
            i = rest.index("--id")
            note_id = rest[i + 1]
            rest = rest[:i] + rest[i + 2:]
        path = fragments.add(root, proj.find(projects, rest[0]), rest[1], " ".join(rest[2:]), note_id)
        print(f"added {path.relative_to(root).as_posix()}")
    elif cmd == "fragment" and argv[1:2] == ["list"]:
        for p in projects:
            notes, problems = fragments.pending(root, p)
            for n in notes:
                print(f"{p.name:<12} {n.type:<10} {n.path}: {n.text.splitlines()[0][:80]}")
            for problem in problems:
                print(f"{p.name:<12} PROBLEM    {problem}")
    elif cmd == "history" and len(argv) > 1:
        p = proj.find(projects, argv[1])
        lines = release.history(root, runner, p, gitops.last_tag(runner, p.tag_prefix()))
        print("\n".join(lines) or "no merged PRs found for this project")
    elif cmd == "triage":
        issues = runner.gh_json("issue", "list", "--state", "open", "--limit", "300",
                                "--json", "number,title,labels,updatedAt") or []
        label_data = runner.gh_json("label", "list", "--limit", "200", "--json", "name") or []
        labels = [lb["name"] for lb in label_data]
        print(triage.scan(issues, labels))
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
