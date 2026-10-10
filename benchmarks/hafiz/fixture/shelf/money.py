"""Prices are kept in cents."""


def format_price(cents, currency="EUR"):
    """12345 -> '123.45 EUR'."""
    return f"{cents / 100} {currency}"
