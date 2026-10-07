"""Claude Code hooks. They must never break the session: any error means "do nothing"."""
from __future__ import annotations

import os
import re
import shlex
import shutil
from pathlib import Path

from . import check, clean, config, rules

CLEAN_SUFFIXES = {".md", ".mdx", ".markdown"}      # cleaned and checked
CHECK_SUFFIXES = CLEAN_SUFFIXES | {".txt", ".rst"}  # .txt/.rst: checked only (rst code is indented prose)
SKIP_DIRS = {"node_modules", ".git", "vendor", ".venv", "venv", "site-packages", "dist", "build",
             "fixtures", "testdata", "__snapshots__", "snapshots"}
OPT_OUT = "bayan: off"
# git's global options come before the subcommand: git -c k=v, -C dir, --no-pager, --git-dir=x, --work-tree x
_GIT_OPTS = (r"(?:\s+(?:-[cC]\s*\S+|--(?:git-dir|work-tree|namespace|exec-path|config-env)(?:=|\s+)\S+"
             r"|--[\w-]+(?:=\S+)?))*")
PUBLISH = re.compile(rf"(?:^|&&|\|\||;)\s*(?:git{_GIT_OPTS}\s+(?:commit|tag)\b"
                     r"|gh\s+(?:pr|release|issue)\s+(?:create|edit|comment)\b)", re.M)
MESSAGE_FILE = re.compile(r"(?:\s-F|--file|--body-file|--notes-file)[ =]+(\"[^\"]+\"|'[^']+'|\S+)")

LEVEL_RULE = {
    "no-code": "The reader has never written code. Use everyday words. When a technical word can't be "
               "avoided, explain it in the same sentence with an everyday comparison. Say what it means "
               "for them before how it works.",
    "junior": "The reader is learning to code. Explain each new technical term once, briefly, and show "
              "one small example when it helps.",
    "developer": "The reader is a developer. Technical terms are fine; stay plain and specific.",
}

GUIDE = """## bayan (Nexika): write like a clear, friendly person
Reader level: {level} (change with /bayan:level). {level_rule}
This applies to everything you write in this session, including prof lessons and reports, amin
release notes, manar audits, commit messages and pull request text.
- Reply in the language the user writes in (Arabic or English). Lead with the answer, then the why.
- One idea per sentence. Mix short sentences with longer ones; most under 20 words.
- Be specific: numbers, names, files, what changed. Cut words that add nothing.
- Friendly, not chatty: no opening praise, no "hope this helps" closings, no cheerleading, no emoji
  in headings, at most one exclamation mark.
- Avoid machine habits: delve, tapestry, testament, realm, landscape, seamless, robust, unlock,
  game-changer, "plays a crucial role", "not just X but Y", em dashes everywhere, every list in
  threes, every bullet opening with a bold label, the same sentence length again and again.
- Arabic: clear Modern Standard Arabic, as a person writes it, in short sentences. Avoid stiff
  phrases such as "من الجدير بالذكر"، "تجدر الإشارة"، "علاوة على ذلك"، "يلعب دورًا محوريًا"، "في الختام".
  Keep code, commands and product names in English and explain them in Arabic.
- Correct before simple: never simplify into something false. If something is uncertain, say so
  once, plainly. Code, commands, paths and quotes stay exact.
In Markdown files you write, the part you wrote is cleaned automatically (hidden characters, AI
signature lines, filler sentences); when bayan reports style notes, rewrite those lines.
Helper: {cmd} check FILE | {cmd} clean FILE --write. Full guide with examples: {guide}"""


def session_start(hook: dict) -> str:
    cfg = config.load()
    bin_dir = Path(__file__).resolve().parent.parent / "bin"
    command = "bayan"
    env_file = os.environ.get("CLAUDE_ENV_FILE")
    line = f'export PATH={shlex.quote(str(bin_dir))}:"$PATH"\n'
    try:
        if not env_file:
            raise OSError
        existing = Path(env_file).read_text(encoding="utf-8") if Path(env_file).exists() else ""
        if line not in existing:   # resume / clear / compact run this hook again
            with open(env_file, "a", encoding="utf-8") as fh:
                fh.write(line)
    except OSError:
        command = f"python3 {shlex.quote(str(bin_dir / 'bayan'))}"
    return GUIDE.format(level=cfg["level"], level_rule=LEVEL_RULE[cfg["level"]], cmd=command,
                        guide=bin_dir.parent / "guide" / "writing.md")


def _project(hook: dict) -> Path:
    return Path(hook.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()).resolve()


def _eligible(path: Path, project: Path) -> bool:
    if path.suffix.lower() not in CHECK_SUFFIXES or path.is_symlink() or not path.is_file():
        return False
    resolved = path.resolve()
    if not resolved.is_relative_to(project):
        return False
    skipped = SKIP_DIRS.intersection(resolved.relative_to(project).parts)
    return not skipped and resolved.stat().st_size < 1_000_000


def _read(path: Path) -> str:
    with open(path, encoding="utf-8", newline="") as fh:   # keep CRLF as it is
        return fh.read()


def _write(path: Path, text: str) -> None:
    """Atomic: a killed hook never leaves a half-written file."""
    tmp = path.with_name(f".{path.name}.bayan-tmp")
    with open(tmp, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)
    shutil.copymode(path, tmp)
    os.replace(tmp, path)


def _regions(hook: dict, text: str) -> list[tuple[int, int]] | None:
    """What Claude just wrote: None = the whole file (Write), [] = can't tell (report only)."""
    tool_input = hook.get("tool_input") or {}
    if hook.get("tool_name") == "Write" or "content" in tool_input:
        return None
    pieces = [tool_input.get("new_string")] + [e.get("new_string") for e in tool_input.get("edits") or []]
    regions = []
    for piece in pieces:
        if piece and text.count(piece) == 1:
            start = text.index(piece)
            regions.append((start, start + len(piece)))
    return regions


def post_write(hook: dict) -> dict | None:
    """After Write/Edit of a prose file: clean what Claude wrote, report what still needs rewriting."""
    path = Path(str((hook.get("tool_input") or {}).get("file_path") or ""))
    if not path.name or not _eligible(path, _project(hook)):
        return None
    text = _read(path)
    if OPT_OUT in text:
        return None
    cfg = config.load()
    regions = _regions(hook, text)
    lines = None   # None = report on the whole file (it was all written by Claude)
    if regions is not None:
        lines = set()
        for start, end in regions:
            lines.update(range(text.count("\n", 0, start) + 1, text.count("\n", 0, end) + 2))
    notes = []
    if cfg.get("auto_clean", True) and path.suffix.lower() in CLEAN_SUFFIXES and regions != []:
        fixed, changes = text, None
        for region in sorted(regions or [None], key=lambda r: -(r[0] if r else 0)):
            fixed, found = clean.clean(fixed, region=region)
            changes = found if changes is None else changes + found
        if changes and fixed != text:
            _write(path, fixed)
            text = fixed
            notes.append(f"bayan cleaned {path.name}: {clean.summary(changes)} (the file on disk changed).")
    todo = [f for f in check.check(text, cfg["level"]) if f.kind == "rewrite"
            and (lines is None or f.line in lines)]
    todo.sort(key=lambda f: -f.weight)
    if todo:
        notes.append(f"bayan style notes for {path.name} (reader: {cfg['level']}); rewrite these lines:")
        notes += [f"- {'L' + str(f.line) if f.line else 'whole text'}: \"{f.text}\" -> {f.advice}"
                  for f in todo[:6]]
    if not notes:
        return None
    return {"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": "\n".join(notes)}}


SIGNATURE_NOTE = ("bayan: this message carries an AI signature (Co-Authored-By / 'Generated with'). "
                  "Leave it out of the next commit or pull request. To stop Claude Code adding it, set "
                  "\"attribution\": {\"commit\": \"\", \"pr\": \"\"} in .claude/settings.json.")


def _message_files(command: str, cwd: Path) -> str:
    texts = []
    for m in MESSAGE_FILE.finditer(command):
        target = Path(m.group(1).strip("\"'"))
        target = target if target.is_absolute() else cwd / target
        try:
            if target.is_file() and target.stat().st_size < 100_000:
                texts.append(target.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
    return "\n".join(texts)


def pre_bash(hook: dict) -> dict | None:
    """Commits, tags, pull requests and releases: block zero-width characters; for an AI signature, tell
    Claude how to leave it out (denying it made every signed commit fail and retry)."""
    command = str((hook.get("tool_input") or {}).get("command") or "")
    cfg = config.load()
    if not PUBLISH.search(command) or not cfg.get("block_signatures", True):
        return None
    message = command + "\n" + _message_files(command, _project(hook))
    if any(ord(c) in rules.ZERO_WIDTH for c in message):
        reason = "bayan: the message contains invisible zero-width characters. Remove them."
    elif rules.SIGNATURE_IN_COMMAND.search(message):
        if not cfg.get("deny_signatures", False):
            return {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                           "additionalContext": SIGNATURE_NOTE}}
        reason = ("bayan: this project doesn't sign commits, pull requests or releases with an AI "
                  "signature. Remove the Co-Authored-By / 'Generated with' line and run it again.")
    else:
        return None
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                   "permissionDecisionReason": reason}}
