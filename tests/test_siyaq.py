"""siyaq: tokens, the index, ranking, hooks, session memory, stats and the CLI."""
from __future__ import annotations

import json
import subprocess
import sys
import textwrap
import time

import pytest
from conftest import PLUGINS, _git

SIYAQ_ROOT = PLUGINS / "siyaq"
if str(SIYAQ_ROOT) not in sys.path:
    sys.path.insert(0, str(SIYAQ_ROOT))

from siyaq import cli, hooks, rank, state, text  # noqa: E402
from siyaq import index as idx  # noqa: E402

DOCS = {
    "docs/deploy.md": """\
        # Deployment

        ## Rollback
        To roll back a release, run `scripts/rollback.sh` with the previous tag. The deploy workflow
        lives in `.github/workflows/deploy.yml`. Never roll back database migrations automatically;
        ask the DBA first.

        ## Environments
        Staging deploys on every merge to main; production deploys from tags only. Secrets live in
        the vault, never in the repository.
        """,
    "docs/orders.md": """\
        # Orders

        ## Discounts
        Discounts are computed in `src/Orders/DiscountService.cs`. A cart over 100 gets 10 percent.
        The legacy rules were in `src/Orders/OldPricing.cs`; the folder `src/Orders/` owns pricing.

        ```text
        src/example/NotReal.cs
        ```
        """,
    "docs/billing-ar.md": """\
        # الفواتير

        ## إصدار الفاتورة
        يتم إصدار الفواتير من خدمة الفوترة في `src/Billing/InvoiceService.cs` بعد تأكيد الدفع،
        ولا يجوز تعديل الفاتورة بعد إصدارها بل يتم إصدار إشعار دائن.
        """,
    ".siyaq/entries/coupons.md": """\
        ---
        title: Coupon codes
        keywords: coupon, voucher, promo code, كوبون, قسيمة
        paths: src/Orders/**
        ---
        Coupon codes are validated by CouponValidator and can never be combined with automatic discounts.
        """,
    "CLAUDE.md": "# Rollback\nThis file is always loaded, so siyaq must never index it again.\n" * 3,
    "src/Orders/DiscountService.cs": "class DiscountService {}\n",
    "src/Billing/InvoiceService.cs": "class InvoiceService {}\n",
    "scripts/rollback.sh": "echo rollback\n",
    ".github/workflows/deploy.yml": "on: push\n",
}


@pytest.fixture
def repo(tmp_path, monkeypatch):
    monkeypatch.setenv("SIYAQ_HOME", str(tmp_path / "siyaq-home"))
    monkeypatch.delenv("SIYAQ", raising=False)
    root = tmp_path / "shop"
    for rel, content in DOCS.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(content), encoding="utf-8")
    _git(root, "init", "-q", "-b", "main")
    _git(root, "add", "-A")
    return root.resolve()


def entries_by_title(index):
    return {e["title"]: e for e in index["entries"]}


def prompt_event(repo, prompt, session="s1"):
    return {"prompt": prompt, "session_id": session, "cwd": str(repo)}


def tool_event(repo, rel, tool="Read", session="s1"):
    return {"tool_name": tool, "tool_input": {"file_path": str(repo / rel)}, "session_id": session,
            "cwd": str(repo)}


def context_of(output):
    return json.loads(output)["hookSpecificOutput"]["additionalContext"]


# ---------------------------------------------------------------- text


def test_arabic_normalization_and_stemming():
    assert text.normalize("أَحْمَد إسلام آمال الفاتورة على") == "احمد اسلام امال الفاتوره علي"
    assert text.tokens("الفاتورة") == text.tokens("فاتورة") == text.tokens("والفاتورة")
    assert text.tokens("الكوبون") == text.tokens("كوبون")


def test_english_stemming_and_code_words():
    assert len({text.tokens(w)[0] for w in ("validation", "validating", "validated", "validate")}) == 1
    assert text.tokens("OrderService") == text.tokens("order_service") == text.tokens("order service")
    assert text.tokens("café") == text.tokens("cafe")


def test_stop_words_and_generic_words_are_ignored():
    assert text.tokens("please fix the bug in this file") == ["fix", "bug"]
    assert text.tokens("كيف ممكن هذا") == []


# ---------------------------------------------------------------- index


def test_index_builds_entries_from_docs_and_manual(repo):
    index = idx.build(repo)
    titles = entries_by_title(index)
    assert set(titles) == {"Deployment > Rollback", "Deployment > Environments", "Orders > Discounts",
                           "الفواتير > إصدار الفاتورة", "Coupon codes"}
    rollback = titles["Deployment > Rollback"]
    assert (rollback["source"], rollback["start"]) == ("docs/deploy.md", 4)
    assert "CLAUDE.md" not in index["sources"]


def test_references_triggers_and_dead_refs(repo):
    titles = entries_by_title(idx.build(repo))
    rollback = titles["Deployment > Rollback"]
    assert rollback["paths"] == ["scripts/rollback.sh", ".github/workflows/deploy.yml"]
    discounts = titles["Orders > Discounts"]
    assert "src/Orders/DiscountService.cs" in discounts["paths"] and "src/Orders/**" in discounts["paths"]
    assert discounts["dead_refs"] == ["src/Orders/OldPricing.cs"]  # the fenced example is ignored
    coupons = titles["Coupon codes"]
    assert coupons["kind"] == "manual" and "كوبون" in coupons["keywords"]
    assert coupons["paths"] == ["src/Orders/**"]


def test_relative_links_resolve_from_the_doc(repo):
    (repo / "docs" / "guide.md").write_text("# Guide\n\n## Links\nThe overview is in ../README.md and the "
                                           "deploy notes in deploy.md, both worth reading first.\n")
    (repo / "README.md").write_text("# Shop\n")
    guide = entries_by_title(idx.build(repo))["Guide > Links"]
    assert guide["dead_refs"] == [] and "README.md" in guide["refs"] and "docs/deploy.md" in guide["refs"]


def test_index_cache_rebuilds_when_a_source_changes(repo):
    first = idx.load(repo)
    assert idx.load(repo)["fingerprint"] == first["fingerprint"]
    time.sleep(0.01)
    doc = repo / "docs" / "deploy.md"
    doc.write_text(doc.read_text() + "\n## Hotfixes\nHotfix branches start from the latest production tag "
                   "and merge back into main after release.\n")
    assert "Deployment > Hotfixes" in entries_by_title(idx.load(repo))


def test_config_exclude(repo):
    (repo / ".siyaq.json").write_text(json.dumps({"exclude": ["docs/orders.md"]}))
    assert "Orders > Discounts" not in entries_by_title(idx.load(repo))


# ---------------------------------------------------------------- ranking


def picked_titles(repo, prompt, shown=None, **cfg):
    index = idx.load(repo)
    picked = rank.select_for_prompt(index, prompt, rank.settings(cfg), shown or {})
    return [p["entry"]["title"] for p in picked]


def test_english_question_finds_the_right_section(repo):
    assert picked_titles(repo, "how do we roll back a release?")[0] == "Deployment > Rollback"


def test_arabic_question_finds_arabic_docs(repo):
    assert picked_titles(repo, "هل يمكن تعديل الفاتورة بعد إصدارها؟") == ["الفواتير > إصدار الفاتورة"]


def test_arabic_keyword_reaches_an_english_entry(repo):
    assert picked_titles(repo, "عندي مشكلة في الكوبون") == ["Coupon codes"]


def test_generic_or_single_body_word_prompts_match_nothing(repo):
    assert picked_titles(repo, "please fix the bug") == []
    assert picked_titles(repo, "where is the vault?") == []  # one body word is not enough


def test_path_noise_words_do_not_match_unrelated_docs(repo):
    # found in a live session: "src" + "Service" pulled the Arabic billing section into this prompt
    picked = picked_titles(repo, "Read the file src/Orders/DiscountService.cs and summarize it")
    assert "الفواتير > إصدار الفاتورة" not in picked and picked[0] == "Orders > Discounts"


def test_top_k_and_budget(repo):
    assert len(picked_titles(repo, "rollback deployment environments staging discounts", top_k=1)) == 1
    index = idx.load(repo)
    picked = rank.select_for_prompt(index, "how do we roll back a release?",
                                    rank.settings({"budget_tokens": 40}), {})
    assert all(len(p["text"]) <= 160 for p in picked)


def test_strong_small_match_is_full_and_large_is_summary(repo):
    index = idx.load(repo)
    picked = rank.select_for_prompt(index, "rollback release", rank.settings({}), {})
    assert picked[0]["level"] == "full" and "ask the DBA first" in picked[0]["text"]
    small = rank.select_for_prompt(index, "rollback release", rank.settings({"full_max_chars": 50}), {})
    assert small[0]["level"] == "summary" and "(more: read docs/deploy.md lines 4-" in small[0]["text"]


# ---------------------------------------------------------------- hooks and session memory


def test_prompt_hook_injects_once_per_session(repo):
    out = hooks.on_prompt(prompt_event(repo, "how do we roll back a release?"))
    data = json.loads(out)["hookSpecificOutput"]
    assert data["hookEventName"] == "UserPromptSubmit"
    assert data["additionalContext"].startswith("siyaq: project knowledge matched to this prompt")
    assert "### Deployment > Rollback  (docs/deploy.md:4-" in data["additionalContext"]
    assert "(more: read docs/deploy.md" in data["additionalContext"]  # weak match: summary first
    assert hooks.on_prompt(prompt_event(repo, "how do we roll back a release?")) is None  # already sent
    upgraded = hooks.on_prompt(prompt_event(repo, "rollback the release again"))  # strong: full, once
    assert "ask the DBA first" in context_of(upgraded)
    assert hooks.on_prompt(prompt_event(repo, "rollback the release again")) is None
    assert hooks.on_prompt(prompt_event(repo, "how do we roll back?", session="other")) is not None


def test_compact_resets_session_memory(repo):
    hooks.on_prompt(prompt_event(repo, "how do we roll back a release?"))
    hooks.on_session_start({"session_id": "s1", "source": "compact", "cwd": str(repo)}, "helper")
    assert hooks.on_prompt(prompt_event(repo, "how do we roll back a release?")) is not None


def test_slash_command_arguments_are_matched(repo):
    assert "Rollback" in context_of(hooks.on_prompt(prompt_event(repo, "/itqan:ship rollback the release")))
    assert hooks.on_prompt(prompt_event(repo, "/itqan:insights")) is None


def test_file_hook_injects_docs_about_that_file(repo):
    out = hooks.on_tool(tool_event(repo, "src/Orders/DiscountService.cs", tool="Edit"))
    data = json.loads(out)["hookSpecificOutput"]
    assert data["hookEventName"] == "PreToolUse" and "permissionDecision" not in data
    assert "Coupon codes" in data["additionalContext"] and "Orders > Discounts" in data["additionalContext"]
    assert hooks.on_tool(tool_event(repo, "src/Billing/InvoiceService.cs")) is not None
    assert hooks.on_tool(tool_event(repo, "scripts/unrelated.sh")) is None
    assert hooks.on_tool({"tool_name": "Bash", "tool_input": {"command": "ls"}, "cwd": str(repo)}) is None


def test_reading_the_source_after_a_summary_counts_as_opened(repo):
    (repo / ".siyaq.json").write_text(json.dumps({"full_max_chars": 50}))
    hooks.on_prompt(prompt_event(repo, "how do we roll back a release?"))
    hooks.on_tool(tool_event(repo, "docs/deploy.md"))
    opened = [e for e in state.read_events(repo) if e["type"] == "opened"]
    assert [e["id"] for e in opened] == ["docs/deploy.md#deployment-rollback"]


def test_misses_are_logged_with_unknown_terms_only(repo):
    hooks.on_prompt(prompt_event(repo, "how does the kafka consumer retry?"))
    misses = [e for e in state.read_events(repo) if e["type"] == "miss"]
    assert misses and "kafka" in misses[0]["terms"]


def test_siyaq_can_be_turned_off(repo, monkeypatch):
    (repo / ".siyaq.json").write_text('{"mode": "off"}')
    assert hooks.on_prompt(prompt_event(repo, "how do we roll back a release?")) is None
    (repo / ".siyaq.json").unlink()
    monkeypatch.setenv("SIYAQ", "off")
    assert hooks.on_prompt(prompt_event(repo, "how do we roll back a release?")) is None


def test_session_start_note(repo, tmp_path):
    note = hooks.on_session_start({"session_id": "s1", "source": "startup", "cwd": str(repo)}, "python3 x")
    assert "5 knowledge entries from 4 sources (1 hand-written)" in note and "siyaq helper: python3 x" in note
    empty = tmp_path / "empty"
    empty.mkdir()
    _git(empty, "init", "-q")
    assert "No knowledge entries yet" in hooks.on_session_start({"cwd": str(empty)}, "h")


# ---------------------------------------------------------------- CLI and stats


def test_cli_match_entries_index(repo, monkeypatch):
    monkeypatch.chdir(repo)
    out = cli.cmd_match(repo, "how do we roll back a release?")
    assert "match      Deployment > Rollback" in out and "would inject" in out
    assert "5 of 5 entries" in cli.cmd_entries(repo)
    assert "Coupon codes" in cli.cmd_entries(repo, "coupon")
    report = cli.cmd_index(repo)
    assert "5 entries (1 hand-written) from 4 sources" in report and "src/Orders/OldPricing.cs" in report


def test_stats_report(repo):
    (repo / ".siyaq.json").write_text(json.dumps({"full_max_chars": 50}))
    for session in ("a", "b"):
        hooks.on_prompt(prompt_event(repo, "how do we roll back a release?", session))
        hooks.on_prompt(prompt_event(repo, "how does the kafka consumer retry?", session))
    hooks.on_tool(tool_event(repo, "docs/deploy.md", session="b"))
    report = cli.cmd_stats(repo)
    assert "injections: 2 (2 summary, 0 full; 2 from prompts, 0 from files)" in report
    assert "prompts with no match: 2" in report
    assert "Deployment > Rollback (shown 2, opened 1)" in report
    assert "never shown: 4 of 5" in report
    assert "recurring topics with no knowledge:" in report and "kafka 2" in report
    assert "dead references: Orders > Discounts -> src/Orders/OldPricing.cs" in report


def test_hook_entry_point_never_fails(tmp_path):
    res = subprocess.run([sys.executable, str(SIYAQ_ROOT / "bin" / "siyaq"), "hook", "prompt"], input="{bad",
                         capture_output=True, text=True, cwd=tmp_path)
    assert res.returncode == 0 and res.stdout == ""


# ---------------------------------------------------------------- relevance (#38)


def test_only_a_sections_own_heading_counts(repo):
    (repo / "docs" / "hafiz.md").write_text(
        "# Hafiz\n\nHafiz keeps the memory of a project between sessions, with nothing sent anywhere.\n\n"
        "## Storage\nMemories are JSON lines in the data folder, owner-only, capped at three thousand.\n\n"
        "## Search\nSearch ranks memories by words, branch and date, in Arabic and in English.\n")
    picked = picked_titles(repo, "what does hafiz remember between sessions?")
    assert "Hafiz" in picked and "Hafiz > Storage" not in picked and "Hafiz > Search" not in picked


def test_a_short_prompt_needs_more_than_one_hit(repo):
    (repo / "docs" / "amin.md").write_text(
        "# Amin\n\n## Merges\nAmin prepares the release notes and the version but never merges a pull "
        "request by itself; a person merges after review.\n")
    assert picked_titles(repo, "merged") == []
    assert picked_titles(repo, "عندي مشكلة في الكوبون") == ["Coupon codes"]  # a written keyword still counts


@pytest.mark.parametrize("prompt", ["ok thanks", "yes, rollback it", "great, merged", "تمام شكرا",
                                    "lgtm, go ahead"])
def test_acknowledgements_inject_nothing(repo, prompt):
    assert hooks.on_prompt(prompt_event(repo, prompt)) is None


def test_back_links_are_not_triggers(repo):
    (repo / "README.md").write_text("# Shop\n")
    (repo / "docs" / "guide.md").write_text("# Guide\n\n## Links\nPart of [Shop](../README.md). The deploy "
                                           "notes are in deploy.md, worth reading before a release.\n")
    guide = entries_by_title(idx.build(repo))["Guide > Links"]
    assert "README.md" in guide["refs"] and "README.md" not in guide["paths"]
    assert "docs/deploy.md" in guide["paths"]


def test_top_results_are_picked_before_dropping_ones_already_shown(repo):
    prompt = "roll back the release from production staging"
    assert picked_titles(repo, prompt, top_k=2) == ["Deployment > Rollback", "Deployment > Environments"]
    shown = {"docs/deploy.md#deployment-rollback": "full"}
    assert picked_titles(repo, "roll back the release from production staging", shown=shown, top_k=1) == []


# ---------------------------------------------------------------- parallel hooks (#79)


def test_parallel_reads_inject_a_block_once(repo, monkeypatch):
    import threading

    barrier = threading.Barrier(2, timeout=0.5)
    real_load = state.load_session

    def slow_load(session):
        data = real_load(session)
        try:
            barrier.wait()  # both hooks have read the session before either writes it
        except threading.BrokenBarrierError:
            pass
        return data

    idx.load(repo)  # built once, so only the session state is shared
    monkeypatch.setattr(state, "load_session", slow_load)
    outputs = []
    threads = [threading.Thread(target=lambda: outputs.append(
        hooks.on_tool(tool_event(repo, "src/Orders/DiscountService.cs", tool="Edit")))) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sum(1 for out in outputs if out) == 1
    shown = [e for e in state.read_events(repo) if e["type"] == "shown" and e["id"].endswith("coupons.md")]
    assert len(shown) == 1


def test_parallel_index_builds_do_not_crash(repo):
    import threading

    errors = []

    def build():
        try:
            idx.load(repo)
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=build) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []


def test_session_state_is_written_atomically(repo):
    state.save_session("s1", {"shown": {"a": "full"}, "opened": []})
    folder = state.data_home() / "sessions"
    assert [p.name for p in folder.iterdir()] == ["s1.json"]


# ---------------------------------------------------------------- developer words and events (#80)


def test_developer_words_are_kept():
    assert text.tokens("run the tests locally") == text.tokens("run test local")
    assert "test" in text.tokens("run the tests locally")
    for word in ("index", "fix", "docs", "spec", "readme"):
        assert text.tokens(word), word


def test_events_file_is_private_and_rotated(repo, monkeypatch):
    import stat as stat_module

    monkeypatch.setattr(state, "EVENTS_LIMIT", 300)
    for n in range(20):
        state.log_event(repo, {"session": "s1", "type": "miss", "terms": [f"word{n}"]})
    folder = idx.project_dir(repo)
    assert stat_module.S_IMODE((folder / "events.jsonl").stat().st_mode) == 0o600
    assert (folder / "events.1.jsonl").exists() and (folder / "events.jsonl").stat().st_size <= 600
    terms = [e["terms"][0] for e in state.read_events(repo)]
    assert terms[-1] == "word19" and len(terms) < 20


# ---------------------------------------------------------------- Arabic and English together (#72)


def test_an_arabic_question_finds_an_english_section(repo):
    assert picked_titles(repo, "كيف نعمل تراجع للإصدار؟")[0] == "Deployment > Rollback"
    assert "Deployment > Environments" in picked_titles(repo, "متى يتم النشر على بيئة الإنتاج؟")


def test_an_english_question_finds_an_arabic_section(repo):
    expected = ["الفواتير > إصدار الفاتورة"]
    assert picked_titles(repo, "can an invoice be edited after it is issued?") == expected


def test_summaries_keep_tables_and_code(repo):
    table = "| plan | requests |\n|------|----------|\n| free | 60 |\n| pro | 600 |"
    code = "```sh\nadmin limits set --plan pro 900\n```"
    (repo / "docs" / "limits.md").write_text(
        "# Limits\n\n## Rate limits\nEach plan has its own request limits, enforced per API key at the "
        f"gateway and reset every minute for all endpoints.\n\n{table}\n\nRaise them with:\n\n{code}\n\n"
        + "More background on how limits evolved over the years. " * 20 + "\n")
    index = idx.load(repo)
    picked = rank.select_for_prompt(index, "rate limits per plan", rank.settings({"full_max_chars": 100}), {})
    assert picked[0]["level"] == "summary"
    assert table in picked[0]["text"] and code in picked[0]["text"]


# ---------------------------------------------------------------- what Claude Code already loads (#49)


def test_files_claude_code_loads_itself_are_never_indexed(repo):
    for rel in (".claude/rules/billing.md", "src/CLAUDE.local.md", "src/CLAUDE.md"):
        path = repo / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("---\npaths: src/**\n---\n# Billing rules\n\n" + "Always round invoice totals "
                        "to cents before saving them to the ledger table. " * 3 + "\n", encoding="utf-8")
    (repo / ".siyaq.json").write_text(json.dumps({"sources": ["**/*.md"], "exclude": ["docs/archive/**"]}))
    sources = {e.get("source") for e in idx.load(repo, idx.load_config(repo))["entries"]}
    assert not [s for s in sources if s and (".claude/" in s or "CLAUDE" in s)], sources


# ---------------------------------------------------------------- machine messages and slow indexes (#118)


@pytest.mark.parametrize("prompt", [
    "<task-notification> <task-id>b78sir6qh</task-id> <summary>Monitor event: rollback the release"
    "</summary></task-notification>",
    '<pasted_content id="57ff">\nYou are lane B. Rollback the release, then roll back again.\n'
    '</pasted_content id="57ff">',
    "Below is a conversation log from a Claude Code coding session. Create a summary to help the next "
    "session quickly understand the context. ## Prioritize including - how we rollback the release",
])
def test_machine_messages_get_no_context(repo, prompt):
    assert hooks.on_prompt(prompt_event(repo, prompt)) is None


def test_words_around_a_pasted_block_still_match(repo):
    out = hooks.on_prompt(prompt_event(repo, 'rollback the release, as in: <pasted_content id="3ba1">\n'
                                             'coupon voucher promo code\n</pasted_content id="3ba1"> ok?'))
    assert "Rollback" in context_of(out) and "Coupon" not in context_of(out)


@pytest.fixture
def slow_build(repo, monkeypatch):
    """slow_build.on(): building the index then takes far longer than a hook may wait. Background builds
    are recorded in slow_build.started instead of run."""
    import threading
    import types

    release = threading.Event()

    def build(*args, **kwargs):
        release.wait(5)
        raise RuntimeError("the test is over")

    started = []
    monkeypatch.setattr(idx, "INDEX_WAIT", 0.2)
    monkeypatch.setattr(idx, "SESSION_START_WAIT", 0.2)
    monkeypatch.setattr(idx, "build_in_background", started.append)
    yield types.SimpleNamespace(started=started, on=lambda: monkeypatch.setattr(idx, "build", build))
    release.set()


def test_prompt_hook_answers_from_the_saved_index_while_it_rebuilds(repo, slow_build):
    idx.load(repo)
    slow_build.on()
    (repo / "docs" / "deploy.md").write_text((repo / "docs" / "deploy.md").read_text() + "\nchanged\n")
    start = time.monotonic()
    out = hooks.on_prompt(prompt_event(repo, "how do we roll back a release?"))
    assert time.monotonic() - start < 1.5
    assert "Deployment > Rollback" in context_of(out)
    assert slow_build.started == [repo]


def test_first_prompt_on_a_slow_repo_never_waits_for_the_index(repo, slow_build):
    slow_build.on()
    start = time.monotonic()
    assert hooks.on_prompt(prompt_event(repo, "how do we roll back a release?")) is None
    assert time.monotonic() - start < 1.5
    assert slow_build.started == [repo]
    assert hooks.on_tool(tool_event(repo, "src/Orders/DiscountService.cs", tool="Edit")) is None
    note = hooks.on_session_start({"session_id": "s1", "source": "startup", "cwd": str(repo)}, "helper")
    assert "being built in the background" in note


def test_background_build_writes_the_index(repo):
    idx.build_in_background(repo)
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline and not (idx.project_dir(repo) / "index.json").exists():
        time.sleep(0.1)
    assert idx.saved(repo)["n"] == 5
    while time.monotonic() < deadline and (idx.project_dir(repo) / "build.lock").exists():
        time.sleep(0.1)
    assert not (idx.project_dir(repo) / "build.lock").exists()


def test_one_background_build_per_project(repo, monkeypatch):
    lock = idx.project_dir(repo) / "build.lock"
    lock.mkdir(parents=True)
    spawned = []
    with monkeypatch.context() as m:
        m.setattr(idx.subprocess, "Popen", lambda *a, **k: spawned.append(a))
        idx.build_in_background(repo)
    assert spawned == []
    assert idx.refresh(repo) is False  # another build holds the lock
    assert not (idx.project_dir(repo) / "index.json").exists()
    lock.rmdir()
    assert idx.refresh(repo) is True and idx.saved(repo)["n"] == 5 and not lock.exists()
