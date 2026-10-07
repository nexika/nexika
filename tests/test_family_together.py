"""The plugins installed together (#66): every hook of every plugin, fired as Claude Code fires them.

Each plugin has its own tests; the bugs of the review (#45 to #48) only showed with several plugins
installed. This module reads every plugin's hooks/hooks.json and runs, for one event, every hook
whose matcher fits, in one throwaway home, with a fake `claude` first on PATH so that no background
job can start a paid model call.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest
from conftest import PLUGINS, REPO, _git

HOOKED = {p.parent.parent.name: json.loads(p.read_text(encoding="utf-8"))
          for p in sorted(PLUGINS.glob("*/hooks/hooks.json"))}
DATA_HOMES = {"NEXIKA_STATUS_HOME", "CLAUDE_CONFIG_DIR", "HARIS", "HAFIZ", "ITQAN_LEARN",
              *(f"{name.upper()}_HOME" for name in HOOKED)}
GUARDS = {"prof": {"PROF_REPORTING": "1"}, "itqan": {"ITQAN_LEARNING": "1"}, "hafiz": {"HAFIZ": "off"}}
SESSION = "together-0001"
RANK = {"deny": 3, "ask": 2, "allow": 1}


@dataclass
class Outcome:
    plugin: str
    event: str
    code: int
    out: str
    err: str

    @property
    def decision(self) -> str | None:
        if self.code == 2:
            return "deny"
        try:
            data = json.loads(self.out)
        except ValueError:
            return None
        specific = (data.get("hookSpecificOutput") or {}) if isinstance(data, dict) else {}
        return specific.get("permissionDecision")


def _matches(matcher: str, tool: str) -> bool:
    return not matcher or matcher == "*" or not tool or re.fullmatch(matcher, tool) is not None


class Family:
    def __init__(self, base: Path):
        self.home = base / "home"
        self.project = base / "project"
        self.claude_log = base / "claude-calls.log"
        fake = base / "bin" / "claude"
        fake.parent.mkdir()
        fake.write_text(f"#!/bin/sh\necho \"$@\" >> {self.claude_log}\n")
        fake.chmod(0o755)
        (self.home / ".claude").mkdir(parents=True)
        self.project.mkdir()
        _git(self.project, "init", "-q", "-b", "main")
        _git(self.project, "config", "user.email", "t@example.com")
        _git(self.project, "config", "user.name", "Test")
        self.env = {k: v for k, v in os.environ.items() if k not in DATA_HOMES and not k.startswith("PROF_")}
        self.env.update({"HOME": str(self.home), "PATH": f"{fake.parent}{os.pathsep}{os.environ['PATH']}",
                         "HAFIZ_CLAUDE": str(fake), "MIZAN_OFFLINE": "1", "MIZAN_LANG": "en"})

    def data(self, plugin: str) -> Path:
        return self.home / ".claude" / "nexika" / plugin

    def fire(self, event: str, payload: dict | None = None, env: dict | None = None,
             cwd: Path | None = None, installed: set[str] | None = None) -> list[Outcome]:
        """Every plugin's hooks for this event (of the installed ones: all by default), one after
        another, as Claude Code would run them."""
        cwd = cwd or self.project
        payload = {"session_id": SESSION, "hook_event_name": event, "cwd": str(cwd),
                   "transcript_path": "", **(payload or {})}
        found = []
        for plugin, config in HOOKED.items():
            if installed is not None and plugin not in installed:
                continue
            for group in (config.get("hooks") or {}).get(event, []):
                if not _matches(group.get("matcher") or "", payload.get("tool_name", "")):
                    continue
                for hook in group["hooks"]:
                    root = str(PLUGINS / plugin)
                    command = hook["command"].replace("${CLAUDE_PLUGIN_ROOT}", root)
                    done = subprocess.run(command, shell=True, cwd=cwd, input=json.dumps(payload),
                                          capture_output=True, text=True, timeout=hook.get("timeout", 60),
                                          env={**self.env, "CLAUDE_PLUGIN_ROOT": root,
                                               "CLAUDE_PROJECT_DIR": str(cwd), **(env or {})})
                    found.append(Outcome(plugin, event, done.returncode, done.stdout.strip(), done.stderr))
        return found


def verdict(outcomes: list[Outcome]) -> tuple[str | None, set[str]]:
    """Claude Code keeps the strictest decision; also who gave it."""
    decided = [(o.decision, o.plugin) for o in outcomes if o.decision]
    if not decided:
        return None, set()
    strictest = max(decided, key=lambda d: RANK.get(d[0], 0))[0]
    return strictest, {plugin for decision, plugin in decided if decision == strictest}


@pytest.fixture
def family(tmp_path):
    return Family(tmp_path)


def transcript(path: Path, turns: list[tuple[str, str]]) -> Path:
    lines = [json.dumps({"type": kind, "message": {"role": kind, "content": text}}) for kind, text in turns]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


# ---------------------------------------------------------------- every hook, every event


def test_every_hook_runs_beside_the_others(family):
    written = family.project / "notes.md"
    written.write_text("# Notes\n\nShort and plain.\n")
    events = [
        ("SessionStart", {"source": "startup"}),
        ("UserPromptSubmit", {"prompt": "add a test for the parser"}),
        ("PreToolUse", {"tool_name": "Bash", "tool_input": {"command": "ls"}}),
        ("PreToolUse", {"tool_name": "Write", "tool_input": {"file_path": str(written), "content": "x"}}),
        ("PostToolUse", {"tool_name": "Write", "tool_input": {"file_path": str(written)},
                         "tool_response": {"type": "create"}}),
        ("SubagentStart", {"agent_type": "Explore"}),
        ("PreCompact", {"trigger": "manual"}),
        ("Stop", {"stop_hook_active": False}),
        ("SessionEnd", {"reason": "exit"}),
    ]
    ran = set()
    for event, payload in events:
        for outcome in family.fire(event, payload):
            ran.add(outcome.plugin)
            assert outcome.code == 0, (outcome.plugin, event, outcome.err[-600:])
            assert "Traceback" not in outcome.err, (outcome.plugin, event, outcome.err[-600:])
            assert outcome.decision in (None, "allow"), (outcome.plugin, event, outcome.out)
    assert ran == {name for name, config in HOOKED.items() if config.get("hooks")}
    assert not family.claude_log.exists()  # nothing started a model call


# ---------------------------------------------------------------- bayan and prof's files (#46)


REPORT = """# Session report

## Concept checklist
- [missed] py :: Python :: generators :: said yield returns a list — then fixed it
- [understood] py :: Python :: list comprehensions :: wrote one unprompted
"""


def test_bayan_leaves_prof_files_alone_with_every_hook_installed(family):
    reports = family.data("prof") / "reports"
    reports.mkdir(parents=True)
    report = reports / "2026-10-07_1200_together.md"
    report.write_text(REPORT)
    control = family.project / "control.md"
    control.write_text(REPORT)
    for path in (report, control):
        family.fire("PostToolUse", {"tool_name": "Write", "tool_input": {"file_path": str(path)},
                                    "tool_response": {"type": "create"}})
    assert control.read_text() != REPORT, "bayan left an ordinary file alone: the check below proves nothing"
    assert report.read_text() == REPORT

    store = [sys.executable, str(PLUGINS / "prof" / "scripts" / "prof_store.py")]
    merged = subprocess.run([*store, "merge-report", str(report)], env=family.env, capture_output=True,
                            text=True)
    assert merged.returncode == 0, merged.stderr
    topic = family.data("prof") / "topics" / "py.md"
    before = topic.read_text()
    for cwd in (family.project, family.home):  # also when Claude runs in the home folder itself
        family.fire("PostToolUse", {"tool_name": "Edit", "tool_input": {"file_path": str(topic)},
                                    "tool_response": {}}, cwd=cwd)
    assert topic.read_text() == before
    shown = subprocess.run([*store, "topic", "py"], env=family.env, capture_output=True, text=True).stdout
    assert "missed:\n- generators — said yield" in shown and "understood:\n- list comprehensions" in shown


# ---------------------------------------------------------------- barq run:test inside itqan ship (#47)


def _test_tool(text: str) -> str:
    for tool in ("pytest", "npm", "pnpm", "yarn", "go test", "cargo test", "dotnet test"):
        if tool in text:
            return tool
    return text


def barq_test_command(family: Family, root: Path) -> str:
    out = subprocess.run([sys.executable, str(PLUGINS / "barq" / "bin" / "barq"), "info"], cwd=root,
                         env=family.env, capture_output=True, text=True, timeout=60).stdout
    line = next(line for line in out.splitlines() if line.strip().startswith("test "))
    return _test_tool(line)


def itqan_test_commands(family: Family, root: Path) -> list[str]:
    out = subprocess.run([sys.executable, str(PLUGINS / "itqan" / "scripts" / "itqan_proof.py"), "checks"],
                         cwd=root, env=family.env, capture_output=True, text=True, timeout=60).stdout
    return [_test_tool(line) for line in out.splitlines() if line.strip().startswith("tests:")]


def _layout(root: Path, files: dict[str, str]) -> Path:
    for rel, text in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text)
    _git(root, "init", "-q", "-b", "main")
    return root


PY = {"pyproject.toml": "[project]\nname = 'x'\n", "tests/test_x.py": "def test_x():\n    pass\n"}
NESTED_NODE = {"plugins/lawha/engine/package.json": '{"scripts": {"test": "node --test"}}'}
ROOT_NODE = {"package.json": '{"scripts": {"test": "vitest"}}'}


@pytest.mark.parametrize("files", [PY, {**PY, **NESTED_NODE}, {**PY, **ROOT_NODE}],
                         ids=["python", "python-and-nested-node", "root-node-and-python"])
def test_barq_runs_a_suite_itqans_proof_records(family, tmp_path, files):
    # /itqan:ship runs every check the proof records; `barq run:test` may stand in only for one of them
    root = _layout(tmp_path / "layout", files)
    assert barq_test_command(family, root) in itqan_test_commands(family, root)


def test_barq_and_itqan_agree_on_this_repository(family):
    assert barq_test_command(family, REPO) == "pytest"
    assert itqan_test_commands(family, REPO) == ["pytest"]


# ---------------------------------------------------------------- itqan beside haris (#48)


def test_haris_and_itqan_together_keep_every_protection(family):
    family.fire("SessionStart", {"source": "startup"})
    assert (family.data("haris") / "active" / SESSION).is_file()

    def bash(command):
        return verdict(family.fire("PreToolUse", {"tool_name": "Bash", "tool_input": {"command": command}}))

    decision, who = bash("git push --force origin main")
    assert decision in ("deny", "ask") and "haris" in who and "itqan" not in who  # itqan steps aside
    decision, who = bash("git commit --no-verify -m wip")
    assert decision == "ask" and "itqan" in who  # a quality rule itqan keeps beside haris
    secret = family.project / ".env"
    write = {"tool_name": "Write", "tool_input": {"file_path": str(secret), "content": "K=1"}}
    decision, who = verdict(family.fire("PreToolUse", write))
    assert decision in ("deny", "ask") and who

    (family.data("haris") / "config.json").write_text('{"mode": "watch"}')
    decision, who = bash("git push --force origin main")
    assert decision in ("deny", "ask") and "itqan" in who  # haris only watches: itqan guards again


def test_itqan_guards_alone_without_haris(family):
    without = set(HOOKED) - {"haris"}
    family.fire("SessionStart", {"source": "startup"}, installed=without)
    push = {"tool_name": "Bash", "tool_input": {"command": "git push --force origin main"}}
    decision, who = verdict(family.fire("PreToolUse", push, installed=without))
    assert decision == "deny" and who == {"itqan"}


# ---------------------------------------------------------------- the background guard (#45)


def _background_session(family: Family) -> Path:
    """A session that makes prof (an automatic report) and itqan (lesson extraction) want to start
    `claude -p` when it ends."""
    prof_settings = family.data("prof") / "settings.json"
    prof_settings.parent.mkdir(parents=True, exist_ok=True)
    prof_settings.write_text('{"auto_report": true}')
    _git(family.project, "commit", "-q", "--allow-empty", "-m", "init")
    path = transcript(family.home / "session.jsonl", [
        ("user", "<command-name>/prof:learn</command-name> teach me generators"),
        ("assistant", "A generator yields values one at a time."),
        ("user", "so it returns a list?"),
        ("assistant", "We always use a list here."),
        ("user", "no, that's wrong, we never use a list for this, use a generator instead"),
        ("assistant", "Right, a generator."),
        ("user", "thanks, done"),
    ])
    family.fire("UserPromptSubmit", {"prompt": "no, that's wrong, we never use a list for this"})
    return path


def started(family: Family) -> set[str]:
    """Which plugins launched their background `claude -p` job (each leaves a mark before it launches)."""
    found = set()
    log = family.data("prof") / "hook.log"
    if log.is_file() and "auto-report started" in log.read_text():
        found.add("prof")
    if (family.data("itqan") / "tmp").is_dir():  # its payload goes there; the job removes the file
        found.add("itqan")
    return found


def test_a_normal_session_end_starts_the_background_jobs(family):
    path = _background_session(family)
    family.fire("SessionEnd", {"reason": "exit", "transcript_path": str(path)})
    assert started(family) == {"prof", "itqan"}  # the harness sees a launch, so the checks below count


@pytest.mark.parametrize("plugin", ["prof", "itqan"])
def test_a_background_job_does_not_start_itself_again(family, plugin):
    path = _background_session(family)
    family.fire("SessionEnd", {"reason": "exit", "transcript_path": str(path)}, env=GUARDS[plugin])
    assert plugin not in started(family)


def test_hafiz_hooks_stay_out_of_its_own_summary(family):
    family.fire("SessionEnd", {"reason": "exit"}, env=GUARDS["hafiz"])
    assert not family.data("hafiz").exists()


@pytest.mark.xfail(strict=True, reason="#45: each plugin silences only its own hooks; the others still "
                                       "start their paid background job inside it")
@pytest.mark.parametrize("plugin", sorted(GUARDS))
def test_no_background_job_starts_inside_another(family, plugin):
    path = _background_session(family)
    family.fire("SessionEnd", {"reason": "exit", "transcript_path": str(path)}, env=GUARDS[plugin])
    assert started(family) == set()
