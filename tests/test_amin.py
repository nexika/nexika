"""amin: versions, notes, changelogs, release plan/prepare/publish, the CI rule, triage, CLI."""
from __future__ import annotations

import datetime
import json
import subprocess
import sys

import pytest
from conftest import PLUGINS, _git

AMIN_ROOT = PLUGINS / "amin"
if str(AMIN_ROOT) not in sys.path:
    sys.path.insert(0, str(AMIN_ROOT))

from amin import changelog, check, cli, fragments, gitops, release, triage  # noqa: E402
from amin import project as proj  # noqa: E402

# ---------------------------------------------------------------- helpers


def write(root, rel, text):
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def commit(root, message="change"):
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", message)


def init_repo(root, files: dict[str, str]):
    for rel, text in files.items():
        write(root, rel, text)
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "t@example.com")
    _git(root, "config", "user.name", "Test")
    commit(root, "init")
    origin = root.parent / f"{root.name}-origin.git"
    _git(root.parent, "init", "-q", "--bare", str(origin))
    _git(root, "remote", "add", "origin", str(origin))
    _git(root, "push", "-q", "-u", "origin", "main")
    _git(root, "remote", "set-head", "origin", "main")
    return root.resolve()


def plugin_json(name, version):
    return json.dumps({"name": name, "version": version, "description": "x"}, indent=2) + "\n"


@pytest.fixture
def market(tmp_path):
    return init_repo(tmp_path / "market", {
        "plugins/alpha/.claude-plugin/plugin.json": plugin_json("alpha", "0.1.0"),
        "plugins/alpha/main.py": "x = 1\n",
        "plugins/beta/.claude-plugin/plugin.json": plugin_json("beta", "1.2.0"),
        "plugins/beta/main.py": "y = 1\n",
        "README.md": "# market\n",
    })


class FakeRunner(gitops.Runner):
    """Real git; canned gh answers (no network)."""

    def __init__(self, root, checks=None, prs=None, issue=None):
        super().__init__(root)
        self.checks = checks if checks is not None else [{"name": "CI", "status": "completed",
                                                           "conclusion": "success"}]
        self.prs, self.issue, self.gh_calls = prs or [], issue, []

    def gh(self, *args, check=True):
        self.gh_calls.append(args)
        if args[:2] == ("release", "create"):
            return f"https://github.com/o/r/releases/tag/{args[2]}\n"
        return json.dumps(self.gh_json(*args))

    def gh_json(self, *args):
        if args[:2] == ("repo", "view"):
            return {"nameWithOwner": "o/r"}
        if args[0] == "api":
            return {"check_runs": self.checks}
        if args[:2] == ("pr", "list"):
            return self.prs
        if args[:2] == ("issue", "view"):
            return self.issue
        raise AssertionError(f"unexpected gh call {args}")


def projects_of(root):
    return {p.name: p for p in proj.detect(root)}


# ---------------------------------------------------------------- versions


@pytest.mark.parametrize(("version", "types", "expected"), [
    ("0.1.0", {"fixed"}, "0.1.1"),
    ("0.1.0", {"added", "fixed"}, "0.2.0"),
    ("0.1.0", {"breaking"}, "0.2.0"),       # 0.x: breaking is a minor bump
    ("1.2.3", {"security"}, "1.2.4"),
    ("1.2.3", {"changed"}, "1.3.0"),
    ("1.2.3", {"removed"}, "2.0.0"),
    ("1.2.3", set(), "1.2.3"),
])
def test_bump_rules(version, types, expected):
    assert proj.bump(version, types)[0] == expected


def test_parse_rejects_non_semver():
    with pytest.raises(ValueError):
        proj.parse("1.2")


# ---------------------------------------------------------------- detection and version files


def test_detect_marketplace(market):
    alpha = projects_of(market)["alpha"]
    assert (alpha.path, alpha.changelog, alpha.fragments) == (
        "plugins/alpha", "plugins/alpha/CHANGELOG.md", "changelog.d/alpha")
    assert alpha.tag("0.2.0") == "alpha-v0.2.0" and alpha.tag_prefix() == "alpha-v"


@pytest.mark.parametrize(("rel", "content"), [
    ("package.json", '{\n  "name": "app",\n  "version": "2.0.0"\n}\n'),
    ("pyproject.toml", '[project]\nname = "app"\nversion = "2.0.0"\n'),
    ("App.csproj", "<Project><PropertyGroup><Version>2.0.0</Version></PropertyGroup></Project>\n"),
])
def test_detect_single_project_and_write_version(tmp_path, rel, content):
    root = tmp_path / "app"
    write(root, rel, content)
    [p] = proj.detect(root)
    assert (p.path, p.tag("2.0.1"), p.fragments, p.version_files) == (".", "v2.0.1", "changelog.d", [rel])
    proj.write_version(root, rel, "2.1.0")
    assert proj.read_version(root, rel) == "2.1.0"
    assert (root / rel).read_text().replace("2.1.0", "2.0.0") == content  # nothing else changed


def test_config_overrides_detection(market):
    write(market, ".amin.json", json.dumps({"projects": [
        {"name": "core", "path": "plugins/alpha",
         "version_files": ["plugins/alpha/.claude-plugin/plugin.json"], "tag": "core/{version}"}]}))
    [core] = proj.detect(market)
    assert core.tag("1.0.0") == "core/1.0.0" and core.fragments == "changelog.d/core"


def test_owner_of_picks_the_project(market):
    projects = proj.detect(market)
    assert proj.owner_of(projects, "plugins/beta/main.py").name == "beta"
    assert proj.owner_of(projects, "README.md") is None


# ---------------------------------------------------------------- notes and changelog


def test_notes_add_list_and_problems(market):
    alpha = projects_of(market)["alpha"]
    fragments.add(market, alpha, "added", "Batch edits.", "12")
    fragments.add(market, alpha, "added", "Another one.", "12")   # same id -> 12-2
    write(market, "changelog.d/alpha/oops.txt.md", "x")
    write(market, "changelog.d/alpha/13.fixd.md", "typo")
    write(market, "changelog.d/alpha/README.md", "rules")
    notes, problems = fragments.pending(market, alpha)
    assert sorted(n.path.rsplit("/", 1)[-1] for n in notes) == ["12-2.added.md", "12.added.md"]
    assert len(problems) == 2 and any("type must be one of" in p for p in problems)
    with pytest.raises(ValueError):
        fragments.add(market, alpha, "feature", "x", "1")


def test_grouped_sections_and_bullets():
    notes = [fragments.Fragment("a", "7", "fixed", "Crash on empty input."),
             fragments.Fragment("b", "8", "added", "- Outline mode\n- Symbol reads"),
             fragments.Fragment("c", "slug", "added", "Stats\nfor tokens.")]
    assert fragments.grouped(notes) == {
        "Added": ["- Outline mode (#8)", "- Symbol reads (#8)", "- Stats for tokens."],
        "Fixed": ["- Crash on empty input. (#7)"],
    }


def test_changelog_insert_and_extract(tmp_path):
    path = tmp_path / "CHANGELOG.md"
    changelog.insert(path, "alpha", "0.1.0", "2026-10-01", {"Added": ["- First."]})
    changelog.insert(path, "alpha", "0.2.0", "2026-10-06", {"Fixed": ["- Second."]})
    text = path.read_text()
    assert text.startswith("# Changelog\n\nAll notable changes to alpha")
    assert text.index("## [0.2.0] - 2026-10-06") < text.index("## [0.1.0] - 2026-10-01")
    assert changelog.extract(path, "0.2.0") == "### Fixed\n- Second."
    assert changelog.extract(path, "0.1.0") == "### Added\n- First."
    with pytest.raises(ValueError):
        changelog.insert(path, "alpha", "0.2.0", "2026-10-06", {"Fixed": ["- again"]})


# ---------------------------------------------------------------- plan and prepare


def plan_by_name(root):
    return {pl.project.name: pl for pl in release.plan(root, gitops.Runner(root), proj.detect(root))}


def test_plan_first_release(market):
    plans = plan_by_name(market)
    assert plans["alpha"].status == "needs-notes" and plans["alpha"].next == "0.1.0"
    fragments.add(market, projects_of(market)["alpha"], "added", "Initial release.", "1")
    assert plan_by_name(market)["alpha"].status == "first-release"


def test_plan_after_tags(market):
    _git(market, "tag", "-a", "alpha-v0.1.0", "-m", "x")
    _git(market, "tag", "-a", "beta-v1.2.0", "-m", "x")
    assert plan_by_name(market)["alpha"].status == "nothing"
    write(market, "plugins/alpha/main.py", "x = 2\n")
    commit(market)
    assert plan_by_name(market)["alpha"].status == "needs-notes"   # changed without a note
    p = projects_of(market)
    fragments.add(market, p["alpha"], "fixed", "Bug.", "5")
    fragments.add(market, p["beta"], "breaking", "Renamed option.", "6")
    plans = plan_by_name(market)
    assert (plans["alpha"].status, plans["alpha"].next) == ("release", "0.1.1")
    assert plans["beta"].next == "2.0.0"


def test_prepare_bumps_writes_changelog_and_consumes_notes(market):
    _git(market, "tag", "-a", "alpha-v0.1.0", "-m", "x")
    alpha = projects_of(market)["alpha"]
    note = fragments.add(market, alpha, "added", "Outline mode.", "9")
    pl = plan_by_name(market)["alpha"]
    changed = release.prepare(market, [(pl, pl.next)], date="2026-10-06")
    assert proj.read_version(market, alpha.version_files[0]) == "0.2.0"
    assert changelog.extract(market / alpha.changelog, "0.2.0") == "### Added\n- Outline mode. (#9)"
    assert not note.exists() and set(changed) == {alpha.version_files[0], alpha.changelog,
                                                   "changelog.d/alpha/9.added.md"}
    with pytest.raises(release.ReleaseError):
        release.prepare(market, [(pl, "0.0.9")])


# ---------------------------------------------------------------- publish


def released_market(market):
    """alpha prepared for its first release, committed and pushed."""
    fragments.add(market, projects_of(market)["alpha"], "added", "Initial release.", "1")
    pl = plan_by_name(market)["alpha"]
    release.prepare(market, [(pl, pl.next)], date="2026-10-06")
    commit(market, "Release alpha 0.1.0")
    _git(market, "push", "-q", "origin", "main")
    return projects_of(market)["alpha"]


def _tags(root):
    return subprocess.run(["git", "tag"], cwd=root, capture_output=True, text=True).stdout.strip()


def test_publish_creates_tag_and_release(market):
    alpha = released_market(market)
    runner = FakeRunner(market)
    report = release.publish(market, runner, alpha)
    assert "CI green (1 checks)" in report[0]
    assert report[-1] == "release published: https://github.com/o/r/releases/tag/alpha-v0.1.0"
    remote_tags = subprocess.run(["git", "ls-remote", "--tags", "origin"], cwd=market, capture_output=True,
                                 text=True).stdout
    assert "refs/tags/alpha-v0.1.0" in remote_tags
    create = next(c for c in runner.gh_calls if c[:2] == ("release", "create"))
    assert create[2:5] == ("alpha-v0.1.0", "--title", "alpha 0.1.0")


def test_publish_dry_run_creates_nothing(market):
    alpha = released_market(market)
    report = release.publish(market, FakeRunner(market), alpha, dry_run=True)
    assert report[-1] == "dry run: nothing was created" and _tags(market) == ""


@pytest.mark.parametrize(("setup", "message"), [
    (lambda r: _git(r, "switch", "-q", "-c", "other"), "releases are cut from main"),
    (lambda r: write(r, "dirty.txt", "x"), "uncommitted changes"),
    (lambda r: (write(r, "more.txt", "x"), commit(r)), "is not the same commit as origin/main"),
    (lambda r: _git(r, "tag", "alpha-v0.1.0"), "already exists"),
])
def test_publish_refuses_unsafe_states(market, setup, message):
    alpha = released_market(market)
    setup(market)
    with pytest.raises(release.ReleaseError, match=message):
        release.publish(market, FakeRunner(market), alpha)


@pytest.mark.parametrize(("checks", "message"), [
    ([], "no CI results"),
    ([{"name": "test", "status": "in_progress"}], "CI still running: test"),
    ([{"name": "lint", "status": "completed", "conclusion": "failure"}], "CI failed: lint"),
])
def test_publish_requires_green_ci(market, checks, message):
    alpha = released_market(market)
    with pytest.raises(release.ReleaseError, match=message):
        release.publish(market, FakeRunner(market, checks=checks), alpha)
    assert _tags(market) == ""


def test_publish_requires_a_changelog_section(market):
    alpha = projects_of(market)["alpha"]
    with pytest.raises(release.ReleaseError, match="has no section for 0.1.0"):
        release.publish(market, FakeRunner(market), alpha)


# ---------------------------------------------------------------- the CI rule


def run_check(root, labels=()):
    return check.check(root, gitops.Runner(root), proj.detect(root), "main", list(labels))


def feature_branch(root):
    _git(root, "switch", "-q", "-c", "feat/x")


def test_check_requires_a_note_for_changed_projects(market):
    feature_branch(market)
    write(market, "plugins/alpha/main.py", "x = 3\n")
    commit(market)
    ok, lines = run_check(market)
    assert not ok and "alpha: files changed but no note in changelog.d/alpha/" in lines[0]
    assert run_check(market, ["no-changelog"])[0]
    fragments.add(market, projects_of(market)["alpha"], "fixed", "Fix.", "3")
    commit(market)
    assert run_check(market) == (True, ["alpha: ok (note added)"])


def test_check_accepts_release_prs_and_unrelated_files(market):
    _git(market, "tag", "-a", "alpha-v0.1.0", "-m", "x")
    fragments.add(market, projects_of(market)["alpha"], "added", "Outline mode.", "1")
    commit(market)
    feature_branch(market)
    write(market, "README.md", "# changed\n")
    commit(market)
    assert run_check(market) == (True, ["no project files changed: no note needed"])
    pl = plan_by_name(market)["alpha"]
    release.prepare(market, [(pl, pl.next)])   # bumps plugin.json, consumes the note
    commit(market)
    assert run_check(market) == (True, ["alpha: ok (release)"])


def test_check_rejects_bad_note_names(market):
    feature_branch(market)
    write(market, "changelog.d/alpha/4.feature.md", "x")
    write(market, "plugins/alpha/main.py", "x = 4\n")
    commit(market)
    ok, lines = run_check(market)
    assert not ok and "bad note name: changelog.d/alpha/4.feature.md" in lines[0]


def test_deleting_another_projects_note_is_not_a_release(market):
    # issue #33: deleting beta's pending note let an alpha change pass as a "release"
    fragments.add(market, projects_of(market)["beta"], "added", "Beta feature.", "1")
    commit(market)
    feature_branch(market)
    write(market, "plugins/beta/main.py", "y = 2\n")
    (market / "changelog.d/beta/1.added.md").unlink()
    commit(market)
    ok, lines = run_check(market)
    assert not ok and "beta: files changed but no note" in lines[0]


def test_empty_and_misplaced_notes_are_rejected(market):
    feature_branch(market)
    write(market, "plugins/alpha/main.py", "x = 5\n")
    write(market, "changelog.d/alpha/5.fixed.md", "  \n")
    write(market, "changelog.d/6.fixed.md", "Lost at the root.\n")
    write(market, "changelog.d/gamma/7.fixed.md", "No such project.\n")
    commit(market)
    ok, lines = run_check(market)
    text = "\n".join(lines)
    assert not ok
    assert "empty note: changelog.d/alpha/5.fixed.md" in text
    assert "misplaced note: changelog.d/6.fixed.md" in text
    assert "misplaced note: changelog.d/gamma/7.fixed.md" in text


# ---------------------------------------------------------------- triage


def test_triage_scan():
    old = (datetime.date.today() - datetime.timedelta(days=120)).isoformat()
    today = datetime.date.today().isoformat()
    issues = [
        {"number": 1, "title": "Login fails with expired token", "labels": [], "updatedAt": old},
        {"number": 2, "title": "Expired token makes login fail", "labels": [{"name": "bug"}],
         "updatedAt": old},
        {"number": 3, "title": "Dark mode for settings", "labels": [], "updatedAt": today},
    ]
    report = triage.scan(issues, ["bug", "enhancement"])
    assert "without labels (2):\n  #1 Login fails with expired token\n  #3 Dark mode for settings" in report
    assert "#1 ~ #2" in report and "#3 ~" not in report
    assert "no activity for 90+ days (2)" in report


def test_title_similarity_ignores_noise_words():
    assert triage.similarity("Add support for dark mode", "Fix the bug in dark mode") == 1.0
    assert triage.similarity("error", "bug") == 0.0


# ---------------------------------------------------------------- CLI, history, work


def test_cli_projects_plan_and_notes(market, monkeypatch, capsys):
    monkeypatch.chdir(market)
    assert cli.main(["projects"]) == 0
    assert "alpha        0.1.0    path=plugins/alpha" in capsys.readouterr().out
    assert cli.main(["fragment", "add", "alpha", "fixed", "Crash", "on", "start", "--id", "8"]) == 0
    assert "added changelog.d/alpha/8.fixed.md" in capsys.readouterr().out
    cli.main(["fragment", "list"])
    assert "alpha        fixed      changelog.d/alpha/8.fixed.md: Crash on start" in capsys.readouterr().out
    cli.main(["plan"])
    assert "alpha        first-release  0.1.0 -> 0.1.0" in capsys.readouterr().out
    assert cli.main(["prepare", "nope"]) == 1
    assert "unknown project 'nope'" in capsys.readouterr().err


def test_history_filters_by_project_path(market):
    prs = [{"number": 3, "title": "Alpha thing", "mergedAt": "2026-10-01T10:00:00Z",
            "files": [{"path": "plugins/alpha/main.py"}]},
           {"number": 4, "title": "Beta thing", "mergedAt": "2026-10-02T10:00:00Z",
            "files": [{"path": "plugins/beta/main.py"}]}]
    lines = release.history(market, FakeRunner(market, prs=prs), projects_of(market)["alpha"], None)
    assert lines == ["#3 Alpha thing (2026-10-01)"]


def test_work_start_creates_branch_and_worktree(market):
    issue = {"number": 42, "title": "Crash when cart is empty!", "body": "Steps...", "state": "OPEN",
             "labels": [{"name": "bug"}], "url": "https://github.com/o/r/issues/42"}
    out = cli.cmd_work_start(market, FakeRunner(market, issue=issue), "42")
    worktree = market.parent / "market-amin" / "42"
    assert "branch: fix/42-crash-when-cart-is-empty" in out and worktree.is_dir()
    branch = subprocess.run(["git", "branch", "--show-current"], cwd=worktree, capture_output=True, text=True)
    assert branch.stdout.strip() == "fix/42-crash-when-cart-is-empty"
    closed = dict(issue, state="CLOSED")
    with pytest.raises(gitops.CommandError, match="closed"):
        cli.cmd_work_start(market, FakeRunner(market, issue=closed), "42")


def test_session_note_and_help(capsys):
    assert cli.main(["hook", "session-start"]) == 0
    assert "amin helper: python3" in capsys.readouterr().out
    assert cli.main([]) == 2
