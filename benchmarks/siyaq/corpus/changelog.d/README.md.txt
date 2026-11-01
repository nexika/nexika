# Change notes

Every pull request that changes a plugin adds one note here, used by `/amin:release` to write
the plugin's CHANGELOG and choose its next version:

```
changelog.d/<plugin>/<PR or issue number>.<type>.md
```

The file holds one sentence (or a few `- ` bullets) written for users: what changed for them,
not how the code changed.

| Type | Use for | Version bump |
|---|---|---|
| `breaking` | users must change something | major (minor while 0.x) |
| `added` | new capability | minor |
| `changed` | different behaviour of something existing | minor |
| `deprecated` | still works, will be removed | minor |
| `removed` | taken out | major (minor while 0.x) |
| `fixed` | bug fix | patch |
| `security` | security fix | patch |

Add one with `python3 plugins/amin/bin/amin fragment add <plugin> <type> "<text>" --id <PR>`.
CI fails a PR that changes a plugin without a note; label the PR `no-changelog` when no note
makes sense (e.g. internal refactoring with no visible change).
