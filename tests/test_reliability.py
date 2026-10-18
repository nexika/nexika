"""Shared state survives what several sessions and crashes do to it (#394): two writers at once, a
corrupted or half-written file, and data from an older release. A bad file means "nothing known";
it never breaks a session."""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys

import pytest
from conftest import REPO


def load(name):
    spec = importlib.util.spec_from_file_location(f"nexika_{name}", REPO / "common" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def status():
    return load("status")


@pytest.fixture
def background():
    return load("background")


@pytest.fixture
def family():
    return load("family")


# ---------------------------------------------------------------- status files

@pytest.mark.parametrize("updated", ['"soon"', "[1]", "{}", "null", '"1e999"', "true"])
def test_a_status_file_with_a_bad_time_is_ignored(status, updated):
    for plugin, session in (("haris", ""), ("mizan", "s1")):
        path = status.path_for(plugin, session)
        status.ensure_dir(path.parent)
        path.write_text(f'{{"schema": "{status.schema(plugin)}", "updated": {updated}}}', encoding="utf-8")
    assert status.read("haris", max_age=60) in ({}, json.loads(status.path_for("haris").read_text()))
    assert isinstance(status.sessions("mizan"), list)


@pytest.mark.parametrize("text", ["", "{", '{"schema": "nexika.haris/1", "upd', "[]", '"x"', "null",
                                  "\udcff"])
def test_a_broken_status_file_reads_as_nothing_known(status, text):
    path = status.path_for("haris")
    status.ensure_dir(path.parent)
    path.write_bytes(text.encode("utf-8", "surrogateescape"))
    assert status.read("haris") == {}


def test_a_leftover_temp_file_is_not_read_as_a_session(status):
    assert status.publish("mizan", {"context": 10}, session="s1")
    folder = status.home() / "mizan"
    (folder / ".s2.json.999.tmp").write_text('{"schema": "nexika.mizan/1", "upd', encoding="utf-8")
    assert [s["context"] for s in status.sessions("mizan")] == [10]


# ---------------------------------------------------------------- the family settings file

def test_the_background_log_survives_a_bad_line(background, nexika_home):
    background.record("hafiz", "summary")
    with open(nexika_home / "background.jsonl", "ab") as log:
        log.write(b'{"ts": "2099-01-01", "plugin": "x", "ran": tr\n\xff\xfe not utf-8\n[1, 2]\n')
    background.record("hafiz", "summary")
    assert background.counts()["hafiz"] == {"ran": 2, "skipped": 0}
    assert "hafiz: 2 ran" in background.status_text()


@pytest.mark.parametrize("text", ['{"role": ["writer"], "background": 5}', '{"role": null}',
                                  '{"background": {"on": 1}}'])
def test_settings_of_the_wrong_type_read_as_unset(family, background, nexika_home, text):
    nexika_home.mkdir(parents=True, exist_ok=True)
    (nexika_home / "settings.json").write_text(text, encoding="utf-8")
    assert family.role() == ""
    assert background.setting() == "ask"


SETTER = """
import importlib.util, sys
spec = importlib.util.spec_from_file_location("background", sys.argv[1])
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
for i in range(int(sys.argv[3])):
    m.update_settings(**{f"{sys.argv[2]}_{i}": i})
"""


def test_two_sessions_saving_settings_at_once_lose_nothing(nexika_home):
    writers, rounds = 6, 25
    procs = [subprocess.Popen([sys.executable, "-c", SETTER, str(REPO / "common" / "background.py"),
                               f"w{n}", str(rounds)]) for n in range(writers)]
    assert all(p.wait(timeout=60) == 0 for p in procs)
    saved = json.loads((nexika_home / "settings.json").read_text(encoding="utf-8"))
    missing = [f"w{n}_{i}" for n in range(writers) for i in range(rounds) if f"w{n}_{i}" not in saved]
    assert not missing, f"{len(missing)} of {writers * rounds} settings were lost"
    assert not list(nexika_home.glob(".settings.json.*"))


def test_settings_save_where_files_cannot_be_locked(family, nexika_home, monkeypatch):
    """A home on a network drive may refuse file locks: the change is still saved, unlocked."""
    import fcntl

    def refuse(*args):
        raise OSError(37, "No locks available")
    monkeypatch.setattr(fcntl, "flock", refuse)
    family.save_role("writer")
    assert family.role() == "writer"


def test_an_old_profile_moves_in_under_the_lock(family, background, old_profile, nexika_home):
    old_profile.parent.mkdir(parents=True, exist_ok=True)
    old_profile.write_text('{"role": "learner"}')
    background.set_setting("on")  # a change saved while the old profile is still there
    assert family.role() == "learner" and background.setting() == "on"
    assert not old_profile.exists()


UPDATER = """
import importlib.util, sys
spec = importlib.util.spec_from_file_location("status", sys.argv[1])
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
for i in range(int(sys.argv[3])):
    m.update("manar", lambda d: d.setdefault("audits", {}).__setitem__(f"{sys.argv[2]}_{i}", {"score": i}))
"""


def test_two_sessions_publishing_at_once_both_keep_their_part(status):
    writers, rounds = 6, 20
    procs = [subprocess.Popen([sys.executable, "-c", UPDATER, str(REPO / "common" / "status.py"), f"w{n}",
                               str(rounds)]) for n in range(writers)]
    assert all(p.wait(timeout=60) == 0 for p in procs)
    audits = status.read("manar").get("audits") or {}
    assert len(audits) == writers * rounds, f"{writers * rounds - len(audits)} entries were lost"
    assert not list(status.home().glob(".manar.json.*.tmp"))


def test_update_starts_from_nothing_when_the_file_is_unusable(status):
    path = status.path_for("tabib")
    status.ensure_dir(path.parent)
    path.write_text('{"schema": "nexika.tabib/1", "runs": [1')
    saved = status.update("tabib", lambda d: d.update(runs={"r": {}}))
    assert saved["runs"] == {"r": {}} and status.read("tabib")["runs"] == {"r": {}}


def test_a_failed_write_leaves_no_temp_file(status, monkeypatch):
    def broken(*args, **kwargs):
        raise OSError(28, "No space left on device")
    monkeypatch.setattr(status.os, "replace", broken)
    assert status.publish("amin", {"repos": {}}) is False
    assert not [p for p in status.home().iterdir() if p.name.endswith(".tmp")]
