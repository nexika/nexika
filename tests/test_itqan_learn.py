"""itqan v0.2: learning from corrections, the rules file, usage tracking and insights."""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys

import pytest
from conftest import PLUGINS, _git

SCRIPTS = PLUGINS / "itqan" / "scripts"


@pytest.fixture
def learn(tmp_path, monkeypatch):
    monkeypatch.setenv("ITQAN_HOME", str(tmp_path / "itqan-home"))
    for name in ("ITQAN_LEARN", "ITQAN_LEARNING"):
        monkeypatch.delenv(name, raising=False)
    spec = importlib.util.spec_from_file_location("itqan_learn", SCRIPTS / "itqan_learn.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / "shop"
    root.mkdir()
    (root / "app.py").write_text("x = 1\n")
    _git(root, "init", "-q", "-b", "main")
    return root.resolve()


def lesson(id_, rule="Use pnpm, not npm.", quote="no, we use pnpm", kind="convention"):
    return {"id": id_, "rule": rule, "kind": kind, "quote": quote}


# ---------------------------------------------------------------- correction filter


@pytest.mark.parametrize("text", [
    "no, we use file-scoped namespaces", "Don't add comments everywhere", "you forgot to run the tests",
    "why did you change that?", "I told you to use pnpm", "that's not how we name tests",
    "لا، استخدم async هنا", "غلط، الاسم خطأ", "قلت لك استخدم pnpm",
])
def test_corrections_are_flagged(learn, text):
    assert learn.CORRECTION.search(text)


@pytest.mark.parametrize("text", [
    "please add a login page", "nothing else to add", "write the notes", "knowledge base",
    "make it always-on", "شكرا هذا ممتاز",
])
def test_normal_messages_are_not_flagged(learn, text):
    assert not learn.CORRECTION.search(text)


# ---------------------------------------------------------------- hooks


def test_signal_hook_stores_corrections_only(learn, repo):
    learn.hook_signal({"prompt": "no, we use pnpm", "session_id": "s1", "cwd": str(repo)})
    learn.hook_signal({"prompt": "add a cart page", "session_id": "s1", "cwd": str(repo)})
    learn.hook_signal({"prompt": "/itqan:learn no", "session_id": "s1", "cwd": str(repo)})
    signals = learn.read_jsonl(learn.data_home() / "signals.jsonl")
    assert [s["prompt"] for s in signals] == ["no, we use pnpm"]


def test_learning_can_be_turned_off(learn, repo, monkeypatch):
    (repo / ".itqan.json").write_text('{"learn": {"mode": "off"}}')
    learn.hook_signal({"prompt": "no, wrong", "session_id": "s1", "cwd": str(repo)})
    (repo / ".itqan.json").unlink()
    monkeypatch.setenv("ITQAN_LEARN", "off")
    learn.hook_signal({"prompt": "no, wrong", "session_id": "s1", "cwd": str(repo)})
    assert not (learn.data_home() / "signals.jsonl").exists()


def test_usage_hook_logs_skills_and_agents(learn, repo):
    learn.hook_usage({"tool_name": "Skill", "tool_input": {"skill": "itqan:review"}, "cwd": str(repo)})
    learn.hook_usage({"tool_name": "Task", "tool_input": {"subagent_type": "itqan:planner"},
                      "cwd": str(repo)})
    learn.hook_usage({"tool_name": "Agent", "tool_input": {}, "cwd": str(repo)})
    usage = learn.read_jsonl(learn.data_home() / "usage.jsonl")
    assert [(u["kind"], u["name"]) for u in usage] == [("skill", "itqan:review"), ("agent", "itqan:planner")]


def write_transcript(path, rows):
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    return path


def msg(kind, content, **extra):
    return {"type": kind, "message": {"content": content}, **extra}


def test_correction_exchanges_pair_with_preceding_assistant_text(learn, tmp_path):
    path = write_transcript(tmp_path / "t.jsonl", [
        msg("user", "add tests"),
        msg("assistant", [{"type": "text", "text": "Added tests with npm test."}]),
        msg("user", [{"type": "tool_result", "content": "ok"}]),
        msg("user", "<system-reminder>no</system-reminder>"),
        msg("user", "no, meta", isMeta=True),
        msg("user", "/itqan:learn"),
        msg("user", "no, we use pnpm here"),
    ])
    assert learn.correction_exchanges(path) == [("Added tests with npm test.", "no, we use pnpm here")]


def test_extract_only_runs_for_sessions_with_signals(learn, repo, tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(learn, "project_root", lambda cwd: repo)  # git also uses Popen
    monkeypatch.setattr(learn.subprocess, "Popen", lambda *a, **kw: calls.append((a, kw)))
    transcript = write_transcript(tmp_path / "t.jsonl", [
        msg("assistant", [{"type": "text", "text": "Used npm."}]), msg("user", "no, we use pnpm")])
    event = {"session_id": "sess-1234", "transcript_path": str(transcript), "cwd": str(repo)}

    learn.hook_extract(event)
    assert calls == []  # no signal recorded for this session

    learn.hook_signal({"prompt": "no, we use pnpm", "session_id": "sess-1234", "cwd": str(repo)})
    learn.hook_extract(event)
    args, kwargs = calls[0]
    payload = learn.data_home() / "tmp" / "sess-123.txt"
    assert args[0][-4:] == ["run-extract", "sess-1234", str(payload), str(repo)]
    assert kwargs["env"]["ITQAN_LEARNING"] == "1" and kwargs["start_new_session"] is True
    assert "ASSISTANT: Used npm.\nUSER: no, we use pnpm" in payload.read_text()


# ---------------------------------------------------------------- parsing and merging


def test_parse_lessons_tolerates_prose_and_normalizes(learn):
    out = 'Sure:\n[{"id": "Use PNPM!", "rule": "Use pnpm.", "kind": "weird", "quote": "q"}, {"rule": ""}]\n'
    expected = {"id": "use-pnpm", "rule": "Use pnpm.", "kind": "preference", "quote": "q"}
    assert learn.parse_lessons(out) == [expected]
    assert learn.parse_lessons("no json here") == []
    assert learn.parse_lessons("[not json]") == []


def test_lesson_lifecycle(learn):
    store = {"lessons": {}}
    learn.merge_lessons(store, [lesson("use-pnpm")])
    assert store["lessons"]["use-pnpm"]["status"] == "candidate"
    learn.merge_lessons(store, [lesson("use-pnpm", quote="pnpm please")])
    assert store["lessons"]["use-pnpm"]["status"] == "proposed"

    store["lessons"]["use-pnpm"]["status"] = "approved"
    learn.merge_lessons(store, [lesson("use-pnpm", quote="again: pnpm!")])
    assert [v["quote"] for v in store["lessons"]["use-pnpm"]["violations"]] == ["again: pnpm!"]

    store["lessons"]["use-pnpm"]["status"] = "rejected"
    learn.merge_lessons(store, [lesson("use-pnpm")])
    assert len(store["lessons"]["use-pnpm"]["evidence"]) == 2


def test_run_extract_with_fake_claude(learn, repo, monkeypatch):
    store = {"root": str(repo), "lessons": {}}
    learn.merge_lessons(store, [lesson("use-pnpm")])
    learn.save_store(repo, store)
    payload = learn.data_home() / "p.txt"
    payload.write_text("ASSISTANT: npm\nUSER: no, pnpm")
    seen = {}

    def run(cmd, stdin, **kw):
        seen["prompt"], seen["stdin"] = cmd[2], stdin.read()
        out = json.dumps([lesson("use-pnpm", quote="no, pnpm"), lesson("tests-first", "Write tests first.")])
        return subprocess.CompletedProcess(cmd, 0, stdout=out, stderr="")

    monkeypatch.setattr(learn.shutil, "which", lambda name: "/fake/claude")
    monkeypatch.setattr(learn.subprocess, "run", run)
    assert learn.run_extract("sess", payload, repo) == 0
    lessons = learn.load_store(repo)["lessons"]
    assert lessons["use-pnpm"]["status"] == "proposed" and lessons["tests-first"]["status"] == "candidate"
    assert "- use-pnpm: Use pnpm, not npm. (candidate)" in seen["prompt"]
    assert seen["stdin"].endswith("USER: no, pnpm") and not payload.exists()


def test_run_extract_failure_changes_nothing(learn, repo, monkeypatch):
    payload = learn.data_home() / "p.txt"
    payload.parent.mkdir(parents=True)
    payload.write_text("x")
    monkeypatch.setattr(learn.shutil, "which", lambda name: "/fake/claude")
    failed = subprocess.CompletedProcess([], 1, stdout="", stderr="boom")
    monkeypatch.setattr(learn.subprocess, "run", lambda cmd, stdin, **kw: failed)
    assert learn.run_extract("sess", payload, repo) == 1
    assert learn.load_store(repo)["lessons"] == {}


# ---------------------------------------------------------------- approval and the rules file


def proposed_store(learn, repo, *ids):
    store = {"root": str(repo), "lessons": {}}
    for id_ in ids:
        learn.merge_lessons(store, [lesson(id_, rule=f"Rule {id_}.")] * 2)
    learn.save_store(repo, store)


def test_approve_writes_rules_file_and_session_note(learn, repo):
    proposed_store(learn, repo, "use-pnpm", "tests-first")
    assert "Proposed rules (2)" in learn.cmd_proposals(repo)
    assert "2 rule proposal(s)" in learn.session_note(repo)

    out = learn.cmd_approve(repo, "use-pnpm", "Always use pnpm.")
    assert "Approved [use-pnpm] Always use pnpm." in out
    text = (repo / ".itqan" / "rules.md").read_text()
    assert f"{learn.RULES_START}\n- [use-pnpm] Always use pnpm.\n{learn.RULES_END}" in text
    note = learn.session_note(repo)
    assert "- Always use pnpm." in note and "1 rule proposal(s)" in note
    assert "No lesson 'nope'" in learn.cmd_approve(repo, "nope", None)


def test_rules_file_edits_win_and_deleted_lines_retire(learn, repo):
    proposed_store(learn, repo, "use-pnpm", "tests-first")
    learn.cmd_approve(repo, "use-pnpm", None)
    learn.cmd_approve(repo, "tests-first", None)
    path = repo / ".itqan" / "rules.md"
    text = path.read_text().replace("Rule use-pnpm.", "Use pnpm for every script.")
    text = text.replace("- [tests-first] Rule tests-first.\n", "")
    path.write_text(text + "\n- Hand-written rule kept as is.\n")

    store = learn.load_store(repo)
    learn.sync_from_file(repo, store)
    assert store["lessons"]["use-pnpm"]["rule"] == "Use pnpm for every script."
    assert store["lessons"]["tests-first"]["status"] == "retired"
    assert "- Hand-written rule kept as is." in learn.cmd_rules(repo)


def test_rewriting_keeps_text_outside_the_markers(learn, repo):
    proposed_store(learn, repo, "a", "b")
    learn.cmd_approve(repo, "a", None)
    path = repo / ".itqan" / "rules.md"
    path.write_text("# My notes\n\n" + path.read_text() + "\nFooter.\n")
    learn.cmd_approve(repo, "b", None)
    text = path.read_text()
    assert text.startswith("# My notes") and text.rstrip().endswith("Footer.")
    assert "- [a] Rule a.\n- [b] Rule b." in text


def test_reject_removes_an_approved_rule(learn, repo):
    proposed_store(learn, repo, "use-pnpm")
    learn.cmd_approve(repo, "use-pnpm", None)
    assert "will not be proposed again" in learn.cmd_reject(repo, "use-pnpm")
    assert "use-pnpm" not in (repo / ".itqan" / "rules.md").read_text()


# ---------------------------------------------------------------- insights


def test_insights_report(learn, repo):
    for name, kind in (("itqan:review", "skill"), ("itqan:review", "skill"), ("ecc:tdd", "skill"),
                       ("itqan:code-reviewer", "agent")):
        learn._append("usage.jsonl", {"ts": learn._now(), "cwd": str(repo), "kind": kind, "name": name})
    learn._append("usage.jsonl", {"ts": learn._now(), "cwd": "/elsewhere", "kind": "skill", "name": "x:y"})
    learn._append("guard.jsonl", {"ts": learn._now(), "decision": "deny", "rule": "force-push-protected"})
    learn.hook_signal({"prompt": "no, wrong", "session_id": "s", "cwd": str(repo)})
    proposed_store(learn, repo, "use-pnpm", "tests-first")
    learn.cmd_approve(repo, "use-pnpm", None)
    learn.cmd_approve(repo, "tests-first", None)
    store = learn.load_store(repo)
    learn.merge_lessons(store, [lesson("tests-first", quote="you forgot the tests again")])
    learn.save_store(repo, store)

    out = learn.cmd_insights(repo)
    assert "workflows: itqan:review 2" in out
    assert "agents: itqan:code-reviewer 1" in out
    assert "other skills used: ecc:tdd 1" in out and "x:y" not in out
    assert "guard (all projects): 1 refused, 0 asked" in out
    assert "corrections captured: 1" in out
    assert "rules: 2 approved" in out
    assert "[use-pnpm] 0d old: working" in out
    assert "[tests-first] 0d old: corrected again 1x" in out and "you forgot the tests again" in out


# ---------------------------------------------------------------- end to end through the real scripts


def run_script(name, args, cwd, home, stdin=""):
    return subprocess.run([sys.executable, str(SCRIPTS / name), *args], cwd=cwd, input=stdin,
                          capture_output=True, text=True, env={**os.environ, "ITQAN_HOME": str(home)})


def test_cli_and_session_note(learn, repo):
    home = learn.data_home()
    proposed_store(learn, repo, "use-pnpm")
    res = run_script("itqan_learn.py", ["approve", "use-pnpm", "Use", "pnpm."], repo, home)
    assert res.returncode == 0 and "Approved [use-pnpm] Use pnpm." in res.stdout

    note = run_script("itqan_hooks.py", ["session-start"], repo, home,
                      json.dumps({"cwd": str(repo), "session_id": "s1"})).stdout
    assert "Project rules (.itqan/rules.md), follow them:\n- Use pnpm." in note
    helper = SCRIPTS / "itqan_learn.py"
    assert f"itqan helper (for /itqan:learn and /itqan:insights): python3 {helper}" in note


def test_hook_commands_never_fail(tmp_path):
    for cmd in ("signal", "usage", "extract"):
        res = run_script("itqan_learn.py", [cmd], tmp_path, tmp_path / "h", "{broken")
        assert res.returncode == 0 and res.stdout == ""


# ---------------------------------------------------------------- private storage (#23)


def test_signal_redacts_secrets_and_is_private(learn, repo):
    prompt = "no, use the key AKIAIOSFODNN7EXAMPLE and ghp_" + "a" * 36 + " instead"
    learn.hook_signal({"prompt": prompt, "cwd": str(repo), "session_id": "s1"})
    path = learn.data_home() / "signals.jsonl"
    text = path.read_text()
    assert "AKIAIOSFODNN7EXAMPLE" not in text and "ghp_" not in text
    assert "[secret]" in text
    assert path.stat().st_mode & 0o777 == 0o600
    assert learn.data_home().stat().st_mode & 0o777 == 0o700


def test_usage_and_guard_logs_are_private(learn, repo):
    learn.hook_usage({"tool_name": "Skill", "tool_input": {"skill": "itqan:ship"}, "cwd": str(repo)})
    assert (learn.data_home() / "usage.jsonl").stat().st_mode & 0o777 == 0o600
    guard = load_script("itqan_guard")
    event = {"session_id": "s1", "tool_input": {"command": "curl -H 'Authorization: Bearer "
                                                            + "x" * 30 + "' https://x"}}
    guard.log_decision(event, ("ask", "net", "why"))
    path = learn.data_home() / "guard.jsonl"
    assert path.stat().st_mode & 0o777 == 0o600
    assert "x" * 30 not in path.read_text()


def test_jsonl_files_rotate(learn, repo, monkeypatch):
    monkeypatch.setattr(learn.itqan_files, "LIMIT", 200)
    for i in range(20):
        learn.hook_usage({"tool_name": "Skill", "tool_input": {"skill": f"s{i}"}, "cwd": str(repo)})
    home = learn.data_home()
    assert (home / "usage.1.jsonl").exists()
    assert (home / "usage.jsonl").stat().st_size <= 400
    names = [u["name"] for u in learn.read_jsonl(home / "usage.jsonl")]
    assert names[-1] == "s19" and "s0" not in names


def load_script(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------- branches (#24)


def test_approving_on_another_branch_keeps_rules_approved_elsewhere(learn, repo):
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "Test")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "init")
    proposed_store(learn, repo, "a", "b", "c", "d")

    def approve(lid):
        learn.cmd_approve(repo, lid, None)
        _git(repo, "add", "-A")
        _git(repo, "commit", "-qm", f"approve {lid}")

    approve("a")
    _git(repo, "branch", "old")
    approve("b")
    _git(repo, "checkout", "-q", "old")
    approve("c")
    _git(repo, "checkout", "-q", "main")
    approve("d")

    managed, _ = learn.read_rules_file(repo)
    assert list(managed) == ["a", "b", "d"]
    statuses = {k: v["status"] for k, v in learn.load_store(repo)["lessons"].items()}
    assert statuses == {"a": "approved", "b": "approved", "c": "approved", "d": "approved"}


def test_rules_the_store_does_not_know_are_never_rewritten(learn, repo):
    proposed_store(learn, repo, "a")
    path = repo / ".itqan" / "rules.md"
    path.parent.mkdir()
    path.write_text(f"{learn.RULES_START}\n- [from-a-teammate] Keep it.\n{learn.RULES_END}\n")
    learn.cmd_approve(repo, "a", None)
    managed, _ = learn.read_rules_file(repo)
    assert managed == {"from-a-teammate": "Keep it.", "a": "Rule a."}


# ---------------------------------------------------------------- what learning and the guard cost (#76)


def test_extraction_cost_is_recorded_and_reported(learn, repo, monkeypatch):
    payload = learn.data_home() / "p.txt"
    payload.parent.mkdir(parents=True, exist_ok=True)
    payload.write_text("ASSISTANT: npm\nUSER: no, pnpm")
    answer = json.dumps({"type": "result", "result": json.dumps([lesson("use-pnpm")]),
                         "total_cost_usd": 0.0123})
    done = subprocess.CompletedProcess([], 0, stdout=answer, stderr="")
    monkeypatch.setattr(learn.shutil, "which", lambda name: "/fake/claude")
    monkeypatch.setattr(learn.subprocess, "run", lambda cmd, stdin, **kw: done)
    assert learn.run_extract("sess", payload, repo) == 0
    assert learn.load_store(repo)["lessons"]["use-pnpm"]["status"] == "candidate"
    out = learn.cmd_insights(repo)
    assert "learning: 1 extraction(s), $0.01" in out


def test_insights_report_the_guard_false_positive_rate(learn, repo):
    for asked, approved in ((2, 1), (2, 2)):
        learn._append("sessions.jsonl", {"ts": learn._now(), "session": "s", "deny": 0, "ask": asked,
                                         "ask_approved": approved, "rules": []})
    assert "asks you approved: 3 of 4 (75%)" in learn.cmd_insights(repo)
