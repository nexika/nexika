"""git and gh calls in one place, behind a Runner that tests can replace."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path


class CommandError(Exception):
    pass


class Runner:
    def __init__(self, root: Path):
        self.root = root

    def run(self, *args: str, check: bool = True) -> str:
        try:
            res = subprocess.run(list(args), cwd=self.root, capture_output=True, text=True, timeout=120)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise CommandError(f"{args[0]}: {exc}") from None
        if check and res.returncode != 0:
            raise CommandError(f"{' '.join(args[:3])}...: {(res.stderr or res.stdout).strip()[:400]}")
        return res.stdout

    def git(self, *args: str, check: bool = True) -> str:
        return self.run("git", *args, check=check)

    def gh(self, *args: str, check: bool = True) -> str:
        return self.run("gh", *args, check=check)

    def gh_json(self, *args: str):
        out = self.gh(*args)
        return json.loads(out) if out.strip() else None


def repo_root(cwd: Path) -> Path:
    res = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=cwd, capture_output=True, text=True)
    if res.returncode != 0:
        raise CommandError("not inside a git repository")
    return Path(res.stdout.strip()).resolve()


def default_branch(runner: Runner) -> str:
    ref = runner.git("symbolic-ref", "--short", "refs/remotes/origin/HEAD", check=False).strip()
    if ref:
        return ref.split("/", 1)[-1]
    for name in ("main", "master"):
        if runner.git("rev-parse", "--verify", "--quiet", name, check=False).strip():
            return name
    return "main"


def last_tag(runner: Runner, prefix: str, final_only: bool = False) -> str | None:
    """The last release of this branch: the newest tag reachable from HEAD that is
    <prefix><MAJOR.MINOR.PATCH>, or <prefix><MAJOR.MINOR.PATCH-prerelease> unless final_only, by SemVer
    precedence (git's own sort puts 6.0.0-alpha.4 after 6.0.0). A tag of another release line (5.x's
    v5.12.5 seen from main, main's v6.0.0 seen from 5.x) is not this branch's last release."""
    from .project import SEMVER, parse
    out = runner.git("tag", "--merged", "HEAD", "--list", f"{prefix}*", check=False)
    found = [(parse(tag[len(prefix):]), tag) for tag in out.split()
             if (m := SEMVER.match(tag[len(prefix):])) and not (final_only and m.group(4))]
    return max(found)[1] if found else None


def released_versions(runner: Runner, prefix: str) -> list[str]:
    """The versions of the tags <prefix><MAJOR.MINOR.PATCH...> reachable from HEAD, newest first."""
    out = runner.git("tag", "--merged", "HEAD", "--list", f"{prefix}*", "--sort=-v:refname", check=False)
    return [tag[len(prefix):] for tag in out.split() if tag[len(prefix):][:1].isdigit()]


def commits_since(runner: Runner, tag: str | None, path: str) -> list[str]:
    rng = [f"{tag}..HEAD"] if tag else ["HEAD"]
    out = runner.git("log", "--format=%h %s", *rng, "--", path, check=False)
    return [line for line in out.splitlines() if line.strip()]
