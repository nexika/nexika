"""mizan: the Python core, its fallbacks, and how it works with hafiz, haris, siyaq and itqan."""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import pytest
from conftest import PLUGINS

MIZAN_ROOT = PLUGINS / "mizan"
BIN = MIZAN_ROOT / "bin" / "mizan"
for root in (MIZAN_ROOT, PLUGINS / "siyaq", PLUGINS / "haris"):
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

from mizan import (  # noqa: E402
    config,
    device,
    family,
    forge,
    gitinfo,
    hooks,
    i18n,
    render,
    snapshot,
    status,
    tasks,
)
from siyaq import hooks as siyaq_hooks  # noqa: E402
from siyaq import rank  # noqa: E402

ANSI = re.compile(r"\x1b\[[0-9;]*m")
REAL_HOME = os.environ.get("HOME", "")  # the itqan check below runs pytest, which may live in the user site


@pytest.fixture
def env(tmp_path, monkeypatch):
    """mizan, the status files, hafiz, itqan and HOME all in tmp_path; no network; English."""
    values = {"MIZAN_HOME": tmp_path / "mizan", "NEXIKA_STATUS_HOME": tmp_path / "status",
              "HAFIZ_HOME": tmp_path / "hafiz", "ITQAN_HOME": tmp_path / "itqan", "HOME": tmp_path / "home"}
    for key, value in values.items():
        monkeypatch.setenv(key, str(value))
    (tmp_path / "home").mkdir()
    monkeypatch.setenv("MIZAN_OFFLINE", "1")
    monkeypatch.setenv("MIZAN_LANG", "en")
    return tmp_path


def git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


@pytest.fixture
def repo(env):
    root = env / "repo"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.name", "Loai Elattar")
    git(root, "config", "user.email", "loai@example.com")
    (root / "a.txt").write_text("a\n")
    git(root, "add", "-A")
    git(root, "-c", "user.name=Jean Dupont", "commit", "-q", "-m", "initial")
    return root


def run(*args, stdin: dict | str | None = None, cwd=None) -> subprocess.CompletedProcess:
    data = stdin if isinstance(stdin, str) or stdin is None else json.dumps(stdin)
    return subprocess.run([sys.executable, str(BIN), *args], input=data or "", capture_output=True, text=True,
                          cwd=cwd, timeout=60, env=os.environ.copy())


# ---------------------------------------------------------------- levels and device

@pytest.mark.parametrize("percent,level", [(0, "fresh"), (39, "fresh"), (40, "mid"), (75, "mid"), (76, "full"),
                                           (100, "full")])
def test_context_levels(percent, level):
    assert snapshot.context_level(percent) == level


@pytest.mark.parametrize("percent,level", [(None, "unknown"), (10, "ok"), (84, "ok"), (85, "warn"), (94, "warn"),
                                           (95, "bad")])
def test_device_levels(percent, level):
    assert device.level(percent) == level


def test_meminfo_and_vm_stat():
    total, available = device.parse_meminfo("MemTotal: 16000000 kB\nMemFree: 1000 kB\nMemAvailable: 4000000 kB\n")
    assert (total, available) == (16000000 * 1024, 4000000 * 1024)
    assert device.parse_meminfo("MemTotal: 1000 kB\nMemFree: 100 kB\nCached: 100 kB\n") == (1024000, 204800)
    vm = "Mach Virtual Memory Statistics: (page size of 16384 bytes)\nPages free: 100.\nPages inactive: 50.\n"
    assert device.parse_vm_stat(vm, 10_000_000) == (10_000_000, 150 * 16384)


def test_device_reading_is_sane(env):
    found = device.read(str(env))
    assert found["disk"]["percent"] is None or 0 <= found["disk"]["percent"] <= 100


# ---------------------------------------------------------------- git: branch and creator

def test_creator_is_you_until_the_branch_has_commits(repo):
    git(repo, "switch", "-q", "-c", "feat/x")
    info = gitinfo.read(str(repo))
    assert (info["branch"], info["creator"], info["creator_source"]) == ("feat/x", "Loai", "user")
    (repo / "b.txt").write_text("b\n")
    git(repo, "add", "-A")
    git(repo, "-c", "user.name=Sara Nabil", "commit", "-q", "-m", "first own commit")
    (repo / "c.txt").write_text("c\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "second")
    info = gitinfo.read(str(repo))
    assert (info["creator"], info["creator_source"]) == ("Sara", "commit")


def test_default_branch_has_no_creator(repo):
    info = gitinfo.read(str(repo))
    assert info["branch"] == "main" and info["creator"] == ""


def test_not_a_repo(env):
    assert gitinfo.read(str(env)) == {}


@pytest.mark.parametrize("remote,host", [
    ("git@github.com:nexika/nexika.git", "github"), ("https://github.com/nexika/nexika", "github"),
    ("ssh://git@gitlab.com/a/b.git", "gitlab"), ("https://gitlab.example.org/a/b", "gitlab"),
    ("https://example.com/a/b", ""), ("", ""), ("https://evil.com/github.com/x", "")])
def test_host_of(remote, host):
    assert gitinfo.host_of(remote) == host


# ---------------------------------------------------------------- gh and glab answers

PRS = json.dumps([
    {"number": 1, "author": {"login": "loai", "name": "Loai Elattar"}, "headRefName": "feat/a"},
    {"number": 2, "author": {"login": "jean", "name": "Jean Dupont"}, "headRefName": "feat/b"},
    {"number": 3, "author": {"login": "loai", "name": "Loai Elattar"}, "headRefName": "feat/x", "url": "u"},
    {"number": 4, "author": {"login": "bot", "name": ""}, "headRefName": "deps"},
    {"number": 5, "author": {"login": "jean", "name": "Jean Dupont"}, "headRefName": "feat/c"},
    {"number": 6, "author": {"login": "loai", "name": "Loai Elattar"}, "headRefName": "feat/d"},
])


def test_prs_per_user_and_branch_pr():
    found = forge.parse_gh_prs(PRS, "feat/x")
    assert found["per_user"] == [["Loai", 3], ["Jean", 2], ["bot", 1]]
    assert found["branch_pr"] == {"number": 3, "author": "Loai", "url": "u"}
    assert render._prs(found, "en")["text"] == "PRs Loai(3) Jean(2) bot(1)"


def test_glab_merge_requests():
    mrs = json.dumps([{"iid": 9, "author": {"username": "sara", "name": "Sara Nabil"}, "source_branch": "fix/y",
                       "web_url": "w"}])
    found = forge.parse_glab_mrs(mrs, "fix/y")
    assert found["per_user"] == [["Sara", 1]] and found["branch_pr"]["number"] == 9
    assert render._prs(found, "en")["text"] == "MRs Sara(1)"


def test_checks_and_runs():
    assert forge.parse_gh_checks(json.dumps([{"name": "lint", "bucket": "pass"},
                                             {"name": "test (py3.10)", "bucket": "fail"}])) == \
        {"state": "failed", "failed": ["test (py3.10)"], "run": None}
    linked = json.dumps([{"name": "t", "bucket": "fail", "link": "https://github.com/a/b/actions/runs/42/job/7"}])
    assert forge.parse_gh_checks(linked)["run"] == 42
    assert forge.parse_gh_checks(json.dumps([{"name": "a", "bucket": "pass"}, {"name": "b", "bucket": "pending"}]))[
        "state"] == "running"
    assert forge.parse_gh_checks(json.dumps([{"name": "a", "bucket": "pass"}]))["state"] == "passed"
    assert forge.parse_gh_checks("[]")["state"] == "none"
    runs = json.dumps([
        {"databaseId": 7, "status": "completed", "conclusion": "failure", "name": "CI", "headSha": "new"},
        {"databaseId": 6, "status": "completed", "conclusion": "success", "name": "CI", "headSha": "old"}])
    assert forge.parse_gh_runs(runs, "new")["failed_run"] == 7
    assert forge.parse_gh_runs(runs, "old")["state"] == "passed"
    assert forge.parse_gh_runs(runs, "unpushed")["state"] == "failed"  # falls back to the newest commit's runs
    running = json.dumps([{"databaseId": 8, "status": "in_progress", "conclusion": "", "name": "CI", "headSha": "h"}])
    assert forge.parse_gh_runs(running, "h")["state"] == "running"
    jobs = json.dumps({"jobs": [{"name": "lint", "conclusion": "success"},
                                {"name": "test (py3.12)", "conclusion": "failure"}]})
    assert forge.parse_gh_jobs(jobs) == ["test (py3.12)"]


def test_glab_pipeline():
    assert forge.parse_glab_pipeline(json.dumps({"status": "failed", "jobs": [{"name": "rspec", "status": "failed"}]}))[
        "failed"] == ["rspec"]
    assert forge.parse_glab_pipeline(json.dumps({"status": "running"}))["state"] == "running"
    assert forge.parse_glab_pipeline(json.dumps({"status": "success"}))["state"] == "passed"


def test_missing_tool_is_reported_not_raised(repo, monkeypatch):
    info = {**gitinfo.read(str(repo)), "host": "github", "remote": "git@github.com:a/b.git"}
    monkeypatch.setenv("PATH", "/nonexistent")
    assert forge.fetch_prs(info) == {"state": "off", "why": "off_tool", "tool": "gh"}


def test_cache_marks_a_new_commit_stale(repo):
    info = gitinfo.read(str(repo))
    forge.save_cache(info["repo"], {"prs": {"state": "ok", "per_user": [], "fetched": time.time()},
                                    "ci": {"main": {"state": "passed", "head": "older", "fetched": time.time()}}})
    found = forge.cached(info)
    assert found["ci"]["stale"] and found["due"]
    assert render._ci(found["ci"], "en")["tone"] == "dim"


# ---------------------------------------------------------------- the band and the status line

def snap(**over):
    base = {"git": {"branch": "feat/x", "creator": "Loai"},
            "prs": {"state": "ok", "tool": "gh", "per_user": [["Loai", 7], ["Jean", 3]]},
            "ci": {"state": "failed", "failed": ["test (py3.10)", "lint"]},
            "device": {"ram": {"percent": 96, "level": "bad"}, "disk": {"percent": 50, "level": "ok"}},
            "context": {"percent": 52, "level": "mid", "window": 200000},
            "cost": {"usd": 1.84, "today_usd": 1.84, "budget_usd": 0},
            "agents": [{"type": "Explore", "description": "find auth code"}, {"type": "Plan", "description": "x"}],
            "tasks": tasks.summarize([{"text": "a", "status": "completed"}, {"text": "b", "status": "completed"},
                                      {"text": "c", "active": "Writing tests", "status": "in_progress"},
                                      {"text": "d", "status": "pending"}]),
            "haris": {"profile": "standard", "mode": "on"}}
    return {**base, **over}


def test_band_lines_in_english():
    lines = render.plain(render.band(snap(), "en")).splitlines()
    assert lines[0] == "⎇ feat/x (Loai) · PRs Loai(7) Jean(3) · CI failed: test (py3.10) +1 · RAM 96% · Disk 50%"
    assert lines[1] == ("Context mid 52% · $1.84 · Agent Explore: find auth code +1 more · "
                        "Task 3/4: Writing tests · haris standard")


def test_band_lines_in_arabic():
    text = render.plain(render.band(snap(), "ar"))
    for words in ("طلبات الدمج Loai(7) Jean(3)", "فشل الفحص: test (py3.10)", "الذاكرة 96%", "السياق متوسط 52%",
                  "المهمة 3/4", "حارس standard"):
        assert words in text


def test_every_text_has_both_languages():
    assert set(i18n.TEXT["en"]) == set(i18n.TEXT["ar"])
    for key, value in i18n.TEXT["en"].items():
        assert set(re.findall(r"{(\w+)}", value)) == set(re.findall(r"{(\w+)}", i18n.TEXT["ar"][key])), key


def test_outside_text_cannot_inject_terminal_codes():
    dirty = snap(git={"branch": "feat/\x1b[2Jevil‮", "creator": "Lo\x07ai"})
    text = render.ansi(render.band(dirty, "en"))
    assert "\x1b[2J" not in text and "‮" not in text and "\x07" not in text


def test_status_line_is_the_band_painted():
    lines = render.band(snap(), "en")
    assert ANSI.sub("", render.ansi(lines)) == render.plain(lines)


def test_budget_colors_the_cost(env):
    (env / "mizan").mkdir()
    (env / "mizan" / "config.json").write_text(json.dumps({"daily_budget_usd": 2}))
    assert snapshot._cost("s1", 1.7)["level"] == "warn"
    assert snapshot._cost("s1", 2.5)["level"] == "bad"
    status.publish("mizan", {"session": "other", "cost_usd": 1.0, "date": snapshot.today()}, "other")
    assert snapshot._cost("s1", 0.5)["today_usd"] == 1.5


def test_task_steps():
    assert tasks.summarize([])["total"] == 0
    found = tasks.summarize([{"text": "a", "status": "completed"}, {"text": "b", "status": "pending"}])
    assert (found["step"], found["current"], found["all_done"]) == (2, "b", False)
    assert tasks.summarize([{"text": "a", "status": "completed"}])["all_done"]


def test_tasks_from_transcript(tmp_path):
    rows = [{"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "TodoWrite", "input": {
        "todos": [{"content": "old", "status": "pending", "activeForm": "Old"}]}}]}},
            {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "TodoWrite", "input": {
                "todos": [{"content": "a", "status": "completed", "activeForm": "A"},
                          {"content": "b", "status": "in_progress", "activeForm": "Doing b"}]}}]}}]
    path = tmp_path / "t.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n{broken\n")
    assert [t["text"] for t in tasks.from_transcript(str(path))] == ["a", "b"]
    assert tasks.from_transcript(str(tmp_path / "missing.jsonl")) == []


# ---------------------------------------------------------------- the helper: status, statusline, report, export

MOD_PAYLOAD = {"session": "s1", "context": {"percent": 52, "tokens": 104000, "window": 200000},
               "cost": {"usd": 1.84}, "agents": [{"type": "Explore", "description": "find auth code"}],
               "tasks": {"items": [{"text": "a", "status": "completed"},
                                   {"text": "b", "active": "Writing b", "status": "in_progress"}]}}


def test_status_json_is_the_snapshot(repo, env):
    done = run("status", "--json", "--stdin", "--publish", stdin={**MOD_PAYLOAD, "cwd": str(repo)})
    assert done.returncode == 0, done.stderr
    data = json.loads(done.stdout)
    assert data["schema"] == "nexika.mizan/1"
    assert data["context"]["level"] == "mid" and data["tasks"]["step"] == 2
    assert data["prs"] == {"state": "off", "why": "off_offline", "tool": ""}
    assert data["band"][1][0] == {"text": "Context mid 52%", "tone": "warn"}
    assert set(data["labels"]) >= {"full_saved", "proof_ask", "yes", "no"}
    published = status.read("mizan", "s1")
    assert published["level"] == "mid" and published["mod"] is True and published["cost_usd"] == 1.84


def test_status_line_shows_the_same_line_as_the_mod(repo, env):
    mod = json.loads(run("status", "--json", "--stdin", stdin={**MOD_PAYLOAD, "cwd": str(repo),
                                                               "agents": []}).stdout)
    line = {"session_id": "s2", "transcript_path": "", "workspace": {"current_dir": str(repo)},
            "cost": {"total_cost_usd": 1.84},
            "context_window": {"used_percentage": 52, "total_input_tokens": 104000, "context_window_size": 200000}}
    done = run("statusline", stdin=line)
    assert done.returncode == 0
    printed = ANSI.sub("", done.stdout).strip().splitlines()
    assert printed[0] == render.plain(mod["band"]).splitlines()[0]
    assert printed[1].startswith("Context mid 52% · $1.84")
    assert status.read("mizan", "s2")["mod"] is False


def test_status_line_never_hides_a_live_mod(env):
    snapshot.build({**MOD_PAYLOAD, "cwd": str(env)}, publish=True)
    snapshot.build({"session_id": "s1", "workspace": {"current_dir": str(env)}}, publish=True)
    assert status.read("mizan", "s1")["mod"] is True
    data = status.read("mizan", "s1")
    data["mod_at"] = time.time() - 3600
    status.publish("mizan", data, "s1")
    snapshot.build({"session_id": "s1", "workspace": {"current_dir": str(env)}}, publish=True)
    assert status.read("mizan", "s1")["mod"] is False


def test_status_line_survives_garbage(env):
    done = run("statusline", stdin="{not json")
    assert done.returncode == 0


def test_report_and_export_use_the_last_session(repo, env):
    run("status", "--json", "--stdin", "--publish", stdin={**MOD_PAYLOAD, "cwd": str(repo)})
    report = run("report", cwd=repo)
    assert report.returncode == 0
    assert "Context mid 52%" in report.stdout and "[now] b" in report.stdout and "Device" in report.stdout
    export = json.loads(run("export", "--json", cwd=repo).stdout)
    assert export["schema"] == "nexika.mizan/1" and export["cost"]["usd"] == 1.84


def test_status_in_arabic(repo, env, monkeypatch):
    monkeypatch.setenv("MIZAN_LANG", "ar")
    done = run("status", "--stdin", stdin={**MOD_PAYLOAD, "cwd": str(repo)})
    assert "السياق متوسط 52%" in done.stdout


# ---------------------------------------------------------------- hooks: the note and the fallback flow

def test_startup_note_is_small_with_a_long_path():
    long_path = "/home/" + "a-rather-long-user-name/" * 3 + ".claude/plugins/cache/nexika/mizan/0.1.0/bin/mizan"
    note = json.loads(hooks.on_session_start({}, long_path))["hookSpecificOutput"]["additionalContext"]
    assert len(note.encode("utf-8")) < 400
    assert "/clear" in note and "never clear" in note and long_path in note


def test_startup_note_from_the_helper():
    done = run("hook", "session-start", stdin={})
    note = json.loads(done.stdout)["hookSpecificOutput"]["additionalContext"]
    assert len(note.encode("utf-8")) < 400 and str(BIN) in note


def test_stop_hook_at_full_without_the_mod(env, monkeypatch):
    calls = []
    monkeypatch.setattr(family, "handoff", lambda s, t, c: calls.append(s) or {"saved": True})
    status.publish("mizan", {"level": "full", "mod": False}, "s1")
    first = json.loads(hooks.on_stop({"session_id": "s1", "transcript_path": "t", "cwd": "."}))
    assert "Type /clear and press Enter" in first["systemMessage"] and calls == ["s1"]
    assert hooks.on_stop({"session_id": "s1"}) == ""  # once per crossing
    status.publish("mizan", {"level": "fresh", "mod": False}, "s1")
    hooks.on_stop({"session_id": "s1"})
    status.publish("mizan", {"level": "full", "mod": False}, "s1")
    assert hooks.on_stop({"session_id": "s1"})


def test_stop_hook_steps_aside_for_the_mod_and_refreshes_at_mid(env, monkeypatch):
    calls = []
    monkeypatch.setattr(family, "handoff", lambda s, t, c: calls.append(s) or {"saved": True})
    status.publish("mizan", {"level": "full", "mod": True}, "s1")
    assert hooks.on_stop({"session_id": "s1"}) == "" and calls == []
    status.publish("mizan", {"level": "mid", "mod": False}, "s2")
    for _ in range(6):
        assert hooks.on_stop({"session_id": "s2"}) == ""
    assert calls == ["s2", "s2"]
    assert hooks.on_stop({"session_id": "../etc"}) == ""


# ---------------------------------------------------------------- hafiz: the handoff

def transcript(env) -> Path:
    path = env / "home" / ".claude" / "projects" / "p" / "s1.jsonl"
    path.parent.mkdir(parents=True)
    rows = [{"type": "user", "message": {"role": "user", "content": "Add the login page"}, "cwd": str(env)},
            {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": "Done."}]}}]
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    return path


def test_mizan_finds_hafiz_beside_it():
    assert family.find_plugin("hafiz") == PLUGINS / "hafiz"
    assert family.find_plugin("nothing-here") is None


def test_handoff_through_hafiz(repo, env):
    path = transcript(env)
    done = run("handoff", stdin={"session": "s1", "transcript": str(path), "cwd": str(repo)}, cwd=repo)
    assert json.loads(done.stdout) == {"saved": True, "why": ""}
    refused = run("handoff", stdin={"session": "s1", "transcript": "/etc/hostname", "cwd": str(repo)}, cwd=repo)
    assert json.loads(refused.stdout)["saved"] is False


def test_hafiz_save_reads_only_session_transcripts(repo, env):
    secret = env / "home" / "notes.jsonl"
    secret.write_text("{}\n")
    done = subprocess.run([sys.executable, str(PLUGINS / "hafiz" / "bin" / "hafiz"), "handoff", "--save",
                           "--session", "s1", "--transcript", str(secret)], cwd=repo, capture_output=True,
                          text=True, env=os.environ.copy())
    assert done.returncode == 1 and "Nothing saved" in done.stderr


# ---------------------------------------------------------------- haris: status and protection

def test_haris_publishes_its_state_for_the_band(repo, env):
    event = {"session_id": "s1", "cwd": str(repo), "hook_event_name": "SessionStart"}
    done = subprocess.run([sys.executable, str(PLUGINS / "haris" / "bin" / "haris"), "hook", "session-start"],
                          input=json.dumps(event), capture_output=True, text=True, env=os.environ.copy(), cwd=repo)
    assert done.returncode == 0
    assert family.haris_status("s1") == {"profile": "standard", "mode": "on"}
    text = render.plain(render.band({"haris": family.haris_status("s1")}, "en"))
    assert text == "haris standard"


def test_haris_guards_mizan(repo, env):
    from haris import policy

    cfg = policy.effective_config(str(repo))
    home = env / "home"
    cache_bin = f"{home}/.claude/plugins/cache/nexika/mizan/0.1.0/bin/mizan"
    cases = {
        f"echo '{{}}' > {env}/status/mizan/s1.json": "deny",
        f"rm -rf {env}/mizan": "deny",
        "claude plugin uninstall mizan": "deny",
        f"python3 {cache_bin} hook stop": "deny",
        f"python3 {cache_bin} status --stdin --publish": "deny",
        f"python3 {cache_bin} report": "allow",
    }
    for command, verdict in cases.items():
        decision = policy.decide({"tool_name": "Bash", "tool_input": {"command": command}, "cwd": str(repo)}, cfg)
        assert decision.verdict == verdict, (command, decision.verdict, decision.cls)


# ---------------------------------------------------------------- siyaq: loads less as the context fills

def test_siyaq_squeeze():
    cfg = rank.settings({})
    assert rank.squeeze(cfg, "fresh") == cfg and rank.squeeze(cfg, "") == cfg
    mid = rank.squeeze(cfg, "mid")
    assert mid["budget_tokens"] == cfg["budget_tokens"] // 2 and mid["top_k"] == cfg["top_k"] - 1
    full = rank.squeeze(cfg, "full")
    assert full["top_k"] == 1 and full["full_max_chars"] == 0 and full["min_score"] == cfg["min_score"] * 2


def test_siyaq_reads_mizans_level(env):
    assert siyaq_hooks.context_level("s1") == ""
    status.publish("mizan", {"level": "full"}, "s1")
    assert siyaq_hooks.context_level("s1") == "full"
    stale = status.read("mizan", "s1")
    stale["updated"] = time.time() - 3600
    status.write_json(status.path_for("mizan", "s1"), stale)
    assert siyaq_hooks.context_level("s1") == ""
    status.write_json(status.path_for("mizan", "s2"), {"schema": "other/1", "updated": time.time(), "level": "full"})
    assert siyaq_hooks.context_level("s2") == ""
    assert siyaq_hooks.context_level("../x") == ""


# ---------------------------------------------------------------- itqan: the proof mizan shows

def test_itqan_proof_is_shown_by_mizan(env):
    project = env / "proj"
    (project / "tests").mkdir(parents=True)
    (project / "pyproject.toml").write_text("[project]\nname = 'p'\n")
    (project / "tests" / "test_ok.py").write_text("def test_ok():\n    assert True\n")
    git(project, "init", "-q", "-b", "feat/p")
    script = PLUGINS / "itqan" / "scripts" / "itqan_proof.py"
    done = subprocess.run([sys.executable, str(script), "run", "--only", "tests", "--review", "approve",
                           "--done", "login works", "--open", "docs"], cwd=project, capture_output=True,
                          text=True, env={**os.environ, "HOME": REAL_HOME}, timeout=300)
    assert done.returncode == 0, done.stdout + done.stderr
    shown = json.loads(run("proof", "--json", cwd=project).stdout)
    assert shown["available"] is True
    proof = shown["proof"]
    assert proof["schema"] == "nexika.itqan.proof/1" and proof["checks"][0]["passed"]
    assert proof["review"]["by"] == "reported by Claude"
    assert [r["done"] for r in proof["requirements"]] == [True, False]
    words = render.sections_text(shown["sections"])
    assert "All checks passed" in words and "✓ login works" in words and "· docs" in words


def test_proof_redacts_secrets_and_skips_unknown_projects(env):
    sys.path.insert(0, str(PLUGINS / "itqan" / "scripts"))
    import itqan_proof

    assert "ghp_" not in itqan_proof.redact("token ghp_" + "a" * 36)
    assert itqan_proof.detect(env) == []
    assert json.loads(run("proof", "--json", cwd=env).stdout)["available"] is False


# ---------------------------------------------------------------- the mod: fixed commands, no AI, no clearing

MOD = (MIZAN_ROOT / "hooks" / "register.tsx").read_text(encoding="utf-8")


def test_mod_runs_only_the_fixed_helper():
    helper = re.search(r"const HELPER = \{(.*?)\} as const", MOD, re.S).group(1)
    assert set(re.findall(r"^\s+(\w+):", helper, re.M)) == {"status", "handoff", "proof"}
    assert MOD.count("$.process.run(") == 1
    assert "const argv = ['python3', `${$.plugin.root}/bin/mizan`, ...HELPER[which]]" in MOD
    assert "$.process.spawn" not in MOD and "$.http" not in MOD


def test_mod_makes_no_model_calls_and_never_clears():
    for forbidden in ("$.model.", "$.agent.spawn", "$.session.compact", "$.prompt.submit", "$.command.run"):
        assert forbidden not in MOD, forbidden
    assert "$.prompt.fill({ text })" in MOD and "offer($, '/clear')" in MOD


def test_hooks_json_has_the_module_and_the_fallback_hooks():
    data = json.loads((MIZAN_ROOT / "hooks" / "hooks.json").read_text())
    assert data["modules"] == ["./register.tsx"]
    assert set(data["hooks"]) == {"SessionStart", "Stop"}


def test_status_files_are_owner_only(env):
    status.publish("mizan", {"level": "mid"}, "s1")
    mode = status.path_for("mizan", "s1").stat().st_mode & 0o777
    assert mode == 0o600 or sys.platform == "win32"
    assert status.path_for("mizan", "../x") is None and not status.publish("mizan", {}, "../x")


def test_config_defaults(env):
    assert config.load()["lang"] == "auto" and config.budget() == 0 and not config.network()


# ---------------------------------------------------------------- review fixes

def test_status_flags_cannot_be_abbreviated(env):
    done = run("status", "--stdin", "--pub", stdin={"session": "s9", "context": {"percent": 5}})
    assert done.returncode != 0 and status.read("mizan", "s9") == {}


def test_forged_costs_are_ignored(env):
    status.publish("mizan", {"session": "evil", "cost_usd": -500, "date": snapshot.today()}, "evil")
    status.publish("mizan", {"session": "nan", "cost_usd": "nan", "date": snapshot.today()}, "nan")
    assert snapshot._cost("s1", 1.0)["today_usd"] == 1.0
    assert snapshot._cost("s1", -3)["usd"] == 0.0


def test_a_session_past_midnight_counts_only_todays_part(env):
    status.publish("mizan", {"session": "old", "cost_usd": 30.0, "date": "2000-01-01"}, "old")
    assert snapshot.day_start(status.read("mizan", "old")) == 30.0
    snapshot.build({"session": "old", "cwd": str(env), "cost": {"usd": 32.0}}, publish=True)
    published = status.read("mizan", "old")
    assert published["cost_day_start"] == 30.0 and published["date"] == snapshot.today()
    assert snapshot._cost("s1", 1.0)["today_usd"] == 3.0  # 2 from "old" today, 1 from s1


def test_mizan_shows_only_proofs_in_itqans_own_folder(env, repo):
    fake = env / "elsewhere" / "latest.json"
    fake.parent.mkdir()
    fake.write_text(json.dumps({"schema": family.PROOF_SCHEMA, "checks": [{"name": "x", "passed": True}]}))
    status.publish("itqan", {"proofs": {str(repo): str(fake)}})
    assert family.proof(str(repo)) == {}


def test_proof_older_than_head_says_so():
    proof = {"checks": [{"name": "t", "passed": True, "seconds": 1}], "commit": "abc1234", "created": "x"}
    assert "earlier commit" in render.sections_text(render.proof_view(proof, "en", "def5678000"))
    assert "earlier commit" not in render.sections_text(render.proof_view(proof, "en", "abc1234999"))


def test_proof_redacts_assignments_and_url_passwords():
    sys.path.insert(0, str(PLUGINS / "itqan" / "scripts"))
    import itqan_proof

    text = itqan_proof.redact("DB_PASSWORD=hunter2 url postgres://u:s3cret@db/x AWS_SECRET_ACCESS_KEY: abc")
    assert "hunter2" not in text and "s3cret" not in text and "abc" not in text


def test_hafiz_save_follows_a_moved_config_folder(repo, env, monkeypatch):
    moved = env / "home" / ".config" / "claude"
    path = moved / "projects" / "p" / "s1.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"type": "user", "message": {"role": "user", "content": "hi"}}) + "\n")
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(moved))
    done = run("handoff", stdin={"session": "s1", "transcript": str(path), "cwd": str(repo)}, cwd=repo)
    assert json.loads(done.stdout)["saved"] is True


def test_mod_resets_on_every_session_end():
    block = MOD[MOD.index("on('session.end'"):]
    block = block[:block.index("return next(e)")]
    assert "e.reason" not in block and "update($, tasks, () => [])" in block
