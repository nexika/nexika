"""Where a path lives, which decides what touching it means.

    self         haris's own code, data and settings (and the repo's .haris.json), and what haris guards
                 beside itself: mizan's code and data, itqan's proofs, tabib's diagnoses, the status files
    persistence  files that run code later: shell profiles, cron, launchd, systemd, git hooks,
                 Claude Code settings and plugins, PATH folders, PowerShell profiles
    secret       keys, tokens and credential stores (.env.example and *.pub are fine)
    system       the operating system (/etc, /usr, /bin, disks under /dev, C:/Windows ...)
    config-exec  project files that make tools run commands (.mcp.json, .envrc, .vscode/tasks.json)
    git          inside .git (hooks and config are persistence)
    project      inside the project, or inside another worktree of the same git repository
    memory       Claude Code's memory folder for this project (~/.claude/projects/<project>/memory)
    temp         temporary folders
    home         elsewhere in your home folder
    outside      anywhere else
    null         /dev/null and the standard streams

Paths are resolved first (~, $HOME, .., symlinks), so a link or a detour cannot hide the target.
"""
from __future__ import annotations

import fnmatch
import os
import re
from pathlib import Path

PLUGIN_ROOT = str(Path(__file__).resolve().parent.parent)
UNKNOWN = "\x00"

SECRET_NAME = re.compile(
    r"""(?ix)^(?:
        \.env(?:\.(?!example$|sample$|template$|dist$|defaults?$)[\w.-]+)?
      | id_(?:rsa|dsa|ecdsa|ed25519)(?:_sk)?
      | .*\.(?:pem|key|p12|pfx|jks|keystore|kdbx|ppk|tfvars|tfstate|tfstate\.backup)
      | credentials(?:\.json|\.toml)? | \.credentials\.json | \.netrc | _netrc | \.npmrc | \.pypirc
      | \.git-credentials | \.pgpass | \.htpasswd | \.my\.cnf | \.boto | \.s3cfg | master\.key
      | secrets?\.(?:ya?ml|json|toml) | service[-_]?account.*\.json | \.vault-token | \.dockercfg
      | kubeconfig | shadow | gshadow
    )$""")
SECRET_HOME_DIRS = (".ssh", ".aws", ".gnupg", ".config/gcloud", ".azure", ".kube", ".password-store",
                    ".config/gh", ".config/hub", ".terraform.d", ".oci", ".config/doctl", ".config/op",
                    "Library/Keychains", ".local/share/keyrings", ".mozilla", ".config/google-chrome",
                    ".config/chromium", "Library/Application Support/Google/Chrome", "Library/Cookies",
                    ".config/rclone", ".docker/config.json", ".cargo/credentials", ".cargo/credentials.toml",
                    ".claude/.credentials.json", ".claude.json", ".bash_history", ".zsh_history", ".zhistory",
                    ".histfile", ".sh_history", ".local/share/fish/fish_history", ".python_history",
                    ".node_repl_history", ".psql_history", ".mysql_history", ".sqlite_history",
                    ".rediscli_history", ".local/share/powershell/PSReadLine",
                    "AppData/Roaming/Microsoft/Windows/PowerShell/PSReadLine")
SECRET_OK = re.compile(r"(?i)(\.pub|/known_hosts(\.old)?|/\.ssh/config)$")
PERSIST_HOME = (".bashrc", ".bash_profile", ".bash_login", ".bash_logout", ".profile", ".zshrc", ".zshenv",
                ".zprofile", ".zlogin", ".zlogout", ".kshrc", ".cshrc", ".tcshrc", ".config/fish",
                ".ssh/authorized_keys", ".ssh/authorized_keys2", ".ssh/rc", ".ssh/config", ".gitconfig",
                ".config/git", ".config/autostart", ".config/systemd", "Library/LaunchAgents",
                ".claude/settings.json", ".claude/settings.local.json", ".claude.json", ".claude/plugins",
                ".claude/hooks", ".local/bin", "bin", ".config/powershell", "Documents/PowerShell",
                "Documents/WindowsPowerShell", ".config/environment.d", ".pam_environment", ".xprofile",
                ".xinitrc", ".xsession", "AppData/Roaming/Microsoft/Windows/Start Menu/Programs/Startup")
PERSIST_SYSTEM = ("/etc/cron", "/etc/crontab", "/var/spool/cron", "/etc/systemd", "/lib/systemd",
                  "/usr/lib/systemd", "/etc/init.d", "/etc/rc.local", "/Library/LaunchAgents",
                  "/Library/LaunchDaemons", "/etc/profile", "/etc/bash.bashrc", "/etc/zshrc", "/etc/zsh",
                  "/etc/environment", "/etc/sudoers", "/etc/ld.so.preload")
PERSIST_PROJECT = (".git/hooks", ".git/config", ".claude/settings.json", ".claude/settings.local.json",
                   ".claude/hooks")
CONFIG_EXEC_PROJECT = (".mcp.json", ".envrc", ".vscode/tasks.json", ".vscode/settings.json",
                       ".devcontainer", ".claude/agents", ".claude/commands", ".claude/skills")
SYSTEM_DIRS = ("/etc", "/usr", "/bin", "/sbin", "/lib", "/lib32", "/lib64", "/boot", "/sys", "/proc", "/dev",
               "/var", "/opt", "/root", "/srv", "/snap", "/System", "/Library", "/private/etc",
               "/private/var", "/Applications", "/Volumes", "/mnt", "/media", "C:/Windows",
               "C:/Program Files", "/c/Windows", "/cygdrive/c/Windows")
NULL_DEVICES = ("/dev/null", "/dev/stdout", "/dev/stderr", "/dev/stdin", "/dev/tty", "/dev/zero",
                "/dev/random", "/dev/urandom")
NULL_PREFIXES = ("/dev/fd/", "/proc/self/fd/")
TEMP_DIRS = ("/tmp", "/var/tmp", "/private/tmp", "/private/var/folders", "/var/folders", "/dev/shm")
DEVICE = re.compile(r"^/dev/(?:sd|hd|vd|xvd|nvme|mmcblk|disk|rdisk|mapper/|md|loop|dm-)")
DRIVE = re.compile(r"^[A-Za-z]:/")


def norm(path: str) -> str:
    path = os.path.normpath(path.replace("\\", "/"))
    return path.replace("\\", "/")


def under(path: str, base: str) -> bool:
    return path == base or path.startswith(base.rstrip("/") + "/")


def data_home() -> str:
    return norm(os.path.expanduser(os.environ.get("HARIS_HOME") or "~/.claude/nexika/haris"))


GUARDED_PLUGINS = ("haris", "mizan")
TRANSCRIPT = re.compile(r"^(.*?/\.claude/projects/[^/]+)/[^/]")
# At any depth under a folder you approved outside the project, these still ask: they make git, tools,
# CI or Claude run things.
GUARDED_PARTS = {".git", ".claude", ".husky", ".githooks", ".vscode", ".devcontainer", ".envrc", ".mcp.json",
                 ".pre-commit-config.yaml", "CLAUDE.md"}


def memory_folder(transcript: str) -> str:
    """Claude Code's memory folder for the session's project, from the session's transcript path
    (~/.claude/projects/<project>/<session>.jsonl, set by Claude Code, not by Claude); "" if unknown."""
    m = TRANSCRIPT.match(norm(os.path.realpath(transcript))) if transcript else None
    return m.group(1) + "/memory" if m else ""


def guarded_inside(path: str, folder: str) -> bool:
    """`path`, below the approved `folder`, is a file that makes tools or Claude run things."""
    folder = folder.rstrip("/")
    rel = path[len(folder) + 1:] if under(path, folder) else path
    return bool(GUARDED_PARTS & set(rel.split("/"))) or "/.github/workflows/" in "/" + rel


def worktrees(root: str) -> tuple[str, ...]:
    """The other checkouts of `root`'s git repository (git worktree), read from .git without running git."""
    dot = root + "/.git"
    try:
        if os.path.isfile(dot):
            with open(dot, encoding="utf-8") as fh:
                line = fh.read(4096).strip()
            if not line.startswith("gitdir:"):
                return ()
            gitdir = norm(os.path.join(root, line[len("gitdir:"):].strip()))
            common = norm(os.path.dirname(os.path.dirname(gitdir)))  # <common>/worktrees/<name>
        elif os.path.isdir(dot):
            common = dot
        else:
            return ()
        trees = {norm(os.path.dirname(common))} if os.path.basename(common) == ".git" else set()
        for name in os.listdir(common + "/worktrees") if os.path.isdir(common + "/worktrees") else ():
            try:
                with open(f"{common}/worktrees/{name}/gitdir", encoding="utf-8") as fh:
                    trees.add(norm(os.path.dirname(fh.read(4096).strip())))
            except OSError:
                continue
    except OSError:
        return ()
    return tuple(sorted(t for t in trees if t != root and t.startswith("/")))


def guarded_homes() -> tuple[str, ...]:
    """mizan's data, itqan's proofs, tabib's diagnoses, lawha's check records and the shared status
    files (~/.claude/nexika/status): what the band shows and what siyaq, itqan and mizan read must
    come from the plugins, never from Claude."""
    return (norm(os.path.expanduser(os.environ.get("MIZAN_HOME") or "~/.claude/nexika/mizan")),
            norm(os.path.expanduser(os.environ.get("ITQAN_HOME") or "~/.claude/nexika/itqan")),
            norm(os.path.expanduser(os.environ.get("TABIB_HOME") or "~/.claude/nexika/tabib")),
            norm(os.path.expanduser(os.environ.get("LAWHA_HOME") or "~/.claude/nexika/lawha")),
            norm(os.path.expanduser(os.environ.get("NEXIKA_STATUS_HOME") or "~/.claude/nexika/status")))


class Where:
    """Places paths for one project: its root, the home folder and any extra secret globs."""

    def __init__(self, root: str, secret_globs: list[str] | None = None, memory: str = ""):
        self.root = norm(os.path.realpath(root))
        self.memory = memory
        self._trees: tuple[str, ...] | None = None
        self.home = norm(os.path.realpath(os.path.expanduser("~")))
        self.secret_globs = list(secret_globs or [])
        import tempfile  # loads shutil and random: only when a Where is built
        temp = norm(os.path.realpath(tempfile.gettempdir()))
        self.temps = tuple(sorted({*TEMP_DIRS, temp}))
        running = () if self.develops(PLUGIN_ROOT) else (PLUGIN_ROOT,)
        self.self_paths = (*running, data_home(), *guarded_homes(), norm(self.root + "/.haris.json"))

    def develops(self, path: str) -> bool:
        """`path` is source being worked on in this project: inside a git checkout, not an installed copy
        under ~/.claude. Only the installed haris and its data are protected (#119)."""
        path = norm(os.path.realpath(path))
        return (under(path, self.root) and os.path.exists(self.root + "/.git")
                and not under(self.root, self.home + "/.claude"))

    def checkout(self, name: str) -> bool:
        """This project holds the source of plugin `name` (plugins/<name>/<name>, or <name>/ at the top)."""
        return any(os.path.isfile(f"{base}/{name}/__init__.py") and self.develops(base)
                   for base in (f"{self.root}/plugins/{name}", self.root))

    def trees(self) -> tuple[str, ...]:
        """The project and the other worktrees of its repository (#122): one repository, one project."""
        if self._trees is None:
            self._trees = (self.root, *worktrees(self.root))
        return self._trees

    def project_of(self, path: str) -> str | None:
        """The checkout `path` is in: the project root, or a worktree of the same repository (never the
        worktree's own folder: deleting a whole worktree is not an ordinary edit)."""
        if under(path, self.root):
            return self.root
        if under(path, self.home + "/.claude"):
            return None
        return next((t for t in self.trees()[1:] if path.startswith(t + "/")), None)

    def resolve(self, value: str, cwd: str | None) -> str | None:
        """An absolute, normalized path with symlinks followed; None when it is not known."""
        if not value or UNKNOWN in value:
            return None
        value = value.replace("\\", "/")
        if value == "~" or value.startswith("~/"):
            value = self.home + value[1:]
        if not value.startswith("/") and not DRIVE.match(value):
            if cwd is None:
                return None
            value = cwd + "/" + value
        if DRIVE.match(value):
            return norm(value)
        try:
            return norm(os.path.realpath(value))
        except (OSError, ValueError):
            return norm(value)

    def home_rel(self, path: str) -> str | None:
        return path[len(self.home) + 1:] if path.startswith(self.home + "/") else None

    def is_self(self, path: str) -> bool:
        if any(under(path, p) for p in self.self_paths):
            return True
        rel = self.home_rel(path)
        return bool(rel and rel.startswith(".claude/plugins/") and
                    any(f"/{name}" in rel[len(".claude/plugins"):] for name in GUARDED_PLUGINS))

    def is_persistence(self, path: str) -> bool:
        rel = self.home_rel(path)
        if rel and any(under(rel, p) for p in PERSIST_HOME):
            return True
        if any(under(path, p) or path.startswith(p) for p in PERSIST_SYSTEM):
            return True
        return any(under(path, f"{t}/{p}") for t in self.trees() for p in PERSIST_PROJECT)

    def is_secret(self, path: str) -> bool:
        if SECRET_OK.search(path):
            return False
        if SECRET_NAME.match(os.path.basename(path)):
            return True
        rel = self.home_rel(path)
        if rel and any(under(rel, d) for d in SECRET_HOME_DIRS):
            return True
        if re.match(r"^/proc/[^/]+(?:/task/[^/]+)?/environ$", path):
            return True
        if path in ("/etc/shadow", "/etc/gshadow", "/etc/sudoers") or re.match(r"^/etc/ssh/ssh_host_\w+_key$",
                                                                               path):
            return True
        return any(fnmatch.fnmatch(path, g) for g in self.secret_globs)

    def is_system(self, path: str) -> bool:
        if path == "/" or DEVICE.match(path):
            return True
        if any(under(path, t) for t in self.temps):
            return False
        return any(under(path, d) for d in SYSTEM_DIRS)

    def place(self, path: str | None) -> str:
        if path is None:
            return "unknown"
        if path in NULL_DEVICES or path.startswith(NULL_PREFIXES):
            return "null"
        if self.is_self(path):
            return "self"
        if self.is_persistence(path):
            return "persistence"
        if self.is_secret(path):
            return "secret"
        if self.is_system(path):
            return "system"
        if self.memory and under(path, self.memory) and path != self.memory:
            return "memory"
        tree = self.project_of(path)
        if tree:
            if any(under(path, f"{tree}/{p}") for p in CONFIG_EXEC_PROJECT):
                return "config-exec"
            if under(path, tree + "/.git"):
                return "git"
            return "project"
        if under(path, self.home) and not any(under(path, t) and under(t, self.home) for t in self.temps):
            return "home"
        if any(under(path, t) for t in self.temps):
            return "temp"
        return "outside"

    def critical(self, path: str) -> bool:
        """Deleting this would wipe far more than one project: /, home, a parent of the project."""
        if path in ("/", "/home", "/Users", "C:", "C:/") or path in SYSTEM_DIRS:
            return True
        return under(self.root, path) or under(self.home, path)

    def holds(self, path: str) -> str | None:
        """For a folder being deleted or moved: the most protected place inside it."""
        prefix = path.rstrip("/") + "/"
        if any(p.startswith(prefix) for p in self.self_paths):
            return "self"
        if (self.home + "/.claude/plugins").startswith(prefix):
            return "self"
        inside = [f"{self.home}/{p}" for p in PERSIST_HOME] + list(PERSIST_SYSTEM)
        inside += [f"{self.root}/{p}" for p in PERSIST_PROJECT if not p.startswith(".git/")]
        if any(p.startswith(prefix) for p in inside):
            return "persistence"
        if any(f"{self.home}/{d}".startswith(prefix) for d in SECRET_HOME_DIRS):
            return "secret"
        return None
