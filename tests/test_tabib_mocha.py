"""tabib reads mocha (#360): the spec and dot reporters' "N failing" block, and the TAP reporter."""
from __future__ import annotations

import sys

from conftest import PLUGINS

TABIB_ROOT = PLUGINS / "tabib"
if str(TABIB_ROOT) not in sys.path:
    sys.path.insert(0, str(TABIB_ROOT))

from tabib import compare, parse  # noqa: E402


def gh_log(job: str, lines: list[str]) -> str:
    return "\n".join(f"{job}\tRun tests\t2026-10-06T07:17:41.0737615Z {line}" for line in lines)


def read(lines: list[str], job: str = "Node.js 20 - ubuntu-latest") -> list[dict]:
    return parse.read_log(gh_log(job, lines))[job]["failures"]


def places(failures: list[dict]) -> list[tuple]:
    return [(f["framework"], f["kind"], f["test"], f["file"], f["line"]) for f in failures]


# The spec reporter (mocha's default), as express prints it: a passing test, a failing one marked inline
# with its number, a pending one, then the summary and the "N failing" block with a test and a hook.
SPEC_LOG = [
    "> mocha --require test/support/env --reporter spec --check-leaks test/ test/acceptance/",
    "",
    "  req",
    "    .acceptsEncodings(encoding)",
    "      ✔ should be true if encoding accepted",
    "      1) should accept any encoding when Accept-Encoding is not present",
    "      - should be skipped for now",
    "",
    "  app.router",
    "    2) \"before each\" hook for \"should route\"",
    "",
    "  1267 passing (3s)",
    "  2 pending",
    "  2 failing",
    "",
    "  1) req",
    "       .acceptsEncodings(encoding)",
    "         should accept any encoding when Accept-Encoding is not present:",
    "",
    "      Error: expected { bogus: 'bogus' } response body, got { bogus: false }",
    "      + expected - actual",
    "",
    "      at Context.<anonymous> (test/req.acceptsEncodings.js:50:10)",
    "      at process.processImmediate (node:internal/timers:483:21)",
    "  ----",
    "      at error (node_modules/supertest/lib/test.js:335:15)",
    "      at /home/runner/work/express/express/node_modules/supertest/lib/test.js:308:13",
    "",
    "  2) app.router",
    "       \"before each\" hook for \"should route\":",
    "     TypeError: Cannot read properties of undefined (reading 'get')",
    "      at Context.<anonymous> (D:\\a\\express\\express\\test\\app.router.js:12:7)",
    "",
    "##[error]Process completed with exit code 2.",
]


def test_mocha_spec_failures_are_read():
    failures = read(SPEC_LOG)
    assert places(failures) == [
        ("mocha", "tests", "req > .acceptsEncodings(encoding) > should accept any encoding when "
         "Accept-Encoding is not present", "test/req.acceptsEncodings.js", 50),
        ("mocha", "tests", 'app.router > "before each" hook for "should route"', "test/app.router.js", 12)]
    assert failures[0]["message"] == "Error: expected { bogus: 'bogus' } response body, got { bogus: false }"
    assert failures[1]["message"].startswith("TypeError: Cannot read properties of undefined")


def test_mocha_with_only_passes_and_pending_has_no_failure():
    lines = ["  req", "    ✔ should be true (5ms)", "    - should be skipped", "",
             "  1267 passing (3s)", "  2 pending"]
    assert read(lines) == []


def test_mocha_uncaught_error_and_windows_frame():
    # express run 37953351037: an uncaught assertion, the frame with Windows separators
    lines = ["  1 failing", "",
             "  1) node:http pass-through",
             "       res",
             "         should support res.writeEarlyHints():",
             "",
             "      Uncaught AssertionError [ERR_ASSERTION]: Expected values to be strictly equal:",
             "      ",
             "      at IncomingMessage.<anonymous> (test\\http.native.js:172:20)",
             "      at IncomingMessage.emit (node:events:525:35)"]
    failures = read(lines, "Node.js 16 - windows-latest")
    assert places(failures) == [("mocha", "tests", "node:http pass-through > res > should support "
                                 "res.writeEarlyHints()", "test/http.native.js", 172)]
    assert failures[0]["message"] == "AssertionError [ERR_ASSERTION]: Expected values to be strictly equal:"


def test_old_mocha_one_line_title_with_only_library_frames():
    # express run 34755690134, Node 0.10: the title on one line, no frame in the project
    lines = ["  723 passing (2s)", "  24 pending", "  1 failing", "",
             "  1) res .clearCookie(name, options) should set both maxAge and expires when passed:",
             "     Error: expected \"Set-Cookie\" of \"a\", got \"b\"",
             "      at Test._assertHeader (node_modules\\supertest\\lib\\test.js:231:12)",
             "      at net.js:1277:10", "", "", "npm ERR! Test failed.  See above for more details."]
    assert places(read(lines)) == [
        ("mocha", "tests", "res .clearCookie(name, options) should set both maxAge and expires when passed",
         "", 0)]


def test_mocha_message_lines_outside_the_indent_do_not_end_the_failure():
    # express run 37953351037, whole log: assert's diff starts at column 0, the stack comes after it
    lines = ["  1 failing", "",
             "  1) node:http pass-through", "       res",
             "         should support res.writeEarlyHints():", "",
             "      Uncaught AssertionError [ERR_ASSERTION]: Expected values to be strictly equal:", "",
             "false !== true", "", "      + expected - actual", "",
             "      at IncomingMessage.<anonymous> (test/http.native.js:172:20)", "", "",
             "-----------------|---------|----------|", "File             | % Stmts | % Branch |",
             "      at Server.x (test/other.js:9:1)"]
    assert [(f["file"], f["line"]) for f in read(lines)] == [("test/http.native.js", 172)]


def test_a_colon_line_followed_by_an_error_is_not_mocha_without_a_mocha_entry():
    lines = ["  Traceback details follow:", "", "    Error: something broke"]
    assert [f for f in parse.failures(lines) if f["framework"] == "mocha"] == []


def test_mocha_dot_reporter_failures_are_read():
    lines = ["  ․․․․․․!․․․", "", "  9 passing (40ms)", "  1 failing", "",
             "  1) Array", "       #indexOf()", "         should return -1 when not present:",
             "     AssertionError [ERR_ASSERTION]: 0 == -1",
             "      at Context.<anonymous> (test/array.spec.js:8:14)"]
    assert places(read(lines)) == [
        ("mocha", "tests", "Array > #indexOf() > should return -1 when not present", "test/array.spec.js", 8)]


def test_mocha_tap_reporter_failures_are_read():
    lines = ["1..3", "ok 1 Array #indexOf() should return the index",
             "not ok 2 Array #indexOf() should return -1 when not present",
             "  AssertionError [ERR_ASSERTION]: 0 == -1",
             "      at Context.<anonymous> (test/array.spec.js:8:14)",
             "      at process.processImmediate (node:internal/timers:483:21)",
             "ok 3 Array #push() should be skipped # SKIP -",
             "# tests 2", "# pass 1", "# fail 1"]
    failures = read(lines)
    assert places(failures) == [("mocha", "tests", "Array #indexOf() should return -1 when not present",
                                 "test/array.spec.js", 8)]
    assert failures[0]["message"] == "AssertionError [ERR_ASSERTION]: 0 == -1"


def test_node_test_tap_is_not_read_as_mocha():
    # node:test's TAP names a test after " - " and gives YAML: not mocha's
    lines = ["TAP version 13", "# Subtest: adds", "not ok 1 - adds", "  ---", "  duration_ms: 1.2",
             "  failureType: 'testCodeFailure'", "  ...", "1..1", "# fail 1"]
    assert [f for f in parse.failures(lines) if f["framework"] == "mocha"] == []


def test_mocha_is_a_node_framework_for_dependency_changes():
    assert compare.deps_changed(["package-lock.json", "uv.lock"], "mocha") == ["package-lock.json"]
