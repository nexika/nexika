"""bayan: prose detection, clean-up, style check, hooks and CLI, in English and Arabic."""
from __future__ import annotations

import io
import json
import sys

import pytest
from conftest import PLUGINS

BAYAN_ROOT = PLUGINS / "bayan"
if str(BAYAN_ROOT) not in sys.path:
    sys.path.insert(0, str(BAYAN_ROOT))

from bayan import check, clean, cli, config, hooks, prose  # noqa: E402


@pytest.fixture(autouse=True)
def bayan_home(tmp_path, monkeypatch):
    monkeypatch.setenv("BAYAN_HOME", str(tmp_path / "bayan-home"))
    monkeypatch.delenv("BAYAN_LEVEL", raising=False)
    monkeypatch.delenv("CLAUDE_ENV_FILE", raising=False)


def cleaned(text, **kw):
    return clean.clean(text, **kw)[0]


# ---------------------------------------------------------------- prose vs code


def test_code_links_and_comments_are_protected():
    text = ("Use `utilize()` and see https://x.dev/in-order-to\n```\nin order to — keep\n```\n"
            "<!-- in order to -->")
    assert cleaned(text) == text


def test_sentences_join_wrapped_lines_and_split_list_items():
    text = ("# Title\nThis sentence is wrapped\nacross two lines. Second one here.\n"
            "- a list item here\n| a | table |")
    assert prose.sentences(text) == ["This sentence is wrapped across two lines.", "Second one here.",
                                     "a list item here"]


# ---------------------------------------------------------------- clean


def test_hidden_characters_go_but_joiners_and_direction_marks_stay():
    text = "a​b c﻿ 👩‍💻 ‏مرحبا"
    out, changes = clean.clean(text)
    assert out == "ab c 👩‍💻 ‏مرحبا" and changes["hidden character"] == 3


def test_signature_lines_are_removed():
    text = ("Fix the parser\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>\n"
            "🤖 Generated with [Claude Code](https://claude.com/claude-code)\n")
    assert cleaned(text) == "Fix the parser\n"
    assert cleaned("Co-authored-by: Sam <sam@x.dev>\n") == "Co-authored-by: Sam <sam@x.dev>\n"   # people stay


def test_filler_sentences_and_wordy_phrases():
    text = ("Great question! It's worth noting that the cache is fast. We use it in order to save time.\n\n"
            "I hope this helps! Let me know if you have any other questions.\n")
    assert cleaned(text) == "The cache is fast. We use it to save time.\n"
    assert cleaned("In order to start, they utilized it.") == "To start, they used it."
    assert cleaned("This is certainly. fine") == "This is certainly. fine"    # only at sentence start


def test_dashes_become_commas_in_the_right_language():
    assert cleaned("Fast — and free.") == "Fast, and free."
    assert cleaned("سريعة — ومجانية.") == "سريعة، ومجانية."
    assert cleaned("pages 1–5 and 2020-2026") == "pages 1–5 and 2020-2026"   # ranges stay
    assert cleaned("Fast — and free.", dashes=False) == "Fast — and free."


def test_arabic_filler_and_phrases():
    text = "بالتأكيد! من الجدير بالذكر أن الإضافة سريعة. آمل أن يكون هذا مفيدًا.\n"
    assert cleaned(text) == "الإضافة سريعة.\n"
    assert cleaned("تجدر الإشارة إلى أن الأداة مجانية.") == "الأداة مجانية."


# ---------------------------------------------------------------- check


def advice(text, level="no-code"):
    return " | ".join(f.advice for f in check.check(text, level))


def test_flags_machine_words_and_patterns_in_both_languages():
    found = advice("We delve into a robust tool. It plays a crucial role. It is not just fast, but safe.")
    assert "'delve'" in found and "'robust'" in found and "say what it actually does" in found
    assert "not just X but Y" in found
    ar = advice("علاوة على ذلك، تلعب الأداة دورًا محوريًا.")
    assert "علاوة على ذلك" in ar and "قل ماذا يفعل بالضبط" in ar


def test_jargon_depends_on_the_reader():
    text = "The API returns JSON to the frontend."
    assert "'API' is not explained" in advice(text, "no-code")
    assert "not explained" not in advice(text, "developer")
    assert "'API'" not in advice(text, "junior")          # a basic term for a learner
    assert "'API'" not in advice("The API (the way programs talk to each other) works.")
    assert "'API'" not in advice("الـ API، أي طريقة تواصل البرامج، تعمل.")


def test_rhythm_lists_of_three_and_long_sentences():
    same = " ".join(["This line has exactly six words."] * 9)
    assert "same length" in advice(same)
    varied = "Short one. " + "This one is a good deal longer than the first one was, on purpose. " * 2 + "Done now."
    assert "same length" not in advice(varied)
    assert "three items" in advice("We test, ship, and learn. You read, write, and run. They plan, build, and fix.")
    assert "split it" in advice(" ".join(["word"] * 30) + ".")


def test_score_is_high_for_plain_text_and_low_for_machine_text():
    plain = "manar checks your site. It finds pages that Google can't read and tells you how to fix them."
    bad = ("Great question! In today's fast-paced world, our seamless and robust platform plays a crucial "
           "role. Let's delve into the vibrant tapestry of SEO. I hope this helps!")
    assert check.score(plain, check.check(plain)) == 100
    assert check.score(bad, check.check(bad)) < 50


# ---------------------------------------------------------------- hooks


def post(path, **tool_input):
    return hooks.post_write({"tool_name": "Edit" if "new_string" in tool_input else "Write", "cwd": str(path.parent),
                             "tool_input": {"file_path": str(path), **tool_input}})


def test_post_write_cleans_prose_files_and_reports_what_is_left(tmp_path):
    doc = tmp_path / "notes.md"
    doc.write_text("Great question! We delve into it in order to learn.\n")
    note = post(doc)["hookSpecificOutput"]["additionalContext"]
    assert doc.read_text() == "We delve into it to learn.\n"
    assert "bayan cleaned notes.md" in note and "'delve'" in note


def test_post_write_leaves_code_opt_out_and_disabled_files_alone(tmp_path):
    code = tmp_path / "app.py"
    code.write_text("# Great question! in order to\n")
    assert post(code) is None and code.read_text() == "# Great question! in order to\n"
    off = tmp_path / "guide.md"
    off.write_text("<!-- bayan: off -->\nGreat question!\n")
    assert post(off) is None
    config.save(auto_clean=False)
    doc = tmp_path / "x.md"
    doc.write_text("Great question! Fine.\n")
    post(doc)
    assert doc.read_text() == "Great question! Fine.\n"


def test_pre_bash_blocks_signed_commits_and_pull_requests():
    def decide(command):
        out = hooks.pre_bash({"tool_input": {"command": command}})
        return out and out["hookSpecificOutput"]["permissionDecision"]
    assert decide('git commit -m "Fix\n\nCo-Authored-By: Claude <noreply@anthropic.com>"') == "deny"
    assert decide('gh pr create --title x --body "🤖 Generated with [Claude Code](https://c)"') == "deny"
    assert decide('git commit -m "Fix​ parser"') == "deny"
    assert decide('git commit -m "Fix parser"') is None
    assert decide('echo "Co-Authored-By: Claude"') is None          # not a commit
    config.save(block_signatures=False)
    assert decide('git commit -m "x\n\nCo-Authored-By: Claude"') is None


def test_session_start_uses_the_saved_level_and_puts_bayan_on_path(tmp_path, monkeypatch):
    env = tmp_path / "env.sh"
    monkeypatch.setenv("CLAUDE_ENV_FILE", str(env))
    config.save(level="developer")
    note = hooks.session_start({})
    assert "Reader level: developer" in note and "Helper: bayan check FILE" in note
    hooks.session_start({})
    assert env.read_text().count("export PATH=") == 1          # written once, even on resume
    monkeypatch.setenv("BAYAN_LEVEL", "junior")
    assert "Reader level: junior" in hooks.session_start({})


# ---------------------------------------------------------------- CLI


def test_cli(tmp_path, capsys, monkeypatch):
    doc = tmp_path / "a.md"
    doc.write_text("Great question! We delve into it.\n")
    assert cli.main(["check", str(doc)]) == 0
    out = capsys.readouterr().out
    assert "plainness score:" in out and "not an AI detector" in out and "'delve'" in out
    assert cli.main(["check", str(doc), "--min-score", "99"]) == 1
    capsys.readouterr()
    assert cli.main(["check", str(doc), "--json", "--level", "developer"]) == 0
    assert json.loads(capsys.readouterr().out)["level"] == "developer"
    assert cli.main(["clean", str(doc), "--write"]) == 0
    assert doc.read_text() == "We delve into it.\n" and "cleaned 1 filler sentence" in capsys.readouterr().out
    assert cli.main(["level", "junior"]) == 0 and config.load()["level"] == "junior"
    assert cli.main(["level", "expert"]) == 1
    capsys.readouterr()
    monkeypatch.setattr("sys.stdin", io.StringIO('{"tool_input": {"command": "git commit -m x"}}'))
    assert cli.main(["hook", "pre-bash"]) == 0 and capsys.readouterr().out == ""


# ---------------------------------------------------------------- regressions from the itqan review


def test_code_blocks_keep_signatures_and_special_spaces():
    text = ("Docs:\n\n```\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>\nprintf('a b')\n```\n\n"
            "````md\n```\nin order to — x\n```\n````\n")
    assert cleaned(text) == text


def test_arabic_attached_pronouns_are_not_cut():
    assert cleaned("من الجدير بالذكر أنه يعمل.") == "من الجدير بالذكر أنه يعمل."
    assert cleaned("لا شك أنها فكرة جيدة.") == "لا شك أنها فكرة جيدة."


def test_links_html_front_matter_and_indented_code_are_protected():
    text = ("---\ndescription: in order to utilize\n---\nSee [g](docs/utilize-cache.md) and "
            '<img src="img/utilized.png">.\n\n    code — here; utilize()\n\n[ref]: docs/in-order-to.md\n')
    assert cleaned(text) == text


def test_dashes_in_tables_quotes_and_ranges_stay():
    text = "| x | — |\n|---|---|\n\n> — Oscar Wilde\n\npages 10 – 20, 2020—2026\n"
    assert cleaned(text) == text


def test_filler_needs_a_complete_sentence():
    for text in ("I hope this helps you decide between the plans.",
                 "Let me know if you have any questions about pricing, we reply in a day.",
                 "He said “Certainly!” and left."):
        assert cleaned(text) == text


def test_human_co_authors_stay_and_are_not_blocked():
    for line in ("Co-authored-by: Claude Monet <cm@example.com>", "Co-authored-by: Ana <ana@openai.com>"):
        assert cleaned(f"Fix\n\n{line}\n") == f"Fix\n\n{line}\n"
        assert hooks.pre_bash({"tool_input": {"command": f'git commit -m "Fix\n\n{line}"'}}) is None


def test_crlf_is_kept(tmp_path):
    doc = tmp_path / "a.md"
    doc.write_bytes(b"Fast \xe2\x80\x94 and free.\r\nSecond line.\r\n")
    post(doc)
    assert doc.read_bytes() == b"Fast, and free.\r\nSecond line.\r\n"


def test_only_the_edited_part_is_cleaned(tmp_path):
    doc = tmp_path / "story.md"
    doc.write_text("Certainly! Right away, sir — he said.\n\nNew part: we did it in order to learn.\n")
    note = post(doc, old_string="x", new_string="New part: we did it in order to learn.")
    assert doc.read_text() == "Certainly! Right away, sir — he said.\n\nNew part: we did it to learn.\n"
    assert "1 wordy phrase" in note["hookSpecificOutput"]["additionalContext"]


def test_symlinks_outside_project_fixtures_and_rst_are_not_rewritten(tmp_path):
    outside = tmp_path / "outside.md"
    outside.write_text("We did it in order to learn.\n")
    project = tmp_path / "project"
    (project / "tests" / "fixtures").mkdir(parents=True)
    link = project / "link.md"
    link.symlink_to(outside)
    assert hooks.post_write({"tool_name": "Write", "cwd": str(project),
                             "tool_input": {"file_path": str(link)}}) is None
    assert hooks.post_write({"tool_name": "Write", "cwd": str(project),
                             "tool_input": {"file_path": str(outside)}}) is None
    golden = project / "tests" / "fixtures" / "golden.md"
    golden.write_text("in order to — x\n")
    assert hooks.post_write({"tool_name": "Write", "cwd": str(project),
                             "tool_input": {"file_path": str(golden)}}) is None
    rst = project / "doc.rst"
    rst.write_text("Text.\n\n    in order to\n")
    post(rst)
    assert rst.read_text() == "Text.\n\n    in order to\n" and outside.read_text() == "We did it in order to learn.\n"


def test_guard_ignores_look_alikes_and_reads_message_files(tmp_path):
    def decide(command):
        out = hooks.pre_bash({"cwd": str(tmp_path), "tool_input": {"command": command}})
        return out and out["hookSpecificOutput"]["permissionDecision"]
    assert decide('git commit -m "docs: stop adding Generated with Claude Code footer"') is None
    assert decide('git log --grep commit | grep "Co-authored-by: claude"') is None
    assert decide('git commit -m "Résumé : corrigé"') is None          # French no-break space is fine
    (tmp_path / "msg.txt").write_text("Fix\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>\n")
    assert decide("git commit -F msg.txt") == "deny"
    assert decide("cd x && gh pr create --body-file msg.txt") == "deny"


def test_unclosed_comment_is_fast():
    import time
    text = "<!--" + "a in order to " * 8000
    start = time.monotonic()
    assert cleaned(text) == text and time.monotonic() - start < 1
