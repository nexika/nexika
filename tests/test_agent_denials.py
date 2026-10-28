"""benchmarks/agent/denials.py: which calls an unattended run denied, why, and one arm before and after."""

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "benchmarks" / "agent"))

import denials  # noqa: E402
from agentbench import summary  # noqa: E402

NO_SURFACE = ("Permission for this tool use was denied. It requires approval, and this session has no "
              "approval surface")


def _use(uid, command):
    return {"type": "assistant", "message": {"content": [
        {"type": "tool_use", "id": uid, "name": "Bash", "input": {"command": command}}]}}


def _result(uid, text, error=True):
    return {"type": "user", "message": {"content": [
        {"type": "tool_result", "tool_use_id": uid, "is_error": error, "content": text}]}}


def _hook(decision, reason):
    out = json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": decision,
                                             "permissionDecisionReason": reason}})
    return {"type": "system", "subtype": "hook_response", "hook_event": "PreToolUse", "stdout": out}


def _stream(*events, denied=()):
    done = {"type": "result", "permission_denials": [
        {"tool_name": "Bash", "tool_use_id": uid, "tool_input": {"command": cmd}} for uid, cmd in denied]}
    return [json.dumps(e) for e in (*events, done)]


def test_a_refusal_takes_its_reason_from_the_tool_result():
    lines = _stream(_use("t1", "python -c 'import sympy'"),
                    _result("t1", "PreToolUse:Bash hook error: haris: The Python code imports more than 32 "
                                  "modules, too many for haris to read each one. Nobody can answer..."),
                    denied=[("t1", "python -c 'import sympy'")])
    [call] = denials.denied_calls(lines)
    assert call["tool"] == "Bash" and call["input"] == {"command": "python -c 'import sympy'"}
    assert denials.kind(call["reason"]) == ("The Python code imports more than 32 modules, too many for "
                                            "haris to read each one.")


def test_an_ask_takes_its_reason_from_the_hook_between_the_call_and_its_result():
    lines = _stream(_hook("ask", "haris: Changes the current folder."),  # an earlier, allowed call's ask
                    _use("t0", "cd /x"), _result("t0", "ok", error=False),
                    _use("t1", "python - <<E"),
                    _hook("ask", "haris: `python` runs shell commands from inside the code."),
                    _result("t1", NO_SURFACE),
                    _use("t2", "ls"), _result("t2", "a b", error=False),
                    denied=[("t1", "python - <<E")])
    [call] = denials.denied_calls(lines)
    assert call["reason"] == "haris: `python` runs shell commands from inside the code."
    assert denials.kind(call["reason"]) == "`…` runs shell commands from inside the code."


def test_a_denial_with_no_hook_reason_is_named_as_such_and_bad_lines_are_skipped():
    lines = ["not json", "[1, 2]", "{broken", *_stream(_use("t1", "x"), _result("t1", NO_SURFACE),
                                                       denied=[("t1", "x")])]
    assert [c["reason"] for c in denials.denied_calls(lines)] == [denials.UNKNOWN]
    assert denials.denied_calls([]) == []


def test_kind_groups_calls_that_differ_only_in_names_and_details():
    a = "haris: haris could not read this command (a ' quote is never closed), so it cannot tell. More."
    b = "haris: haris could not read this command (a \" quote is never closed), so it cannot tell."
    assert denials.kind(a) == denials.kind(b) == "haris could not read this command, so it cannot tell."


def test_kinds_table_counts_calls_and_runs():
    by_run = {"r1": [{"reason": "haris: Too many. x"}, {"reason": "haris: Too many. y"}],
              "r2": [{"reason": "haris: Too many."}, {"reason": "haris: Other."}]}
    table = denials.kinds_table(by_run)
    assert "| Too many. | 3 | 2 |" in table and "| Other. | 1 | 1 |" in table


def _write(home, arm, rows):
    (home / "runs").mkdir(parents=True)
    with open(home / "results.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=summary.COLUMNS, extrasaction="ignore")
        w.writeheader()
        for task, denied, resolved in rows:
            w.writerow({"instance_id": task, "arm": arm, "run": 1, "valid": True, "resolved": resolved,
                        "regression": False, "cost_usd": 0.1, "permission_denials": denied})


def test_compare_pairs_one_arm_across_two_folders(tmp_path):
    _write(tmp_path / "before", "B", [("t1", 0, True), ("t2", 0, False), ("t3", 1, True)])
    _write(tmp_path / "after", "B", [("t1", 2, True), ("t2", 1, True), ("t4", 5, True)])
    before = denials.load(tmp_path / "before", "B", "A")
    after = denials.load(tmp_path / "after", "B", "B")
    out = denials.compare(before, after)
    assert "| permission_denials | 0.00 | 1.50 | +1.50 |" in out  # t1 and t2 only: t3, t4 are unpaired
    assert "| any_denial | 0% | 100% | +100 pts |" in out
    assert "| resolved | 50% | 100% | +50 pts |" in out
    assert "- any_denial: 2 tasks; only after 2, only before 0 (exact sign test p = 0.5)" in out
    assert "- After: 3 valid runs, 8 denials in all" in out


def test_run_denials_reads_only_the_arm_asked_for(tmp_path):
    for name in ("t1__B__r1", "t1__A__r1", "t2__B__r1"):
        (tmp_path / "runs" / name).mkdir(parents=True)
    stream = _stream(_use("t1", "x"), _result("t1", "PreToolUse:Bash hook error: haris: No."),
                     denied=[("t1", "x")])
    for name in ("t1__B__r1", "t1__A__r1"):
        (tmp_path / "runs" / name / "stream.jsonl").write_text("\n".join(stream) + "\n")
    (tmp_path / "runs" / "t2__B__r1" / "stream.jsonl").write_text("\n".join(_stream()) + "\n")
    assert list(denials.run_denials(tmp_path, "B")) == ["t1__B__r1"]
