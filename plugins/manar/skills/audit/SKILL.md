---
name: audit
description: Audit a website or built site folder for search engines and AI assistants, with a prioritised fix list. Use when the user says "SEO audit", "why don't we show up in Google / ChatGPT / Gemini", "check our site", or "manar audit".
argument-hint: "<URL or built folder>"
---

# Audit

The manar helper is `python3 "${CLAUDE_PLUGIN_ROOT}/bin/manar"` (for a website the session note
names it too); below it is written `manar`.

1. Target: $ARGUMENTS. A live URL, or a built folder (`dist/`, `_site/`, `out/`, `wwwroot/`) with
   `--base-url https://the-real-domain` (manar infers it from a CNAME file or the home page's
   canonical, and stops if it can't). For a local dev server add `--allow-local`.
2. Run `manar audit <target>` (default 50 pages; `--max-pages N`). It saves the result in
   `.manar/audits/` so later audits of the same site can be compared with `manar diff [target]`.
3. Explain the result in plain words:
   - the **checklist score** is "known problems found", not a ranking prediction;
   - **AI crawlers**: search/assistant bots must be allowed to be cited; training bots are a
     policy choice;
   - **citability** is an *Estimated* heuristic; say so.
4. Give a short, ordered plan: blockers first (noindex, blocked crawlers, JS-only content), then
   entity/structured data, sitemap/robots/llms.txt, then page-level content.
5. Offer `/manar:fix` to apply the fixes in the codebase, and `/manar:visibility` to measure AI
   mentions before and after.
