"""Read one run's stream-json output and diff into plain numbers."""

import json

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
    }
    for event in _events(lines):
        kind, sub = event.get("type"), event.get("subtype", "")
        if kind == "system" and sub == "init":
            out["session_id"] = event.get("session_id", "")
            out["model_used"] = event.get("model", "")
            out["plugins_loaded"] = sorted(_plugin_name(p) for p in event.get("plugins") or [])
        elif kind == "system" and sub == "hook_response":
            out["hook_runs"] += 1
            if event.get("exit_code") not in (0, 2, None) or event.get("outcome") == "error":
                out["hook_errors"] += 1
        elif kind in ("assistant", "user"):
            content = (event.get("message") or {}).get("content")
            for block in content if isinstance(content, list) else []:
                if block.get("type") == "tool_use":
                    out["tool_calls"] += 1
                    out["bash_calls"] += block.get("name") == "Bash"
                elif block.get("type") == "tool_result" and block.get("is_error"):
                    out["failed_tool_calls"] += 1
        elif kind == "result":
            usage = event.get("usage") or {}
            out.update(
                result=sub, is_error=event.get("is_error"), cost_usd=event.get("total_cost_usd"),
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


def validity(meta, arm):
    """A run that did not test what it claims is kept but left out of the comparison."""
    # A timeout is the arm's own outcome (graded on its diff, cost unknown); a crash is not.
    if not meta.get("result") and not meta.get("timed_out"):
        return False, "no result event (claude did not finish)"
    if not meta.get("session_id"):
        return False, "claude did not start"
    loaded = set(meta.get("plugins_loaded") or []) & set(NEXIKA)
    if arm == "B" and loaded != set(NEXIKA):
        missing = ", ".join(sorted(set(NEXIKA) - loaded)) or "none"
        return False, f"arm B without every Nexika plugin (missing: {missing})"
    if arm == "A" and loaded:
        return False, f"arm A with Nexika plugins: {', '.join(sorted(loaded))}"
    return True, ""
