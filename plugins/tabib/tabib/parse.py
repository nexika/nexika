"""Reading a failed CI log: which tests or checks failed, where, and signs of trouble outside the code.

The log is untrusted text (anyone can open a pull request): it is only matched against fixed
patterns here, never run or followed. Parsers cover pytest, jest and vitest, Playwright, go test,
dotnet test, cargo test, JUnit XML printed in the log, tsc, mypy, ruff and eslint, plus generic error
lines and crashes (a segmentation fault); signals cover timeouts, running out of memory, crashes, the
network, rate limits, the runner, credentials, a CI setup that cannot work and dependency resolution.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET

# GitHub's downloaded log keeps some colours as text: "^[[41m" for "\x1b[41m".
ANSI = re.compile(r"\x1b(?:\[[0-9;?]*[ -/]*[@-~]|\][^\x07\x1b]*(?:\x07|\x1b\\)|[@-Z\\-_])"
                  r"|\^\[\[[0-9;]*m")
CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f\u061c\u200e\u200f\u202a-\u202e\u2066-\u2069]")
STAMP = re.compile(r"^﻿?\d{4}-\d\d-\d\dT[\d:.]+Z ?")
MAX_LINES = 200_000

# ------------------------------------------------------------------ signals (outside the code)

SIGNALS = [
    # The job's or a step's time limit, not a test's own ("'test timed out after 30000ms'", #253).
    ("timeout", re.compile(r"(?i)exceeded the maximum execution time|(?:job|step|action) .{0,40}timed out|"
                           r"deadline exceeded")),
    # "Killed" only as the shell or the kernel says it, never inside a test's own message.
    ("oom", re.compile(r"(?i)exit code 137\b|^\s*Killed\s*$|line \d+:\s+\d+ Killed\b|Killed process \d+|"
                       r"heap out of memory|\bMemoryError\b|OOMKilled|cannot allocate memory")),
    ("network", re.compile(r"(?i)could not resolve host|ECONNRESET|ETIMEDOUT|ECONNREFUSED|EAI_AGAIN|"
                           r"connection (?:timed out|reset)|TLS handshake timeout|temporary failure in name "
                           r"resolution|50[234] (?:Bad Gateway|Service Unavailable|Gateway Time-?out)|"
                           # GitHub's own service errors (#254); a 403 is not one: it may never lift.
                           r"Failed to resolve action download info|\bHTTP 50[0234]\b|"
                           r"^##\[error\](?:Service Unavailable|Internal Server Error|Bad Gateway|"
                           r"Gateway Time-?out)\s*$|"
                           r"failed to download .{0,60}Status code: 5\d\d\b")),
    ("rate_limit", re.compile(r"(?i)rate limit exceeded|429 Too Many Requests|secondary rate limit")),
    ("runner", re.compile(r"(?i)runner has received a shutdown signal|lost communication with the server|"
                          r"was not acquired by runner|"
                          r"no space left on device|hosted runner encountered an error")),
    ("auth", re.compile(r"(?i)bad credentials|401 Unauthorized|403 Forbidden|input required and not supplied|"
                        r"permission denied \(publickey\)|resource not accessible by integration")),
    # A workflow that cannot work as written: a re-run fails the same way (#127).
    ("setup", re.compile(r"(?i)\bis externally managed\b|\berror: externally-managed-environment|"
                         r"\bFailed to spawn: `|\bline \d+: [\w.-]+: command not found|"
                         r"^##\[error\]\"[\w-]+\" (?:is required|is not allowed|must be|length must be)\b|"
                         r"Unable to resolve action `|Can't find 'action\.ya?ml'|Invalid workflow file|"
                         r"The version '[^']+' with architecture '[^']+' was not found|"   # setup-python
                         r"(?:^|\s)--[a-z][\w-]+ error: invalid value: '|"   # a tool option from the env
                         r"Artifact directory does not exist|Artifact not found for name")),
    # A branch rule the workflow's token cannot pass (#262): a re-run fails the same way.
    ("rules", re.compile(r"(?i)repository rule violations found|\d+ approving reviews? (?:is|are) required")),
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
# GitHub's problem matchers print "##[error]" before a linter's own line (#256).
MATCHER = re.compile(r"^##\[(?:error|warning)\]")
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


PRE_COMMIT_FAILED = re.compile(r"^\S.*?\.{3,}\s*Failed$")
PRE_COMMIT_ID = re.compile(r"^- hook id: ([\w.-]+)$")   # it ends up in a command: nothing else gets through
PRE_COMMIT_NOTE = re.compile(r"^- (files were modified by this hook|exit code: \d+)$")
DIFF_FILE = re.compile(r"^diff --git a/(\S+) b/")


def pre_commit(lines: list[str]) -> list[dict]:
    """pre-commit's failed hooks: 'ruff format....Failed', then '- hook id: ruff-format' and what it did."""
    found = []
    for i, line in enumerate(lines[:-1]):
        if PRE_COMMIT_FAILED.match(line.strip()) and (m := PRE_COMMIT_ID.match(lines[i + 1].strip())):
            notes = (PRE_COMMIT_NOTE.match(n.strip()) for n in lines[i + 2:i + 4])
            found.append(_failure("pre-commit", "lint", m.group(1),
                                  message=next((n.group(1) for n in notes if n), "")))
    if len(found) == 1:  # the diff after "All changes made by hooks" is shared: a file is sure for one hook
        found[0]["file"] = next((m.group(1) for line in lines if (m := DIFF_FILE.match(line.strip()))), "")
    return found


CONFTEST = re.compile(r"^ImportError while loading conftest '([^']+)'\.?$")
CONFTEST_LOC = re.compile(r"^(\S+\.py):(\d+): in ")


def conftest(lines: list[str]) -> list[dict]:
    """A conftest pytest could not import: nothing ran (exit code 4). The file is the relative one of the
    traceback's first frame (the header has the CI machine's path), the message its 'E   ' line."""
    found = []
    for i, line in enumerate(lines):
        if not (m := CONFTEST.match(line.strip())):
            continue
        file, number = m.group(1), 0
        if i + 1 < len(lines) and (loc := CONFTEST_LOC.match(lines[i + 1].strip())) \
                and file.endswith("/" + loc.group(1)):
            file, number = loc.group(1), int(loc.group(2))
        message = next((n.strip()[1:].strip() for n in lines[i + 1:i + 60] if n.startswith("E ")),
                       "ImportError")
        found.append(_failure("pytest", "tests", file, file, number, message))
    return found


REFORMAT = re.compile(r"^(would reformat|Would reformat:) (\S+)$")
PRETTIER_FILE = re.compile(r"^\[warn\] (\S+)$")
PRETTIER_END = re.compile(r"^\[warn\] Code style issues found")
CHECKOUT = re.compile(r"^(?:.*?/work/[^/]+/[^/]+/|[A-Za-z]:/a/[^/]+/[^/]+/)")
SAFE_PATH = re.compile(r"^[\w.@+-][\w./@+-]*$")   # it ends up in a command: nothing else gets through
FORMAT_COMMANDS = {"black": "black", "ruff-format": "ruff format", "prettier": "prettier --write"}


def formatter(lines: list[str]) -> list[dict]:
    """Files a formatter's check would change: black ('would reformat <path>'), ruff format ('Would
    reformat: <path>'), prettier ('[warn] <path>' before 'Code style issues found'); paths made relative
    to the checkout."""
    found = []
    warned: list[str] = []
    for line in lines:
        line = line.strip()
        tool, path = "", ""
        if m := REFORMAT.match(line):
            tool, path = ("black" if m.group(1) == "would reformat" else "ruff-format"), m.group(2)
        elif PRETTIER_END.match(line):
            found += [_failure("prettier", "lint", file=p, message="prettier --check") for p in warned]
            warned = []
        elif m := PRETTIER_FILE.match(line):
            warned.append(CHECKOUT.sub("", m.group(1).replace("\\", "/")))
        if path:
            path = CHECKOUT.sub("", path.replace("\\", "/"))
            if SAFE_PATH.match(path):
                found.append(_failure(tool, "lint", file=path, message=f"{tool}: would reformat"))
    return [f for f in found if SAFE_PATH.match(f["file"])]


STEP_START = re.compile(r"^##\[group\]Run ")
STEP_EXIT = re.compile(r"^##\[error\]Process completed with exit code [1-9]")
ECHO = re.compile(r"""\becho\s+(?:-e\s+)?(["'])(.+?)\1""")


# A JavaScript action's step: "Run owner/action@ref". One that sets up the job (checkout, setup-*, cache,
# artifacts) is no check of the project when it fails.
STEP_ACTION = re.compile(r"^##\[group\]Run [\w.-]+/[\w./-]+@\S+\s*$")
LINK_STATUS = re.compile(r"^\[\d{3}\] \S+")   # a link checker's "[403] <url>": a site's answer, not a check
SETUP_ACTION = re.compile(r"(?i)^##\[group\]Run [\w.-]+/(?:[\w.-]*setup[\w.-]*|checkout|cache|"
                          r"(?:upload|download)-artifact)(?:/[\w./-]*)?@")


def steps(lines: list[str]):
    """Each step that failed: (its script and env, its output), from GitHub's '##[group]Run ...' header to
    its '##[error]Process completed with exit code N', or for a JavaScript action (no exit-code line) to
    its first '##[error]' line, the last line of the output (#260)."""
    header: list[str] = []
    output: list[str] = []
    in_header = False
    for line in lines:
        if STEP_START.match(line):
            header, output, in_header = [line], [], True
        elif in_header:
            header.append(line)
            in_header = line.strip() != "##[endgroup]"
        elif STEP_EXIT.match(line):
            if header:
                yield header, output
            header, output = [], []
        elif header and line.startswith("##[error]") and STEP_ACTION.match(header[0]):
            yield header, output + [line]
            header, output = [], []
        elif header:
            output.append(line)


def step_message(lines: list[str]) -> list[dict]:
    """A failed step's own message (#172): an output line the step's script prints with echo, such as
    black's "Please add '(#5235)' change line to CHANGES.md", or a JavaScript action's '##[error]' (#260)."""
    found = []
    signalled: bool | None = None
    for header, output in steps(lines):
        if STEP_ACTION.match(header[0]):   # core.setFailed(): the action's own '##[error]' line (#260)
            said = output[-1].removeprefix("##[error]").strip() if output else ""
            if not said or SETUP_ACTION.match(header[0]) or LINK_STATUS.match(said):
                continue
            if signalled is None:   # a sign of trouble outside the code explains the action's error
                signalled = any(pattern.search(line) for line in lines for _, pattern in SIGNALS)
            if not signalled:
                found.append(_failure("step", "check", message=said))
            continue
        echoed = [m.group(2).split("$")[0].strip() for line in header for m in ECHO.finditer(line)]
        echoed = [e for e in echoed if len(e) >= 10]
        said = [line.strip() for line in output
                if not line.startswith("##[") and any(line.strip().startswith(e) for e in echoed)]
        if said:
            found.append(_failure("step", "check", message=said[-1]))
    return found


CONFLICT = re.compile(r"^CONFLICT \([\w/ -]+\): .*?(?:Merge conflict in|in) (\S+)$")
MERGE_REF = re.compile(r"^\s*git (?:merge|rebase|pull)\b.*?\s(?:origin/)?([\w][\w./-]*)\s*$")


def merge_conflict(lines: list[str]) -> list[dict]:
    """A branch that does not merge into its base (#173): one failure per conflicting file, its test
    'merge into <base>' when the step's 'git merge origin/<base>' is in the log."""
    base = next((m.group(1) for line in lines if (m := MERGE_REF.match(line))), "")
    found = []
    for line in lines:
        if (m := CONFLICT.match(line.strip())) and SAFE_PATH.match(m.group(1)):
            found.append(_failure("git", "merge", f"merge into {base}" if base else "merge",
                                  m.group(1), message=line.strip()))
    return found


GIT_DIFF_CHECK = re.compile(r"\bgit diff\b.*--(?:exit-code|quiet)\b")
SAFE_COMMAND = re.compile(r"^[\w ./=:+-]+$")   # shown as advice to run: nothing else gets through


def generated(lines: list[str]) -> list[dict]:
    """Generated files out of date (#174): a step whose script ends in `git diff --exit-code` printed a diff;
    the test is the script's other lines, the command that regenerates them, when it is plain."""
    found = []
    for header, output in steps(lines):
        script = []
        for line in header[1:]:
            if line.startswith("shell: ") or line.strip() == "##[endgroup]":
                break
            script.append(line.strip())
        if not any(GIT_DIFF_CHECK.search(line) for line in script):
            continue
        redo = [line for line in script if line and not GIT_DIFF_CHECK.search(line)]
        command = " && ".join(redo) if redo and all(SAFE_COMMAND.match(line) for line in redo) else ""
        for line in output:
            if (m := DIFF_FILE.match(line.strip())) and SAFE_PATH.match(m.group(1)):
                found.append(_failure("generated", "generated", command, m.group(1),
                                      message="generated file out of date"))
    return found


TSTYCHE_FILE = re.compile(r"^(fail|pass)\s+\.?/?(\S+\.tst\.[cm]?tsx?)\s*$")
TSTYCHE_ERROR = re.compile(r"^Error: (.+)$")
TSTYCHE_AT = re.compile(r"^\s*at \.?/?(\S+\.[cm]?tsx?):(\d+):\d+\s*$")
TSD_FILE = re.compile(r"^\s*(\S+\.test-d\.[cm]?tsx?)\s*$")
TSD_ERROR = re.compile(r"^\s*✖\s+(\d+):\d+\s+(.+?)\s*$")


def type_tests(lines: list[str]) -> list[dict]:
    """TypeScript type tests (#258): tstyche's 'Error: <message>' with the 'at ./x.tst.ts:L:C' after it, under
    a 'fail <file>' header; tsd's '✖  L:C  <message>' under its '<file>.test-d.ts' header."""
    found: list[dict] = []
    in_tstyche, message, tsd_file = False, "", ""
    for line in lines:
        if m := TSTYCHE_FILE.match(line.strip()):
            in_tstyche, message = m.group(1) == "fail", ""
        elif in_tstyche and (m := TSTYCHE_ERROR.match(line.strip())):
            message = m.group(1)
        elif in_tstyche and message and (m := TSTYCHE_AT.match(line)):
            found.append(_failure("tstyche", "tests", file=m.group(1), line=int(m.group(2)), message=message))
            message = ""
        elif m := TSD_FILE.match(line):
            tsd_file = m.group(1)
        elif tsd_file and (m := TSD_ERROR.match(line)):
            found.append(_failure("tsd", "tests", file=tsd_file, line=int(m.group(1)), message=m.group(2)))
    return [f for f in found if SAFE_PATH.match(f["file"])]


COVERAGE_UNMET = re.compile(
    r"(Coverage for (?:lines|branches|functions|statements) \([\d.]+%\) does not meet (?:global )?threshold"
    r" \([\d.]+%\)"                                                       # c8, nyc
    r"|coverage threshold for (?:lines|branches|functions|statements) \([\d.]+%\) not met: [\d.]+%"   # jest
    r"|Required test coverage of [\d.]+% not reached\. Total coverage: [\d.]+%)")              # pytest-cov
COVERAGE_ROW = re.compile(r"^( *)([^|]*?\S)\s*\|((?:\s*[\d.]+\s*\|){4})\s*(\S*)\s*$")
COVERAGE_LINE = re.compile(r"^(?:\.\.\.\d*-)?(\d+)")
CHECKOUT_NAME = re.compile(r"(?:/work|\b[A-Za-z]:/a)/([^/\s]+)/\1(?:/|\s|$)")


def coverage(lines: list[str]) -> list[dict]:
    """A coverage threshold that is not met (#257): one failure per file the table shows below 100%, at its
    first uncovered line; one without a place when there is no table (pytest-cov)."""
    unmet = next((m.group(1) for line in lines if (m := COVERAGE_UNMET.search(line))), "")
    if not unmet:
        return []
    found: list[dict] = []
    folders: dict[int, str] = {}
    # c8 names folders from the checkout's own folder ("fastify/lib"): that name is dropped.
    checkout = next((m.group(1) for line in lines
                     if (m := CHECKOUT_NAME.search(line.replace("\\", "/")))), "")
    for line in lines:
        if not (m := COVERAGE_ROW.match(line)) or m.group(2) in ("All files", "File"):
            continue
        depth, name = len(m.group(1)), m.group(2).strip()
        if "." not in name.rsplit("/", 1)[-1]:   # a folder
            folders = {d: f for d, f in folders.items() if d < depth}
            first, _, rest = name.partition("/")
            folders[depth] = rest if checkout and first == checkout else name
            continue
        percents = [float(p) for p in m.group(3).replace("|", " ").split()]
        if min(percents) >= 100:
            continue
        folder = next((folders[d] for d in sorted(folders, reverse=True) if d < depth), "")
        file = f"{folder}/{name}" if folder else name
        first = COVERAGE_LINE.match(m.group(4) or "")
        if SAFE_PATH.match(file):
            found.append(_failure("coverage", "coverage", file, file, int(first.group(1)) if first else 0,
                                  unmet))
    return found or [_failure("coverage", "coverage", "coverage", message=unmet)]


NODE_BLOCK = re.compile(r"^✖ failing tests:\s*$")
NODE_AT = re.compile(r"^test at (\S+?):(\d+):\d+\s*$")
NODE_FAIL = re.compile(r"^\s*✖ (.+?) \(\d+(?:\.\d+)?m?s\)\s*$")
NODE_FRAME = re.compile(r"\(?(?:file://)?([^\s()]+?\.[cm]?[jt]sx?):(\d+):\d+\)?\s*$")
NODE_SUBTESTS = re.compile(r"^'?\d+ subtests? failed'?$")
BORP_FAILED = re.compile(r"^failed: (\S.*?\.[cm]?[jt]sx?) \([\d,.]+ ?m?s\)\s*$")


def _checkout_path(path: str) -> str:
    return CHECKOUT.sub("", path.replace("\\", "/"))


def _node_place(body: list[str], file: str, number: int) -> tuple[str, int]:
    """The first frame of the checkout, in the test's own file when there is one."""
    places = []
    for line in body:
        if (m := NODE_FRAME.search(line.replace("\\", "/"))) and not FOREIGN.search(m.group(1)):
            places.append((_checkout_path(m.group(1)), int(m.group(2))))
    same = [p for p in places if file and p[0] == file]
    return (same or [(file, number)] if file else places or [("", 0)])[0]


def node_test(lines: list[str]) -> list[dict]:
    """Node's built-in test runner (#251): each test of its '✖ failing tests:' block, with its message and
    the frame in its file; else borp's 'failed: <file>' lines, placed by the frame in that file."""
    found: list[dict] = []
    start = next((i for i, line in enumerate(lines) if NODE_BLOCK.match(line.strip())), -1)
    if start >= 0:
        at: tuple[str, int] = ("", 0)
        entry: dict | None = None
        body: list[str] = []

        def close():
            if entry is not None and not NODE_SUBTESTS.match(entry["message"]):
                entry["file"], entry["line"] = _node_place(body, *at)
                found.append(entry)

        for line in lines[start + 1:]:
            if line.startswith("##["):
                break
            if m := NODE_AT.match(line.strip()):
                close()
                entry, body, at = None, [], (_checkout_path(m.group(1)), int(m.group(2)))
            elif (m := NODE_FAIL.match(line)) and not line.startswith("    "):
                close()
                name = m.group(1)
                if "/" in name or "\\" in name:   # a file that failed as a whole
                    name = _checkout_path(name)
                entry, body = _failure("node:test", "tests", name), []
            elif entry is not None:
                body.append(line)
                if not entry["message"] and line.strip():
                    entry["message"] = _short(line.strip())
        close()
        if found:
            return found
    for i, line in enumerate(lines):
        if not (m := BORP_FAILED.match(line.strip())):
            continue
        file = _checkout_path(m.group(1))
        after = lines[i + 1:i + 400]
        message = next((x[len("##[error]"):].strip() for x in after
                        if x.startswith("##[error]") and "Process completed with exit code" not in x), "")
        found.append(_failure("borp", "tests", file, file, _node_place(after, file, 0)[1],
                              message or "failed"))
    return found


MARKDOWNLINT = re.compile(r"^(?:##\[(?:error|warning)\])?(\S+\.(?:md|markdown)):(\d+)(?::\d+)?\s+"
                          r"(?:error\s+)?(MD\d{3}(?:/[\w/-]+)?)\s+(.+)$")
LYCHEE_PAGE = re.compile(r"^#{2,4} Errors in (\S+)\s*$")
LYCHEE_LINK = re.compile(r"^\* \[(ERROR|\d{3})\] <(\S+)> \| (.+)$")
LINKINATOR = re.compile(r"^(?:##\[error\])?\s*\[(\d{3})\] (\S+) - HTTP \d{3}\s*$")
# A link that is gone or a page that is missing is the docs' own; a site that is down or slow is not (#254).
GONE = ("404", "410")


def _link(url: str) -> str:
    """A link as the docs have it: a local file:// link relative to the checkout."""
    return CHECKOUT.sub("", url.removeprefix("file://")) if url.startswith("file://") else url


def doc_checks(lines: list[str]) -> list[dict]:
    """Documentation checks (#259): markdownlint's 'file.md:L:C [error] MDxxx/rule message', lychee's broken
    links under '### Errors in <page>', linkinator's '[404] <url> - HTTP 404'."""
    found: list[dict] = []
    page = ""
    for line in lines:
        bare = line.strip()
        if m := MARKDOWNLINT.match(bare):
            if SAFE_PATH.match(m.group(1)):
                found.append(_failure("markdownlint", "lint", m.group(3), m.group(1), int(m.group(2)),
                                      m.group(4)))
        elif m := LYCHEE_PAGE.match(bare):
            page = m.group(1) if SAFE_PATH.match(m.group(1)) else ""
        elif (m := LYCHEE_LINK.match(bare)) and page:
            status, message = m.group(1), m.group(3)
            if status in GONE or (status == "ERROR" and message.startswith("Cannot find file")):
                found.append(_failure("lychee", "links", _link(m.group(2)), page, message=message))
        elif (m := LINKINATOR.match(bare)) and m.group(1) in GONE:
            found.append(_failure("linkinator", "links", m.group(2), message=bare.removeprefix("##[error]")))
    return found


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


# A test runner's own time limit for one test (#253): node:test, jest, pytest-timeout.
TEST_TIMEOUT = re.compile(r"test timed out after \d|Exceeded timeout of \d|^(?:Failed: )?Timeout >\s?\d")


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
        bare = MATCHER.sub("", line)   # the lint parsers' line, without a problem matcher's prefix
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
        elif m := MYPY.match(bare):
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
        elif m := TSC.match(bare):
            found.append(_failure("tsc", "build", m.group(4), m.group(1), int(m.group(2) or m.group(3)),
                                  m.group(5)))
        elif m := RUFF.match(bare):
            found.append(_failure("ruff", "lint", m.group(3), m.group(1), int(m.group(2)), m.group(4)))
        elif m := RUFF_CODE.match(line):
            ruff_code = line
        elif (m := RUFF_ARROW.match(line)) and ruff_code:
            code, _, message = ruff_code.partition(" ")
            found.append(_failure("ruff", "lint", code, m.group(1), int(m.group(2)), message))
            ruff_code = ""
        elif m := ESLINT_FILE.match(line):
            eslint_file = CHECKOUT.sub("", m.group(1).replace("\\", "/"))
        elif (m := ESLINT.match(bare)) and eslint_file:
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
    found += pre_commit(lines)
    found += conftest(lines)
    found += formatter(lines)
    found += merge_conflict(lines)
    found += generated(lines)
    found += playwright(lines)
    found += type_tests(lines)
    found += coverage(lines)
    found += node_test(lines)
    found += doc_checks(lines)
    for block in junit_blocks(lines):
        found += junit_xml(block)
    if not found:   # nothing a tool reports: the step's own words, when its script printed them
        found += step_message(lines)
    if not found and (crashed := crash(lines)):
        found.append(crashed)  # the tests stopped with the process; nothing else names the failure
    seen, unique = set(), []
    for f in found:
        if TEST_TIMEOUT.search(f["message"]):
            f["timeout"] = True
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


PY_FRAME = re.compile(r'^\s*File "([^"<>]+)", line (\d+)')
PY_RAISED = re.compile(r"^([A-Za-z_][\w.]*(?:Error|Exception)): (.*)$")
CI_HELPER = re.compile(r"(?:^|/)(?:\.github|scripts)/(\S+)$")
RUNNER_CHECKOUT = re.compile(r"^(?:.*?/work/[^/]+/[^/]+/|[A-Za-z]:/a/[^/]+/[^/]+/)")


def helper_crash(lines: list[str]) -> str:
    """A CI helper script (scripts/, .github/) that crashed: 'scripts/x.py:98: ValueError: ...' when the
    traceback's innermost frame of the checkout is in one (#176), else ''."""
    last = ""
    for line in lines:
        if (m := PY_FRAME.match(line)) and not FOREIGN.search(m.group(1)):
            path = RUNNER_CHECKOUT.sub("", m.group(1).replace("\\", "/"))
            last = f"{path}:{m.group(2)}" if CI_HELPER.search(path) else ""
        elif (m := PY_RAISED.match(line.strip())) and last:
            return _short(f"{last}: {m.group(1)}: {m.group(2)}", 200)
    return ""


# A test runner's pass line names a test that passed (#252): "✔ ignores ECONNRESET (19ms)" is no signal.
PASS_LINE = re.compile(r"^\s*(?:✔|✓|√|ok \d+\b|PASS\b|passed: )|\sPASSED(?:\s|$)")


def signals(lines: list[str]) -> list[dict]:
    found = []
    lines = [line for line in lines if not PASS_LINE.search(line)]
    for kind, pattern in SIGNALS:
        hit = next((line for line in lines if pattern.search(line)), None)
        if hit is None and kind == "setup":
            hit = helper_crash(lines) or None
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


WARNING_RAISED = re.compile(r"^E\s+(\w*Warning): (.*)$")
TB_PLACE = re.compile(r'^(\S+\.py):(\d+): in |^\s*File "([^"]+)", line (\d+)')
PACKAGE = re.compile(r"(?:site|dist)-packages/([A-Za-z_]\w*)")


def upstream(lines: list[str]) -> list[dict]:
    """Warnings made errors inside a dependency's code: pytest's 'E   DeprecationWarning: ...' right after
    a frame in site-packages/<package>/ (#133). Only warnings: an assertion or a TypeError raised inside a
    library is usually the caller's mistake."""
    found: list[dict] = []
    place = ""
    for line in lines:
        if m := TB_PLACE.match(line):
            place = f"{m.group(1) or m.group(3)}:{m.group(2) or m.group(4)}"
        elif (m := WARNING_RAISED.match(line)) and (pkg := PACKAGE.search(place)):
            item = {"package": pkg.group(1), "place": place[pkg.start(1):], "warning": m.group(1),
                    "message": _short(m.group(2))}
            if item not in found:
                found.append(item)
            place = ""
    return found[:10]


NODE_ERROR = re.compile(r"^\s*([A-Z]\w*Error)(?: \[[\w-]+\])?: (.+)$")
NODE_MODULE_FRAME = re.compile(r"^\s*at .*node_modules/((?:@[\w.-]+/)?[\w.-]+)/(\S+?:\d+)")


def raised(lines: list[str]) -> list[dict]:
    """JavaScript errors whose innermost frame is inside node_modules/<package>/ (#261): a crash in a
    dependency's own code. Not an assertion: an assertion library throws what the test asked it to."""
    found: list[dict] = []
    for i, line in enumerate(lines[:-1]):
        if not (m := NODE_ERROR.match(line)) or "Assertion" in m.group(1):
            continue
        if frame := NODE_MODULE_FRAME.match(lines[i + 1].replace("\\", "/")):
            item = {"package": frame.group(1), "place": f"{frame.group(1)}/{frame.group(2)}",
                    "error": m.group(1), "message": _short(m.group(2))}
            if item not in found:
                found.append(item)
    return found[:10]


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
    """{job: {failures, signals, errors, frames, missing, upstream, raised, lines}} for each job in a failed
    log."""
    out = {}
    for job, lines in split_jobs(text).items():
        out[job] = {"failures": failures(lines), "signals": signals(lines), "errors": errors(lines),
                    "frames": frames(lines), "missing": missing_modules(lines),
                    "upstream": upstream(lines), "raised": raised(lines), "lines": lines}
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
