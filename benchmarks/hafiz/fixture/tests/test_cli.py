import contextlib
import io
import os
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


if __name__ == "__main__":
    unittest.main()
