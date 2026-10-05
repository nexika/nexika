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


def check(root: Path, runner: gitops.Runner, projects: list[proj.Project], base: str,
          labels: list[str]) -> tuple[bool, list[str]]:
    if SKIP_LABEL in labels:
        return True, [f"skipped: the PR has the {SKIP_LABEL} label"]
    diff = f"{base}...HEAD"
    changed = runner.git("diff", "--name-only", diff).split()
    added = runner.git("diff", "--name-only", "--diff-filter=A", diff).split()
    deleted = runner.git("diff", "--name-only", "--diff-filter=D", diff).split()
    lines, ok = [], True

    for rel in added:
        if rel.startswith("changelog.d/") and not rel.lower().endswith("readme.md"):
            problem = fragments.check_name(rel.rsplit("/", 1)[-1])
            if problem:
                ok = False
                lines.append(f"bad note name: {rel}: {problem.split(': ', 1)[-1]}")

    needs: dict[str, proj.Project] = {}
    for rel in changed:
        owner = proj.owner_of(projects, rel)
        if owner and not _exempt(rel, owner):
            needs[owner.name] = owner
    for name, p in sorted(needs.items()):
        has_note = any(f.startswith(p.fragments + "/") for f in added)
        is_release = any(f.startswith(p.fragments + "/") for f in deleted)
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
