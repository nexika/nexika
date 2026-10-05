"""Shared fixtures: load prof_store against a throwaway data directory."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
PLUGINS = REPO / "plugins"
STORE_PATH = PLUGINS / "prof" / "scripts" / "prof_store.py"


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
