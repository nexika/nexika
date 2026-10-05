"""git-status: where am I, what changed, and what should happen next."""
from __future__ import annotations

from . import files
from .core import READ, Context, OpError, OpSpec, Result

CONFLICT_CODES = {"DD", "AU", "UD", "UA", "DU", "AA", "UU"}
LIST_CAP = 25


def _git(ctx: Context, *args: str) -> str | None:
    out = files._git(list(args), ctx.root)
    return out.rstrip("\n") if out is not None else None


def _default_branch(ctx: Context) -> str:
    ref = _git(ctx, "symbolic-ref", "--short", "refs/remotes/origin/HEAD")
    if ref:
        return ref.split("/", 1)[-1]
    for name in ("main", "master"):
        if _git(ctx, "rev-parse", "--verify", "--quiet", name) is not None:
            return name
    return "main"


def op_git_status(ctx: Context, full=False) -> Result:
    if _git(ctx, "rev-parse", "--is-inside-work-tree") != "true":
        raise OpError("not a git repository")
    cap = 10_000 if full in (True, "full", "true", "1") else LIST_CAP
    branch = _git(ctx, "rev-parse", "--abbrev-ref", "HEAD") or "?"
    upstream = _git(ctx, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")
    ahead = behind = 0
    if upstream:
        counts = (_git(ctx, "rev-list", "--left-right", "--count", "HEAD...@{u}") or "0 0").split()
        ahead, behind = int(counts[0]), int(counts[1])
    default = _default_branch(ctx)

    staged, unstaged, untracked, conflicts = [], [], [], []
    raw = _git(ctx, "status", "--porcelain=v1", "-z", "--untracked-files=all") or ""
    entries = raw.split("\0")
    i = 0
    while i < len(entries):
        entry = entries[i]
        i += 1
        if len(entry) < 4:
            continue
        xy, path = entry[:2], entry[3:]
        if xy[0] in "RC":
            i += 1  # the rename source follows as its own entry
        if xy == "??":
            untracked.append(path)
        elif xy in CONFLICT_CODES:
            conflicts.append(path)
        else:
            if xy[0] not in " ?!":
                staged.append(f"{xy[0]} {path}")
            if xy[1] not in " ?!":
                unstaged.append(f"{xy[1]} {path}")

    head = f"branch: {branch}"
    if upstream:
        head += f" -> {upstream} ({ahead} ahead, {behind} behind)"
    else:
        head += " (no upstream)"
    head += f"   [default: {default}]"
    lines = [head]

    log = _git(ctx, "log", "-5", "--format=%h %ad %s", "--date=short")
    if log:
        lines.append("recent commits:")
        lines += [f"  {ln}" for ln in log.split("\n")]

    lines.append(f"changes: {len(staged)} staged, {len(unstaged)} unstaged, "
                 f"{len(untracked)} untracked, {len(conflicts)} conflicted")
    for title, items in (("conflicts", conflicts), ("staged", staged), ("unstaged", unstaged),
                         ("untracked", untracked)):
        if items:
            lines.append(f"  {title}:")
            lines += [f"    {it}" for it in items[:cap]]
            if len(items) > cap:
                lines.append(f"    ... {len(items) - cap} more (git-status:full)")
    stashes = _git(ctx, "stash", "list")
    if stashes:
        lines.append(f"stashes: {len(stashes.splitlines())}")

    dirty = bool(staged or unstaged or untracked)
    steps = []
    if conflicts:
        steps.append(f"resolve {len(conflicts)} conflicted file(s), then git add them")
    if branch == default and dirty:
        steps.append(f"you are on {default}: create a branch first (git switch -c feat/<name>)")
    elif staged and not unstaged and not untracked:
        steps.append("commit the staged changes")
    elif dirty:
        steps.append("review the changes, stage what belongs together, commit")
    if behind:
        steps.append(f"pull/rebase: {behind} new commit(s) on {upstream}")
    if ahead and not dirty:
        steps.append(f"push {ahead} commit(s)")
    if not upstream and branch not in (default, "HEAD") and not dirty:
        steps.append(f"publish the branch: git push -u origin {branch}")
    if branch == "HEAD":
        steps.insert(0, "detached HEAD: switch to a branch before committing")
    lines.append("next: " + ("; ".join(steps) if steps else "nothing to do, working tree clean"))
    return Result(f"git-status ({branch})", "\n".join(lines))


OPS = [
    OpSpec("git-status", op_git_status, lambda parts: {"full": parts[0]} if parts else {}, READ,
           "git-status[:full]",
           "Branch, upstream ahead/behind, recent commits, staged/unstaged/untracked files, "
           "stashes and the suggested next step."),
]
