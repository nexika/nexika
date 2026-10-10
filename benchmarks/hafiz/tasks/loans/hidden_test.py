"""Hidden checks for the loans tasks (loans-compact, loans-restart). They run in the work repo after
the agent finished; the agent never sees them.

On 2026-03-20 three loans of data/loans.tsv are overdue, the oldest first:
    Nineteen Eighty-Four  Anna Berg      due 10.01.2026  69 days late  fine 10.99 EUR (the price)
    The Hobbit            Johann Strauß  due 02.03.2026  18 days late  fine  3.75 EUR
    Pride and Prejudice   Lena Fischer   due 14.03.2026   6 days late  fine  0.75 EUR
The fine rule (a decision): 25 cents a day after 3 free days, never more than the book's price.
"""

import contextlib
import datetime
import io
import os
import unittest

CATALOG = os.path.join(os.getcwd(), "data", "catalog.tsv")
LOANS = os.path.join(os.getcwd(), "data", "loans.tsv")
TODAY = datetime.date(2026, 3, 20)
HOBBIT, PRIDE, ORWELL, INVISIBLE = "9780547928227", "9780141439518", "9780451524935", "9780679732761"


def cli(*argv):
    from shelf.cli import main

    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = main(list(argv))
    return code or 0, out.getvalue()


def loan(isbn):
    from shelf.loans import load_loans

    return next(item for item in load_loans(LOANS) if item["isbn"] == isbn)


class HiddenTest(unittest.TestCase):
    # Finished early in the session (steps 1 to 4).
    def test_done_load_loans(self):
        from shelf.loans import load_loans

        loans = load_loans(LOANS)
        self.assertEqual(len(loans), 4)
        self.assertEqual(loans[1]["member"], "Johann Strauß")
        self.assertEqual(loans[1]["due"], datetime.date(2026, 3, 2))
        self.assertEqual(loans[1]["out"], datetime.date(2026, 2, 2))

    def test_done_overdue(self):
        from shelf.loans import load_loans, overdue

        late = overdue(load_loans(LOANS), TODAY)
        self.assertEqual([item["isbn"] for item in late], [ORWELL, HOBBIT, PRIDE])

    def test_done_loans_command(self):
        code, out = cli("loans", LOANS)
        self.assertEqual(code, 0)
        self.assertIn("Johann Strauß", out)
        self.assertIn("Lena Fischer", out)
        self.assertEqual(sum(1 for line in out.splitlines() if "Anna Berg" in line), 2)

    def test_done_days_late(self):
        from shelf.loans import days_late

        self.assertEqual(days_late(loan(HOBBIT), TODAY), 18)
        self.assertEqual(days_late(loan(ORWELL), TODAY), 69)
        self.assertEqual(days_late(loan(INVISIBLE), TODAY), 0)

    # Open after the break (steps 5 to 7).
    def test_open_fine_cents(self):
        from shelf.loans import fine_cents

        self.assertEqual(fine_cents(0, 1299), 0)
        self.assertGreater(fine_cents(10, 1299), 0)
        self.assertGreaterEqual(fine_cents(12, 1299), fine_cents(10, 1299))

    def test_open_overdue_command(self):
        code, out = cli("overdue", CATALOG, LOANS, "--today", "2026-03-20")
        self.assertEqual(code, 0)
        found = [out.find(title) for title in ("Nineteen Eighty-Four", "The Hobbit", "Pride and Prejudice")]
        self.assertTrue(all(at >= 0 for at in found), out)
        self.assertEqual(found, sorted(found), "oldest due date first")
        self.assertNotIn("Invisible Man", out)

    def test_open_loans_member(self):
        code, out = cli("loans", LOANS, "--member", "anna")
        self.assertEqual(code, 0)
        self.assertEqual(sum(1 for line in out.splitlines() if "Anna Berg" in line), 2)
        self.assertNotIn("Fischer", out)
        self.assertNotIn("Strauß", out)

    # Decisions, stated once at the start of the session.
    def test_decision_fine_rule(self):
        from shelf.loans import fine_cents

        self.assertEqual([fine_cents(days, 1299) for days in (1, 3, 4, 10, 18)], [0, 0, 25, 175, 375])
        self.assertEqual(fine_cents(69, 1099), 1099)
        self.assertEqual(fine_cents(1000, 899), 899)

    def test_decision_fine_whole_cents(self):
        from shelf.loans import fine_cents

        for days in (4, 10, 18, 100):
            self.assertIs(type(fine_cents(days, 1299)), int)

    def test_decision_fines_in_overdue_command(self):
        code, out = cli("overdue", CATALOG, LOANS, "--today", "2026-03-20")
        for title, fine in (("Nineteen Eighty-Four", "10.99 EUR"), ("The Hobbit", "3.75 EUR"),
                            ("Pride and Prejudice", "0.75 EUR")):
            line = next((line for line in out.splitlines() if title in line), "")
            self.assertIn(fine, line, out)

    def test_decision_member_casefold(self):
        code, out = cli("loans", LOANS, "--member", "STRAUSS")
        self.assertEqual(code, 0)
        self.assertIn("Strauß", out)
        self.assertNotIn("Anna Berg", out)

    # Decision stated once, in the second prompt: dates print as DD.MM.YYYY.
    def test_decision_dates_loans_command(self):
        code, out = cli("loans", LOANS)
        self.assertIn("02.03.2026", out)
        self.assertNotIn("2026-03-02", out)

    def test_decision_dates_overdue_command(self):
        code, out = cli("overdue", CATALOG, LOANS, "--today", "2026-03-20")
        self.assertIn("02.03.2026", out)
        self.assertNotIn("2026-03-02", out)
