"""Project root, file listing, the path fence and safe text reads."""
from __future__ import annotations

import os
import subprocess
from functools import lru_cache
from pathlib import Path

# Only used when the project is not a git repo; in a repo, .gitignore decides.
IGNORED_DIRS = {
    ".git", "node_modules", "bin", "obj", "dist", "build", "out", "target", ".venv", "venv",
    "__pycache__", ".mypy_cache", ".pytest_cache", ".ruff_cache", ".idea", ".vs", ".next",
    ".nuxt", "coverage", ".gradle", "vendor", ".tox",
}
MAX_FILES = 50_000
MAX_TEXT_BYTES = 5 * 1024 * 1024
BINARY_SNIFF = 8000


class FenceError(Exception):
    """A path points outside the project."""


class FileError(Exception):
    """A file cannot be read as text."""


def _git(args: list[str], cwd: Path) -> str | None:
    try:
        res = subprocess.run(["git", *args], cwd=cwd, capture_output=True, timeout=15)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return res.stdout.decode("utf-8", "replace") if res.returncode == 0 else None


@lru_cache(maxsize=16)
def project_root(cwd: str) -> Path:
    """The git top-level containing cwd, or cwd itself."""
    top = _git(["rev-parse", "--show-toplevel"], Path(cwd))
    return Path(top.strip()).resolve() if top and top.strip() else Path(cwd).resolve()


def is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def resolve(path_str: str, cwd: Path, root: Path) -> Path:
    """Absolute, symlink-free path; refuses anything outside the project root."""
    p = Path(path_str).expanduser()
    if not p.is_absolute():
        p = cwd / p
    real = p.resolve()
    if os.environ.get("BARQ_ALLOW_OUTSIDE") != "1" and not is_within(real, root):
        raise FenceError(
            f"{path_str} is outside the project ({root}). Set BARQ_ALLOW_OUTSIDE=1 to allow it."
        )
    return real


def rel(path: Path, cwd: Path) -> str:
    """Display path: relative to cwd when possible, always with forward slashes."""
    try:
        out = os.path.relpath(path, cwd)
    except ValueError:  # different drive on Windows
        out = str(path)
    return out.replace(os.sep, "/")


def list_files(base: Path) -> list[Path]:
    """Files under base: git-tracked + untracked-not-ignored in a repo, else a pruned walk."""
    if base.is_file():
        return [base]
    listed = _git(["ls-files", "-z", "--cached", "--others", "--exclude-standard"], base)
    if listed is not None:
        seen: set[Path] = set()
        out = []
        for name in listed.split("\0"):
            if not name:
                continue
            p = base / name
            if p not in seen and p.is_file():
                seen.add(p)
                out.append(p)
                if len(out) >= MAX_FILES:
                    break
        return sorted(out)
    out = []
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = sorted(d for d in dirnames if d not in IGNORED_DIRS)
        for name in sorted(filenames):
            out.append(Path(dirpath) / name)
            if len(out) >= MAX_FILES:
                return out
    return out


def read_text(path: Path) -> str:
    """Decoded text of a file; raises FileError for missing, huge or binary files."""
    if not path.exists():
        raise FileError(f"{path.name}: no such file")
    if path.is_dir():
        raise FileError(f"{path.name} is a directory (use tree or glob)")
    size = path.stat().st_size
    if size > MAX_TEXT_BYTES:
        raise FileError(f"{path.name} is {size // 1024} KB; too large to read as text")
    data = path.read_bytes()
    if b"\0" in data[:BINARY_SNIFF]:
        raise FileError(f"{path.name} looks binary ({size} bytes)")
    return data.decode("utf-8", "replace")


def is_text_file(path: Path) -> bool:
    try:
        with open(path, "rb") as fh:
            return b"\0" not in fh.read(BINARY_SNIFF)
    except OSError:
        return False
