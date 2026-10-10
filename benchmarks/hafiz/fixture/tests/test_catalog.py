import os
import unittest

from shelf import find, load_catalog

CATALOG = os.path.join(os.path.dirname(__file__), "..", "data", "catalog.tsv")


class CatalogTest(unittest.TestCase):
    def test_load(self):
        books = load_catalog(CATALOG)
        self.assertEqual(len(books), 8)
        self.assertEqual(books[0]["title"], "The Hobbit")
        self.assertEqual(books[0]["year"], 1937)
        self.assertEqual(books[0]["price_cents"], 1299)

    def test_find_by_title(self):
        books = load_catalog(CATALOG)
        self.assertEqual([b["title"] for b in find(books, title="hobbit")], ["The Hobbit"])

    def test_find_by_author(self):
        books = load_catalog(CATALOG)
        self.assertEqual(len(find(books, author="tolkien")), 2)


if __name__ == "__main__":
    unittest.main()
