---
name: direct
description: Propose three design directions, pick one by looking, and turn it into Tailwind and shadcn tokens. Use when the user says "design this", "make it look good", "pick a style", "صمم الواجهة", "اقترح تصميماً", or starts a frontend with no design.
argument-hint: "[what the product is] [--kind landing|dashboard]"
---

# Three directions, chosen by looking

The helper is `sh "${CLAUDE_PLUGIN_ROOT}/bin/lawha"` (in a project with a frontend the session note names it
too); below it is written `lawha`.

0. **Remember first.** With hafiz installed, `hafiz recall "design"` and `hafiz recall "taste"`.
   Also run `lawha direct history` (recent choices, so this project gets something different) and
   `lawha ab taste` (what this person picked in blind comparisons). Respect what you find.

1. **The brief, in three answers.** What is it (product), who uses it (audience), and how should it
   feel (one or two words). Take them from the request or the code; ask only what is missing.
   `kind` is `dashboard` for a screen used every day, `landing` for a public page.
   If the user gave reference sites or screenshots, run `/lawha:inspire` on them first and pass the
   DNA files to the director.

2. **Three directions.** Launch the `lawha:director` agent with the brief, the history, the taste
   and any DNA. It writes `directions.json` (three directions, distinct from each other and from
   recent history).

3. **Check and render.** `lawha direct preview directions.json --kind <kind> --product "<...>"
   --audience "<...>" --feeling "<...>"`. It fails a direction whose text or buttons miss 4.5:1, that
   matches a known AI look (purple-blue gradient on white, Inter everywhere with indigo...), or that
   is too close to another. When a direction fails, ask the director to replace it and run again.

4. **Show, don't describe.** Open `gallery.html` and the screenshots yourself (Read the PNGs), then
   show the person the gallery (light, dark, phone, desktop). If an Artifact tool is available,
   publish the gallery so they can look on any device. In one line each: the feeling, the fonts,
   the signature. Let them pick A, B or C, or mix ("A's colours with C's corners": edit the JSON and
   preview again).

5. **Apply.** `lawha direct choose directions.json <id>` writes the theme CSS (Tailwind `@theme` and
   shadcn variables, light and `.dark`) into the app (the folder with `package.json`), and
   `.lawha/design.json`. Import it from the main CSS, install the fonts it names (`@fontsource/...`
   or Google Fonts), and build with the tokens only: no raw hex colours in components.
   For motion, copy the recipes from `${CLAUDE_PLUGIN_ROOT}/recipes/motion/` (`tokens.ts` first): they
   read the direction's timing from the theme, and the signature components match its `motif`.

6. **Remember.** With hafiz: `hafiz remember decision "design: direction <name> - <why they chose it>" --project`.
   Then suggest `/lawha:check` on the first built screen and `/lawha:elevate` once it works.
