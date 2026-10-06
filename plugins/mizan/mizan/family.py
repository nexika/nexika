"""The other Nexika plugins mizan works with, reached only through their files and helpers.

    hafiz  saves the handoff note (`hafiz handoff --save`), when it is installed
    haris  publishes status/haris/<session>.json: its profile and mode for this session
    itqan  publishes status/itqan.json: the latest proof file per project
    lawha  publishes status/lawha.json: the latest check of the project's pages on every screen
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from . import status

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
PROOF_SCHEMA = "nexika.itqan.proof/1"
LAWHA_SCHEMA = "nexika.lawha.check/1"


def _versions(folder: Path) -> list[Path]:
    try:
        found = [p for p in folder.iterdir() if p.is_dir()]
        return sorted(found, key=lambda p: p.stat().st_mtime, reverse=True)
    except OSError:
        return []


def find_plugin(name: str) -> Path | None:
    """Where another Nexika plugin lives: beside mizan (a checkout or a marketplace folder), in the
    plugin cache (<marketplace>/<plugin>/<version>), or where installed_plugins.json says."""
    candidates = [PLUGIN_ROOT.parent / name, *_versions(PLUGIN_ROOT.parent.parent / name)]
    registry = Path(os.path.expanduser("~/.claude/plugins/installed_plugins.json"))
    try:
        installed = json.loads(registry.read_text(encoding="utf-8")).get("plugins") or {}
    except (OSError, ValueError, AttributeError):
        installed = {}
    for key, entries in installed.items():
        if key.split("@")[0] == name and isinstance(entries, list):
            candidates += [Path(e["installPath"]) for e in entries
                           if isinstance(e, dict) and e.get("installPath")]
    return next((c for c in candidates if (c / "bin" / name).is_file()), None)


def handoff(session: str, transcript: str, cwd: str) -> dict:
    """Have hafiz capture the session and write its handoff note now."""
    hafiz = find_plugin("hafiz")
    if hafiz is None:
        return {"saved": False, "why": "hafiz is not installed"}
    if not status.SAFE_ID.match(session or "") or not transcript or not os.path.isfile(transcript):
        return {"saved": False, "why": "no session transcript"}
    argv = [sys.executable, str(hafiz / "bin" / "hafiz"), "handoff", "--save", "--session", session,
            "--transcript", transcript]
    try:
        done = subprocess.run(argv, cwd=cwd or None, capture_output=True, text=True, timeout=60, check=False)
    except (OSError, subprocess.SubprocessError):
        return {"saved": False, "why": "hafiz did not answer"}
    return {"saved": done.returncode == 0, "why": "" if done.returncode == 0 else done.stderr.strip()[-300:]}


def haris_status(session: str) -> dict:
    found = status.read("haris", session) if session else {}
    return {"profile": found.get("profile", ""), "mode": found.get("mode", "")} if found else {}


def itqan_home() -> Path:
    return Path(os.path.expanduser(os.environ.get("ITQAN_HOME") or "~/.claude/nexika/itqan")).resolve()


def _under(path: str, folder: Path) -> bool:
    try:
        return folder in Path(path).resolve().parents
    except (OSError, ValueError):
        return False


def proof(repo: str) -> dict:
    """The latest itqan proof for this repository, or {}."""
    proofs = status.read("itqan").get("proofs") or {}
    if not isinstance(proofs, dict) or not repo:
        return {}
    path = proofs.get(repo) or proofs.get(os.path.realpath(repo))
    if not path or not _under(path, itqan_home() / "proofs"):
        return {}  # only a proof itqan saved in its own (haris-guarded) folder
    data = status.read_json(Path(path))
    return data if data.get("schema") == PROOF_SCHEMA else {}


def lawha_home() -> Path:
    return Path(os.path.expanduser(os.environ.get("LAWHA_HOME") or "~/.claude/nexika/lawha")).resolve()


def lawha_check(repo: str) -> dict:
    """lawha's latest check of this repository's pages, or {}. Only a record in lawha's own
    (haris-guarded) folder counts, like itqan's proofs."""
    checks = status.read("lawha").get("checks") or {}
    if not isinstance(checks, dict) or not repo:
        return {}
    path = checks.get(repo) or checks.get(os.path.realpath(repo))
    if not path or not _under(path, lawha_home() / "checks"):
        return {}
    data = status.read_json(Path(path))
    return data if data.get("schema") == LAWHA_SCHEMA else {}
