"""Each tool call waited about 300 ms on hooks (#50): a hook with nothing to do leaves before
loading the heavy parts, and siyaq keeps its compiled patterns and file list."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time

import pytest
from conftest import PLUGINS


def run_hook(tmp_path, argv, payload):
    """(stdout, modules imported) for one hook run as Claude Code runs it."""
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    env = {"PATH": os.environ["PATH"], "HOME": str(home)}
    res = subprocess.run([sys.executable, "-X", "importtime", *argv], input=json.dumps(payload),
                         capture_output=True, text=True, cwd=tmp_path, env=env, timeout=30)
    assert res.returncode == 0, res.stderr
    modules = {line.split("|")[-1].strip() for line in res.stderr.splitlines()
               if line.startswith("import time:")}
    return res.stdout, modules


HARIS = str(PLUGINS / "haris" / "bin" / "haris")
CLASSIFIER = {"haris.classify", "haris.policy", "haris.powershell", "haris.shell"}


@pytest.mark.parametrize("hook,payload", [
    ("pre-tool-use", {"tool_name": "TodoWrite", "tool_input": {"todos": []}}),
    ("pre-tool-use", {"tool_name": "Task", "tool_input": {"prompt": "rm -rf ~"}}),
    ("post-tool-use", {"tool_name": "Read", "tool_input": {"file_path": "a.py"},
                       "tool_response": "def f():\n    return 1\n"}),
    ("post-tool-use", {"tool_name": "Edit", "tool_input": {"file_path": "a.py"}}),
    ("session-start", {"source": "startup"}),
    ("user-prompt-submit", {"prompt": "fix the login bug"}),
])
def test_haris_leaves_the_classifier_alone_when_there_is_nothing_to_classify(tmp_path, hook, payload):
    payload = {"session_id": "speed-1", "cwd": str(tmp_path), **payload}
    out, modules = run_hook(tmp_path, [HARIS, "hook", hook], payload)
    assert not CLASSIFIER & modules, f"{hook} loaded {sorted(CLASSIFIER & modules)}"
    assert "argparse" not in modules
    if hook != "session-start":
        assert out == ""


def test_haris_still_guards_the_calls_it_checks(tmp_path):
    payload = {"session_id": "speed-1", "cwd": str(tmp_path), "tool_name": "Bash",
               "tool_input": {"command": "rm -rf ~"}}
    out, modules = run_hook(tmp_path, [HARIS, "hook", "pre-tool-use"], payload)
    assert json.loads(out)["hookSpecificOutput"]["permissionDecision"] == "deny"
    payload = {"session_id": "speed-1", "cwd": str(tmp_path), "tool_name": "Read",
               "tool_input": {"file_path": str(tmp_path / "home" / ".ssh" / "id_rsa")}}
    out, _ = run_hook(tmp_path, [HARIS, "hook", "pre-tool-use"], payload)
    assert json.loads(out)["hookSpecificOutput"]["permissionDecision"] in ("ask", "deny")
    payload = {"session_id": "speed-1", "cwd": str(tmp_path), "tool_name": "WebFetch",
               "tool_input": {"url": "http://169.254.169.254/latest/meta-data"}}
    out, _ = run_hook(tmp_path, [HARIS, "hook", "pre-tool-use"], payload)
    assert json.loads(out)["hookSpecificOutput"]["permissionDecision"] in ("ask", "deny")


PARSER = {"haris.classify", "haris.shell", "haris.powershell"}


@pytest.mark.parametrize("tool,tool_input", [
    ("Read", {"file_path": "a.py"}),
    ("Glob", {"pattern": "*.py"}),
    ("Edit", {"file_path": "a.py", "old_string": "x = 1", "new_string": "x = 2"}),
    ("Write", {"file_path": "b.py", "content": "y = 1\n"}),
    ("MultiEdit", {"file_path": "a.py", "edits": [{"old_string": "x", "new_string": "z"}]}),
    ("WebFetch", {"url": "https://example.com/"}),
])
def test_haris_checks_file_and_web_calls_without_the_command_parser(tmp_path, tool, tool_input):
    """Read, Edit and Write only need the path helpers (#102): the shell parser stays unloaded."""
    (tmp_path / "a.py").write_text("x = 1\n")
    payload = {"session_id": "speed-1", "cwd": str(tmp_path), "tool_name": tool, "tool_input": tool_input}
    _, modules = run_hook(tmp_path, [HARIS, "hook", "pre-tool-use"], payload)
    assert not PARSER & modules, f"{tool} loaded {sorted(PARSER & modules)}"


def test_haris_classifier_uses_the_light_path_helpers():
    sys.path.insert(0, str(PLUGINS / "haris"))
    try:
        from haris import classify, targets
    finally:
        sys.path.remove(str(PLUGINS / "haris"))
    for name in ("Ctx", "Finding", "read_paths", "write_paths", "targets", "arg"):
        assert getattr(classify, name) is getattr(targets, name), name


def test_haris_tool_list_matches_what_the_policy_checks():
    sys.path.insert(0, str(PLUGINS / "haris"))
    try:
        from haris import config, policy
    finally:
        sys.path.remove(str(PLUGINS / "haris"))
    risky = {"command": "rm -rf ~", "file_path": "~/.ssh/id_rsa", "url": "http://169.254.169.254/"}
    for tool in ("TodoWrite", "Task", "Agent", "Skill", "AskUserQuestion", "ExitPlanMode", "SlashCommand"):
        assert not config.checked(tool)
        decision = policy.decide({"tool_name": tool, "tool_input": risky, "cwd": "/tmp"},
                                 policy.effective_config("/tmp"))
        assert decision.verdict == "pass", tool
    for tool in ("Bash", "PowerShell", "Read", "Glob", "Grep", "LS", "NotebookRead", "Edit", "Write",
                 "MultiEdit", "NotebookEdit", "WebFetch", "WebSearch", "mcp__github__merge_pull_request"):
        assert config.checked(tool), tool


BAYAN = str(PLUGINS / "bayan" / "bin" / "bayan")
BAYAN_HEAVY = {"bayan.rules", "bayan.check", "bayan.clean", "bayan.prose"}


@pytest.mark.parametrize("hook,payload", [
    ("pre-bash", {"tool_name": "Bash", "tool_input": {"command": "ls -la && pytest -q"}}),
    ("post-write", {"tool_name": "Write", "tool_input": {"file_path": "app.py", "content": "x = 1\n"}}),
])
def test_bayan_leaves_early_when_there_is_nothing_to_clean(tmp_path, hook, payload):
    (tmp_path / "app.py").write_text("x = 1\n")
    out, modules = run_hook(tmp_path, [BAYAN, "hook", hook], {"cwd": str(tmp_path), **payload})
    assert out == "" and not BAYAN_HEAVY & modules, sorted(BAYAN_HEAVY & modules)


def test_bayan_still_checks_a_signed_commit(tmp_path):
    command = 'git commit -m "Fix\n\nCo-Authored-By: Claude <noreply@anthropic.com>"'
    out, _ = run_hook(tmp_path, [BAYAN, "hook", "pre-bash"],
                      {"cwd": str(tmp_path), "tool_name": "Bash", "tool_input": {"command": command}})
    assert "hookSpecificOutput" in json.loads(out)


def test_itqan_hooks_leave_secrets_unloaded_without_a_correction(tmp_path):
    script = str(PLUGINS / "itqan" / "scripts" / "itqan_learn.py")
    _, modules = run_hook(tmp_path, [script, "signal"], {"prompt": "add a login page", "cwd": str(tmp_path)})
    assert "itqan_secrets" not in modules
    _, modules = run_hook(tmp_path, [script, "usage"],
                          {"tool_name": "Skill", "tool_input": {"skill": "x"}, "cwd": str(tmp_path)})
    assert "itqan_secrets" not in modules


# ---------------------------------------------------------------- siyaq


@pytest.fixture
def idx(tmp_path, monkeypatch):
    monkeypatch.setenv("SIYAQ_HOME", str(tmp_path / "siyaq-home"))
    root = str(PLUGINS / "siyaq")
    if root not in sys.path:
        sys.path.insert(0, root)
    from siyaq import index
    return index


@pytest.fixture
def docs(tmp_path):
    root = tmp_path / "shop"
    (root / "docs").mkdir(parents=True)
    body = "Roll back with the previous tag and redeploy the service from the release page. " * 3
    (root / "docs" / "deploy.md").write_text("# Deployment\n\n## Rollback\n" + body + "\n")
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    return root


def test_siyaq_compiles_each_glob_once(idx):
    idx.glob_regex.cache_clear()
    for _ in range(3):
        idx.matches_any("src/a.py", ["docs/**/*.md", "**/README.md"])  # neither matches: both tried
    assert idx.glob_regex.cache_info().misses == 2


def test_siyaq_hooks_reuse_the_file_list(idx, docs, monkeypatch):
    calls = []
    real = idx.project_files
    monkeypatch.setattr(idx, "project_files", lambda root: calls.append(root) or real(root))
    idx.load(docs, max_age=30)
    idx.load(docs, max_age=30)
    assert len(calls) <= 2  # listed for the first build only; the second load reuses the list
    before = len(calls)
    idx.load(docs, max_age=30)
    assert len(calls) == before
    idx.load(docs)  # commands (index, match, stats) always list the files again
    assert len(calls) == before + 1


def test_siyaq_file_list_expires_and_follows_the_config(idx, docs, monkeypatch):
    idx.load(docs, max_age=30)
    calls = []
    real = idx.project_files
    monkeypatch.setattr(idx, "project_files", lambda root: calls.append(root) or real(root))
    (docs / ".siyaq.json").write_text(json.dumps({"exclude": ["docs/deploy.md"]}))
    assert idx.load(docs, max_age=30)["n"] == 0 and calls
    calls.clear()
    real_time = time.time
    monkeypatch.setattr(idx.time, "time", lambda: real_time() + 60)
    idx.load(docs, max_age=30)
    assert calls


def test_siyaq_sees_a_new_doc_written_through_claude(idx, docs, monkeypatch):
    from siyaq import hooks
    monkeypatch.setattr(idx, "project_root", lambda cwd: docs)
    assert idx.load(docs, max_age=30)["n"] == 1
    new = docs / "docs" / "orders.md"
    hooks.on_tool({"tool_name": "Write", "cwd": str(docs), "session_id": "s1",
                   "tool_input": {"file_path": str(new), "content": "x"}})
    new.write_text("# Orders\n\n## Discounts\n" + "Discounts apply to the cart total before tax and "
                   "shipping are added at checkout. " * 3 + "\n")
    assert idx.load(docs, max_age=30)["n"] == 2
