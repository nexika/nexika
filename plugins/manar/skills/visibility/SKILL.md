---
name: visibility
description: Measure whether AI assistants (Gemini with Google Search, Perplexity, ChatGPT search, Claude search) mention and cite the brand for real customer questions, in any language, as rates over several samples, compared with the previous run and with the git release in between. Use when the user asks "do ChatGPT/Gemini recommend us", "AI visibility", "are we cited", "did the SEO work", or "manar visibility".
argument-hint: "[init | plan | run | report]"
---

# AI visibility

The manar helper is printed in the session note; below it is written `manar`.

1. **Panel.** If `.manar/panel.json` doesn't exist, run `manar visibility init` and edit it with
   the user: `brand`, `aliases` (other spellings, product names), `domains` (site, GitHub repo),
   `samples` (3 is a good default), and 5-15 **real questions customers would ask without
   knowing the brand** ("best tool to ...", in the languages of the market, e.g. English and
   Arabic). Questions that contain the brand name prove nothing.
2. **Keys.** At least one: `GEMINI_API_KEY` (free tier; answers grounded in Google Search),
   `PERPLEXITY_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`. Keys stay in the environment;
   never write them to files. Models can be changed with `MANAR_<ENGINE>_MODEL`.
3. **Cost first.** `manar visibility plan` shows the number of API calls; confirm with the user.
4. **Measure.** `manar visibility run` (refuses above `--max-calls`, default 30). Results are
   appended to `.manar/visibility.jsonl` with the git ref (e.g. a release tag).
5. **Report** (`manar visibility report`): per engine, the share of answers that **mention** the
   brand and that **cite** (link) its domains; per prompt; and the sources cited instead (the
   real competition). Each rate comes with a 95% range; samples of one prompt move together, so
   the range counts prompts, not answers. Compare with the previous run only when the report
   says the change is a **real change**; "within noise" means the runs can't tell, and "not
   comparable" (other prompts or another model) means don't compare at all. Name the change
   that happened between.
6. Be honest: a few samples are noisy; trends over weeks matter more than one run; label
   everything Measured. Suggest re-running after each release (`/amin:release`).
