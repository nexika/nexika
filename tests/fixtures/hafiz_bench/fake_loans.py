"""The scripted stand-in for `claude -p` on the hafiz benchmark's loans tasks (v2), for offline tests.

fake_claude.py hands over here when the work repo has data/loans.tsv. Each call works out which
plan steps the prompt asks for, writes shelf/loans.py and shelf/cli.py for every step done so far,
and prints stream-json events in the shape Claude Code prints them. It keeps what it did in
$HOME/.fake-claude.json, inside the run's throwaway home, and writes a transcript per session
under $HOME/.claude/projects like Claude Code.

FAKE_SCENARIO picks the behaviour:

    good          every step as planned, every decision kept
    bad           after the first break (a /compact or a new session) it forgets the decisions (fines
                  without the free days and the cap, lower() for member names, ISO dates), rewrites
                  the finished overdue() from scratch, copies load_loans() as read_loans(), and
                  "fixes" the deferred test by editing it
    stuck         like good, but a new session reports the first session's id (it was resumed)
    quietcompact  like good, but /compact prints no compact_boundary; only the transcript has it
"""
import json
import os
import re
from pathlib import Path

LOANS_HEAD = '''"""Book loans: who has which book, and until when."""

import datetime

FIELDS = ("isbn", "member", "out", "due")
'''

LOAD_LOANS = '''

def load_loans(path):
    """Every loan in the tab-separated file at path, with out and due as dates."""
    loans = []
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.rstrip("\\n")
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            loan = dict(zip(FIELDS, line.split("\\t"), strict=True))
            loan["out"] = datetime.date.fromisoformat(loan["out"])
            loan["due"] = datetime.date.fromisoformat(loan["due"])
            loans.append(loan)
    return loans
'''

READ_LOANS_COPY = LOAD_LOANS.replace("def load_loans(", "def read_loans(")

OVERDUE = '''

def overdue(loans, today):
    """The loans due before today, the oldest due date first."""
    late = [loan for loan in loans if loan["due"] < today]
    late.sort(key=lambda loan: loan["due"])
    return late
'''

OVERDUE_REWRITTEN = '''

def overdue(loans, today):
    """Rewritten: the loans due before today, the oldest due date first."""
    by_due = sorted(loans, key=lambda item: item["due"])
    return list(filter(lambda item: item["due"] < today, by_due))
'''

DAYS_LATE = '''

def days_late(loan, today):
    """How many days after its due date the loan is on today; 0 when it is not late."""
    return max(0, (today - loan["due"]).days)
'''

FINE = '''

FINE_PER_DAY = 25
FREE_DAYS = 3


def fine_cents(days_late, price_cents):
    """25 cents a day after 3 free days, never more than the book's price."""
    return min(price_cents, FINE_PER_DAY * max(0, days_late - FREE_DAYS))
'''

FINE_FORGOTTEN = '''

def fine_cents(days_late, price_cents):
    """25 cents a day."""
    return 25 * days_late
'''

CLI_HEAD = '''"""The shelf command: python3 -m shelf list data/catalog.tsv"""

import argparse
import sys

from .catalog import load_catalog
from .money import format_price


def cmd_list(args):
    books = load_catalog(args.catalog)
    width = max(len(book["title"]) for book in books)
    for book in books:
        price = format_price(book["price_cents"])
        print(f"{book['title']:<{width}}  {book['author']} ({book['year']})  {price}")
    return 0
'''

CMD_LOANS = '''

def cmd_loans(args):
    from .loans import load_loans

    for loan in load_loans(args.loans):
{filter}        print(f"{{loan['isbn']}}  {{loan['member']}}  due {{loan['due']{date}}}")
    return 0
'''

MEMBER_FILTER = '''        if args.member and args.member.{fold}() not in loan["member"].{fold}():
            continue
'''

CMD_OVERDUE = '''

def cmd_overdue(args):
    import datetime

    from .loans import days_late, fine_cents, load_loans, overdue

    books = {{book["isbn"]: book for book in load_catalog(args.catalog)}}
    today = datetime.date.fromisoformat(args.today)
    for loan in overdue(load_loans(args.loans), today):
        book = books[loan["isbn"]]
        fine = fine_cents(days_late(loan, today), book["price_cents"])
        print(f"{{book['title']}}  {{loan['member']}}  due {{loan['due']{date}}}  {{format_price(fine)}}")
    return 0
'''

PARSER_HEAD = '''

def build_parser():
    parser = argparse.ArgumentParser(prog="shelf")
    commands = parser.add_subparsers(dest="command", required=True)
    listing = commands.add_parser("list", help="list every book in a catalog")
    listing.add_argument("catalog")
    listing.set_defaults(handler=cmd_list)
'''

PARSER_LOANS = '''    loans = commands.add_parser("loans", help="list the loans")
    loans.add_argument("loans")
{member}    loans.set_defaults(handler=cmd_loans)
'''

PARSER_OVERDUE = '''    late = commands.add_parser("overdue", help="the overdue loans and their fines")
    late.add_argument("catalog")
    late.add_argument("loans")
    late.add_argument("--today", required=True)
    late.set_defaults(handler=cmd_overdue)
'''

CLI_TAIL = '''    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    return args.handler(args)


if __name__ == "__main__":
    sys.exit(main())
'''

GOOD_DATE, ISO_DATE = ":%d.%m.%Y", ""
FIXED_PRICE = 'f"{\'-\' if cents < 0 else \'\'}{abs(cents) // 100}.{abs(cents) % 100:02d} {currency}"'


def emit(event):
    print(json.dumps(event, ensure_ascii=False), flush=True)


def loans_source(done, forgot, at):
    """shelf/loans.py for the steps done; `forgot`: which steps were done after the first break."""
    text = LOANS_HEAD
    if 1 in done:
        text += LOAD_LOANS
    if 2 in done:
        text += OVERDUE_REWRITTEN if at else OVERDUE
    if 4 in done:
        text += DAYS_LATE
    if 5 in done:
        text += FINE_FORGOTTEN if 5 in forgot else FINE
    if at:
        text += READ_LOANS_COPY
    return text


def cli_source(done, forgot):
    text = CLI_HEAD
    parser = PARSER_HEAD
    if 3 in done:
        fold = "lower" if 7 in forgot else "casefold"
        member = MEMBER_FILTER.format(fold=fold) if 7 in done else ""
        date = ISO_DATE if 3 in forgot else GOOD_DATE
        text += CMD_LOANS.format(filter=member, date=date)
        parser += PARSER_LOANS.format(member='    loans.add_argument("--member")\n' if 7 in done else "")
    if 6 in done:
        text += CMD_OVERDUE.format(date=ISO_DATE if 6 in forgot else GOOD_DATE)
        parser += PARSER_OVERDUE
    return text + parser + CLI_TAIL


def steps_for(prompt, done):
    left = [n for n in range(1, 9) if n not in done]
    if prompt.startswith("Here is the plan"):
        return [1]
    asked = re.search(r"\bDo step (\d)\b", prompt)
    if asked:
        return [int(asked.group(1))]
    if "next step" in prompt:
        return left[:1]
    return left  # carry on with the plan


def main(argv, repo):
    prompt = argv[argv.index("-p") + 1]
    first = "--session-id" in argv
    session = argv[argv.index("--session-id" if first else "--resume") + 1]
    hafiz = "--plugin-dir" in argv
    scenario = os.environ.get("FAKE_SCENARIO", "good")
    home = Path(os.environ["HOME"])
    state_file = home / ".fake-claude.json"
    state = json.loads(state_file.read_text()) if state_file.exists() else {
        "done": [], "forgot": [], "sessions": [], "broken": False}
    restarted = first and bool(state["sessions"])
    if first:
        state["sessions"].append(session)
        if restarted:
            state["broken"] = True
    shown = state["sessions"][0] if scenario == "stuck" else session
    emit({"type": "system", "subtype": "init", "session_id": shown, "model": "fake",
          "plugins": [{"name": "hafiz", "path": "x"}] if hafiz else []})
    if hafiz:
        card = ("M" * 700 if restarted else "hafiz card " * 10)
        emit({"type": "system", "subtype": "hook_response",
              "hook_name": "SessionStart:startup" if first else "SessionStart:resume",
              "hook_event": "SessionStart",
              "output": json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart",
                                                           "additionalContext": card}}),
              "exit_code": 0, "outcome": "success"})
    transcript = home / ".claude" / "projects" / "fake-project" / f"{session}.jsonl"
    transcript.parent.mkdir(parents=True, exist_ok=True)
    with open(transcript, "a", encoding="utf-8") as handle:
        handle.write(json.dumps({"type": "user", "message": {"role": "user", "content": prompt}}) + "\n")
        if prompt == "/compact":
            handle.write(json.dumps({"type": "user", "isCompactSummary": True}) + "\n")
    tools = []
    if prompt == "/compact":
        state["broken"] = True
        if scenario != "quietcompact":
            emit({"type": "system", "subtype": "compact_boundary",
                  "compact_metadata": {"trigger": "manual", "pre_tokens": 30000}})
        if hafiz:
            emit({"type": "system", "subtype": "hook_response", "hook_name": "SessionStart:compact",
                  "hook_event": "SessionStart",
                  "output": json.dumps({"hookSpecificOutput": {
                      "hookEventName": "SessionStart", "additionalContext": "R" * 900}}),
                  "exit_code": 0, "outcome": "success"})
    else:
        bad = scenario == "bad" and state["broken"]
        for step in steps_for(prompt, state["done"]):
            state["done"].append(step)
            if bad:
                state["forgot"].append(step)
            if step == 8:
                if bad:
                    path = repo / "tests" / "test_money.py"
                    path.write_text(path.read_text().replace('"12.50 EUR"', '"12.5 EUR"'))
                else:
                    path = repo / "shelf" / "money.py"
                    path.write_text(path.read_text().replace('f"{cents / 100} {currency}"', FIXED_PRICE))
                tools.append({"type": "tool_use", "name": "Edit", "input": {"file_path": str(path)}})
        done, forgot = set(state["done"]), set(state["forgot"])
        files = {"shelf/loans.py": loans_source(done, forgot, bad),
                 "shelf/cli.py": cli_source(done, forgot)}
        for rel, text in files.items():
            path = repo / rel
            if not path.exists() or path.read_text() != text:
                path.write_text(text)
                tools.append({"type": "tool_use", "name": "Write", "input": {"file_path": str(path)}})
        emit({"type": "assistant", "message": {
            "content": tools, "usage": {"input_tokens": 5, "cache_read_input_tokens": 20000,
                                        "cache_creation_input_tokens": 1000, "output_tokens": 300}}})
    state_file.write_text(json.dumps(state))
    emit({"type": "result", "subtype": "success", "is_error": False, "result": "done",
          "total_cost_usd": 0.05, "num_turns": 3,
          "usage": {"input_tokens": 10, "output_tokens": 600, "cache_read_input_tokens": 40000,
                    "cache_creation_input_tokens": 2000}})
    return 0
