import contextlib
import io
import os
import tempfile
import unittest

from shelf.cli import main

CATALOG = os.path.join(os.path.dirname(__file__), "..", "data", "catalog.tsv")


def run(*argv):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = main(list(argv))
    return code, out.getvalue()


class CliTest(unittest.TestCase):
    def test_list(self):
        code, out = run("list", CATALOG)
        self.assertEqual(code, 0)
        self.assertEqual(len(out.splitlines()), 8)
        self.assertIn("The Hobbit", out)
        self.assertIn("12.99 EUR", out)

    def test_list_empty_catalog(self):
        # Known bug, left for later: an empty catalog crashes instead of saying so.
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "empty.tsv")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("# isbn\ttitle\tauthor\tyear\tprice_cents\n")
            code, out = run("list", path)
        self.assertEqual(code, 0)
        self.assertEqual(out, "no books\n")


if __name__ == "__main__":
    unittest.main()
