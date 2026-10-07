"""itqan's own data files: private (0600 in a 0700 folder), secrets redacted, rotated (stdlib only)."""
from __future__ import annotations

import json
import os
from pathlib import Path

LIMIT = 1_000_000  # bytes; past this a jsonl file is moved to <name>.1.jsonl and a new one started


def private_dir(folder: Path) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(folder, 0o700)
    except OSError:
        pass
    return folder


def _rotated(path: Path) -> Path:
    return path.with_name(f"{path.stem}.1{path.suffix}")


def append_jsonl(path: Path, entry: dict) -> None:
    private_dir(path.parent)
    if path.exists() and path.stat().st_size > LIMIT:
        os.replace(path, _rotated(path))
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    os.fchmod(fd, 0o600)  # files written by older versions were 0644
    with os.fdopen(fd, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


def write_private(path: Path, text: str) -> None:
    private_dir(path.parent)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.fchmod(fd, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(text)


def read_jsonl(path: Path) -> list[dict]:
    """Entries of the rotated file then the current one, oldest first."""
    out = []
    for name in (_rotated(path), path):
        try:
            lines = name.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for line in lines:
            try:
                item = json.loads(line)
            except ValueError:
                continue
            if isinstance(item, dict):
                out.append(item)
    return out
