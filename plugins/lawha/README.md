# lawha (لوحة) - frontend you can see

Part of [Nexika](../../README.md). *Lawha* means board, or canvas.

AI-built pages look fine on the screen they were built on, and break on a phone, in Arabic, or for
someone who can't see low-contrast text. lawha gives Claude eyes: it opens the page in a real
browser at every screen size, looks at it, measures it, and fixes what fails.

```
lawha check http://localhost:5173/pricing --expect-rtl

  fail  6 problems must be fixed · 2 should be fixed
  [fail] The page scrolls sideways: 900px wide in a 390px viewport. (390px)
  [fail] Text is cut off: "Billed yearly, cancel any time" (360px, 390px)
  [fail] Tap target "Close" is 16×16px; WCAG 2.2 AA needs at least 24×24 (all widths)
  [fail] An animation (width) still runs with "reduce motion" on. (390px reduced motion)
  [fail] Physical left/right CSS will not mirror in RTL: .price { margin-left: 16px }
  [warn] Body text is 13px on a phone; 16px is the readable minimum.
  report: .lawha/runs/2026-10-06_18-24-55/report.html
```

The report shows every screen side by side with the problems boxed on the screenshots, and what
the eye measured: the page's real columns and the edges that almost line up, every gap against
the spacing scale, the type scale ratio and line lengths, and the palette actually on screen.

## What it checks

Every page at **360, 390, 768, 1024, 1280 and 1536px**, in light (and dark), LTR (and RTL), and
once with "reduce motion" on.

| | |
|---|---|
| **Layout** | sideways scrolling and the element causing it; text cut off by its box; text overlapping text; layout shift while loading |
| **Phones** | tap targets (24×24 required by WCAG 2.2 AA, 44×44 comfortable); body text under 16px; text under 12px |
| **Accessibility** | axe-core (WCAG 2.2 A and AA): contrast, names, labels, landmarks, keyboard access; the contrast of text over images, video and 3D, read from the real pixels behind it (axe cannot) |
| **Motion** | animations that keep running with "reduce motion" on, including 3D scenes (Three.js, WebGL) drawn on a canvas; motion that never stops (WCAG 2.2.2); interface motion slower than a second; animating width, height or top instead of transform and opacity |
| **RTL** | left/right CSS and utilities (`ml-4`, `text-left`, `rounded-l`) that will not mirror in Arabic (symmetric values like `padding: 16px` are fine); icons that show direction (arrows, chevrons, send, reply, undo, log-out, lists) and still point the same way in Arabic, and media controls, clocks and logos that were mirrored by mistake |
| **The eye** | where the eye lands first above the fold; alignment near-misses, off-scale gaps, uneven lists, type sizes and scale ratio, long lines, tight leading, palette shares, colours outside the tokens, low contrast |
| **Design** | with Figma exports, a pixel diff per width with a heat map and the regions that differ |

## Commands

- `/lawha:check [url] [--fix]` checks a page and explains the results plainly. With `--fix`, the
  `lawha:inspector` agent looks at the screenshots, finds the code behind each problem and
  proposes the smallest fix that keeps the design; Claude applies it and checks again (three
  rounds at most), then reports what passes and what still fails.
- `/lawha:figma <link>` builds a Figma design in code, exactly. It reads the frames (mobile,
  tablet, desktop) in a few batched calls, caches them by file version and shows the call budget
  (Starter plans allow very few). It merges them into one mobile-first spec: Auto Layout as flex,
  named styles as tokens, real line heights, vertical trim, style overrides, photos and SVG icons,
  and design-file habits (a 796px "gap" that is only leftover space) read as intent. Claude builds
  it in your stack, with the prototype's motion read too (click, hover, Smart Animate, springs, as
  exact Motion transitions), then `lawha check --against` compares it with each frame: how much it **looks**
  like the design, position for position, and where heights drift. See the
  [showcase](../../showcases/figma-portfolio/README.md): 95.4% / 91.4% / 93.2% at 387 / 1024 / 1440.
- `/lawha:system` reads the project's design system: Tailwind `@theme` tokens, `tailwind.config.js` and CSS variables,
  shadcn/ui components, your React and Vue components with their props, TanStack and Next.js routes, fonts. It lists drift
  (hard-coded colours, `p-[13px]`, left/right utilities) and saves `.lawha/system.json` so new
  pages reuse what exists.
- `/lawha:direct` gives a project a design when you cannot picture one.
  - The `lawha:director` agent proposes three complete directions: fonts, light and dark palettes, scale, corners, motion and one signature element.
  - lawha checks them: contrast, the known "AI look", sameness with each other and with your recent projects.
  - It renders them as real screens at phone and desktop size, so you choose by looking.
  - The one you pick becomes the project's Tailwind and shadcn tokens.
- `/lawha:inspire <url>` learns a design from a site you like:
  - fonts, with whether they are free and a free look-alike for paid ones;
  - the palette by area, type scale, spacing, corners and shadows;
  - section patterns, transitions, keyframes and scroll reveals;
  - the animation libraries it uses (GSAP, Lenis, Motion, Three.js, Spline, Lottie, Rive).

  It is used as inspiration for `direct` or the page you build, never copied.
- `/lawha:elevate` makes a working page more beautiful:
  - The `lawha:art-director` agent looks at the page and its measurements and proposes at most three bold changes.
  - Each change is kept only if the `lawha:judge` agent prefers it in a blind side-by-side (`lawha ab`), where it never knows which side is new.
  - Your own picks are kept as your taste and used the next time.
  - There is no "beauty score".

**Motion recipes** (`recipes/motion/`):
- entrances in reading order and number count-ups;
- page cross-fades and the shared-layout tab mark;
- press feedback, a sheet on the native dialog, toasts, and skeleton to content without a jump;
- the six signature movements.

All are timed by your direction (calm, lively or precise), mirror in Arabic and respect reduced
motion. See the [showcase](../../showcases/motion-recipes/README.md).

**Three.js recipes** (`recipes/three/`): `WaveField`, `GradientFlow` and `FloatingShapes` for React
Three Fiber, inside a `Scene3D` wrapper that:
- shows one still frame under "reduce motion";
- pauses off screen;
- caps the pixel density;
- falls back without WebGL;
- hides the scene from screen readers.

Colours come from the design tokens. See the
[showcase](../../showcases/three-recipes/README.md), and the
[prof dashboard](../../showcases/prof-dashboard/README.md) built with `direct`, `check` and `elevate`.

Built for **React, TanStack (Router, Query, Start), Tailwind CSS 4 and shadcn/ui**; the checks work
on any web page, including plain HTML.

## Setup

lawha's engine uses Playwright and Chromium. The first time it is needed, Claude asks you and runs
`lawha setup`: it installs them once into `~/.claude/nexika/lawha/engine/`, about 300 MB, with
nothing added to your project. Needs Node.js 20 or newer.

Everything stays on your machine: pages, screenshots and reports are local (`.lawha/runs/`; add
it to `.gitignore`).

## Working with the Nexika family

- **mizan** shows lawha's latest check of this commit in its band (`lawha ✓ 6 widths` or
  `lawha: 3 to fix`) with a **Fix** button, and the problems and report in its pane.
- **itqan** checks the changed pages during `/itqan:ship` when a change touches the UI, and its
  proof shows the pages check of the commit it proves; a failing one fails the proof.
- **haris** guards lawha's records (`~/.claude/nexika/lawha`), so a passing check in mizan or a
  proof always comes from lawha, never from Claude.
- **hafiz** remembers design decisions and problems that keep coming back ("wide tables scroll the
  page sideways on phones"), and lawha reads them before checking or building.

lawha publishes `~/.claude/nexika/status/lawha.json` (schema `nexika.lawha/1`): for each project, the
path of its latest check record (`nexika.lawha.check/1`) in lawha's own folder. Run `lawha check
--no-record` for a check you do not want to share.

## Coming next

lawha is being built in steps (see [DESIGN.md](DESIGN.md)):

1. **0.1:** checks on every screen, the eye's measurements, the design-system index.
2. **0.2:** `/lawha:figma`, Claude's eyes on your Figma file.
3. **0.3:** `/lawha:direct`, `/lawha:inspire`, `/lawha:elevate` with blind A/B and taste, the
   Three.js recipes, and checks for 3D motion and text over media.
4. **0.4, this version:** motion recipes built on Motion, motion from Figma prototypes, RTL icon
   rules, and a [public benchmark](../../benchmarks/README.md) against the leading tools.
