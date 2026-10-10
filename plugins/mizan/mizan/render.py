"""What mizan shows: the two band lines, the detail pane, the proof, in English or Arabic.

The band is a list of lines, each a list of segments {text, tone}; tone is ok, warn, bad, info, dim
or plain. The mod draws segments with theme colors; the status line fallback with ANSI colors, so
both show the same words.
"""
from __future__ import annotations

import re

from .i18n import TEXT, t

CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f؜‎‏‪-‮⁦-⁩]")
ANSI = {"ok": "32", "warn": "33", "bad": "31", "info": "36", "dim": "2"}
SEP = " · "
MAX_USERS = 4


def clean(text, limit: int = 60) -> str:
    """Text from outside (git, gh, agent descriptions) without control or direction characters."""
    flat = " ".join(CONTROL.sub(" ", str(text or "")).split())
    return flat if len(flat) <= limit else flat[: limit - 1].rstrip() + "…"


def seg(text: str, tone: str = "plain") -> dict:
    return {"text": text, "tone": tone}


def money(value: float) -> str:
    return f"{value:.2f}"


def level_tone(level: str) -> str:
    return {"bad": "bad", "warn": "warn"}.get(level, "dim")


def _prs(prs: dict, lang: str) -> dict | None:
    if prs.get("state") != "ok":
        return None
    word = "mrs" if prs.get("tool") == "glab" else "prs"
    users = prs.get("per_user") or []
    if not users:
        return seg(t(f"{word}_none", lang), "dim")
    shown = " ".join(f"{clean(name, 20)}({n})" for name, n in users[:MAX_USERS])
    more = f" +{len(users) - MAX_USERS}" if len(users) > MAX_USERS else ""
    return seg(f"{t(word, lang)} {shown}{more}", "plain")


def _reviews(prs: dict, lang: str) -> dict | None:
    """Pull requests waiting for your review, when there are any."""
    n = prs.get("reviews") if prs.get("state") == "ok" else None
    return seg(t("reviews", lang, n=n), "info") if isinstance(n, int) and n > 0 else None


def _gh_trouble(prs: dict, ci: dict, lang: str) -> dict | None:
    """'gh: rate limited' or 'gh: timed out': why PRs or CI are old or missing."""
    for entry in (ci, prs):
        why = entry.get("error") or (entry.get("why") if entry.get("state") == "off" else "")
        if why in ("off_ratelimit", "off_timeout"):
            return seg(t(f"b_{why}", lang, tool=entry.get("tool") or "gh"), "warn")
    return None


def _ci(ci: dict, lang: str) -> dict | None:
    state = ci.get("state")
    if ci.get("error"):
        ci = {**ci, "stale": True}  # the last known result: gh did not answer this time
    if state == "passed":
        return seg(t("ci_passed", lang), "dim" if ci.get("stale") else "ok")
    if state == "failed":
        jobs = ci.get("failed") or []
        if not jobs:
            return seg(t("ci_failed_plain", lang), "bad")
        flows = ci.get("workflows") or []
        # 'changelog/check, test, build and publish +n': the first job, then every other failed workflow
        shown = ", ".join([clean(jobs[0], 40)] + [clean(w, 24) for w in flows[1:]])
        rest = len(jobs) - max(1, len(flows))
        more = f" +{rest}" if rest > 0 else ""
        n = len(ci.get("cancelled") or [])
        more += f" ({t('ci_n_cancelled', lang, n=n)})" if n else ""
        return seg(t("ci_failed", lang, job=shown + more), "dim" if ci.get("stale") else "bad")
    if state == "cancelled":
        jobs = ci.get("cancelled") or []
        if ci.get("all_cancelled") or not jobs:
            return seg(t("ci_superseded", lang), "dim")
        more = f" +{len(jobs) - 1}" if len(jobs) > 1 else ""
        tone = "dim" if ci.get("stale") else "warn"
        return seg(t("ci_cancelled", lang, job=clean(jobs[0], 40) + more), tone)
    if state == "running":
        if ci.get("elapsed") is None:
            return seg(t("ci_running", lang), "warn")
        text = t("ci_running_for", lang, m=max(1, round(ci["elapsed"] / 60)))
        if ci.get("eta") is not None:
            text += SEP + t("ci_eta", lang, m=max(1, round(ci["eta"] / 60)))
        return seg(text, "warn")
    if state == "approval":  # the workflows wait for a maintainer, or waited until GitHub gave up
        expired = bool(ci.get("expired"))
        return seg(t("ci_expired" if expired else "ci_approval", lang), "dim" if expired else "warn")
    if state == "none":
        return seg(t("ci_none", lang), "dim")
    if state == "loading":
        return seg(t("ci_loading", lang), "dim")
    return None


def tabib_label(found: dict, lang: str) -> str:
    """tabib's kind of failure in a couple of words: '3 failing test(s)', 'only py3.10', 'flaky?'."""
    kind, detail = found.get("kind", ""), found.get("detail") or {}
    if kind == "code":
        key = f"tk_code_{detail.get('what', '')}"
        return t(key if key in TEXT["en"] else "tk_code_", lang, count=detail.get("count", 0))
    if kind == "matrix":
        return t("tk_matrix", lang, value=clean(detail.get("value"), 30))
    if kind == "infra":
        return t(f"ts_{detail.get('signal', 'runner')}", lang)
    if kind == "unknown" and detail.get("jobs") == 0:   # no log exists to see (#331)
        return t("tk_nojobs", lang)
    return t(f"tk_{kind or 'unknown'}", lang)


def band(snap: dict, lang: str) -> list[list[dict]]:
    first, second = [], []
    git = snap.get("git") or {}
    if git.get("branch"):
        who = f" ({clean(git['creator'], 20)})" if git.get("creator") else ""
        first.append(seg(f"⎇ {clean(git['branch'], 50)}{who}", "info"))
        prs, ci = snap.get("prs") or {}, snap.get("ci") or {}
        first += [s for s in (_prs(prs, lang), _reviews(prs, lang), _ci(ci, lang),
                              _gh_trouble(prs, ci, lang)) if s]
        found = snap.get("tabib") or {}
        if found.get("cause_found"):
            first.append(seg(t("tabib_cause", lang), "info"))
        elif found.get("kind"):
            first.append(seg(t("tabib", lang, label=tabib_label(found, lang)), "warn"))
    page = snap.get("lawha") or {}
    if page:
        if not page.get("current"):
            first.append(seg(t("lawha_old", lang), "dim"))
        elif page.get("verdict") == "pass":
            first.append(seg(t("lawha_ok", lang, n=page.get("widths", 0)), "ok"))
        else:
            first.append(seg(t("lawha_bad", lang, n=page.get("fail", 0)), "bad"))
    ready = (snap.get("family") or {}).get("amin") or []
    if ready:
        first.append(seg(t("fam_amin", lang, n=len(ready)), "info"))
    for key in ("ram", "disk"):
        part = (snap.get("device") or {}).get(key) or {}
        if part.get("percent") is not None:
            first.append(seg(t(key, lang, p=part["percent"]), level_tone(part.get("level", ""))))

    context = snap.get("context") or {}
    if context.get("percent") is not None:
        tone = {"fresh": "ok", "mid": "warn", "full": "bad"}[context["level"]]
        second.append(seg(t(f"ctx_{context['level']}", lang, p=context["percent"]), tone))
    cost = snap.get("cost") or {}
    if cost.get("usd") is not None:
        if cost.get("budget_usd"):
            second.append(seg(t("cost_budget", lang, usd=money(cost["usd"]), today=money(cost["today_usd"]),
                                budget=money(cost["budget_usd"])), level_tone(cost.get("level", ""))))
        else:
            second.append(seg(t("cost", lang, usd=money(cost["usd"])), "dim"))
    agents = snap.get("agents") or []
    if agents:
        more = " " + t("agents_more", lang, n=len(agents) - 1) if len(agents) > 1 else ""
        second.append(seg(t("agent", lang, type=clean(agents[0].get("type"), 24),
                            desc=clean(agents[0].get("description"), 40)) + more, "info"))
    tasks = snap.get("tasks") or {}
    if tasks.get("total"):
        if tasks.get("all_done"):
            second.append(seg(t("tasks_done", lang, total=tasks["total"]), "ok"))
        else:
            second.append(seg(t("task", lang, step=tasks["step"], total=tasks["total"],
                                text=clean(tasks.get("current"), 48)), "plain"))
    haris = snap.get("haris") or {}
    if haris.get("profile"):
        watch = haris.get("mode") == "watch"
        words = t("haris_watch", lang) if watch else t("haris", lang, profile=clean(haris["profile"], 16))
        second.append(seg(words, "warn" if watch else "dim"))
    due = ((snap.get("family") or {}).get("prof") or {}).get("due")
    if due:
        second.append(seg(t("fam_prof", lang, n=due), "info"))
    return [line for line in (first, second) if line]


def plain(lines: list[list[dict]]) -> str:
    return "\n".join(SEP.join(s["text"] for s in line) for line in lines)


def ansi(lines: list[list[dict]]) -> str:
    def paint(s: dict) -> str:
        code = ANSI.get(s["tone"])
        return f"\x1b[{code}m{s['text']}\x1b[0m" if code else s["text"]
    sep = f"\x1b[2m{SEP}\x1b[0m"
    return "\n".join(sep.join(paint(s) for s in line) for line in lines)


def _section(title: str, lines: list[dict]) -> dict:
    return {"title": title, "lines": lines}


def _off(entry: dict, lang: str) -> str:
    return t("d_prs_off", lang, why=t(entry.get("why") or "unknown", lang, tool=entry.get("tool") or "gh"))


def _size(n: int) -> str:
    return f"{n / 1024 / 1024:.1f} MB" if n >= 1024 * 1024 else f"{n / 1024:.1f} KB"


def _family(found: dict, lang: str) -> list[dict]:
    """amin, manar, barq and prof, from their status files: one line each, when there is news."""
    lines = []
    ready = found.get("amin") or []
    if ready:
        names = ", ".join(f"{clean(r['name'], 20)} {clean(r['next'], 16)}".strip() for r in ready[:8])
        lines.append(seg(t("d_fam_amin", lang, list=names), "info"))
    audit = found.get("manar") or {}
    if audit:
        score = audit["score"]
        lines.append(seg(t("d_fam_manar", lang, score=score, target=clean(audit.get("target"), 80),
                           when=clean(audit.get("date"), 20).replace("T", " ")),
                         "ok" if score >= 90 else "warn" if score >= 70 else "bad"))
    barq = found.get("barq") or {}
    if barq:
        saved, calls = barq.get("saved_bytes", 0), barq.get("calls", 0)
        if saved >= 0:
            lines.append(seg(t("d_fam_barq", lang, calls=calls, tokens=f"{saved // 4:,}"), "dim"))
        else:
            lines.append(seg(t("d_fam_barq_more", lang, calls=calls, size=_size(-saved)), "warn"))
    prof = found.get("prof") or {}
    if prof.get("due") or prof.get("open"):
        lines.append(seg(t("d_fam_prof", lang, n=prof.get("due", 0), open=prof.get("open", 0)),
                         "info" if prof.get("due") else "dim"))
    return lines


def detail(snap: dict, lang: str) -> list[dict]:
    sections = []
    git = snap.get("git") or {}
    if git.get("branch"):
        if git.get("creator"):
            text = t("d_branch", lang, branch=clean(git["branch"], 80), creator=clean(git["creator"], 30),
                     source=t(f"src_{git.get('creator_source') or 'user'}", lang))
        else:
            text = t("d_branch_plain", lang, branch=clean(git["branch"], 80))
        sections.append(_section(t("t_branch", lang), [seg(text, "info")]))
        prs = snap.get("prs") or {}
        title = t("t_mrs" if prs.get("tool") == "glab" else "t_prs", lang)
        if prs.get("state") == "ok":
            users = ", ".join(f"{clean(n, 30)} ({c})" for n, c in prs.get("per_user") or []) or "-"
            sections.append(_section(title, [seg(t("d_prs", lang, total=prs.get("total", 0), list=users))]))
        elif prs.get("state") == "loading":
            sections.append(_section(title, [seg(t("d_loading", lang), "dim")]))
        else:
            sections.append(_section(title, [seg(_off(prs, lang), "dim")]))
        ci = snap.get("ci") or {}
        lines = [s for s in [_ci(ci, lang)] if s] or [seg(_off(ci, lang), "dim")]
        more_jobs = (ci.get("failed") or [])[1:8]
        lines += [seg(t("d_ci_job", lang, job=clean(job, 80)), "bad") for job in more_jobs]
        allowed = ci.get("allowed") or []
        if allowed:
            more = f" +{len(allowed) - 1}" if len(allowed) > 1 else ""
            lines.append(seg(t("d_ci_allowed", lang, job=clean(allowed[0], 80) + more), "dim"))
        if ci.get("url"):
            lines.append(seg(t("d_ci_url", lang, url=clean(ci["url"], 200)), "dim"))
        if ci.get("error"):
            why = t(ci["error"], lang, tool=ci.get("tool") or "gh")
            lines.append(seg(t("d_ci_kept", lang, why=why), "warn"))
        found = snap.get("tabib") or {}
        if found.get("kind"):
            lines.append(seg(t("d_tabib", lang, label=tabib_label(found, lang),
                               confidence=clean(found.get("confidence"), 10)), "warn"))
        if found.get("cause"):
            lines.append(seg(t("d_tabib_cause", lang, cause=clean(found["cause"], 200)), "info"))
        elif snap.get("why"):
            lines.append(seg(t("d_tabib_ask", lang), "dim"))
        sections.append(_section(t("t_ci", lang), lines))
    else:
        sections.append(_section(t("t_branch", lang), [seg(t("d_no_repo", lang), "dim")]))

    page = snap.get("lawha") or {}
    if page:
        passed = page.get("verdict") == "pass"
        covered = t("d_lawha_covered", lang, n=page.get("widths", 0),
                    themes="/".join(page.get("themes") or []),
                    dirs="/".join(d.upper() for d in page.get("dirs") or []))
        verdict = t("d_lawha_ok" if passed else "d_lawha_bad", lang,
                    n=page.get("fail", 0), warn=page.get("warn", 0))
        lines = [seg(verdict, "ok" if passed else "bad"),
                 seg(f"{page.get('url', '')} · {covered}", "dim")]
        lines += [seg(f"{p['text']} ({p['where']})", "bad") for p in page.get("problems") or []]
        if not page.get("current"):
            lines.append(seg(t("d_lawha_old", lang, when=page.get("created", "").replace("T", " ")), "warn"))
        if page.get("report"):
            lines.append(seg(t("d_lawha_report", lang, path=page["report"]), "dim"))
        if snap.get("fix"):
            lines.append(seg(t("d_lawha_fix", lang), "dim"))
        sections.append(_section(t("t_lawha", lang), lines))

    lines = _family(snap.get("family") or {}, lang)
    if lines:
        sections.append(_section(t("t_family", lang), lines))

    device = snap.get("device") or {}
    lines = []
    ram, disk = device.get("ram") or {}, device.get("disk") or {}
    if ram.get("percent") is not None:
        lines.append(seg(t("d_ram", lang, p=ram["percent"], used=ram.get("used_gb", "?"),
                           total=ram.get("total_gb", "?")), level_tone(ram.get("level", ""))))
    if disk.get("percent") is not None:
        lines.append(seg(t("d_disk", lang, p=disk["percent"], free=disk.get("free_gb", "?")),
                         level_tone(disk.get("level", ""))))
    if any(p.get("level") in ("warn", "bad") for p in (ram, disk)):
        lines.append(seg(t("d_device_warn", lang, p=85), "warn"))
    sections.append(_section(t("t_device", lang), lines or [seg(t("unknown", lang), "dim")]))

    context = snap.get("context") or {}
    if context.get("percent") is not None:
        lines = [seg(t("d_context", lang, p=context["percent"], window=context.get("window") or "?",
                       level=t(f"d_level_{context['level']}", lang))), seg(t("d_levels", lang), "dim")]
        if context["level"] in ("mid", "full"):
            lines.append(seg(t(f"d_context_{context['level']}", lang), "warn"))
        sections.append(_section(t("t_context", lang), lines))
    cost = snap.get("cost") or {}
    if cost.get("usd") is not None:
        lines = [seg(t("d_cost", lang, usd=money(cost["usd"]))),
                 seg(t("d_cost_today", lang, today=money(cost.get("today_usd") or 0)), "dim")]
        if cost.get("budget_usd"):
            percent = round(100 * (cost.get("today_usd") or 0) / cost["budget_usd"])
            lines.append(seg(t("d_budget", lang, budget=money(cost["budget_usd"]), p=percent),
                             level_tone(cost.get("level", ""))))
        sections.append(_section(t("t_cost", lang), lines))
    agents = snap.get("agents") or []
    sections.append(_section(t("t_agents", lang), [
        seg(t("d_agent", lang, type=clean(a.get("type"), 30), desc=clean(a.get("description"), 100)), "info")
        for a in agents[:10]] or [seg(t("d_no_agents", lang), "dim")]))
    tasks = snap.get("tasks") or {}
    marks = {"completed": ("d_task_done", "dim"), "in_progress": ("d_task_now", "info"),
             "pending": ("d_task_open", "plain")}
    lines = []
    for item in (tasks.get("items") or [])[:30]:
        word, tone = marks[item["status"]]
        lines.append(seg(f"[{t(word, lang)}] {clean(item.get('text'), 120)}", tone))
    sections.append(_section(t("t_tasks", lang), lines or [seg(t("d_no_tasks", lang), "dim")]))
    haris = snap.get("haris") or {}
    if haris.get("profile"):
        mode = t("mode_watch" if haris.get("mode") == "watch" else "mode_enforce", lang)
        line = seg(t("d_haris", lang, profile=clean(haris["profile"], 20), mode=mode), "dim")
    else:
        line = seg(t("d_haris_off", lang), "dim")
    sections.append(_section(t("t_guard", lang), [line]))
    return sections


def _seconds(value) -> str:
    try:
        return f"{float(value):g}"
    except (TypeError, ValueError):
        return "?"


def proof_view(proof: dict, lang: str, head: str = "") -> list[dict]:
    """The itqan proof as pane sections: checks itqan ran itself, then what Claude reported."""
    if not proof:
        return [_section(t("proof_title", lang), [seg(t("proof_none", lang), "dim")])]
    checks = proof.get("checks") or []
    passed = bool(checks) and all(c.get("passed") for c in checks)
    lines = [seg(t("proof_ok" if passed else "proof_bad", lang), "ok" if passed else "bad"),
            seg(t("proof_made", lang, when=clean(proof.get("created"), 20).replace("T", " "),
                  branch=clean(proof.get("branch") or "-", 60), commit=clean(proof.get("commit") or "-", 12)),
                "dim")]
    commit = str(proof.get("commit") or "")
    if head and commit and not head.startswith(commit):
        lines.append(seg(t("proof_stale", lang), "warn"))
    sections = [_section(t("proof_title", lang), lines)]
    sections.append(_section(t("proof_checks", lang), [
        seg(f"{'✓' if c.get('passed') else '✗'} {clean(c.get('name'), 20)}: {clean(c.get('command'), 80)}"
            f"{' = ' + clean(c.get('defined'), 80) if c.get('defined') else ''} "
            f"({_seconds(c.get('seconds'))}s)", "ok" if c.get("passed") else "bad")
        for c in checks] or [seg("-", "dim")]))
    for c in checks:
        if not c.get("passed") and c.get("tail"):
            sections[-1]["lines"] += [seg("  " + clean(line, 160), "dim") for line in c["tail"][-6:]]
    failure = proof.get("ci_failure") or {}
    if failure.get("run"):
        reproduced = failure.get("reproduced") == "reproduced"
        lines = [seg(t("proof_ci", lang, run=clean(failure["run"], 20)), "info")]
        if reproduced:
            lines.append(seg(t("proof_ci_reproduced", lang), "ok"))
        if failure.get("cause"):
            lines.append(seg(clean(failure["cause"], 200), "dim"))
        sections.append(_section(t("proof_ci_title", lang), lines))
    ui = proof.get("ui") or {}
    if ui:
        ok = ui.get("verdict") == "pass"
        verdict = t("d_lawha_ok" if ok else "d_lawha_bad", lang, n=ui.get("fail", 0), warn=ui.get("warn", 0))
        lines = [seg(verdict, "ok" if ok else "bad"),
                 seg(f"{clean(ui.get('url'), 160)} · {len(ui.get('widths') or [])} widths", "dim")]
        lines += [seg(clean(p, 160), "bad") for p in (ui.get("problems") or [])[:5]]
        sections.append(_section(t("t_lawha", lang), lines))
    review = proof.get("review") or {}
    if review.get("verdict"):
        tone = "ok" if review["verdict"] == "approve" else "warn"
        lines = [seg(clean(review["verdict"], 20), tone)]
        lines += [seg(clean(note, 200), "dim") for note in (review.get("notes") or [])[:10]]
        sections.append(_section(t("proof_review", lang), lines))
    reqs = proof.get("requirements") or []
    if reqs:
        sections.append(_section(t("proof_reqs", lang), [
            seg(f"{'✓' if r.get('done') else '·'} {clean(r.get('text'), 160)}",
                "ok" if r.get("done") else "warn") for r in reqs[:30]]))
    return sections


def sections_text(sections: list[dict]) -> str:
    out = []
    for section in sections:
        out.append(section["title"])
        out += ["  " + line["text"] for line in section["lines"]]
    return "\n".join(out)


def labels(lang: str) -> dict:
    keys = ("full_saved", "full_type", "full_nosave", "full_type_nosave", "proof_ask", "yes", "no", "close",
            "details", "proof_missing", "proof_title", "why", "fix")
    return {key: t(key, lang) for key in keys}
