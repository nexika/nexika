"""Releases in three steps; the human approves each one and always does the merge.

plan     what each project would release, from its notes (no changes)
prepare  bump versions, write CHANGELOG sections, delete used notes -> committed as a PR
publish  after that PR is merged: checks, then tag + GitHub Release
"""
from __future__ import annotations

import datetime
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from . import changelog, fragments, gitops
from . import project as proj


class ReleaseError(Exception):
    pass


@dataclass
class Plan:
    project: proj.Project
    current: str | None
    last_tag: str | None
    notes: list = field(default_factory=list)
    problems: list[str] = field(default_factory=list)
    commits: list[str] = field(default_factory=list)
    next: str | None = None
    reason: str = ""
    status: str = "nothing"   # release | first-release | needs-notes | nothing | error


def _current_version(root: Path, p: proj.Project) -> tuple[str | None, list[str]]:
    versions = {vf: proj.read_version(root, vf) for vf in p.version_files}
    found = {v for v in versions.values() if v}
    if not found:
        return None, [f"no version found in {', '.join(p.version_files)}"]
    if len(found) > 1:
        return sorted(found)[0], [f"version files disagree: {versions}"]
    return found.pop(), []


def plan(root: Path, runner: gitops.Runner, projects: list[proj.Project]) -> list[Plan]:
    plans = []
    for p in projects:
        current, problems = _current_version(root, p)
        tag = gitops.last_tag(runner, p.tag_prefix())
        notes, note_problems = fragments.pending(root, p)
        item = Plan(p, current, tag, notes, problems + note_problems,
                    gitops.commits_since(runner, tag, p.path))
        types = {n.type for n in notes}
        if current is None:
            item.status, item.reason = "error", problems[0]
        elif tag is None:
            item.next = current
            if notes:
                item.status, item.reason = "first-release", f"first release of {current}"
            else:
                item.status = "needs-notes"
                item.reason = "first release: add notes describing this version (amin history helps)"
        elif notes:
            last = tag[len(p.tag_prefix()):]
            item.next, item.reason = proj.bump(last, types)
            item.status = "release"
            if current != last:
                item.problems.append(f"version file says {current}, last tag says {last}; using the tag")
        elif item.commits:
            item.status = "needs-notes"
            item.reason = f"{len(item.commits)} commit(s) since {tag} but no notes"
        else:
            item.reason = f"nothing new since {tag}"
        plans.append(item)
    return plans


def render_plan(plans: list[Plan]) -> str:
    lines = []
    for pl in plans:
        kinds = sorted({n.type for n in pl.notes})
        notes = f"{len(pl.notes)} note(s): {', '.join(kinds)}" if pl.notes else "no notes"
        target = f"{pl.current or '?'} -> {pl.next}" if pl.next else (pl.current or "?")
        lines.append(f"{pl.project.name:<12} {pl.status:<14} {target:<16} {notes}  "
                     f"[last tag: {pl.last_tag or 'none'}] {pl.reason}")
        lines += [f"    ! {problem}" for problem in pl.problems]
    return "\n".join(lines) or "no projects detected (see /amin:setup)"


def prepare(root: Path, chosen: list[tuple[Plan, str]], date: str | None = None,
            allow_lower: bool = False) -> list[str]:
    """Apply chosen (plan, version) pairs. Returns the files changed (to commit as one PR).

    A version below what the notes require (a breaking note released as a minor) is refused
    unless allow_lower."""
    date = date or datetime.date.today().isoformat()
    changed: list[str] = []
    for pl, version in chosen:
        proj.parse(version)
        if pl.last_tag:
            last = pl.last_tag[len(pl.project.tag_prefix()):]
            if proj.parse(version) <= proj.parse(last):
                raise ReleaseError(f"{pl.project.name}: {version} is not newer than {last}")
            required, reason = proj.bump(last, {n.type for n in pl.notes})
            if not allow_lower and proj.parse(version) < proj.parse(required):
                raise ReleaseError(f"{pl.project.name}: {version} is too low: {reason}, so it needs at "
                                   f"least {required} (pass --allow-lower to release {version} anyway)")
        if not pl.notes:
            raise ReleaseError(f"{pl.project.name}: no notes to release")
        for vf in pl.project.version_files:
            if proj.read_version(root, vf) != version:
                proj.write_version(root, vf, version)
                changed.append(vf)
        changelog.insert(root / pl.project.changelog, pl.project.name, version, date,
                         fragments.grouped(pl.notes))
        changed.append(pl.project.changelog)
        for note in pl.notes:
            (root / note.path).unlink()
            changed.append(note.path)
    return changed


# ---------------------------------------------------------------- publish


def _ci_state(runner: gitops.Runner, sha: str) -> tuple[bool, str]:
    repo = runner.gh_json("repo", "view", "--json", "nameWithOwner")["nameWithOwner"]
    data = runner.gh_json("api", f"repos/{repo}/commits/{sha}/check-runs?per_page=100")
    runs = (data or {}).get("check_runs", [])
    if not runs:
        return False, "no CI results for this commit yet"
    pending = [r["name"] for r in runs if r.get("status") != "completed"]
    failed = [r["name"] for r in runs if r.get("status") == "completed"
              and r.get("conclusion") not in ("success", "skipped", "neutral")]
    if pending:
        return False, f"CI still running: {', '.join(pending[:5])}"
    if failed:
        return False, f"CI failed: {', '.join(failed[:5])}"
    return True, f"CI green ({len(runs)} checks)"


def publish(root: Path, runner: gitops.Runner, project: proj.Project, dry_run: bool = False) -> list[str]:
    """Check everything, then (unless dry_run) create the tag and the GitHub Release."""
    report, failures = [], []
    default = gitops.default_branch(runner)
    branch = runner.git("rev-parse", "--abbrev-ref", "HEAD").strip()
    if branch != default:
        failures.append(f"on branch {branch}; releases are cut from {default}")
    if runner.git("status", "--porcelain").strip():
        failures.append("working tree has uncommitted changes")
    runner.git("fetch", "--quiet", "--tags", "origin", default, check=False)
    head = runner.git("rev-parse", "HEAD").strip()
    remote = runner.git("rev-parse", f"origin/{default}", check=False).strip()
    if head != remote:
        failures.append(f"local {default} is not the same commit as origin/{default}: pull or push first")
    version, problems = _current_version(root, project)
    failures += problems
    tag = project.tag(version or "?")
    notes = changelog.extract(root / project.changelog, version or "?")
    if not notes:
        failures.append(f"{project.changelog} has no section for {version}: run prepare and merge that PR")
    # a tag already on HEAD with no release yet means an earlier publish stopped half way: finish it
    tagged = runner.git("rev-parse", "-q", "--verify", f"refs/tags/{tag}^{{commit}}", check=False).strip()
    pushed = bool(runner.git("ls-remote", "--tags", "origin", f"refs/tags/{tag}", check=False).strip())
    resume = False
    if tagged or pushed:
        if tagged and tagged != head:
            failures.append(f"tag {tag} already exists on another commit ({tagged[:7]})")
        elif runner.gh("release", "view", tag, "--json", "url", check=False).strip():
            failures.append(f"tag {tag} already exists and its release is already published")
        else:
            resume = True
    if not failures:
        ok, ci = _ci_state(runner, head)
        (report if ok else failures).append(ci)
    if failures:
        raise ReleaseError("not releasing:\n" + "\n".join(f"  - {f}" for f in failures))
    report.append(f"ready: {project.name} {version} -> tag {tag} on {head[:7]}")
    if resume:
        report.append(f"tag {tag} already {'pushed' if pushed else 'created'}: creating only what is missing")
    if dry_run:
        return report + ["dry run: nothing was created"]
    if not tagged:
        runner.git("tag", "-a", tag, "-m", f"{project.name} {version}")
    if not pushed:
        runner.git("push", "origin", tag)
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as fh:
        fh.write(notes)
        notes_file = fh.name
    try:
        url = runner.gh("release", "create", tag, "--title", f"{project.name} {version}",
                        "--notes-file", notes_file, "--verify-tag").strip()
    finally:
        Path(notes_file).unlink(missing_ok=True)
    return report + ([] if pushed else [f"tag {tag} pushed"]) + [f"release published: {url}"]


def history(root: Path, runner: gitops.Runner, project: proj.Project, tag: str | None) -> list[str]:
    """Merged PRs that touched the project since tag (to write first-release notes)."""
    since = runner.git("log", "-1", "--format=%cI", tag, check=False).strip() if tag else ""
    prs = runner.gh_json("pr", "list", "--state", "merged", "--limit", "200",
                         "--json", "number,title,mergedAt,files") or []
    out = []
    for pr in sorted(prs, key=lambda x: x.get("mergedAt", "")):
        if since and pr.get("mergedAt", "") <= since:
            continue
        paths = [f.get("path", "") for f in pr.get("files") or []]
        if project.path == "." or any(x == project.path or x.startswith(project.path + "/") for x in paths):
            out.append(f"#{pr['number']} {pr['title']} ({pr.get('mergedAt', '')[:10]})")
    return out
