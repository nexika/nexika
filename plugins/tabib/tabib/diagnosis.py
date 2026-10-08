"""A diagnosis: triage (no AI, no code run), the full diagnosis (+ the comparison and the local run),
and the cause Claude reports. Saved as nexika.tabib/1 JSON and announced in status/tabib.json.

    ~/.claude/nexika/tabib/<repo>/<run id>.json   one per diagnosed run (TABIB_HOME moves it)
    ~/.claude/nexika/status/tabib.json            the latest diagnosis per repository and branch
"""
from __future__ import annotations

import datetime
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

from . import __version__, classify, compare, forge, inject, parse, reproduce, secrets, status

SCHEMA = "nexika.tabib/1"
KEEP = 50
CONFIDENCE = ("high", "medium", "low")


def home() -> Path:
    return Path(os.path.expanduser(os.environ.get("TABIB_HOME") or "~/.claude/nexika/tabib"))


def folder(repo: str) -> Path:
    return home() / hashlib.sha1(repo.encode()).hexdigest()[:16]


def path_for(repo: str, run_id) -> Path:
    return folder(repo) / f"{int(run_id)}.json"


def load(path: Path) -> dict:
    data = status.read_json(path)
    return data if data.get("schema") == SCHEMA else {}


def now() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


def rerun_command(run: dict) -> str:
    if run["provider"] == "gitlab":
        failed = next((j for j in run["jobs"] if j["conclusion"] in forge.FAILED and j.get("id")), None)
        return f"glab ci retry {int(failed['id'])}" if failed else "glab ci retry <job id>"
    return f"gh run rerun {int(run['id'])} --failed"


def _gather(log: str) -> tuple[list[dict], list[dict], list[str], dict, list[str], list[str]]:
    failures, signals, errors, excerpts, frames, missing = [], [], [], {}, [], []
    seen = set()
    for job, found in parse.read_log(log).items():
        missing += [m for m in found["missing"] if m not in missing]
        for f in found["failures"]:
            failures.append({**f, "job": job, "message": secrets.redact(f["message"])})
        for s in found["signals"]:
            if s["kind"] not in seen:
                seen.add(s["kind"])
                signals.append({**s, "job": job, "line": secrets.redact(s["line"])})
        errors += [secrets.redact(e) for e in found["errors"] if e not in errors][:12]
        frames += [f"{path}:{line}" for path, line in found["frames"] if f"{path}:{line}" not in frames]
        if len(excerpts) < 4:
            needles = [f["test"].split("::")[-1] or f["file"] for f in found["failures"][:4]]
            needles += [s["line"][:60] for s in found["signals"][:2]]
            excerpts[job or "log"] = secrets.redact(parse.excerpt(found["lines"], needles))
    return failures[:50], signals, errors[:12], excerpts, frames[:30], missing[:10]


def places(failures: list[dict], frames: list[str]) -> list[tuple[str, int, int]]:
    """Where to run git blame: each failure's own line (weight 2), then the stack frames (weight 1)."""
    found = [(f["file"], int(f["line"]), 2) for f in failures if f.get("file") and f.get("line")]
    for frame in frames:
        path, _, line = frame.rpartition(":")
        if path and line.isdigit():
            found.append((path, int(line), 1))
    return found


def publish(record: dict) -> None:
    current = status.read("tabib")
    runs = current.get("runs") if isinstance(current.get("runs"), dict) else {}
    runs = {repo: {b: e for b, e in branches.items()
                   if isinstance(e, dict) and Path(e.get("path", "")).is_file()}
            for repo, branches in runs.items() if isinstance(branches, dict)}
    cause = record.get("cause") or {}
    reproduction = record.get("reproduction") or {}
    runs.setdefault(record["repo"], {})[record["branch"]] = {
        "run": record["run"]["id"], "sha": record["run"]["sha"], "kind": record["kind"],
        "detail": record["detail"], "confidence": record["confidence"], "cause_found": bool(cause),
        "cause": cause.get("text", "")[:200], "reproduced": reproduction.get("status", ""),
        "path": str(path_for(record["repo"], record["run"]["id"])), "updated": record["updated"]}
    status.publish("tabib", {"runs": runs})


def save(record: dict) -> dict:
    record["updated"] = now()
    target = path_for(record["repo"], record["run"]["id"])
    status.write_json(target, record)
    for old in sorted(target.parent.glob("*.json"), key=lambda p: p.stat().st_mtime)[:-KEEP]:
        old.unlink(missing_ok=True)
    publish(record)
    return record


def triage(info: dict, run_id: int | None = None, refresh: bool = False) -> dict:
    """What failed and what kind of failure it is, from the CI log and history: no AI, no code run."""
    run = forge.find_run(info, run_id)
    existing = load(path_for(info["repo"], run["id"]))
    same = bool(existing) and existing["run"].get("attempt") == run.get("attempt") \
        and (existing["run"].get("updated") or "") == (run.get("updated") or "")   # saved as None when absent
    if same and not refresh:
        return existing
    if not same:
        existing = {}
    log = secrets.redact(forge.failed_log(info, run))  # whole blocks (keys) before anything is cut
    failures, signals, errors, excerpts, frames, missing = _gather(log)
    fork = forge.from_fork(info, run)
    hist = forge.history(info, run)
    flaky = forge.flaky_tests(info, run, failures) if not hist.get("same_commit_passed") else []
    green = hist.get("last_green") or {}
    files = [f["file"] for f in failures]
    suspects = {"available": False}
    if green:
        suspects = compare.compare(info["repo"], green["sha"], run["sha"], files, places(failures, frames))
    own = compare.own_modules(info["repo"], run["sha"], missing) if missing else set()
    facts = {"failures": failures, "signals": signals, "errors": errors, "jobs": run["jobs"],
             "same_commit_passed": hist.get("same_commit_passed"), "event": run.get("event"),
             "from_fork": fork, "flaky_tests": flaky,
             "lock_changed": suspects.get("lock_changed"),
             "missing_modules": [m for m in missing if m not in own]}
    verdict = classify.classify(facts)
    record = {"schema": SCHEMA, "version": __version__, "created": now(), "repo": info["repo"],
              "branch": run.get("branch") or info.get("branch", ""),
              "run": {**{k: run.get(k) for k in ("provider", "id", "url", "workflow", "sha", "attempt",
                                                  "event", "number", "created", "updated")},
                      "from_fork": fork},
              "jobs": run["jobs"], "failures": failures, "flaky_tests": flaky, "signals": signals,
              "errors": errors, "frames": frames,
              "kind": verdict["kind"], "detail": verdict["detail"], "confidence": verdict["confidence"],
              "evidence": [secrets.redact(e) for e in verdict["evidence"]], "history": hist,
              "suspects": {**suspects, "green_run": green.get("id")},
              "reproduction": existing.get("reproduction"),
              "injection": [],
              "excerpts": excerpts, "cause": existing.get("cause"),
              "rerun": rerun_command(run) if verdict["kind"] in ("flaky", "infra") else ""}
    record["injection"] = scan(record)
    return save(record)


def scan(record: dict) -> list[str]:
    """Text in what tabib stores (and the agent reads) that tries to give instructions."""
    stored = [record.get("excerpts"), record.get("errors"), record.get("evidence"),
              [[f.get("test"), f.get("message")] for f in record.get("failures") or []],
              [j.get("name") for j in record.get("jobs") or []], record["run"].get("workflow"),
              [c.get("subject") for c in (record.get("suspects") or {}).get("commits") or []]]
    return inject.scan(stored)


def diagnose(info: dict, run_id: int | None = None, local_run: bool = True) -> dict:
    """Triage, then fetch the two commits for the comparison and run the failing tests in a worktree."""
    record = triage(info, run_id, refresh=True)
    run, green = record["run"], record["history"].get("last_green") or {}
    if green and compare.fetch(info["repo"], green["sha"], green.get("branch", "")) and \
            compare.fetch(info["repo"], run["sha"], record["branch"]):
        record["suspects"] = {**compare.compare(info["repo"], green["sha"], run["sha"],
                                                [f["file"] for f in record["failures"]],
                                                places(record["failures"], record.get("frames") or [])),
                              "green_run": green.get("id")}
    if local_run and record["kind"] not in ("flaky", "infra"):
        record["reproduction"] = reproduce.run(info["repo"], run["sha"], record["branch"], record["failures"],
                                               record["jobs"], fork=run.get("from_fork"))
    elif local_run:
        record["reproduction"] = {"status": "skipped", "why": "not a code failure"}
    record["injection"] = scan(record)
    return save(record)


def latest(info: dict, run_id: int | None = None) -> dict:
    if run_id:
        return load(path_for(info["repo"], run_id))
    runs = status.read("tabib").get("runs") or {}
    entry = (runs.get(info["repo"]) or {}).get(info.get("branch", "")) or {}
    return load(Path(entry["path"])) if entry.get("path") else {}


def find_plugin(name: str) -> Path | None:
    """Another Nexika plugin beside tabib, in the plugin cache, or where installed_plugins.json says."""
    root = Path(__file__).resolve().parent.parent
    candidates = [root.parent / name]
    try:
        candidates += sorted((p for p in (root.parent.parent / name).iterdir() if p.is_dir()), reverse=True)
    except OSError:
        pass
    config = os.environ.get("CLAUDE_CONFIG_DIR") or "~/.claude"
    try:
        installed = json.loads((Path(os.path.expanduser(config)) / "plugins" / "installed_plugins.json")
                               .read_text(encoding="utf-8")).get("plugins") or {}
    except (OSError, ValueError, AttributeError):
        installed = {}
    for key, entries in installed.items():
        if key.split("@")[0] == name and isinstance(entries, list):
            candidates += [Path(e["installPath"]) for e in entries
                           if isinstance(e, dict) and e.get("installPath")]
    return next((c for c in candidates if (c / "bin" / name).is_file()), None)


def record_cause(info: dict, run_id: int | None, text: str, confidence: str, evidence: list[str]) -> dict:
    """The cause Claude found (kept as reported by Claude), and a hafiz problem for the branch."""
    record = latest(info, run_id)
    if not record:
        return {}
    clean = parse.clean_text(" ".join(secrets.redact(text).split()))[:600]
    proofs = [parse.clean_text(" ".join(secrets.redact(e).split()))[:300] for e in evidence[:10]]
    flagged = inject.scan([clean, proofs])
    record["cause"] = {"text": clean, "confidence": confidence if confidence in CONFIDENCE else "low",
                       "evidence": proofs, "by": "reported by Claude", "at": now(), "flagged": flagged}
    save(record)
    hafiz = find_plugin("hafiz")
    if hafiz and clean and not flagged and record["run"].get("from_fork") is False:
        note = f"CI run {int(record['run']['id'])} failed: {clean}"
        try:
            subprocess.run([sys.executable, str(hafiz / "bin" / "hafiz"), "remember", "problem", note],
                           cwd=info["repo"], capture_output=True, timeout=30, check=False)
        except (OSError, subprocess.SubprocessError):
            pass
    return record


def facts(record: dict) -> dict:
    """What the diagnostician agent reads: the record without bulky parts."""
    return {k: v for k, v in record.items() if k not in ("history",)}
