"""What kind of failure it is: code, matrix (one Python, one OS), flaky, infra or dependency.

Each kind comes with its evidence, and a confidence: high when the evidence settles it (the same
commit passed in another run), medium when a strong sign points to it, low otherwise.
"""
from __future__ import annotations

import re

INFRA = ("timeout", "network", "rate_limit", "runner", "oom")
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


def classify(facts: dict) -> dict:
    """{kind, detail, confidence, evidence} from what triage found."""
    failures = facts.get("failures") or []
    signals = {s["kind"]: s["line"] for s in facts.get("signals") or []}
    evidence: list[str] = []
    passed_same = facts.get("same_commit_passed")
    if passed_same:
        evidence.append(f"The same commit passed in run {passed_same}.")
        return {"kind": "flaky", "detail": {}, "confidence": "high", "evidence": evidence}
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
    if not failures and "auth" in signals:
        evidence.append(f"credentials: {signals['auth']}")
        if facts.get("event") == "pull_request" and facts.get("from_fork"):
            evidence.append("The pull request comes from a fork, which gets no repository secrets.")
        return {"kind": "infra", "detail": {"signal": "auth"}, "confidence": "medium", "evidence": evidence}
    if "dependency" in signals or (facts.get("lock_changed") and any(
            "No module named" in f["message"] or "Cannot find module" in f["message"] for f in failures)):
        if "dependency" in signals:
            evidence.append(f"dependencies: {signals['dependency']}")
        if facts.get("lock_changed"):
            evidence.append("Dependency files changed since the last green run.")
        return {"kind": "dependency", "detail": {}, "confidence": "medium", "evidence": evidence}
    only = matrix_only(facts.get("jobs") or [])
    what = failures[0]["kind"] if failures else ""
    if only:
        evidence.append(f"Only the jobs with {only} failed; the same job passed with other values.")
        return {"kind": "matrix", "detail": {"value": only, "count": len(failures), "what": what},
                "confidence": "medium", "evidence": evidence}
    if failures:
        evidence += [f"{f['test'] or f['file']}: {f['message']}" for f in failures[:3]]
        if one_matrix_job(facts.get("jobs") or []):
            # One job of a matrix: a race in a test or a real platform difference; one run cannot say.
            evidence.append("Only one job of the matrix failed and nothing it alone has explains it; "
                            "a rerun tells a flaky test from a platform difference.")
            return {"kind": "code", "detail": {"count": len(failures), "what": what, "jobs": 1},
                    "confidence": "low", "evidence": evidence}
        return {"kind": "code", "detail": {"count": len(failures), "what": what}, "confidence": "medium",
                "evidence": evidence}
    if infra:
        evidence += [f"{k}: {signals[k]}" for k in infra]
        return {"kind": "infra", "detail": {"signal": infra[0]}, "confidence": "low", "evidence": evidence}
    return {"kind": "unknown", "detail": {}, "confidence": "low",
            "evidence": [e for e in facts.get("errors") or []][:3]}
