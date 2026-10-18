"""itqan's own data files: private (0600 in a 0700 folder), secrets redacted, rotated (stdlib only)."""
from __future__ import annotations

import contextlib
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


def write_atomic(path: Path, text: str, mode: int = 0o600, errors: str = "strict") -> None:
    """Replaces path whole: a reader sees the old text or the new one, and two writers never share a
    temp file (#394). The mode of an existing file is kept."""
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{os.urandom(4).hex()}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    try:
        with contextlib.suppress(OSError):
            os.fchmod(fd, path.stat().st_mode & 0o777)
        with os.fdopen(fd, "w", encoding="utf-8", errors=errors) as fh:
            fh.write(text)
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


@contextlib.contextmanager
def locked(path: Path):
    """Holds an exclusive lock on .<name>.lock beside path for one read-modify-write of path (#394).
    The caller makes the folder. Without fcntl (Windows) or when the lock cannot be taken, the block
    runs unlocked. Never nest two blocks on one path in a process: the second would wait forever."""
    fd = None
    try:
        import fcntl

        fd = os.open(path.with_name(f".{path.name}.lock"), os.O_RDWR | os.O_CREAT, 0o600)
        fcntl.flock(fd, fcntl.LOCK_EX)
    except (ImportError, OSError):
        if fd is not None:
            os.close(fd)
            fd = None
    try:
        yield
    finally:
        if fd is not None:
            os.close(fd)


def read_jsonl(path: Path) -> list[dict]:
    """Entries of the rotated file then the current one, oldest first. A line cut by a writer that was
    killed (half a character, half an object) is skipped, never the whole file (#394)."""
    out = []
    for name in (_rotated(path), path):
        try:
            lines = name.read_text(encoding="utf-8", errors="replace").splitlines()
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
