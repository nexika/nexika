"""barq end to end: the CLI against a real temporary git project."""
from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest
from conftest import BARQ_ROOT, _git

# ---------------------------------------------------------------- read


def test_read_full_then_unchanged_then_diff(project, barq_run):
    code, out = barq_run("read:src/app.py")
    assert code == 0
    assert "=== read src/app.py (11 lines) ===" in out and "5\t    def total(self):" in out

    _, out = barq_run("read:src/app.py")
    assert "(unchanged, 11 lines)" in out and "def total" not in out

    path = project / "src" / "app.py"
    path.write_text(path.read_text().replace("return 42", "return 43"))
    _, out = barq_run("read:src/app.py")
    assert "6\t        return 43" in out  # small file: the whole text is cheaper than a diff


def test_changed_big_file_returns_only_the_diff(project, barq_run):
    path = project / "src" / "big.py"
    path.write_text("".join(f"x{i} = {i}\n" for i in range(80)))
    barq_run("read:src/big.py")
    path.write_text(path.read_text().replace("x40 = 40", "x40 = 400"))
    _, out = barq_run("read:src/big.py")
    assert "changed since your last read: diff, 80 lines now" in out
    assert "-x40 = 40\n+x40 = 400" in out and "x10 = 10" not in out


def test_full_and_fresh_bypass_the_cache(project, barq_run):
    barq_run("read:src/app.py")
    assert "def total" in barq_run("read:src/app.py:full")[1]
    assert "def total" in barq_run("--fresh", "read:src/app.py")[1]


def test_cache_needs_a_session(project, barq_run, monkeypatch):
    monkeypatch.delenv("BARQ_SESSION")
    barq_run("read:src/app.py")
    assert "def total" in barq_run("read:src/app.py")[1]


def test_read_range_symbol_and_outline(project, barq_run):
    _, out = barq_run("read:src/app.py:5:6", "read:src/app.py@Cart.total", "read:src/app.py:outline")
    assert "(lines 5-6 of 11)" in out
    assert "read src/app.py@Cart.total (lines 5-6 of 11)" in out
    assert "4-6     class Cart" in out and "    def total(self)" in out


def test_a_symbol_read_that_may_be_partial_says_so(project, barq_run):
    (project / "broken.js").write_text("function broken() {\n" + "  x();\n" * 80)
    _, out = barq_run("read:broken.js@broken")
    assert "may be cut short" in out and "read:broken.js:1:" in out
    assert "may be cut short" not in barq_run("read:src/app.py@Cart.total")[1]


def test_read_unknown_symbol_lists_available(project, barq_run):
    code, out = barq_run("read:src/app.py@Nope")
    assert code == 1 and "[ERROR]" in out and "Symbols: Cart, Cart.total, helper" in out


def test_read_errors(project, barq_run):
    (project / "img.bin").write_bytes(b"\x00\x01\x02")
    code, out = barq_run("read:missing.py", "read:img.bin", "read:src")
    assert code == 1
    assert "no such file" in out and "looks binary" in out and "is a directory" in out


def test_large_file_is_truncated_with_next_step(project, barq_run):
    (project / "big.txt").write_text("".join(f"line {i}\n" for i in range(1, 1601)))
    _, out = barq_run("read:big.txt")
    assert "(lines 1-1500 of 1600, truncated)" in out and "Next: read:big.txt:1501:3000" in out


def test_read_masks_secrets(project, barq_run):
    (project / ".env").write_text("DB_PASSWORD=hunter2\n")
    _, out = barq_run("read:.env")
    assert "hunter2" not in out and "DB_PASSWORD=[masked]" in out and "1 secret(s) masked" in out
    assert "read:.env:raw" in out  # masked lines must not be copied into an edit


def test_raw_read_returns_exact_text_and_keeps_the_cache(project, barq_run):
    (project / ".env").write_text("DB_PASSWORD=hunter2\n")
    _, out = barq_run("read:.env:raw")
    assert "DB_PASSWORD=hunter2" in out and "[masked]" not in out
    _, out = barq_run("read:.env")
    assert "unchanged" in out


# ---------------------------------------------------------------- fence


def test_path_fence_blocks_outside_and_symlink_escape(project, barq_run, tmp_path):
    outside = tmp_path / "outside.txt"
    outside.write_text("secret")
    (project / "link.txt").symlink_to(outside)
    code, out = barq_run(f"read:{outside}", "read:../outside.txt", "read:link.txt")
    assert code == 1 and out.count("is outside the project") == 3 and "secret" not in out


def test_path_fence_can_be_lifted(project, barq_run, tmp_path, monkeypatch):
    outside = tmp_path / "outside.txt"
    outside.write_text("hello")
    monkeypatch.setenv("BARQ_ALLOW_OUTSIDE", "1")
    assert "hello" in barq_run(f"read:{outside}")[1]


# ---------------------------------------------------------------- search


def test_grep_respects_gitignore_and_reports_counts(project, barq_run):
    _, out = barq_run("grep:TODO")
    assert "2 matches in 2 files" in out
    assert "src/app.py:10: # TODO: remove" in out and "ignored/" not in out


def test_grep_limit_and_invalid_regex(project, barq_run):
    _, out = barq_run("grep:return:src:1", "grep:(unclosed")
    assert "... 2 more matches" in out
    assert "invalid regex" in out


def test_grep_json_form_with_colon_and_options(project, barq_run):
    req = json.dumps([{"op": "grep", "pattern": "todo: REMOVE", "ignore_case": True, "glob": "*.py"}])
    _, out = barq_run(req)
    assert "1 matches in 1 files" in out


def test_glob_tree_map(project, barq_run):
    _, out = barq_run("glob:**/*.py", "tree::1", "map:src")
    assert "glob **/*.py in .: 2 files" in out and "src/app.py\nsrc/util.py" in out
    assert "src/ (2 files)" in out
    assert "src/app.py\n  L4 class Cart\n  L5   def total(self)" in out


def test_map_names_the_files_without_symbols(project, barq_run):
    # #170: "25 of 25 source files" listed 21; const.py and __main__.py were left out silently
    (project / "src" / "const.py").write_text("DEFAULT_LINE_LENGTH = 88\n")
    _, out = barq_run("map:src")
    assert "map src: 3 of 3 source files" in out
    assert "no symbols: src/const.py" in out


# ---------------------------------------------------------------- info / run / custom ops


def test_info_detects_dotnet_and_node(project, barq_run):
    (project / "Shop.sln").write_text("")
    (project / "src" / "Shop.csproj").write_text("<Project/>")
    (project / "web").mkdir()
    (project / "web" / "package.json").write_text('{"scripts": {"test": "vitest", "build": "vite build"}}')
    (project / "web" / "pnpm-lock.yaml").write_text("")
    _, out = barq_run("info")
    assert "stacks: dotnet (Shop.sln); node (pnpm) (web/package.json)" in out
    assert "test   dotnet test   [dotnet]" in out
    assert "also detected:" in out and "cd web && pnpm test" in out


def test_info_prefers_the_root_python_suite_over_a_nested_package(project, barq_run):
    # #47: this repo's plugins/lawha/engine/package.json won run:test over the root pytest suite
    (project / "pyproject.toml").write_text("[project]\nname = 'x'\n")
    (project / "tests").mkdir()
    (project / "tests" / "test_app.py").write_text("def test_x():\n    pass\n")
    engine = project / "plugins" / "lawha" / "engine"
    engine.mkdir(parents=True)
    (engine / "package.json").write_text('{"scripts": {"test": "node --test"}}')
    _, out = barq_run("info")
    assert "stacks: python (pyproject.toml); node (npm) (plugins/lawha/engine/package.json)" in out
    assert "test   python -m pytest   [python]" in out
    assert "also detected:" in out and "cd plugins/lawha/engine && npm test" in out


def test_info_keeps_a_root_node_project_first(project, barq_run):
    (project / "package.json").write_text('{"scripts": {"test": "vitest"}}')
    (project / "pyproject.toml").write_text("[project]\nname = 'x'\n")
    (project / "tests").mkdir()
    (project / "tests" / "test_app.py").write_text("def test_x():\n    pass\n")
    _, out = barq_run("info")
    assert "test   npm test   [node (npm)]" in out


def test_run_build_does_not_pick_a_nested_build_when_the_root_has_none(project, barq_run):
    # #109: with no root build, run:build ran `cd benchmarks/starter && npm run build`
    (project / "pyproject.toml").write_text("[project]\nname = 'x'\n")
    for sub in ("benchmarks/starter", "plugins/x/engine"):
        (project / sub).mkdir(parents=True)
        (project / sub / "package.json").write_text(
            '{"scripts": {"build": "node -e \\"require(\'fs\').writeFileSync(\'built\', \'\')\\""}}')
    code, out = barq_run("run:build")
    assert code == 1
    assert "no 'build' command at the project root" in out
    assert "cd benchmarks/starter && npm run build" in out
    assert "cd plugins/x/engine && npm run build" in out
    assert not (project / "benchmarks" / "starter" / "built").exists()
    _, out = barq_run("info")
    assert "build  -" in out and "cd benchmarks/starter && npm run build" in out


def test_barq_json_commands_override_and_run_compresses(project, barq_run):
    script = (
        "import sys; print('noise\\n' * 50); "
        "print('FAILED tests/t.py::test_x - assert 1 == 2'); "
        "print('==== 1 failed, 3 passed in 0.10s ===='); sys.exit(1)"
    )
    (project / ".barq.json").write_text(json.dumps({"commands": {"test": f'{sys.executable} -c "{script}"'}}))
    code, out = barq_run("run:test")
    assert code == 1
    assert "run test: FAILED (exit 1)" in out
    assert "1 failed, 3 passed in 0.10s" in out and "FAILED tests/t.py::test_x" in out
    assert out.count("noise") == 1  # only in the echoed command line, none of the 50 output lines
    assert "52 output lines -> 1 shown" in out


def test_run_json_command_and_missing_command(project, barq_run):
    req = json.dumps([{"op": "run", "cmd": f"{sys.executable} -c \"print('hi')\""},
                      {"op": "run", "what": "deploy"}])
    code, out = barq_run(req)
    assert code == 1
    assert ": ok ===" in out and "no 'deploy' command detected" in out


def test_run_timeout(project, barq_run):
    req = json.dumps({"op": "run", "cmd": f"{sys.executable} -c \"import time; time.sleep(5)\"",
                      "timeout": 1})
    code, out = barq_run(req)
    assert code == 1 and "TIMED OUT" in out


def test_custom_op_from_barq_json(project, barq_run):
    (project / ".barq.json").write_text(json.dumps({"ops": {
        "hello": {"cmd": f"{sys.executable} -c \"import sys; print('hi', *sys.argv[1:])\" {{args}}",
                  "safety": "read", "description": "say hi"}}}))
    _, out = barq_run("hello:there")
    assert "=== hello: ok" in out and "hi there" in out
    assert "say hi" in barq_run("ops")[1]


def test_invalid_barq_json_is_reported_not_fatal(project, barq_run):
    (project / ".barq.json").write_text("{nope")
    code, out = barq_run("read:README.md")
    assert code == 0 and "warning: ignoring invalid .barq.json" in out


# ---------------------------------------------------------------- git-status


def test_git_status_on_main_with_changes_says_branch_first(project, barq_run):
    (project / "new.txt").write_text("x")
    _, out = barq_run("git-status")
    assert "branch: main (no upstream)" in out
    assert "1 untracked" in out and "new.txt" in out
    assert "create a branch first" in out


def test_git_status_feature_branch_staged_and_clean(project, barq_run):
    _git(project, "switch", "-q", "-c", "feat/x")
    (project / "src" / "util.py").write_text("changed\n")
    _git(project, "add", "-A")
    assert "next: commit the staged changes" in barq_run("git-status")[1]
    _git(project, "commit", "-q", "-m", "change")
    assert "publish the branch: git push -u origin feat/x" in barq_run("git-status")[1]


def test_git_status_outside_git(barq_env, barq_run, monkeypatch):
    plain = barq_env / "plain"
    plain.mkdir()
    monkeypatch.chdir(plain)
    code, out = barq_run("git-status")
    assert code == 1 and "not a git repository" in out


# ---------------------------------------------------------------- CLI behaviour


def test_unknown_op_suggests_close_names(project, barq_run):
    code, out = barq_run("raed:src/app.py")
    assert code == 1 and "Did you mean: read" in out


def test_bad_json_requests(project, barq_run):
    assert "invalid JSON input" in barq_run("[oops")[1]
    assert 'needs an "op"' in barq_run('[{"path": "x"}]')[1]
    assert "bad arguments for read" in barq_run('{"op": "read", "nope": 1}')[1]


def test_batch_keeps_order_and_json_output(project, barq_run):
    code, out = barq_run("--json", "read:README.md", "raed:x", "glob:*.md")
    data = json.loads(out)
    assert [d["ok"] for d in data] == [True, False, True]
    assert data[0]["label"].startswith("read README.md") and data[2]["label"].startswith("glob")
    assert code == 1


def test_help_ops_version(project, barq_run):
    assert barq_run()[0] == 2
    assert "read:PATH@SYMBOL" in barq_run("ops")[1]
    assert "git-status[:full]" in barq_run("help", "git-status")[1]
    assert barq_run("version")[1].startswith("barq 0.1.0")


def test_stats_record_savings(project, barq_run):
    barq_run("read:src/app.py", "glob:*.md")
    barq_run("read:src/app.py")   # unchanged -> saved bytes + cache hit
    _, out = barq_run("stats")
    assert "calls: 2, ops: 3" in out
    assert "round-trips saved: 1" in out
    assert "seen-before cache: 1 read(s)" in out
    assert "savings by op: read" in out
    assert "period must be one of" in barq_run("stats:year")[1]


# ---------------------------------------------------------------- launcher and hook


def run_hook(stdin: dict, env: dict) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(BARQ_ROOT / "hooks" / "session_start.py")],
        input=json.dumps(stdin), capture_output=True, text=True, env={**os.environ, **env},
    )


def test_session_start_puts_barq_on_path(barq_env):
    env_file = barq_env / "claude.env"
    res = run_hook({"session_id": "abc-123", "source": "startup"},
                   {"CLAUDE_ENV_FILE": str(env_file), "BARQ_HOME": str(barq_env / "h")})
    assert res.returncode == 0
    assert "barq run:test" in res.stdout
    exports = env_file.read_text()
    assert "export BARQ_SESSION='abc-123'" in exports
    assert f'export PATH="{BARQ_ROOT / "bin"}:$PATH"' in exports


def test_session_start_without_env_file_prints_full_command(barq_env):
    env = {k: v for k, v in os.environ.items() if k != "CLAUDE_ENV_FILE"}
    res = subprocess.run([sys.executable, str(BARQ_ROOT / "hooks" / "session_start.py")],
                         input='{"session_id": "s1"}', capture_output=True, text=True,
                         env={**env, "BARQ_HOME": str(barq_env / "h")})
    assert f"BARQ_SESSION=s1 python3 {BARQ_ROOT / 'bin' / 'barq'} run:test" in res.stdout


def test_session_start_after_compact_resets_cache(project, barq_run, barq_env):
    barq_run("read:src/app.py")
    assert "unchanged" in barq_run("read:src/app.py")[1]
    run_hook({"session_id": "test-session", "source": "compact"},
             {"BARQ_HOME": os.environ["BARQ_HOME"], "CLAUDE_ENV_FILE": str(barq_env / "e")})
    assert "def total" in barq_run("read:src/app.py")[1]


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX launcher")
def test_bin_launcher_runs(project):
    res = subprocess.run([str(BARQ_ROOT / "bin" / "barq"), "read:README.md"],
                         capture_output=True, text=True)
    assert res.returncode == 0 and "# Demo" in res.stdout


# ---------------------------------------------------------------- issue #39: savings, capped reads, agents


def logged_ops():
    from barq import stats
    return [op for line in stats.log_path().read_text().splitlines() for op in json.loads(line)["ops"]]


def test_partial_reads_and_grep_use_the_built_in_tools_output_as_baseline(project, barq_run):
    (project / "big.py").write_text("".join(f"value_{i} = {i}  # padding padding\n" for i in range(1200)))
    barq_run("read:big.py:1:5")
    barq_run("grep:value_1:.")
    rng, grep = logged_ops()
    assert rng["baseline"] < 500            # Read with offset/limit returns about the same 5 lines, not 50 KB
    assert grep["baseline"] < 100           # Grep's default output is the file names


def test_stats_count_negative_savings(project, barq_run):
    from barq import stats
    stats.record([{"op": "read", "out": 3000, "baseline": 1000, "hit": False},
                  {"op": "grep", "out": 0, "baseline": 3048, "hit": False}], 1, "s", ".")
    _, out = barq_run("stats")
    assert "avoided: 1.0 KB" in out                 # 3048 - 2000 lost on the read, not 3 KB


def test_a_full_read_is_capped_near_25_kb_and_not_cached(project, barq_run):
    (project / "wide.txt").write_text("".join(f"{i:04d} " + "x" * 95 + "\n" for i in range(600)))  # 60 KB
    _, out = barq_run("read:wide.txt")
    assert "truncated" in out and "Next: read:wide.txt:" in out
    assert len(out.encode()) < 27_000
    _, again = barq_run("read:wide.txt")
    assert "unchanged" not in again                 # Claude never saw it all


def test_the_seen_before_cache_is_per_agent(project, barq_run, monkeypatch):
    barq_run("read:src/app.py")
    monkeypatch.setenv("BARQ_AGENT", "sub-1")       # a subagent has its own context
    assert "def total" in barq_run("read:src/app.py")[1]
    assert "unchanged" in barq_run("read:src/app.py")[1]
    monkeypatch.delenv("BARQ_AGENT")
    assert "unchanged" in barq_run("read:src/app.py")[1]


def test_subagent_start_tells_the_subagent_its_barq_agent_id(barq_env):
    res = subprocess.run([sys.executable, str(BARQ_ROOT / "hooks" / "subagent_start.py")],
                         input=json.dumps({"session_id": "s1", "agent_id": "ag-42", "agent_type": "Explore"}),
                         capture_output=True, text=True)
    assert res.returncode == 0
    context = json.loads(res.stdout)["hookSpecificOutput"]["additionalContext"]
    assert "BARQ_AGENT=ag-42" in context


def test_session_note_leaves_reads_and_searches_to_the_built_in_tools(barq_env):
    # #49: "prefer barq over cat/grep/find" kept Claude off Read, but Edit needs a prior Read
    env = {"CLAUDE_ENV_FILE": str(barq_env / "e"), "BARQ_HOME": str(barq_env / "h")}
    res = run_hook({"session_id": "s1"}, env)
    note = res.stdout
    assert "Prefer barq over" not in note and "'read:PATH'" not in note and "grep:" not in note
    assert "Read" in note and "Edit" in note
    for op in ("run:test", "git-status", "read:PATH:outline", "read:PATH@Symbol", "map"):
        assert op in note
