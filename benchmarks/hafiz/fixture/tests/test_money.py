import unittest

from shelf.money import format_price


class MoneyTest(unittest.TestCase):
    def test_format(self):
        self.assertEqual(format_price(12345), "123.45 EUR")

    def test_currency(self):
        self.assertEqual(format_price(199, "USD"), "1.99 USD")


if __name__ == "__main__":
    unittest.main()
