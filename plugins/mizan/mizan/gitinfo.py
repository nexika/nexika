"""The repository: branch, who started it, the remote's host. Local git reads only, no network.

The branch creator is the author of the branch's first commit of its own (commits not on the
default branch); with none yet it is you (git's user.name). A pull request's author, when one is
known, takes precedence (snapshot.py applies that).
"""
from __future__ import annotations

import re
import subprocess
from urllib.parse import urlparse


def git(cwd: str, *args: str, timeout: float = 4) -> str:
    try:
        done = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, timeout=timeout,
                              check=False)
    except (OSError, subprocess.SubprocessError):
        return ""
    return done.stdout.strip() if done.returncode == 0 else ""


def first_name(name: str) -> str:
    return (name or "").strip().split()[0] if (name or "").strip() else ""


def host_of(remote: str) -> str:
    """'github', 'gitlab' or '' for a remote URL (https, ssh or scp-like)."""
    if not remote:
        return ""
    match = re.match(r"^[\w.-]+@([\w.-]+):", remote)
    host = match.group(1) if match else (urlparse(remote).hostname or "")
    host = host.lower()
    if host == "github.com" or host.endswith(".github.com") or host.startswith("github."):
        return "github"
    if "gitlab" in host:
        return "gitlab"
    return ""


def default_branch(cwd: str) -> str:
    head = git(cwd, "rev-parse", "--abbrev-ref", "origin/HEAD")
    if head.startswith("origin/") and head != "origin/HEAD":
        return head[len("origin/"):]
    for name in ("main", "master", "trunk", "develop"):
        if git(cwd, "rev-parse", "--verify", "--quiet", f"refs/heads/{name}"):
            return name
    return ""


def read(cwd: str) -> dict:
    top = git(cwd, "rev-parse", "--show-toplevel")
    if not top:
        return {}
    branch = git(cwd, "rev-parse", "--abbrev-ref", "HEAD")
    head = git(cwd, "rev-parse", "HEAD")
    if branch == "HEAD":
        branch = head[:8]  # detached
    default = default_branch(cwd)
    remote = git(cwd, "remote", "get-url", "origin")
    info = {"repo": top, "branch": branch, "default": default, "head": head, "remote": remote,
            "host": host_of(remote), "creator": "", "creator_source": ""}
    if not branch or branch == default:
        return info
    base = ""
    for ref in (f"origin/{default}", default):
        if default and git(cwd, "rev-parse", "--verify", "--quiet", ref):
            base = ref
            break
    authors = git(cwd, "log", "--reverse", "--format=%an", f"{base}..HEAD") if base else ""
    first = authors.splitlines()[0] if authors else ""
    if first:
        info.update(creator=first_name(first), creator_source="commit")
    else:
        info.update(creator=first_name(git(cwd, "config", "user.name")), creator_source="user")
    return info
