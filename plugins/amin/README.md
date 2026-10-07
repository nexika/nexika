# amin (أمين) - a maintainer that never merges for you

Part of [Nexika](../../README.md). *Amin* means the trustworthy keeper.

amin takes the repetitive part of maintaining a GitHub repository - sorting issues, turning an
issue into a reviewed pull request, writing changelogs, choosing versions, tagging and
publishing releases - and leaves every decision, and every merge, to you.

## Skills

| Skill | What it does | Your role |
|---|---|---|
| `/amin:setup` | Confirms the projects and versions it detected, adds the change-notes folder, the CI rule and the `no-changelog` label | approve, merge the setup PR |
| `/amin:triage` | Unlabeled issues, likely duplicates and stale issues, with proposed labels and reasons | approve what is applied (it never closes issues) |
| `/amin:work <issue>` | Isolated worktree and branch, plan → tests first → implement → verify (via `itqan:ship` if installed), a change note, a PR with `Closes #N` | approve the plan, review and merge the PR |
| `/amin:release` | Change notes → versions with reasons → a release PR (versions + CHANGELOG) → after your merge: checks, tag, GitHub Release | approve the notes and versions, merge the release PR, approve publishing |

There is **no merge command**: a human always merges.

## Change notes

Every pull request that changes a project adds one small file:

```
changelog.d/<project>/<id>.<type>.md        single-project repos: changelog.d/<id>.<type>.md
```

`<id>` is the PR or issue number; `<type>` decides the version bump:

| Type | Bump | (0.x versions) |
|---|---|---|
| `breaking`, `removed` | major | minor |
| `added`, `changed`, `deprecated` | minor | minor |
| `fixed`, `security` | patch | patch |

One file per PR means no merge conflicts in CHANGELOG.md. `/amin:work` writes the note for you;
by hand: `amin fragment add <project> fixed "What changed, for users" --id 42`. A CI job
(`amin check-fragment`) fails a PR that changes a project without a note, unless the PR is
labelled `no-changelog`. It also fails empty notes and notes outside a project's notes folder
(they would never be released), and deleting a note only counts as a release when the PR also
changes that project's CHANGELOG or version. CI runs the base branch's copy of the checker.

## Releases

```
amin plan                       barq   release   0.1.0 -> 0.2.0   2 notes: added, fixed
amin prepare barq               bumps plugin.json, writes plugins/barq/CHANGELOG.md, deletes the notes
  └─ you merge the release PR
amin publish barq --dry-run     checks: default branch, clean, up to date, version, CHANGELOG
                                section, tag free, CI green on that commit
amin publish barq               tag barq-v0.2.0 + GitHub Release with the CHANGELOG section
```

First release of a project with no tags: `amin history <project>` lists the merged PRs that
touched it, so notes can be written from real history.

## Projects

Detected automatically:
- a plugin marketplace (`plugins/*/.claude-plugin/plugin.json`): one project per plugin, tags
  `<name>-v<version>`, `CHANGELOG.md` in each plugin folder;
- otherwise one project at the root, versioned in `package.json`, `pyproject.toml`,
  `.claude-plugin/plugin.json`, `Directory.Build.props` or a `.csproj` `<Version>`: tags `v<version>`.

Anything else: `.amin.json`

```json
{"projects": [{"name": "api", "path": "src/Api", "version_files": ["src/Api/Api.csproj"],
               "tag": "api-v{version}"}]}
```

## Requirements and limits
- `git` and an authenticated `gh` (GitHub only for now).
- amin keeps no state of its own: notes, changelogs and tags in the repo are the state.
- Version files supported: JSON `"version"`, TOML `version =`, MSBuild `<Version>`.
