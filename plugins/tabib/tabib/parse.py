"""Reading a failed CI log: which tests or checks failed, where, and signs of trouble outside the code.

The log is untrusted text (anyone can open a pull request): it is only matched against fixed
patterns here, never run or followed. Parsers cover pytest, jest and vitest, Playwright, go test,
dotnet test, cargo test, JUnit XML printed in the log, tsc, mypy, ruff and eslint, plus generic error
lines and crashes (a segmentation fault); signals cover timeouts, running out of memory, crashes, the
network, rate limits, the runner, credentials and dependency resolution.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET

ANSI = re.compile(r"\x1b(?:\[[0-9;?]*[ -/]*[@-~]|\][^\x07\x1b]*(?:\x07|\x1b\\)|[@-Z\\-_])")
CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f\u061c\u200e\u200f\u202a-\u202e\u2066-\u2069]")
STAMP = re.compile(r"^﻿?\d{4}-\d\d-\d\dT[\d:.]+Z ?")
MAX_LINES = 200_000

# ------------------------------------------------------------------ signals (outside the code)

SIGNALS = [
    ("timeout", re.compile(r"(?i)exceeded the maximum execution time|timed? ?out after \d|"
                           r"job .{0,40}timed out|deadline exceeded")),
    # "Killed" only as the shell or the kernel says it, never inside a test's own message.
    ("oom", re.compile(r"(?i)exit code 137\b|^\s*Killed\s*$|line \d+:\s+\d+ Killed\b|Killed process \d+|"
                       r"heap out of memory|\bMemoryError\b|OOMKilled|cannot allocate memory")),
    ("network", re.compile(r"(?i)could not resolve host|ECONNRESET|ETIMEDOUT|ECONNREFUSED|EAI_AGAIN|"
                           r"connection (?:timed out|reset)|TLS handshake timeout|temporary failure in name "
                           r"resolution|50[234] (?:Bad Gateway|Service Unavailable|Gateway Time-?out)")),
    ("rate_limit", re.compile(r"(?i)rate limit exceeded|429 Too Many Requests|secondary rate limit")),
    ("runner", re.compile(r"(?i)runner has received a shutdown signal|lost communication with the server|"
                          r"was not acquired by runner|"
                          r"no space left on device|hosted runner encountered an error")),
    ("auth", re.compile(r"(?i)bad credentials|401 Unauthorized|403 Forbidden|input required and not supplied|"
                        r"permission denied \(publickey\)|resource not accessible by integration")),
    ("segfault", re.compile(r"(?i)segmentation (?:fault|violation)|\bSIGSEGV\b|exit code 139\b|"
                            r"Windows fatal exception: access violation")),
    # GitHub prints this after a timeout, a shutdown and a cancel alike: the weakest sign.
    ("cancelled", re.compile(r"(?i)the operation was canceled")),
    ("dependency", re.compile(r"(?i)could not find a version that satisfies|no matching distribution|"
                              r"\bERESOLVE\b|npm ERR! code ETARGET|version solving failed|"
                              r"unable to resolve dependency|no solution found when resolving")),
]

SIGNALS_BY_KIND = dict(SIGNALS)

# ------------------------------------------------------------------ failures (in the code)

PYTEST = re.compile(r"^(FAILED|ERROR) (\S+?\.py)(::.+?)?(?: - (.*))?$")
PY_LOC = re.compile(r"^(\S+\.py):(\d+): (\w+)")
PY_SECTION = re.compile(r"^_{3,} (\S.*?) _{3,}$")
MYPY = re.compile(r"^(\S+\.pyi?):(\d+)(?::\d+)?: error: (.*?)(?:\s+\[([\w-]+)\])?$")
JEST_FILE = re.compile(r"^\s*(?:FAIL|×|✗|❯)\s+(\S+\.[cm]?[jt]sx?)(?:\s+>\s+(.+?))?"
                       r"(?:\s+\(?\d+(?:\.\d+)?\s*m?s\)?)?\s*$")
JEST_TEST = re.compile(r"^\s*●\s+(.+?)\s*$")
JS_LOC = re.compile(r"(?:❯|at .*?\(|at )\s*(?:file://)?(\S+?\.[cm]?[jt]sx?):(\d+):\d+")
GO_FAIL = re.compile(r"^\s*--- FAIL: (\S+)")
GO_RUN = re.compile(r"^=== (?:RUN|CONT)\s+(\S+)")
GO_END = re.compile(r"^\s*--- (?:PASS|SKIP): ")
GO_LOC = re.compile(r"^\s+(\S+_test\.go):(\d+): (.*)$")
GO_PKG = re.compile(r"^FAIL\s+(\S+)\s+[\d.]+s$")
DOTNET = re.compile(r"^\s*Failed (\S+) \[")
CARGO = re.compile(r"^test (\S+) \.\.\. FAILED$")
CARGO_PANIC = re.compile(r"(?:thread '([^']+)' )?panicked at (\S+?\.rs):(\d+):\d+:?\s*(.*)$")
CARGO_SECTION = re.compile(r"^---- (\S+) stdout ----$")
TSC = re.compile(r"^(\S+\.tsx?)(?:\((\d+),\d+\):|:(\d+):\d+ -) error (TS\d+): (.*)$")
RUFF = re.compile(r"^(\S+\.py):(\d+):\d+: ([A-Z]+\d+)\b:? ?(.*)$")
RUFF_CODE = re.compile(r"^([A-Z]+\d+) (.+)$")
RUFF_ARROW = re.compile(r"^\s*--> (\S+\.py):(\d+):\d+")
ESLINT_FILE = re.compile(r"^(/\S+\.[cm]?[jt]sx?|\S+/\S+\.[cm]?[jt]sx?)$")
ESLINT = re.compile(r"^\s+(\d+):\d+\s+error\s+(.+?)\s{2,}(\S+)$")
# Stack frames and other `path:line` places in a traceback, for git blame (#104).
FRAMES = [re.compile(r'^\s*File "([^"<>]+)", line (\d+)'),                    # Python (and faulthandler)
          re.compile(r"^(\S+\.py):(\d+): \w"),                                # pytest
          re.compile(r"(?:\bat |❯)\s*.*?\(?(?:file://)?([^\s()]+?\.[cm]?[jt]sx?):(\d+):\d+"),   # node
          re.compile(r"panicked at (\S+?\.rs):(\d+):\d+"),                    # rust
          re.compile(r"^\s+(\S+\.go):(\d+)(?::\d+)?[: ]"),                      # go
          re.compile(r"^\s*at (?:[\w.@-]+/+)?(?!(?:java|javax|jdk|sun|kotlin|junit|org\.junit|"   # JVM, not
                     r"org\.opentest4j|org\.gradle|org\.apache\.maven)\.)"                     # the libraries
                     r"[\w.$<>]+\((\w+\.(?:java|kt|scala)):(\d+)\)")]
FOREIGN = re.compile(r"(?:^|/)(?:site-packages|dist-packages|node_modules|\.cargo/registry|go/pkg/mod|"
                     r"lib/python\d|hostedtoolcache)/|^(?:/usr|internal|node:)")
# Playwright: "  1) [chromium] › tests/a.spec.ts:8:5 › describe › title ───", the "✘  2 [...] › ..."
# lines of the list reporter, and the summary's "  1 failed" / "  1 flaky" groups that follow.
PW_ENTRY = re.compile(r"^\s*(?:(\d+)\) |✘\s+\d+ )?\[([^\]]+)\] › (\S+?):(\d+):\d+ › (.+?)"
                      r"(?: \(retry #\d+\))?(?: \(\d+(?:\.\d+)?m?s\))?(?:\s*─+)?\s*$")
PW_GROUP = re.compile(r"^\s*\d+ (failed|flaky|passed|skipped|interrupted|did not run)\b")
PW_ERROR = re.compile(r"^\s*(?:\w+)?Error\b")
JUNIT_START = re.compile(r"<(testsuites|testsuite)\b")
FAULT_HEADER = re.compile(r"Fatal Python error: Segmentation fault")
FAULT_FRAME = re.compile(r'^\s*File "([^"]+)", line (\d+) in (test\w*)')
ERROR_LINE = re.compile(r"(?i)^(?:##\[error\]|error(?:\[\w+\])?:|fatal:|npm ERR!|E\s{3})"
                        r"|\b\w+(?:Error|Exception): ")


def clean_text(text: str) -> str:
    """Text from a log or a CI service, safe to print: no escape sequences, controls or direction marks."""
    return CONTROL.sub("", ANSI.sub("", str(text or "")))


def clean_line(line: str) -> str:
    return STAMP.sub("", clean_text(line.rstrip("\r\n")))


def split_jobs(text: str) -> dict[str, list[str]]:
    """`gh run view --log-failed` lines are `job<TAB>step<TAB>time text`; other logs are one job."""
    jobs: dict[str, list[str]] = {}
    for raw in text.splitlines()[:MAX_LINES]:
        parts = raw.split("\t", 2)
        if len(parts) == 3:
            job, _step, rest = parts
            job = clean_text(job)[:200]
        else:
            job, rest = "", raw
        jobs.setdefault(job, []).append(clean_line(rest))
    return jobs


def _short(text: str, limit: int = 240) -> str:
    flat = " ".join(text.split())
    return flat if len(flat) <= limit else flat[: limit - 1] + "…"


def _failure(framework: str, kind: str, test: str = "", file: str = "", line: int = 0,
             message: str = "") -> dict:
    return {"framework": framework, "kind": kind, "test": _short(test, 200), "file": file, "line": line,
            "message": _short(message), "package": ""}


def playwright(lines: list[str]) -> list[dict]:
    """Playwright's failed tests: the summary's "failed" group when there is one (a test in its "flaky"
    group passed on a retry), else the numbered error blocks, else the list reporter's ✘ lines."""
    blocks: dict[tuple[str, str, str], dict] = {}
    listed: list[tuple[str, str, str]] = []
    groups: dict[str, list[tuple[str, str, str]]] = {}
    block: dict | None = None
    group = ""
    for line in lines:
        if m := PW_GROUP.match(line):
            group, block = m.group(1), None
            groups.setdefault(group, [])
            continue
        if m := PW_ENTRY.match(line):
            key = (m.group(2), m.group(3), m.group(5).replace(" › ", " > "))
            if m.group(1):
                group = ""
                block = blocks.setdefault(key, _failure("playwright", "tests", f"[{key[0]}] {key[2]}", key[1],
                                                        int(m.group(4))))
                block["placed"] = False
            elif line.lstrip().startswith("✘"):
                listed.append(key)
            elif group:
                groups[group].append(key)
            continue
        group = "" if line.strip() else group
        if block is not None and not block.get("done"):
            if not block["message"] and PW_ERROR.match(line):
                block["message"] = _short(line)
            if (m := JS_LOC.search(line)) and not block["placed"] \
                    and m.group(1).split("/")[-1] == block["file"].split("/")[-1]:
                block.update(line=int(m.group(2)), placed=True)
            if line.strip().startswith("Retry #"):
                block["done"] = True
    if "failed" in groups or "interrupted" in groups:
        keys = groups.get("failed", []) + groups.get("interrupted", [])
    else:
        keys = list(blocks) or listed
    out = []
    for key in dict.fromkeys(keys):
        failure = blocks.get(key) or _failure("playwright", "tests", f"[{key[0]}] {key[2]}", key[1])
        failure.pop("placed", None)
        failure.pop("done", None)
        out.append(failure)
    return out


def junit_xml(text: str) -> list[dict]:
    """Failed and errored test cases in a JUnit XML report (JUnit, Gradle, Maven, pytest --junitxml).

    The report is untrusted: one with a DOCTYPE or an entity is refused, so nothing is ever expanded.
    """
    if len(text) > 4_000_000 or "<!DOCTYPE" in text.upper() or "<!ENTITY" in text.upper():
        return []
    try:
        root = ET.fromstring(text)
    except (ET.ParseError, ValueError):
        return []
    found = []
    for case in root.iter("testcase"):
        for child in case:
            if child.tag not in ("failure", "error"):
                continue
            body = (child.text or "").strip()
            places = frames(body.splitlines())
            file = case.get("file") or ""
            place = next((p for p in places if not file or p[0].split("/")[-1] == file.split("/")[-1]), None)
            given = case.get("line") or ""
            line = place[1] if place else int(given) if given.isdigit() else 0
            name, owner = case.get("name") or "", case.get("classname") or ""
            message = child.get("message") or (body.splitlines() or [child.get("type") or child.tag])[0]
            found.append(_failure("junit", "tests", f"{owner}.{name}" if owner else name,
                                  file or (place[0] if place else ""), line, message))
            break
        if len(found) >= 50:
            break
    return found


def junit_blocks(lines: list[str]) -> list[str]:
    """JUnit XML reports printed in the log (`cat build/test-results/...xml`), as text."""
    out: list[str] = []
    block: list[str] = []
    root = ""
    for line in lines:
        if not block and (m := JUNIT_START.search(line)):
            root, line = m.group(1), line[m.start():]
        if root:
            block.append(line)
            if f"</{root}>" in line or len(block) > 20_000:
                out.append("\n".join(block))
                block, root = [], ""
    return out


def crash(lines: list[str]) -> dict | None:
    """A segmentation fault, as a failure; with Python's faulthandler, at the test that was running."""
    hit = next((line for line in lines if SIGNALS_BY_KIND["segfault"].search(line)), None)
    if hit is None:
        return None
    failure = _failure("crash", "tests", message=hit)
    started = next((i for i, line in enumerate(lines) if FAULT_HEADER.search(line)), -1)
    for line in lines[started + 1:] if started >= 0 else []:
        if m := FAULT_FRAME.match(line):
            failure.update(test=m.group(3), file=m.group(1), line=int(m.group(2)))
            break
    return failure


def failures(lines: list[str]) -> list[dict]:
    found: list[dict] = []
    py_lines: dict[str, int] = {}
    py_test_lines: dict[str, int] = {}  # "TestTax.test_rate[eu]" -> its own line, from its FAILURES section
    py_section = ""
    go_run = ""  # the test `go test -v` is running: its locations come before "--- FAIL"
    go_locs: dict[str, tuple[str, int, str]] = {}
    cargo_section = ""
    cargo_panics: dict[str, tuple[str, int, str]] = {}
    js_lines: dict[str, int] = {}
    pending_jest: list[dict] = []
    eslint_file = ""
    jest_file = ""
    ruff_code = ""
    dotnet_last: dict | None = None
    for i, line in enumerate(lines):
        if m := PY_SECTION.match(line):
            py_section = m.group(1) if "." in m.group(1) or m.group(1).startswith("test") else ""
        if m := PY_LOC.match(line):
            py_lines.setdefault(m.group(1), int(m.group(2)))
            if py_section:
                py_test_lines.setdefault(py_section, int(m.group(2)))
        if m := JS_LOC.search(line):
            js_lines.setdefault(m.group(1).split("/")[-1], int(m.group(2)))
        if m := PYTEST.match(line):
            node = m.group(2) + (m.group(3) or "")
            found.append(_failure("pytest", "tests", node, m.group(2), 0, m.group(4) or m.group(1).lower()))
        elif m := MYPY.match(line):
            found.append(_failure("mypy", "build", m.group(4) or "mypy", m.group(1), int(m.group(2)),
                                  m.group(3)))
        elif m := GO_RUN.match(line):
            go_run = m.group(1)
        elif GO_END.match(line):
            go_run = ""
        elif m := GO_FAIL.match(line):
            failure = _failure("go", "tests", m.group(1))
            if m.group(1) in go_locs:
                file, number, message = go_locs[m.group(1)]
                failure.update(file=file, line=number, message=_short(message))
            found.append(failure)
            go_run = ""
        elif (m := GO_LOC.match(line)) and go_run:
            go_locs.setdefault(go_run, (m.group(1), int(m.group(2)), m.group(3)))
        elif (m := GO_LOC.match(line)) and found and found[-1]["framework"] == "go" and not found[-1]["file"]:
            found[-1].update(file=m.group(1), line=int(m.group(2)), message=_short(m.group(3)))
        elif m := GO_PKG.match(line):
            for f in found:
                if f["framework"] == "go" and not f.get("package"):
                    f["package"] = m.group(1)
        elif m := DOTNET.match(line):
            dotnet_last = _failure("dotnet", "tests", m.group(1))
            found.append(dotnet_last)
        elif dotnet_last is not None and line.strip() == "Error Message:" and i + 1 < len(lines):
            dotnet_last["message"] = _short(lines[i + 1])
            dotnet_last = None
        elif m := CARGO.match(line):
            found.append(_failure("cargo", "tests", m.group(1)))
        elif m := CARGO_SECTION.match(line):
            cargo_section = m.group(1)
        elif m := CARGO_PANIC.search(line):
            # The thread is named after its test; the "---- <test> stdout ----" header says it too.
            owner = m.group(1) if m.group(1) and m.group(1) != "main" else cargo_section
            message = m.group(4) or (lines[i + 1] if i + 1 < len(lines) else "")
            if owner:
                cargo_panics.setdefault(owner, (m.group(2), int(m.group(3)), message))
            else:
                target = next((f for f in reversed(found)
                               if f["framework"] == "cargo" and not f["file"]), None)
                if target:
                    target.update(file=m.group(2), line=int(m.group(3)), message=_short(message))
        elif m := TSC.match(line):
            found.append(_failure("tsc", "build", m.group(4), m.group(1), int(m.group(2) or m.group(3)),
                                  m.group(5)))
        elif m := RUFF.match(line):
            found.append(_failure("ruff", "lint", m.group(3), m.group(1), int(m.group(2)), m.group(4)))
        elif m := RUFF_CODE.match(line):
            ruff_code = line
        elif (m := RUFF_ARROW.match(line)) and ruff_code:
            code, _, message = ruff_code.partition(" ")
            found.append(_failure("ruff", "lint", code, m.group(1), int(m.group(2)), message))
            ruff_code = ""
        elif m := ESLINT_FILE.match(line):
            eslint_file = m.group(1)
        elif (m := ESLINT.match(line)) and eslint_file:
            found.append(_failure("eslint", "lint", m.group(3), eslint_file, int(m.group(1)), m.group(2)))
        elif m := JEST_FILE.match(line):
            found.append(_failure("jest", "tests", m.group(2) or "", m.group(1)))
            jest_file = m.group(1)
        elif (m := JEST_TEST.match(line)) and m.group(1) != "Console":
            test = _failure("jest", "tests", m.group(1).replace(" › ", " > "), jest_file)
            pending_jest.append(test)
    for f in found:
        if f["framework"] == "cargo" and not f["file"] and f["test"] in cargo_panics:
            file, number, message = cargo_panics[f["test"]]
            f.update(file=file, line=number, message=_short(message))
        if f["framework"] == "pytest" and not f["line"]:
            name = f["test"].partition("::")[2].replace("::", ".")
            f["line"] = py_test_lines.get(name) or py_lines.get(f["file"], 0)
        elif f["framework"] == "jest" and not f["line"] and f["file"]:
            f["line"] = js_lines.get(f["file"].split("/")[-1], 0)
    if pending_jest:  # jest names tests under "●", each after the "FAIL <file>" it belongs to
        found = [f for f in found if not (f["framework"] == "jest" and not f["test"])]
        for f in pending_jest:
            f["line"] = js_lines.get(f["file"].split("/")[-1], 0) if f["file"] else 0
        found += pending_jest
    found += playwright(lines)
    for block in junit_blocks(lines):
        found += junit_xml(block)
    if not found and (crashed := crash(lines)):
        found.append(crashed)  # the tests stopped with the process; nothing else names the failure
    seen, unique = set(), []
    for f in found:
        key = (f["framework"], f["test"], f["file"], f["line"])
        if key not in seen:
            seen.add(key)
            unique.append(f)
    return unique[:50]


def frames(lines: list[str], limit: int = 30) -> list[tuple[str, int]]:
    """`(path, line)` places named in stack traces, in log order, without libraries; untrusted paths."""
    found: list[tuple[str, int]] = []
    for line in lines:
        for pattern in FRAMES:
            m = pattern.search(line)
            if m and not FOREIGN.search(m.group(1)) and 0 < int(m.group(2)) < 1_000_000:
                place = (m.group(1), int(m.group(2)))
                if place not in found:
                    found.append(place)
                    if len(found) >= limit:
                        return found
                break
    return found


def signals(lines: list[str]) -> list[dict]:
    found = []
    for kind, pattern in SIGNALS:
        hit = next((line for line in lines if pattern.search(line)), None)
        if hit is not None:
            found.append({"kind": kind, "line": _short(hit, 200)})
    return found


def errors(lines: list[str], limit: int = 12) -> list[str]:
    out: list[str] = []
    for line in lines:
        if ERROR_LINE.search(line) and "Process completed with exit code" not in line:
            text = _short(line, 200)
            if text and text not in out:
                out.append(text)
                if len(out) >= limit:
                    break
    return out


MISSING_MODULE = re.compile(r"No module named '?([\w.]+)'?|Cannot find module '([^'./][^']*)'")


def missing_modules(lines: list[str]) -> list[str]:
    """Modules an import could not find: 'jsonschema' (Python), 'left-pad' (Node); relative paths are not."""
    found: list[str] = []
    for line in lines:
        for m in MISSING_MODULE.finditer(line):
            name = m.group(1) or m.group(2)
            if name not in found:
                found.append(name)
    return found


def read_log(text: str) -> dict:
    """{job: {failures, signals, errors, frames, missing, lines}} for each job in a failed log."""
    out = {}
    for job, lines in split_jobs(text).items():
        out[job] = {"failures": failures(lines), "signals": signals(lines), "errors": errors(lines),
                    "frames": frames(lines), "missing": missing_modules(lines), "lines": lines}
    return out


def excerpt(lines: list[str], needles: list[str], around: int = 12, limit: int = 4000) -> str:
    """The log lines around the first mention of each failure, for the diagnosis (untrusted text)."""
    picked: list[int] = []
    for needle in needles:
        if not needle:
            continue
        index = next((i for i, line in enumerate(lines) if needle in line), None)
        if index is not None:
            picked += range(max(0, index - around), min(len(lines), index + around))
    if not picked:
        picked = list(range(max(0, len(lines) - 2 * around), len(lines)))
    text, last = [], -2
    for i in sorted(set(picked)):
        if i != last + 1:
            text.append("…")
        text.append(lines[i][:300])
        last = i
    joined = "\n".join(text)
    return joined[-limit:]
