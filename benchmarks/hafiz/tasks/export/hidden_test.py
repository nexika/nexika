"""Hidden checks for the export task. They run in the work repo after the agent finished."""

import contextlib
import csv
import io
import json
import os
import tempfile
import unittest

CATALOG = os.path.join(os.getcwd(), "data", "catalog.tsv")
FIELDS = ("isbn", "title", "author", "year", "price_cents")


def cli(*argv):
    from shelf.cli import main

    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = main(list(argv))
    return code or 0, out.getvalue()


class HiddenTest(unittest.TestCase):
    # Decision: the public API stays backwards compatible.
    def test_compat_load_catalog(self):
        from shelf import load_catalog

        books = load_catalog(CATALOG)
        self.assertEqual(len(books), 8)
        self.assertTrue(all(type(book) is dict for book in books))
        self.assertEqual(set(books[0]), set(FIELDS))
        self.assertEqual(books[0]["year"], 1937)

    def test_compat_find(self):
        from shelf import find, load_catalog

        books = load_catalog(CATALOG)
        self.assertEqual([b["title"] for b in find(books, "hobbit")], ["The Hobbit"])
        self.assertEqual(len(find(books, None, "tolkien")), 2)
        self.assertEqual(len(find(books, title="lord", author="tolkien")), 1)

    # Finished before the compaction: still works.
    def test_done_export_csv(self):
        from shelf import load_catalog
        from shelf.export import export_csv

        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "out.csv")
            export_csv(load_catalog(CATALOG), path)
            with open(path, newline="", encoding="utf-8") as handle:
                rows = list(csv.reader(handle))
        self.assertIn("title", rows[0])
        self.assertEqual(len(rows), 9)

    def test_done_export_json(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "out.json")
            code, _ = cli("export", CATALOG, path, "--format", "json")
            with open(path, encoding="utf-8") as handle:
                data = json.load(handle)
        self.assertEqual(code, 0)
        self.assertEqual(len(data), 8)

    # Open after the compaction: step 4, load_catalog reads .csv too.
    def test_open_load_csv(self):
        from shelf import load_catalog
        from shelf.export import export_csv

        books = load_catalog(CATALOG)
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "books.csv")
            export_csv(books, path)
            again = load_catalog(path)
        self.assertEqual(again, books)
