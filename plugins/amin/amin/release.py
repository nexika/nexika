"""Releases in three steps; the human approves each one and always does the merge.

plan     what each project would release, from its notes (no changes)
prepare  bump versions, write CHANGELOG sections, delete used notes -> committed as a PR
publish  after that PR is merged: checks, then tag + GitHub Release
"""
from __future__ import annotations

import datetime
import re
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
    calver: bool = False      # calendar versions (YY.M.patch): the date decides the next version


def today() -> datetime.date:
    return datetime.date.today()


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
        tag = gitops.last_tag(runner, p.tag_prefix())
        if p.version_files:
            current, problems = _current_version(root, p)
        else:   # the version lives in tags only (hatch-vcs, setuptools-scm)
            current = tag[len(p.tag_prefix()):] if tag else None
            problems = [] if tag else [f"the version comes from tags and no {p.tag('X.Y.Z')} tag "
                                       "was found: pass NAME=VERSION to prepare"]
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
            item.calver = proj.is_calver(gitops.released_versions(runner, p.tag_prefix()), today())
            item.next, item.reason = (proj.calver_bump(last, today()) if item.calver
                                      else proj.bump(last, types))
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


def rc_version(runner: gitops.Runner, pl: Plan) -> str:
    """The next release candidate of the planned version: 1.3.0-rc.1, then -rc.2 ..."""
    if not pl.next:
        raise ReleaseError(f"{pl.project.name}: no proposed version ({pl.reason})")
    prefix = pl.project.tag(f"{pl.next}-rc.")
    tags = runner.git("tag", "--list", f"{prefix}*", check=False).split()
    numbers = [int(t[len(prefix):]) for t in tags if t[len(prefix):].isdigit()]
    return f"{pl.next}-rc.{max(numbers, default=0) + 1}"


def preflight(runner: gitops.Runner) -> None:
    """prepare runs on a release branch with a clean tree (its changes become the release PR)."""
    failures = []
    default = gitops.default_branch(runner)
    branch = runner.git("rev-parse", "--abbrev-ref", "HEAD").strip()
    if branch == default:
        failures.append(f"on {default}: create a release branch first, e.g. release/{datetime.date.today()}")
    if runner.git("status", "--porcelain").strip():
        failures.append("working tree has uncommitted changes")
    if failures:
        raise ReleaseError("not preparing:\n" + "\n".join(f"  - {f}" for f in failures))


def pr_for(runner: gitops.Runner, rel: str) -> str | None:
    """The pull request that added a note: from a squash or merge subject, else from GitHub."""
    line = runner.git("log", "--diff-filter=A", "-1", "--format=%H %s", "--", rel, check=False).strip()
    if not line:
        return None
    sha, _, subject = line.partition(" ")
    m = re.search(r"\(#(\d+)\)\s*$", subject) or re.match(r"Merge pull request #(\d+)", subject)
    if m:
        return m.group(1)
    try:
        repo = runner.gh_json("repo", "view", "--json", "nameWithOwner")["nameWithOwner"]
        pulls = runner.gh_json("api", f"repos/{repo}/commits/{sha}/pulls") or []
        merged = [pr for pr in pulls if pr.get("merged_at")] or pulls
        return str(merged[0]["number"]) if merged else None
    except (gitops.CommandError, ValueError, KeyError, TypeError, IndexError):
        return None


def _umbrella_version(root: Path, runner: gitops.Runner | None, umbrella: proj.Project,
                      types: set[str]) -> str:
    tag = gitops.last_tag(runner or gitops.Runner(root), umbrella.tag_prefix())
    base = tag[len(umbrella.tag_prefix()):] if tag else _current_version(root, umbrella)[0]
    if not base:
        raise ReleaseError(f"{umbrella.name}: no umbrella version found (no tag and no root version file)")
    released = tag or changelog.has_version(root / umbrella.changelog, base)
    return proj.bump(base, types)[0] if released else base   # else: the first umbrella release


def stale_copies(root: Path) -> list[str]:
    """Copies (from .amin.json "copies") that differ from their source or are missing."""
    stale = []
    for source, targets in proj.copies(root).items():
        data = (root / source).read_bytes()
        for target in targets:
            path = root / target
            if not path.is_file() or path.read_bytes() != data:
                stale.append(target)
    return stale


def sync_copies(root: Path, dry_run: bool = False) -> list[str]:
    """Refresh every stale copy from its source; returns the files changed."""
    stale = stale_copies(root)
    if not dry_run:
        sources = {t: s for s, targets in proj.copies(root).items() for t in targets}
        for target in stale:
            path = root / target
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes((root / sources[target]).read_bytes())
    return stale


def prepare(root: Path, chosen: list[tuple[Plan, str]], date: str | None = None,
            allow_lower: bool = False, runner: gitops.Runner | None = None, umbrella: bool = False,
            dry_run: bool = False, blocks: list[str] | None = None) -> list[str]:
    """Apply chosen (plan, version) pairs. Returns the files changed (to commit as one PR).

    A version below what the notes require (a breaking note released as a minor) is refused
    unless allow_lower. With runner, notes named by a slug get their PR number. With umbrella, the
    whole repo gets a version and a root CHANGELOG section too. dry_run writes nothing; the
    CHANGELOG sections go to blocks either way."""
    date = date or datetime.date.today().isoformat()
    changed: list[str] = []
    blocks = blocks if blocks is not None else []
    for pl, version in chosen:
        proj.parse(version)
        if pl.last_tag:
            last = pl.last_tag[len(pl.project.tag_prefix()):]
            if proj.parse(version) <= proj.parse(last):
                raise ReleaseError(f"{pl.project.name}: {version} is not newer than {last}")
            required, reason = proj.bump(last, {n.type for n in pl.notes})
            if not allow_lower and not pl.calver and proj.parse(version)[:3] < proj.parse(required)[:3]:
                raise ReleaseError(f"{pl.project.name}: {version} is too low: {reason}, so it needs at "
                                   f"least {required} (pass --allow-lower to release {version} anyway)")
        if not pl.notes:
            raise ReleaseError(f"{pl.project.name}: no notes to release")
    whole = proj.umbrella(root) if umbrella else None
    if umbrella and whole is None:
        raise ReleaseError("--umbrella needs a plugin marketplace or an \"umbrella\" entry in .amin.json")
    if whole:
        types = {n.type for pl, _ in chosen for n in pl.notes}
        whole_version = _umbrella_version(root, runner, whole, types)
        if changelog.has_version(root / whole.changelog, whole_version):
            raise ReleaseError(f"{whole.changelog} already has a section for {whole_version}")
    for pl, version in chosen:
        for note in pl.notes:
            if runner and not note.id.isdigit():
                note.pr = pr_for(runner, note.path)
        for vf in pl.project.version_files:
            if proj.read_version(root, vf) != version:
                if not dry_run:
                    proj.write_version(root, vf, version)
                changed.append(vf)
        sections = fragments.grouped(pl.notes)
        blocks.append(f"{pl.project.name} {version}\n" + changelog.render(version, date, sections))
        if not dry_run:
            changelog.insert(root / pl.project.changelog, pl.project.name, version, date, sections)
        changed.append(pl.project.changelog)
        if proj.is_prerelease(version):
            continue   # a release candidate keeps its notes: the final release collects them all
        for note in pl.notes:
            if not dry_run:
                (root / note.path).unlink()
            changed.append(note.path)
    if whole:
        rows = ["| Project | Version |", "|---|---|"] + [
            f"| [{pl.project.name}]({pl.project.changelog}) | {version} |" for pl, version in chosen]
        sections = {"Released": rows}
        blocks.append(f"{whole.name} {whole_version}\n" + changelog.render(whole_version, date, sections))
        for vf in whole.version_files:
            if proj.read_version(root, vf) != whole_version:
                if not dry_run:
                    proj.write_version(root, vf, whole_version)
                changed.append(vf)
        if not dry_run:
            changelog.insert(root / whole.changelog, whole.name, whole_version, date, sections)
        changed.append(whole.changelog)
    changed += sync_copies(root, dry_run)   # shared files ship as copies: refresh them in the release PR
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
    if branch == default and head != remote:   # on another branch, the line above already refused
        failures.append(f"local {default} is not the same commit as origin/{default}: pull or push first")
    if project.version_files:
        version, problems = _current_version(root, project)
    else:   # the version lives in tags only: release the newest CHANGELOG section
        version = changelog.latest(root / project.changelog)
        problems = [] if version else [f"{project.changelog} has no version section: run prepare first"]
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
                        "--notes-file", notes_file, "--verify-tag",
                        *(["--prerelease"] if proj.is_prerelease(version) else []),
                        *(["--latest=false"] if _newer_final(runner, project, version) else [])).strip()
    finally:
        Path(notes_file).unlink(missing_ok=True)
    return report + ([] if pushed else [f"tag {tag} pushed"]) + [f"release published: {url}"]


def _newer_final(runner: gitops.Runner, project: proj.Project, version: str) -> str | None:
    """A final release above version (any branch): an older line's release must not become "Latest"."""
    prefix = project.tag_prefix()
    for tag in runner.git("tag", "--list", f"{prefix}*", check=False).split():
        other = tag[len(prefix):]
        if (proj.SEMVER.match(other) and not proj.is_prerelease(other) and proj.SEMVER.match(version)
                and proj.parse(other) > proj.parse(version)):
            return other
    return None


def _when(stamp: str) -> datetime.datetime | None:
    try:
        return datetime.datetime.fromisoformat(stamp.strip().replace("Z", "+00:00"))
    except ValueError:
        return None


UNTAGGED_LIMIT = 200


def history(root: Path, runner: gitops.Runner, project: proj.Project, tag: str | None,
            to: str | None = None) -> list[str]:
    """Merged PRs that touched the project in tag..to (to: HEAD by default), to write release notes.
    A PR counts when its merge commit is in that range, so each release line (main, 5.x) gets its own
    PRs; a merge commit missing from this clone counts when the PR's base is the current branch."""
    since = _when(runner.git("log", "-1", "--format=%cI", tag, check=False)) if tag else None
    until = _when(runner.git("log", "-1", "--format=%cI", to, check=False)) if to else None
    terms = ([f"merged:>={since.astimezone(datetime.timezone.utc).date()}"] if since else []) + (
        [f"merged:<={until.astimezone(datetime.timezone.utc).date()}"] if until else [])
    search = ["--search", " ".join(terms)] if terms else []
    limit = "5000" if since else str(UNTAGGED_LIMIT)   # no tag: only the latest PRs, or gh times out
    prs = runner.gh_json("pr", "list", "--state", "merged", "--limit", limit, *search,
                         "--json", "number,title,mergedAt,files,mergeCommit,author,baseRefName") or []
    upper = to or "HEAD"
    in_range = set(runner.git("rev-list", f"{tag}..{upper}" if tag else upper, check=False).split())
    oids = {(pr.get("mergeCommit") or {}).get("oid") or "" for pr in prs} - in_range - {""}
    checked = runner.git("cat-file", "--batch-check", input="\n".join(sorted(oids)) + "\n",
                         check=False) if oids else ""
    missing = {line.split()[0] for line in checked.splitlines() if line.endswith(" missing")}
    branch = None if to else runner.git("rev-parse", "--abbrev-ref", "HEAD", check=False).strip()
    out = []
    for pr in sorted(prs, key=lambda x: _when(x.get("mergedAt", "")) or datetime.datetime.min.replace(
            tzinfo=datetime.timezone.utc)):
        oid = (pr.get("mergeCommit") or {}).get("oid") or ""
        if oid not in in_range:   # git can't tell: the merge time and the PR's base branch decide
            merged = _when(pr.get("mergedAt", ""))
            if (oid and oid not in missing                    # merged into another line, or released
                    or pr.get("baseRefName") not in (None, "", branch)
                    or since and (merged is None or merged <= since) or until and merged and merged > until):
                continue
        paths = [f.get("path", "") for f in pr.get("files") or []]
        if project.path == "." or any(x == project.path or x.startswith(project.path + "/") for x in paths):
            out.append(f"#{pr['number']} {pr['title']} ({pr.get('mergedAt', '')[:10]}){_kind(pr, paths)}")
    return out


CI_FILES = re.compile(r"^(\.github/|\.circleci/|\.gitlab-ci\.yml$|\.pre-commit-config\.yaml$)")
BOTS = ("[bot]", "dependabot", "pre-commit-ci", "renovate")


def _kind(pr: dict, paths: list[str]) -> str:
    """A mark for PRs that release notes usually leave out: bots, or only CI files changed."""
    author = pr.get("author") or {}
    if author.get("is_bot") or str(author.get("login", "")).endswith(BOTS):
        return " [bot]"
    if paths and all(CI_FILES.match(x) for x in paths):
        return " [ci only]"
    return ""
