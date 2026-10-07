"""mizan doctor: the plugins installed together, their hooks, known conflicts, status files (#68)."""
from __future__ import annotations

import json
import os
import sys
import time

import pytest
from conftest import PLUGINS

if str(PLUGINS / "mizan") not in sys.path:
    sys.path.insert(0, str(PLUGINS / "mizan"))

from mizan import cli, doctor, status  # noqa: E402


@pytest.fixture
def claude(tmp_path, monkeypatch):
    """A Claude Code config folder where the given Nexika plugins are installed from this checkout."""
    config = tmp_path / "claude"
    (config / "plugins").mkdir(parents=True)
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(config))
    monkeypatch.setenv("NEXIKA_STATUS_HOME", str(tmp_path / "status"))
    project = tmp_path / "project"
    project.mkdir()

    def install(*names, settings=None):
        plugins = {f"{n}@nexika": [{"scope": "user", "installPath": str(PLUGINS / n), "version": "0.1.0"}]
                   for n in names}
        registry = config / "plugins" / "installed_plugins.json"
        registry.write_text(json.dumps({"version": 2, "plugins": plugins}))
        (config / "settings.json").write_text(json.dumps(settings or {}))
        return project

    return install


def problems(found, kind):
    return [p for p in found["problems"] if p["kind"] == kind]


def test_lists_installed_plugins_and_their_hooks(claude):
    cwd = claude("bayan", "haris")
    found = doctor.run(cwd, latency=False)
    names = {p["name"]: p for p in found["plugins"]}
    assert set(names) == {"bayan", "haris"}
    events = {h["event"] for h in names["bayan"]["hooks"]}
    assert events == {"SessionStart", "PreToolUse", "PostToolUse"}
    pre = next(h for h in names["bayan"]["hooks"] if h["event"] == "PreToolUse")
    assert pre["matcher"] == "Bash" and "hook pre-bash" in pre["command"]


def test_bayan_with_claudes_signature_on_is_a_conflict(claude):
    found = doctor.run(claude("bayan"), latency=False)
    assert problems(found, "bayan-attribution")
    off = {"attribution": {"commit": "", "pr": ""}}
    assert not problems(doctor.run(claude("bayan", settings=off), latency=False), "bayan-attribution")
    legacy = {"includeCoAuthoredBy": False}
    assert not problems(doctor.run(claude("bayan", settings=legacy), latency=False), "bayan-attribution")


def test_itqan_without_haris_is_a_conflict(claude):
    assert problems(doctor.run(claude("itqan"), latency=False), "itqan-without-haris")
    assert not problems(doctor.run(claude("itqan", "haris"), latency=False), "itqan-without-haris")
    disabled = {"enabledPlugins": {"haris@nexika": False}}
    found = doctor.run(claude("itqan", "haris", settings=disabled), latency=False)
    assert problems(found, "itqan-without-haris")
    assert {p["name"]: p["enabled"] for p in found["plugins"]} == {"itqan": True, "haris": False}


def test_project_settings_count_too(claude):
    cwd = claude("bayan")
    (cwd / ".claude").mkdir()
    (cwd / ".claude" / "settings.json").write_text(json.dumps({"attribution": {"commit": "", "pr": ""}}))
    assert not problems(doctor.run(cwd, latency=False), "bayan-attribution")


def test_status_files_freshness(claude):
    cwd = claude("mizan", "prof")
    status.publish("prof", {"due": 1})
    stale = status.path_for("amin")
    status.write_json(stale, {"schema": "nexika.amin/1", "updated": int(time.time()) - 30 * 86400})
    status.write_json(status.path_for("barq"), {"schema": "nexika.barq/9", "updated": int(time.time())})
    found = {s["name"]: s for s in doctor.run(cwd, latency=False)["status"]}
    assert found["prof"]["state"] == "fresh"
    assert found["amin"]["state"] == "stale" and found["amin"]["age_days"] >= 30
    assert found["barq"]["state"] == "unknown-schema"
    kinds = {p["kind"] for p in doctor.run(cwd, latency=False)["problems"]}
    assert {"status-stale", "status-schema"} <= kinds


def test_status_files_open_to_others_are_flagged(claude):
    cwd = claude("prof")
    status.publish("prof", {"due": 1})
    os.chmod(status.path_for("prof"), 0o644)
    assert problems(doctor.run(cwd, latency=False), "status-mode")


def test_hook_latency_is_measured_in_a_throwaway_home(claude, tmp_path):
    cwd = claude("bayan")
    found = doctor.run(cwd, latency=True)
    timed = [h for p in found["plugins"] for h in p["hooks"]]
    assert timed and all(isinstance(h["ms"], int) and h["ms"] >= 0 for h in timed)
    assert all(h["exit"] == 0 for h in timed), timed
    assert not (tmp_path / "claude" / "nexika").exists()  # the hooks ran away from the real config


def test_cli_text_and_json(claude, capsys):
    cwd = claude("itqan")
    code = cli.main(["doctor", "--no-latency", "--cwd", str(cwd)])
    text = capsys.readouterr().out
    assert code == 1
    assert "itqan" in text and "haris" in text and "PreToolUse" in text
    assert cli.main(["doctor", "--json", "--no-latency", "--cwd", str(cwd)]) == 1
    data = json.loads(capsys.readouterr().out)
    assert data["schema"] == "nexika.doctor/1" and data["problems"]


def test_nothing_installed_says_so(claude, capsys):
    cwd = claude()
    assert cli.main(["doctor", "--no-latency", "--cwd", str(cwd)]) == 0
    assert "no Nexika plugin" in capsys.readouterr().out
