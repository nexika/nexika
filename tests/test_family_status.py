"""Status files for amin, manar, barq and prof, and mizan showing them (#67)."""
from __future__ import annotations

import datetime
import json
import sys

import pytest
from conftest import PLUGINS
from test_amin import init_repo, plugin_json

for name in ("amin", "manar", "mizan"):
    if str(PLUGINS / name) not in sys.path:
        sys.path.insert(0, str(PLUGINS / name))

from amin import cli as amin_cli  # noqa: E402
from manar import cli as manar_cli  # noqa: E402
from mizan import family, i18n, render, snapshot, status  # noqa: E402


@pytest.fixture
def env(tmp_path, monkeypatch):
    for key, folder in (("NEXIKA_STATUS_HOME", "status"), ("MIZAN_HOME", "mizan"), ("HOME", "home")):
        monkeypatch.setenv(key, str(tmp_path / folder))
    (tmp_path / "home").mkdir()
    monkeypatch.setenv("MIZAN_OFFLINE", "1")
    monkeypatch.setenv("MIZAN_LANG", "en")
    return tmp_path


def read(plugin):
    return json.loads((status.home() / f"{plugin}.json").read_text(encoding="utf-8"))


def test_amin_publishes_the_projects_ready_to_release(env, monkeypatch, capsys):
    repo = init_repo(env / "market", {
        "plugins/alpha/.claude-plugin/plugin.json": plugin_json("alpha", "0.1.0"),
        "plugins/beta/.claude-plugin/plugin.json": plugin_json("beta", "1.2.0"),
    })
    monkeypatch.chdir(repo)
    assert amin_cli.main(["plan"]) == 0
    assert read("amin")["repos"][str(repo)]["ready"] == []
    assert amin_cli.main(["fragment", "add", "alpha", "fixed", "Crash", "--id", "1"]) == 0
    found = read("amin")
    assert found["schema"] == "nexika.amin/1"
    assert found["repos"][str(repo)]["ready"] == [{"name": "alpha", "next": "0.1.0"}]
    assert family.amin_ready(str(repo)) == [{"name": "alpha", "next": "0.1.0"}]


def test_manar_publishes_the_last_audit_score(env, monkeypatch, capsys):
    site = env / "site"
    site.mkdir()
    (site / "index.html").write_text("<html><head><title>Home</title></head><body><h1>Hi</h1></body></html>")
    monkeypatch.setattr(manar_cli, "project_root", lambda: env / "proj")
    assert manar_cli.main(["audit", str(site), "--base-url", "https://nexika.dev"]) == 0
    entry = read("manar")["audits"][str(env / "proj")]
    assert entry["target"] == "https://nexika.dev" and 0 <= entry["score"] <= 100
    assert entry["path"].endswith(".json")
    assert family.manar_audit(str(env / "proj"))["score"] == entry["score"]


def test_barq_publishes_honest_savings_for_today(env, project, barq_run, monkeypatch):
    monkeypatch.setenv("NEXIKA_STATUS_HOME", str(env / "status"))
    barq_run("read:src/app.py")
    barq_run("read:src/app.py")  # the second read is answered as unchanged: a real saving
    found = read("barq")
    assert found["schema"] == "nexika.barq/1" and found["date"] == datetime.date.today().isoformat()
    assert found["calls"] == 2 and found["estimated"] is True
    assert found["saved_bytes"] == found["avoided_bytes"] - found["extra_bytes"]
    assert family.barq_savings()["calls"] == 2


def test_barq_savings_from_another_day_are_not_shown(env):
    status.publish("barq", {"date": "2000-01-01", "calls": 9, "saved_bytes": 10})
    assert family.barq_savings() == {}


def test_prof_publishes_the_reviews_due(env, store, capsys):
    old = (datetime.date.today() - datetime.timedelta(days=40)).isoformat()
    (store.TOPICS).mkdir(parents=True)
    (store.TOPICS / "sql.md").write_text(
        f"# SQL\n\n- [understood] joins — explained them ({old})\n- [missed] indexes — guessed ({old})\n")
    store.session_start({"session_id": "s1"})
    found = read("prof")
    assert found["schema"] == "nexika.prof/1"
    assert found["due"] == 1 and found["open"] == 1 and found["topics"] == 1
    assert family.prof_due() == {"due": 1, "open": 1, "topics": 1}


def snap(**over):
    base = {"git": {"branch": "main"}, "prs": {}, "ci": {}, "device": {}, "context": {}, "cost": {},
            "agents": [], "tasks": {}, "haris": {}}
    return {**base, **over}


def test_mizan_shows_the_family_in_the_band_and_the_pane():
    family_view = {"amin": [{"name": "alpha", "next": "0.2.0"}, {"name": "beta", "next": "1.3.0"}],
                   "manar": {"score": 82, "target": "https://nexika.dev", "date": "2026-10-01T10:00:00"},
                   "barq": {"calls": 4, "saved_bytes": 40960, "extra_bytes": 0, "avoided_bytes": 40960},
                   "prof": {"due": 3, "open": 1, "topics": 2}}
    view = snap(family=family_view)
    band = render.plain(render.band(view, "en"))
    assert "amin: 2 ready to release" in band and "prof: 3 to review" in band
    pane = render.sections_text(render.detail(view, "en"))
    assert "alpha 0.2.0, beta 1.3.0" in pane
    assert "82/100" in pane and "https://nexika.dev" in pane
    assert "~10,240 tokens" in pane and "estimated" in pane
    assert "3 concept(s) due for a retention check" in pane
    arabic = render.sections_text(render.detail(view, "ar"))
    assert "82/100" in arabic and "أمين" in render.plain(render.band(view, "ar"))


def test_mizan_says_when_barq_cost_more_than_it_saved():
    barq = {"calls": 2, "saved_bytes": -2048, "extra_bytes": 4096, "avoided_bytes": 2048}
    view = snap(family={"barq": barq})
    pane = render.sections_text(render.detail(view, "en"))
    assert "sent 2.0 KB more than the built-in tools" in pane


def test_mizan_snapshot_reads_the_family(env, monkeypatch):
    status.publish("prof", {"due": 2, "open": 0, "topics": 1})
    found = snapshot.build({"session": "s1", "cwd": str(env)})
    assert found["family"]["prof"] == {"due": 2, "open": 0, "topics": 1}
    assert "prof: 2 to review" in render.plain(found["band"])


def test_family_words_have_both_languages():
    keys = [k for k in i18n.TEXT["en"] if k.startswith(("fam_", "d_fam_", "t_family"))]
    assert keys and all(k in i18n.TEXT["ar"] for k in keys)
