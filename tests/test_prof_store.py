"""Behaviour of the prof plugin's storage and hook helper."""
from __future__ import annotations

import datetime
import io
import json
import subprocess

import pytest

TODAY = datetime.date.today()
OLD = (TODAY - datetime.timedelta(days=30)).isoformat()


def write_report(store, name, lines, extra=""):
    store.REPORTS.mkdir(parents=True, exist_ok=True)
    path = store.REPORTS / name
    path.write_text(extra + "\n## Concept checklist\n" + "\n".join(lines) + "\n", encoding="utf-8")
    return path


def write_transcript(path, rows):
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    return path


def user(text):
    return {"type": "user", "message": {"role": "user", "content": text}}


def assistant(*blocks):
    return {"type": "assistant", "message": {"role": "assistant", "content": list(blocks)}}


def text(t):
    return {"type": "text", "text": t}


def slash(command, args=""):
    """How Claude Code records a slash command the user ran."""
    return user(f"<command-message>{command[1:]} is running…</command-message>\n"
                f"<command-name>{command}</command-name>\n<command-args>{args}</command-args>")


# ---------------------------------------------------------------- slugify


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("C# async/await", "c-sharp-async-await"), ("  Hello World ", "hello-world"), ("###", "general"),
     ("C++", "cpp"), ("C#", "c-sharp"), ("F# basics", "f-sharp-basics"), (".NET DI", "dotnet-di")],
)
def test_slugify(store, raw, expected):
    assert store.slugify(raw) == expected


# ---------------------------------------------------------------- merge-report


def test_merge_report_creates_topic_sorted_worst_first(store):
    report = write_report(store, "2026-10-04_1500_abcd1234.md", [
        "- [understood] csharp-async :: C# async/await :: Task.WhenAll :: wrote a correct example",
        "- [missed] csharp-async :: C# async/await :: await and threads :: said await blocks",
        "- [shaky] csharp-async :: C# async/await :: async void :: needed 2 hints",
    ])
    assert store.merge_report(report) == 3

    title, entries = store.load_topic("csharp-async")
    assert title == "C# async/await"
    assert entries["await and threads"] == ("missed", "await and threads", "said await blocks", "2026-10-04")

    statuses = [line.split("]")[0] for line in
                (store.TOPICS / "csharp-async.md").read_text().splitlines() if line.startswith("- [")]
    assert statuses == ["- [missed", "- [shaky", "- [understood"]


def test_merge_report_updates_existing_concept_case_insensitively(store):
    first = write_report(store, "2026-10-01_1000_aaaa0000.md",
                         ["- [missed] py :: Python :: List Comprehension :: wrong syntax"])
    second = write_report(store, "2026-10-05_1000_bbbb0000.md",
                          ["- [understood] py :: Python :: list comprehension :: correct answer"])
    store.merge_report(first)
    store.merge_report(second)

    _, entries = store.load_topic("py")
    assert len(entries) == 1
    assert entries["list comprehension"][0] == "understood"
    assert entries["list comprehension"][3] == "2026-10-05"


def test_merge_report_ignores_malformed_lines(store):
    report = write_report(store, "2026-10-05_1000_cccc0000.md", [
        "- [great] py :: Python :: unknown status :: x",
        "- [missed] py :: missing separators",
        "- [shaky] py :: Python :: decorators :: needed hints",
    ])
    assert store.merge_report(report) == 1


def test_merge_report_records_merged_file(store):
    report = write_report(store, "2026-10-05_1000_dddd0000.md", ["- [shaky] py :: Python :: loops :: x"])
    store.merge_report(report)
    assert report.name in store.MERGED.read_text()


def test_not_checked_never_overwrites_a_checked_status(store):
    # issue #61/#87: a later "explained but not tested" erased an "understood" with evidence
    first = write_report(store, "2026-10-01_1000_aaaa0000.md",
                         ["- [understood] py :: Python :: generators :: wrote a correct one"])
    later = write_report(store, "2026-10-05_1000_bbbb0000.md",
                         ["- [not-checked] py :: Python :: generators :: mentioned again"])
    store.merge_report(first)
    store.merge_report(later)
    assert store.load_topic("py")[1]["generators"][:3] == ("understood", "generators", "wrote a correct one")


def test_c_sharp_and_c_plus_plus_stay_separate_topics(store):
    report = write_report(store, "2026-10-05_1000_cccc0001.md", [
        "- [shaky] C# :: C# :: delegates :: hints",
        "- [missed] C++ :: C++ :: pointers :: wrong",
    ])
    store.merge_report(report)
    assert set(store.load_topic("c-sharp")[1]) == {"delegates"}
    assert set(store.load_topic("cpp")[1]) == {"pointers"}


def test_skill_triggers_need_a_learning_request():
    # plain working questions must not start a lesson
    from conftest import PLUGINS
    text = "\n".join(p.read_text(encoding="utf-8").split("---")[1]
                     for p in (PLUGINS / "prof" / "skills").glob("*/SKILL.md"))
    for plain in ("what is X and how does it work", "explain this code", "what does this file do",
                  '"bye"', '"done for today"', "explain this project"):
        assert plain not in text, plain
    assert '"teach me"' in text


# ---------------------------------------------------------------- summaries / topic command


def test_topic_summaries_open_and_stale_items(store):
    store.save_topic("py", "Python", {
        "loops": ("understood", "loops", "fine", OLD),
        "decorators": ("shaky", "decorators", "hints", TODAY.isoformat()),
        "classes": ("understood", "classes", "fine", TODAY.isoformat()),
    })
    [(slug, title, last, open_items, stale)] = store.topic_summaries()
    assert (slug, title, last) == ("py", "Python", TODAY.isoformat())
    assert [e[1] for e in open_items] == ["decorators"]
    assert [e[1] for e in stale] == ["loops"]


def test_print_topic_fuzzy_match(store, capsys):
    store.save_topic("csharp-async", "C# async", {"x": ("missed", "x", "e", OLD)})
    store.print_topic("C# async")
    assert "# C# async [csharp-async]" in capsys.readouterr().out


def test_print_topic_unknown_lists_known(store, capsys):
    store.save_topic("python-basics", "Python", {"x": ("missed", "x", "e", OLD)})
    store.print_topic("rust")
    assert "Known topics: python-basics" in capsys.readouterr().out


# ---------------------------------------------------------------- session-start


def test_session_start_is_one_line_when_nothing_is_due(store, capsys):
    # issue #61: every session got the full tutoring context, turning plain questions into lessons
    store.set_auto_report(False)
    store.PROFILE.parent.mkdir(parents=True, exist_ok=True)
    store.PROFILE.write_text("# Learner profile\n- Level: junior\n", encoding="utf-8")
    store.save_topic("py", "Python", {"loops": ("understood", "loops", "fine", TODAY.isoformat())})
    store.session_start({"session_id": "abcdef1234567"})
    out = capsys.readouterr().out.strip()
    assert len(out.splitlines()) == 1
    assert "short: abcdef12" in out and "nothing due" in out
    assert "Warm-up rule" not in out and "Level: junior" not in out


def test_session_start_lists_history_and_warmup_rule(store, capsys):
    report = write_report(
        store, "2026-10-04_1500_abcd1234.md",
        ["- [missed] py :: Python :: generators :: could not explain yield"],
        extra="## Weak areas & logic gaps\n- confuses yield with return\n"
              "## Review next time\n- generators first\n",
    )
    store.merge_report(report)
    store.PROFILE.write_text("# Learner profile\n- Level: junior\n", encoding="utf-8")

    store.session_start({"session_id": "s1"})
    out = capsys.readouterr().out
    assert "- Level: junior" in out
    assert "- confuses yield with return" in out
    assert "- generators first" in out
    assert "[missed] generators" in out
    assert "Warm-up rule (mandatory)" in out


def test_session_start_silent_inside_background_report(store, capsys, monkeypatch):
    monkeypatch.setenv("PROF_REPORTING", "1")
    store.session_start({"session_id": "s1"})
    assert capsys.readouterr().out == ""


# ---------------------------------------------------------------- transcript extraction


def test_extract_conversation_detects_tutoring_and_counts_turns(store, tmp_path):
    path = write_transcript(tmp_path / "t.jsonl", [
        slash("/prof:learn", "generators"),
        assistant({"type": "tool_use", "name": "Skill", "input": {"skill": "prof:warmup", "args": "py"}}),
        assistant(text("Q1: what does yield do?")),
        user("it returns a value"),
        user("<system-reminder>ignore me</system-reminder>"),
        {"type": "user", "isMeta": True, "message": {"content": "meta"}},
        {"type": "attachment", "foo": "bar"},
        "not json at all",
    ])
    convo, tutoring, turns = store.extract_conversation(path)
    assert tutoring is True
    assert turns == 2
    assert "[used skill prof:warmup py]" in convo
    assert "LEARNER: it returns a value" in convo
    assert "meta" not in convo


def test_extract_conversation_plain_session_is_not_tutoring(store, tmp_path):
    path = write_transcript(tmp_path / "t.jsonl", [user("fix the build"), assistant(text("done"))])
    _, tutoring, _ = store.extract_conversation(path)
    assert tutoring is False


# ---------------------------------------------------------------- session-end


@pytest.fixture
def popen_calls(store, monkeypatch):
    calls = []
    monkeypatch.setattr(store.subprocess, "Popen", lambda *a, **kw: calls.append((a, kw)))
    return calls


def tutoring_transcript(tmp_path):
    return write_transcript(tmp_path / "t.jsonl", [
        slash("/prof:learn", "loops"), assistant(text("Q1?")), user("a"), user("b"), user("bye"),
    ])


def test_session_end_spawns_background_report(store, tmp_path, popen_calls):
    store.set_auto_report(True)
    store.session_end({"session_id": "abcd1234zz", "transcript_path": str(tutoring_transcript(tmp_path))})
    assert len(popen_calls) == 1
    args, kwargs = popen_calls[0]
    assert args[0][-3:] == ["write-auto-report", "abcd1234zz", str(store.TMP / "abcd1234.txt")]
    assert kwargs["env"]["PROF_REPORTING"] == "1"
    assert kwargs["start_new_session"] is True
    assert "LEARNER: bye" in (store.TMP / "abcd1234.txt").read_text()


def test_session_end_skips_plain_session(store, tmp_path, popen_calls):
    path = write_transcript(tmp_path / "t.jsonl", [user("a"), user("b"), user("c"), user("d")])
    store.session_end({"session_id": "s1", "transcript_path": str(path), "cwd": str(tmp_path)})
    assert popen_calls == []


def test_session_end_skips_short_session(store, tmp_path, popen_calls):
    path = write_transcript(tmp_path / "t.jsonl", [slash("/prof:learn", "x"), user("bye")])
    store.session_end({"session_id": "s1", "transcript_path": str(path)})
    assert popen_calls == []


def test_session_end_skips_when_report_exists(store, tmp_path, popen_calls):
    write_report(store, "2026-10-05_1200_abcd1234.md", [])
    store.session_end({"session_id": "abcd1234zz", "transcript_path": str(tutoring_transcript(tmp_path))})
    assert popen_calls == []


def test_session_end_professor_style_counts_as_tutoring(store, tmp_path, popen_calls):
    store.set_auto_report(True)
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "settings.local.json").write_text('{"outputStyle": "Professor"}')
    rows = [user("what is a loop"), user("ok"), user("why"), user("bye")]
    path = write_transcript(tmp_path / "t.jsonl", rows)
    store.session_end({"session_id": "s1", "transcript_path": str(path), "cwd": str(tmp_path)})
    assert len(popen_calls) == 1


# issue #43: any message mentioning /prof: started a paid background report without asking


def test_mentioning_prof_in_a_message_is_not_tutoring(store, tmp_path, popen_calls):
    store.set_auto_report(True)
    rows = [user("how do I turn off /prof:report?"), user("ok"), user("and /prof:learn?"), user("bye")]
    path = write_transcript(tmp_path / "t.jsonl", rows)
    assert store.extract_conversation(path)[1] is False
    store.session_end({"session_id": "s1", "transcript_path": str(path), "cwd": str(tmp_path)})
    assert popen_calls == []


def test_no_background_report_until_the_learner_agrees(store, tmp_path, popen_calls, capsys):
    hook = {"session_id": "abcd1234zz", "transcript_path": str(tutoring_transcript(tmp_path))}
    assert store.auto_report_setting() is None
    store.session_end(hook)
    assert popen_calls == []
    assert "not enabled" in store.LOG.read_text()
    store.session_start({"session_id": "s2"})
    assert "auto-report on" in capsys.readouterr().out          # Claude is told to ask once
    assert store.main(["prof_store.py", "auto-report", "off"]) == 0
    store.session_end(hook)
    assert popen_calls == [] and store.auto_report_setting() is False
    store.session_start({"session_id": "s3"})
    assert "auto-report on" not in capsys.readouterr().out      # asked once, never again
    store.main(["prof_store.py", "auto-report", "on"])
    store.session_end(hook)
    assert len(popen_calls) == 1


# ---------------------------------------------------------------- write-auto-report


VALID_REPORT = "# Tutor session report\n## Concept checklist\n- [shaky] py :: Python :: loops :: hints\n"


def fake_claude(store, monkeypatch, stdout, returncode=0):
    seen = {}

    def run(cmd, stdin, **kw):
        seen["cmd"] = cmd
        seen["stdin"] = stdin.read()
        return subprocess.CompletedProcess(cmd, returncode, stdout=stdout, stderr="")

    monkeypatch.setattr(store.shutil, "which", lambda name: "/fake/claude")
    monkeypatch.setattr(store.subprocess, "run", run)
    return seen


def test_write_auto_report_saves_and_merges(store, monkeypatch):
    store.save_topic("py", "Python", {"loops": ("missed", "loops", "x", OLD)})
    store.TMP.mkdir(parents=True)
    convo = store.TMP / "abcd1234.txt"
    convo.write_text("LEARNER: hi")
    seen = fake_claude(store, monkeypatch, VALID_REPORT)

    assert store.write_auto_report("abcd1234zz", convo) == 0

    [report] = store.REPORTS.glob("*_abcd1234.md")
    assert "## Concept checklist" in report.read_text()
    assert store.load_topic("py")[1]["loops"][0] == "shaky"
    assert not convo.exists()
    assert seen["stdin"] == "LEARNER: hi"
    assert seen["cmd"][seen["cmd"].index("--tools") + 1] == ""
    assert "py (Python): loops" in seen["cmd"][2]  # known topics are offered for reuse


@pytest.mark.parametrize(("stdout", "rc"), [("no checklist here", 0), (VALID_REPORT, 1)])
def test_write_auto_report_rejects_bad_output(store, monkeypatch, stdout, rc):
    store.TMP.mkdir(parents=True)
    convo = store.TMP / "x.txt"
    convo.write_text("hi")
    fake_claude(store, monkeypatch, stdout, rc)
    assert store.write_auto_report("abcd1234", convo) == 1
    assert not store.REPORTS.exists() or not list(store.REPORTS.glob("*.md"))


def test_write_auto_report_without_claude(store, monkeypatch, tmp_path):
    monkeypatch.setattr(store.shutil, "which", lambda name: None)
    assert store.write_auto_report("abcd1234", tmp_path / "x.txt") == 1
    assert "not on PATH" in store.LOG.read_text()


# ---------------------------------------------------------------- CLI


def test_main_hook_never_fails(store, monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO("{not json"))
    monkeypatch.setattr(store, "session_end", lambda hook: 1 / 0)
    assert store.main(["prof_store.py", "session-end"]) == 0
    assert "ZeroDivisionError" in store.LOG.read_text()


def test_main_unknown_command_prints_usage(store, capsys):
    assert store.main(["prof_store.py", "nope"]) == 2
    assert "Commands:" in capsys.readouterr().out
