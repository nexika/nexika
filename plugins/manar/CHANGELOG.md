# Changelog

All notable changes to manar are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and versions follow [Semantic Versioning](https://semver.org/).

## [0.2.0] - 2026-10-08

### Added
- Publishes the last audit's checklist score per project to the shared status file (status/manar.json), so mizan can show it. (#67)
- manar audit reports broken internal links (pages that return an error, and in a built folder links to pages that don't exist), pages missing from the sitemap, and JSON-LD missing the properties its schema.org type needs (Article without author, FAQPage without mainEntity, ...). The new audit --fail-on SEVERITY exits with 1 when a finding is that severe or worse, for CI. (#74)

### Fixed
- manar audit now checks hreflang: invalid language codes (such as "arabic"), relative or other-site alternates, a missing x-default, missing return links and alternates that point to broken pages. It also flags a canonical that points to another page, and marks one that points to another language version as high, because that drops the page from search. (#41)
- manar visibility reports a 95% range for every rate (counting prompts, not correlated samples), says whether a before/after is a real change or within noise, and refuses to compare runs whose prompts or models differ. (#42)
- Hooks exit at once inside a Nexika background model call (NEXIKA_BACKGROUND=1), so other plugins' paid `claude -p` jobs no longer start this plugin's hooks. (#45)
- manar visibility counts a source as cited only when the answer links it, the same way for every engine (sources an engine only read are kept apart); Gemini's redirect links are resolved, so domains with a path such as github.com/you/repo can be credited; and visibility plan shows a rough cost estimate. (#62)
- manar diff compares the last two audits of the same site (pass a target to pick one) instead of the last two of any site; robots.txt rules that close a section such as /docs/ to an AI search crawler are reported; a built folder's address is taken from --base-url, a CNAME file or the home page's canonical, and the audit stops instead of guessing; and Arabic passages are no longer scored lower for having no capital letters. (#84)

## [0.1.0] - 2026-10-06

### Added
- manar, be found by search engines and AI assistants: deterministic audits (including every AI crawler, llms.txt and passage citability in English and Arabic), fixes written into Next.js, Astro, ASP.NET Core and static sites, and measured AI visibility in Gemini, Perplexity, ChatGPT and Claude, compared across releases.
