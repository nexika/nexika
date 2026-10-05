---
name: audit
description: Audit a website or a built site folder for search engines and AI assistants - indexing, titles and descriptions, canonical, language, structured data, sitemap, robots.txt rules for every AI crawler, llms.txt, client-side rendering, and how quotable the content is - then give a prioritised fix list. Use when the user says "SEO audit", "why don't we show up in Google / ChatGPT / Gemini", "check our site", or "manar audit".
argument-hint: "<URL or built folder>"
---

# Audit

The manar helper is printed in the session note ("manar helper: python3 .../bin/manar"); below
it is written `manar`.

1. Target: $ARGUMENTS. A live URL, or a built folder (`dist/`, `_site/`, `out/`, `wwwroot/`) with
   `--base-url https://the-real-domain`. For a local dev server add `--allow-local`.
2. Run `manar audit <target>` (default 50 pages; `--max-pages N`). It saves the result in
   `.manar/audits/` so later audits can be compared with `manar diff`.
3. Explain the result in plain words:
   - the **checklist score** is "known problems found", not a ranking prediction;
   - **AI crawlers**: search/assistant bots must be allowed to be cited; training bots are a
     policy choice;
   - **citability** is an *Estimated* heuristic; say so.
4. Give a short, ordered plan: blockers first (noindex, blocked crawlers, JS-only content), then
   entity/structured data, sitemap/robots/llms.txt, then page-level content.
5. Offer `/manar:fix` to apply the fixes in the codebase, and `/manar:visibility` to measure AI
   mentions before and after.
