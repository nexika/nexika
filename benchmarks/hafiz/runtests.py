#!/usr/bin/env python3
"""Run a work repo's own tests, and optionally a task's hidden checks, and print one JSON line.

    python3 runtests.py <repo> [--hidden tasks/<task>/hidden_test.py]

Output: {"tests": {"<test id>": "pass" | "fail" | "error" | "skip"}, "load_errors": [...]}. The repo's
tests come from unittest discovery in <repo>/tests; the hidden checks load as the module "hidden", so
their ids start with "hidden.". bench.py runs this in a subprocess with a time limit, because the code
under test is whatever the agent wrote.
"""
from __future__ import annotations

import argparse
import importlib.util
import io
import json
import os
import sys
import unittest


class _Result(unittest.TestResult):
    def __init__(self):
        super().__init__()
        self.outcomes = {}

    def addSuccess(self, test):
        self.outcomes[test.id()] = "pass"

    def addFailure(self, test, err):
        super().addFailure(test, err)
        self.outcomes[test.id()] = "fail"

    def addError(self, test, err):
        super().addError(test, err)
        self.outcomes[test.id()] = "error"

    def addSkip(self, test, reason):
        self.outcomes[test.id()] = "skip"

    def addExpectedFailure(self, test, err):
        self.outcomes[test.id()] = "fail"

    def addUnexpectedSuccess(self, test):
        self.outcomes[test.id()] = "pass"


def _load_errors(suite, out):
    """Discovery turns a module that does not import into a _FailedTest: record it by name."""
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            _load_errors(item, out)
        elif type(item).__name__ == "_FailedTest":
            out.append(item.id())


def collect(repo: str, hidden: str | None) -> dict:
    os.chdir(repo)
    sys.path.insert(0, repo)
    suite = unittest.TestSuite()
    load_errors: list[str] = []
    if os.path.isdir(os.path.join(repo, "tests")):
        found = unittest.defaultTestLoader.discover(os.path.join(repo, "tests"), top_level_dir=repo)
        _load_errors(found, load_errors)
        suite.addTests(found)
    if hidden:
        spec = importlib.util.spec_from_file_location("hidden", hidden)
        module = importlib.util.module_from_spec(spec)
        sys.modules["hidden"] = module
        try:
            spec.loader.exec_module(module)
            suite.addTests(unittest.defaultTestLoader.loadTestsFromModule(module))
        except Exception as exc:  # the hidden checks import the agent's code
            load_errors.append(f"hidden: {type(exc).__name__}: {exc}")
    result = _Result()
    quiet = io.StringIO()
    stdout, stderr = sys.stdout, sys.stderr
    sys.stdout = sys.stderr = quiet
    try:
        suite.run(result)
    finally:
        sys.stdout, sys.stderr = stdout, stderr
    return {"tests": dict(sorted(result.outcomes.items())), "load_errors": load_errors}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("repo")
    parser.add_argument("--hidden")
    args = parser.parse_args(argv)
    hidden = os.path.abspath(args.hidden) if args.hidden else None
    print(json.dumps(collect(os.path.abspath(args.repo), hidden)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
