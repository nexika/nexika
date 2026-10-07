"""Turn transcript events into session state and typed memories, with fixed rules (no AI).

What is captured, and from where:
    decision  answers to Claude's multiple-choice questions, approved plans, Claude's proposals the
              user agrees to ("I suggest ..." then "yes" / "تمام"), and sentences of user messages
              that start with a choice ("let's go with", "don't use", "قررنا", "نستخدم" ...), with
              the reason when one is given ("because ...", "لأن ...")
    task      Claude's task list (TodoWrite, TaskCreate/TaskUpdate), kept up to date
    problem   a failing test/build/lint command, marked solved when the same command passes
    file      files Claude changed (Edit, Write, MultiEdit, NotebookEdit), one memory per file
    link      URLs the user shares and pull requests or issues created during the session
    commit    commits made in the session, from `git commit` output or, when it prints nothing, `git log`

Every memory keeps its source ("transcript <session> L<line>") so it can be checked.
"""
from __future__ import annotations

import datetime
import hashlib
import os
import re
from pathlib import Path

from . import secrets, store, transcript

EDIT_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
KEEP_PROMPTS = 6
PROMPT_CHARS = 400

# A decision is a sentence that *starts* with a choice ("let's use", "we'll go with", "don't use",
# "use X instead of Y"); the same words in the middle of a request ("explain why it uses X instead
# of Y") are not one.
DECISION_EN = re.compile(
    r"^(?:[\w-]+:\s+)?(?:(?:ok(?:ay)?|yes|yeah|yep|no|nope|fine|so|then|alright|right|good|great|and|but)\b[,.!:]?\s+)*"
    r"(?:let'?s (?:go with|use|keep|stick with|switch to|move to|drop|not use|avoid)|"
    r"(?:we|i)(?:'ll| will| are going to| am going to|'re going to|'m going to) "
    r"(?:go with|use|keep|stick with|switch to|move to|drop|avoid)|"
    r"(?:we|i)(?: have|'ve)? decided\b|we decide\b|"
    r"(?:don'?t|do not|never|always) use|stick with|go with|"
    r"(?:use|switch to|move to|change to) [^,;]{1,60}? instead of|prefer [^,;]{1,60}? over)\b", re.I)
DECISION_AR = re.compile(r"(قررنا|قررت|خلينا|خلّينا|نعتمد|اعتمد|بدلا من|بدل ما|لا تستخدم|لا نستخدم|"
                         r"دايما استخدم|دائما استخدم|نمشي على|امشي على|سنستخدم|"
                         r"(?:^|\s)(?:نستخدم|خلّ?ي|خليه|خليها)(?=\s|$))")
# Claude proposes ("I suggest ...", "Shall I ...?") and the user agrees ("yes", "تمام"): that is
# how most decisions are made in Claude Code.
PROPOSAL = re.compile(
    r"\b(?:i (?:suggest|recommend|propose|would|'d)\b|my (?:recommendation|suggestion)\b|"
    r"i think we should|we should\b|the best option is|let'?s\b)", re.I)
OFFER = re.compile(r"^(?:shall i|should i|do you want me to|want me to|would you like me to|how about)\b",
                   re.I)
CONTINUE_ONLY = re.compile(r"\b(?:go ahead|proceed|continue|start|do (?:it|that|this)|"
                           r"implement (?:it|this|that))\W*$", re.I)
APPROVAL = re.compile(
    r"^(?:yes|yep|yeah|yup|sure|ok(?:ay)?|go ahead|do it|sounds good|agreed|approved|lgtm|perfect|"
    r"great|let'?s do it|please do|go for it|نعم|ايوه|أيوه|تمام|اوكي|أوكي|موافق|ماشي|يلا|اعمل|اكيد|أكيد)"
    r"(?=$|[\s,.!،])", re.I)
NOT_PLAIN_YES = re.compile(r"\b(?:but|however|instead|no|not|don'?t|rather|what|why|which)\b|"
                           r"[?؟]|(?:^|\s)(?:لكن|بس|لا|بدل)(?=\s|$)", re.I)
REASON = re.compile(r"\s*(?:,\s*)?\b(?:because|since|as it|so that)\b\s*|\s*(?:لأن|لان|عشان|علشان)\s*", re.I)
REASON_NEXT = re.compile(r"^(?:because|that way|this way|it|this|لأن|لان|عشان|كذا|بهذا)\b,?\s*", re.I)
SENTENCE_END = re.compile(r"(?<=[.!?؟])\s+|\n+")
CODE_BLOCK = re.compile(r"```.*?(?:```|\Z)|<pasted_content\b.*?(?:</pasted_content[^>]*>|\Z)", re.S | re.I)
PASTE_TAG = re.compile(r"</?pasted_content\b[^>]*>", re.I)
MAX_DECISIONS_PER_PROMPT = 3
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


def _split_reason(sentence: str) -> tuple[str, str]:
    """("use X", "it is faster") from "use X because it is faster."."""
    parts = REASON.split(sentence, maxsplit=1)
    if len(parts) == 2 and parts[1].strip():
        return parts[0].strip().rstrip(","), parts[1].strip().rstrip(".!")
    return sentence, ""


def _approves(prompt: str) -> bool:
    words = prompt.split()
    return 0 < len(words) <= 12 and bool(APPROVAL.match(prompt.strip())) and not NOT_PLAIN_YES.search(prompt)


def _first_error(text: str) -> str:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    for ln in lines:
        if ERROR_LINE.search(ln) and not ln.startswith(("===", "---")):
            return ln
    return lines[-1] if lines else ""


_TOPS: dict[str, Path] = {}


def _rel(path: str, cwd: str, root: Path) -> str:
    """The path relative to the repository (this worktree or the main one); "" when outside it."""
    if not path:
        return ""
    p = Path(path)
    if not p.is_absolute() and cwd:
        p = Path(cwd) / p
    bases = [root]
    if cwd:
        if cwd not in _TOPS:
            _TOPS[cwd] = store.worktree_root(Path(cwd))
        bases.insert(0, _TOPS[cwd])
    for base in bases:
        try:
            return p.resolve().relative_to(base.resolve()).as_posix()
        except (ValueError, OSError):
            continue
    return ""


def new_state(session: str, transcript_path: str) -> dict:
    return {"session": session, "transcript": transcript_path, "offset": 0, "line": 0,
            "started": store.now(), "updated": "", "ended": "", "branch": "", "cwd": "",
            "first_prompt": "", "prompts": [], "prompt_count": 0, "files": {}, "commits": [],
            "tasks": {}, "task_ids": {}, "problems": {}, "decisions": [], "links": [], "pending": {},
            "proposal": {}, "touched": {},
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
        shown = _short(PASTE_TAG.sub(" ", text), PROMPT_CHARS)
        if not state["first_prompt"]:
            state["first_prompt"] = shown
        state["prompts"] = (state["prompts"] + [shown])[-KEEP_PROMPTS:]
        for url in dict.fromkeys(URL.findall(text)):
            url = url.rstrip(".,;:")
            if url not in state["links"]:
                state["links"].append(url)
                self._add("link", f"{url} (shared: {_short(text.replace(url, ''), 120)})", event,
                          key=f"link|{url}", scope="project")
        proposal, state["proposal"] = state.get("proposal") or {}, {}
        if proposal and _approves(text):
            sentence = proposal["text"]
            if sentence not in state["decisions"]:
                state["decisions"].append(sentence)
                digest = hashlib.sha1(sentence.encode()).hexdigest()[:12]
                self._add("decision", f"Agreed: {sentence}", event, key=f"decision|{self.sid}|a{digest}",
                          reason=proposal.get("reason", ""))
        found = 0
        for sentence in SENTENCE_END.split(CODE_BLOCK.sub("\n", text)[:8000]):
            sentence = sentence.strip(" \t-*>")
            if not (DECISION_EN.search(sentence) or DECISION_AR.search(sentence)):
                continue
            if sentence.endswith(("?", "؟")) or QUESTION.match(sentence):
                continue  # a question is not a decision
            sentence = _short(sentence, 300)
            if len(sentence) >= 12 and sentence not in state["decisions"]:
                state["decisions"].append(sentence)
                self._add("decision", f"User: {sentence}", event, key=f"decision|{self.sid}|{sentence[:80]}",
                          reason=_split_reason(sentence)[1])
                found += 1
                if found >= MAX_DECISIONS_PER_PROMPT:
                    break

    def say(self, event: dict) -> None:
        """Remember Claude's latest proposal, so a "yes" in the next prompt records it as a decision."""
        prose = CODE_BLOCK.sub("\n", event["text"])[-4000:]
        sentences = [x.strip(" \t-*>") for x in SENTENCE_END.split(prose)]
        sentences = [x for x in sentences if x]
        picked = None
        for n, sentence in enumerate(sentences):
            if PROPOSAL.search(sentence) and not sentence.endswith(("?", "؟")):
                picked = n
            elif OFFER.match(sentence) and not CONTINUE_ONLY.search(sentence.rstrip("?؟ ")):
                picked = n
        if picked is None:
            self.state["proposal"] = {}
            return
        text, reason = _split_reason(sentences[picked])
        if not reason and picked + 1 < len(sentences) and REASON_NEXT.match(sentences[picked + 1]):
            reason = REASON_NEXT.sub("", sentences[picked + 1]).rstrip(".!")
        self.state["proposal"] = {"text": _short(self.clean(text), 300),
                                  "reason": _short(self.clean(reason), 200), "line": event["line"]}

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
            keep["time"] = event.get("time", "")
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
                self.state["touched"][rel] = event["line"]
                self._add("file", f"Changed {rel} ({count} edit{'s' if count > 1 else ''})", event,
                          key=f"file|{self.sid}|{rel}")
        elif name == "Bash":
            self._bash(call["command"], event, ok, call.get("time", ""))
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

    def _bash(self, command: str, event: dict, ok: bool, started: str = "") -> None:
        if ok and re.search(r"\bgit\b[^|;&]*\bcommit\b", command):
            found = [(b, sha, msg) for b, sha, msg in COMMIT_LINE.findall(event["text"])]
            if not found and started:  # `git commit -q` prints nothing: ask git what was committed
                found = self._commits_since(started, event)
            for found_branch, sha, message in found:
                entry = {"hash": sha[:9], "message": _short(self.clean(message), 160),
                         "branch": found_branch, "time": event.get("time", "")}
                if not any(c["hash"][:7] == entry["hash"][:7] for c in self.state["commits"]):
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

    def _commits_since(self, started: str, event: dict) -> list[tuple[str, str, str]]:
        try:
            since = datetime.datetime.fromisoformat(started) - datetime.timedelta(seconds=2)
        except ValueError:
            return []
        cwd = Path(event.get("cwd") or self.state["cwd"] or self.root)
        out = store._git(cwd, "log", "-n", "20", "--reverse", f"--since={since.isoformat()}",
                         "--format=%H%x09%s")
        branch = event.get("branch") or self.state["branch"]
        return [(branch, sha, message) for sha, _, message in
                (line.partition("\t") for line in out.splitlines()) if sha]

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
        if event["kind"] in ("prompt", "say", "tool", "result"):
            getattr(capture, event["kind"])(event)
    memory.upsert(capture.memories)
    save_state(memory.dir, state)
    return state
