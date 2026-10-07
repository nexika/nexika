# Task 2: a brief, no design

Give both tools this prompt in a copy of `benchmarks/starter`, one session each, same model, no human edits.

> Design and build the landing page for **Qalam**, a writing app for people who write in Arabic and
> English: notes, drafts and long essays, with the same calm editor in both languages. The page is
> for students and writers. It needs a hero, three features, how it works, a testimonial, pricing
> (free and pro), and a final call to action. It must work in English and in Arabic (right to left,
> with `?lang=ar`), on phones and desktops, in light and dark. Make it memorable. Do not ask me
> questions. When you are done, `npm run build` must pass.

## Each tool's method
- **lawha:** start with `/lawha:direct`, choose the direction the judge agent prefers blind (no human pick), build, then `/lawha:check --fix` and `/lawha:elevate`.
- **frontend-design** (Anthropic's skill): with the skill enabled, as its instructions say.
