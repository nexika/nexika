"""Hidden checks for the search task. They run in the work repo after the agent finished."""

import contextlib
import inspect
import io
import os
import unittest

CATALOG = os.path.join(os.getcwd(), "data", "catalog.tsv")


def cli(*argv):
    from shelf.cli import main

    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = main(list(argv))
    return code or 0, out.getvalue()


class HiddenTest(unittest.TestCase):
    # Decision: find stays backwards compatible, year is keyword-only.
    def test_compat_find(self):
        from shelf import find, load_catalog

        books = load_catalog(CATALOG)
        self.assertEqual([b["title"] for b in find(books, "hobbit")], ["The Hobbit"])
        self.assertEqual(len(find(books, None, "tolkien")), 2)
        self.assertEqual(len(find(books, author="tolkien", year=1937)), 1)
        year = inspect.signature(find).parameters["year"]
        self.assertEqual(year.kind, inspect.Parameter.KEYWORD_ONLY)

    # Decision: casefold, so "strasse" finds "Straße".
    def test_decision_casefold_search(self):
        from shelf import load_catalog
        from shelf.catalog import search

        found = search(load_catalog(CATALOG), "STRASSE ölsardinen")
        self.assertEqual([b["title"] for b in found], ["Straße der Ölsardinen"])

    def test_decision_casefold_list_title(self):
        code, out = cli("list", CATALOG, "--title", "strasse")
        self.assertEqual(code, 0)
        self.assertIn("Ölsardinen", out)
        self.assertNotIn("Hobbit", out)

    # Finished before the compaction: still works.
    def test_done_search_command(self):
        code, out = cli("search", CATALOG, "tolkien")
        self.assertEqual(code, 0)
        self.assertIn("The Hobbit", out)
        self.assertIn("The Lord of the Rings", out)

    # Open after the compaction: step 4.
    def test_open_search_year(self):
        code, out = cli("search", CATALOG, "tolkien", "--year", "1937")
        self.assertEqual(code, 0)
        self.assertIn("The Hobbit", out)
        self.assertNotIn("The Lord of the Rings", out)

    def test_open_list_title(self):
        code, out = cli("list", CATALOG, "--title", "hobbit")
        self.assertEqual(code, 0)
        self.assertIn("The Hobbit", out)
        self.assertNotIn("Brave New World", out)
