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


def git_out(root, *args):
    return subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True).stdout


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

    def __init__(self, root, checks=None, prs=None, issue=None, releases=(), fail_release=False):
        super().__init__(root)
        self.releases, self.fail_release = set(releases), fail_release
        self.pulls = {}   # commit sha -> PRs that contain it
        self.checks = checks if checks is not None else [{"name": "CI", "status": "completed",
                                                           "conclusion": "success"}]
        self.prs, self.issue, self.gh_calls = prs or [], issue, []

    def gh(self, *args, check=True):
        self.gh_calls.append(args)
        if args[:2] == ("release", "view"):
            if args[2] in self.releases:
                return json.dumps({"url": f"https://github.com/o/r/releases/tag/{args[2]}"})
            if check:
                raise gitops.CommandError("release not found")
            return ""
        if args[:2] == ("release", "create"):
            if self.fail_release:
                raise gitops.CommandError("gh release create: HTTP 502")
            self.releases.add(args[2])
            return f"https://github.com/o/r/releases/tag/{args[2]}\n"
        return json.dumps(self.gh_json(*args))

    def gh_json(self, *args):
        if not self.gh_calls or self.gh_calls[-1] != args:
            self.gh_calls.append(args)
        if args[:2] == ("repo", "view"):
            return {"nameWithOwner": "o/r"}
        if args[0] == "api" and args[1].endswith("/pulls"):
            return self.pulls.get(args[1].split("/")[-2], [])
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


def test_new_versions_go_below_unreleased(tmp_path):
    # issue #35: the new version was inserted above "## [Unreleased]"
    path = tmp_path / "CHANGELOG.md"
    path.write_text("# Changelog\n\n## [Unreleased]\n\n## [0.1.0] - 2026-10-01\n### Added\n- First.\n")
    changelog.insert(path, "alpha", "0.2.0", "2026-10-06", {"Fixed": ["- Second."]})
    text = path.read_text()
    assert text.index("## [Unreleased]") < text.index("## [0.2.0]") < text.index("## [0.1.0]")
    assert changelog.extract(path, "0.2.0") == "### Fixed\n- Second."


def test_a_version_override_below_what_the_notes_require_is_refused(market):
    # issue #35: with a breaking note, prepare beta=1.3.0 on 1.2.0 went through silently
    _git(market, "tag", "-a", "beta-v1.2.0", "-m", "x")
    fragments.add(market, projects_of(market)["beta"], "breaking", "Renamed option.", "6")
    pl = plan_by_name(market)["beta"]
    with pytest.raises(release.ReleaseError, match="breaking.*needs at least 2.0.0"):
        release.prepare(market, [(pl, "1.3.0")])
    assert proj.read_version(market, pl.project.version_files[0]) == "1.2.0"
    release.prepare(market, [(pl, "1.3.0")], allow_lower=True)
    assert proj.read_version(market, pl.project.version_files[0]) == "1.3.0"


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


def test_prepare_links_notes_to_the_pr_that_added_them(market):
    # issue #56: a note written before its PR existed had no PR link
    _git(market, "tag", "-a", "alpha-v0.1.0", "-m", "x")
    alpha = projects_of(market)["alpha"]
    fragments.add(market, alpha, "added", "Outline mode.", "outline")
    commit(market, "alpha: outline mode (#12)")                      # squash merge subject
    fragments.add(market, alpha, "fixed", "No crash on start.", "crash")
    commit(market, "alpha: fix the crash")
    runner = FakeRunner(market)
    sha = git_out(market, "rev-parse", "HEAD").strip()
    runner.pulls[sha] = [{"number": 14, "merged_at": "2026-10-05T10:00:00Z"}]
    pl = plan_by_name(market)["alpha"]
    release.prepare(market, [(pl, pl.next)], date="2026-10-06", runner=runner)
    text = changelog.extract(market / alpha.changelog, "0.2.0")
    assert "- Outline mode. (#12)" in text and "- No crash on start. (#14)" in text


def umbrella_market(market):
    write(market, ".claude-plugin/marketplace.json", json.dumps({"name": "market", "plugins": []}))
    write(market, "pyproject.toml", '[project]\nname = "market"\nversion = "0.1.0"\n')
    write(market, "CHANGELOG.md", "# Market changelog\n\n## [0.1.0] - 2026-10-01\n\nFirst.\n")
    commit(market)
    for tag in ("alpha-v0.1.0", "beta-v1.2.0", "market-v0.1.0"):
        _git(market, "tag", "-a", tag, "-m", "x")
    p = projects_of(market)
    fragments.add(market, p["alpha"], "added", "Outline mode.", "1")
    fragments.add(market, p["beta"], "fixed", "Bug.", "2")
    commit(market)
    _git(market, "switch", "-q", "-c", "release/2026-10-06")
    return market


def test_prepare_umbrella_releases_the_whole_repo_too(market):
    # issue #56: the umbrella tag and root CHANGELOG were made by hand
    umbrella_market(market)
    plans = plan_by_name(market)
    changed = release.prepare(market, [(plans["alpha"], "0.2.0"), (plans["beta"], "1.2.1")],
                              date="2026-10-06", umbrella=True)
    assert "pyproject.toml" in changed and "CHANGELOG.md" in changed
    assert proj.read_version(market, "pyproject.toml") == "0.2.0"
    section = changelog.extract(market / "CHANGELOG.md", "0.2.0")
    assert "| [alpha](plugins/alpha/CHANGELOG.md) | 0.2.0 |" in section
    assert "| [beta](plugins/beta/CHANGELOG.md) | 1.2.1 |" in section
    text = (market / "CHANGELOG.md").read_text()
    assert text.index("## [0.2.0]") < text.index("## [0.1.0]")
    umbrella = cli.find_project(market, proj.detect(market), "market")    # amin publish market
    assert (umbrella.name, umbrella.tag("0.2.0")) == ("market", "market-v0.2.0")
    assert changelog.extract(market / umbrella.changelog, "0.2.0")


def test_prepare_dry_run_checks_branch_and_tree_and_writes_nothing(market, monkeypatch, capsys):
    umbrella_market(market)
    monkeypatch.chdir(market)
    before = git_out(market, "status", "--porcelain")
    assert cli.main(["prepare", "--umbrella", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "dry run" in out and "alpha 0.2.0" in out and "market 0.2.0" in out and "### Added" in out
    assert git_out(market, "status", "--porcelain") == before
    assert proj.read_version(market, "pyproject.toml") == "0.1.0"
    write(market, "dirty.txt", "x")
    assert cli.main(["prepare", "--dry-run"]) == 1
    assert "uncommitted changes" in capsys.readouterr().err
    (market / "dirty.txt").unlink()
    _git(market, "switch", "-q", "main")
    assert cli.main(["prepare"]) == 1
    assert "on main" in capsys.readouterr().err


def test_release_candidates_then_promotion_to_final(market):
    # issue #69: no pre-releases
    _git(market, "tag", "-a", "beta-v1.2.0", "-m", "x")
    beta = projects_of(market)["beta"]
    fragments.add(market, beta, "added", "Dark mode.", "7")
    pl = plan_by_name(market)["beta"]
    assert release.rc_version(gitops.Runner(market), pl) == "1.3.0-rc.1"
    release.prepare(market, [(pl, "1.3.0-rc.1")], date="2026-10-06")
    assert proj.read_version(market, beta.version_files[0]) == "1.3.0-rc.1"
    assert changelog.extract(market / beta.changelog, "1.3.0-rc.1") == "### Added\n- Dark mode. (#7)"
    assert (market / "changelog.d/beta/7.added.md").exists()          # kept for the final release
    commit(market)
    _git(market, "tag", "-a", "beta-v1.3.0-rc.1", "-m", "x")
    pl = plan_by_name(market)["beta"]
    assert pl.next == "1.3.0" and release.rc_version(gitops.Runner(market), pl) == "1.3.0-rc.2"
    release.prepare(market, [(pl, pl.next)], date="2026-10-07")        # promotion to final
    assert proj.read_version(market, beta.version_files[0]) == "1.3.0"
    assert not (market / "changelog.d/beta/7.added.md").exists()
    assert proj.parse("1.3.0-rc.2") < proj.parse("1.3.0") and proj.is_prerelease("1.3.0-rc.2")


def test_package_lock_and_cargo_workspaces_are_versioned(tmp_path):
    node = tmp_path / "node"
    write(node, "package.json", '{\n  "name": "app",\n  "version": "1.0.0"\n}\n')
    write(node, "package-lock.json", json.dumps({
        "name": "app", "version": "1.0.0", "lockfileVersion": 3,
        "packages": {"": {"name": "app", "version": "1.0.0"},
                     "node_modules/dep": {"version": "4.5.6"}}}, indent=2) + "\n")
    [p] = proj.detect(node)
    assert p.version_files == ["package.json", "package-lock.json"]
    for vf in p.version_files:
        proj.write_version(node, vf, "1.1.0")
    lock = json.loads((node / "package-lock.json").read_text())
    assert lock["version"] == lock["packages"][""]["version"] == "1.1.0"
    assert lock["packages"]["node_modules/dep"]["version"] == "4.5.6"

    rust = tmp_path / "rust"
    write(rust, "Cargo.toml",
          '[workspace]\nmembers = ["crates/*"]\n\n[workspace.package]\nversion = "0.3.0"\n')
    write(rust, "crates/core/Cargo.toml", '[package]\nname = "core"\nversion.workspace = true\n')
    write(rust, "Cargo.lock", 'version = 4\n\n[[package]]\nname = "core"\nversion = "0.3.0"\n\n'
                              '[[package]]\nname = "serde"\nversion = "0.3.0"\n')
    [p] = proj.detect(rust)
    assert p.version_files == ["Cargo.toml", "Cargo.lock"]
    assert proj.read_version(rust, "Cargo.lock") == "0.3.0"
    for vf in p.version_files:
        proj.write_version(rust, vf, "0.4.0")
    lock = (rust / "Cargo.lock").read_text()
    assert 'name = "core"\nversion = "0.4.0"' in lock and 'name = "serde"\nversion = "0.3.0"' in lock
    assert proj.read_version(rust, "Cargo.toml") == "0.4.0"


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


def test_publish_resumes_after_the_release_step_failed(market):
    # issue #34: the tag was pushed, gh release create failed, and a retry stopped at "tag already exists"
    alpha = released_market(market)
    with pytest.raises(gitops.CommandError, match="502"):
        release.publish(market, FakeRunner(market, fail_release=True), alpha)
    assert "alpha-v0.1.0" in _tags(market)
    runner = FakeRunner(market)
    report = release.publish(market, runner, alpha)
    assert "tag alpha-v0.1.0 already pushed" in "\n".join(report)
    assert report[-1] == "release published: https://github.com/o/r/releases/tag/alpha-v0.1.0"
    with pytest.raises(release.ReleaseError, match="already published"):
        release.publish(market, FakeRunner(market, releases={"alpha-v0.1.0"}), alpha)


def test_publish_dry_run_creates_nothing(market):
    alpha = released_market(market)
    report = release.publish(market, FakeRunner(market), alpha, dry_run=True)
    assert report[-1] == "dry run: nothing was created" and _tags(market) == ""


@pytest.mark.parametrize(("setup", "message"), [
    (lambda r: _git(r, "switch", "-q", "-c", "other"), "releases are cut from main"),
    (lambda r: write(r, "dirty.txt", "x"), "uncommitted changes"),
    (lambda r: (write(r, "more.txt", "x"), commit(r)), "is not the same commit as origin/main"),
    (lambda r: _git(r, "tag", "alpha-v0.1.0", "HEAD~1"), "already exists on another commit"),
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


def test_history_compares_real_times_and_asks_github_for_every_pr_since_the_tag(market):
    # issue #85: a +03:00 tag date compared as text against GitHub's UTC dropped PRs; only 200 were read
    import os
    write(market, "plugins/alpha/main.py", "x = 9\n")
    _git(market, "add", "-A")
    env = {**os.environ, "GIT_COMMITTER_DATE": "2026-10-01T12:00:00+03:00"}
    subprocess.run(["git", "commit", "-q", "-m", "x"], cwd=market, env=env, check=True)
    _git(market, "tag", "-a", "alpha-v0.1.0", "-m", "x")
    prs = [{"number": 5, "title": "After the tag", "mergedAt": "2026-10-01T10:00:00Z",   # 13:00 +03:00
            "files": [{"path": "plugins/alpha/main.py"}]},
           {"number": 6, "title": "Before the tag", "mergedAt": "2026-10-01T08:59:00Z",
            "files": [{"path": "plugins/alpha/main.py"}]}]
    runner = FakeRunner(market, prs=prs)
    lines = release.history(market, runner, projects_of(market)["alpha"], "alpha-v0.1.0")
    assert lines == ["#5 After the tag (2026-10-01)"]
    call = next(c for c in runner.gh_calls if c[:2] == ("pr", "list"))
    assert "merged:>=2026-10-01" in " ".join(call)   # the date filter runs on GitHub, so no PR is cut off


def test_single_project_name_comes_from_the_manifest_not_the_folder(tmp_path):
    # issue #85: inside an amin work worktree (<repo>-amin/42) the project was named "42"
    for rel, content in (("package.json", '{"name": "@acme/app", "version": "1.0.0"}'),
                         ("pyproject.toml", '[project]\nname = "app"\nversion = "1.0.0"\n'),
                         ("App.csproj", "<Project><PropertyGroup><Version>1.0.0</Version>"
                                        "</PropertyGroup></Project>")):
        root = tmp_path / rel.replace(".", "-") / "repo-amin" / "42"
        write(root, rel, content)
        assert proj.detect(root)[0].name in ("@acme/app", "app", "App"), rel


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


# ---------------------------------------------------------------- a repo like psf/black (#52)

BLACK_PYPROJECT = '''[tool.black]
line-length = 88
target-version = ["py310"]

[build-system]
requires = ["hatch-fancy-pypi-readme", "hatch-vcs>=0.3.0", "hatchling>=1.27.0"]
build-backend = "hatchling.build"

[project]
name = "black"
description = "The uncompromising code formatter."
requires-python = ">=3.10"
dynamic = ["readme", "version"]

[tool.hatch.version]
source = "vcs"

[tool.hatch.build.hooks.vcs]
version-file = "src/_black_version.py"
template = """
version = "{version}"
"""
'''


def black_repo(tmp_path, files=None):
    return init_repo(tmp_path / "black", {"pyproject.toml": BLACK_PYPROJECT, "src/black/__init__.py": "",
                                          **(files or {})})


def test_a_version_from_git_tags_is_never_written_into_pyproject(tmp_path):
    # issue #152: the hatch-vcs template `version = "{version}"` was read as the version and overwritten
    black = black_repo(tmp_path)
    assert proj.read_version(black, "pyproject.toml") is None
    [p] = proj.detect(black)
    assert (p.name, p.version_files) == ("black", [])
    _git(black, "tag", "-a", p.tag("26.10.0"), "-m", "x")
    fragments.add(black, p, "fixed", "Test note", "1")
    pl = plan_by_name(black)["black"]
    assert (pl.status, pl.current) == ("release", "26.10.0") and not pl.problems
    changed = release.prepare(black, [(pl, "26.11.0")], date="2026-10-08")
    assert "pyproject.toml" not in changed
    assert (black / "pyproject.toml").read_text() == BLACK_PYPROJECT
    assert changelog.latest(black / p.changelog) == "26.11.0"   # what publish tags


def test_bare_version_tags_are_found(tmp_path, monkeypatch, capsys):
    # issue #153: black tags 26.10.0 (no "v"), so amin saw no tag and treated 74 releases as a first one
    black = black_repo(tmp_path)
    for tag in ("26.5.1", "26.10.0"):
        _git(black, "tag", "-a", tag, "-m", "x")
    [p] = proj.detect(black)
    assert (p.tag("26.11.0"), p.tag_prefix()) == ("26.11.0", "")
    assert gitops.last_tag(gitops.Runner(black), p.tag_prefix()) == "26.10.0"
    assert plan_by_name(black)["black"].current == "26.10.0"
    monkeypatch.chdir(black)
    assert cli.main(["projects"]) == 0
    assert "last tag=26.10.0" in capsys.readouterr().out
    _git(black, "tag", "-a", "v26.11.0", "-m", "x")      # a v tag wins when both styles exist
    assert proj.detect(black)[0].tag("1.0.0") == "v1.0.0"


def test_history_without_a_tag_is_bounded(market):
    # issue #153: with no tag, history asked GitHub for 5000 PRs with their files and timed out
    runner = FakeRunner(market, prs=[])
    release.history(market, runner, projects_of(market)["alpha"], None)
    call = next(c for c in runner.gh_calls if c[:2] == ("pr", "list"))
    assert int(call[call.index("--limit") + 1]) == release.UNTAGGED_LIMIT <= 300


BLACK_CHANGES = """# Change Log

## Unreleased

<!-- PR authors:
     Please include the PR number in the changelog entry, not the issue number -->

### Highlights

<!-- Include any especially major or disruptive changes here -->

### Stable style

- Keep repeated lines outside the selected `--line-ranges` unchanged (#5436)

## Version 26.10.0

### Stable style

- Fix a crash on empty `--line-ranges` (#5400)

### Packaging

- Drop support for Python 3.9 (#5401)

## Version 26.5.1

### Stable style

- Fix the 26.5.0 regression (#5300)
"""


def test_changes_md_and_version_headings_are_recognised(tmp_path):
    # issue #154: amin made a new CHANGELOG.md, appended after the oldest release, and found no notes
    black = black_repo(tmp_path, {"CHANGES.md": BLACK_CHANGES})
    [p] = proj.detect(black)
    assert p.changelog == "CHANGES.md"
    path = black / p.changelog
    assert changelog.extract(path, "26.10.0") == (
        "### Stable style\n\n- Fix a crash on empty `--line-ranges` (#5400)\n\n"
        "### Packaging\n\n- Drop support for Python 3.9 (#5401)")
    assert changelog.has_version(path, "26.5.1") and changelog.latest(path) == "26.10.0"
    changelog.insert(path, "black", "26.11.0", "2026-10-08", {"Fixed": ["- Test note (#1)"]})
    text = path.read_text()
    assert text.index("## Unreleased") < text.index("## Version 26.11.0\n") < text.index("## Version 26.10.0")
    assert "2026-10-08" not in text                       # black's headings carry no date
    assert changelog.extract(path, "26.11.0") == "### Fixed\n- Test note (#1)"
    assert changelog.latest(path) == "26.11.0"


def test_calendar_versions_are_detected_and_bumped_by_date():
    # issue #155: black's 26.10.0 (YY.M.patch) got a SemVer patch, 26.10.1, in November
    today = datetime.date(2026, 11, 3)
    assert proj.is_calver(["26.10.0", "26.5.1", "26.5.0", "25.12.0"], today)
    assert proj.is_calver(["2026.10.0"], today)
    assert not proj.is_calver(["1.2.0", "0.3.0"], today) and not proj.is_calver([], today)
    assert not proj.is_calver(["26.13.0"], today) and not proj.is_calver(["27.1.0"], today)
    assert proj.calver_bump("26.10.0", today)[0] == "26.11.0"
    assert proj.calver_bump("26.10.0", datetime.date(2026, 10, 20))[0] == "26.10.1"
    assert proj.calver_bump("2026.10.0", today)[0] == "2026.11.0"
    assert proj.calver_bump("25.12.1", datetime.date(2026, 1, 5))[0] == "26.1.0"


def test_plan_and_prepare_use_the_calendar_for_calver_projects(tmp_path, monkeypatch):
    black = black_repo(tmp_path)
    for tag in ("26.5.1", "26.10.0"):
        _git(black, "tag", "-a", tag, "-m", "x")
    monkeypatch.setattr(release, "today", lambda: datetime.date(2026, 11, 3))
    fragments.add(black, proj.detect(black)[0], "breaking", "Drop Python 3.9", "1")
    pl = plan_by_name(black)["black"]
    assert (pl.status, pl.next) == ("release", "26.11.0") and "calendar" in pl.reason
    release.prepare(black, [(pl, pl.next)], date="2026-11-03")   # a breaking note is not "too low"
    assert changelog.latest(black / "CHANGELOG.md") == "26.11.0"


def test_history_skips_the_release_pr_of_the_tag_and_marks_bot_and_ci_prs(tmp_path):
    # issue #158: "Prepare release 26.5.1" (the tagged commit) was listed after 26.5.1, bots were not marked
    black = black_repo(tmp_path)
    _git(black, "tag", "-a", "26.5.1", "-m", "x")
    tagged = git_out(black, "rev-parse", "26.5.1^{commit}").strip()
    tag_time = git_out(black, "log", "-1", "--format=%cI", "26.5.1").strip()
    later = (datetime.datetime.fromisoformat(tag_time) + datetime.timedelta(seconds=5)).isoformat()
    prs = [
        {"number": 5140, "title": "Prepare release 26.5.1", "mergedAt": later, "mergeCommit": {"oid": tagged},
         "author": {"login": "cobaltt7", "is_bot": False}, "files": [{"path": "CHANGES.md"}]},
        {"number": 5141, "title": "Bump actions/checkout from 4 to 5", "mergedAt": "2099-01-02T00:00:00Z",
         "mergeCommit": {"oid": "a" * 40}, "author": {"login": "app/dependabot", "is_bot": True},
         "files": [{"path": ".github/workflows/test.yml"}]},
        {"number": 5142, "title": "Run tests on Python 3.14", "mergedAt": "2099-01-03T00:00:00Z",
         "mergeCommit": {"oid": "b" * 40}, "author": {"login": "JelleZijlstra", "is_bot": False},
         "files": [{"path": ".github/workflows/test.yml"}, {"path": ".pre-commit-config.yaml"}]},
        {"number": 5143, "title": "Fix a crash", "mergedAt": "2099-01-04T00:00:00Z",
         "mergeCommit": {"oid": "c" * 40}, "author": {"login": "someone", "is_bot": False},
         "files": [{"path": "src/black/__init__.py"}]},
    ]
    p = proj.detect(black)[0]
    lines = release.history(black, FakeRunner(black, prs=prs), p, "26.5.1")
    assert lines == ["#5141 Bump actions/checkout from 4 to 5 (2099-01-02) [bot]",
                     "#5142 Run tests on Python 3.14 (2099-01-03) [ci only]",
                     "#5143 Fix a crash (2099-01-04)"]


@pytest.mark.parametrize("content", [
    '[project]\nname = "app"\nversion = "2.0.0"\n',
    '[tool.poetry]\nname = "app"\nversion = "2.0.0"\n',
    '[tool.x]\nversion = "9.9.9"\n\n[project]\nname = "app"\nversion = "2.0.0"\n',
])
def test_pyproject_version_is_read_only_from_project_or_poetry(tmp_path, content):
    write(tmp_path, "pyproject.toml", content)
    assert proj.read_version(tmp_path, "pyproject.toml") == "2.0.0"
    proj.write_version(tmp_path, "pyproject.toml", "2.1.0")
    assert (tmp_path / "pyproject.toml").read_text() == content.replace("2.0.0", "2.1.0")
