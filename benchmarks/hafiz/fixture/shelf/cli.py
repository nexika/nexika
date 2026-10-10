"""The shelf command: python3 -m shelf list data/catalog.tsv"""

import argparse
import sys

from .catalog import load_catalog
from .money import format_price


def cmd_list(args):
    books = load_catalog(args.catalog)
    width = max(len(book["title"]) for book in books)
    for book in books:
        price = format_price(book["price_cents"])
        print(f"{book['title']:<{width}}  {book['author']} ({book['year']})  {price}")
    return 0


def build_parser():
    parser = argparse.ArgumentParser(prog="shelf")
    commands = parser.add_subparsers(dest="command", required=True)
    listing = commands.add_parser("list", help="list every book in a catalog")
    listing.add_argument("catalog")
    listing.set_defaults(handler=cmd_list)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    return args.handler(args)


if __name__ == "__main__":
    sys.exit(main())
