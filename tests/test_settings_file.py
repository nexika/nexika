"""One settings file for the Nexika family (#108): the role (#65) and the background-call consent
(#45) live together in ~/.claude/nexika/settings.json, read through common/."""
from __future__ import annotations

import importlib.util
import json
import re
import stat
import sys

import pytest
from conftest import PLUGINS, REPO

if str(PLUGINS / "mizan") not in sys.path:
    sys.path.insert(0, str(PLUGINS / "mizan"))

from mizan import doctor  # noqa: E402


def load(name):
    spec = importlib.util.spec_from_file_location(f"nexika_{name}", REPO / "common" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def family():
    return load("family")


@pytest.fixture
def background():
    return load("background")


@pytest.fixture
def legacy(old_profile):
    """profile.json as #65 wrote it, before the two files were one."""
    old_profile.parent.mkdir(parents=True, exist_ok=True)
    return old_profile


def settings(nexika_home):
    return json.loads((nexika_home / "settings.json").read_text(encoding="utf-8"))


def test_role_and_consent_share_one_owner_only_file(family, background, nexika_home):
    family.save_role("writer")
    background.set_setting("on")
    data = settings(nexika_home)
    assert data == {"schema": "nexika.settings/1", "role": "writer", "background_calls": "on"}
    assert stat.S_IMODE((nexika_home / "settings.json").stat().st_mode) == 0o600
    assert family.role() == "writer" and background.setting() == "on"
    family.save_role("learner")
    assert settings(nexika_home)["background_calls"] == "on"


def test_an_old_profile_is_moved_in_once(family, background, legacy, nexika_home):
    nexika_home.mkdir(parents=True)
    (nexika_home / "settings.json").write_text(json.dumps({"background_calls": "off"}))
    legacy.write_text(json.dumps({"schema": "nexika.profile/1", "role": "learner", "asked": "2026-10-01"}))
    assert background.setting() == "off"   # either reader migrates
    assert settings(nexika_home) == {"schema": "nexika.settings/1", "background_calls": "off",
                                     "role": "learner", "asked": "2026-10-01"}
    assert not legacy.exists() and legacy.with_name(legacy.name + ".migrated").is_file()
    assert family.role() == "learner"
    assert family.ask_note("helper") == ""   # answered before the move: never asked again


def test_an_old_question_already_asked_is_not_asked_again(family, legacy, nexika_home):
    legacy.write_text(json.dumps({"schema": "nexika.profile/1", "asked": "2026-10-01"}))
    assert family.ask_note("helper") == ""
    assert settings(nexika_home)["asked"] == "2026-10-01"


def test_the_settings_file_wins_over_an_old_profile(family, legacy, nexika_home):
    family.save_role("developer")
    legacy.write_text(json.dumps({"role": "writer"}))   # left behind by an older plugin copy
    assert family.role() == "developer"
    assert not legacy.exists()


def test_an_unreadable_old_profile_is_set_aside(family, legacy, nexika_home):
    legacy.write_text("not json")
    assert family.role() == ""
    assert not legacy.exists() and legacy.with_name(legacy.name + ".migrated").read_text() == "not json"


def test_a_consent_file_from_before_gets_the_schema_once(background, nexika_home):
    nexika_home.mkdir(parents=True)
    (nexika_home / "settings.json").write_text(json.dumps({"background_calls": "on"}))
    assert background.setting() == "on"
    assert settings(nexika_home) == {"schema": "nexika.settings/1", "background_calls": "on"}


def test_family_and_background_carry_the_same_settings_code():
    """Each shared file ships alone, so both hold the settings block: it must not drift."""
    block = re.compile(r"# -{8,} the family settings file\n.*?# -{8,} end of the family settings file\n",
                       re.S)
    blocks = [block.search((REPO / "common" / f"{n}.py").read_text()) for n in ("family", "background")]
    assert all(blocks), "the settings block markers are missing"
    assert blocks[0].group(0) == blocks[1].group(0)


# ---------------------------------------------------------------- mizan doctor


@pytest.fixture
def doctor_env(tmp_path, monkeypatch):
    config = tmp_path / "claude"
    (config / "plugins").mkdir(parents=True)
    (config / "plugins" / "installed_plugins.json").write_text(json.dumps({"version": 2, "plugins": {}}))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(config))
    project = tmp_path / "project"
    project.mkdir()
    return project


def test_doctor_shows_the_family_settings(family, background, doctor_env, nexika_home):
    family.save_role("learner")
    background.set_setting("off")
    found = doctor.run(doctor_env, latency=False)
    assert found["settings"]["path"] == str(nexika_home / "settings.json")
    assert found["settings"]["role"] == "learner" and found["settings"]["background_calls"] == "off"
    out = doctor.text(found)
    assert "Nexika settings" in out and "role learner" in out and "background calls off" in out


def test_doctor_shows_the_defaults_when_nothing_is_set(doctor_env, nexika_home):
    found = doctor.run(doctor_env, latency=False)
    assert found["settings"]["role"] == "" and found["settings"]["background_calls"] == "ask"
    assert "role not chosen (developer assumed)" in doctor.text(found)


def test_doctor_warns_about_settings_open_to_others(family, doctor_env, nexika_home):
    family.save_role("writer")
    (nexika_home / "settings.json").chmod(0o644)
    assert [p for p in doctor.run(doctor_env, latency=False)["problems"] if p["kind"] == "settings-mode"]


def test_doctor_hook_timing_never_touches_the_real_settings():
    assert {"NEXIKA_HOME", "NEXIKA_PROFILE"} <= set(doctor.DATA_HOMES)


def test_a_broken_settings_file_is_never_overwritten_by_a_read(family, background, legacy, nexika_home):
    nexika_home.mkdir(parents=True)
    (nexika_home / "settings.json").write_text("{broken")
    legacy.write_text(json.dumps({"role": "writer"}))
    assert background.setting() == "ask" and family.role() == ""
    assert (nexika_home / "settings.json").read_text() == "{broken"
    assert legacy.exists()   # moved in once the file can be read again
    family.save_role("learner")   # a save replaces it
    assert settings(nexika_home)["role"] == "learner"
