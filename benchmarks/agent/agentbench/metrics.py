"""Read one run's stream-json output and diff into plain numbers."""

import json
import re

# A Bash command that runs the project's tests (the agent checking its work).
TEST_COMMAND = re.compile(r"\b(pytest|py\.test|runtests\.py|bin/test|unittest|tox|nox)\b|manage\.py test")

# A run that ended on one of these never did the task: it is redone, not counted as a failure.
API_FAILURE = re.compile(r"usage limit|rate limit|overloaded|API Error|authentication|"
                         r"Invalid API key|OAuth token|credit balance", re.I)

NEXIKA = ("amin", "barq", "bayan", "hafiz", "haris", "itqan", "lawha", "manar", "mizan", "prof",
          "siyaq", "tabib")


def _events(lines):
    for line in lines:
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if isinstance(event, dict):
            yield event


def _plugin_name(entry):
    name = entry.get("name", "") if isinstance(entry, dict) else str(entry)
    return name.split("@")[0]


def parse_stream(lines):
    out = {
        "session_id": "", "model_used": "", "plugins_loaded": [],
        "result": "", "is_error": None, "cost_usd": None, "duration_ms": None, "api_ms": None,
        "turns": None, "input_tokens": 0, "output_tokens": 0, "cache_read_tokens": 0,
        "cache_write_tokens": 0, "tool_calls": 0, "failed_tool_calls": 0, "bash_calls": 0,
        "permission_denials": 0, "hook_runs": 0, "hook_errors": 0,
        "test_commands": 0, "ran_tests": False, "first_prompt_tokens": None, "hook_output_chars": 0,
        "result_text": "",
    }
    for event in _events(lines):
        kind, sub = event.get("type"), event.get("subtype", "")
        if kind == "system" and sub == "init":
            out["session_id"] = event.get("session_id", "")
            out["model_used"] = event.get("model", "")
            out["plugins_loaded"] = sorted(_plugin_name(p) for p in event.get("plugins") or [])
        elif kind == "system" and sub == "hook_response":
            out["hook_runs"] += 1
            out["hook_output_chars"] += len(event.get("output") or "")
            if event.get("exit_code") not in (0, 2, None) or event.get("outcome") == "error":
                out["hook_errors"] += 1
        elif kind in ("assistant", "user"):
            message = event.get("message") or {}
            usage = message.get("usage") if kind == "assistant" else None
            if usage and out["first_prompt_tokens"] is None:
                # Everything the model read on its first call: system prompt, tools, skills, the
                # hooks' added context and the task. Plugins change it before any work is done.
                out["first_prompt_tokens"] = sum(usage.get(k) or 0 for k in (
                    "input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"))
            content = message.get("content")
            for block in content if isinstance(content, list) else []:
                if block.get("type") == "tool_use":
                    out["tool_calls"] += 1
                    out["bash_calls"] += block.get("name") in ("Bash", "bash")
                    if TEST_COMMAND.search(str((block.get("input") or {}).get("command", ""))):
                        out["test_commands"] += 1
                        out["ran_tests"] = True
                elif block.get("type") == "tool_result" and block.get("is_error"):
                    out["failed_tool_calls"] += 1
        elif kind == "result":
            usage = event.get("usage") or {}
            out.update(
                result=sub, is_error=event.get("is_error"), cost_usd=event.get("total_cost_usd"),
                result_text=str(event.get("result") or "")[:300],
                duration_ms=event.get("duration_ms"), api_ms=event.get("duration_api_ms"),
                turns=event.get("num_turns"),
                input_tokens=usage.get("input_tokens", 0), output_tokens=usage.get("output_tokens", 0),
                cache_read_tokens=usage.get("cache_read_input_tokens", 0),
                cache_write_tokens=usage.get("cache_creation_input_tokens", 0),
                permission_denials=len(event.get("permission_denials") or []),
            )
    return out


def diff_stats(diff):
    files, added, removed = set(), 0, 0
    for line in diff.splitlines():
        if line.startswith("+++ b/"):
            files.add(line[6:])
        elif line.startswith("+") and not line.startswith("+++"):
            added += 1
        elif line.startswith("-") and not line.startswith("---"):
            removed += 1
    return {"files_changed": len(files), "lines_added": added, "lines_removed": removed}


def validity(meta, arm, expected=None):
    """A run that did not test what it claims is kept but left out of the comparison.
    expected: the Nexika plugins the arm should load (default: A none, B all)."""
    # A timeout is the arm's own outcome (graded on its diff, cost unknown); a crash is not.
    if not meta.get("result") and not meta.get("timed_out"):
        return False, "no result event (claude did not finish)"
    if not meta.get("session_id"):
        return False, "claude did not start"
    if meta.get("is_error") and API_FAILURE.search(meta.get("result_text") or ""):
        return False, f"API failure: {meta['result_text'][:120]}"
    if expected is None:
        expected = NEXIKA if arm == "B" else ()
    loaded, expected = set(meta.get("plugins_loaded") or []) & set(NEXIKA), set(expected)
    if loaded - expected:
        return False, f"arm {arm} with extra Nexika plugins: {', '.join(sorted(loaded - expected))}"
    if expected - loaded:
        return False, f"arm {arm} without {', '.join(sorted(expected - loaded))}"
    return True, ""
