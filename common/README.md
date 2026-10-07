# common

One source for the files several plugins ship. Each plugin installs on its own, so it carries
a copy; `.amin.json` lists where each file is copied.

- Edit the file here, never a copy.
- Run `python3 plugins/amin/bin/amin copies` to refresh the copies (`--check` only lists stale ones).
- `amin prepare` refreshes them too, so a release never ships a drifted copy.
- `tests/test_common.py` fails if any copy differs from its source, or if a plugin holds an
  unlisted copy.
