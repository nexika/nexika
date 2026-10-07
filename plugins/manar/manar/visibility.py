"""Measure AI visibility: ask real AI search engines real questions and record mentions and citations.

Each engine is asked through its own API with web search turned on, so the answer comes with
the sources it used. A prompt is asked several times; results are rates, not anecdotes, and are
stored in .manar/visibility.jsonl with the git ref, so before/after can be compared.
Keys come only from environment variables and are never stored.
"""
from __future__ import annotations

import datetime
import json
import math
import os
import re
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

ENGINES = {
    "gemini": ("GEMINI_API_KEY", "MANAR_GEMINI_MODEL", "gemini-2.5-flash"),
    "perplexity": ("PERPLEXITY_API_KEY", "MANAR_PERPLEXITY_MODEL", "sonar"),
    "openai": ("OPENAI_API_KEY", "MANAR_OPENAI_MODEL", "gpt-5-mini"),
    "anthropic": ("ANTHROPIC_API_KEY", "MANAR_ANTHROPIC_MODEL", "claude-haiku-4-5-20251001"),
}
DEFAULT_MAX_CALLS = 30


@dataclass
class Answer:
    text: str
    citations: list[str] = field(default_factory=list)   # URLs (and source titles when engines give them)


def _post(url: str, headers: dict, body: dict, timeout: int = 90) -> dict:
    request = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                     headers={"Content-Type": "application/json", **headers})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:300]
        raise RuntimeError(f"HTTP {exc.code}: {detail}") from None
    except (urllib.error.URLError, TimeoutError) as exc:
        raise RuntimeError(str(getattr(exc, "reason", exc))) from None


def ask_gemini(prompt, key, model, post=_post) -> Answer:
    data = post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                {"x-goog-api-key": key},
                {"contents": [{"parts": [{"text": prompt}]}], "tools": [{"google_search": {}}]})
    cand = (data.get("candidates") or [{}])[0]
    text = "".join(p.get("text", "") for p in (cand.get("content") or {}).get("parts", []))
    cites = []
    for chunk in (cand.get("groundingMetadata") or {}).get("groundingChunks", []):
        web = chunk.get("web") or {}
        cites += [v for v in (web.get("uri"), web.get("title")) if v]
    return Answer(text, cites)


def ask_perplexity(prompt, key, model, post=_post) -> Answer:
    data = post("https://api.perplexity.ai/chat/completions", {"Authorization": f"Bearer {key}"},
                {"model": model, "messages": [{"role": "user", "content": prompt}]})
    text = ((data.get("choices") or [{}])[0].get("message") or {}).get("content", "")
    cites = list(data.get("citations") or []) + [r.get("url") for r in data.get("search_results") or []
                                                  if r.get("url")]
    return Answer(text, cites)


def ask_openai(prompt, key, model, post=_post) -> Answer:
    data = post("https://api.openai.com/v1/responses", {"Authorization": f"Bearer {key}"},
                {"model": model, "tools": [{"type": "web_search"}], "input": prompt})
    text, cites = [], []
    for item in data.get("output") or []:
        for part in item.get("content") or []:
            text.append(part.get("text", ""))
            cites += [a.get("url") for a in part.get("annotations") or [] if a.get("url")]
    return Answer("".join(text), cites)


def ask_anthropic(prompt, key, model, post=_post) -> Answer:
    data = post("https://api.anthropic.com/v1/messages",
                {"x-api-key": key, "anthropic-version": "2023-06-01"},
                {"model": model, "max_tokens": 1024, "messages": [{"role": "user", "content": prompt}],
                 "tools": [{"type": "web_search_20250305", "name": "web_search", "max_uses": 3}]})
    text, cites = [], []
    for block in data.get("content") or []:
        if block.get("type") == "text":
            text.append(block.get("text", ""))
            cites += [c.get("url") for c in block.get("citations") or [] if c.get("url")]
        elif block.get("type") == "web_search_tool_result" and isinstance(block.get("content"), list):
            cites += [r.get("url") for r in block["content"] if r.get("url")]
    return Answer("".join(text), cites)


ASK = {"gemini": ask_gemini, "perplexity": ask_perplexity, "openai": ask_openai, "anthropic": ask_anthropic}


# ---------------------------------------------------------------- panel and runs


def available(env=None) -> dict[str, tuple[str, str]]:
    """engine -> (key, model) for every engine whose key is set."""
    env = os.environ if env is None else env
    return {name: (env[key_var], env.get(model_var) or default)
            for name, (key_var, model_var, default) in ENGINES.items() if env.get(key_var)}


def panel_template(brand: str, domains: list[str]) -> dict:
    return {
        "brand": brand, "aliases": [], "domains": domains, "samples": 3,
        "prompts": [
            {"text": "What are the best plugins to make Claude Code faster and cheaper?", "lang": "en"},
            {"text": "Which tools help a junior developer learn a new codebase with Claude?", "lang": "en"},
            {"text": "ما هي أفضل الإضافات لـ Claude Code؟", "lang": "ar"},
        ],
    }


def mentions(text: str, names: list[str]) -> bool:
    return any(re.search(rf"(?<![\w-]){re.escape(n)}(?![\w-])", text, re.I) for n in names if n)


def _host_path(value: str) -> tuple[str, str]:
    value = value.strip().lower()
    parts = urllib.parse.urlsplit(value if "://" in value else "https://" + value)
    return (parts.hostname or "").removeprefix("www."), parts.path.rstrip("/")


def is_cited(citations: list[str], domains: list[str]) -> int | None:
    """1-based position of the first citation on one of the brand's domains, else None.

    Hosts match exactly or as a subdomain (docs.nexika.dev for nexika.dev, never notnexika.dev);
    a domain with a path (github.com/nexika/nexika) also needs that path prefix.
    """
    wanted = [_host_path(d) for d in domains if d.strip()]
    for i, cite in enumerate(citations, 1):
        host, path = _host_path(cite)
        for w_host, w_path in wanted:
            if (host == w_host or host.endswith("." + w_host)) and (
                    not w_path or path == w_path or path.startswith(w_path + "/")):
                return i
    return None


def git_ref(root: Path) -> str:
    res = subprocess.run(["git", "describe", "--tags", "--always", "--dirty"], cwd=root,
                         capture_output=True, text=True)
    return res.stdout.strip() if res.returncode == 0 else ""


def run(panel: dict, engines: dict[str, tuple[str, str]], ask=None, ref: str = "") -> list[dict]:
    ask = ask or ASK
    run_id = datetime.datetime.now().isoformat(timespec="seconds")
    names = [panel["brand"], *panel.get("aliases", [])]
    records = []
    for prompt in panel["prompts"]:
        for engine, (key, model) in engines.items():
            for sample in range(1, int(panel.get("samples", 3)) + 1):
                rec = {"run": run_id, "ref": ref, "engine": engine, "model": model, "prompt": prompt["text"],
                       "lang": prompt.get("lang", ""), "sample": sample}
                try:
                    answer = ask[engine](prompt["text"], key, model)
                    position = is_cited(answer.citations, panel.get("domains", []))
                    rec.update(mentioned=mentions(answer.text, names), cited=position is not None,
                               position=position, citations=answer.citations[:15], error="")
                except Exception as exc:  # one engine failing must not stop the run
                    rec.update(mentioned=False, cited=False, position=None, citations=[],
                               error=str(exc)[:300])
                records.append(rec)
    return records


def _rates(rows: list[dict]) -> tuple[float, float]:
    n = len(rows) or 1
    return sum(r["mentioned"] for r in rows) / n, sum(r["cited"] for r in rows) / n


def wilson(k: float, n: float, z: float = 1.96) -> tuple[float, float]:
    """95% Wilson score interval for k successes out of n."""
    if n <= 0:
        return 0.0, 1.0
    p = k / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    margin = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return max(0.0, centre - margin), min(1.0, centre + margin)


def _range(rows: list[dict], key: str) -> tuple[float, float]:
    """Samples of one prompt are strongly correlated, so the prompt is the unit: n = prompts and k = the
    sum of per-prompt rates. Wider than counting every answer, and honest."""
    by_prompt: dict[str, list[bool]] = {}
    for r in rows:
        by_prompt.setdefault(r["prompt"], []).append(bool(r[key]))
    return wilson(sum(sum(v) / len(v) for v in by_prompt.values()), len(by_prompt))


def comparable(before: list[dict], after: list[dict], engine: str) -> str:
    """Why two runs can't be compared for one engine ("" when they can)."""
    old = [r for r in before if r["engine"] == engine]
    new = [r for r in after if r["engine"] == engine]
    if {r["prompt"] for r in old} != {r["prompt"] for r in new}:
        return "the prompts differ"
    old_models, new_models = {str(r.get("model")) for r in old}, {str(r.get("model")) for r in new}
    if old_models != new_models:
        return f"the model changed ({', '.join(sorted(old_models))} -> {', '.join(sorted(new_models))})"
    return ""


def _change(before: list[dict], after: list[dict], key: str) -> str:
    """Real only when the 95% ranges don't overlap (conservative)."""
    lo_b, hi_b = _range(before, key)
    lo_a, hi_a = _range(after, key)
    return "real change" if lo_a > hi_b or hi_a < lo_b else "within noise"


def report(records: list[dict], previous: list[dict] | None = None, domains: list[str] | None = None) -> str:
    ok = [r for r in records if not r["error"]]
    errors = [r for r in records if r["error"]]
    lines = [f"AI visibility (Measured: {len(ok)} answers, {len(errors)} failed calls)"]
    prev = [r for r in previous or [] if not r["error"]]
    for engine in sorted({r["engine"] for r in records}):
        rows = [r for r in ok if r["engine"] == engine]
        if not rows:
            first_error = next(r["error"] for r in errors if r["engine"] == engine)
            lines.append(f"  {engine:<11} all calls failed: {first_error}")
            continue
        m, c = _rates(rows)
        (m_lo, m_hi), (c_lo, c_hi) = _range(rows, "mentioned"), _range(rows, "cited")
        prompts = len({r["prompt"] for r in rows})
        line = (f"  {engine:<11} mentioned in {m:.0%} of answers, cited (linked) in {c:.0%}"
                f"  [{len(rows)} answers, {prompts} prompts; 95% range: mentioned {m_lo:.0%}-{m_hi:.0%},"
                f" cited {c_lo:.0%}-{c_hi:.0%}]")
        before = [r for r in prev if r["engine"] == engine]
        if before:
            why = comparable(before, rows, engine)
            if why:
                line += f"  (before: not comparable, {why})"
            else:
                pm, pc = _rates(before)
                line += (f"  (before: {pm:.0%} / {pc:.0%}, ref {before[0].get('ref') or '?'}; "
                         f"mentioned: {_change(before, rows, 'mentioned')}, "
                         f"cited: {_change(before, rows, 'cited')})")
        lines.append(line)
    lines.append("by prompt (cited, with the 95% range over its samples):")
    for prompt in dict.fromkeys(r["prompt"] for r in ok):
        rows = [r for r in ok if r["prompt"] == prompt]
        m, c = _rates(rows)
        lo, hi = wilson(sum(r["cited"] for r in rows), len(rows))
        lines.append(f"  {m:4.0%} mentioned, {c:4.0%} cited ({lo:.0%}-{hi:.0%})  - {prompt}")
    own = [d.lower() for d in domains or []]
    hosts: Counter = Counter()
    for r in ok:
        for cite in r["citations"]:
            host = urllib.parse.urlsplit(cite).netloc.lower()
            if host and not any(o in cite.lower() for o in own) and "vertexaisearch" not in host:
                hosts[host] += 1
    if hosts:
        lines.append("most cited other sources (who answers instead of you): "
                     + ", ".join(f"{h} {n}" for h, n in hosts.most_common(8)))
    return "\n".join(lines)


def save(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")


def load_runs(path: Path) -> list[list[dict]]:
    """All stored runs, oldest first."""
    try:
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    except (OSError, ValueError):
        return []
    runs: dict[str, list[dict]] = {}
    for row in rows:
        runs.setdefault(row["run"], []).append(row)
    return [runs[k] for k in sorted(runs)]
