"""One guard and one consent for the family's paid background model calls (#45)."""
from __future__ import annotations

import importlib.util
import json
import os
import stat
import subprocess
import sys
import textwrap

import pytest
from conftest import PLUGINS, REPO

spec = importlib.util.spec_from_file_location("nexika_background", REPO / "common" / "background.py")
background = importlib.util.module_from_spec(spec)
spec.loader.exec_module(background)

# The tool guards (haris, and itqan's guard when haris is off) keep the family safe: a background
# call runs with no tools, so they never fire there, and NEXIKA_BACKGROUND=1 set by hand must not
# switch a guard off.
GUARDS = {("haris", "PreToolUse"), ("haris", "PostToolUse"), ("itqan", "PreToolUse")}


def hook_commands():
    for path in sorted(PLUGINS.glob("*/hooks/hooks.json")):
        plugin = path.parent.parent.name
        for event, groups in json.loads(path.read_text())["hooks"].items():
            for group in groups:
                for item in group.get("hooks", []):
                    if (plugin, event) not in GUARDS:
                        yield pytest.param(plugin, event, group.get("matcher", ""), item["command"],
                                           id=f"{plugin}-{event}-{item['command'].split()[-1]}")


def files_under(*roots):
    return {str(p) for root in roots for p in root.rglob("*")}


@pytest.mark.parametrize("plugin,event,matcher,command", list(hook_commands()))
def test_every_hook_is_silent_inside_a_background_call(tmp_path, plugin, event, matcher, command):
    home, cwd = tmp_path / "home", tmp_path / "proj"
    home.mkdir()
    cwd.mkdir()
    transcript = tmp_path / "t.jsonl"
    line = {"type": "user", "message": {"role": "user", "content": "no, use pnpm"}}
    transcript.write_text(json.dumps(line) + "\n")
    tool = (matcher.split("|")[0] if matcher not in ("", "*") else "Bash")
    payload = {"hook_event_name": event, "session_id": "bg-session-1", "transcript_path": str(transcript),
               "cwd": str(cwd), "source": "startup", "prompt": "no, we use pnpm here, teach me",
               "tool_name": tool, "tool_input": {"command": "rm -rf build", "file_path": str(cwd / "a.md"),
                                                 "content": "Hello — world", "skill": "x"},
               "tool_response": {"success": True}}
    env = {"PATH": os.environ["PATH"], "HOME": str(home), "NEXIKA_BACKGROUND": "1",
           "CLAUDE_PLUGIN_ROOT": str(PLUGINS / plugin), "CLAUDE_PROJECT_DIR": str(cwd)}
    before = files_under(home, cwd)
    res = subprocess.run(command.replace("${CLAUDE_PLUGIN_ROOT}", str(PLUGINS / plugin)), shell=True,
                         input=json.dumps(payload), capture_output=True, text=True, cwd=cwd, env=env,
                         timeout=30)
    assert res.returncode == 0, res.stderr
    assert res.stdout.strip() == "", f"{plugin} {event} spoke inside a background call"
    assert files_under(home, cwd) == before, f"{plugin} {event} wrote files inside a background call"


# ---------------------------------------------------------------- the shared module


def test_setting_defaults_to_ask_and_is_stored_once_for_the_family(nexika_home):
    assert background.setting() == "ask"
    assert not background.allowed() and background.allowed(asked=True)
    background.set_setting("on")
    assert background.allowed()
    background.set_setting("off")
    assert not background.allowed(asked=True)
    assert json.loads((nexika_home / "settings.json").read_text()) == {"background_calls": "off",
                                                                        "schema": "nexika.settings/1"}
    with pytest.raises(ValueError):
        background.set_setting("maybe")


def test_calls_are_counted(nexika_home, capsys):
    background.record("prof", "auto-report", "sonnet")
    background.record("prof", "auto-report", "sonnet", ran=False)
    background.record("hafiz", "summary", "opus")
    assert background.counts() == {"prof": {"ran": 1, "skipped": 1}, "hafiz": {"ran": 1, "skipped": 0}}
    assert background.main(["background.py", "status"]) == 0
    out = capsys.readouterr().out
    assert "ask" in out and "- prof: 1 ran, 1 skipped" in out
    assert stat.S_IMODE((nexika_home / "background.jsonl").stat().st_mode) == 0o600


def test_child_env_marks_the_call():
    assert background.child_env({"X": "1"})["NEXIKA_BACKGROUND"] == "1"


# ---------------------------------------------------------------- prof


def tutoring(store, tmp_path):
    lines = [{"type": "user", "message": {"role": "user", "content":
              "<command-name>/prof:learn</command-name><command-args>loops</command-args>"}}]
    lines += [{"type": "user", "message": {"role": "user", "content": t}} for t in ("a", "b", "bye")]
    path = tmp_path / "t.jsonl"
    path.write_text("\n".join(json.dumps(x) for x in lines) + "\n")
    return {"session_id": "abcd1234zz", "transcript_path": str(path)}


@pytest.mark.parametrize("family,prof_answer,runs", [
    ("ask", True, True), ("on", None, True), ("off", True, False), ("on", False, False),
    ("ask", None, False)])
def test_prof_report_follows_the_family_setting(store, tmp_path, monkeypatch, family, prof_answer, runs):
    calls = []
    monkeypatch.setattr(store.subprocess, "Popen", lambda *a, **kw: calls.append(kw))
    background.set_setting(family)
    if prof_answer is not None:
        store.set_auto_report(prof_answer)
    store.session_end(tutoring(store, tmp_path))
    assert len(calls) == int(runs)
    if runs:
        assert calls[0]["env"]["NEXIKA_BACKGROUND"] == "1"


def test_prof_report_call_is_marked_and_counted(store, monkeypatch):
    seen = {}

    def run(cmd, stdin, **kw):
        seen.update(kw)
        return subprocess.CompletedProcess(cmd, 0, stdout="## Concept checklist\n", stderr="")

    monkeypatch.setattr(store.shutil, "which", lambda name: "/fake/claude")
    monkeypatch.setattr(store.subprocess, "run", run)
    store.TMP.mkdir(parents=True)
    convo = store.TMP / "abcd1234.txt"
    convo.write_text("LEARNER: hi")
    store.write_auto_report("abcd1234zz", convo)
    assert seen["env"]["NEXIKA_BACKGROUND"] == "1"
    assert background.counts()["prof"]["ran"] == 1


def test_prof_hooks_exit_inside_a_background_call(store, monkeypatch, capsys):
    monkeypatch.setenv("NEXIKA_BACKGROUND", "1")
    store.session_start({"session_id": "s1"})
    assert capsys.readouterr().out == ""


# ---------------------------------------------------------------- itqan


@pytest.fixture
def learn(tmp_path, monkeypatch):
    monkeypatch.setenv("ITQAN_HOME", str(tmp_path / "itqan-home"))
    for name in ("ITQAN_LEARN", "ITQAN_LEARNING"):
        monkeypatch.delenv(name, raising=False)
    path = PLUGINS / "itqan" / "scripts" / "itqan_learn.py"
    spec = importlib.util.spec_from_file_location("itqan_learn", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("family,runs", [("ask", False), ("off", False), ("on", True)])
def test_itqan_extraction_needs_consent(learn, tmp_path, monkeypatch, family, runs):
    root = tmp_path / "shop"
    root.mkdir()
    calls = []
    monkeypatch.setattr(learn, "project_root", lambda cwd: root)
    monkeypatch.setattr(learn.subprocess, "Popen", lambda *a, **kw: calls.append(kw))
    background.set_setting(family)
    transcript = tmp_path / "t.jsonl"
    transcript.write_text("\n".join(json.dumps(x) for x in [
        {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": "npm"}]}},
        {"type": "user", "message": {"role": "user", "content": "no, we use pnpm"}}]) + "\n")
    learn.hook_signal({"prompt": "no, we use pnpm", "session_id": "sess-1234", "cwd": str(root)})
    learn.hook_extract({"session_id": "sess-1234", "transcript_path": str(transcript), "cwd": str(root)})
    assert len(calls) == int(runs)
    if runs:
        assert calls[0]["env"]["NEXIKA_BACKGROUND"] == "1"
    else:
        assert background.counts()["itqan"] == {"ran": 0, "skipped": 1}


def test_itqan_extract_call_is_marked_and_counted(learn, tmp_path, monkeypatch):
    seen = {}

    def run(cmd, stdin, **kw):
        seen.update(kw)
        return subprocess.CompletedProcess(cmd, 0, stdout="[]", stderr="")

    monkeypatch.setattr(learn.shutil, "which", lambda name: "/fake/claude")
    monkeypatch.setattr(learn.subprocess, "run", run)
    payload = tmp_path / "p.txt"
    payload.write_text("x")
    root = tmp_path / "shop"
    root.mkdir()
    assert learn.run_extract("sess", payload, root) == 0
    assert seen["env"]["NEXIKA_BACKGROUND"] == "1"
    assert background.counts()["itqan"]["ran"] == 1


# ---------------------------------------------------------------- hafiz


@pytest.fixture
def summary(tmp_path, monkeypatch):
    monkeypatch.setenv("HAFIZ_HOME", str(tmp_path / "hafiz-home"))
    monkeypatch.delenv("HAFIZ", raising=False)
    root = str(PLUGINS / "hafiz")
    if root not in sys.path:
        sys.path.insert(0, root)
    from hafiz import summary
    return summary


def test_hafiz_summary_call_is_marked_and_counted(summary, tmp_path, monkeypatch):
    record = tmp_path / "env.json"
    script = tmp_path / "claude"
    script.write_text(textwrap.dedent(f"""\
        #!{sys.executable}
        import json, os, sys
        sys.stdin.read()
        json.dump(dict(os.environ), open({str(record)!r}, "w"))
        print("summary")
        """))
    script.chmod(0o755)
    monkeypatch.setenv("HAFIZ_CLAUDE", str(script))
    assert summary.call_claude("hi", "sonnet") == ("summary\n", "")
    env = json.loads(record.read_text())
    assert env["NEXIKA_BACKGROUND"] == "1" and env["HAFIZ"] == "off"
    assert background.counts()["hafiz"]["ran"] == 1


def test_hafiz_summary_respects_off(summary, tmp_path):
    background.set_setting("off")
    code, message = summary.run(tmp_path)
    assert code == 1 and "background_calls" in message and "on" in message


def test_itqan_asks_once_after_skipping(learn, capsys):
    hooks_path = PLUGINS / "itqan" / "scripts" / "itqan_hooks.py"
    spec = importlib.util.spec_from_file_location("itqan_hooks", hooks_path)
    hooks = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(hooks)
    hooks.session_start({"session_id": "s1"})
    assert "background" not in capsys.readouterr().out  # nothing skipped: nothing to ask
    background.record("itqan", "learn-extract", "sonnet", ran=False)
    hooks.session_start({"session_id": "s1"})
    out = capsys.readouterr().out
    assert "skipped learning from 1 session" in out and "background_calls" not in out
    assert "itqan_background.py on" in out
    background.set_setting("off")
    hooks.session_start({"session_id": "s1"})
    assert "skipped learning" not in capsys.readouterr().out  # answered: never ask again


@pytest.mark.parametrize("family,asks", [("ask", True), ("on", False), ("off", False)])
def test_prof_asks_only_while_nobody_answered(store, capsys, family, asks):
    background.set_setting(family)
    store.session_start({"session_id": "s1"})
    assert ("ask once" in capsys.readouterr().out) is asks
