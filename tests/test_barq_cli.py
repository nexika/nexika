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
    assert "barq 'read:PATH'" in res.stdout
    exports = env_file.read_text()
    assert "export BARQ_SESSION='abc-123'" in exports
    assert f'export PATH="{BARQ_ROOT / "bin"}:$PATH"' in exports


def test_session_start_without_env_file_prints_full_command(barq_env):
    env = {k: v for k, v in os.environ.items() if k != "CLAUDE_ENV_FILE"}
    res = subprocess.run([sys.executable, str(BARQ_ROOT / "hooks" / "session_start.py")],
                         input='{"session_id": "s1"}', capture_output=True, text=True,
                         env={**env, "BARQ_HOME": str(barq_env / "h")})
    assert f"BARQ_SESSION=s1 python3 {BARQ_ROOT / 'bin' / 'barq'} 'read:PATH'" in res.stdout


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
