# barq ⚡ - many operations, one call

Part of [Nexika](../../README.md). *barq* (برق) means lightning.

Claude Code normally reads one file, waits, greps once, waits, runs `git status`, waits, and
every round-trip re-sends the whole conversation. barq answers several questions in **one call**,
and sends back **less text** for each of them.

```bash
barq 'read:src/app.py' 'grep:TODO:src' 'git-status'
```

## Ops

| Op | What it does |
|---|---|
| `read:PATH` | Whole file. **Seen-before cache:** a repeated read of an unchanged file returns one line; a changed file returns only the diff |
| `read:PATH:START[:END]` | A line range |
| `read:PATH@Symbol` | Just one class / function / method (`@UserService.Login` works too) |
| `read:PATH:outline` | Signatures only, with line ranges |
| `read:PATH:full` | Whole file, bypassing the cache |
| `read:PATH:raw` | Whole file, exact text without secret masking (use it before editing a masked file) |
| `grep:REGEX[:PATH[:MAX]]` | Search the project (respects `.gitignore`) |
| `glob:PATTERN[:PATH]` | Files matching `**/*.cs`, ... |
| `tree[:PATH[:DEPTH]]` | Directory tree, deep folders summarized |
| `map[:PATH]` | Outline of every source file under PATH |
| `info` | Languages, stacks, manifests and the build/test/lint commands |
| `run:test` / `run:build` / `run:lint` | Runs the command and returns **only** the verdict, failures and errors |
| `git-status[:full]` | Branch, ahead/behind, changes, stashes, and the suggested next step |
| `stats[:today\|week\|month\|all]` | What barq saved: round-trips, bytes, estimated tokens |

Symbols and outlines: Python (exact, via `ast`), C#, Java, Kotlin, JS/TS, Go, Rust, C/C++, PHP,
Swift, Dart, Scala (declaration patterns + brace matching), Markdown (headings).

`run` understands pytest, `dotnet test`, `dotnet build`/MSBuild, jest/vitest, `go test`,
cargo and tsc output, with a generic fallback for everything else.

Quote every op on the command line: shells expand `*` and some treat `@` specially.

### JSON form

For arguments that contain `:` or spaces, or for options the short form doesn't have:

```bash
barq '[{"op":"grep","pattern":"TODO: fix","path":"src","ignore_case":true,"glob":"*.cs"},
       {"op":"run","cmd":"dotnet test --filter Auth"}]'
```

Add `--json` for machine-readable output, `--fresh` to ignore the cache.

## Project config: `.barq.json`

```json
{
  "commands": { "test": "dotnet test Api.Tests", "build": "dotnet build Api.sln" },
  "ops": {
    "db-status": { "cmd": "docker compose ps {args}", "safety": "read",
                   "description": "Containers and their health" }
  }
}
```

`commands` overrides what `info`/`run` detect. `ops` adds custom ops (`barq db-status`).
Ops marked `"safety": "read"` may run in parallel with other read ops.

## Safety

- **Path fence:** paths outside the project (git root, or cwd) are refused, including via
  symlinks. `BARQ_ALLOW_OUTSIDE=1` lifts it.
- **Secret masking:** tokens (GitHub, GitLab, Anthropic, OpenAI, AWS, Slack, Google, JWT),
  bearer tokens, private keys, passwords in URLs, every value in `.env` files, and values of
  keys whose last word names a secret (`DB_PASSWORD`, `GITHUB_TOKEN`, `ClientSecret`, `api_key`)
  are printed as `[masked]`. Keys that only mention one (`MAX_TOKENS`, `token_type`,
  `jsonwebtoken`), versions, code expressions and placeholders are left as written. When a read
  masks something its header says so; `read:PATH:raw` gives the exact text for editing.
  Best effort; `BARQ_NO_MASK=1` disables it.
- Read ops run in parallel; `run` and custom exec ops always run one after another.

## How it plugs into Claude Code

The SessionStart hook puts `bin/` on `PATH` (via `CLAUDE_ENV_FILE`), passes the session id to
barq for the cache, resets the cache after `/compact` or `/clear` (Claude no longer has the
old content), and tells Claude how to use barq.

Data lives in `~/.claude/nexika/barq/` (`BARQ_HOME` to move it): `stats.jsonl` and
per-session cache files, deleted after 7 days.

## Try it

```bash
claude --plugin-dir ./plugins/barq     # from the repo root
./plugins/barq/bin/barq info git-status
```
