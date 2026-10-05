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
