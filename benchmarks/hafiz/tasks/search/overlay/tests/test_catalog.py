import os
import tempfile
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

    def test_load_skips_blank_and_indented_comment_lines(self):
        # Known bug, left for later: a line of spaces or an indented comment breaks loading.
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "catalog.tsv")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("9780547928227\tThe Hobbit\tJ. R. R. Tolkien\t1937\t1299\n")
                handle.write("   \n")
                handle.write("  # an indented comment\n")
                handle.write("9780141439518\tPride and Prejudice\tJane Austen\t1813\t899\n")
            books = load_catalog(path)
        self.assertEqual([b["title"] for b in books], ["The Hobbit", "Pride and Prejudice"])


if __name__ == "__main__":
    unittest.main()
