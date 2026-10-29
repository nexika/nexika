#!/usr/bin/env python3
"""prof_courses - reviewed lessons from nexika/courses for prof's lessons (stdlib only).

prof clones https://github.com/nexika/courses into its data folder the first time a lesson is looked
for, and pulls it at most once a week after that. No hook calls this: only /prof:learn does. Only
lessons the courses repo marks reviewed or verified are offered. If the clone or the pull fails,
nothing is offered and prof teaches as usual.

Commands:
  prof_courses.py find TOPIC [--lang en|ar|fr]   the lessons that match a topic, with their files
  prof_courses.py lesson ID [--lang en|ar|fr]    one lesson's files
  prof_courses.py list [--lang en|ar|fr]         every lesson prof may teach from
  prof_courses.py update                         pull now

Data: <PROF_HOME>/courses (the clone) and <PROF_HOME>/courses.json (when it was last fetched).
PROF_COURSES_URL points at another copy of the repository (tests use a local one).
"""
from __future__ import annotations

import datetime
import json
import os
import re
import shutil
import subprocess
import sys
import unicodedata
from pathlib import Path

HOME = Path(os.environ.get("PROF_HOME") or Path.home() / ".claude" / "nexika" / "prof")
CLONE = HOME / "courses"
STATE = HOME / "courses.json"
URL = os.environ.get("PROF_COURSES_URL") or "https://github.com/nexika/courses.git"
PULL_DAYS = 7
TEACH = ("reviewed", "verified")   # maintainer's choice (#442): "checked" lessons have no reviews yet
GIT_TIMEOUT = 120
TOOL_TIMEOUT = 60

# Words that say nothing about the topic. "claude" is in almost every lesson of the first course.
STOP = set("""
a an the to of in on at by for and or with without from into is are be how what why when which who do does
i me my we our you your it its this that these those can could should would want need about some any
teach learn lesson lessons course explain show give help please tell work works
claude
في من على عن الى إلى كيف ما ماذا لماذا هل مع او أو و علمني اشرح درس
le la les l de des du d un une et ou en au aux pour sur avec comment quoi est sont je me moi nous vous
""".split())
WORD = re.compile(r"\w+")


def today() -> datetime.date:
    return datetime.date.today()


def _git(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0")   # never wait for a password
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, timeout=GIT_TIMEOUT,
                          env=env)


def _fetched() -> datetime.date | None:
    try:
        return datetime.date.fromisoformat(json.loads(STATE.read_text(encoding="utf-8"))["fetched"])
    except (OSError, ValueError, KeyError, TypeError):
        return None


def _mark_fetched() -> None:
    HOME.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps({"fetched": today().isoformat(), "url": URL}) + "\n", encoding="utf-8")


def update(force: bool = False) -> tuple[bool, str]:
    """Clone the courses if there is no clone, pull if the last fetch is a week old (or force).
    Returns whether a clone is there to read, and what happened."""
    try:
        if not (CLONE / ".git").is_dir():
            shutil.rmtree(CLONE, ignore_errors=True)
            CLONE.parent.mkdir(parents=True, exist_ok=True)
            done = _git("clone", "--depth", "1", "--quiet", URL, str(CLONE))
            if done.returncode != 0:
                shutil.rmtree(CLONE, ignore_errors=True)
                return False, f"could not clone {URL}: {done.stderr.strip()[:200]}"
            _mark_fetched()
            return True, "cloned"
        fetched = _fetched()
        if not force and fetched is not None and (today() - fetched).days < PULL_DAYS:
            return True, f"up to date (fetched {fetched.isoformat()})"
        done = _git("pull", "--ff-only", "--quiet", cwd=CLONE)
        if done.returncode != 0:
            return True, f"could not update, using the copy from {fetched or 'an earlier day'}"
        _mark_fetched()
        return True, "updated"
    except (OSError, subprocess.SubprocessError) as exc:
        return (CLONE / ".git").is_dir(), f"{type(exc).__name__}: {exc}"


def _read_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def statuses(course_id: str) -> dict[str, str]:
    """Each lesson's status from the courses repo's own tool. Without --run it reads the files and the
    recorded reviews; it never runs lesson code. Any failure means no statuses, so nothing is taught."""
    tool = CLONE / "bin" / "courses"
    try:
        done = subprocess.run([sys.executable, "-I", str(tool), "status", "--json", course_id], cwd=CLONE,
                              capture_output=True, text=True, timeout=TOOL_TIMEOUT)
        rows = json.loads(done.stdout) if done.returncode == 0 else []
    except (OSError, ValueError, subprocess.SubprocessError):
        return {}
    return {row["lesson"]: row["status"] for row in rows if isinstance(row, dict)
            and isinstance(row.get("lesson"), str) and isinstance(row.get("status"), str)}


def _summary(folder: Path) -> str:
    """What each language's text says the lesson teaches: its first section (the goals) and the first
    paragraph of the next (the idea), without footnote marks."""
    parts = []
    for path in sorted(folder.glob("*.md")):
        try:
            sections = re.split(r"^## .*$", path.read_text(encoding="utf-8"), flags=re.M)
        except OSError:
            continue
        idea = sections[2].strip().split("\n\n")[0] if len(sections) > 2 else ""
        parts.append((sections[1] if len(sections) > 1 else "") + " " + idea)
    return re.sub(r"\[\^[^\]]*\]", " ", " ".join(parts))


def lessons() -> list[dict]:
    """Every lesson prof may teach from, in course order."""
    found = []
    for course_file in sorted(CLONE.glob("courses/*/course.json")):
        course = _read_json(course_file)
        course_id = course_file.parent.name
        status = statuses(course_id)
        listed = _read_json(course_file.parent / "competencies.json").get("competencies") or []
        skills = {c.get("id"): c for c in listed if isinstance(c, dict)}
        for module in course.get("modules") or []:
            for lesson_id in module.get("lessons") or []:
                if status.get(lesson_id) not in TEACH:
                    continue
                folder = course_file.parent / "lessons" / lesson_id
                meta = _read_json(folder / "lesson.json")
                taught = [skills[c] for c in meta.get("competencies") or [] if c in skills]
                found.append({
                    "id": lesson_id, "course": course_id, "status": status[lesson_id],
                    "title": meta.get("title") or {}, "module": meta.get("module") or module.get("id"),
                    "level": meta.get("level"), "minutes": meta.get("minutes"),
                    "prerequisites": meta.get("prerequisites") or [],
                    "concepts": [c for skill in taught for c in skill.get("concepts") or []],
                    "can": [text for skill in taught for text in (skill.get("can") or {}).values()],
                    "summary": _summary(folder),
                })
    return found


def words(text: str) -> set[str]:
    """Lowercase words without accents or Arabic marks, plurals folded, filler dropped."""
    plain = "".join(ch for ch in unicodedata.normalize("NFKD", text.replace("_", " "))
                    if unicodedata.category(ch) != "Mn")
    out = set()
    for word in WORD.findall(plain.lower()):
        if len(word) < 2 or word in STOP:
            continue
        if word.isascii() and len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
            word = word[:-1]
        if word.startswith("ال") and len(word) > 4:
            word = word[2:]
        out.add(word)
    return out


def score(topic_words: set[str], lesson: dict) -> int:
    """A title word counts 3, a concept 2, the rest of what the lesson teaches 1 (its skills, goals and
    the first paragraph of its idea); each topic word scores its best field."""
    fields = ((3, " ".join(lesson["title"].values())), (2, " ".join(lesson["concepts"])),
              (1, " ".join(lesson["can"]) + " " + lesson["id"] + " " + lesson.get("summary", "")))
    weights = [(weight, words(text)) for weight, text in fields]
    return sum(max((weight for weight, found in weights if word in found), default=0) for word in topic_words)


def find(topic: str, candidates: list[dict], limit: int = 3) -> list[dict]:
    """The lessons that match a topic, best first. A lesson needs at least a concept's worth of match
    and half the best lesson's score, so a passing word doesn't pull in an unrelated lesson."""
    topic_words = words(topic)
    if not topic_words:
        return []
    # Best score first; a tie goes to the lesson that comes first in the course.
    scored = sorted(((score(topic_words, lesson), i) for i, lesson in enumerate(candidates)),
                    key=lambda pair: (-pair[0], pair[1]))
    best = scored[0][0] if scored else 0
    return [candidates[i] for points, i in scored if points >= max(2, best / 2)][:limit] if best >= 2 else []


def files(lesson: dict, lang: str) -> dict[str, Path]:
    base = CLONE / "courses" / lesson["course"] / "lessons" / lesson["id"]
    text = base / f"{lang}.md"
    return {"text": text if text.is_file() else base / "en.md", "quiz": base / "quiz.json",
            "sources": base / "sources.json", "exercise": base / "exercise", "folder": base}


def describe(lesson: dict, lang: str) -> str:
    title = lesson["title"].get(lang) or lesson["title"].get("en") or lesson["id"]
    paths = files(lesson, lang)
    lines = [f"{lesson['id']}: {title} ({lesson['status']}, module {lesson['module']}, "
             f"level {lesson['level']}, about {lesson['minutes']} min)",
             f"   text: {paths['text']}",
             f"   quiz: {paths['quiz']}",
             f"   exercise: {paths['exercise']} (exercise.json, starter/, tests/; solution/ is the answer)",
             f"   sources: {paths['sources']}"]
    if lesson["prerequisites"]:
        lines.append(f"   comes after: {', '.join(lesson['prerequisites'])}")
    return "\n".join(lines)


def _lang(argv: list[str]) -> str:
    if "--lang" in argv and argv.index("--lang") + 1 < len(argv):
        return argv[argv.index("--lang") + 1]
    return "en"


def main(argv: list[str]) -> int:
    args = [a for i, a in enumerate(argv[1:], 1) if a != "--lang" and argv[i - 1] != "--lang"]
    cmd, rest = (args[0], args[1:]) if args else ("", [])
    lang = _lang(argv)
    if cmd == "update":
        ok, message = update(force=True)
        print(f"nexika/courses: {message}")
        return 0 if ok else 1
    if cmd not in ("find", "lesson", "list") or (cmd != "list" and not rest):
        print(__doc__)
        return 2
    ok, message = update()
    available = lessons() if ok else []
    if cmd == "find":
        topic = " ".join(rest)
        found = find(topic, available)
        if not found:
            why = f" ({message})" if not ok else ""
            print(f"No reviewed course lesson matches {topic!r}: teach as usual{why}.")
            return 0
        print(f"Reviewed lessons from nexika/courses for {topic!r}, best first:")
    elif cmd == "lesson":
        found = [lesson for lesson in available if lesson["id"] == rest[0]]
        if not found:
            print(f"No reviewed lesson {rest[0]!r}" + (f" ({message})" if not ok else "") + ".")
            return 1
    else:
        found = available
        if not found:
            print("No reviewed course lessons" + (f" ({message})" if not ok else "") + ".")
            return 0
    for n, lesson in enumerate(found, 1):
        print(f"{n}. {describe(lesson, lang)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
