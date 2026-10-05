# manar pack: being understood and cited by AI assistants

What AI search tools can only do if you make it easy:

1. **Be fetchable.** Allow search/assistant crawlers (OAI-SearchBot, ChatGPT-User, PerplexityBot,
   Claude-SearchBot, Googlebot, Bingbot); serve text in the HTML (no JS-only content).
2. **Be one clear entity.** The same name everywhere; Organization or SoftwareApplication JSON-LD
   with `sameAs` to official profiles (GitHub, LinkedIn, X, package registries); an About page.
3. **Answer questions directly.** For each question customers ask, a section whose first sentence
   answers it ("Nexika is a set of Claude Code plugins that ..."), 40-300 words, with specifics
   (numbers, versions, limits, prices), and a heading phrased like the question.
4. **Be comparable.** Honest comparison and "how to choose" pages get cited for "best X" questions.
5. **Be present where AI looks.** Reputable third-party mentions (docs listings, awesome lists,
   articles, forums, package registries) are often cited more than your own site.
6. **Every language you sell in.** Separate, real pages per language with `lang`, `hreflang` and
   (for Arabic) `dir="rtl"`; questions in the panel in those languages.
7. **Measure, don't guess.** `/manar:visibility` before and after each release.

Don't: stuff keywords, hide text, publish thin AI-generated pages at scale, or claim guarantees.
