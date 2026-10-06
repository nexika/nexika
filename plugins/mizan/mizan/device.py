"""The machine: memory and disk in use, as percentages, with a warning level.

A full machine stopped a build once; mizan warns at 85 % (yellow) and 95 % (red).
Linux reads /proc/meminfo, macOS asks sysctl and vm_stat; elsewhere memory is unknown.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys

WARN, BAD = 85, 95
GB = 1024 ** 3


def level(percent: float | None) -> str:
    if percent is None:
        return "unknown"
    return "bad" if percent >= BAD else "warn" if percent >= WARN else "ok"


def parse_meminfo(text: str) -> tuple[int, int] | None:
    """(total, available) in bytes from /proc/meminfo."""
    values = {}
    for line in text.splitlines():
        name, _, rest = line.partition(":")
        number = re.match(r"\s*(\d+)", rest)
        if number:
            values[name.strip()] = int(number.group(1)) * 1024
    total = values.get("MemTotal")
    available = values.get("MemAvailable")
    if available is None and total:
        available = values.get("MemFree", 0) + values.get("Buffers", 0) + values.get("Cached", 0)
    return (total, available) if total else None


def parse_vm_stat(text: str, total: int) -> tuple[int, int] | None:
    """(total, available) from macOS vm_stat: free, inactive, speculative and purgeable pages."""
    size = re.search(r"page size of (\d+) bytes", text)
    page = int(size.group(1)) if size else 4096
    pages = {m.group(1).lower(): int(m.group(2)) for m in re.finditer(r"Pages ([\w ]+):\s+(\d+)", text)}
    free = sum(pages.get(k, 0) for k in ("free", "inactive", "speculative", "purgeable"))
    return (total, min(total, free * page)) if total else None


def _run(argv: list[str]) -> str:
    try:
        return subprocess.run(argv, capture_output=True, text=True, timeout=3, check=False).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def memory() -> dict:
    found = None
    if sys.platform.startswith("linux"):
        try:
            with open("/proc/meminfo", encoding="ascii") as fh:
                found = parse_meminfo(fh.read())
        except OSError:
            found = None
    elif sys.platform == "darwin":
        total = _run(["sysctl", "-n", "hw.memsize"]).strip()
        if total.isdigit():
            found = parse_vm_stat(_run(["vm_stat"]), int(total))
    if not found:
        return {"percent": None, "level": "unknown"}
    total, available = found
    percent = round(100 * (1 - available / total))
    return {"percent": percent, "level": level(percent), "total_gb": round(total / GB, 1),
            "used_gb": round((total - available) / GB, 1)}


def disk(path: str) -> dict:
    try:
        usage = shutil.disk_usage(path if os.path.isdir(path) else os.path.expanduser("~"))
    except OSError:
        return {"percent": None, "level": "unknown"}
    percent = round(100 * usage.used / usage.total) if usage.total else None
    return {"percent": percent, "level": level(percent), "free_gb": round(usage.free / GB, 1)}


def read(cwd: str) -> dict:
    return {"ram": memory(), "disk": disk(cwd)}
