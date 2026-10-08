"""The test setup itself: what every test can rely on."""
from __future__ import annotations

import subprocess


def test_a_new_repo_can_commit_without_any_git_config(tmp_path, monkeypatch):
    monkeypatch.delenv("EMAIL", raising=False)   # git would guess an identity from it
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    done = subprocess.run(["git", "commit", "-q", "--allow-empty", "-m", "init"], cwd=tmp_path,
                          capture_output=True, text=True)
    assert done.returncode == 0, done.stderr


def test_a_repo_s_own_identity_still_wins(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "Sara"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-q", "--allow-empty", "-m", "init"], cwd=tmp_path, check=True)
    author = subprocess.run(["git", "log", "-1", "--format=%an"], cwd=tmp_path,
                            capture_output=True, text=True)
    assert author.stdout.strip() == "Sara"
