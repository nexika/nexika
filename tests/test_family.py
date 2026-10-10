"""The Nexika family profile (#65): one role, read by bayan, prof and siyaq."""
from __future__ import annotations

import importlib.util
import json
import stat
import subprocess
import sys

import pytest
from conftest import PLUGINS, REPO

for root in (PLUGINS / "bayan", PLUGINS / "siyaq"):
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

from bayan import check as bayan_check  # noqa: E402
from bayan import config as bayan_config  # noqa: E402
from bayan import hooks as bayan_hooks  # noqa: E402
from siyaq import rank  # noqa: E402

FAMILY = REPO / "common" / "family.py"


@pytest.fixture
def family():
    spec = importlib.util.spec_from_file_location("nexika_family", FAMILY)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(autouse=True)
def bayan_home(tmp_path, monkeypatch):
    monkeypatch.setenv("BAYAN_HOME", str(tmp_path / "bayan-home"))
    monkeypatch.delenv("BAYAN_LEVEL", raising=False)
    monkeypatch.delenv("CLAUDE_ENV_FILE", raising=False)
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "claude-config"))


def set_role(path, role):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"schema": "nexika.settings/1", "role": role}), encoding="utf-8")


# ---------------------------------------------------------------- the file


def test_role_is_saved_owner_only_and_read_back(family, family_profile):
    assert family.role() == ""
    family.save_role("learner")
    assert family.role() == "learner"
    assert json.loads(family_profile.read_text())["schema"] == "nexika.settings/1"
    assert stat.S_IMODE(family_profile.stat().st_mode) == 0o600


def test_unknown_roles_are_refused_and_ignored(family, family_profile):
    with pytest.raises(ValueError):
        family.save_role("wizard")
    set_role(family_profile, "wizard")
    assert family.role() == ""
    family_profile.write_text("not json", encoding="utf-8")
    assert family.role() == ""


def test_the_question_is_asked_once(family):
    note = family.ask_note("python3 /x/family.py")
    assert "developer" in note and "learner" in note and "writer" in note
    assert "python3 /x/family.py role <answer>" in note
    assert family.ask_note("python3 /x/family.py") == ""   # another plugin, or a later session


def test_no_question_once_a_role_is_chosen(family, family_profile):
    set_role(family_profile, "writer")
    assert family.ask_note("helper") == ""


def test_command_line_sets_the_role(family_profile):
    run = subprocess.run([sys.executable, str(FAMILY), "role", "developer"], capture_output=True, text=True)
    assert run.returncode == 0 and "role developer" in run.stdout
    assert json.loads(family_profile.read_text())["role"] == "developer"
    bad = subprocess.run([sys.executable, str(FAMILY), "role", "boss"], capture_output=True, text=True)
    assert bad.returncode == 2


# ---------------------------------------------------------------- bayan: the reader level


@pytest.mark.parametrize("role,level",
                         [("developer", "developer"), ("learner", "junior"), ("writer", "no-code")])
def test_bayan_level_follows_the_role(family_profile, role, level):
    set_role(family_profile, role)
    assert bayan_config.load()["level"] == level


def test_bayan_own_level_wins_over_the_role(family_profile):
    set_role(family_profile, "developer")
    bayan_config.save(level="junior")
    assert bayan_config.load()["level"] == "junior"


def test_bayan_other_settings_do_not_pin_a_level(family_profile):
    bayan_config.save(auto_clean=False)          # used to write the default level into config.json too
    set_role(family_profile, "developer")
    assert bayan_config.load()["level"] == "developer"
    assert bayan_config.load()["auto_clean"] is False


def test_bayan_session_note_asks_once(family_profile):
    first = bayan_hooks.session_start({})
    assert "Nexika profile: not set yet" in first and "bayan/bayan/family.py role <answer>" in first
    assert "Nexika profile" not in bayan_hooks.session_start({})


# ---------------------------------------------------------------- prof: teach or answer


def _due_item(store):
    report = store.REPORTS / "2026-10-04_1500_abcd1234.md"
    store.REPORTS.mkdir(parents=True, exist_ok=True)
    line = "- [missed] py :: Python :: generators :: could not explain yield"
    report.write_text(f"## Concept checklist\n{line}\n", encoding="utf-8")
    store.merge_report(report)


def test_prof_answers_a_developer_instead_of_teaching(store, family_profile, capsys):
    set_role(family_profile, "developer")
    _due_item(store)
    store.session_start({"session_id": "abcdef1234567"})
    out = capsys.readouterr().out.strip()
    assert len(out.splitlines()) == 1
    assert "the user is a developer" in out and "answer questions about code directly" in out
    assert "Warm-up rule" not in out and "1 concepts are due" in out


def test_prof_still_teaches_a_learner(store, family_profile, capsys):
    set_role(family_profile, "learner")
    _due_item(store)
    store.session_start({"session_id": "s1"})
    out = capsys.readouterr().out
    assert "Warm-up rule (mandatory)" in out and "Nexika profile" not in out


def test_prof_session_note_asks_once(store, capsys):
    store.set_auto_report(False)
    store.PROFILE.parent.mkdir(parents=True, exist_ok=True)  # prof speaks only to a learner (#336)
    store.PROFILE.write_text("# Learner profile\n", encoding="utf-8")
    store.session_start({"session_id": "s1"})
    out = capsys.readouterr().out.strip()
    assert len(out.splitlines()) == 1 and "prof/scripts/prof_family.py role <answer>" in out
    store.session_start({"session_id": "s2"})
    assert "Nexika profile" not in capsys.readouterr().out


# ---------------------------------------------------------------- siyaq: the match threshold


def test_siyaq_threshold_follows_the_role(family_profile):
    base = rank.settings({})["min_score"]
    set_role(family_profile, "learner")
    assert rank.settings({})["min_score"] < base
    set_role(family_profile, "developer")
    assert rank.settings({})["min_score"] == rank.ROLE_MIN_SCORE["developer"]


def test_siyaq_project_setting_wins_over_the_role(family_profile):
    set_role(family_profile, "learner")
    assert rank.settings({"min_score": 2.5})["min_score"] == 2.5


# ---------------------------------------------------------------- #51: no profile means a developer


def test_without_a_profile_bayan_writes_for_a_developer(family_profile):
    # bayan's default reader was no-code: every session told Claude the user had never written code
    assert not family_profile.exists()
    assert bayan_config.load()["level"] == "developer"
    assert "Reader level: developer" in bayan_hooks.session_start({})


def test_without_a_profile_bayan_check_does_not_flag_branch_as_jargon():
    doc = "Merge the branch after the API review passes and the build is green."
    findings = bayan_check.check(doc, bayan_config.load()["level"])
    assert not [f for f in findings if "not explained" in f.advice]


def test_without_a_profile_siyaq_keeps_the_developer_threshold():
    assert rank.settings({})["min_score"] == rank.ROLE_MIN_SCORE["developer"]
