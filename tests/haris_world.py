"""The world haris's corpus and benchmark run in: a throwaway home with keys and shell profiles, and a
project inside it on branch feat/x. Shared by tests/test_haris.py and benchmarks/haris/bench.py, so
it needs neither pytest nor conftest."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
HARIS_ROOT = REPO / "plugins" / "haris"
CORPUS = REPO / "tests" / "haris_corpus.tsv"
if str(HARIS_ROOT) not in sys.path:
    sys.path.insert(0, str(HARIS_ROOT))

from haris import policy  # noqa: E402


def _git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def build_world(base):
    """A home folder with keys and shell profiles, and a project inside it on branch feat/x."""
    home = base / "home"
    project = home / "work" / "proj"
    for d in ("src", "build", "node_modules/.bin", "scripts", "tests"):
        (project / d).mkdir(parents=True, exist_ok=True)
    files = {
        "src/app.py": "print('hi')\n", "README.md": "# demo\n", "package.json": '{"name": "demo"}\n',
        ".env": "API_KEY=abc\n", ".env.example": "API_KEY=\n", ".env.production": "API_KEY=prod\n",
        "data.txt": "a b\n", "list.txt": "a\n", "node_modules/.bin/jest": "", "scripts/build.sh": "echo\n",
    }
    for name, text in files.items():
        (project / name).write_text(text)
    for name, text in {".ssh/id_rsa": "KEY", ".ssh/id_rsa.pub": "PUB", ".ssh/id_ed25519": "KEY",
                       ".aws/credentials": "[default]", ".bashrc": "", ".netrc": "",
                       ".docker/config.json": "{}",
                       ".claude/settings.json": "{}", ".gitconfig": "[alias]\n\tco = checkout\n"}.items():
        path = home / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    _git(project, "init", "-q", "-b", "main")
    _git(project, "config", "user.email", "t@example.com")
    _git(project, "config", "user.name", "Test")
    _git(project, "add", "src", "README.md", "package.json", ".env.example", "data.txt", "list.txt")
    _git(project, "commit", "-q", "-m", "initial")
    _git(project, "switch", "-q", "-c", "feat/x")
    remote = project / ".git" / "refs" / "remotes" / "origin"
    remote.mkdir(parents=True)
    (remote / "HEAD").write_text("ref: refs/remotes/origin/main\n")
    (project / "src" / "app.py").write_text("print('changed')\n")  # uncommitted work
    return home, project


def decide(project, tool, value, cfg=None, session=None, approvals=None):
    if tool in ("Bash", "PowerShell"):
        tool_input = {"command": value}
    elif tool == "WebFetch":
        tool_input = {"url": value}
    elif tool == "WebSearch":
        tool_input = {"query": value}
    elif tool.startswith("mcp__"):
        tool_input = json.loads(value)
    elif tool in ("Grep", "Glob"):
        tool_input = {"path": value}
    else:
        tool_input = {"file_path": value}
    cfg = cfg or policy.effective_config(str(project))
    return policy.decide({"tool_name": tool, "tool_input": tool_input, "cwd": str(project)}, cfg, session,
                         approvals)


def corpus_lines(path=CORPUS):
    """(line number, expected, tool, value, section) for every case; the section is the title of the
    `# ----` header above the line."""
    out, section = [], ""
    for n, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        if line.startswith("# ---"):
            section = line.lstrip("# -").strip()
        if not line.strip() or line.startswith("#"):
            continue
        expected, _, rest = line.partition("\t")
        tool, value = "Bash", rest
        if rest.startswith("@"):
            tool, _, value = rest[1:].partition("\t")
        value = value.replace("↵", "\n").replace("{PLUGIN}", str(HARIS_ROOT))
        out.append((n, expected, tool, value, section))
    return out


def home_path(tool, value, home):
    """Read, Write and Edit lines name files under ~ that a tool would get as full paths."""
    if tool in ("Read", "Write", "Edit") and value.startswith("~"):
        return str(home) + value[1:]
    return value
