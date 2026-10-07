"""The failing CI run, its jobs, its failed log and its history: read-only gh (GitHub) and glab (GitLab).

Every command is a fixed read with its arguments as a list (no shell); branch names go in as
`--branch=<name>` or URL-encoded, run ids through int(), so nothing from a log or a branch name can
become a flag. tabib never re-runs, cancels or edits a run.

    gh run list --branch=<b> --json ... --limit 30
    gh run view <id> --json ...            gh run view <id> --log-failed
    gh run view <id> --attempt <n> --json ... / --log-failed       (earlier attempts, for flaky tests)
    glab api --method GET projects/:id/pipelines?ref=<b>    .../pipelines/<id>/jobs    .../jobs/<id>/trace
"""
from __future__ import annotations

import json
import os
import subprocess
from urllib.parse import quote

from . import compare, parse
from .parse import clean_text

RUN_FIELDS = ("databaseId,status,conclusion,name,workflowName,headSha,headBranch,event,createdAt,attempt,"
              "url,number,updatedAt")
VIEW_FIELDS = RUN_FIELDS + ",jobs"
FAILED = ("failure", "timed_out", "cancelled", "startup_failure")
LOG_LIMIT = 8 * 1024 * 1024
PAST_RUNS = 10   # earlier runs (and attempts) of the same commit looked at for flaky tests
PAST_LOGS = 5    # of which at most this many failed logs are read
GITLAB = {"failed": "failure", "success": "success", "canceled": "cancelled", "skipped": "skipped"}


class Off(Exception):
    """gh or glab cannot answer: the message says why in a few words."""


def run_tool(argv: list[str], cwd: str, timeout: int = 60, accept: tuple[int, ...] = (0,)) -> str:
    env = {**os.environ, "GH_PROMPT_DISABLED": "1", "NO_COLOR": "1", "GLAB_NO_PROMPT": "1",
           "GH_NO_UPDATE_NOTIFIER": "1", "GH_PAGER": "cat", "PAGER": "cat"}
    try:
        done = subprocess.run(argv, cwd=cwd, capture_output=True, timeout=timeout, env=env, check=False)
    except FileNotFoundError as error:
        raise Off(f"{argv[0]} is not installed") from error
    except (OSError, subprocess.SubprocessError) as error:
        raise Off(f"{argv[0]} did not answer") from error
    out = done.stdout[:LOG_LIMIT].decode("utf-8", "replace")
    if done.returncode not in accept:
        err = done.stderr.decode("utf-8", "replace").lower()
        if "auth login" in err or "not logged" in err or "authenticat" in err:
            raise Off(f"{argv[0]} is not signed in")
        raise Off(f"{argv[0]} failed: {err.strip()[:160]}")
    return out


def _json(text: str):
    try:
        return json.loads(text or "null")
    except ValueError as error:
        raise Off("unexpected answer from the CI tool") from error


# ------------------------------------------------------------------ GitHub

def _gh_run(item: dict) -> dict:
    jobs = []
    for job in item.get("jobs") or []:
        failed_step = next((s.get("name", "") for s in job.get("steps") or []
                            if s.get("conclusion") in FAILED), "")
        jobs.append({"id": job.get("databaseId"), "name": clean_text(job.get("name", ""))[:200],
                     "conclusion": job.get("conclusion") or job.get("status", ""),
                     "failed_step": failed_step})
    return {"provider": "github", "id": item.get("databaseId"), "url": item.get("url", ""),
            "workflow": clean_text(item.get("workflowName") or item.get("name", ""))[:120],
            "sha": item.get("headSha", ""), "branch": clean_text(item.get("headBranch", ""))[:200],
            "event": item.get("event", ""),
            "attempt": item.get("attempt") or 1, "number": item.get("number"),
            "created": item.get("createdAt", ""), "updated": item.get("updatedAt", ""),
            "conclusion": item.get("conclusion", ""), "status": item.get("status", ""), "jobs": jobs}


def gh_runs(cwd: str, branch: str, workflow: str = "") -> list[dict]:
    argv = ["gh", "run", "list", f"--branch={branch}", "--json", RUN_FIELDS, "--limit", "30"]
    if workflow:
        argv.insert(4, f"--workflow={workflow}")
    return [_gh_run(item) for item in _json(run_tool(argv, cwd)) or []]


def gh_view(cwd: str, run_id: int, attempt: int = 0) -> dict:
    argv = ["gh", "run", "view", str(int(run_id)), "--json", VIEW_FIELDS]
    if attempt:
        argv[4:4] = ["--attempt", str(int(attempt))]
    return _gh_run(_json(run_tool(argv, cwd)) or {})


# ------------------------------------------------------------------ GitLab

def _glab(cwd: str, path: str, raw: bool = False):
    text = run_tool(["glab", "api", "--method", "GET", path], cwd)
    return text if raw else _json(text)


def _gl_run(pipeline: dict, jobs: list[dict]) -> dict:
    return {"provider": "gitlab", "id": pipeline.get("id"), "url": pipeline.get("web_url", ""),
            "workflow": pipeline.get("source") or "pipeline", "sha": pipeline.get("sha", ""),
            "branch": pipeline.get("ref", ""), "event": pipeline.get("source", ""), "attempt": 1,
            "number": pipeline.get("iid"), "created": pipeline.get("created_at", ""),
            "updated": pipeline.get("updated_at", ""),
            "conclusion": GITLAB.get(pipeline.get("status", ""), pipeline.get("status", "")),
            "status": "completed" if pipeline.get("status") in GITLAB else pipeline.get("status", ""),
            "jobs": [{"id": j.get("id"), "name": clean_text(j.get("name", ""))[:200],
                      "conclusion": GITLAB.get(j.get("status", ""), j.get("status", "")),
                      "failed_step": j.get("stage", "") if j.get("status") == "failed" else ""}
                     for j in jobs]}


def gl_runs(cwd: str, branch: str) -> list[dict]:
    pipelines = _glab(cwd, f"projects/:id/pipelines?ref={quote(branch, safe='')}&per_page=20") or []
    return [_gl_run(p, []) for p in pipelines]


def gl_view(cwd: str, run_id: int) -> dict:
    pipeline = _glab(cwd, f"projects/:id/pipelines/{int(run_id)}") or {}
    jobs = _glab(cwd, f"projects/:id/pipelines/{int(run_id)}/jobs?per_page=100") or []
    return _gl_run(pipeline, jobs)


# ------------------------------------------------------------------ either

def runs(info: dict, branch: str = "", workflow: str = "") -> list[dict]:
    branch = branch or info.get("branch", "")
    if info.get("host") == "gitlab":
        return gl_runs(info["repo"], branch)
    return gh_runs(info["repo"], branch, workflow)


def view(info: dict, run_id: int) -> dict:
    return gl_view(info["repo"], run_id) if info.get("host") == "gitlab" else gh_view(info["repo"], run_id)


def find_run(info: dict, run_id: int | None = None) -> dict:
    """The run to diagnose: the one asked for, else the newest failed run of the branch (HEAD's first)."""
    if run_id:
        return view(info, run_id)
    recent = runs(info)
    found = [r for r in recent if r["conclusion"] in FAILED
             and (r["sha"] == info.get("head")
                  or compare.on_remote_branch(info["repo"], r["sha"], info["branch"]))
             and not any(o["conclusion"] == "success" and o.get("workflow") == r.get("workflow")
                         and o.get("created", "") > r.get("created", "") for o in recent)]
    if not found:
        raise Off("no failed run to diagnose: CI is green on this branch, or its failures were fixed")
    head = [r for r in found if r["sha"] == info.get("head")]
    return view(info, (head or found)[0]["id"])


def from_fork(info: dict, run: dict) -> bool | None:
    """Whether the run tested another repository's code (a fork's pull request); None when unknown."""
    try:
        if run["provider"] == "github":
            data = _json(run_tool(["gh", "api", f"repos/{{owner}}/{{repo}}/actions/runs/{int(run['id'])}"],
                                  info["repo"]))
            head = ((data or {}).get("head_repository") or {}).get("full_name")
            base = ((data or {}).get("repository") or {}).get("full_name")
            return None if not base else head != base
        pipeline = _glab(info["repo"], f"projects/:id/pipelines/{int(run['id'])}") or {}
        # a merge request pipeline may carry a fork's code: treated as not ours
        return pipeline.get("source") in ("merge_request_event", "external_pull_request_event")
    except (Off, TypeError, ValueError):
        return None


def failed_log(info: dict, run: dict, attempt: int = 0) -> str:
    """The failed part of the log, as `job<TAB>step<TAB>line` lines (GitHub: of one attempt when given)."""
    if run["provider"] == "github":
        argv = ["gh", "run", "view", str(int(run["id"])), "--log-failed"]
        if attempt:
            argv[4:4] = ["--attempt", str(int(attempt))]
        text = run_tool(argv, info["repo"], timeout=120)
        for job in run["jobs"]:
            if job["conclusion"] in ("cancelled", "timed_out", "startup_failure") and job.get("id"):
                try:
                    path = f"repos/{{owner}}/{{repo}}/check-runs/{int(job['id'])}/annotations"
                    notes = _json(run_tool(["gh", "api", path], info["repo"])) or []
                except Off:
                    notes = []
                text += "".join(f"\n{job['name']}\tannotation\t{n.get('message', '')}" for n in notes[:10]
                                if isinstance(n, dict))
        return text
    parts = []
    for job in run["jobs"]:
        if job["conclusion"] in FAILED and job.get("id"):
            trace = _glab(info["repo"], f"projects/:id/jobs/{int(job['id'])}/trace", raw=True)
            parts += [f"{job['name']}\t{job['failed_step']}\t{line}" for line in trace.splitlines()]
    return "\n".join(parts)


def history(info: dict, run: dict) -> dict:
    """Did the same commit pass elsewhere (flaky), and which run was the last green one before it."""
    same, green = None, None
    try:
        recent = runs(info, run.get("branch") or info.get("branch", ""), run.get("workflow", ""))
    except Off:
        recent = []
    for other in recent:
        if other["id"] == run["id"] or other.get("workflow") != run.get("workflow"):
            continue
        if other["sha"] == run["sha"] and other["conclusion"] == "success" \
                and other.get("event") == run.get("event"):
            same = other["id"]
        if green is None and other["conclusion"] == "success" and other["sha"] != run["sha"] \
                and other.get("created", "") < run.get("created", ""):
            green = {"id": other["id"], "sha": other["sha"], "branch": other.get("branch", "")}
    if green is None and info.get("default") and info.get("default") != run.get("branch"):
        try:
            for other in runs(info, info["default"], run.get("workflow", "")):
                if other["conclusion"] == "success" and other.get("created", "") < run.get("created", ""):
                    green = {"id": other["id"], "sha": other["sha"], "branch": other.get("branch", "")}
                    break
        except Off:
            pass
    return {"same_commit_passed": same, "last_green": green}


def _attempt_url(run: dict, attempt: int) -> str:
    return f"{run.get('url') or ''}/attempts/{int(attempt)}" if run.get("url") else ""


def _outcomes(info: dict, source: dict, wanted: set[tuple[str, str]], budget: list[int]) -> dict:
    """{(job, test): 'passed' | 'failed'} in one earlier run or attempt; a test it cannot tell is left out.

    A green run passed every test. Otherwise a test passed when its job passed, or when the job's failed
    log names other failing tests but not this one (so the tests did run).
    """
    if source.get("conclusion") == "success":
        return {key: "passed" for key in wanted}
    run = gh_view(info["repo"], source["id"], source.get("only_attempt", 0))
    jobs = {j["name"]: j["conclusion"] for j in run.get("jobs") or []}
    found = {key: "passed" for key in wanted if jobs.get(key[0]) == "success"}
    if not any(jobs.get(job) in FAILED for job, _ in wanted - found.keys()) or budget[0] <= 0:
        return found
    budget[0] -= 1
    log = failed_log(info, {**run, "provider": "github", "id": source["id"]}, source.get("only_attempt", 0))
    for job, read in parse.read_log(log).items():
        failed = {f["test"] for f in read["failures"] if f["test"]}
        for key in wanted - found.keys():
            if key[0] == job and failed:
                found[key] = "failed" if key[1] in failed else "passed"
    return found


def flaky_tests(info: dict, run: dict, failures: list[dict]) -> list[dict]:
    """Failing tests that passed in another run of the same commit, workflow and event, with the run links.

    Read on demand from GitHub (no local history): the earlier attempts of this run and the other runs
    of the same workflow on the branch, at most PAST_RUNS of them and PAST_LOGS failed logs.
    """
    wanted = {(f.get("job") or "", f["test"]) for f in failures if f.get("kind") == "tests" and f.get("test")}
    if run.get("provider") != "github" or not wanted:
        return []
    try:
        recent = runs(info, run.get("branch") or info.get("branch", ""), run.get("workflow", ""))
    except Off:
        recent = []
    sources = [{"id": run["id"], "only_attempt": n, "conclusion": "", "url": _attempt_url(run, n)}
               for n in range(int(run.get("attempt") or 1) - 1, 0, -1)]
    sources += [o for o in recent if o["id"] != run["id"] and o["sha"] == run["sha"]
                and o.get("workflow") == run.get("workflow") and o.get("event") == run.get("event")
                and o.get("status", "completed") == "completed"]
    seen: dict[tuple[str, str], dict[str, list[str]]] = {key: {"passed": [], "failed": []} for key in wanted}
    budget = [PAST_LOGS]
    for source in sources[:PAST_RUNS]:
        try:
            found = _outcomes(info, source, wanted, budget)
        except (Off, KeyError, TypeError, ValueError):
            continue
        for key, outcome in found.items():
            seen[key][outcome].append(source.get("url") or "")
    return [{"job": job, "test": test, **seen[(job, test)]}
            for job, test in sorted(wanted) if seen[(job, test)]["passed"]]
