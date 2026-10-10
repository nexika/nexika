"""Hidden checks for the models task. They run in the work repo after the agent finished."""

import contextlib
import dataclasses
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


def order(out, titles):
    """The titles in the order the output lists them."""
    return sorted(titles, key=out.find)


class HiddenTest(unittest.TestCase):
    # Decision: load_catalog keeps returning plain dicts.
    def test_compat_load_catalog(self):
        from shelf import load_catalog

        books = load_catalog(CATALOG)
        self.assertEqual(len(books), 8)
        self.assertTrue(all(type(book) is dict for book in books))

    # Decision: dataclasses from the standard library.
    def test_decision_dataclass(self):
        from shelf.models import Book

        self.assertTrue(dataclasses.is_dataclass(Book))

    # Finished before the compaction: still works.
    def test_done_load_books_and_sort(self):
        from shelf.catalog import load_books, sort_books
        from shelf.models import Book

        books = load_books(CATALOG)
        self.assertTrue(all(isinstance(book, Book) for book in books))
        self.assertEqual(sort_books(books, key="year")[0].title, "Pride and Prejudice")

    # Open after the compaction: step 4, shelf list --sort.
    def test_open_list_sort_year(self):
        code, out = cli("list", CATALOG, "--sort", "year")
        self.assertEqual(code, 0)
        titles = ["Pride and Prejudice", "Crime and Punishment", "Brave New World", "The Hobbit"]
        self.assertEqual(order(out, titles), titles)

    def test_open_list_sort_author(self):
        code, out = cli("list", CATALOG, "--sort", "author")
        self.assertEqual(code, 0)
        titles = ["Brave New World", "Crime and Punishment", "Nineteen Eighty-Four", "Invisible Man"]
        self.assertEqual(order(out, titles), titles)
