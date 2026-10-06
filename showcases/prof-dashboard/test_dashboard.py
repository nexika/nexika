"""lawha: read-only parsing of prof's files, the course clone, and the local server's safety rules."""
from __future__ import annotations

import datetime
import http.client
import importlib.util
import json
import sys
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

# This showcase (the dashboard app built with lawha); prof's plugin for the format-pinning test.
LAWHA = Path(__file__).resolve().parent
PLUGINS = LAWHA.parent.parent / "plugins"


@pytest.fixture
def store(tmp_path, monkeypatch):
    """prof's real store module, its data in tmp_path/prof (the same fixture as tests/conftest.py)."""
    monkeypatch.setenv("PROF_HOME", str(tmp_path / "prof"))
    monkeypatch.delenv("PROF_REPORTING", raising=False)
    path = PLUGINS / "prof" / "scripts" / "prof_store.py"
    spec = importlib.util.spec_from_file_location("prof_store", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["prof_store"] = module
    spec.loader.exec_module(module)
    yield module
    sys.modules.pop("prof_store", None)
TODAY = datetime.date(2026, 10, 6)


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, LAWHA / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


data = _load("lawha_data")
server = _load("lawha_server")


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


@pytest.fixture
def prof_home(tmp_path):
    home = tmp_path / "prof"
    write(home / "profile.md", "# Learner\n- junior\n")
    write(home / "topics" / "git.md", "# Git\n\n"
          "- [missed] rebase vs merge — said they are the same (2026-10-05)\n"
          "- [understood] commits — made three clean commits (2026-10-04)\n"
          "- [understood] branches — explained HEAD (2026-09-01)\n")
    write(home / "reports" / "2026-10-05_1430_ab12cd34.md", "# Tutor session report - 2026-10-05\n\n"
          "## What you learned today\n- rebase: replays commits\n\n"
          "## Comprehension checks\n| Question | Learner's answer (short) | Verdict |\n|---|---|---|\n"
          "| Is rebase merge? | yes | wrong |\n\n"
          "## Review next time\n- rebase vs merge\n\n"
          "## Concept checklist\n- [missed] git :: Git :: rebase vs merge :: said they are the same\n")
    return home


# ---------------------------------------------------------------- parsing

def test_parser_is_pinned_to_prof_formats(store):
    """lawha has its own parser (plugins install separately); fail if prof's formats move."""
    assert data.TOPIC_LINE_RE.pattern == store.TOPIC_LINE_RE.pattern
    assert data.CHECK_RE.pattern == store.CHECK_RE.pattern
    assert data.STATUSES == store.STATUSES and data.STALE_DAYS == store.STALE_DAYS
    headings = [line[3:].lower() for line in store.REPORT_FORMAT.splitlines() if line.startswith("## ")]
    starts = [start for start, _ in data.SECTIONS]
    assert all(any(h.startswith(s) for s in starts) for h in headings), headings


def test_reads_what_prof_writes(store):
    line = "- [shaky] python-async :: Python async :: await in loops :: hesitated"
    report = write(store.REPORTS / "2026-10-05_0900_feedbeef.md", f"## Concept checklist\n{line}\n")
    store.merge_report(report)
    prof = data.Prof(store.HOME, TODAY)
    topic = prof.topic("python-async")
    assert topic["title"] == "Python async"
    assert topic["concepts"][0] == {"topic": "python-async", "concept": "await in loops", "status": "shaky",
                                    "evidence": "hesitated", "date": "2026-10-05", "stale": False}
    assert prof.sessions()[0]["id"] == "2026-10-05_0900_feedbeef"


def test_summary_review_list_and_stale(prof_home):
    s = data.Prof(prof_home, TODAY).summary()
    assert s["has_data"] and s["topics"] == 1 and s["sessions"] == 1 and s["last_session"] == "2026-10-05"
    assert s["today"]["counts"] == {"missed": 1, "shaky": 0, "not-checked": 0, "understood": 2, "stale": 1}
    assert [c["concept"] for c in s["today"]["review"]] == ["rebase vs merge", "branches"]


def test_topics_mastery_counts_only_fresh_understood(prof_home):
    [t] = data.Prof(prof_home, TODAY).topics()
    assert t["mastery"] == round(1 / 3, 3) and t["last"] == "2026-10-05"


def test_session_sections(prof_home):
    r = data.Prof(prof_home, TODAY).session("2026-10-05_1430_ab12cd34")
    assert r["time"] == "14:30"
    assert r["sections"]["checks"] == [{"q": "Is rebase merge?", "answer": "yes", "verdict": "wrong"}]
    assert r["sections"]["checklist"][0]["concept"] == "rebase vs merge"
    assert r["sections"]["review_next"] == ["rebase vs merge"]


def test_empty_home_has_no_data(tmp_path):
    s = data.Prof(tmp_path / "nothing", TODAY).summary()
    assert not s["has_data"] and s["today"]["review"] == [] and s["last_session"] is None


@pytest.mark.parametrize("slug", ["../profile", "..", "a/b", "Git", ""])
def test_unsafe_topic_slugs_are_refused(prof_home, slug):
    assert data.Prof(prof_home, TODAY).topic(slug) is None


@pytest.mark.parametrize("sid", ["../profile", "2026-10-05_1430_../x", "nope"])
def test_unsafe_session_ids_are_refused(prof_home, sid):
    assert data.Prof(prof_home, TODAY).session(sid) is None


def test_demo_data_parses():
    prof = data.Prof(server.DEMO, server.DEMO_TODAY)
    s = prof.summary()
    assert s["has_data"] and s["topics"] >= 3 and s["sessions"] >= 3 and s["today"]["review"]
    for session in prof.sessions():
        full = prof.session(session["id"])
        assert full["sections"]["checks"] and full["sections"]["checklist"]


def test_course_from_a_clone(tmp_path):
    base = tmp_path / "courses" / "ai-engineering"
    write(base / "course.json", json.dumps({"id": "ai-engineering", "title": {"en": "AI"}, "modules": [
        {"id": "m1", "level": 1, "title": {"en": "Basics"}, "lessons": ["l1-a", "l1-b"]}]}))
    write(base / "lessons" / "l1-a" / "lesson.json", json.dumps({"title": {"en": "A"}, "minutes": 30}))
    c = data.course(tmp_path, statuses={"l1-a": "reviewed"})
    assert c["available"]
    assert c["modules"][0]["lessons"] == [
        {"id": "l1-a", "title": {"en": "A"}, "minutes": 30, "status": "reviewed"},
        {"id": "l1-b", "title": {}, "minutes": None, "status": "planned"}]
    assert data.course(tmp_path / "missing", statuses={}) == {"available": False}


# ---------------------------------------------------------------- server

@pytest.fixture
def live(prof_home, tmp_path):
    dist = tmp_path / "dist"
    write(dist / "index.html", "<!doctype html><title>lawha</title>")
    write(dist / "assets" / "app.js", "console.log(1)")
    write(tmp_path / "secret.txt", "do not serve")
    app = server.App("tok-123", prof_home, tmp_path / "no-courses", dist)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.make_handler(app))
    app.port = httpd.server_address[1]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()

    def request(path, token="tok-123", host=None, method="GET"):
        conn = http.client.HTTPConnection("127.0.0.1", app.port, timeout=5)
        headers = {"Host": host or f"127.0.0.1:{app.port}"}
        if token:
            headers["X-Lawha-Token"] = token
        conn.request(method, path, headers=headers)
        resp = conn.getresponse()
        body = resp.read()
        conn.close()
        return resp, body

    yield request
    httpd.shutdown()
    httpd.server_close()


def test_api_needs_the_token(live):
    assert live("/api/summary", token=None)[0].status == 403
    assert live("/api/summary", token="wrong")[0].status == 403
    resp, body = live("/api/summary")
    assert resp.status == 200 and json.loads(body)["topics"] == 1


def test_foreign_host_is_refused(live):
    assert live("/api/summary", host="evil.example:80")[0].status == 403
    assert live("/", host="evil.example")[0].status == 403


def test_only_get(live):
    for method in ("POST", "PUT", "DELETE", "PATCH"):
        assert live("/api/summary", method=method)[0].status == 405


def test_routes_and_demo(live):
    assert json.loads(live("/api/topics/git")[1])["title"] == "Git"
    assert json.loads(live("/api/sessions")[1])[0]["id"] == "2026-10-05_1430_ab12cd34"
    assert json.loads(live("/api/profile")[1])["markdown"].startswith("# Learner")
    assert json.loads(live("/api/course")[1]) == {"available": False}
    demo = json.loads(live("/api/summary?demo=1")[1])
    assert demo["demo"] is True and demo["topics"] >= 3
    assert live("/api/topics/..%2Fprofile")[0].status == 404
    assert live("/api/nothing")[0].status == 404


def test_static_files_stay_inside_dist(live):
    resp, _ = live("/assets/app.js", token=None)
    assert resp.status == 200 and "javascript" in resp.getheader("Content-Type")
    assert live("/topics/git", token=None)[1].startswith(b"<!doctype html>")  # app route
    assert live("/../secret.txt", token=None)[0].status == 404
    assert live("/%2e%2e/secret.txt", token=None)[0].status == 404
    assert live("/assets/missing.js", token=None)[0].status == 404


def test_security_headers(live):
    resp, _ = live("/api/summary")
    assert resp.getheader("Access-Control-Allow-Origin") is None
    assert resp.getheader("Referrer-Policy") == "no-referrer"
    assert "frame-ancestors 'none'" in resp.getheader("Content-Security-Policy")
    assert resp.getheader("Cache-Control") == "no-store"


def test_nothing_is_written_to_prof(live, prof_home):
    before = {p: p.stat().st_mtime_ns for p in prof_home.rglob("*")}
    for path in ("/api/summary", "/api/topics", "/api/topics/git", "/api/sessions",
                 "/api/sessions/2026-10-05_1430_ab12cd34", "/api/profile"):
        assert live(path)[0].status == 200
    assert {p: p.stat().st_mtime_ns for p in prof_home.rglob("*")} == before
