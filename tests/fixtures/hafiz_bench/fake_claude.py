#!/usr/bin/env python3
"""A scripted stand-in for `claude -p` on the hafiz benchmark's export task, for offline tests.

It edits the work repo the way an agent would at each call and prints stream-json events in the
shape Claude Code prints them. FAKE_SCENARIO picks the behaviour after the compaction:

    good    does step 4 and fixes format_price; touches nothing finished
    bad     rewrites shelf/export.py whole with pandas, and "fixes" the deferred test by editing it
    nocompact   like good, but /compact does not compact
"""
import json
import os
import sys
from pathlib import Path

EXPORT_CSV = '''"""Write the catalog to other formats."""

import csv
import json

from .catalog import FIELDS


def export_csv(books, path):
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(books)
'''

EXPORT_JSON = '''

def export_json(books, path):
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(books, handle, ensure_ascii=False, indent=1)
'''

EXPORT_PANDAS = '''"""Write the catalog to other formats."""

import pandas


def export_csv(books, path):
    pandas.DataFrame(books).to_csv(path, index=False)


def export_json(books, path):
    pandas.DataFrame(books).to_json(path, orient="records")
'''

CLI_OLD = '''    listing.set_defaults(handler=cmd_list)
'''
CLI_EXPORT = '''    listing.set_defaults(handler=cmd_list)
    exporting = commands.add_parser("export", help="write a catalog as csv")
    exporting.add_argument("catalog")
    exporting.add_argument("out")
    exporting.set_defaults(handler=cmd_export)
'''
CMD_EXPORT = '''

def cmd_export(args):
    from .export import export_csv

    export_csv(load_catalog(args.catalog), args.out)
    return 0
'''
CMD_EXPORT_FORMAT = '''

def cmd_export(args):
    from .export import export_csv, export_json

    writer = export_json if args.format == "json" else export_csv
    writer(load_catalog(args.catalog), args.out)
    return 0
'''

LOAD_OLD = '''    books = []
    with open(path, encoding="utf-8") as handle:
'''
LOAD_CSV = '''    if str(path).endswith(".csv"):
        import csv

        with open(path, newline="", encoding="utf-8") as handle:
            books = [dict(row) for row in csv.DictReader(handle)]
        for book in books:
            book["year"] = int(book["year"])
            book["price_cents"] = int(book["price_cents"])
        return books
    books = []
    with open(path, encoding="utf-8") as handle:
'''


def emit(event):
    print(json.dumps(event), flush=True)


def edit(repo, rel, old, new, tools):
    path = repo / rel
    text = path.read_text(encoding="utf-8")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    tools.append({"type": "tool_use", "name": "Edit", "input": {"file_path": str(path)}})


def write(repo, rel, text, tools):
    path = repo / rel
    path.write_text(text, encoding="utf-8")
    tools.append({"type": "tool_use", "name": "Write", "input": {"file_path": str(path)}})


def main(argv):
    prompt = argv[argv.index("-p") + 1]
    flag = "--session-id" if "--session-id" in argv else "--resume"
    session = argv[argv.index(flag) + 1]
    hafiz = "--plugin-dir" in argv
    scenario = os.environ.get("FAKE_SCENARIO", "good")
    repo = Path.cwd()
    emit({"type": "system", "subtype": "init", "session_id": session, "model": "fake",
          "plugins": [{"name": "hafiz", "path": "x"}] if hafiz else []})
    if hafiz:
        name = "SessionStart:startup" if "--session-id" in argv else "SessionStart:resume"
        emit({"type": "system", "subtype": "hook_response", "hook_name": name, "hook_event": "SessionStart",
              "output": json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart",
                                                           "additionalContext": "hafiz card " * 10}}),
              "exit_code": 0, "outcome": "success"})
    tools = []
    if prompt == "/compact":
        if scenario != "nocompact":
            emit({"type": "system", "subtype": "compact_boundary",
                  "compact_metadata": {"trigger": "manual", "pre_tokens": 30000}})
            if hafiz:
                emit({"type": "system", "subtype": "hook_response", "hook_name": "SessionStart:compact",
                      "hook_event": "SessionStart",
                      "output": json.dumps({"hookSpecificOutput": {
                          "hookEventName": "SessionStart", "additionalContext": "R" * 900}}),
                      "exit_code": 0, "outcome": "success"})
    elif prompt.startswith("Here is the plan"):
        write(repo, "shelf/export.py", EXPORT_CSV, tools)
    elif "step 2" in prompt:
        edit(repo, "shelf/cli.py", CLI_OLD, CLI_EXPORT, tools)
        (repo / "shelf/cli.py").write_text((repo / "shelf/cli.py").read_text() + CMD_EXPORT)
    elif "step 3" in prompt:
        rows = "writer.writerows(books)\n"
        edit(repo, "shelf/export.py", rows, rows + EXPORT_JSON, tools)
        out = '    exporting.add_argument("out")\n'
        option = '    exporting.add_argument("--format", default="csv")\n'
        edit(repo, "shelf/cli.py", out, out + option, tools)
        edit(repo, "shelf/cli.py", CMD_EXPORT, CMD_EXPORT_FORMAT, tools)
    elif scenario == "bad":
        write(repo, "shelf/export.py", EXPORT_PANDAS, tools)
        edit(repo, "tests/test_money.py", '"12.50 EUR"', '"12.5 EUR"', tools)
    else:
        edit(repo, "shelf/catalog.py", LOAD_OLD, LOAD_CSV, tools)
        edit(repo, "shelf/money.py", 'f"{cents / 100} {currency}"',
             'f"{\'-\' if cents < 0 else \'\'}{abs(cents) // 100}.{abs(cents) % 100:02d} {currency}"', tools)
    if prompt != "/compact":
        emit({"type": "assistant", "message": {
            "content": tools, "usage": {"input_tokens": 5, "cache_read_input_tokens": 20000,
                                        "cache_creation_input_tokens": 1000, "output_tokens": 300}}})
    emit({"type": "result", "subtype": "success", "is_error": False, "result": "done",
          "total_cost_usd": 0.05, "num_turns": 3,
          "usage": {"input_tokens": 10, "output_tokens": 600, "cache_read_input_tokens": 40000,
                    "cache_creation_input_tokens": 2000}})
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
