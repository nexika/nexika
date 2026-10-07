"""One reading of the session's balance: the nexika.mizan/1 snapshot.

The input is what only the session knows (context, cost, running agents, tasks), either from the
mod or from Claude Code's status line JSON; mizan adds git, gh/glab (cached), the device, haris and
itqan. Context levels: fresh under 40 %, mid 40-75 %, full above 75 % (context_mid and context_full
in config.json move them).
"""
from __future__ import annotations

import datetime
import math
import os
import time

from . import __version__, config, device, family, forge, gitinfo, i18n, render, status, tasks

SCHEMA = "nexika.mizan/1"
MOD_FRESH = 120  # seconds: the mod publishes every 15 s while it runs


def context_level(percent: float) -> str:
    mid, full = config.thresholds()
    return "full" if percent > full else "mid" if percent >= mid else "fresh"


def _number(value) -> float | None:
    try:
        return float(value) if value is not None and value != "" else None
    except (TypeError, ValueError):
        return None


def normalize(raw: dict) -> dict:
    """The mod's payload as is; Claude Code's status line JSON mapped onto the same fields."""
    raw = raw if isinstance(raw, dict) else {}
    if "session_id" in raw or "context_window" in raw or "workspace" in raw:
        window = raw.get("context_window") or {}
        cost = raw.get("cost") or {}
        return {"session": raw.get("session_id", ""), "transcript": raw.get("transcript_path", ""),
                "cwd": (raw.get("workspace") or {}).get("current_dir") or raw.get("cwd", ""),
                "context": {"percent": window.get("used_percentage"),
                            "tokens": window.get("total_input_tokens"),
                            "window": window.get("context_window_size")},
                "cost": {"usd": cost.get("total_cost_usd")}, "agents": [], "tasks": None,
                "source": "statusline"}
    return {"session": raw.get("session", ""), "transcript": raw.get("transcript", ""),
            "cwd": raw.get("cwd", ""), "context": raw.get("context") or {}, "cost": raw.get("cost") or {},
            "agents": raw.get("agents") or [], "tasks": raw.get("tasks"),
            "source": raw.get("source") or "mod"}


def today() -> str:
    return datetime.date.today().isoformat()


def _network(info: dict) -> tuple[dict, dict]:
    if not info:
        return {}, {}
    if not config.network():
        off = {"state": "off", "why": "off_offline", "tool": ""}
        return off, off
    found = forge.cached(info)
    forge.ensure_fresh(info)
    return found["prs"] or {"state": "loading"}, found["ci"] or {"state": "loading"}


def _dollars(value) -> float:
    """A cost as a sane number: never negative, never NaN or infinite."""
    found = _number(value)
    return found if found is not None and math.isfinite(found) and found > 0 else 0.0


def day_start(before: dict) -> float:
    """What a session had cost when today began: a session open past midnight counts only today's part."""
    if not before:
        return 0.0
    if before.get("date") == today():
        return _dollars(before.get("cost_day_start"))
    return _dollars(before.get("cost_usd"))


def _cost(session: str, usd: float | None, start: float = 0.0) -> dict:
    if usd is None:
        return {"usd": None}
    usd = _dollars(usd)
    others = sum(max(0.0, _dollars(s.get("cost_usd")) - _dollars(s.get("cost_day_start")))
                 for s in status.sessions("mizan")
                 if s.get("date") == today() and s.get("session") != session)
    budget = config.budget()
    found = {"usd": usd, "today_usd": round(others + max(0.0, usd - start), 4), "budget_usd": budget,
             "level": "ok", "day_start": start}
    if budget:
        share = found["today_usd"] / budget
        found["level"] = "bad" if share >= 1 else "warn" if share >= 0.8 else "ok"
    return found


def _tabib(info: dict, ci: dict) -> tuple[dict, bool]:
    """tabib's word on the failed run: the triage mizan's refresh asked for, updated by a diagnosis."""
    if not info or ci.get("state") != "failed" or ci.get("stale"):
        return {}, False
    found = dict(ci.get("tabib") or {})
    runs = status.read("tabib").get("runs") or {}
    mine = (runs.get(info.get("repo", "")) or {}) if isinstance(runs, dict) else {}
    entry = mine.get(info.get("branch", "")) if isinstance(mine, dict) else None
    if isinstance(entry, dict) and entry.get("run") and entry.get("run") == ci.get("run"):
        keys = ("run", "kind", "detail", "confidence", "cause_found", "cause")
        found.update({k: entry.get(k) for k in keys})
    return found, family.find_plugin("tabib") is not None


def _lawha(info: dict) -> tuple[dict, bool]:
    """lawha's latest check of this project's pages; Fix is offered when it failed at this commit."""
    found = family.lawha_check(info.get("repo", "")) if info else {}
    if not found:
        return {}, False
    counts = found.get("counts") or {}
    commit = str(found.get("commit") or "")
    head = str(info.get("head") or "")
    current = bool(commit) and head.startswith(commit)
    problems = [{"text": render.clean(p.get("message"), 160),
                 "where": ", ".join(render.clean(w, 30) for w in (p.get("where") or [])[:4])}
                for p in (found.get("problems") or [])[:5] if isinstance(p, dict)]
    view = {"verdict": "pass" if found.get("verdict") == "pass" else "fail", "current": current,
            "fail": int(counts.get("fail") or 0), "warn": int(counts.get("warn") or 0),
            "widths": len(found.get("widths") or []),
            "dirs": [str(d) for d in (found.get("dirs") or [])][:2],
            "themes": [str(t) for t in (found.get("themes") or [])][:2],
            "url": render.clean(found.get("url"), 200),
            "report": render.clean(found.get("report"), 300),
            "created": render.clean(found.get("created"), 20),
            "problems": problems}
    return view, view["verdict"] == "fail" and current and family.find_plugin("lawha") is not None


def build(raw: dict, publish: bool = False) -> dict:
    p = normalize(raw)
    cwd = p["cwd"] or os.getcwd()
    session = p["session"] if status.SAFE_ID.match(p["session"] or "") else ""
    before = status.read("mizan", session) if session else {}
    start = day_start(before)
    info = gitinfo.read(cwd)
    prs, ci = _network(info)
    pr = prs.get("branch_pr") if prs.get("state") == "ok" else None
    if pr and pr.get("author"):
        info = {**info, "creator": pr["author"], "creator_source": "pr"}
    percent = _number((p["context"] or {}).get("percent"))
    context = {"percent": None}
    if percent is not None:
        context = {"percent": round(percent), "tokens": _number(p["context"].get("tokens")),
                   "window": _number(p["context"].get("window")), "level": context_level(percent)}
        context["window"] = int(context["window"]) if context["window"] else None
    running = p["agents"]
    if isinstance(p["tasks"], dict):
        items = p["tasks"].get("items")
    else:
        items = tasks.from_transcript(p["transcript"])
        if p["source"] == "statusline":
            # The status line is told nothing about agents: the transcript says which ran and finished.
            called = tasks.agents_from_transcript(p["transcript"])
            running = [a for a in called if a["status"] == "running"]
            items = items or tasks.from_agents(called)
    agents = [{"type": render.clean(a.get("type"), 40),
               "description": render.clean(a.get("description"), 120)}
              for a in running if isinstance(a, dict)][:10]
    lang = i18n.lang()
    snap = {
        "schema": SCHEMA, "version": __version__,
        "created": datetime.datetime.now().isoformat(timespec="seconds"),
        "lang": lang, "session": session, "cwd": cwd, "source": p["source"],
        "git": {k: info.get(k, "") for k in ("repo", "branch", "default", "head", "host", "creator",
                                             "creator_source")} if info else {},
        "prs": prs, "ci": ci, "device": device.read(cwd), "context": context,
        "cost": _cost(session, _number((p["cost"] or {}).get("usd")), start), "agents": agents,
        "tasks": tasks.summarize(items or []), "haris": family.haris_status(session),
    }
    snap["tabib"], snap["why"] = _tabib(info, ci)
    proof = family.proof(info.get("repo", "")) if info else {}
    checks = proof.get("checks") or []
    passed = bool(checks) and all(c.get("passed") for c in checks)
    snap["proof"] = {"available": bool(proof), "passed": passed, "created": proof.get("created", "")}
    snap["lawha"], snap["fix"] = _lawha(info)
    snap["band"] = render.band(snap, lang)
    snap["detail"] = render.detail(snap, lang)
    snap["alerts"] = [{"key": key, "text": f"{i18n.t(key, lang, p=part['percent'])}: "
                                          f"{i18n.t('d_device_warn', lang, p=device.BAD)}"}
                      for key, part in snap["device"].items() if part.get("level") == "bad"]
    snap["labels"] = render.labels(lang)
    if publish and session:
        found = record(snap, p["transcript"])
        # The status line may publish too; it never hides a mod that published within MOD_FRESH.
        found["mod_at"] = time.time() if found["mod"] else float(before.get("mod_at") or 0)
        found["mod"] = time.time() - found["mod_at"] < MOD_FRESH
        found["transcript"] = found["transcript"] or before.get("transcript", "")
        status.publish("mizan", found, session)
    return snap


def record(snap: dict, transcript: str = "") -> dict:
    """What mizan publishes per session (status/mizan/<session>.json): siyaq reads `level`."""
    context = snap["context"]
    return {"session": snap["session"], "cwd": snap["cwd"], "repo": snap["git"].get("repo", ""),
            "branch": snap["git"].get("branch", ""), "level": context.get("level", ""), "context": context,
            "cost_usd": snap["cost"].get("usd"), "cost_day_start": snap["cost"].get("day_start", 0.0),
            "date": today(), "transcript": transcript,
            "device": {k: v.get("percent") for k, v in snap["device"].items()},
            "agents": snap["agents"], "tasks": {"items": snap["tasks"]["items"]},
            "mod": snap["source"] == "mod"}


def latest_payload(cwd: str) -> dict:
    """The newest published session for this folder, as a payload (for report and export)."""
    cwd = os.path.realpath(cwd)
    top = gitinfo.git(cwd, "rev-parse", "--show-toplevel")
    found = [s for s in status.sessions("mizan")
             if os.path.realpath(s.get("cwd") or "") == cwd or (top and s.get("repo") == top)]
    if not found:
        return {"cwd": cwd, "source": "cli"}
    s = max(found, key=lambda s: s.get("updated", 0))
    return {"session": s.get("session", ""), "cwd": cwd, "context": s.get("context") or {},
            "cost": {"usd": s.get("cost_usd")}, "agents": s.get("agents") or [], "tasks": s.get("tasks"),
            "transcript": s.get("transcript", ""), "source": "cli"}
