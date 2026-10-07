"""common/: one source for the files several plugins ship (#44)."""
from __future__ import annotations

import importlib.util
import json
import sys

import pytest
from conftest import PLUGINS, REPO

AMIN_ROOT = PLUGINS / "amin"
if str(AMIN_ROOT) not in sys.path:
    sys.path.insert(0, str(AMIN_ROOT))

from amin import project as proj  # noqa: E402
from amin import release  # noqa: E402

COPIES = proj.copies(REPO)


def test_every_shared_file_is_listed():
    assert set(COPIES) == {f"common/{n}" for n in ("secrets.py", "inject.py", "status.py", "gitinfo.py")}
    assert all((REPO / source).is_file() for source in COPIES)


@pytest.mark.parametrize("source,copy", [(s, t) for s, targets in COPIES.items() for t in targets])
def test_each_copy_is_identical_to_common(source, copy):
    assert (REPO / copy).read_bytes() == (REPO / source).read_bytes(), \
        f"{copy} drifted from {source}: edit {source}, then run python3 plugins/amin/bin/amin copies"


def test_no_unlisted_copy_of_a_shared_file():
    listed = {t for targets in COPIES.values() for t in targets}
    for source in COPIES:
        data = (REPO / source).read_bytes()
        same = {str(p.relative_to(REPO)) for p in PLUGINS.rglob("*.py")
                if "node_modules" not in p.parts and p.read_bytes() == data}
        assert same <= listed, f"copies of {source} missing from .amin.json: {sorted(same - listed)}"


# ---------------------------------------------------------------- amin keeps the copies in sync


@pytest.fixture
def repo(tmp_path):
    (tmp_path / "common").mkdir()
    (tmp_path / "common" / "x.py").write_text("NEW = 1\n")
    (tmp_path / "plugins" / "a" / "a").mkdir(parents=True)
    (tmp_path / "plugins" / "a" / "a" / "x.py").write_text("OLD = 1\n")
    (tmp_path / ".amin.json").write_text(json.dumps(
        {"copies": {"common/x.py": ["plugins/a/a/x.py", "plugins/b/b/x.py"]}}))
    return tmp_path


def test_stale_and_missing_copies_are_found(repo):
    assert release.stale_copies(repo) == ["plugins/a/a/x.py", "plugins/b/b/x.py"]


def test_sync_refreshes_every_copy(repo):
    assert release.sync_copies(repo) == ["plugins/a/a/x.py", "plugins/b/b/x.py"]
    assert (repo / "plugins/a/a/x.py").read_text() == "NEW = 1\n"
    assert (repo / "plugins/b/b/x.py").read_text() == "NEW = 1\n"
    assert release.stale_copies(repo) == []


def test_dry_run_writes_nothing(repo):
    assert release.sync_copies(repo, dry_run=True) == ["plugins/a/a/x.py", "plugins/b/b/x.py"]
    assert (repo / "plugins/a/a/x.py").read_text() == "OLD = 1\n"


def test_no_copies_configured(tmp_path):
    assert release.sync_copies(tmp_path) == []


# ---------------------------------------------------------------- itqan's proof uses the shared redaction


def test_proof_redacts_what_the_shared_patterns_catch():
    spec = importlib.util.spec_from_file_location(
        "itqan_proof_common", PLUGINS / "itqan" / "scripts" / "itqan_proof.py")
    proof = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(proof)
    stripe = "sk_live_" + "a1B2c3D4e5F6g7H8i9J0"
    jwt = ("eyJhbGciOiJIUzI1NiJ9." + "eyJzdWIiOiIxMjM0NTY3ODkwIn0."
           + "dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U")
    bearer = "Bearer " + "abcDEF123456ghiJKL789012mno"
    github = "ghp_" + "x" * 36
    out = proof.redact(f"key={stripe} token {jwt}\nAuthorization: {bearer}\nGITHUB={github}")
    for leaked in (stripe, jwt, bearer.split()[1], "ghp_"):
        assert leaked not in out
    assert "[secret]" in out
