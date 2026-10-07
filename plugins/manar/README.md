# manar (منار) - be found by search engines and AI assistants

Part of [Nexika](../../README.md). *Manar* means lighthouse.

Most SEO plugins write reports. manar **fixes your code** and **measures whether AI assistants
actually mention and cite you**, so you can see what each change did.

| Skill | What it does |
|---|---|
| `/manar:audit <url or built folder>` | Deterministic checks of indexing, titles, descriptions, canonical, language and hreflang (codes, absolute URLs, return links, x-default), structured data, sitemap, robots.txt rules for every AI crawler, llms.txt, JavaScript-only content, and how quotable each passage is (English and Arabic) |
| `/manar:fix` | Writes the fixes into your project with the framework's own conventions (Next.js, Astro, ASP.NET Core, static / GitHub Pages), re-audits the build, and opens a pull request (via itqan and amin when installed) |
| `/manar:visibility` | Asks Gemini (Google Search grounded), Perplexity, ChatGPT search and Claude search your customers' real questions, several times each, and reports how often you are **mentioned** and **cited**, who is cited instead, and the change since the last release |

## Why it's different
- **Fixes, not just findings.** Framework guides in `packs/` and exact generators (robots.txt,
  sitemap.xml, llms.txt, JSON-LD) instead of copy-paste snippets.
- **Measured, not estimated.** AI visibility comes from the engines' own APIs with web search,
  as rates over several samples, labelled *Measured*; heuristics (citability) are labelled
  *Estimated*. No SEO vendor subscription needed: one free Gemini key is enough to start.
- **Before/after tied to releases.** Audits and measurements are stored in `.manar/` with the git
  ref, so `manar diff` and the visibility report show what changed after each release.
- **Raw HTML, real crawler.** Pages are fetched and parsed directly (nothing stripped from
  `<head>`), with a bounded same-site crawler, robots.txt respected, and an offline mode for a
  built folder (great in CI).
- **Every AI crawler, explained.** Search and assistant bots (must be allowed to be cited) are
  separated from training bots (a policy choice).
- **Arabic and any language.** `lang`/`dir="rtl"` checks, Arabic passages scored, panel questions
  in every language you sell in.

## Commands (the helper the skills use)

```
manar audit URL|FOLDER [--max-pages N] [--allow-local] [--base-url URL] [--json]
manar diff [TARGET]
manar detect
manar generate robots --origin URL [--block-training]
manar generate sitemap|llms URL|FOLDER --name N --summary S
manar generate schema organization|website|software|sourcecode|article name=.. url=.. same_as=a,b
manar visibility init|plan|run|report [--engines gemini,perplexity] [--max-calls N]
```

## Keys for measuring AI visibility (optional)
`GEMINI_API_KEY`, `PERPLEXITY_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY` from the environment
only (never stored). Override models with `MANAR_GEMINI_MODEL` etc. A run refuses to make more than
`--max-calls` (default 30) calls.

## Honest limits
- Nobody can guarantee the first position in Google, ChatGPT or Gemini. manar removes known
  obstacles, makes the site easy to understand and cite, and measures the result.
- A few samples are noisy: each rate has a 95% range (counted per prompt, since samples of one
  prompt move together), a before/after is called a real change only when the ranges don't
  overlap, and runs with other prompts or models are not compared.
- JavaScript is not executed; pages that need it are reported as a problem (as crawlers see them).
- Pure Python standard library; no paid services required.
