"""Pull requests and CI from GitHub (gh) or GitLab (glab): read-only, cached, refreshed in the background.

The band and the status line never wait for the network: they read the cache, and when it is stale
mizan starts `mizan refresh` detached (one at a time per repository, behind a lock file). Only
these read commands run, with arguments as a list (no shell):

    gh pr list --state open --json number,author,headRefName,headRefOid,url,isCrossRepository --limit 200
    gh pr list --state open --search review-requested:@me --json number --limit 100
    gh pr checks <number> --json name,bucket,link,workflow,event
    gh run list --branch=<branch> --limit 20
        --json databaseId,status,conclusion,name,headSha,url,startedAt,updatedAt,event,createdAt,
               workflowDatabaseId
    gh run list --commit=<head> --limit 20 --json ...   (detached, or the head is not in the list above,
        or the PR's only passing checks are pull_request_target ones: are its workflows waiting?)
    gh run list --workflow=<id> --status=completed --limit 20 --json ...
        (CI running and the branch has no finished run of that workflow: for the time left; by id,
        since two workflows may share a name)
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
RUN_FIELDS = ("databaseId,status,conclusion,name,headSha,url,startedAt,updatedAt,event,createdAt,"
              "workflowDatabaseId")


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

TITLES = {"mr", "mrs", "ms", "miss", "mx", "dr", "prof", "sir"}


def author_name(author: dict) -> str:
    """A person's first name ('Mr. RB' is RB), a bot's plain name ('app/dependabot' is dependabot)."""
    author = author if isinstance(author, dict) else {}
    login = str(author.get("login") or author.get("username") or "")
    if login.startswith("app/") or author.get("is_bot") or login.endswith("[bot]"):
        return login.removeprefix("app/").removesuffix("[bot]") or "?"
    words = str(author.get("name") or "").split()
    while words and words[0].lower().rstrip(".") in TITLES:
        words = words[1:]
    return first_name(" ".join(words)) or login or "?"


def per_user(names: list[str]) -> list[list]:
    counts = collections.Counter(names)
    return [[name, n] for name, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0].lower()))]


def parse_gh_prs(text: str, branch: str, head: str = "") -> dict:
    items = json.loads(text or "[]")
    names = [author_name(pr.get("author")) for pr in items]
    # A fork's pull request is this branch's only when its head is our commit: forks reuse names like main.
    mine = next((pr for pr in items if pr.get("headRefName") == branch
                 and (not pr.get("isCrossRepository") or (head and pr.get("headRefOid") == head))), None)
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
MAX_FAILED_RUNS = 5  # `gh run view` calls per refresh to name failed jobs


def job_label(workflow: str, job: str) -> str:
    """'workflow/job', so a job called 'check' says which workflow it belongs to."""
    return f"{workflow}/{job}" if workflow and job and workflow != job else (job or workflow or "?")
FAILED = ("failure", "timed_out", "startup_failure")  # cancelled is counted apart
# A run that waits for a maintainer's approval (a first-time contributor's fork) has not run. After
# 30 days GitHub ends it as failure with no jobs: still not run.
WAITING, EXPIRED_AFTER = "action_required", 29 * 86400


def parse_gh_checks(text: str) -> dict:
    checks = json.loads(text or "[]")
    bad = [c for c in checks if c.get("bucket") == "fail"]
    cancelled = [c.get("name", "?") for c in checks if c.get("bucket") == "cancel"]
    if bad:
        link = next((m.group(1) for c in bad if (m := RUN_LINK.search(c.get("link") or ""))), None)
        flows = list(dict.fromkeys(c.get("workflow") or "" for c in bad))
        bad.sort(key=lambda c: flows.index(c.get("workflow") or ""))  # each workflow's jobs together
        labels = [job_label(c.get("workflow") or "", c.get("name", "?")) for c in bad]
        return {"state": "failed", "failed": labels,
                "workflows": [w for w in flows if w],
                "run": int(link) if link else None, "cancelled": cancelled}
    if any(c.get("bucket") == "pending" for c in checks):
        return {"state": "running", "failed": []}
    if cancelled:
        return {"state": "cancelled", "failed": [], "cancelled": cancelled,
                "all_cancelled": not any(c.get("bucket") == "pass" for c in checks)}
    passing = [c for c in checks if c.get("bucket") == "pass"]
    if passing:
        # Only pull_request_target checks (a labeler) ran: the PR's own workflows may wait for approval.
        target_only = all(c.get("event") == "pull_request_target" for c in passing)
        return {"state": "passed", "failed": [], **({"target_only": True} if target_only else {})}
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
                  and (start := _when(r.get("startedAt")))
                  and (end := _when(r.get("updatedAt"))) and end > start)
    if not took:
        return {"elapsed": elapsed, "eta": None}
    usual = took[len(took) // 2]
    return {"elapsed": elapsed, "eta": max(0, usual - elapsed)}


def waited_out(run: dict) -> bool:
    """A failed run that ended a month after it was created: GitHub expired its wait for approval."""
    start, end = _when(run.get("createdAt")), _when(run.get("updatedAt"))
    return bool(start and end and end - start >= EXPIRED_AFTER)


def parse_gh_runs(text: str, head: str, now: float | None = None, history: list[dict] | None = None) -> dict:
    """history: more runs (other commits, other branches) to learn a workflow's usual duration from."""
    every = json.loads(text or "[]")
    runs = pick_runs(every, head)
    if not runs:
        return {"state": "none", "failed": [], "failed_run": None}
    done = [r for r in runs if r.get("status") == "completed"]
    bad = [r for r in done if r.get("conclusion") in FAILED]
    cancelled = [r.get("name", "?") for r in done if r.get("conclusion") == "cancelled"]
    if bad:
        found = {"state": "failed", "failed": [r.get("name", "?") for r in bad], "cancelled": cancelled,
                 "failed_run": bad[0].get("databaseId"), "url": bad[0].get("url", ""),
                 "failed_runs": [[r.get("databaseId"), r.get("name", "?")] for r in bad]}
        if all(waited_out(r) for r in bad):
            found["maybe_expired"] = True  # fetch_ci looks at one run's jobs: none means it never ran
        return found
    going = [r for r in runs if r.get("status") != "completed"]
    if going:
        return {"state": "running", "failed": [], "failed_run": None,
                **timing(every if history is None else history, going, now)}
    waiting = [r.get("name", "?") for r in done if r.get("conclusion") == WAITING]
    if waiting:
        return {"state": "approval", "failed": [], "failed_run": None, "waiting": waiting}
    if cancelled:  # cancelled is not failed: a newer push or a fail-fast matrix stopped it
        ran = [r for r in done if r.get("conclusion") not in ("skipped", "neutral")]
        return {"state": "cancelled", "failed": [], "failed_run": None, "cancelled": cancelled,
                "all_cancelled": len(cancelled) == len(ran)}
    return {"state": "passed", "failed": [], "failed_run": None}


def parse_gh_jobs(text: str) -> dict:
    """The failed jobs of a run, and apart from them the cancelled ones."""
    jobs = json.loads(text or "{}").get("jobs") or []
    return {"failed": [j.get("name", "?") for j in jobs if j.get("conclusion") in FAILED],
            "cancelled": [j.get("name", "?") for j in jobs if j.get("conclusion") == "cancelled"]}


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
    except subprocess.TimeoutExpired as error:
        raise Off("off_timeout", argv[0]) from error
    except (OSError, subprocess.SubprocessError) as error:
        raise Off("off_error", argv[0]) from error
    if done.returncode not in accept_codes and not done.stdout.strip().startswith(("[", "{")):
        lowered = done.stderr.lower()
        if "auth login" in lowered or "not logged" in lowered or "authenticat" in lowered:
            raise Off("off_auth", argv[0])
        if "rate limit" in lowered:
            raise Off("off_ratelimit", argv[0])
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
                    "number,author,headRefName,headRefOid,url,isCrossRepository", "--limit", "200"]
            found = parse_gh_prs(run_tool(argv, cwd), branch, info.get("head", ""))
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


def detached(info: dict) -> bool:
    """A detached HEAD: gitinfo names the branch after the commit's first 8 characters."""
    head = info.get("head") or ""
    return bool(head) and info.get("branch") == head[:8]


def ours(info: dict, runs: list[dict]) -> list[dict]:
    """Runs of this branch's own commits: a fork's pull request may share the branch's name."""
    head, repo, branch = info.get("head", ""), info["repo"], info.get("branch", "")
    keep = []
    for r in runs:
        sha = r.get("headSha", "")
        if sha == head or on_remote_branch(repo, sha, branch):
            keep.append(r)
    return keep


def finish_runs(found: dict, cwd: str) -> dict:
    """parse_gh_runs's answer with every failed workflow's failed jobs (`gh run view`), or, when the
    failed runs are a month old with no jobs, the approval that never came."""
    run_id = found.pop("failed_run", None)
    found["run"] = run_id
    failed_runs = found.pop("failed_runs", [])
    if found.pop("maybe_expired", False) and failed_runs:
        text = run_tool(["gh", "run", "view", str(int(failed_runs[0][0])), "--json", "jobs"], cwd)
        if not (json.loads(text or "{}") or {}).get("jobs"):
            return {"state": "approval", "expired": True, "failed": [], "run": None,
                    "waiting": [workflow for _, workflow in failed_runs]}
    if failed_runs:  # every failed workflow, each with its failed jobs
        failed = []
        for number, workflow in failed_runs[:MAX_FAILED_RUNS]:
            jobs = parse_gh_jobs(run_tool(["gh", "run", "view", str(int(number)), "--json", "jobs"], cwd))
            failed += [job_label(workflow, job) for job in jobs["failed"]] or [workflow]
            found["cancelled"] = found.get("cancelled", []) + jobs["cancelled"]
        found["failed"] = failed + [workflow for _, workflow in failed_runs[MAX_FAILED_RUNS:]]
        found["workflows"] = list(dict.fromkeys(workflow for _, workflow in failed_runs))
    return found


def fetch_ci(info: dict, pr: dict | None) -> dict:
    tool = TOOL.get(info.get("host"), "gh")
    cwd, branch = info["repo"], info.get("branch", "")
    try:
        if tool == "glab":
            argv = ["glab", "ci", "get", f"--branch={branch}", "--output", "json"]
            return parse_glab_pipeline(run_tool(argv, cwd))
        checks = None
        fields = ["--json", RUN_FIELDS, "--limit", "20"]
        head = info.get("head", "")
        if pr and pr.get("number"):
            argv = ["gh", "pr", "checks", str(int(pr["number"])), "--json", "name,bucket,link,workflow,event"]
            checks = parse_gh_checks(run_tool(argv, cwd, accept_codes=(0, 1, 8)))
            if checks.pop("target_only", False) and re.match(r"^[0-9a-f]{7,64}$", head):
                # `gh pr checks` leaves out runs waiting for approval: ask for the commit's runs.
                by_commit = run_tool(["gh", "run", "list", f"--commit={head}", *fields], cwd)
                found = finish_runs(parse_gh_runs(by_commit, head), cwd)
                if found["state"] == "approval":
                    return found
            if checks["state"] not in ("none", "running"):
                return checks
            # Running: the run list below says for how long, and about how long is left.
        listed = [] if detached(info) else json.loads(
            run_tool(["gh", "run", "list", f"--branch={branch}", *fields], cwd) or "[]")
        mine = ours(info, listed)
        if re.match(r"^[0-9a-f]{7,64}$", head) and not any(r.get("headSha") == head for r in mine):
            # A detached HEAD, or a commit older than the branch's newest 20 runs: ask by commit.
            by_commit = json.loads(run_tool(["gh", "run", "list", f"--commit={head}", *fields], cwd) or "[]")
            mine = [r for r in by_commit if r.get("headSha") == head] or mine
        history = listed + [r for r in mine if r not in listed]  # all of them: durations for the time left
        found = parse_gh_runs(json.dumps(mine), head, history=history)
        if found["state"] == "running" and found.get("elapsed") is not None and found.get("eta") is None:
            # No finished run of this workflow on the branch (a fork's new branch): its recent runs anywhere.
            going = next((r for r in pick_runs(mine, head)
                          if r.get("status") != "completed" and r.get("name")), {})
            workflow = going.get("workflowDatabaseId") or going.get("name")
            if workflow:
                try:  # only the time left: an error here never hides that CI is running
                    recent = json.loads(run_tool(["gh", "run", "list", f"--workflow={workflow}",
                                                  "--status=completed", "--json",
                                                  "name,status,conclusion,startedAt,updatedAt",
                                                  "--limit", "20"], cwd) or "[]")
                    found = parse_gh_runs(json.dumps(mine), head, history=history + recent)
                except (Off, ValueError, TypeError):
                    pass
        if checks and checks["state"] == "running" and found["state"] != "running":
            return checks
        return finish_runs(found, cwd)
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
    due = (not fresh(prs, PR_TTL * factor) or not fresh(ci, ci_ttl(ci) * factor)
           or bool(ci and ci.get("stale") and not ci.get("error")))  # gh in trouble: wait the TTL
    return {"prs": prs, "ci": ci, "due": due}


def _gist(prs: dict | None, ci: dict | None) -> list:
    """What the person would see change: not when it was fetched."""
    prs, ci = prs or {}, ci or {}
    return [prs.get("state"), prs.get("per_user"), prs.get("branch_pr"),
            ci.get("state"), ci.get("run"), ci.get("failed"), ci.get("head")]


PASSING = ("off_error", "off_timeout", "off_ratelimit")  # gh may answer next time


def keep_known(new: dict, old: dict | None) -> dict:
    """One gh error does not erase what was known: the last good result stays, marked with the error."""
    known = bool(old) and old.get("state") not in (None, "off")
    if new.get("state") == "off" and new.get("why") in PASSING and known:
        return {**old, "error": new["why"], "tool": new.get("tool") or old.get("tool"),
                "fetched": new["fetched"]}
    return {k: v for k, v in new.items() if k != "error"}


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
    if not fresh(prs, PR_TTL) or (prs or {}).get("state") != "ok" or (prs or {}).get("error"):
        prs = keep_known({**fetch_prs(info), "fetched": time.time()}, prs)
    trouble = prs.get("error") or (prs.get("why") if prs.get("state") == "off" else "")
    if trouble in ("off_timeout", "off_ratelimit"):  # gh just timed out or was refused: don't wait twice
        found = {"state": "off", "why": trouble, "tool": prs.get("tool") or "gh"}
    else:
        found = fetch_ci(info, prs.get("branch_pr"))
    ci = keep_known({**found, "fetched": time.time(), "head": info.get("head")}, before)
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
