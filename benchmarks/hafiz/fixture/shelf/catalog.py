"""Read the catalog file and look books up."""

FIELDS = ("isbn", "title", "author", "year", "price_cents")


def load_catalog(path):
    """Every book in the tab-separated file at path, as a dict with FIELDS as keys."""
    books = []
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.rstrip("\n")
            if not line or line.startswith("#"):
                continue
            book = dict(zip(FIELDS, line.split("\t"), strict=True))
            book["year"] = int(book["year"])
            book["price_cents"] = int(book["price_cents"])
            books.append(book)
    return books


def find(books, title=None, author=None):
    """The books whose title and author contain the given text, ignoring case."""
    found = []
    for book in books:
        if title and title.lower() not in book["title"].lower():
            continue
        if author and author.lower() not in book["author"].lower():
            continue
        found.append(book)
    return found
