---
name: fix
description: Apply SEO and AI-visibility fixes in the project's code (meta tags, schema, sitemap, robots.txt, llms.txt). Use when the user says "fix the SEO", "make us visible to ChatGPT/Gemini", "add schema / sitemap / llms.txt", or "manar fix".
argument-hint: "[audit file or issue ids]"
---

# Fix in the codebase

The manar helper is `python3 "${CLAUDE_PLUGIN_ROOT}/bin/manar"` (for a website the session note
names it too); below it is written `manar`.

1. **Know the problems.** Use the latest `.manar/audits/*.json` (or run `/manar:audit` first).
2. **Know the framework.** Run `manar detect` and read the matching guide next to this plugin:
   `packs/<pack>.md` (nextjs, astro, aspnet, static, generic) plus `packs/geo.md` for content.
   Follow the guide's file locations and APIs; don't invent a parallel system.
3. **Plan, then approval.** List each fix: file, change, which audit finding it resolves. If the
   itqan plugin is installed, follow `itqan:ship` (branch, plan approval, tests, review);
   otherwise create a branch and ask for approval of the plan.
4. **Generate exact artifacts with manar** instead of writing them by hand:
   - `manar generate robots --origin https://domain [--block-training]`
   - `manar generate sitemap|llms <url-or-built-folder> --name ... --summary ...`
   - `manar generate schema organization|website|software|sourcecode|article name=.. url=.. same_as=..`
   Ask the user for facts you can't know (official name, profiles for sameAs, summary).
5. **Implement**, build the site, and **re-audit the build** (`manar audit <built folder>
   --base-url ...`), then `manar diff` to show what was fixed.
6. **Pull request** with the before/after, and a change note if the repo uses amin
   (`amin fragment add <project> fixed|added "..." --id <PR>`). The user merges.
7. After deployment, suggest `/manar:visibility` to measure the effect over the next weeks.

Never claim a fix will make the site rank first: say it removes known obstacles and makes
the site easier to understand and cite.
