"""lawha_data - read-only views of prof's learner files and a nexika/courses clone (stdlib only).

Nothing here writes. prof's formats (see plugins/prof/scripts/prof_store.py) are:
  topics/SLUG.md              "# Title" then "- [status] concept — evidence (YYYY-MM-DD)"
  reports/DATE_HHMM_SID8.md   fixed "## " sections; checklist lines
                              "- [status] topic-slug :: Topic Title :: concept :: evidence"
  profile.md                  free markdown
"""
from __future__ import annotations

import datetime
import json
import os
import re
import subprocess
import sys
from pathlib import Path

STATUSES = ("missed", "shaky", "not-checked", "understood")
STALE_DAYS = 14

TOPIC_LINE_RE = re.compile(
    r"^- \[(missed|shaky|not-checked|understood)\] (.+?) — (.*) \((\d{4}-\d{2}-\d{2})\)$"
)
CHECK_RE = re.compile(
    r"^\s*-\s*\[(missed|shaky|not-checked|understood)\]\s*"
    r"(.+?)\s*::\s*(.+?)\s*::\s*(.+?)\s*::\s*(.*?)\s*$"
)
REPORT_NAME_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})_(\d{2})(\d{2})_([\w-]{1,8})\.md$")
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,80}$")
ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,80}$")

# Report "## " heading (start, lowercase) -> key in the API.
SECTIONS = (
    ("what you learned", "learned"),
    ("what you did", "did"),
    ("comprehension checks", "checks"),
    ("weak areas", "weak"),
    ("level estimate", "levels"),
    ("review next time", "review_next"),
    ("concept checklist", "checklist"),
)


def prof_home() -> Path:
    return Path(os.environ.get("PROF_HOME") or Path.home() / ".claude" / "nexika" / "prof")


def courses_home() -> Path:
    return Path(os.environ.get("LAWHA_COURSES") or Path.home() / "nexika-courses")


def _read(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def _bullets(lines: list[str]) -> list[str]:
    return [re.sub(r"^\s*[-*]\s+", "", line).strip() for line in lines if line.strip()]


class Prof:
    """Read-only access to one prof data folder. `today` is fixed for demo data."""

    def __init__(self, home: Path, today: datetime.date | None = None):
        self.home = home
        self.today = today or datetime.date.today()
        self.cutoff = (self.today - datetime.timedelta(days=STALE_DAYS)).isoformat()

    # ------------------------------------------------------------ concepts and topics

    def _concept(self, topic: str, status: str, concept: str, evidence: str, date: str) -> dict:
        return {"topic": topic, "concept": concept, "status": status, "evidence": evidence,
                "date": date, "stale": status == "understood" and date < self.cutoff}

    def _topic_file(self, slug: str) -> tuple[str, list[dict]] | None:
        if not SLUG_RE.match(slug):
            return None
        text = _read(self.home / "topics" / f"{slug}.md")
        if text is None:
            return None
        title, concepts = slug, []
        for line in text.splitlines():
            if line.startswith("# "):
                title = line[2:].strip()
                continue
            m = TOPIC_LINE_RE.match(line.strip())
            if m:
                status, concept, evidence, date = m.groups()
                concepts.append(self._concept(slug, status, concept, evidence, date))
        rank = {s: i for i, s in enumerate(STATUSES)}
        concepts.sort(key=lambda c: (rank[c["status"]], not c["stale"], c["concept"].lower()))
        return title, concepts

    def _counts(self, concepts: list[dict]) -> dict:
        counts = {s: 0 for s in STATUSES}
        for c in concepts:
            counts[c["status"]] += 1
        counts["stale"] = sum(c["stale"] for c in concepts)
        return counts

    def topics(self) -> list[dict]:
        folder = self.home / "topics"
        out = []
        for path in sorted(folder.glob("*.md")) if folder.is_dir() else []:
            found = self._topic_file(path.stem)
            if not found or not found[1]:
                continue
            title, concepts = found
            fresh = sum(c["status"] == "understood" and not c["stale"] for c in concepts)
            out.append({"slug": path.stem, "title": title, "last": max(c["date"] for c in concepts),
                        "counts": self._counts(concepts), "mastery": round(fresh / len(concepts), 3)})
        out.sort(key=lambda t: (t["last"], t["slug"]), reverse=True)
        return out

    def topic(self, slug: str) -> dict | None:
        found = self._topic_file(slug)
        if not found:
            return None
        title, concepts = found
        return {"slug": slug, "title": title, "concepts": concepts}

    # ------------------------------------------------------------ reports

    def _report_paths(self) -> list[Path]:
        folder = self.home / "reports"
        if not folder.is_dir():
            return []
        return sorted((p for p in folder.glob("*.md") if REPORT_NAME_RE.match(p.name)), reverse=True)

    def _sections(self, text: str) -> dict[str, list[str]]:
        found: dict[str, list[str]] = {key: [] for _, key in SECTIONS}
        current = None
        for line in text.splitlines():
            if line.startswith("## "):
                heading = line[3:].strip().lower()
                current = next((key for start, key in SECTIONS if heading.startswith(start)), None)
                continue
            if current and line.strip():
                found[current].append(line)
        return found

    def _report(self, path: Path, full: bool) -> dict | None:
        m = REPORT_NAME_RE.match(path.name)
        text = _read(path)
        if not m or text is None:
            return None
        date, hh, mm, _sid = m.groups()
        raw = self._sections(text)
        out = {"id": path.stem, "date": date, "time": f"{hh}:{mm}",
               "learned": _bullets(raw["learned"]), "review_next": _bullets(raw["review_next"])}
        if not full:
            return out
        checks = []
        for line in raw["checks"]:
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) == 3 and not set(cells[0]) <= set("-: ") and cells[0].lower() != "question":
                checks.append({"q": cells[0], "answer": cells[1], "verdict": cells[2]})
        checklist = []
        for line in raw["checklist"]:
            cm = CHECK_RE.match(line)
            if cm:
                status, slug, _title, concept, evidence = cm.groups()
                checklist.append(self._concept(slug, status, concept, evidence or "-", date))
        out["sections"] = {"learned": out.pop("learned"), "did": _bullets(raw["did"]), "checks": checks,
                           "weak": _bullets(raw["weak"]), "levels": _bullets(raw["levels"]),
                           "review_next": out.pop("review_next"), "checklist": checklist}
        return out

    def sessions(self) -> list[dict]:
        return [r for r in (self._report(p, False) for p in self._report_paths()) if r]

    def session(self, sid: str) -> dict | None:
        if not REPORT_NAME_RE.match(f"{sid}.md"):
            return None
        path = self.home / "reports" / f"{sid}.md"
        return self._report(path, True) if path.is_file() else None

    # ------------------------------------------------------------ profile and summary

    def profile(self) -> dict:
        return {"markdown": _read(self.home / "profile.md")}

    def summary(self) -> dict:
        review, totals = [], {s: 0 for s in STATUSES} | {"stale": 0}
        topics = self.topics()
        for t in topics:
            for key, n in t["counts"].items():
                totals[key] += n
            for c in (self.topic(t["slug"]) or {}).get("concepts", []):
                if c["status"] in ("missed", "shaky") or c["stale"]:
                    review.append(c)
        rank = {"missed": 0, "shaky": 1}
        review.sort(key=lambda c: (rank.get(c["status"], 2), c["date"]))
        sessions = self._report_paths()
        last = REPORT_NAME_RE.match(sessions[0].name).group(1) if sessions else None
        return {"today": {"review": review, "counts": totals}, "topics": len(topics),
                "sessions": len(sessions), "last_session": last,
                "has_data": bool(topics or sessions or (self.home / "profile.md").is_file())}


# ---------------------------------------------------------------- course clone

def _status_json(root: Path, course_id: str) -> dict[str, str]:
    """Lesson statuses from `courses status --json`, if this clone's tool supports it; {} otherwise."""
    tool = root / "bin" / "courses"
    if not tool.is_file():
        return {}
    try:
        out = subprocess.run([sys.executable, str(tool), "status", "--json", course_id], cwd=root,
                             capture_output=True, text=True, timeout=60, check=False)
        rows = json.loads(out.stdout or "null")
    except (OSError, ValueError, subprocess.SubprocessError):
        return {}
    if not isinstance(rows, list):
        return {}
    return {str(r.get("lesson")): str(r.get("status")) for r in rows if isinstance(r, dict)}


def course(root: Path, course_id: str = "ai-engineering", statuses: dict[str, str] | None = None) -> dict:
    if not ID_RE.match(course_id):
        return {"available": False}
    base = root / "courses" / course_id
    try:
        meta = json.loads((base / "course.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"available": False}
    statuses = _status_json(root, course_id) if statuses is None else statuses
    modules = []
    for module in meta.get("modules", []):
        lessons = []
        for lid in module.get("lessons", []):
            lesson = {"id": lid, "title": {}, "minutes": None, "status": statuses.get(lid)}
            if ID_RE.match(str(lid)):
                try:
                    info = json.loads((base / "lessons" / lid / "lesson.json").read_text(encoding="utf-8"))
                    lesson.update(title=info.get("title", {}), minutes=info.get("minutes"))
                except (OSError, ValueError):
                    lesson["status"] = lesson["status"] or "planned"
            lessons.append(lesson)
        modules.append({"id": module.get("id"), "level": module.get("level"),
                        "title": module.get("title", {}), "lessons": lessons})
    return {"available": True, "course": {"id": meta.get("id"), "title": meta.get("title", {})},
            "modules": modules}
