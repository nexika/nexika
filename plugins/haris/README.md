# haris (حارس) - guards your machine and your accounts

Part of [Nexika](../../README.md). *Haris* means guard.

Claude runs real commands on your computer. Most are harmless; a few can delete your work, leak
a key, plant something that runs every time you log in, or publish something you cannot take
back. Text Claude reads (a web page, a README, a tool's output) can also try to talk it into
doing that. haris checks **every tool call before it runs** (subagents included) and decides:

| Decision | When | What you see |
|---|---|---|
| **allow** | provably safe: reading, running the project's own tests and builds, or exactly what you approved | nothing; it just runs |
| **pass** | no objection, but not provably safe (editing project files, installing packages, unknown programs) | Claude Code's own permission rules decide, as without haris |
| **ask** | risky but often intended: reading a secret, force-pushing your branch, deleting outside the project, merging, publishing, deploying | Claude Code asks you, with haris's reason |
| **deny** | dangerous: wiping your home folder, sending a secret off the machine, changing shell startup files, cron or git hooks, changing haris itself | refused, with the reason and the safe alternative |

Anything haris cannot read, and any error inside haris, becomes **ask**, never a silent allow.

## How it judges a command

```
command ─► shell parser ─► every command it would start ─► unwrap wrappers ─► action + target ─► decision
            quotes, escapes, $'..', ; & && || | |&,          env, sudo, nice, nohup, timeout,     read / run / write / delete
            newlines, ( ) { }, if/while/for/case,            xargs, find -exec/-delete,           egress / secret / persistence
            functions, $( ) ` ` <( ) >( ), heredocs          bash -c, eval, source, python -c,    remote / self ...
            (their $( ) runs too), redirections              node -e, ssh, docker/kubectl exec,   + where: project, temp, home,
                                                             git aliases, uv/poetry run ...       secret, system, haris itself
```

It never decides by the command's name alone. `rm -rf build` in the project passes; `rm -rf ~`
is refused whether it is written `\rm`, `/bin/rm`, `"rm"`, `$'\x72\x6d'`, after `env`, `nice`
or `sudo`, inside `bash -c '...'`, `eval`, a heredoc piped to `sh`, `find ~ -exec rm {} +`,
`echo ~ | xargs rm -rf`, `python3 -c "shutil.rmtree(...)"` or a git alias. Paths are resolved
first (`~`, `$HOME`, `..`, symlinks, globs, `cd` earlier in the line), so a detour does not
hide the target.

### What it protects

- **Your files:** deleting `/`, your home folder, a parent of the project or the project itself
  is refused; deleting or writing outside the project asks; the operating system's folders and
  disks are refused.
- **Secrets:** `~/.ssh`, `~/.aws`, `~/.config/gcloud`, `~/.kube`, `.env` (not `.env.example`),
  key files, `.netrc`, `~/.claude.json`, shell history, a process's environment, cloud and
  password-manager CLIs, `gh auth token`, `echo $GITHUB_TOKEN` ... reading them into the
  conversation asks, also through side doors such as `git show HEAD:.env` or `source .env`. Filling in the project's own `.env` is fine.
- **Data leaving the machine:** what `curl`, `wget`, `scp`, `rsync`, `nc`, `ssh`, `gh`, web
  searches, web fetches and MCP tools send is checked for secrets (the same rules as hafiz's
  redaction, in a copy a test keeps identical). A secret file, a secret read by another command
  (`cat .env | curl -d @-`, `$(cat ~/.ssh/id_rsa)`) or a literal key is **refused**.
- **Persistence:** shell profiles, `crontab`, launchd, systemd, `.git/hooks` and `.git/config`,
  git settings that run programs (`core.hooksPath`, `core.pager`, `!` aliases), Claude Code
  settings, hooks and plugins, `~/.local/bin`, PowerShell profiles: refused.
- **History and shared things:** force-pushing `main`, `master`, `develop`, `production`,
  `trunk`, `release/*` or the remote's default branch is refused; force-pushing your own
  branch, `reset --hard` with uncommitted work, `clean -f`, `branch -D` ask. Merging pull
  requests, releases, tags, publishing packages, deploying, `terraform apply/destroy`,
  `kubectl delete`, SQL `DROP`/`TRUNCATE`, deleting repos or buckets **always ask**, and no
  approval removes that (it backs [amin](../amin/README.md), which never merges for you).
- **Download and run:** `curl ... | sh`, `bash <(curl ...)`, `eval "$(curl ...)"`, running a
  file the same command just downloaded: ask (refused in strict).
- **haris itself:** its code, data, settings and the repo's `.haris.json` cannot be changed by
  Claude, `claude plugin disable haris` is refused, and running its hook by hand is refused.

### No self-approval

Approvals count only from what **you type**. `/haris:allow <exact command>` (or
`/haris:allow read <path>`, `/haris:allow write <path>`) is read by haris's own
`UserPromptSubmit` hook from your message, before Claude sees it. It approves exactly that
command or path for this session (`--project` keeps it for this project); `--remove` takes it
back. Claude cannot call the skill, cannot write haris's files and cannot run its hook, so it
cannot approve anything for itself. There are no broad rules like `git *`.

Some actions are refused in every profile: deleting your home folder or the system, writing to
persistence spots, sending secrets off the machine, force-pushing a protected branch, a remote
shell, a fork bomb and changes to haris. **No approval lifts these**; `/haris:allow` says so
instead of recording it. If you really want one, do it yourself, outside Claude.

### Scripts written and run in one command

When a command writes a script and runs it straight away (`echo '...' > x.sh && bash x.sh`, a
heredoc, `./x.sh`, `python3 x.py`), haris does not ask about the script blindly: it reads what
the script will run and judges that. A safe script goes through; a harmful one is stopped with
a plain warning, exactly as if the commands had been typed directly.

### Prompt injection

After each tool call haris scans the output (web pages, files, command output, MCP results) for
text that tries to give Claude orders: "ignore previous instructions", fake system messages,
"do not tell the user", requests to send secrets somewhere, hidden characters, instructions in
HTML comments, in English and Arabic. Claude is told the text is data, not a request from you,
and for your next 3 messages sending data out and irreversible remote actions are raised one
level (pass becomes ask, ask becomes deny).

## Profiles

| | relaxed | standard (default) | strict |
|---|---|---|---|
| reading, project tests and builds | allow | allow | allow (outside the project: pass) |
| editing and deleting in the project | allow | pass | edits pass, deletes ask |
| writing outside the project | pass | ask | ask |
| reading secrets, download-and-run | ask | ask | deny |
| persistence, haris, wiping, leaking secrets | deny | deny | deny |
| merges, releases, publishing, deploys | ask | ask | ask |

## Settings

`~/.claude/nexika/haris/config.json` is yours: it can loosen or tighten. A repository's
`.haris.json` can **only tighten** (a cloned repo cannot switch haris off).

```json
{
  "profile": "standard",
  "mode": "on",
  "ask": ["terraform plan", "make deploy"],
  "deny": ["kubectl delete"],
  "allow": ["npm publish --dry-run"],
  "protected_branches": ["staging"],
  "secret_paths": ["*/secrets/*"],
  "taint_turns": 3
}
```

`mode`: `on` (default, protecting from day one), `watch` (records what it would do, stops
nothing) or `off`. `ask`/`deny` are command prefixes matched after unwrapping (`*` matches one
word), so `env X=1 nice terraform apply` still matches `terraform apply`. `allow` holds exact
commands only, and only in your own file. In `.haris.json` only `profile` (stricter),
`ask`, `deny`, `protected_branches`, `secret_paths` and a larger `taint_turns` count.

## Skills

| Skill | What it does |
|---|---|
| `/haris:why [n]` | what haris asked about or refused, why, and the safe way forward |
| `/haris:allow ...` | approve one exact command or path (typed by you; Claude cannot call it) |
| `/haris:status` | profile, mode, settings, taint and approvals |
| `/haris:audit [--days N]` | the audit log |

The helper behind them: `haris why`, `haris status`, `haris audit`, `haris approvals`,
`haris check "<command>"` (what haris would decide, without running it) and `haris export
--json`.

## Data

In `~/.claude/nexika/haris/` (`HARIS_HOME` moves it), owner-only (folders 0700, files 0600):
`config.json`, `sessions/<id>.json` (taint and session approvals, kept 7 days),
`approvals.json` (`--project` approvals), `audit.jsonl` (every ask, refusal, approval and
injection warning; secrets in commands replaced with `[secret]`; rotated at 1 MB) and
`active/<id>`. Nothing is sent anywhere.

## Working with the other Nexika plugins

- **itqan:** its guard steps aside in sessions haris guards (haris covers its rules and more);
  the workflow, reviews and checklists are unchanged.
- **amin:** merges and releases always ask, whatever the profile or approvals.
- **hafiz:** the same secret rules (`secrets.py` is a copy, kept identical by a test).
  `haris export --json` (schema `nexika.haris/1`: profile, mode, session taint, the last week's
  asks, refusals and approvals) is there for hafiz and the others to read, and `/haris:allow`
  offers to record a lasting approval as a hafiz decision.
- **Shared startup budget:** haris's start note is under 600 bytes.

## Speed and testing

Every check is pure Python (stdlib only, 3.10+), with no network and no AI call; it runs git
only for `git commit`, `reset --hard` and `checkout`/`restore` (with every program-running git
option switched off). `tests/haris_corpus.tsv` holds 588 adversarial and ordinary commands
(339 of them dangerous) with their expected decisions, and CI fails unless no dangerous
command is missed, fewer than 2% of ordinary commands are blocked, and checks stay under 50 ms.

## Limits

- haris is a guard, not a sandbox. It judges each action before it runs; it does not follow a
  process while it runs. A program or script it cannot see into (a script already on disk,
  `make`, a binary) is left to Claude Code's own permission rules, and code built to hide what
  it does can get past any static check. Inline code (`python -c`, `node -e`) is never approved.
- PowerShell gets a lighter reading than bash (common cmdlets and aliases); a full PowerShell
  parser is planned.
- Prompt-injection scanning matches known patterns; it cannot understand every way text can
  try to steer a model.

## Credit

The idea of a permission guard plugin came from
[claude-caliper](https://github.com/nikhilsitaram/claude-caliper) by nikhilsitaram (MIT).
haris is written from scratch with a different design: a real shell parser, decisions by
action and target instead of command names, exact approvals only from what you type, and
protection of secrets, persistence spots and itself.
