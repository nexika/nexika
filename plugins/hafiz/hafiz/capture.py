"""Turn transcript events into session state and typed memories, with fixed rules (no AI).

What is captured, and from where:
    decision  answers to Claude's multiple-choice questions, approved plans, and user messages
              that state a choice ("let's go with", "don't use", "قررنا", "خلينا نستخدم" ...)
    task      Claude's task list (TodoWrite, TaskCreate/TaskUpdate), kept up to date
    problem   a failing test/build/lint command, marked solved when the same command passes
    file      files Claude changed (Edit, Write, MultiEdit, NotebookEdit), one memory per file
    link      URLs the user shares and pull requests or issues created during the session

Every memory keeps its source ("transcript <session> L<line>") so it can be checked.
"""
from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path

from . import secrets, store, transcript

EDIT_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
KEEP_PROMPTS = 6
PROMPT_CHARS = 400

DECISION_EN = re.compile(
    r"\b(let'?s (?:go with|use|keep|stick with|switch to|drop)|(?:we|i)(?:'ll| will) (?:go with|use)|"
    r"go with|decided|we decide|i prefer|prefer to|stick with|switch to|don'?t use|do not use|"
    r"never use|always use|instead of)\b", re.I)
DECISION_AR = re.compile(r"(قررنا|قررت|القرار|خلينا|خلّينا|نعتمد|اعتمد|بدلا من|بدل ما|لا تستخدم|لا نستخدم|"
                         r"دايما|دائما|نمشي على|امشي على|سنستخدم)")
QUESTION = re.compile(r"^(why|what|which|how|should|shall|could|can|would|do|does|did|is|are|"
                      r"هل|ليش|لماذا|ليه|كيف|ايش|شو|ماذا)\b", re.I)
URL = re.compile(r"https?://[^\s<>\"'`)\]]+")
GH_REF = re.compile(r"https://github\.com/[\w.-]+/[\w.-]+/(?:pull|issues)/\d+")
COMMIT_LINE = re.compile(r"^\[([^\s\]]+)(?: \(root-commit\))? ([0-9a-f]{7,40})\] (.+)$", re.M)
RUNNERS = re.compile(
    r"(?:^|[;&|(]\s*|\b(?:uv run|poetry run|npx|bunx|python3? -m|sudo|time)\s+)"
    r"(pytest|py\.test|tox|nox|ruff|mypy|flake8|pylint|npm (?:run )?(?:test|build|lint)|"
    r"pnpm (?:run )?(?:test|build|lint)|yarn (?:test|build|lint)|bun test|vitest|jest|eslint|tsc|"
    r"go (?:test|build|vet)|cargo (?:test|build|clippy|check)|dotnet (?:test|build)|mvn|gradle|"
    r"gradlew|make|ctest|phpunit|rspec|swift (?:test|build)|flutter (?:test|analyze)|"
    r"claude plugin validate)\b([^;&|]*)")
ERROR_LINE = re.compile(r"(error|failed|failure|exception|traceback|assert|panic|fatal|خطأ)", re.I)
ANSWER = re.compile(r'"([^"\n]{3,300})"\s*=\s*"([^"\n]{1,300})"')


def _short(text: str, limit: int) -> str:
    flat = re.sub(r"\s+", " ", text).strip()
    return flat if len(flat) <= limit else flat[: limit - 1].rsplit(" ", 1)[0] + "…"


def _sentence_with(text: str, match: re.Match) -> str:
    start = max(text.rfind(c, 0, match.start()) for c in ".!?\n؟")
    ends = [i for i in (text.find(c, match.end()) for c in ".!?\n؟") if i >= 0]
    return text[start + 1: min(ends) + 1 if ends else len(text)].strip()


def _first_error(text: str) -> str:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    for ln in lines:
        if ERROR_LINE.search(ln) and not ln.startswith(("===", "---")):
            return ln
    return lines[-1] if lines else ""


def _rel(path: str, cwd: str, root: Path) -> str:
    if not path:
        return ""
    p = Path(path)
    if not p.is_absolute() and cwd:
        p = Path(cwd) / p
    for base in (Path(cwd) if cwd else None, root):
        if base is None:
            continue
        try:
            return p.resolve().relative_to(base.resolve()).as_posix()
        except (ValueError, OSError):
            continue
    return p.as_posix()


def new_state(session: str, transcript_path: str) -> dict:
    return {"session": session, "transcript": transcript_path, "offset": 0, "line": 0,
            "started": store.now(), "updated": "", "ended": "", "branch": "", "cwd": "",
            "first_prompt": "", "prompts": [], "prompt_count": 0, "files": {}, "commits": [],
            "tasks": {}, "task_ids": {}, "problems": {}, "decisions": [], "links": [], "pending": {},
            "note": "", "compactions": 0, "private_salt": "", "private": []}


def state_path(folder: Path, session: str) -> Path:
    return folder / "sessions" / f"{store.safe_name(session, 64)}.json"


def load_state(folder: Path, session: str, transcript_path: str = "") -> dict:
    data = store.read_json(state_path(folder, session), {})
    state = new_state(session, transcript_path)
    state.update({k: v for k, v in data.items() if k in state})
    if transcript_path and transcript_path != state["transcript"]:
        state.update(transcript=transcript_path, offset=0, line=0, pending={})
    return state


def save_state(folder: Path, state: dict) -> None:
    state["updated"] = store.now()
    store.write_json(state_path(folder, state["session"]), state)


class Capture:
    """Applies the rules to new events of one session."""

    def __init__(self, root: Path, state: dict, commit: str):
        self.root, self.state, self.commit = root, state, commit
        self.memories: list[dict] = []
        self._memories: list[dict] | None = None
        self.sid = state["session"][:8]

    def clean(self, text: str) -> str:
        """Secrets replaced, and words the user marked <private> earlier in the session masked."""
        return secrets.mask(secrets.redact(text), set(self.state["private"]), self.state["private_salt"])

    def _remember_private(self, raw: str) -> None:
        words = secrets.private_words(raw)
        if not words:
            return
        if not self.state["private_salt"]:
            self.state["private_salt"] = os.urandom(8).hex()
        known = set(self.state["private"])
        known.update(secrets.word_hash(w, self.state["private_salt"]) for w in words)
        self.state["private"] = sorted(known)[-500:]

    def _add(self, kind: str, text: str, event: dict, **fields) -> None:
        fields.setdefault("branch", event.get("branch") or self.state["branch"])
        self.memories.append(store.Memory.make(
            kind, text, date=event.get("time") or store.now(), commit=self.commit, session=self.sid,
            source=f"transcript {self.sid} L{event['line']}", origin="auto", **fields))

    # ------------------------------------------------------------ per event

    def prompt(self, event: dict) -> None:
        self._remember_private(event["text"])
        text = self.clean(event["text"]).strip()
        if not text:
            return
        state = self.state
        state["prompt_count"] += 1
        if not state["first_prompt"]:
            state["first_prompt"] = _short(text, PROMPT_CHARS)
        state["prompts"] = (state["prompts"] + [_short(text, PROMPT_CHARS)])[-KEEP_PROMPTS:]
        for url in dict.fromkeys(URL.findall(text)):
            url = url.rstrip(".,;:")
            if url not in state["links"]:
                state["links"].append(url)
                self._add("link", f"{url} (shared: {_short(text.replace(url, ''), 120)})", event,
                          key=f"link|{url}", scope="project")
        if len(text) <= 600:
            for pattern in (DECISION_EN, DECISION_AR):
                match = pattern.search(text)
                if match:
                    sentence = _short(_sentence_with(text, match), 300)
                    if sentence.endswith(("?", "؟")) or QUESTION.match(sentence):
                        break  # a question is not a decision
                    if len(sentence) >= 12 and sentence not in state["decisions"]:
                        state["decisions"].append(sentence)
                        self._add("decision", f"User: {sentence}", event,
                                  key=f"decision|{self.sid}|{sentence[:80]}")
                    break

    def tool(self, event: dict) -> None:
        name, data = event["name"], event["input"]
        if name == "TodoWrite":
            listed = set()
            for todo in data.get("todos") or []:
                if isinstance(todo, dict) and todo.get("content"):
                    status = "done" if todo.get("status") == "completed" else "open"
                    listed.add(self._task(str(todo["content"]), status, event, source="todo"))
            for key, task in list(self.state["tasks"].items()):
                if task.get("source") == "todo" and task["status"] == "open" and key not in listed:
                    self._task(task["text"], "dropped", event, source="todo")
            return
        if name == "TaskUpdate":
            subject = self.state["task_ids"].get(str(data.get("taskId") or ""))
            status = data.get("status")
            if subject and status in ("completed", "deleted"):
                self._task(subject, "done" if status == "completed" else "dropped", event)
            return
        keep = {"name": name, "line": event["line"]}
        if name in EDIT_TOOLS:
            keep["path"] = str(data.get("file_path") or data.get("notebook_path") or "")
        elif name == "Bash":
            keep["command"] = self.clean(str(data.get("command") or "")[:2000])
        elif name == "TaskCreate":
            keep["subject"] = self.clean(str(data.get("subject") or ""))
        elif name == "AskUserQuestion":
            pass
        elif name == "ExitPlanMode":
            keep["plan"] = self.clean(str(data.get("plan") or "")[:600])
        else:
            return
        pending = self.state["pending"]
        pending[event["id"]] = keep
        if len(pending) > 200:
            for old in list(pending)[:-200]:
                pending.pop(old, None)

    def result(self, event: dict) -> None:
        call = self.state["pending"].pop(event["id"], None)
        if not call:
            return
        name, ok = call["name"], not event["error"]
        if name in EDIT_TOOLS and ok:
            rel = _rel(call.get("path", ""), event.get("cwd") or self.state["cwd"], self.root)
            if rel:
                count = self.state["files"].get(rel, 0) + 1
                self.state["files"][rel] = count
                self._add("file", f"Changed {rel} ({count} edit{'s' if count > 1 else ''})", event,
                          key=f"file|{self.sid}|{rel}")
        elif name == "Bash":
            self._bash(call["command"], event, ok)
        elif name == "TaskCreate" and ok:
            number = re.search(r"#(\d+)", event["text"])
            subject = call.get("subject", "")
            if subject:
                if number:
                    self.state["task_ids"][number.group(1)] = subject
                self._task(subject, "open", event)
        elif name == "AskUserQuestion" and ok:
            answers = ANSWER.findall(event["text"])
            extra = event.get("extra")
            if not answers and isinstance(extra, dict) and isinstance(extra.get("answers"), dict):
                answers = [(str(q), str(a)) for q, a in extra["answers"].items()]
            for question, answer in answers:
                question, answer = self.clean(question), self.clean(answer)
                text = f"{_short(question, 160)} -> {_short(answer, 200)}"
                if text not in self.state["decisions"]:
                    self.state["decisions"].append(text)
                    digest = hashlib.sha1(question.encode()).hexdigest()[:12]
                    self._add("decision", text, event, key=f"decision|{self.sid}|q{digest}")
        elif name == "ExitPlanMode" and ok and call.get("plan"):
            heading = next((ln.strip("# ").strip() for ln in call["plan"].splitlines() if ln.strip()), "")
            if heading:
                text = self.clean(f"Plan approved: {_short(heading, 200)}")
                self.state["decisions"].append(text)
                self._add("decision", text, event, key=f"decision|{self.sid}|plan|{heading[:60]}")

    def _task(self, subject: str, status: str, event: dict, source: str = "task") -> str:
        subject = _short(self.clean(subject), 200)
        key = f"task|{subject.lower()[:100]}"  # the same task in a later session is the same memory
        before = self.state["tasks"].get(key)
        if before and before["status"] == status:
            return key
        self.state["tasks"][key] = {"text": subject, "status": status, "source": source}
        self._add("task", subject, event, key=key, status=status)
        return key

    def _bash(self, command: str, event: dict, ok: bool) -> None:
        if ok and re.search(r"\bgit\b[^|;&]*\bcommit\b", command):
            for found_branch, sha, message in COMMIT_LINE.findall(event["text"]):
                entry = {"hash": sha[:9], "message": _short(self.clean(message), 160),
                         "branch": found_branch, "time": event.get("time", "")}
                if entry not in self.state["commits"]:
                    self.state["commits"].append(entry)
                    self.commit = sha[:9]
        if ok and re.search(r"\bgh (pr|issue) create\b", command):
            for url in dict.fromkeys(GH_REF.findall(event["text"])):
                if url not in self.state["links"]:
                    self.state["links"].append(url)
                    kind = "pull request" if "/pull/" in url else "issue"
                    self._add("link", f"{url} ({kind} created in this session)", event, key=f"link|{url}")
        runner = RUNNERS.search(command)
        if not runner:
            return
        family = runner.group(1)
        targets = sorted(a for a in runner.group(2).split() if not a.startswith("-"))[:6]
        name = " ".join([family, *targets])
        key = f"problem|{name}"  # by command, so a pass in any later session closes it
        if not ok:
            detail = _short(self.clean(_first_error(event["text"])), 220)
            text = f"`{name}` failed: {detail}" if detail else f"`{name}` failed"
            self.state["problems"][key] = {"text": text, "status": "open", "line": event["line"],
                                           "family": family}
            self._add("problem", text, event, key=key, status="open")
            return

        # a pass solves the same run, or every run of that tool when it ran without targets
        def same(other: str) -> bool:
            ran = other.rsplit("|", 1)[-1]
            return ran == name or (not targets and (ran == family or ran.startswith(family + " ")))

        for other, problem in list(self.state["problems"].items()):
            if same(other) and problem["status"] == "open":
                text = f"{problem['text']} (passed again at L{event['line']})"
                self.state["problems"][other] = {**problem, "text": text, "status": "solved"}
                self._add("problem", text, event, key=other, status="solved")
        for item in self._stored():
            if (item["type"] == "problem" and item.get("status") == "open" and item.get("key")
                    and item["key"] not in self.state["problems"] and same(item["key"])):
                text = f"{item['text']} (passed again in session {self.sid})"
                self._add("problem", text, event, key=item["key"], status="solved")

    def _stored(self) -> list[dict]:
        if self._memories is None:
            self._memories = store.Memory(self.root).all()
        return self._memories


def update(root: Path, session: str, transcript_path: str, cwd: str = "") -> dict:
    """Read what is new in the session transcript, store new memories, return the session state."""
    memory = store.Memory(root)
    with store.locked(memory.dir / "sessions", timeout=8):
        return _update(memory, root, session, transcript_path, cwd)


def _update(memory: store.Memory, root: Path, session: str, transcript_path: str, cwd: str) -> dict:
    state = load_state(memory.dir, session, transcript_path)
    if cwd and not state["cwd"]:
        state["cwd"] = cwd
    if not state["branch"]:
        state["branch"] = store.branch(Path(state["cwd"] or root))
    events: list[dict] = []
    if state["transcript"]:
        events, state["offset"], state["line"] = transcript.read_new(
            state["transcript"], state["offset"], state["line"])
    capture = Capture(root, state, store.head_commit(Path(state["cwd"] or root)))
    for event in events:
        if event.get("branch"):
            state["branch"] = event["branch"]
        if event.get("cwd"):
            state["cwd"] = event["cwd"]
        if event["kind"] in ("prompt", "tool", "result"):
            getattr(capture, event["kind"])(event)
    memory.upsert(capture.memories)
    save_state(memory.dir, state)
    return state
