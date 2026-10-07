"""CI rule: a pull request that changes a project must add a change note for it.

Exempt: PRs labelled `no-changelog`, release PRs (they consume notes), a project's own
CHANGELOG.md, and for single-project repos also .github/, docs/, tests/ and top-level *.md.
"""
from __future__ import annotations

from pathlib import Path

from . import fragments, gitops
from . import project as proj

SKIP_LABEL = "no-changelog"
SINGLE_EXEMPT_PREFIXES = (".github/", "docs/", "tests/", "test/", "changelog.d/")


def _exempt(rel: str, owner: proj.Project) -> bool:
    if rel == owner.changelog or rel.startswith("changelog.d/"):
        return True
    if owner.path == ".":
        return rel.startswith(SINGLE_EXEMPT_PREFIXES) or ("/" not in rel and rel.endswith(".md"))
    return False


def _text(root: Path, rel: str) -> str:
    try:
        return (root / rel).read_text(encoding="utf-8").strip()
    except (OSError, UnicodeDecodeError):
        return ""


def check(root: Path, runner: gitops.Runner, projects: list[proj.Project], base: str,
          labels: list[str]) -> tuple[bool, list[str]]:
    if SKIP_LABEL in labels:
        return True, [f"skipped: the PR has the {SKIP_LABEL} label"]
    diff = f"{base}...HEAD"
    changed = runner.git("diff", "--name-only", diff).split()
    added = runner.git("diff", "--name-only", "--diff-filter=A", diff).split()
    deleted = runner.git("diff", "--name-only", "--diff-filter=D", diff).split()
    lines, ok = [], True

    folders = {p.fragments for p in projects}
    notes = []   # added notes that will be released
    for rel in added:
        if not rel.startswith("changelog.d/") or rel.lower().endswith("readme.md"):
            continue
        problem = fragments.check_name(rel.rsplit("/", 1)[-1])
        if problem:
            lines.append(f"bad note name: {rel}: {problem.split(': ', 1)[-1]}")
        elif rel.rsplit("/", 1)[0] not in folders:
            problem = "misplaced"
            lines.append(f"misplaced note: {rel}: it is never released; notes go in "
                         + " or ".join(sorted(f + "/" for f in folders)[:3])
                         + (" ..." if len(folders) > 3 else ""))
        elif not _text(root, rel):
            problem = "empty"
            lines.append(f"empty note: {rel}: write what changed, for users")
        else:
            notes.append(rel)
        ok = ok and not problem

    needs: dict[str, proj.Project] = {}
    for rel in changed:
        owner = proj.owner_of(projects, rel)
        if owner and not _exempt(rel, owner):
            needs[owner.name] = owner
    for name, p in sorted(needs.items()):
        has_note = any(f.rsplit("/", 1)[0] == p.fragments for f in notes)
        # deleting notes is a release only together with the CHANGELOG or version it was released into;
        # on its own it just destroys someone's note
        released = p.changelog in changed or any(v in changed for v in p.version_files)
        is_release = released and any(f.rsplit("/", 1)[0] == p.fragments for f in deleted)
        if has_note or is_release:
            lines.append(f"{name}: ok ({'release' if is_release and not has_note else 'note added'})")
            continue
        ok = False
        lines.append(
            f"{name}: files changed but no note in {p.fragments}/. Add one, e.g.\n"
            f"    python3 plugins/amin/bin/amin fragment add {name} fixed \"What changed, for users\""
            " --id <PR>\n"
            f"  types: breaking, added, changed, deprecated, removed, fixed, security"
            f" (or label the PR {SKIP_LABEL})"
        )
    if not needs and ok:
        lines.append("no project files changed: no note needed")
    return ok, lines
