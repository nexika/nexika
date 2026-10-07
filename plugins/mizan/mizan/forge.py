"""Pull requests and CI from GitHub (gh) or GitLab (glab): read-only, cached, refreshed in the background.

The band and the status line never wait for the network: they read the cache, and when it is stale
mizan starts `mizan refresh` detached (one at a time per repository, behind a lock file). Only
these read commands run, with arguments as a list (no shell):

    gh pr list --state open --json number,author,headRefName,url --limit 200
    gh pr list --state open --search review-requested:@me --json number --limit 100
    gh pr checks <number> --json name,bucket,link
    gh run list --branch=<branch> --json databaseId,status,conclusion,name,headSha,url,startedAt,updatedAt --limit 20
    gh run view <id> --json jobs
    glab mr list --output json
    glab mr list --reviewer=@me --output json
    glab ci get --branch=<branch> --output json
"""
from __future__ import annotations

import collections
import datetime
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

from . import config, family, status
from .gitinfo import first_name

PR_TTL, CI_TTL, CI_RUNNING_TTL, LOCK_TTL = 300, 90, 45, 360  # a refresh may wait up to 180 s for tabib
# Nothing changed for IDLE_AFTER seconds (same commit, same PRs, same CI result, CI not running):
# ask IDLE_FACTOR times less often. A new commit is still fetched at once.
IDLE_AFTER, IDLE_FACTOR = 600, 4
BIN = Path(__file__).resolve().parent.parent / "bin" / "mizan"
TOOL = {"github": "gh", "gitlab": "glab"}


def cache_path(repo: str) -> Path:
    return config.home() / "cache" / (hashlib.sha1(repo.encode()).hexdigest()[:16] + ".json")


def load_cache(repo: str) -> dict:
    try:
        with open(cache_path(repo), encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def save_cache(repo: str, data: dict) -> None:
    path = cache_path(repo)
    status.ensure_dir(path.parent)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False)
    os.replace(tmp, path)


# ------------------------------------------------------------------ parsing (pure, tested)

def author_name(author: dict) -> str:
    author = author if isinstance(author, dict) else {}
    return first_name(author.get("name") or "") or author.get("login") or author.get("username") or "?"


def per_user(names: list[str]) -> list[list]:
    counts = collections.Counter(names)
    return [[name, n] for name, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0].lower()))]


def parse_gh_prs(text: str, branch: str) -> dict:
    items = json.loads(text or "[]")
    names = [author_name(pr.get("author")) for pr in items]
    mine = next((pr for pr in items
                 if pr.get("headRefName") == branch and not pr.get("isCrossRepository")), None)
    found = {"state": "ok", "tool": "gh", "total": len(items), "per_user": per_user(names),
             "branch_pr": None}
    if mine:
        found["branch_pr"] = {"number": mine.get("number"), "author": author_name(mine.get("author")),
                              "url": mine.get("url", "")}
    return found


def parse_glab_mrs(text: str, branch: str) -> dict:
    items = json.loads(text or "[]")
    names = [author_name(mr.get("author")) for mr in items]
    mine = next((mr for mr in items if mr.get("source_branch") == branch), None)
    found = {"state": "ok", "tool": "glab", "total": len(items), "per_user": per_user(names),
             "branch_pr": None}
    if mine:
        found["branch_pr"] = {"number": mine.get("iid"), "author": author_name(mine.get("author")),
                              "url": mine.get("web_url", "")}
    return found


RUN_LINK = re.compile(r"/actions/runs/(\d+)")


def parse_gh_checks(text: str) -> dict:
    checks = json.loads(text or "[]")
    bad = [c for c in checks if c.get("bucket") in ("fail", "cancel")]
    if bad:
        link = next((m.group(1) for c in bad if (m := RUN_LINK.search(c.get("link") or ""))), None)
        return {"state": "failed", "failed": [c.get("name", "?") for c in bad],
                "run": int(link) if link else None}
    if any(c.get("bucket") == "pending" for c in checks):
        return {"state": "running", "failed": []}
    if any(c.get("bucket") == "pass" for c in checks):
        return {"state": "passed", "failed": []}
    return {"state": "none", "failed": []}


def pick_runs(runs: list[dict], head: str) -> list[dict]:
    """The workflow runs of the local HEAD commit, else of the newest commit that has runs."""
    same = [r for r in runs if r.get("headSha") == head]
    if same or not runs:
        return same
    return [r for r in runs if r.get("headSha") == runs[0].get("headSha")]


def _when(value) -> float | None:
    try:
        return datetime.datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        return None


def timing(all_runs: list[dict], running: list[dict], now: float | None = None) -> dict:
    """How long the running workflow has run, and about how long is left: its usual duration (the
    median of its recent finished runs, passed or failed) minus that."""
    now = time.time() if now is None else now
    starts = [s for s in (_when(r.get("startedAt")) for r in running) if s]
    if not starts:
        return {}
    elapsed = max(0, int(now - min(starts)))
    names = {r.get("name") for r in running}
    took = sorted(int(end - start) for r in all_runs
                  if r.get("status") == "completed" and r.get("name") in names
                  and r.get("conclusion") in ("success", "failure")
                  and (start := _when(r.get("startedAt"))) and (end := _when(r.get("updatedAt"))) and end > start)
    if not took:
        return {"elapsed": elapsed, "eta": None}
    usual = took[len(took) // 2]
    return {"elapsed": elapsed, "eta": max(0, usual - elapsed)}


def parse_gh_runs(text: str, head: str, now: float | None = None) -> dict:
    every = json.loads(text or "[]")
    runs = pick_runs(every, head)
    if not runs:
        return {"state": "none", "failed": [], "failed_run": None}
    bad = [r for r in runs if r.get("status") == "completed"
           and r.get("conclusion") in ("failure", "cancelled", "timed_out", "startup_failure")]
    if bad:
        return {"state": "failed", "failed": [r.get("name", "?") for r in bad],
                "failed_run": bad[0].get("databaseId"), "url": bad[0].get("url", "")}
    going = [r for r in runs if r.get("status") != "completed"]
    if going:
        return {"state": "running", "failed": [], "failed_run": None, **timing(every, going, now)}
    return {"state": "passed", "failed": [], "failed_run": None}


def parse_gh_jobs(text: str) -> list[str]:
    jobs = json.loads(text or "{}").get("jobs") or []
    return [j.get("name", "?") for j in jobs
            if j.get("conclusion") in ("failure", "cancelled", "timed_out", "startup_failure")]


def parse_glab_pipeline(text: str) -> dict:
    pipeline = json.loads(text or "{}") or {}
    status = (pipeline.get("status") or "").lower()
    jobs = pipeline.get("jobs") or []
    failed = [j.get("name", "?") for j in jobs if (j.get("status") or "").lower() in ("failed", "canceled")]
    url = pipeline.get("web_url", "")
    if status in ("failed", "canceled") or failed:
        return {"state": "failed", "failed": failed, "url": url, "run": pipeline.get("id")}
    if status in ("running", "pending", "created", "preparing", "waiting_for_resource", "scheduled"):
        return {"state": "running", "failed": [], "url": url}
    if status == "success":
        return {"state": "passed", "failed": [], "url": url}
    return {"state": "none", "failed": [], "url": url}


# ------------------------------------------------------------------ running gh / glab

class Off(Exception):
    """gh or glab cannot answer: reason is an i18n key, tool its name."""

    def __init__(self, reason: str, tool: str):
        super().__init__(reason)
        self.reason, self.tool = reason, tool


def run_tool(argv: list[str], cwd: str, accept_codes: tuple[int, ...] = (0,)) -> str:
    env = {**os.environ, "GH_PROMPT_DISABLED": "1", "NO_COLOR": "1", "GLAB_NO_PROMPT": "1",
           "GH_NO_UPDATE_NOTIFIER": "1"}
    try:
        done = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, timeout=20, env=env, check=False)
    except FileNotFoundError as error:
        raise Off("off_tool", argv[0]) from error
    except (OSError, subprocess.SubprocessError) as error:
        raise Off("off_error", argv[0]) from error
    if done.returncode not in accept_codes and not done.stdout.strip().startswith(("[", "{")):
        lowered = done.stderr.lower()
        if "auth login" in lowered or "not logged" in lowered or "authenticat" in lowered:
            raise Off("off_auth", argv[0])
        raise Off("off_error", argv[0])
    return done.stdout


def fetch_prs(info: dict) -> dict:
    tool = TOOL.get(info.get("host"), "gh")
    cwd, branch = info["repo"], info.get("branch", "")
    try:
        if tool == "glab":
            found = parse_glab_mrs(run_tool(["glab", "mr", "list", "--output", "json"], cwd), branch)
            mine = ["glab", "mr", "list", "--reviewer=@me", "--output", "json"]
        else:
            argv = ["gh", "pr", "list", "--state", "open", "--json",
                    "number,author,headRefName,url,isCrossRepository", "--limit", "200"]
            found = parse_gh_prs(run_tool(argv, cwd), branch)
            mine = ["gh", "pr", "list", "--state", "open", "--search", "review-requested:@me", "--json",
                    "number", "--limit", "100"]
        try:  # reviews waiting for you: a bonus, never a reason to lose the PR list
            found["reviews"] = len(json.loads(run_tool(mine, cwd) or "[]"))
        except (Off, ValueError, TypeError):
            found["reviews"] = None
        return found
    except Off as off:
        return {"state": "off", "why": off.reason, "tool": off.tool}
    except ValueError:
        return {"state": "off", "why": "off_error", "tool": tool}


def on_remote_branch(repo: str, sha: str, branch: str) -> bool:
    """The commit is in origin's branch as this clone last saw it (local git, no network)."""
    if not (re.match(r"^[0-9a-f]{7,64}$", sha or "") and re.match(r"^[\w][\w./-]*$", branch or "")):
        return False
    try:
        done = subprocess.run(["git", "merge-base", "--is-ancestor", sha, f"refs/remotes/origin/{branch}"],
                              cwd=repo, capture_output=True, timeout=10, check=False)
    except (OSError, subprocess.SubprocessError):
        return False
    return done.returncode == 0


def ours(info: dict, runs: list[dict]) -> list[dict]:
    """Runs of this branch's own commits: a fork's pull request may share the branch's name."""
    head, repo, branch = info.get("head", ""), info["repo"], info.get("branch", "")
    keep = []
    for r in runs:
        sha = r.get("headSha", "")
        if sha == head or on_remote_branch(repo, sha, branch):
            keep.append(r)
    return keep


def fetch_ci(info: dict, pr: dict | None) -> dict:
    tool = TOOL.get(info.get("host"), "gh")
    cwd, branch = info["repo"], info.get("branch", "")
    try:
        if tool == "glab":
            argv = ["glab", "ci", "get", f"--branch={branch}", "--output", "json"]
            return parse_glab_pipeline(run_tool(argv, cwd))
        checks = None
        if pr and pr.get("number"):
            checks = parse_gh_checks(run_tool(["gh", "pr", "checks", str(int(pr["number"])), "--json",
                                               "name,bucket,link"], cwd, accept_codes=(0, 1, 8)))
            if checks["state"] not in ("none", "running"):
                return checks
            # Running: the run list below says for how long, and about how long is left.
        argv = ["gh", "run", "list", f"--branch={branch}", "--json",
                "databaseId,status,conclusion,name,headSha,url,startedAt,updatedAt", "--limit", "20"]
        mine = ours(info, json.loads(run_tool(argv, cwd) or "[]"))
        found = parse_gh_runs(json.dumps(mine), info.get("head", ""))
        if checks and checks["state"] == "running" and found["state"] != "running":
            return checks
        run_id = found.pop("failed_run", None)
        found["run"] = run_id
        if run_id:
            jobs = parse_gh_jobs(run_tool(["gh", "run", "view", str(int(run_id)), "--json", "jobs"], cwd))
            found["failed"] = jobs or found["failed"]
        return found
    except Off as off:
        return {"state": "off", "why": off.reason, "tool": off.tool}
    except (ValueError, TypeError):
        return {"state": "off", "why": "off_error", "tool": tool}


# ------------------------------------------------------------------ cache and background refresh

def fresh(entry: dict | None, ttl: float) -> bool:
    return bool(entry) and time.time() - float(entry.get("fetched") or 0) < ttl


def ci_ttl(entry: dict | None) -> float:
    return CI_RUNNING_TTL if (entry or {}).get("state") == "running" else CI_TTL


def idle(data: dict, ci: dict | None) -> bool:
    """Nothing has changed for IDLE_AFTER seconds and no CI run is going: poll less."""
    changed = float(data.get("changed") or 0)
    return bool(changed) and time.time() - changed > IDLE_AFTER and (ci or {}).get("state") != "running"


def cached(info: dict) -> dict:
    """{prs, ci} from the cache (either may be None: not fetched yet), and whether a refresh is due."""
    data = load_cache(info["repo"])
    prs = data.get("prs")
    ci = (data.get("ci") or {}).get(info.get("branch", ""))
    if ci and ci.get("head") != info.get("head"):
        ci = {**ci, "stale": True}  # a new commit: the old result stays shown until the new one is in
    factor = IDLE_FACTOR if idle(data, ci) else 1
    due = not fresh(prs, PR_TTL * factor) or not fresh(ci, ci_ttl(ci) * factor) or bool(ci and ci.get("stale"))
    return {"prs": prs, "ci": ci, "due": due}


def _gist(prs: dict | None, ci: dict | None) -> list:
    """What the person would see change: not when it was fetched."""
    prs, ci = prs or {}, ci or {}
    return [prs.get("state"), prs.get("per_user"), prs.get("branch_pr"),
            ci.get("state"), ci.get("run"), ci.get("failed"), ci.get("head")]


def refresh(info: dict) -> dict:
    """Ask gh or glab now and store the answers (what `mizan refresh` runs)."""
    if not info.get("host") and not info.get("remote"):
        off = {"state": "off", "why": "off_remote", "tool": "", "fetched": time.time()}
        data = {"prs": off, "ci": {info.get("branch", ""): {**off, "head": info.get("head")}}}
        save_cache(info["repo"], data)
        return data
    data = load_cache(info["repo"])
    branch = info.get("branch", "")
    before = (data.get("ci") or {}).get(branch)
    prs = data.get("prs")
    if not fresh(prs, PR_TTL) or (prs or {}).get("state") != "ok":
        prs = {**fetch_prs(info), "fetched": time.time()}
    ci = {**fetch_ci(info, prs.get("branch_pr")), "fetched": time.time(), "head": info.get("head")}
    if before and before.get("tabib") and before.get("run") == ci.get("run"):
        ci["tabib"] = before["tabib"]
    if _gist(prs, ci) != _gist(data.get("prs"), before) or not data.get("changed"):
        data["changed"] = time.time()
    data["prs"] = prs

    def store(found: dict) -> None:
        data["ci"] = {**{k: v for k, v in (data.get("ci") or {}).items()
                         if time.time() - float(v.get("fetched") or 0) < 86400}, branch: found}
        save_cache(info["repo"], data)

    store(ci)  # shown now: tabib's triage below can take seconds
    triaged = with_triage(info, ci, before)
    if triaged != ci:
        store(triaged)
    return data


def with_triage(info: dict, ci: dict, before: dict | None) -> dict:
    """A newly failed run gets tabib's triage (no AI, no code run), once per run: what kind of failure."""
    if ci.get("state") != "failed" or not ci.get("run"):
        return ci
    tabib = family.find_plugin("tabib")  # tabib keeps one reading per run and attempt: asking again is cheap
    if tabib is None:
        return ci
    argv = [sys.executable, str(tabib / "bin" / "tabib"), "triage", "--run", str(int(ci["run"])), "--json",
            "--cwd", info["repo"]]
    try:
        done = subprocess.run(argv, cwd=info["repo"], capture_output=True, text=True, timeout=180,
                              check=False)
        found = json.loads(done.stdout or "{}")
    except (OSError, subprocess.SubprocessError, ValueError):
        return ci
    if not isinstance(found, dict) or "kind" not in found:
        return ci
    return {**ci, "tabib": {k: found.get(k) for k in ("run", "kind", "detail", "confidence")}}


def _take_lock(repo: str) -> bool:
    lock = cache_path(repo).with_suffix(".lock")
    status.ensure_dir(lock.parent)
    try:
        if time.time() - lock.stat().st_mtime > LOCK_TTL:
            lock.unlink()
    except OSError:
        pass
    try:
        os.close(os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600))
    except OSError:
        return False
    return True


def release_lock(repo: str) -> None:
    try:
        cache_path(repo).with_suffix(".lock").unlink()
    except OSError:
        pass


def ensure_fresh(info: dict) -> bool:
    """Start `mizan refresh` in the background when the cache is stale; True when one was started."""
    if not info or not config.network() or not cached(info)["due"] or not _take_lock(info["repo"]):
        return False
    try:
        subprocess.Popen([sys.executable, str(BIN), "refresh", "--locked", "--cwd", info["repo"]],
                         cwd=info["repo"], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, start_new_session=True, close_fds=True)
    except OSError:
        release_lock(info["repo"])
        return False
    return True
