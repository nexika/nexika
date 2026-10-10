import unittest

from shelf.money import format_price


class MoneyTest(unittest.TestCase):
    def test_format(self):
        self.assertEqual(format_price(12345), "123.45 EUR")

    def test_currency(self):
        self.assertEqual(format_price(199, "USD"), "1.99 USD")

    def test_two_decimals(self):
        # Known bug, left for later: 1250 cents prints as "12.5 EUR".
        self.assertEqual(format_price(1250), "12.50 EUR")
        self.assertEqual(format_price(5), "0.05 EUR")
        self.assertEqual(format_price(-1999), "-19.99 EUR")


if __name__ == "__main__":
    unittest.main()
