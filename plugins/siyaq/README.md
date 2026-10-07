# siyaq (سياق) - project knowledge, only when it matters

Part of [Nexika](../../README.md). *Siyaq* means context.

CLAUDE.md is loaded into every session, whether the task needs it or not. siyaq keeps project
knowledge out of the context until a prompt or a file Claude touches makes it relevant, then
adds just that piece.

## How it works

```
your docs ─────────► index (automatic): every heading section of docs/**, READMEs, CONTRIBUTING,
.siyaq/entries/ ───►   ARCHITECTURE, adr/** + your hand-written entries; rebuilt by itself when
                       a source changes, so there is no index to forget
prompt ────────────► language-aware words (Arabic included) ─► relevance ranking (BM25)
                       ─► up to 3 entries within a token budget (summary first, full if strong)
Read/Edit a file ──► the sections that mention that file or its (specific) folder
once per session ──► never sent twice; reset after /compact or /clear
usage ─────────────► shown / opened / no-match events ─► /siyaq:stats
```

### Matching that understands people
- **Any language:** Arabic letter variants are unified (أ إ آ → ا, ة → ه, ى → ي), diacritics
  removed, and light stemming handles both English (`validation` = `validating`) and Arabic
  (`الخصم` = `خصم`).
- **Code words:** `OrderService` and `order_service` both become `order service`.
- **Relevance, not keyword hits:** one shared body word is never enough; a hit on the section's
  own heading (not the doc title above it) or a keyword, or two different words, is required. A
  short prompt needs two words or a keyword, acknowledgements ("ok thanks", "تمام") match
  nothing, and the best matches win: a repeat never pulls in weaker sections instead.
- **Back-links are not topics:** a "Part of ..." link to a parent README does not tie the
  section to that README.
- **Bounded cost:** at most `top_k` entries and `budget_tokens` per prompt; big sections are sent
  as a summary with the exact lines to read for more. Tables and code blocks in a summary are kept
  whole, never cut halfway.
- **Less as the context fills:** with mizan installed, siyaq reads its context level: normal when
  fresh, half the budget and one entry fewer at mid, only the strongest match as a summary when
  full.
- **Fast on big repos:** hooks reuse the list of doc files for up to 30 seconds (sooner after a
  commit, checkout or staging, a config change, or a new doc Claude writes), so a tool call does
  not list and match every file in the repo again. A changed doc is still noticed at once; a new
  doc made outside Claude shows up within 30 seconds. `siyaq index` lists them again at once.

## Skills

| Skill | What it does |
|---|---|
| `/siyaq:add [topic]` | Capture knowledge as `.siyaq/entries/<slug>.md`, with synonyms in the team's languages and file paths, then verify it matches |
| `/siyaq:slim` | Move situational sections of CLAUDE.md into on-demand entries (with your approval) and report the tokens saved per session |
| `/siyaq:stats [days]` | What was injected, opened, never used, which topics had no knowledge, and dead references in docs |

## Hand-written entries

```markdown
---
title: Rolling back a deployment
keywords: rollback, revert release, تراجع, استرجاع
paths: deploy/**, .github/workflows/deploy.yml
inject: full        # optional: summary | full (default: decided by match strength and size)
---
1. ...
```

## The helper

The session note prints its path. `siyaq match "how do we roll back?"` shows scores and exactly
what would be injected; `siyaq entries`, `siyaq index` (sources, dead references) and
`siyaq stats` are there too.

## Configuration: `.siyaq.json`

```json
{
  "sources": ["docs/**/*.md", "**/README.md", "handbook/**/*.md"],
  "exclude": ["docs/archive/**"],
  "top_k": 3, "budget_tokens": 1200, "path_budget_tokens": 600,
  "min_score": 1.0, "full_max_chars": 1800,
  "mode": "on"
}
```

`"mode": "off"` or `SIYAQ=off` disables it. CLAUDE.md and CHANGELOG.md are never indexed
(CLAUDE.md is already loaded). Data lives in `~/.claude/nexika/siyaq/` (`SIYAQ_HOME` to move it);
the usage events (which hold words from your prompts) are readable only by you and rotate at 1 MB.

## Limits
- Matching is lexical (words, stems, synonyms you add), not semantic. A built-in glossary of
  common software and business words (deploy = نشر, invoice = فاتورة, rollback = تراجع ...) lets an
  Arabic question find English docs and the reverse; other terms match across languages only
  through `keywords` you add (as `/siyaq:add` does).
- Docs can be wrong; injected text tells Claude to trust the code when they disagree.
