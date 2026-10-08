"""Shared fixtures: load prof_store against a throwaway data directory."""
from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
PLUGINS = REPO / "plugins"
STORE_PATH = PLUGINS / "prof" / "scripts" / "prof_store.py"
BARQ_ROOT = PLUGINS / "barq"
if str(BARQ_ROOT) not in sys.path:
    sys.path.insert(0, str(BARQ_ROOT))


@pytest.fixture(scope="session")
def _test_gitconfig(tmp_path_factory):
    path = tmp_path_factory.mktemp("git") / "gitconfig"
    path.write_text("[user]\n\tname = Test\n\temail = t@example.com\n[init]\n\tdefaultBranch = main\n")
    return path


@pytest.fixture(autouse=True)
def _git_identity(_test_gitconfig, monkeypatch):
    """CI runners have no global git user: every test (and every git it starts) gets the same
    global config with one, so a commit in a test repo never fails there while passing on a
    developer machine. A repo's own user.name still wins; the developer's config is not read."""
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(_test_gitconfig))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")


@pytest.fixture(autouse=True)
def _status_home(tmp_path, monkeypatch):
    """Plugins publish status files as they run: keep them out of the real ~/.claude."""
    monkeypatch.setenv("NEXIKA_STATUS_HOME", str(tmp_path / "status"))


@pytest.fixture(autouse=True)
def old_profile(tmp_path, monkeypatch):
    """Where #65 kept the profile before it moved into the settings file (#108): migrated from
    tmp_path, never from ~/.claude."""
    path = tmp_path / "nexika-profile.json"
    monkeypatch.setenv("NEXIKA_PROFILE", str(path))
    return path


@pytest.fixture(autouse=True)
def nexika_home(tmp_path, monkeypatch):
    """The family's shared settings and background-call log stay out of ~/.claude (#45)."""
    monkeypatch.setenv("NEXIKA_HOME", str(tmp_path / "nexika"))
    monkeypatch.delenv("NEXIKA_BACKGROUND", raising=False)
    return tmp_path / "nexika"


@pytest.fixture
def family_profile(nexika_home):
    """The family settings file, which holds the profile's role (#65, #108)."""
    return nexika_home / "settings.json"


@pytest.fixture
def store(tmp_path, monkeypatch):
    """A fresh prof_store module whose data lives in tmp_path/prof (never ~/.claude)."""
    monkeypatch.setenv("PROF_HOME", str(tmp_path / "prof"))
    monkeypatch.delenv("PROF_REPORTING", raising=False)
    spec = importlib.util.spec_from_file_location("prof_store", STORE_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules["prof_store"] = module
    spec.loader.exec_module(module)
    yield module
    sys.modules.pop("prof_store", None)


@pytest.fixture
def barq_env(tmp_path, monkeypatch):
    """barq with its data dir and session isolated in tmp_path."""
    from barq import files

    monkeypatch.setenv("BARQ_HOME", str(tmp_path / "barq-home"))
    monkeypatch.setenv("BARQ_SESSION", "test-session")
    for name in ("BARQ_NO_MASK", "BARQ_ALLOW_OUTSIDE", "BARQ_DEBUG"):
        monkeypatch.delenv(name, raising=False)
    files.project_root.cache_clear()
    yield tmp_path
    files.project_root.cache_clear()


def _git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


@pytest.fixture
def project(barq_env, monkeypatch):
    """A small git repo (on main, one commit) as the current directory."""
    root = barq_env / "proj"
    (root / "src").mkdir(parents=True)
    (root / "src" / "app.py").write_text(
        "import os\n\n\nclass Cart:\n    def total(self):\n        return 42\n\n\n"
        "def helper():\n    # TODO: remove\n    return Cart()\n"
    )
    (root / "src" / "util.py").write_text("def add(a, b):\n    return a + b  # TODO later\n")
    (root / "README.md").write_text("# Demo\n\n## Usage\nrun it\n")
    (root / ".gitignore").write_text("ignored/\n")
    (root / "ignored").mkdir()
    (root / "ignored" / "skip.py").write_text("# TODO: must not be found\n")
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "t@example.com")
    _git(root, "config", "user.name", "Test")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "initial")
    monkeypatch.chdir(root)
    return root


@pytest.fixture
def barq_run(capsys):
    """Run the barq CLI in-process: returns (exit code, stdout)."""
    from barq import cli

    def run(*args):
        code = cli.main(list(args))
        return code, capsys.readouterr().out

    return run
