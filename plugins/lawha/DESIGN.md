# lawha (لوحة, "board, canvas"): design v0.1

lawha is a frontend plugin for Claude Code. It does three things:

- **Imagination:** it designs master-class, animated pages for developers with weak design imagination, or who would rather do backend work.
- **Eyes on Figma:** it turns a user's Figma design into that exact page in code.
- **Proof:** it shows, with screenshots and checks, that every page works on a phone and on every screen size.
- **An artistic eye:** it measures exactly what is on screen, critiques it like an art director, and keeps only the changes that win a blind side-by-side comparison.

Status: **approved 2026-10-06**. Build order: check and see first, then Figma, then directions with the art director, then motion. The user has a Full seat on a free Figma team.

## Why: what the best three tools miss

We studied the three leading tools in depth. The reports with sources are in the research notes:

- **Anthropic's frontend-design plugin** (1.1M installs). It is one prompt file. It has good anti-"AI look" rules and plans before it builds.
  - It never looks at its own result.
  - Responsive design gets one sentence.
  - It now discourages animation.
  - It has no Figma input, no knowledge of the project, and no RTL support.
  - Its own style has become recognisable.
- **Figma's MCP server and plugin.** It gives authoritative design data, Code Connect, and motion as CSS or Motion code.
  - One frame becomes code for one fixed size.
  - Nothing checks the result: users build their own screenshot loops, and one benchmark went from about 70% to 95% match that way.
  - The output depends on how tidy the file is.
  - It allows 20 calls a month on the free plan.
  - It has no RTL support and no prototype interactions.
- **Builder.io Visual Copilot / Fusion.** A purpose-built model pipeline that works inside the user's repo.
  - By its own account it gets "75% of the way there".
  - Breakpoints are set by hand.
  - It has no visual check and converts no animation.
  - Its key features are Enterprise-only and run in its cloud.

**What none of them do, and lawha does:**
- check the result against the design at every screen size, and fix it until it matches;
- merge mobile and desktop frames into one responsive page;
- offer design directions you choose by looking, not by writing a brief;
- treat animation as part of the design;
- support right-to-left (RTL) layouts;
- remember the project's own design system.

## Stack lawha writes

- **React 19 and TypeScript.**
- **TanStack Router** for routes, and **TanStack Query** for data. TanStack Start is used when the project already uses it.
- **Tailwind CSS 4**, with design tokens as CSS variables in `@theme`.
- **shadcn/ui** components. lawha adds the components it needs with the shadcn CLI and restyles them through the tokens, never by forking them.
- **Motion** (motion.dev) for animation.
- **Logical CSS properties** everywhere (`ms-*`, `me-*`, `ps-*`, `pe-*`, `start-*`, `end-*`), so every page mirrors correctly in RTL.

It works in an existing project of this stack, or creates a new one.

## The five modes

### 1. `/lawha:direct`: imagination for those who don't have it

The developer does not write a design brief. lawha asks three plain questions: what the page is for, who uses it, and one word for the feeling. It then:

1. **Proposes three distinct directions.** Each one is a complete token set:
   - typography: a display face and a text face, chosen for the language, with an Arabic face when the page is RTL;
   - a palette of 4 to 6 named colours, in light and dark;
   - the spacing scale and radii;
   - one signature element;
   - a motion personality: calm, lively or precise.
2. **Renders each direction as a real preview page:** a hero, a card, a form, a button set, and a motion sample. It screenshots each preview on a phone and on a desktop, then opens a local gallery where the developer **chooses by looking**.
3. **Avoids sameness:**
   - It keeps the named anti-"AI look" list (credited to frontend-design).
   - It keeps a style history in `~/.claude/nexika/lawha/history.json`. A new direction must differ from the user's recent ones in type, palette and layout, which fixes frontend-design's "every site looks the same".
4. **Saves the chosen direction** as the project's design system in `.lawha/design.json`, and writes it into Tailwind `@theme` and shadcn's CSS variables.

### 2. `/lawha:figma`: Claude's eyes on Figma

Input: a Figma link to one frame, or to several frames, such as the mobile, tablet and desktop versions of a page.

1. **Fetch once, batched, then cache.** One REST call fetches the layer trees of every selected frame, and one call renders their images. Both are cached in `.lawha/figma/` by file version, so the same design is never fetched twice. The MCP server is used only for what REST lacks: motion context, and Code Connect when the user has it. lawha shows the remaining monthly budget before each call.
2. **Normalise the design:**
   - Auto Layout becomes flex or grid, and constraints become sizing rules.
   - Variables and styles become tokens.
   - Text styles become type roles.
   - Icons are exported as SVG with correct bounds, and images are downloaded into the project (Figma's links expire after 7 days).
3. **Merge breakpoints.** When there are several frames of the same page, layers are matched by name and structure. The differences become responsive rules: what stacks, what hides, what changes size. The result is **one mobile-first component**. With only one frame, lawha writes down its responsive decisions in a short plan the developer can see and change; it never guesses silently.
4. **Map to the project:** shadcn components and the project's own components (see `/lawha:system`) are used instead of new divs. Buttons are buttons and inputs are real inputs.
5. **Build**, then run `/lawha:check` against the Figma images until they match.

### 3. `/lawha:check`: proof on every screen

lawha's engine uses Playwright to render the page:
- at the widths **360, 390, 768, 1024, 1280 and 1536**;
- in light and dark;
- in LTR and, when the project supports it, RTL;
- with and without reduced motion.

**Checks:**
- **Visual match:** a perceptual diff per region against the Figma image, or against the approved direction preview. It produces a heat map and a score, and lists the regions that are off.
- **Layout faults:**
  - horizontal scroll;
  - clipped or overlapping text;
  - content cut off at any width;
  - layout shift while loading.
- **Phone fitness:**
  - tap targets: at least 24×24 CSS px is required (WCAG 2.2 AA), and 44×44 is the recommended size;
  - a readable base text size;
  - nothing that needs hover to work.
- **Accessibility:**
  - axe-core;
  - colour contrast;
  - focus order and visible focus;
  - landmarks and labels.
- **Motion:**
  - only transform and opacity are animated, unless the developer approves otherwise;
  - everything still works under reduced motion.

**The loop:** lawha fixes what failed and checks again, for at most 3 rounds. It then reports honestly: the score per width, side-by-side images, and what is still off and why. The report is a local HTML page in `.lawha/reports/`.

### 4. `/lawha:system`: know the project

- **Index the project locally:**
  - the Tailwind theme;
  - CSS variables;
  - installed shadcn components;
  - the project's own components, with their props, read from TypeScript;
  - routes (TanStack Router);
  - fonts and icons.
- **Keep it in `.lawha/system.json`.** Every new page reuses the same tokens and components, so page five matches page one.
- **Report drift:** hard-coded colours, sizes outside the spacing scale, and components duplicated under different names.

### 5. `/lawha:elevate`: the artistic eye

"Correct" is not the goal; beautiful is. The artistic eye has two halves.

**Seeing exactly: `lawha see`, measured, objective.** The engine reads the rendered page itself, not the code and not an impression of a screenshot. Using computed styles and element boxes from Playwright, it measures:

- **Alignment:**
  - the real edges that elements share;
  - near-misses ("these two cards are 3 px apart from aligning");
  - the grid the layout actually follows.
- **Rhythm:** every gap between elements, compared with the spacing scale. Off-scale gaps and uneven repeats are flagged.
- **Typography:**
  - the actual sizes, and the scale ratio between them;
  - line lengths in characters (comfortable is about 45 to 75 for Latin text);
  - line heights;
  - how many different families and weights are used.
- **Colour:**
  - the palette actually on screen, with each colour's share of the area;
  - harmony relations between the colours;
  - contrast between each pair of colours in use;
  - colours used that are not tokens.
- **Visual weight and focus:**
  - a saliency map of where the eye lands first;
  - whether that is the element that should be the focal point.
- **Balance and space:**
  - how mass is distributed across the page;
  - whitespace per section;
  - crowding.
- **Motion choreography:** a frame-by-frame recording of each animation. It measures timing and stagger order, whether things move together or fight, and the frames per second.
- **Figma pixel overlay:** the built page and the design layered at each width, with every measured difference listed in px.

**Taste: the art-director agent, judged, subjective.** It works from the `see` measurements together with the screenshots at every width. It critiques like a demanding senior designer, using an explicit rubric:

- hierarchy and focal point;
- rhythm and spacing;
- typographic craft;
- colour harmony and restraint;
- balance and tension;
- depth and texture;
- the detail that makes it memorable;
- motion that tells the story;
- coherence on phones.

It names each weakness with its evidence ("the hero headline and the card titles are 2 steps apart on the scale; the focal point lands on the logo, not the call to action"). It then proposes the refinements with the biggest effect.

**Proof that it is better, not just different:**
1. Each refinement is applied in a scratch copy.
2. Both versions are rendered.
3. A **blind side-by-side judgement** is made: an independent judge sees A and B in random order, without knowing which is new, and picks one with reasons.
4. Only refinements that win are kept, and none may break a `/lawha:check` rule (contrast, tap targets, layout faults).
5. The developer sees the before and after for each round and has the final word.

**Limits, stated honestly:**
- Taste is not a number. lawha never shows a "beauty score".
- The measurements are facts. The judgements are opinions, backed by evidence and by side-by-side wins.
- In Figma mode, the eye's job is **fidelity first**. It points out improvements to the design as suggestions, and never changes a designer's work unasked.

**Learning the user's taste:** every A/B the developer decides is saved in `~/.claude/nexika/lawha/taste.json`, and the art director weighs future proposals with it.

## Motion

Motion is part of the design, not decoration. Each direction has a motion personality, and lawha ships a library of **motion recipes** built on Motion:

- page transitions;
- staggered list and card entrances;
- shared-layout transitions (`layoutId`);
- scroll reveal;
- number count-up;
- skeleton-to-content transitions;
- press and hover feedback;
- drawers and dialogs;
- toasts.

Every recipe follows the same rules:
- it is based on springs or tuned easing;
- it animates only transform and opacity;
- it respects `useReducedMotion`;
- it is mirrored in RTL (a "slide in from the start" respects `dir`).

From Figma, lawha uses the motion context (CSS keyframes or Motion code) when the MCP budget allows. Prototype interactions are not available through Figma's API, so lawha asks for them or proposes a recipe instead.

## RTL and languages

- **`dir` and `lang` on the root.** Only logical properties are used, and `/lawha:check` fails on physical left and right values.
- **Icons:** directional icons such as arrows and chevrons are mirrored; universal ones such as play, clock and logos are not. The rule list is in the plugin.
- **Arabic typography:**
  - a proper Arabic face;
  - a larger line height;
  - no letter-spacing on Arabic;
  - numerals chosen deliberately (Western or Arabic-Indic).
- **Figma has no text direction in its API.** lawha asks once whether the design is RTL and remembers the answer.

## Engine

- **The plugin itself** is skills and agents in markdown:
  - **director:** proposes directions;
  - **builder:** writes the code;
  - **inspector:** reads check reports and decides the fixes;
  - **art-director:** critiques with the `see` measurements;
  - **judge:** blind A/B choices;
  - **figma-reader.**
- **The engine** is a Node CLI, `lawha`, written in TypeScript and shipped as built JavaScript. It handles:
  - `shoot`: renders and screenshots at each width, mode and direction;
  - `diff`: perceptual diff, heat map and regions;
  - `audit`: layout, phone, accessibility and motion checks;
  - `see`: alignment, rhythm, typography, colour, saliency, balance, motion frames and the Figma overlay;
  - `ab`: renders two versions for a blind comparison;
  - `figma fetch`: batched and cached, with the budget shown;
  - `index`: builds the project system index;
  - `gallery`: the local page for choosing a direction and viewing reports.
- **Dependencies:** Playwright, axe-core, pixelmatch or an SSIM implementation, and a TypeScript parser for component props. They are installed once into `~/.claude/nexika/lawha/engine`, after asking the developer, with nothing added to the project.
- **Local-first.** Designs, screenshots and reports stay on the machine. The only network calls go to Figma (with the developer's token) and to the package registry for the first install.
- **The Figma token** is read from the environment variable `FIGMA_TOKEN` and never written to a file.

## How we know lawha is the best

A **benchmark** lives in the plugin (`bench/`):
- 6 public Figma community designs, mixing clean and messy files, and including one Arabic RTL design;
- 3 briefs for `/lawha:direct`.

For each case we measure:
- the visual match score per width;
- blind side-by-side preference against the other tools' output;
- layout faults;
- axe violations;
- the time and the number of Figma calls used.

We run the same cases with the Figma MCP server alone and with frontend-design alone, and publish the numbers in the README. A release must not lower any score.

## Phases

| Version | Delivers |
|---|---|
| **0.1** | engine `shoot`, `audit`, `see` (alignment, rhythm, typography, colour) and `diff`; `/lawha:check` with its report; `/lawha:system` index. This proves every page, including pages lawha did not write. |
| **0.2** | `/lawha:figma`: batched and cached fetch, normalisation, breakpoint merge, the build and check loop. Built: see `showcases/figma-portfolio`. |
| **0.3** | `/lawha:direct`: three rendered directions, the gallery, style history. `/lawha:inspire`: design DNA from live sites, with font licences. `/lawha:elevate` (the art director), with a visual-weight ranking, blind A/B (`lawha ab`) and taste learning. Three.js recipes; checks for 3D under reduced motion and for text over media. Built: see `showcases/prof-dashboard` and `showcases/three-recipes`. |
| **0.4** | The motion recipe library and Figma motion context; the RTL icon rules; the benchmark published. |

The **prof learner dashboard** (designed earlier, kept in `showcases/prof-dashboard/`) is the first real app built with lawha. It goes through `/lawha:direct`, then `/lawha:check` in English, Arabic and French.
