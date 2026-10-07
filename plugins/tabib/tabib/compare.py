"""What changed between the last green run and the failing one: commits, files, dependency files.

Local git only (diagnose may fetch the two commits first); a commit that touched a file named in a
failure is marked a suspect.
"""
from __future__ import annotations

import re
import subprocess

LOCKFILES = re.compile(r"(?:^|/)(?:package-lock\.json|npm-shrinkwrap\.json|pnpm-lock\.yaml|yarn\.lock|"
                       r"poetry\.lock|uv\.lock|Pipfile(?:\.lock)?|requirements[\w.-]*\.(?:txt|in)|"
                       r"pyproject\.toml|setup\.(?:cfg|py)|go\.(?:mod|sum)|Cargo\.(?:toml|lock)|"
                       r"packages\.lock\.json|[^/]+\.csproj|Directory\.Packages\.props|Gemfile(?:\.lock)?|"
                       r"composer\.(?:json|lock))$")
SHA = re.compile(r"^[0-9a-f]{7,64}$")
# Which dependency files can change a failure, by the tool that reported it.
ECOSYSTEMS = {
    "python": re.compile(r"(?:^|/)(?:poetry\.lock|uv\.lock|Pipfile(?:\.lock)?|"
                         r"requirements[\w.-]*\.(?:txt|in)|pyproject\.toml|setup\.(?:cfg|py))$"),
    "node": re.compile(r"(?:^|/)(?:package-lock\.json|npm-shrinkwrap\.json|pnpm-lock\.yaml|yarn\.lock)$"),
    "go": re.compile(r"(?:^|/)go\.(?:mod|sum)$"),
    "rust": re.compile(r"(?:^|/)Cargo\.(?:toml|lock)$"),
    "dotnet": re.compile(r"(?:^|/)(?:packages\.lock\.json|[^/]+\.csproj|Directory\.Packages\.props)$"),
}
FRAMEWORK_ECOSYSTEM = {"pytest": "python", "ruff": "python", "mypy": "python", "jest": "node",
                       "eslint": "node", "tsc": "node", "go": "go", "cargo": "rust", "dotnet": "dotnet"}


def git(cwd: str, *args: str, timeout: float = 30) -> tuple[int, str]:
    try:
        done = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, timeout=timeout,
                              check=False)
    except (OSError, subprocess.SubprocessError):
        return 1, ""
    return done.returncode, done.stdout.strip()


def have(repo: str, sha: str) -> bool:
    return bool(SHA.match(sha or "")) and git(repo, "cat-file", "-e", f"{sha}^{{commit}}")[0] == 0


def fetch(repo: str, sha: str, branch: str = "") -> bool:
    """Bring a commit in from origin (the branch first, then the commit itself); True when present."""
    if have(repo, sha):
        return True
    if branch and not branch.startswith("-"):
        git(repo, "fetch", "--quiet", "--no-tags", "origin", f"refs/heads/{branch}", timeout=120)
    if not have(repo, sha) and SHA.match(sha or ""):
        git(repo, "fetch", "--quiet", "--no-tags", "origin", sha, timeout=120)
    return have(repo, sha)


SAFE_BRANCH = re.compile(r"^[\w][\w./-]*$")


def on_remote_branch(repo: str, sha: str, branch: str) -> bool:
    """True when the commit is in the history of origin's branch as this clone last saw it (no network)."""
    if not (SHA.match(sha or "") and SAFE_BRANCH.match(branch or "") and ".." not in branch):
        return False
    return have(repo, sha) and git(repo, "merge-base", "--is-ancestor", sha,
                                   f"refs/remotes/origin/{branch}")[0] == 0


def advertised_by_origin(repo: str, sha: str, branch: str) -> bool:
    """True when origin itself still advertises the branch and the commit is in its history (asks origin)."""
    if not (SHA.match(sha or "") and SAFE_BRANCH.match(branch or "") and ".." not in branch):
        return False
    code, out = git(repo, "ls-remote", "--heads", "origin", f"refs/heads/{branch}", timeout=60)
    tip = out.split()[0] if code == 0 and out.split() else ""
    if not SHA.match(tip) or not fetch(repo, tip, branch):
        return False
    return git(repo, "merge-base", "--is-ancestor", sha, tip)[0] == 0


def deps_changed(files: list[str], framework: str = "") -> list[str]:
    """Dependency files among these; with a framework, only its ecosystem's.

    pytest ignores package-lock.json, jest ignores uv.lock.
    """
    scope = ECOSYSTEMS.get(FRAMEWORK_ECOSYSTEM.get(framework, ""), LOCKFILES)
    return [f for f in files if scope.search(f)]


def advertised_tip(repo: str, sha: str) -> bool:
    """True when origin advertises a ref (a branch, or a pull request's head) whose tip is this commit.

    After a squash-merge deletes the branch, GitHub still serves refs/pull/<n>/head. Such a ref may
    hold a fork's code, so callers trust it only when the CI service says the run was not a fork's.
    """
    if not SHA.match(sha or ""):
        return False
    code, out = git(repo, "ls-remote", "origin", "refs/heads/*", "refs/pull/*/head", timeout=60)
    if code != 0:
        return False
    for line in out.splitlines():
        tip = line.partition("\t")[0]
        if tip.startswith(sha) or (len(tip) >= len(sha) and sha.startswith(tip)):
            return have(repo, sha) or fetch(repo, sha)
    return False


def compare(repo: str, green_sha: str, failing_sha: str, failure_files: list[str]) -> dict:
    if not (have(repo, green_sha) and have(repo, failing_sha)):
        return {"available": False, "green_sha": green_sha}
    _, log = git(repo, "log", "--format=%h%x09%an%x09%s", "--max-count=50", f"{green_sha}..{failing_sha}")
    _, names = git(repo, "diff", "--name-only", green_sha, failing_sha)
    files = [n for n in names.splitlines() if n]
    touched = set()
    wanted = [f for f in failure_files if f and not f.startswith(("/", "-")) and ".." not in f]
    if wanted:
        _, hits = git(repo, "log", "--format=%h", f"{green_sha}..{failing_sha}", "--", *wanted[:20])
        touched = set(hits.split())
    commits = []
    for line in log.splitlines():
        sha, _, rest = line.partition("\t")
        author, _, subject = rest.partition("\t")
        commits.append({"sha": sha, "author": author, "subject": subject[:200], "suspect": sha in touched})
    lock = deps_changed(files)
    return {"available": True, "green_sha": green_sha, "commits": commits, "files": files[:200],
            "deps_changed": lock, "lock_changed": bool(lock)}
