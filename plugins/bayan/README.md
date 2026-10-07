<!-- bayan: off (this page quotes the phrases bayan removes) -->
# bayan (بيان): write like a clear, friendly person

Part of [Nexika](../../README.md). *Bayan* means clarity and eloquence.

With bayan installed, Claude explains things so that someone who has never written code can follow,
in English or Arabic, without getting anything wrong. It also removes the habits that make text
sound machine-written. This covers everything Claude writes in the session, including the output
of the other Nexika plugins: prof's lessons and reports, amin's release notes, manar's audits.

| Skill | What it does |
|---|---|
| `/bayan:level` | Choose the reader: `no-code`, `junior` or `developer`. Saved for future sessions. |
| `/bayan:write <file or text>` | Rewrites it for that reader. Facts, numbers, links and code stay exactly as they were. |
| `/bayan:check <file or text>` | Lists, line by line, what is hard to read or sounds machine-made, with a better wording. |

## What happens on its own
- **At the start of each session**, Claude gets a short writing guide for your reader level.
- **After Claude writes or edits a Markdown file** (`.md`, `.mdx`), bayan cleans **only the part
  Claude just wrote**: it removes hidden characters (zero-width spaces and the like), AI signature
  lines, filler sentences (`Great question!`, `I hope this helps!`) and wordy phrases (`in order to`,
  `it's worth noting that`), and turns em dashes between words into commas (dashes in headings,
  table rows and ranges such as `Mon – Fri` stay). Then it tells Claude which of those lines still
  need rewriting. When Claude rewrites a whole existing file, only the lines that changed count as
  Claude's. Text written by people is left alone, and so are code, front matter, HTML, link targets,
  comments, files outside the project, symlinks and test fixtures. Prompt files are never changed:
  `SKILL.md`, `CLAUDE.md`, `AGENTS.md` and anything in `.claude/`, `agents/` or `output-styles/`.
  `.txt` and `.rst` files are only checked, never changed.
- **Before a commit, tag, pull request or release**, bayan stops it if the message (or the message
  file) carries zero-width characters. When it carries an AI signature line
  (`Co-Authored-By: Claude ... <noreply@anthropic.com>`, `Generated with [Claude Code]`), bayan lets it
  through and tells Claude to leave the line out and how to turn it off with Claude Code's
  `attribution` setting; set `deny_signatures` to `true` to block it instead. Human co-authors are
  never touched.

Both languages are covered: for example `من الجدير بالذكر أن`, `تجدر الإشارة إلى أن` and
`علاوة على ذلك` are removed or flagged, and Arabic gets an Arabic comma when a dash is replaced.

## Works with Claude Code's built-ins

- **The `attribution` setting** decides whether Claude Code signs commits and pull requests. When
  you set it to keep the signature (or set the older `includeCoAuthoredBy` to `true`), bayan says
  nothing about it; it only suggests the setting when you haven't chosen. `deny_signatures` is
  still bayan's own stricter switch.
- **Output styles** change how Claude talks; bayan's note is about how the words read, so the two
  stack.

## Commands (used by the skills; also handy in CI)

```
bayan check FILE|- [--level no-code|junior|developer] [--json] [--min-score N]
bayan clean FILE... [--write] [--keep-dashes]
bayan level [no-code|junior|developer]
```

`--min-score` makes `check` exit with 1 below that score, so a CI job can keep docs readable.
Put `bayan: off` anywhere in a file to leave it alone. Settings live in
`~/.claude/nexika/bayan/config.json` (`level`, `auto_clean`, `block_signatures`, `deny_signatures`).
Without a `level` there, the Nexika profile's role picks it (`developer` → developer, `learner` →
junior, `writer` → no-code); with no role either, bayan writes for a developer.

## Honest limits
- The plainness score measures the habits in [the guide](guide/writing.md). It is **not an AI
  detector**. Nobody can promise what GPTZero, Copyleaks or any other detector will say: they
  change their models often and also flag text written by people, especially formal writing and
  writing by non-native speakers.
- bayan does not rewrite text over and over until a detector says "human". It aims for writing
  that real readers find clear and natural.
- A plugin can't edit Claude's chat replies after they are written. Those follow the guide;
  files are cleaned for certain.
- Pure Python standard library, nothing sent anywhere.
