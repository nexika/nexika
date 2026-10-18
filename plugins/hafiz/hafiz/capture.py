"""Turn transcript events into session state and typed memories, with fixed rules (no AI).

What is captured, and from where:
    decision  answers to Claude's multiple-choice questions, approved plans, Claude's proposals the
              user agrees to ("I suggest ..." then "yes" / "تمام"), and sentences of user messages
              that start with a choice ("let's go with", "don't use", "قررنا", "نستخدم" ...), state
              a rule in plain words ("compare X with Y, not Z", "never ...", "X must stay ..."), or
              stand under a label ("Decisions:", "Some rules for this work:"), with the reason when
              one is given ("because ...", "لأن ..."); never Claude's own words
    task      Claude's task list (TodoWrite, TaskCreate/TaskUpdate), kept up to date
    problem   a failing test/build/lint command (also when piped through `tail`: the summary line
              says it failed), marked solved when the same command passes
    file      files Claude changed (Edit, Write, MultiEdit, NotebookEdit) and, at the end of each
              turn, files git shows as written since the session began (edits made through Bash:
              `sed -i`, a heredoc, a script), one memory per file
    link      URLs the user shares and pull requests or issues created during the session
    commit    commits made in the session, from `git commit` output or, when it prints nothing, `git log`
    plan      (session state) the numbered steps of a prompt about a plan, or of an approved plan; the
              step asked for last ("do step 4", "the next step") and the steps Claude said are done;
              a new session on the same branch starts from the last one's plan

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
MAX_GIT_FILES = 40           # files taken from git at the end of one turn
GIT_JUNK = re.compile(r"(?:^|/)(?:__pycache__|\.pytest_cache|\.mypy_cache|\.ruff_cache|node_modules|\.venv|"
                      r"venv|\.tox|\.idea|\.vscode)/|\.py[co]$|(?:^|/)\.DS_Store$")

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
# A rule stated in plain words (#369). Precision matters more than recall: every captured line is
# read again after each compaction, so a sentence only counts when its shape says how the work is
# to be done, never because it has "not" in it.
_LEAD = (r"^(?:[\w-]+:\s+)?(?:(?:ok(?:ay)?|yes|so|and|also|but|then|please|good|great|fine|note|"
         r"remember|important)\b[,.!:]?\s+)*")
_HOW = (r"(?:use|compare|store|keep|format|name|represent|round|sort|return|write|parse|encode|match|"
        r"model|validate|log|raise|handle|treat|prefer|call|save|print|express|measure|count|put)")
_NOT_A_CHOICE = (r"(?!(?:much|yet|now|sure|bad|really|quite|so|too|very|only|just|always|necessarily|"
                 r"exactly|all|everything|anything|that|this|here|there|later|today|again|me|us|it)\b)")
_NOT_A_RULE = (r"(?!(?:worry|forget|hesitate|bother|mind|ask|wait|know|think|understand|see|get|need|"
               r"panic|apologi[sz]e|stop|reply|respond|explain|summari[sz]e|repeat|be|tell|show|again|"
               r"seen|been|done|had|heard|the|a|an|this|that|it|so|too|really|sure)\b|\w+ed\b)")
RULE_EN = re.compile(
    _LEAD + r"(?:"
    # how to do it, against an alternative: "compare names with casefold(), not lower()"
    rf"{_HOW}\s+(?!me\b|us\b|going\b)[^.?!]*?(?:[,;:]\s*(?:and\s+|but\s+)?(?:not|never)\s+{_NOT_A_CHOICE}\S|"
    r"\s(?:instead of|rather than)\s)"
    # a standing prohibition: "never mutate ...", "don't change the format of ..."
    rf"|(?:never|don'?t|do not)\s+{_NOT_A_RULE}\w|always\s+{_HOW}\b"
    # something that must stay as it is: "the public API must stay backwards compatible"
    r"|(?!(?:it|this|that|there|these|those|which|what|you|i|he|she|they|we)\b)[\w`'\"./()\[\], -]{2,80}?\s"
    r"(?:(?:must|has to|have to)\s+(?:always\s+|never\s+|not\s+)?(?:stay|remain|keep|use|return|match|"
    r"follow|work|accept|support|change)|must (?:not|never) be)\b"
    # a convention for every case: "print every date as DD.MM.YYYY"
    rf"|{_HOW}\s+(?:every|all|each|any)\s+[^.?!]{{1,60}}?\s(?:as|in|with|using|like|by)\b"
    r")", re.I)
# "Decisions:", "Some rules for this work:", "قواعد:": every sentence of that paragraph is one.
RULES_LABEL = re.compile(
    r"^(?:(?:some|a few|few|the|our|my|two|three|four|important|ground|house|key)\s+){0,2}"
    r"(?:rules?|decisions?|constraints?|conventions?|guidelines?)(?:\s+(?:for|of|in|to)\b[^:\n]{0,30})?\s*:"
    r"|^(?:ال)?(?:قواعد|قرارات|القواعد|القرارات)[^:\n]{0,30}:", re.I)
# ... unless it is about this moment or this reply, not the work: "don't commit yet", "write a
# short summary, not a report", "use git log to see what changed, not blame".
ONE_OFF = re.compile(r"\b(?:yet|for now|right now|this time|for the moment|summary|summari[sz]e|report|"
                     r"answer|reply|response|explanation|explain)\b|"
                     r"\bto (?:see|check|find|look|debug|understand|figure|investigate|reproduce)\b", re.I)
PARAGRAPH = re.compile(r"\n\s*\n")
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
MAX_DECISIONS_PER_PROMPT = 6
QUESTION = re.compile(r"^(why|what|which|how|should|shall|could|can|would|do|does|did|is|are|"
                      r"هل|ليش|لماذا|ليه|كيف|ايش|شو|ماذا)\b", re.I)
URL = re.compile(r"https?://[^\s<>\"'`)\]]+")
GH_REF = re.compile(r"https://github\.com/[\w.-]+/[\w.-]+/(?:pull|issues)/\d+")
COMMIT_LINE = re.compile(r"^\[([^\s\]]+)(?: \(root-commit\))? ([0-9a-f]{7,40})\] (.+)$", re.M)
RUNNERS = re.compile(
    r"(?:^|[;&|(\n]\s*|\b(?:uv run|poetry run|npx|bunx|python3? -m|sudo|time)\s+)"
    r"(pytest|py\.test|unittest|tox|nox|ruff|mypy|flake8|pylint|npm (?:run )?(?:test|build|lint)|"
    r"pnpm (?:run )?(?:test|build|lint)|yarn (?:test|build|lint)|bun test|vitest|jest|eslint|tsc|"
    r"go (?:test|build|vet)|cargo (?:test|build|clippy|check)|dotnet (?:test|build)|mvn|gradle|"
    r"gradlew|make|ctest|phpunit|rspec|swift (?:test|build)|flutter (?:test|analyze)|"
    r"claude plugin validate)(?=[\s;&|)]|$)([^;&|\n]*)")
# The body of a heredoc is a file's text (`cat > test_x.py <<'EOF'`), not commands that ran.
HEREDOC = re.compile(r"<<-?\s*(['\"]?)(\w+)\1[^\n]*\n.*?\n\s*\2\s*(?=\n|$)", re.S)
# A test run piped through `tail` exits 0 even when tests fail: its summary line still says so.
FAILED_RUN = re.compile(
    r"^(?:FAILED \((?:failures|errors)=\d+|=+ .*\b[1-9]\d* (?:failed|errors?)\b|[1-9]\d* failed\b|"
    r"--- FAIL:|FAIL\t|Tests:\s+[1-9]\d* failed\b|\s*[1-9]\d* failing\b)", re.M)
ERROR_LINE = re.compile(r"(error|failed|failure|exception|traceback|assert|panic|fatal|خطأ)", re.I)
ANSWER = re.compile(r'"([^"\n]{3,300})"\s*=\s*"([^"\n]{1,300})"')
# The session's plan (#370): a numbered list of steps in a prompt that speaks of a plan or steps, or
# in an approved plan; which step was asked for last, and which steps Claude said are done.
PLAN_STEP = re.compile(r"^[ \t]*(?:#+[ \t]*|[-*][ \t]+)?(?:step[ \t]+)?(\d{1,2})[.):][ \t]+(\S.*)$",
                       re.M | re.I)
PLAN_WORDS = re.compile(r"\b(?:plan|steps?)\b", re.I)
STEP_ASKED = re.compile(r"\bsteps? (\d{1,2})(?:\s*(?:-|–|to|and|,)\s*(\d{1,2}))?\b", re.I)
NEXT_STEP = re.compile(r"\bnext step\b", re.I)
STEPS_DONE = re.compile(r"\bsteps? ((?:\d{1,2}(?:\s*(?:,|and|&|to|-|–)\s*)?)+?) (?:is|are) (?:now |all )?"
                        r"(?:done|complete|completed|finished)\b", re.I)
PLAN_DONE = re.compile(r"\b(?:whole|entire) plan is (?:now )?(?:done|complete|finished)\b|"
                       r"\ball (?:the )?steps are (?:now )?(?:done|complete|finished)\b", re.I)
STEP_CHARS = 220
MAX_STEPS = 20


def plan_steps(text: str) -> list[str]:
    """The steps of a numbered list (1., 2., 3., ... at least three, in order), each on one line."""
    steps: list[str] = []
    for match in PLAN_STEP.finditer(text):
        number = int(match.group(1))
        if number == len(steps) + 1:
            steps.append(_short(match.group(2), STEP_CHARS))
        elif number == 1 and len(steps) >= 3:
            break  # a second list after the plan
    return steps[:MAX_STEPS] if len(steps) >= 3 else []


def _numbers(text: str) -> set[int]:
    """{4, 5, 6} from "4 to 6", "4-6", "4, 5 and 6"."""
    found = set()
    for low, high in re.findall(r"(\d{1,2})\s*(?:-|–|to)\s*(\d{1,2})", text):
        found.update(range(int(low), int(high) + 1))
    found.update(int(n) for n in re.findall(r"\d{1,2}", text))
    return found


def _short(text: str, limit: int) -> str:
    flat = re.sub(r"\s+", " ", text).strip()
    return flat if len(flat) <= limit else flat[: limit - 1].rsplit(" ", 1)[0] + "…"


def _split_reason(sentence: str) -> tuple[str, str]:
    """("use X", "it is faster") from "use X because it is faster."."""
    parts = REASON.split(sentence, maxsplit=1)
    if len(parts) == 2 and parts[1].strip():
        return parts[0].strip().rstrip(","), parts[1].strip().rstrip(".!")
    return sentence, ""


def decision_sentences(text: str) -> list[str]:
    """The sentences of a user's message that state how the work is to be done.

    A sentence counts when it starts with a choice ("let's use", "قررنا"), states a rule in plain
    words ("compare X with Y, not Z", "never ...", "X must stay ..."), or stands in a paragraph
    labelled as rules ("Decisions:", "Some rules for this work:"). Quoted lines (">") and code are
    left out, and so is a question.
    """
    text = CODE_BLOCK.sub("\n", text)[:8000]
    text = "\n".join(ln for ln in text.splitlines() if not ln.lstrip().startswith(">"))
    found = []
    for paragraph in PARAGRAPH.split(text):
        paragraph = paragraph.strip()
        label = RULES_LABEL.match(paragraph)
        if label:
            paragraph = paragraph[label.end():]
        for sentence in SENTENCE_END.split(paragraph):
            sentence = sentence.strip(" \t-*>•")
            if len(sentence) < 12 or sentence.endswith(("?", "؟")) or QUESTION.match(sentence):
                continue  # a question is not a decision
            if (label or DECISION_EN.search(sentence) or DECISION_AR.search(sentence)
                    or (RULE_EN.search(sentence) and not ONE_OFF.search(sentence))):
                found.append(sentence)
    return found


def _said_key(sentence: str) -> str:
    flat = re.sub(r"\s+", " ", sentence).strip(" .!").lower()
    return hashlib.sha1(flat.encode()).hexdigest()[:10]


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


def git_changes(top: Path, since: float) -> dict[str, int]:
    """Files git shows as changed or new in the working tree at `top`, written at or after `since`
    (seconds since the epoch), as {path: mtime in ns}. Edits made through Bash (`sed -i`, a heredoc,
    a script) show up here, where no Edit call names them; a file left changed before the session
    started does not. Caches and build folders are left out."""
    out = store._git(top, "status", "--porcelain=v1", "-z", "--untracked-files=all", raw=True)
    records = out.split("\0")
    found: dict[str, int] = {}
    skip = False
    for record in records:
        if skip:  # the old name of a rename
            skip = False
            continue
        if len(record) < 4:
            continue
        code, path = record[:2], record[3:]
        skip = "R" in code or "C" in code
        if "D" in code or GIT_JUNK.search(path):
            continue
        try:
            mtime = (top / path).stat().st_mtime_ns
        except OSError:
            continue
        if mtime >= (since - 2) * 1e9:
            found[path] = mtime
            if len(found) >= MAX_GIT_FILES:
                break
    return found


def commit_files(cwd: Path, sha: str) -> list[str]:
    """The files a commit changed, relative to the repository."""
    out = store._git(cwd, "diff-tree", "--no-commit-id", "--name-only", "-r", "-z", "--root", sha, raw=True)
    return [p for p in out.split("\0") if p and not GIT_JUNK.search(p)][:MAX_GIT_FILES]


def clean_plan(plan) -> dict:
    """A plan read from a file ({} when it is not one): steps are text, `asked` and `done` step numbers."""
    if not isinstance(plan, dict) or not isinstance(plan.get("steps"), list) or not plan["steps"] \
            or not all(isinstance(step, str) for step in plan["steps"]):
        return {}
    asked, done = plan.get("asked", 0), plan.get("done", [])
    return {"steps": list(plan["steps"]), "asked": asked if type(asked) is int else 0,
            "done": [n for n in done if type(n) is int] if isinstance(done, list) else []}


def inherited_plan(folder: Path, branch: str, session: str) -> dict:
    """The plan of the latest earlier session on this branch, for a new session that carries on."""
    best, found = "", {}
    for path in (folder / "sessions").glob("*.json"):
        other = store.read_json(path, {})
        plan = clean_plan(other.get("plan"))
        updated = other.get("updated", "")
        if (other.get("session") != session and other.get("branch") == branch and plan
                and isinstance(updated, str) and updated > best):
            best, found = updated, plan
    return found


def _epoch(stamp: str) -> float:
    try:
        return datetime.datetime.fromisoformat(stamp).timestamp()
    except (ValueError, TypeError):
        return 0.0


def new_state(session: str, transcript_path: str) -> dict:
    return {"session": session, "transcript": transcript_path, "offset": 0, "line": 0,
            "started": store.now(), "updated": "", "ended": "", "branch": "", "cwd": "",
            "first_prompt": "", "prompts": [], "prompt_count": 0, "files": {}, "commits": [],
            "tasks": {}, "task_ids": {}, "problems": {}, "decisions": [], "links": [], "pending": {},
            "proposal": {}, "touched": {}, "said": [], "since": "", "seen": {}, "plan": {},
            "note": "", "compactions": 0, "private_salt": "", "private": []}


def state_path(folder: Path, session: str) -> Path:
    return folder / "sessions" / f"{store.safe_name(session, 64)}.json"


def typed(data: dict, session: str = "", transcript_path: str = "") -> dict:
    """A session state read from a file: a field missing or of the wrong type (a damaged or hand-edited
    file) gets its default, so it never breaks capture or a card."""
    state = new_state(session, transcript_path)
    state.update({k: v for k, v in data.items() if k in state and type(v) is type(state[k])})
    state["plan"] = clean_plan(state["plan"])
    return state


def load_state(folder: Path, session: str, transcript_path: str = "") -> dict:
    state = typed(store.read_json(state_path(folder, session), {}), session, transcript_path)
    if transcript_path and transcript_path != state["transcript"]:
        state.update(transcript=transcript_path, offset=0, line=0, pending={})
    return state


def save_state(folder: Path, state: dict) -> None:
    state["updated"] = store.now()
    store.write_json(state_path(folder, state["session"]), state)


def change_state(folder: Path, session: str, change) -> dict:
    """Load a session's state, apply `change(state)` and save it, under the lock `update` holds, so
    a capture running at the same time never writes over the change (or the change over it)."""
    with store.locked(folder / "sessions", timeout=8):
        state = load_state(folder, session)
        change(state)
        save_state(folder, state)
        return state


class Capture:
    """Applies the rules to new events of one session."""

    def __init__(self, root: Path, state: dict, commit: str):
        self.root, self.state, self.commit = root, state, commit
        self.memories: list[dict] = []
        self._memories: list[dict] | None = None
        self.sid = state["session"][:8]
        self.edited: set[str] = set()  # files an Edit call (or a commit) counted in this run

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
        said = set(state.get("said") or [])
        for sentence in decision_sentences(text):
            if _said_key(sentence) in said:
                continue  # the agent's own words, pasted back
            sentence = _short(sentence, 300)
            if sentence not in state["decisions"]:
                state["decisions"].append(sentence)
                self._add("decision", f"User: {sentence}", event, key=f"decision|{self.sid}|{sentence[:80]}",
                          reason=_split_reason(sentence)[1])
                found += 1
                if found >= MAX_DECISIONS_PER_PROMPT:
                    break
        self._plan_prompt(CODE_BLOCK.sub("\n", text))

    def _plan_prompt(self, text: str, approved: bool = False) -> None:
        """A numbered plan replaces the one before; "do step 4" or "the next step" moves it on."""
        steps = plan_steps(text) if approved or PLAN_WORDS.search(text) else []
        plan = self.state.get("plan") or {}
        if steps and steps != plan.get("steps"):
            plan = self.state["plan"] = {"steps": steps, "asked": 0, "done": []}
        if not plan.get("steps"):
            return
        count = len(plan["steps"])
        asked = [n for match in STEP_ASKED.finditer(text) for n in _numbers(match.group(0)) if 0 < n <= count]
        if asked:
            plan["asked"] = max(asked)
        elif NEXT_STEP.search(text):
            plan["asked"] = min(count, max([plan.get("asked", 0), *plan.get("done", [])]) + 1)

    def _plan_said(self, prose: str) -> None:
        """Claude's "Step 3 is done." / "Steps 4 and 5 are done" / "the whole plan is finished"."""
        plan = self.state.get("plan") or {}
        if not plan.get("steps"):
            return
        count = len(plan["steps"])
        done = set(plan.get("done", []))
        if PLAN_DONE.search(prose):
            done = set(range(1, count + 1))
        for match in STEPS_DONE.finditer(prose):
            done.update(n for n in _numbers(match.group(1)) if 0 < n <= count)
        plan["done"] = sorted(done)

    def say(self, event: dict) -> None:
        """Remember Claude's latest proposal, so a "yes" in the next prompt records it as a decision."""
        prose = CODE_BLOCK.sub("\n", event["text"])[-4000:]
        sentences = [x.strip(" \t-*>") for x in SENTENCE_END.split(prose)]
        sentences = [x for x in sentences if x]
        self.state["said"] = (self.state.get("said", []) + [_said_key(x) for x in sentences])[-80:]
        self._plan_said(prose)
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
            # a script's text can be long: the commands around it are what counts
            keep["command"] = self.clean(HEREDOC.sub("\n", str(data.get("command") or ""))[:2000])
            keep["time"] = event.get("time", "")
        elif name == "TaskCreate":
            keep["subject"] = self.clean(str(data.get("subject") or ""))
        elif name == "AskUserQuestion":
            pass
        elif name == "ExitPlanMode":
            keep["plan"] = self.clean(str(data.get("plan") or "")[:6000])
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
                self.edited.add(rel)
                self._file(rel, event)
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
            self._plan_prompt(call["plan"], approved=True)

    def _file(self, rel: str, event: dict) -> None:
        count = self.state["files"].get(rel, 0) + 1
        self.state["files"][rel] = count
        self.state["touched"][rel] = event["line"]
        self._add("file", f"Changed {rel} ({count} edit{'s' if count > 1 else ''})", event,
                  key=f"file|{self.sid}|{rel}")

    def from_git(self, cwd: Path, event: dict) -> None:
        """At the end of a turn: files changed through Bash, which no Edit call names (#369).

        A file counts once per turn in which it was written, and not again when an Edit call of the
        same turn already counted it.
        """
        since = _epoch(self.state.get("since") or self.state["started"])
        if not since:
            return
        top = _TOPS.get(str(cwd)) or store.worktree_root(cwd)
        _TOPS[str(cwd)] = top
        seen = self.state.setdefault("seen", {})
        for path, mtime in git_changes(top, since).items():
            rel = self.clean(path)
            if seen.get(rel) == mtime:
                continue
            seen[rel] = mtime
            if rel not in self.edited:
                self._file(rel, event)
        if len(seen) > 200:
            self.state["seen"] = dict(list(seen.items())[-200:])

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
                    # files committed in the same turn are clean again by the end of it
                    cwd = Path(event.get("cwd") or self.state["cwd"] or self.root)
                    for path in commit_files(cwd, sha):
                        rel = self.clean(path)
                        if rel not in self.state["files"]:
                            self.edited.add(rel)
                            self._file(rel, event)
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
        if ok and FAILED_RUN.search(event["text"]):
            ok = False
        targets = sorted(a for a in runner.group(2).split()
                         if not a.startswith("-") and not any(c in a for c in "<>"))[:6]
        if family == "unittest" and "discover" in targets:
            targets = []  # `unittest discover -s tests` runs the whole suite
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
    if not state["prompt_count"] and not state["plan"] and state["branch"]:
        state["plan"] = inherited_plan(memory.dir, state["branch"], session)
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
        if not state["since"] and event.get("time"):
            state["since"] = event["time"]  # when the session began: older changes are not its own
        if event["kind"] in ("prompt", "say", "tool", "result"):
            getattr(capture, event["kind"])(event)
    if events:
        last = events[-1]
        capture.from_git(Path(state["cwd"] or root), {"line": last["line"], "time": last.get("time", ""),
                                                      "branch": state["branch"]})
    memory.upsert(capture.memories)
    save_state(memory.dir, state)
    return state
