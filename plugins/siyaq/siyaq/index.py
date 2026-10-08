"""The knowledge index: entries generated from docs plus hand-written ones, cached per project.

Doc entries: every heading section (levels 1-3) of the configured markdown sources becomes an
entry titled with its breadcrumb ("Deploy > Rollback"). File and folder paths mentioned in a
section become path triggers; mentioned paths that no longer exist are reported as dead refs.

Manual entries: .siyaq/entries/**/*.md with optional frontmatter
    title: ...      keywords: a, b, مرادف     paths: src/billing/**, deploy.yml     inject: full

The index is rebuilt automatically whenever a source file, the config or the plugin version
changes: there is no rebuild step to forget. Hooks reuse the list of source files for up to
FILES_MAX_AGE seconds (a new doc made outside Claude can take that long to appear).
"""
from __future__ import annotations

import functools
import hashlib
import json
import os
import posixpath
import re
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

from . import __version__, glossary, text

INDEX_VERSION = 4
DEFAULT_SOURCES = [
    "docs/**/*.md", "doc/**/*.md", "adr/**/*.md", "**/README.md", "CONTRIBUTING.md", "ARCHITECTURE.md",
]
# Claude Code loads these itself (CLAUDE.md files, .claude/rules with paths:, skills, agents):
# indexing them would send the same text twice. They stay excluded whatever .siyaq.json says.
DEFAULT_EXCLUDE = ["**/node_modules/**", "**/vendor/**", "**/CHANGELOG.md", "**/CLAUDE.md",
                   "**/CLAUDE.local.md", ".claude/**", "**/.claude/**", "**/LICENSE*"]
MANUAL_DIR = ".siyaq/entries"
MIN_SECTION_CHARS = 80
MAX_BODY_CHARS = 6000
TITLE_WEIGHT = 3
MAX_TRIGGER_DIR_FILES = 15
# A hook may reuse the project's list of doc files this long (#50): listing a big repo and matching
# every file against the globs took most of each tool call's wait.
FILES_MAX_AGE = 30
# A prompt or file hook waits this long for the index, then answers from the last saved one while a
# background process builds it (#118): building a large repo's index froze prompts for 30 s or more.
INDEX_WAIT = 0.3
SESSION_START_WAIT = 3.0
BUILD_TIMEOUT = 300  # seconds; a background build is stopped after this, and its lock counts as stale
LAUNCHER = Path(__file__).resolve().parent.parent / "bin" / "siyaq"

HEADING = re.compile(r"^(#{1,3})\s+(.+?)\s*#*\s*$")
FENCE = re.compile(r"^\s*(```|~~~)")
PATH_LIKE = re.compile(
    r"(?<![\w/.-])((?:\./)?(?:[\w.-]+/)+[\w.-]*|[\w-]+\.(?:cs|py|ts|tsx|js|jsx|go|rs|java|kt|json|ya?ml|"
    r"toml|md|sql|csproj|sln|sh|ps1|tf))(?![\w-])"
)
FRONTMATTER = re.compile(r"^---\n(.*?)\n---\n?", re.S)


# ---------------------------------------------------------------- locations and config


def data_home() -> Path:
    return Path(os.environ.get("SIYAQ_HOME") or Path.home() / ".claude" / "nexika" / "siyaq")


def project_root(cwd: Path) -> Path:
    try:
        res = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=cwd, capture_output=True,
                             text=True, timeout=10)
        if res.returncode == 0 and res.stdout.strip():
            return Path(res.stdout.strip()).resolve()
    except (OSError, subprocess.TimeoutExpired):
        pass
    return cwd.resolve()


def project_dir(root: Path) -> Path:
    digest = hashlib.sha1(str(root).encode()).hexdigest()[:8]
    name = re.sub(r"[^A-Za-z0-9_.-]+", "-", root.name) or "project"
    return data_home() / "projects" / f"{name}-{digest}"


def load_config(root: Path) -> dict:
    try:
        data = json.loads((root / ".siyaq.json").read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


# ---------------------------------------------------------------- globs and files


@functools.lru_cache(maxsize=256)
def glob_regex(pattern: str) -> re.Pattern:
    """Glob to regex: ** spans folders (and may be empty), * and ? stay inside one folder."""
    out, i = "", 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out, i = out + "(?:.*/)?", i + 3
        elif pattern.startswith("**", i):
            out, i = out + ".*", i + 2
        elif pattern[i] == "*":
            out, i = out + "[^/]*", i + 1
        elif pattern[i] == "?":
            out, i = out + "[^/]", i + 1
        else:
            out, i = out + re.escape(pattern[i]), i + 1
    return re.compile(out + r"\Z")


def matches_any(path: str, patterns: list[str]) -> bool:
    return any(glob_regex(p).match(path) for p in patterns)


def project_files(root: Path) -> list[str]:
    try:
        res = subprocess.run(["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
                             cwd=root, capture_output=True, timeout=20)
        if res.returncode == 0:
            names = {n for n in res.stdout.decode("utf-8", "replace").split("\0") if n}
            return sorted(n for n in names if (root / n).is_file())
    except (OSError, subprocess.TimeoutExpired):
        pass
    skip = {".git", "node_modules", "bin", "obj", "dist", "build", ".venv", "venv", "__pycache__"}
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in skip]
        for name in filenames:
            out.append(Path(dirpath, name).relative_to(root).as_posix())
    return sorted(out)


def source_files(root: Path, all_files: list[str], config: dict) -> list[str]:
    sources = config.get("sources") or DEFAULT_SOURCES
    exclude = (config.get("exclude") or []) + DEFAULT_EXCLUDE
    docs = [f for f in all_files if matches_any(f, sources) and not matches_any(f, exclude)]
    manual = [f for f in all_files if f.startswith(MANUAL_DIR + "/") and f.endswith(".md")]
    return sorted(set(docs) | set(manual))


def fingerprint(root: Path, files: list[str], config: dict) -> dict:
    fp = {"_config": json.dumps(config, sort_keys=True), "_version": f"{INDEX_VERSION}/{__version__}"}
    for rel in files:
        try:
            st = (root / rel).stat()
            fp[rel] = [st.st_mtime_ns, st.st_size]
        except OSError:
            continue
    return fp


# ---------------------------------------------------------------- building entries


def slug(value: str) -> str:
    return re.sub(r"[^\w]+", "-", value.lower()).strip("-")[:80] or "section"


def _prose(body: str) -> str:
    """The body without fenced code blocks: paths in code are usually examples, not references."""
    out, fence = [], False
    for line in body.split("\n"):
        if FENCE.match(line):
            fence = not fence
            continue
        if not fence:
            out.append(line)
    return "\n".join(out)


def _refs(body: str, source: str, fileset: set[str],
          dirs: dict[str, int]) -> tuple[list[str], list[str], list[str]]:
    """(path triggers, existing refs, dead refs) for the paths a section's prose mentions.

    Paths resolve relative to the doc first (../../README.md), then to the repo root. Only
    specific folders (at most MAX_TRIGGER_DIR_FILES files) become triggers: a broad folder
    would attach the section to every file inside it.
    """
    triggers, refs, dead = [], [], []
    doc_dir = posixpath.dirname(source)
    for raw in PATH_LIKE.findall(_prose(body)):
        rel = raw.rstrip("/")
        if not rel or rel.startswith(("http", "www.")):
            continue
        candidates = [posixpath.normpath(posixpath.join(doc_dir, rel)), posixpath.normpath(rel)]
        hit = next((c for c in candidates if c in fileset or c in dirs), None)
        if hit in fileset:
            refs.append(hit)
            if not _back_link(hit, doc_dir):
                triggers.append(hit)
        elif hit is not None:
            refs.append(hit + "/")
            if dirs[hit] <= MAX_TRIGGER_DIR_FILES:
                triggers.append(hit + "/**")
        elif "/" in rel and "." in rel.rsplit("/", 1)[-1] and not rel.startswith("."):
            dead.append(rel)

    def unique(items: list[str]) -> list[str]:
        return list(dict.fromkeys(items))

    return unique(triggers), unique(refs), unique(dead)


def _back_link(target: str, doc_dir: str) -> bool:
    """A link to the README of a folder above the doc ("Part of Nexika" in every plugin's README):
    it says where the doc belongs, not what it is about, so it never makes the README a trigger."""
    if posixpath.basename(target).lower() != "readme.md":
        return False
    folder = posixpath.dirname(target)
    return folder == "" or doc_dir == folder or doc_dir.startswith(folder + "/")


def _terms(title: str, keywords: list[str], body: str) -> Counter:
    terms: Counter = Counter()
    for tok in text.tokens(title + " " + " ".join(keywords)):
        terms[tok] += TITLE_WEIGHT
    terms.update(text.tokens(body))
    return terms


def _finish(entry: dict, heading: str) -> dict:
    """`heading` is the section's own heading: the doc title and parent headings in the breadcrumb are
    shared by every section below them, so they never count as a title hit."""
    terms = _terms(heading, entry["keywords"], entry["body"])
    head = set(text.tokens(heading + " " + " ".join(entry["keywords"])))
    # the other language's words for the terms used here (glossary.py), weighted like the originals
    translated_head = glossary.other_language(sorted(head))
    for word in translated_head:
        terms[word] += TITLE_WEIGHT
    for word in glossary.other_language(sorted(set(terms) - head)):
        terms[word] += 1
    entry["terms"] = dict(terms)
    entry["head"] = sorted(head | set(translated_head))
    entry["key_terms"] = sorted(set(text.tokens(" ".join(entry["keywords"]))))
    entry["length"] = sum(terms.values())
    entry["body"] = entry["body"][:MAX_BODY_CHARS]
    return entry


def doc_entries(rel: str, content: str, fileset: set[str], dirs: dict[str, int]) -> list[dict]:
    lines = content.split("\n")
    heads: list[tuple[int, int, str]] = []
    fence = False
    for i, line in enumerate(lines):
        if FENCE.match(line):
            fence = not fence
            continue
        m = None if fence else HEADING.match(line)
        if m:
            heads.append((i, len(m.group(1)), m.group(2).strip()))
    doc_title = next((t for _, lvl, t in heads if lvl == 1), Path(rel).stem.replace("-", " ").title())
    bounds = [(-1, 0, doc_title)] + heads  # text before the first heading belongs to the doc title
    entries: list[dict] = []
    seen: Counter = Counter()
    crumbs: list[tuple[int, str]] = []
    for n, (i, level, title) in enumerate(bounds):
        end = bounds[n + 1][0] if n + 1 < len(bounds) else len(lines)
        if level:
            crumbs = [c for c in crumbs if c[0] < level] + [(level, title)]
        names = [t for _, t in crumbs] or [doc_title]
        if names[0] != doc_title:
            names = [doc_title, *names]
        breadcrumb = " > ".join(dict.fromkeys(names))
        body = "\n".join(lines[i + 1:end]).strip()
        if len(body) < MIN_SECTION_CHARS:
            continue
        base = f"{rel}#{slug(breadcrumb)}"
        seen[base] += 1
        triggers, refs, dead = _refs(body, rel, fileset, dirs)
        entries.append(_finish({
            "id": base if seen[base] == 1 else f"{base}-{seen[base]}", "title": breadcrumb, "source": rel,
            "start": i + 2, "end": end, "body": body, "kind": "doc", "keywords": [], "paths": triggers,
            "refs": refs, "dead_refs": dead, "inject": "auto",
        }, title))
    return entries


def _split_list(value: str) -> list[str]:
    return [v.strip() for v in value.split(",") if v.strip()]


def manual_entry(rel: str, content: str, fileset: set[str], dirs: dict[str, int]) -> dict | None:
    meta: dict[str, str] = {}
    body = content
    m = FRONTMATTER.match(content)
    if m:
        for line in m.group(1).splitlines():
            key, sep, value = line.partition(":")
            if sep:
                meta[key.strip().lower()] = value.strip().strip('"').strip("'")
        body = content[m.end():]
    body = body.strip()
    if not body:
        return None
    title = meta.get("title") or Path(rel).stem.replace("-", " ").capitalize()
    triggers, refs, dead = _refs(body, rel, fileset, dirs)
    start = content[: m.end()].count("\n") + 1 if m else 1
    inject = meta.get("inject", "auto")
    return _finish({
        "id": rel, "title": title, "source": rel, "start": start, "end": content.count("\n") + 1,
        "body": body, "kind": "manual", "keywords": _split_list(meta.get("keywords", "")),
        "paths": _split_list(meta.get("paths", "")) + triggers, "refs": refs, "dead_refs": dead,
        "inject": inject if inject in ("summary", "full") else "auto",
    }, title)


def build(root: Path, config: dict | None = None) -> dict:
    config = load_config(root) if config is None else config
    all_files = project_files(root)
    fileset = set(all_files)
    dirs: Counter = Counter()  # folder -> number of files anywhere below it
    for f in all_files:
        parts = f.split("/")[:-1]
        for k in range(1, len(parts) + 1):
            dirs["/".join(parts[:k])] += 1
    files = source_files(root, all_files, config)
    entries: list[dict] = []
    for rel in files:
        try:
            content = (root / rel).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if rel.startswith(MANUAL_DIR + "/"):
            entry = manual_entry(rel, content, fileset, dirs)
            if entry:
                entries.append(entry)
        else:
            entries.extend(doc_entries(rel, content, fileset, dirs))
    df: Counter = Counter()
    for entry in entries:
        df.update(entry["terms"].keys())
    total = sum(e["length"] for e in entries)
    return {
        "version": INDEX_VERSION, "root": str(root), "fingerprint": fingerprint(root, files, config),
        "sources": files, "entries": entries, "df": dict(df), "n": len(entries),
        "avglen": (total / len(entries)) if entries else 0.0,
    }


def _files_key(root: Path, config: dict) -> list:
    try:  # staging, checkouts and merges change git's index; a worktree has none here (0)
        staged = (root / ".git" / "index").stat().st_mtime_ns
    except OSError:
        staged = 0
    return [json.dumps(config, sort_keys=True), f"{INDEX_VERSION}/{__version__}", staged]


def _save_files(root: Path, key: list, files: list[str]) -> None:
    from .state import write_atomic  # state imports this module

    try:
        write_atomic(project_dir(root) / "files.json", json.dumps({"key": key, "at": time.time(),
                                                                   "sources": files}))
    except OSError:
        pass


def cached_source_files(root: Path, config: dict, max_age: float = 0) -> list[str]:
    """The doc files to index; with max_age, the list saved by a call at most that many seconds ago,
    for the same config and the same git index."""
    key = _files_key(root, config)
    if max_age > 0:
        try:
            data = json.loads((project_dir(root) / "files.json").read_text(encoding="utf-8"))
            if data["key"] == key and 0 <= time.time() - float(data["at"]) < max_age:
                return [str(f) for f in data["sources"]]
        except (OSError, ValueError, TypeError, KeyError):
            pass
    files = source_files(root, project_files(root), config)
    _save_files(root, key, files)
    return files


def forget_files(root: Path) -> None:
    """A new doc is being written: list the files again on the next call."""
    try:
        (project_dir(root) / "files.json").unlink()
    except OSError:
        pass


def load(root: Path, config: dict | None = None, max_age: float = 0) -> dict:
    """The cached index, rebuilt first if any source, the config or the plugin changed. Hooks pass
    max_age=FILES_MAX_AGE to reuse the file list; commands always list the files again."""
    config = load_config(root) if config is None else config
    cache = project_dir(root) / "index.json"
    files = cached_source_files(root, config, max_age)
    current = fingerprint(root, files, config)
    try:
        cached = json.loads(cache.read_text(encoding="utf-8"))
        if cached.get("fingerprint") == current:
            return cached
    except (OSError, ValueError):
        pass
    index = build(root, config)
    from .state import write_atomic  # state imports this module

    write_atomic(cache, json.dumps(index, ensure_ascii=False))
    _save_files(root, _files_key(root, config), index["sources"])
    return index


def saved(root: Path) -> dict:
    """The last index written for this project, current or not; an empty one when there is none."""
    try:
        data = json.loads((project_dir(root) / "index.json").read_text(encoding="utf-8"))
        if isinstance(data, dict) and data.get("version") == INDEX_VERSION and isinstance(data.get("n"), int):
            return data
    except (OSError, ValueError):
        pass
    return {"version": INDEX_VERSION, "root": str(root), "sources": [], "entries": [], "df": {}, "n": 0,
            "avglen": 0.0}


def load_ready(root: Path, config: dict, wait: float | None = None) -> dict:
    """For hooks: the current index if it is ready within `wait` seconds (INDEX_WAIT by default).
    Otherwise the last saved index marked "building", and a background process builds the new one."""
    import threading

    done: dict = {}

    def work() -> None:
        try:
            done["index"] = load(root, config, max_age=FILES_MAX_AGE)
        except Exception:  # noqa: BLE001 - the saved index is used instead
            done["error"] = True

    worker = threading.Thread(target=work, daemon=True)  # left behind when the hook exits
    worker.start()
    worker.join(INDEX_WAIT if wait is None else wait)
    if "index" in done:
        return done["index"]
    if worker.is_alive():
        build_in_background(root)
    return {**saved(root), "building": True}


def _lock_is_fresh(lock: Path) -> bool:
    try:
        return time.time() - lock.stat().st_mtime < BUILD_TIMEOUT + 60
    except OSError:
        return False


def build_in_background(root: Path) -> None:
    """Start `siyaq refresh` in its own process, unless a build of this project is already running."""
    if _lock_is_fresh(project_dir(root) / "build.lock"):
        return
    try:
        subprocess.Popen([sys.executable, str(LAUNCHER), "refresh"], cwd=root, stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    except OSError:
        pass


def refresh(root: Path) -> bool:
    """Bring the saved index up to date (what build_in_background runs); False when another build of
    this project holds the lock."""
    lock = project_dir(root) / "build.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    try:
        lock.mkdir()
    except FileExistsError:
        if _lock_is_fresh(lock):
            return False
        try:
            lock.rmdir()
            lock.mkdir()
        except OSError:
            return False
    try:
        load(root)
    finally:
        try:
            lock.rmdir()
        except OSError:
            pass
    return True
