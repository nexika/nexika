---
name: figma
description: Build a Figma design in code, exactly - reads the frames (mobile, tablet, desktop) with as few Figma calls as possible, merges them into one mobile-first spec with tokens, type, photos and icons, builds the page in the project's stack (React, TanStack, Tailwind, shadcn/ui), then checks it against the design at every width until it matches. Use when the user shares a Figma link, says "build this design", "implement this Figma", "figma to code", "lawha figma", "نفّذ هذا التصميم", "حوّل تصميم فيغما إلى كود".
argument-hint: "<figma link> [frames]"
---

# Figma to code, exactly

The helper is named in the session note ("Helper: .../bin/lawha"); below it is written `lawha`.
Run it from the project folder.

## 0. The token
Figma needs a personal access token in `FIGMA_TOKEN` (read-only "File content"), even for community
files, which must first be duplicated into the user's drafts. If `lawha figma` says it is not set:
- never ask the user to paste the token into the chat, and never put it in a command or a file;
- tell them to run, in their own terminal (zsh shown):
  `read -rs "FIGMA_TOKEN?Figma token: " && print "export FIGMA_TOKEN=$FIGMA_TOKEN" > ~/.figma_token && chmod 600 ~/.figma_token && unset FIGMA_TOKEN`
  then `echo '[ -f ~/.figma_token ] && source ~/.figma_token' >> ~/.zshrc`;
- in your own commands, load it with `. ~/.figma_token && lawha figma ...` (non-interactive shells
  do not read `.zshrc`). Never print it.

## 1. Find the frames (1 call)
`lawha figma outline <link>` lists pages and top-level frames with their sizes, and the call budget
(Starter plans: 20 calls a month on View/Collab seats, 10 a minute on Full seats). The node in the
link is often not the page (a tutorial frame, a style guide). Pick the frames that are the **same
page at different widths** (names like Mobile / Tablet / Desktop, widths like 375-430 / 768-1024 /
1280-1440) and confirm them with the user.

## 2. Make the spec (2-4 calls the first time, cached after)
`lawha figma spec <link> --frames <mobile,tablet,desktop ids> --assets public/figma`
It writes into `.lawha/figma/<file>/<version>/spec/`: `spec.md` (read all of it), `theme.css`,
`designs/<width>.png` (for the check), and copies photos and SVG icons into `--assets`.

How to read `spec.md`:
- breakpoints are mobile first (`base`, then e.g. `md` for a 1024 tablet frame, `xl` for 1440);
  `a → md:b → xl:c` is a value that changes at that breakpoint;
- `fill` = takes the free space (`flex-1` / `w-full`), `hug` = fits content, `NNpx` = fixed;
- `RESTRUCTURED` = the designer built that part differently per frame: build one responsive layout
  that gives each width's version;
- `>` lines are design-file habits read as intent (a 796px "gap" that is only leftover space, padding
  that only centres): follow them;
- `trim cap` = Figma's vertical trim: use the `trim-cap` utility on a **block** element (wrap the
  text in a `<span class="block trim-cap">` inside buttons and flex items); `trim-none` resets it;
- `"..." is styled differently` = mixed styles inside one text (a bold word): keep them.
- `## Motion` = the prototype's interactions:
  - Each line gives the trigger (click, while hovering, after a delay...), what happens, Figma's transition, and the exact Motion `transition={...}` to use, with the recipe that builds it.
  - Directions are logical: `from end` mirrors in Arabic.
  - Indented lines list what changes between a layer and its hover or press variant: animate only those, and only with transform and opacity where you can. A colour change is a CSS transition, not a movement.
  - To see what changes in a variant, pass the variant's id along with the frames.
  - With no prototype, use the recipes in `${CLAUDE_PLUGIN_ROOT}/recipes/motion/`.

## 3. Build it in the project's stack
- Read `.lawha/system.json` (run `/lawha:system` first in an existing project): reuse its components
  and tokens. New project: React + TanStack Router + Tailwind 4 + shadcn/ui.
- Merge `theme.css` into the project's CSS (`@theme` tokens, the line height, the `trim-cap` and
  `trim-none` utilities) without duplicating existing tokens. Load the fonts it lists (e.g.
  `@fontsource/<font>`) with the weights the spec uses.
- Use the spec's exact values (`text-[32px]`, `h-[530px]`, `gap-[42px]`) and tokens
  (`bg-background-color-1`), mobile first.
- **Figma borders are inside the box**; a CSS border adds to it. For hug-sized elements in a row,
  use `ring-1 ring-inset ring-<colour>` instead of `border`, or rows overflow and wrap.
- Give photos meaningful file names and `alt` text; icons get `alt=""` when a label is next to them.
- Real elements: `<header>`, `<nav>`, `<main>`, `<section aria-labelledby>`, `<h1>`-`<h3>`, `<ul>`,
  buttons and links (shadcn `Button asChild` around `<a>`).
- Keep the designer's text exactly. Do not fix typos or odd values silently: list them for the user
  (a misspelled word, an e-mail address with a space, text under 12px).
- Motion only when the design or the user asks; then on load (not on scroll, so nothing is invisible
  in a full-page check), transform and opacity only, `useReducedMotion`.

## 4. Check against the design (the loop)
`lawha check <url> --widths <each frame width and each breakpoint start, e.g. 387,768,1024,1280,1440> --against <designs folder>`
(`--against-scale 0.5` for 2x exports). Per width the report gives how much the page **looks** like
the design (content aligned), the position-for-position match, the heights, and `design.height-drift`
lines: "from y=… the page sits N px lower" points at the section above that is too tall or short.
Fix the biggest drift first, then the regions that differ; look at the screenshots and the design
side by side. At most 3 rounds.

Accessibility wins over pixels: never let a fix fail a required check. When the design itself fails
one (a link trimmed to 11px tall, text under 12px), keep the look and fix the function (a larger hit
area with padding and a matching negative margin), or keep the design and tell the user.

## 5. Report
Per width: looks %, position %, built vs design height; what still differs and why (be specific:
"the tablet contact section was drawn at 0.71 scale without Auto Layout"); the design issues found;
Figma calls used. Never say "pixel-perfect". `lawha check` records the result for mizan and itqan.
