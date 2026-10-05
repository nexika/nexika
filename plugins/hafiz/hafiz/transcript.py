"""Read a Claude Code session transcript incrementally and turn it into simple events.

Only complete new lines after the saved byte offset are read, so a hook that runs after every
turn costs little. Unknown record shapes are skipped: the transcript format is not a stable API.

Events (dicts with "kind" and "line"):
    prompt       text                       a message the user typed
    say          text                       text Claude wrote to the user
    tool         id, name, input            Claude called a tool
    result       id, text, error, extra     the tool's result (extra: toolUseResult when present)
"""
from __future__ import annotations

import datetime
import json
import re
from pathlib import Path

MAX_READ = 8 * 1024 * 1024   # bytes per run; the rest is read on the next run
WRAPPER = re.compile(r"<(system-reminder|local-command-stdout|local-command-stderr|command-message|"
                     r"task-notification|user-prompt-submit-hook|agent-message)\b[^>]*>.*?</\1>",
                     re.S)
COMMAND_NAME = re.compile(r"<command-name>\s*(.*?)\s*</command-name>", re.S)
COMMAND_ARGS = re.compile(r"<command-args>(.*?)</command-args>", re.S)
SKIP_PROMPTS = ("[Request interrupted", "Caveat:", "<local-command", "<bash-", "<task-notification",
                "<agent-message", "[SYSTEM NOTIFICATION")


def local_time(stamp: str) -> str:
    try:
        moment = datetime.datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return ""
    if moment.tzinfo is not None:
        moment = moment.astimezone().replace(tzinfo=None)
    return moment.isoformat(timespec="seconds")


def _text_of(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text") or ""))
            elif isinstance(block, str):
                parts.append(block)
        return "\n".join(parts)
    return ""


def clean_prompt(text: str) -> str:
    """The words the user typed, without the wrappers Claude Code adds around them."""
    name = COMMAND_NAME.search(text)
    if name:
        args = COMMAND_ARGS.search(text)
        text = f"{name.group(1)} {args.group(1).strip() if args else ''}".strip()
    text = WRAPPER.sub("", text).strip()
    if text.startswith(SKIP_PROMPTS):
        return ""
    return text


def events_of(record: dict, line: int) -> list[dict]:
    kind = record.get("type")
    if kind not in ("user", "assistant") or record.get("isSidechain") or record.get("isCompactSummary"):
        return []
    message = record.get("message")
    if not isinstance(message, dict):
        return []
    base = {"line": line, "time": local_time(str(record.get("timestamp") or "")),
            "branch": str(record.get("gitBranch") or ""), "cwd": str(record.get("cwd") or "")}
    content = message.get("content")
    out = []
    if kind == "user":
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "tool_result":
                    out.append({**base, "kind": "result", "id": str(block.get("tool_use_id") or ""),
                                "text": _text_of(block.get("content")), "error": bool(block.get("is_error")),
                                "extra": record.get("toolUseResult")})
        if not out and not record.get("isMeta"):
            text = clean_prompt(_text_of(content))
            if text:
                out.append({**base, "kind": "prompt", "text": text})
        return out
    if isinstance(content, list):
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "text" and str(block.get("text") or "").strip():
                out.append({**base, "kind": "say", "text": str(block["text"]).strip()})
            elif block.get("type") == "tool_use":
                tool_input = block.get("input") if isinstance(block.get("input"), dict) else {}
                out.append({**base, "kind": "tool", "id": str(block.get("id") or ""),
                            "name": str(block.get("name") or ""), "input": tool_input})
    elif isinstance(content, str) and content.strip():
        out.append({**base, "kind": "say", "text": content.strip()})
    return out


def read_new(path: str | Path, offset: int = 0, line: int = 0) -> tuple[list[dict], int, int]:
    """Events after byte `offset` (line number `line`); returns (events, new offset, new line)."""
    try:
        with open(path, "rb") as fh:
            fh.seek(0, 2)
            size = fh.tell()
            if offset > size:  # the file was replaced: start again
                offset, line = 0, 0
            fh.seek(offset)
            chunk = fh.read(MAX_READ)
    except OSError:
        return [], offset, line
    end = chunk.rfind(b"\n")
    if end < 0:  # no complete line yet, or one line larger than MAX_READ (skipped)
        return [], offset + (len(chunk) if len(chunk) >= MAX_READ else 0), line
    events = []
    for raw in chunk[: end + 1].split(b"\n")[:-1]:
        line += 1
        try:
            record = json.loads(raw)
        except ValueError:
            continue
        if isinstance(record, dict):
            events.extend(events_of(record, line))
    return events, offset + end + 1, line


def read_all(path: str | Path) -> list[dict]:
    events, offset, line = [], 0, 0
    while True:
        chunk, new_offset, line = read_new(path, offset, line)
        events.extend(chunk)
        if new_offset == offset:
            return events
        offset = new_offset
