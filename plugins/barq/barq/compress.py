"""Shrink test/build output to what matters: the verdict, failures and errors.

Each parser recognises one tool's output and returns (verdict, detail lines), or None when
the output isn't from that tool. The generic fallback keeps error-looking lines plus the tail.
"""
from __future__ import annotations

import re

ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")
MAX_DETAIL = 120
GENERIC_TAIL = 15
MAX_LINE = 500  # a 16 KB assertion message is cut, not printed in full (#166)


def clean(output: str) -> str:
    return ANSI.sub("", output).replace("\r\n", "\n").replace("\r", "\n")


def _dedupe(lines: list[str]) -> list[str]:
    seen: set[str] = set()
    out = []
    for line in lines:
        key = line.strip()
        if key and key not in seen:
            seen.add(key)
            out.append(line)
    return out


# ---------------------------------------------------------------- python


def pytest(lines: list[str]):
    # "=== 1 failed, 2 passed in 0.05s ===", or with -q just "1 failed, 2 passed in 0.05s"
    summary = [ln for ln in lines if re.match(
        r"^(?:=+ .*\b(passed|failed|errors?|no tests ran|skipped|deselected)\b"
        r"|\d+ (?:passed|failed|errors?|skipped|deselected|xfailed|xpassed|warnings?)\b"
        r"|no tests ran\b).* in [\d.]+s", ln.strip())]
    if not summary:
        return None
    collect_errors = _collection_errors(lines)
    details = []
    for ln in lines:
        if ln.startswith(("FAILED ", "ERROR ")):
            # "ERROR tests/x.py - ../_pytest/python.py:508: in importtestmodule" names a pytest
            # frame: show the module's own error instead (#170)
            m = re.match(r"^ERROR (\S+) - .*/_pytest/", ln)
            if m:
                ln = f"ERROR {m.group(1)}" + (f" - {collect_errors[m.group(1)]}"
                                              if m.group(1) in collect_errors else "")
            details.append(ln)
    for ln in lines:
        if "/_pytest/" in ln:
            continue  # pytest's own frames say nothing about the failure
        if ln.startswith("E ") or re.match(r"^[\w/.\\-]+\.py:\d+: \w", ln):
            details.append(ln)
    return summary[-1].strip("= ").strip(), _dedupe(details)


def _collection_errors(lines: list[str]) -> dict[str, str]:
    """path -> the last 'E   SomeError: msg' line of its '___ ERROR collecting path ___' block."""
    found: dict[str, str] = {}
    current = None
    for ln in lines:
        header = re.match(r"^_+ ERROR collecting (\S+) _+$", ln.strip())
        if header:
            current = header.group(1)
        elif ln.startswith("_") or ln.startswith("="):
            current = None
        elif current:
            m = re.match(r"^E\s+([A-Za-z_][\w.]*(?:Error|Exception|Exit|Interrupt)\b.*)$", ln)
            if m:
                found[current] = m.group(1).strip()
    return found


# ---------------------------------------------------------------- .NET


_MSBUILD_DIAG = re.compile(r":\s(error|warning)\s[A-Z]{1,6}\d+\s*:")
_PROJ_SUFFIX = re.compile(r"\s+\[[^\]]+\.(?:cs|vb|fs)proj[^\]]*\]\s*$")


def _msbuild_diagnostics(lines: list[str]) -> tuple[list[str], list[str]]:
    errors, warnings = [], []
    for ln in lines:
        m = _MSBUILD_DIAG.search(ln)
        if m:
            entry = _PROJ_SUFFIX.sub("", ln.strip())
            (errors if m.group(1) == "error" else warnings).append(entry)
    return _dedupe(errors), _dedupe(warnings)


def dotnet_build(lines: list[str]):
    text = "\n".join(lines)
    if "Build succeeded" not in text and "Build FAILED" not in text and not _MSBUILD_DIAG.search(text):
        return None
    errors, warnings = _msbuild_diagnostics(lines)
    verdict = "Build FAILED" if errors or "Build FAILED" in text else "Build succeeded"
    verdict += f": {len(errors)} error(s), {len(warnings)} warning(s)"
    shown_warnings = warnings[:20]
    if len(warnings) > 20:
        shown_warnings.append(f"... {len(warnings) - 20} more warnings")
    return verdict, errors + shown_warnings


def dotnet_test(lines: list[str]):
    verdict = None
    for ln in lines:
        s = ln.strip()
        if re.match(r"^(Passed|Failed)!\s+-\s+Failed:", s) or re.match(r"(?i)^test summary:\s+total:", s):
            verdict = s if verdict is None else verdict + " | " + s
    if verdict is None:
        return None
    details: list[str] = []
    errors, _ = _msbuild_diagnostics(lines)
    details += errors
    i = 0
    while i < len(lines):
        s = lines[i].strip()
        m = re.match(r"^(?:X\s+)?Failed\s+(\S+)", s)
        if m and not s.startswith("Failed!"):
            details.append(f"FAILED {m.group(1)}")
            j = i + 1
            mode = None
            stack_lines = 0
            while j < len(lines):
                t = lines[j].strip()
                next_test = re.match(r"^(?:X\s+|✓\s+|√\s+)?(Passed|Failed|Skipped)\s+\S", t)
                if next_test and not t.startswith("Failed!"):
                    break
                if t.startswith("Error Message:"):
                    mode = "msg"
                elif t.startswith("Stack Trace:"):
                    mode = "stack"
                elif mode == "msg" and t:
                    details.append("  " + t)
                elif mode == "stack" and " in " in t and ":line " in t and stack_lines < 2:
                    details.append("  " + t)
                    stack_lines += 1
                j += 1
            i = j
            continue
        i += 1
    return verdict, _dedupe(details)


# ---------------------------------------------------------------- JavaScript


def jest_vitest(lines: list[str]):
    verdict = [ln.strip() for ln in lines
               if re.match(r"^\s*Tests:?\s+.*\b(passed|failed|total)\b", ln)]
    if not verdict:
        return None
    keep = ("●", "✕", "×", "FAIL ", "AssertionError", "Expected", "Received", "❯ ", "→ ", "Error:")
    details = [ln.rstrip() for ln in lines if ln.strip().startswith(keep)]
    return " | ".join(verdict), _dedupe(details)


def tsc(lines: list[str]):
    diags = [ln.strip() for ln in lines if re.search(r"\berror TS\d+", ln)]
    if not diags:
        return None
    return f"TypeScript: {len(diags)} error(s)", _dedupe(diags)


# ---------------------------------------------------------------- Go / Rust


_GO_MARKER = re.compile(r"^(--- (FAIL|PASS):|ok\s+\S+\s+(\(cached\)|[\d.]+s)|FAIL\s*$|FAIL\t)")


def go_test(lines: list[str]):
    if not any(_GO_MARKER.match(ln) for ln in lines):
        return None
    details = []
    for i, ln in enumerate(lines):
        if ln.startswith("--- FAIL"):
            details.append(ln)
            for nxt in lines[i + 1:i + 12]:
                if nxt.startswith("    "):
                    details.append(nxt.rstrip())
                else:
                    break
        elif re.match(r"^(FAIL|ok)\s", ln) or ln.startswith("panic:"):
            details.append(ln.rstrip())
    failed = sum(1 for ln in lines if ln.startswith("--- FAIL"))
    any_fail = failed or any(ln.startswith("FAIL") for ln in lines)
    return (f"go test: {failed} failed" if any_fail else "go test: ok"), _dedupe(details)


def cargo(lines: list[str]):
    results = [ln.strip() for ln in lines if ln.startswith("test result:")]
    diags = []
    for i, ln in enumerate(lines):
        if re.match(r"^(error(\[E\d+\])?|warning):", ln):
            diags.append(ln.rstrip())
            if i + 1 < len(lines) and lines[i + 1].strip().startswith("-->"):
                diags.append(lines[i + 1].rstrip())
    is_cargo = any("Compiling " in ln or "could not compile" in ln for ln in lines)
    if not results and not (diags and is_cargo):
        return None
    details = list(diags)
    capture = False
    for ln in lines:
        if re.match(r"^---- .* stdout ----$", ln):
            capture = True
            details.append(ln)
            continue
        if capture:
            if not ln.strip():
                capture = False
            else:
                details.append("  " + ln.strip())
        elif re.match(r"^test .* \.\.\. FAILED$", ln):
            details.append(ln.strip())
    n_errors = sum(1 for d in diags if d.startswith("error"))
    verdict = " | ".join(results) if results else f"cargo: {n_errors} error(s)"
    return verdict, _dedupe(details)


# ---------------------------------------------------------------- generic


_ERRORISH = re.compile(r"(?i)\b(error|errors|failed|failure|fail|exception|fatal|panic|traceback)\b")


def generic(lines: list[str], rc: int | None):
    non_empty = [ln for ln in lines if ln.strip()]
    if rc == 0:
        return "ok", non_empty[-5:]
    picked = []
    for i, ln in enumerate(lines):
        if _ERRORISH.search(ln):
            picked.extend(lines[max(0, i - 1):i + 2])
    details = _dedupe(picked)[:60]
    shown = {ln.strip() for ln in details}
    tail = [ln for ln in non_empty[-GENERIC_TAIL:] if ln.strip() not in shown]
    if tail:
        details += ["--- last lines ---", *tail]
    return "failed", details


# ---------------------------------------------------------------- linters (#166)


# flake8/ruff "path:12:5: F401 msg" and mypy/gcc "path:12:5: error: msg" (column optional)
_LINT_LINE = re.compile(r"^\S.*?:\d+:(?:\d+:)? (?:[A-Z]{1,4}\d{1,4}\b|(error|warning|note):)")
_LINT_SUMMARY = re.compile(r"^(Found \d+ errors?\b.*|Success: no issues found.*)$")


def lint(lines: list[str]):
    diags = [ln.rstrip() for ln in lines if _LINT_LINE.match(ln)]
    if not diags:
        return None
    count = sum(1 for d in diags if _LINT_LINE.match(d).group(1) != "note")
    summaries = [ln.strip() for ln in lines if _LINT_SUMMARY.match(ln.strip())]
    return " | ".join([f"{count} problem(s)", *summaries]), _dedupe(diags)


_ESLINT_FILE = re.compile(r"^(/|[A-Za-z]:[\\/]|\S).*\.(?:[cm]?[jt]sx?|vue|svelte|astro|json|md|html?)$")
_ESLINT_FINDING = re.compile(r"^\s+(\d+):(\d+)\s+(error|warning)\s+(.*?)(?:\s{2,}(\S+))?\s*$")
_ESLINT_SUMMARY = re.compile(r"^✖ (\d+ problems? \(.*\))")


def eslint_stylish(lines: list[str]):
    """ESLint's default format: a file line, then '  12:5  error  msg  rule' lines without the
    file, so each finding gets its file back (#269). Errors come before warnings."""
    errors, warnings = [], []
    current = None
    for ln in lines:
        if _ESLINT_FILE.match(ln) and not ln.startswith(("✖", ">")):
            current = ln.strip()
            continue
        m = _ESLINT_FINDING.match(ln) if current else None
        if m:
            line, col, level, msg, rule = m.groups()
            entry = f"{current}:{line}:{col}: {level} {msg}" + (f" ({rule})" if rule else "")
            (errors if level == "error" else warnings).append(entry)
        elif ln.strip() and not ln.startswith(" "):
            current = None
    summary = next((m.group(1) for ln in lines if (m := _ESLINT_SUMMARY.match(ln.strip()))), None)
    if not (errors or warnings) or summary is None:
        return None
    return f"eslint: {summary}", _dedupe(errors) + _dedupe(warnings)


# Order matters: tsc diagnostics look like MSBuild ones, so tsc is tried first.
PARSERS = [pytest, dotnet_test, tsc, dotnet_build, jest_vitest, go_test, cargo, eslint_stylish, lint]


def summarize(output: str, rc: int | None, root=None) -> tuple[str, list[str], int]:
    """(verdict, kept lines, raw line count) for a command's combined output. With the project
    root, absolute paths under it are shown relative to it."""
    text = clean(output)
    if root:
        text = text.replace(str(root).rstrip("/\\") + "/", "")
    lines = text.split("\n")
    raw_count = sum(1 for ln in lines if ln.strip())
    for parser in PARSERS:
        parsed = parser(lines)
        if parsed:
            verdict, details = parsed
            break
    else:
        verdict, details = generic(lines, rc)
    details = [ln if len(ln) <= MAX_LINE else
               f"{ln[:MAX_LINE]} ... ({len(ln) - MAX_LINE} more characters)" for ln in details]
    if len(details) > MAX_DETAIL:
        details = details[:MAX_DETAIL] + [f"... {len(details) - MAX_DETAIL} more lines"]
    return verdict, details, raw_count
