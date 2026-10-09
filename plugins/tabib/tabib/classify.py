"""What kind of failure it is: code, matrix (one Python, one OS), flaky, infra, setup or dependency.

Each kind comes with its evidence, and a confidence: high when the evidence settles it (the same
commit passed in another run, or every failing test passed in another run of the same commit),
medium when a strong sign points to it, low otherwise.
"""
from __future__ import annotations

import re

# Most specific first: a runner shutdown or a kill explains a timeout or a cancel printed after it.
INFRA = ("runner", "oom", "timeout", "rate_limit", "network", "cancelled")
PARAMS = re.compile(r"^(.*?)\s*\((.*)\)\s*$")


def matrix_parts(name: str) -> tuple[str, tuple[str, ...]]:
    """'test (py3.10, ubuntu-latest)' -> ('test', ('py3.10', 'ubuntu-latest'))."""
    m = PARAMS.match(name or "")
    if not m:
        return name or "", ()
    return m.group(1), tuple(p.strip() for p in m.group(2).split(",") if p.strip())


def _matrix_groups(jobs: list[dict]) -> dict[str, dict[str, list[tuple[str, ...]]]]:
    """Matrix jobs by their base name, split into failed and passed parameter sets."""
    groups: dict[str, dict[str, list[tuple[str, ...]]]] = {}
    for job in jobs:
        base, params = matrix_parts(job.get("name", ""))
        if not params:
            continue
        side = "failed" if job.get("conclusion") in ("failure", "failed", "timed_out") else (
            "passed" if job.get("conclusion") in ("success", "passed") else "")
        if side:
            groups.setdefault(base, {"failed": [], "passed": []})[side].append(params)
    return groups


def matrix_only(jobs: list[dict]) -> str:
    """The matrix value only the failed jobs have, when siblings of the same job passed: 'py3.10'.

    With one failed job every value it has looks like the cause, so a single job counts only when
    exactly one of its values is missing from the jobs that passed; otherwise two or more failed
    jobs must share the value.
    """
    for sides in _matrix_groups(jobs).values():
        if not sides["failed"] or not sides["passed"]:
            continue
        failed_values = set.intersection(*(set(p) for p in sides["failed"]))
        passed_values = set().union(*(set(p) for p in sides["passed"]))
        only = sorted(failed_values - passed_values)
        if len(sides["failed"]) == 1 and len(only) != 1:
            continue
        if only:
            return ", ".join(only)
    return ""


def one_matrix_job(jobs: list[dict]) -> bool:
    """Exactly one job of a matrix failed while its siblings passed: a weak sign either way."""
    groups = [g for g in _matrix_groups(jobs).values() if g["failed"]]
    return len(groups) == 1 and len(groups[0]["failed"]) == 1 and bool(groups[0]["passed"])


OS_FAMILY = re.compile(r"(?i)windows|ubuntu|linux|macos")


def _os(name: str) -> str:
    m = OS_FAMILY.search(" ".join(matrix_parts(name)[1]))
    return {"ubuntu": "linux"}.get(m.group(0).lower(), m.group(0).lower()) if m else ""


def fails_on_base(jobs: list[dict], base: list[dict]) -> list[str]:
    """Base-branch runs where the same job, on the same OS family, failed too: '29181739141 (test (3.13,
    windows-latest))' (#175)."""
    failed = [j["name"] for j in jobs if j.get("conclusion") in ("failure", "failed")]
    if len(failed) != 1 or not _os(failed[0]):
        return []
    name, family = matrix_parts(failed[0])[0], _os(failed[0])
    return [f"{b['id']} ({job})" for b in base for job in b.get("jobs") or []
            if matrix_parts(job)[0] == name and _os(job) == family][:3]


def raised_upstream(failures: list[dict], upstream: list[dict]) -> dict:
    """The dependency every failure comes from, when each one is a warning raised inside a dependency's
    code in its own job (pytest turns warnings into errors): {} otherwise."""
    if not failures or not upstream:
        return {}
    first = {}
    for f in failures:
        here = [u for u in upstream if u.get("job") == f.get("job")
                and (f.get("message") or "").startswith(u["warning"] + ":")]
        if not here:
            return {}
        first = first or here[0]
    return first


def classify(facts: dict) -> dict:
    """{kind, detail, confidence, evidence} from what triage found."""
    failures = facts.get("failures") or []
    # When a job failed, GitHub cancels its matrix siblings (fail-fast): their "canceled" says
    # nothing about why the run failed.
    a_job_failed = any(j.get("conclusion") == "failure" for j in facts.get("jobs") or [])
    signals = {s["kind"]: s["line"] for s in facts.get("signals") or []
               if not (s["kind"] == "cancelled" and a_job_failed)}
    evidence: list[str] = []
    if facts.get("no_jobs"):
        evidence.append("The run has no jobs, so no log: the workflow file did not parse, or no job could "
                        f"start. GitHub's message is on the run page: {facts.get('url') or '-'}")
        return {"kind": "setup", "detail": {"jobs": 0}, "confidence": "medium", "evidence": evidence}
    if facts.get("log_gone"):
        evidence.append("The run's log has expired: GitHub keeps logs for about 90 days.")
        return {"kind": "unknown", "detail": {"log": "expired"}, "confidence": "low", "evidence": evidence}
    passed_same = facts.get("same_commit_passed")
    if passed_same and failures and all(f.get("framework") == "step" for f in failures):
        # A check the workflow wrote (a changelog line) does not flake: a label or setting changed (#172).
        evidence.append(f"The same commit passed in run {passed_same}, likely after a label or a setting "
                        "changed: the check itself does not flake.")
    elif passed_same:
        evidence.append(f"The same commit passed in run {passed_same}.")
        return {"kind": "flaky", "detail": {}, "confidence": "high", "evidence": evidence}
    flaky = {(f.get("job") or "", f["test"]): f for f in facts.get("flaky_tests") or []}
    flaky_notes = [f"{f['test']} failed and passed on the same commit (passed in "
                   f"{', '.join(f['passed'][:3])})" for f in flaky.values()]
    if failures and all((f.get("job") or "", f.get("test")) in flaky for f in failures):
        return {"kind": "flaky", "detail": {}, "confidence": "high", "evidence": flaky_notes[:5]}
    evidence += [f"Likely flaky, not the cause: {note}" for note in flaky_notes[:3]]
    if not failures and "setup" in signals:
        evidence.append(f"CI setup: {signals['setup']}")
        evidence.append("The workflow cannot work as written: a re-run fails the same way.")
        return {"kind": "setup", "detail": {}, "confidence": "medium", "evidence": evidence}
    infra = [k for k in INFRA if k in signals]
    unhappy = [j for j in facts.get("jobs") or []
               if j.get("conclusion") not in ("success", "skipped", "neutral")]
    cancelled = bool(unhappy) and all(j.get("conclusion") == "cancelled" for j in unhappy)
    if not failures and not infra and cancelled:
        names = ", ".join(j["name"] for j in unhappy[:4])
        evidence.append(f"Every job that did not pass was cancelled: {names}")
        evidence.append("Nothing in the log says why; a newer run, a person or a limit usually cancels one.")
        return {"kind": "infra", "detail": {"signal": "cancelled"}, "confidence": "medium",
                "evidence": evidence}
    if not failures and infra:
        evidence += [f"{k}: {signals[k]}" for k in infra]
        return {"kind": "infra", "detail": {"signal": infra[0]}, "confidence": "medium", "evidence": evidence}
    own_run = facts.get("from_fork") is False or (
        facts.get("from_fork") is None and not str(facts.get("event") or "").startswith("pull_request"))
    no_permission = "auth" in signals and "not accessible by integration" in signals["auth"].lower()
    if not failures and ("rules" in signals or (no_permission and own_run)):
        # The repository's own run: its token lacks a permission, or a branch rule stops it (#262).
        evidence.append(f"The workflow's token cannot do this (permissions: or a branch rule): "
                        f"{signals.get('rules') or signals['auth']}")
        evidence.append("A re-run fails the same way: give the job the permission it needs, or change "
                        "the rule.")
        return {"kind": "setup", "detail": {}, "confidence": "medium", "evidence": evidence}
    if not failures and "auth" in signals:
        evidence.append(f"credentials: {signals['auth']}")
        if facts.get("event") == "pull_request" and facts.get("from_fork"):
            evidence.append("The pull request comes from a fork, which gets no repository secrets.")
        return {"kind": "infra", "detail": {"signal": "auth"}, "confidence": "medium", "evidence": evidence}
    upstream = raised_upstream(failures, facts.get("upstream") or [])
    if upstream:
        evidence.append(f"{upstream['warning']} raised inside {upstream['package']} ({upstream['place']}), "
                        f"not in the project's code: {upstream['message']}")
        evidence.append("Warnings are errors in this job: the dependency changed under the project "
                        "(a new release, or the version this job installs).")
        failed = sorted({f.get("job") or "" for f in failures} - {""})
        passed = [j for j in facts.get("jobs") or [] if j.get("conclusion") in ("success", "passed")]
        if failed and passed:
            evidence.append(f"Only the job{'s' if len(failed) > 1 else ''} "
                            f"{', '.join(repr(name) for name in failed[:3])} failed; the other jobs passed.")
        return {"kind": "dependency", "detail": {"package": upstream["package"]}, "confidence": "medium",
                "evidence": evidence}
    missing = facts.get("missing_modules") or []   # modules the project itself does not have
    if "dependency" in signals or missing or (facts.get("lock_changed") and any(
            "No module named" in f["message"] or "Cannot find module" in f["message"] for f in failures)):
        if "dependency" in signals:
            evidence.append(f"dependencies: {signals['dependency']}")
        if missing:
            evidence.append(f"No module named {missing[0]!r}, and the project has no module of that name: "
                            "is it in the requirements?")
        if facts.get("lock_changed"):
            evidence.append("Dependency files changed since the last green run.")
        return {"kind": "dependency", "detail": {"module": missing[0]} if missing else {},
                "confidence": "medium", "evidence": evidence}
    only = matrix_only(facts.get("jobs") or [])
    what = failures[0]["kind"] if failures else ""
    if only and failures:   # a matrix value names where a known failure happens, not a cause (#255)
        evidence.append(f"Only the jobs with {only} failed; the same job passed with other values.")
        return {"kind": "matrix", "detail": {"value": only, "count": len(failures), "what": what},
                "confidence": "medium", "evidence": evidence}
    if failures:
        evidence += [f"{f['test'] or f['file']}: {f['message']}" for f in failures[:3]]
        if all(f.get("timeout") for f in failures):
            evidence.append("Each failing test hit the test runner's own time limit: a slow or hung test, "
                            "or a race; a re-run tells which.")
        if "segfault" in signals:
            evidence.append(f"The process crashed (a segmentation fault): {signals['segfault']}")
        # A test failing in N jobs is one failure, "in N jobs" (#175).
        count = len({(f.get("framework"), f.get("test")) if f.get("test") else
                     (f.get("framework"), f.get("file"), f.get("line")) for f in failures})
        in_jobs = len({f.get("job") or "" for f in failures})
        on_base = fails_on_base(facts.get("jobs") or [], facts.get("base_failures") or [])
        if on_base:
            evidence.append(f"Only one job failed, and the base branch fails the same job on the same "
                            f"system: run {', '.join(on_base)}. A job that fails at random, not this change.")
            return {"kind": "flaky", "detail": {}, "confidence": "medium", "evidence": evidence}
        if one_matrix_job(facts.get("jobs") or []):
            # One job of a matrix: a race in a test or a real platform difference; one run cannot say.
            evidence.append("Only one job of the matrix failed and nothing it alone has explains it; "
                            "a rerun tells a flaky test from a platform difference.")
            return {"kind": "code", "detail": {"count": count, "what": what, "jobs": 1},
                    "confidence": "low", "evidence": evidence}
        detail = {"count": count, "what": what, **({"jobs": in_jobs} if in_jobs > 1 else {})}
        return {"kind": "code", "detail": detail, "confidence": "medium", "evidence": evidence}
    if infra:
        evidence += [f"{k}: {signals[k]}" for k in infra]
        return {"kind": "infra", "detail": {"signal": infra[0]}, "confidence": "low", "evidence": evidence}
    return {"kind": "unknown", "detail": {}, "confidence": "low",
            "evidence": [e for e in facts.get("errors") or []][:3]}
