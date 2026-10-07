"""mizan doctor: how the Nexika plugins installed here get on together (schema nexika.doctor/1).

Several problems only show with more than one plugin installed, so this looks at them as a group:

- which Nexika plugins Claude Code has installed (installed_plugins.json), whether settings turn
  them off, and the hooks each one adds;
- known conflicts: bayan with Claude Code's signature line on (bayan steps in at every commit), and
  itqan without haris (itqan then guards alone, with its smaller rule set);
- the shared status files: too old, of a schema mizan does not know, or readable by others;
- each command hook's latency, run once with a dummy event in a throwaway home and folder, so no
  plugin touches your data or your project.
"""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
from pathlib import Path

from . import status

SCHEMA = "nexika.doctor/1"
FAMILY = ("amin", "barq", "bayan", "hafiz", "haris", "itqan", "lawha", "manar", "mizan", "prof", "siyaq",
          "tabib")
DATA_HOMES = ("NEXIKA_STATUS_HOME", *(f"{name.upper()}_HOME" for name in FAMILY))
SLOW_MS = 1000
STALE_DAYS = 7
EVENTS = {
    "PreToolUse": {"tool_name": "Bash", "tool_input": {"command": "true"}},
    "PostToolUse": {"tool_name": "Read", "tool_input": {"file_path": "doctor.txt"}, "tool_response": {}},
    "UserPromptSubmit": {"prompt": "hello"},
}


def config_dir() -> Path:
    return Path(os.path.expanduser(os.environ.get("CLAUDE_CONFIG_DIR") or "~/.claude"))


def _json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _project_settings(cwd: Path) -> list[Path]:
    """The project's settings files, found as Claude Code finds them: up to the first .claude or .git."""
    folder = cwd.resolve()
    while True:
        files = [folder / ".claude" / "settings.json", folder / ".claude" / "settings.local.json"]
        if any(f.is_file() for f in files) or (folder / ".git").exists():
            return files
        if folder.parent == folder:
            return []
        folder = folder.parent


def settings(cwd: Path) -> dict:
    """User settings, then the project's, then its local ones; enabledPlugins entries are merged."""
    merged: dict = {}
    enabled: dict = {}
    for path in [config_dir() / "settings.json", *_project_settings(cwd)]:
        data = _json(path)
        if isinstance(data.get("enabledPlugins"), dict):
            enabled.update(data["enabledPlugins"])
        merged.update(data)
    merged["enabledPlugins"] = enabled
    return merged


def installed(cwd: Path) -> list[dict]:
    """The Nexika plugins in installed_plugins.json, each with its folder and whether it is enabled."""
    registry = _json(config_dir() / "plugins" / "installed_plugins.json").get("plugins")
    enabled = settings(cwd)["enabledPlugins"]
    found = {}
    for key, entries in registry.items() if isinstance(registry, dict) else []:
        name = str(key).split("@", 1)[0]
        if name not in FAMILY or not isinstance(entries, list):
            continue
        entries = [e for e in entries if isinstance(e, dict) and e.get("installPath")]
        entry = next((e for e in entries if Path(e["installPath"]).is_dir()), None)
        if entry is None:
            continue
        on = enabled.get(key) if isinstance(enabled.get(key), bool) else True
        found[name] = {"name": name, "key": key, "path": str(entry["installPath"]), "enabled": on,
                       "version": str(entry.get("version") or "")}
    return [found[n] for n in FAMILY if n in found]


def hooks_of(root: Path) -> list[dict]:
    data = _json(root / "hooks" / "hooks.json")
    found = [{"event": "mod", "matcher": "", "command": str(m), "timeout": None}
             for m in data.get("modules") or [] if isinstance(m, str)]
    for event, groups in (data.get("hooks") or {}).items():
        for group in groups if isinstance(groups, list) else []:
            for hook in (group.get("hooks") or []) if isinstance(group, dict) else []:
                if isinstance(hook, dict) and hook.get("type") == "command" and hook.get("command"):
                    found.append({"event": event, "matcher": str(group.get("matcher") or ""),
                                  "command": str(hook["command"]), "timeout": hook.get("timeout")})
    return found


def time_hook(root: Path, hook: dict, home: Path) -> dict:
    """Run one command hook once with a dummy event: HOME, Claude's config and every Nexika data
    folder point into `home`, and the hook runs in an empty folder there."""
    work = home / "project"
    work.mkdir(parents=True, exist_ok=True)
    env = {k: v for k, v in os.environ.items() if k not in DATA_HOMES}
    env.update({"HOME": str(home), "USERPROFILE": str(home), "CLAUDE_CONFIG_DIR": str(home / ".claude"),
                "CLAUDE_PLUGIN_ROOT": str(root), "CLAUDE_PROJECT_DIR": str(work)})
    event = {"session_id": "nexika-doctor", "hook_event_name": hook["event"], "cwd": str(work),
             "transcript_path": "", **EVENTS.get(hook["event"], {})}
    command = hook["command"].replace("${CLAUDE_PLUGIN_ROOT}", str(root))
    started = time.monotonic()
    try:
        done = subprocess.run(command, shell=True, cwd=work, env=env, input=json.dumps(event),
                              capture_output=True, text=True, timeout=float(hook.get("timeout") or 60),
                              check=False)
        code = done.returncode
    except subprocess.TimeoutExpired:
        code = None
    except OSError:
        code = -1
    return {"ms": int((time.monotonic() - started) * 1000), "exit": code}


def status_files() -> list[dict]:
    """Every status file (the newest one of a per-session folder): its age and whether it is sound."""
    try:
        entries = sorted(status.home().iterdir())
    except OSError:
        return []
    found = []
    for entry in entries:
        if entry.is_dir():
            files = [p for p in entry.glob("*.json") if p.is_file()]
            if not files:
                continue
            path, name = max(files, key=lambda p: p.stat().st_mtime), entry.name
        elif entry.suffix == ".json" and not entry.name.startswith("."):
            path, name = entry, entry.stem
        else:
            continue
        data = status.read_json(path)
        try:
            age = time.time() - float(data.get("updated") or path.stat().st_mtime)
            others = bool(path.stat().st_mode & 0o077) and os.name != "nt"
        except (OSError, TypeError, ValueError):
            age, others = 0.0, False
        if data.get("schema") != status.schema(name):
            state = "unknown-schema"
        elif age > STALE_DAYS * 86400:
            state = "stale"
        else:
            state = "fresh"
        found.append({"name": name, "path": str(path), "state": state, "age_days": int(age // 86400),
                      "schema": str(data.get("schema") or ""), "open_to_others": others})
    return found


def _signature_on(found: dict) -> bool:
    """Claude Code signs commits and pull requests unless attribution is emptied (or the older
    includeCoAuthoredBy is false)."""
    if found.get("includeCoAuthoredBy") is False:
        return False
    attribution = found.get("attribution")
    if isinstance(attribution, dict):
        return any(attribution.get(k) != "" for k in ("commit", "pr"))
    return True


def conflicts(plugins: list[dict], cwd: Path) -> list[dict]:
    on = {p["name"] for p in plugins if p["enabled"]}
    found = []
    if "bayan" in on and _signature_on(settings(cwd)):
        bayan = _json(Path(os.path.expanduser(os.environ.get("BAYAN_HOME") or "~/.claude/nexika/bayan"))
                      / "config.json")
        what = ("every signed commit and pull request is denied and retried" if bayan.get("deny_signatures")
                else "bayan steps in at every commit and pull request to have the line removed")
        found.append({"kind": "bayan-attribution", "level": "warn",
                      "text": f"bayan with Claude Code's signature line on: {what}. Set "
                              "\"attribution\": {\"commit\": \"\", \"pr\": \"\"} in settings.json."})
    if "itqan" in on and "haris" not in on:
        found.append({"kind": "itqan-without-haris", "level": "warn",
                      "text": "itqan without haris: itqan guards commands alone, with its smaller rule set "
                              "(no shell parser, no approvals, the status files unguarded). Install or "
                              "enable haris."})
    return found


def _hook_problems(plugins: list[dict]) -> list[dict]:
    found = []
    for plugin in plugins:
        for hook in plugin["hooks"]:
            if "ms" not in hook:
                continue
            where = f"{plugin['name']} {hook['event']}"
            if hook["exit"] is None:
                found.append({"kind": "hook-timeout", "level": "warn",
                              "text": f"{where} did not finish within its {hook['timeout']} s timeout"})
            elif hook["exit"] not in (0, 2):
                found.append({"kind": "hook-failed", "level": "warn",
                              "text": f"{where} exited with {hook['exit']} on a dummy event"})
            elif hook["ms"] > SLOW_MS:
                found.append({"kind": "hook-slow", "level": "info",
                              "text": f"{where} took {hook['ms']} ms (cold start, empty folder)"})
    return found


def _status_problems(files: list[dict]) -> list[dict]:
    found = []
    for f in files:
        if f["state"] == "stale":
            found.append({"kind": "status-stale", "level": "info",
                          "text": f"status {f['name']}: nothing new for {f['age_days']} days"})
        elif f["state"] == "unknown-schema":
            found.append({"kind": "status-schema", "level": "warn",
                          "text": f"status {f['name']}: schema {f['schema'] or 'missing'}, expected "
                                  f"{status.schema(f['name'])}; readers ignore it"})
        if f["open_to_others"]:
            found.append({"kind": "status-mode", "level": "warn",
                          "text": f"status {f['name']}: readable by other users ({f['path']})"})
    return found


def run(cwd: Path, latency: bool = True) -> dict:
    cwd = Path(cwd)
    plugins = installed(cwd)
    with tempfile.TemporaryDirectory(prefix="nexika-doctor-") as scratch:
        for plugin in plugins:
            plugin["hooks"] = hooks_of(Path(plugin["path"]))
            for hook in plugin["hooks"] if latency else []:
                if hook["event"] != "mod":
                    hook.update(time_hook(Path(plugin["path"]), hook, Path(scratch) / plugin["name"]))
    files = status_files()
    return {"schema": SCHEMA, "cwd": str(cwd), "config": str(config_dir()), "status_home": str(status.home()),
            "plugins": plugins, "status": files,
            "problems": conflicts(plugins, cwd) + _hook_problems(plugins) + _status_problems(files)}


def text(found: dict) -> str:
    lines = ["Nexika plugins installed"]
    if not found["plugins"]:
        lines.append(f"  no Nexika plugin in {found['config']}/plugins/installed_plugins.json")
    for plugin in found["plugins"]:
        state = "" if plugin["enabled"] else " (disabled in settings)"
        lines.append(f"  {plugin['name']} {plugin['version']}{state}: {plugin['path']}")
        for hook in plugin["hooks"]:
            matcher = f" [{hook['matcher']}]" if hook["matcher"] else ""
            timing = f"  {hook['ms']} ms" if "ms" in hook else ""
            lines.append(f"    {hook['event']}{matcher}: {hook['command']}{timing}")
    lines.append(f"Status files ({found['status_home']})")
    ages = [f"  {f['name']}: {f['state']}, {f['age_days']} day(s) old" for f in found["status"]]
    lines += ages or ["  none"]
    lines.append("Problems")
    lines += [f"  [{p['level']}] {p['text']}" for p in found["problems"]] or ["  none found"]
    return "\n".join(lines)


def exit_code(found: dict) -> int:
    """1 when something needs fixing (a warning); information alone is 0."""
    return 1 if any(p["level"] == "warn" for p in found["problems"]) else 0
