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
| **Accessibility** | axe-core (WCAG 2.2 A and AA): contrast, names, labels, landmarks, keyboard access |
| **Motion** | animations that keep running with "reduce motion" on; animating width, height or top instead of transform and opacity |
| **RTL** | left/right CSS and utilities (`ml-4`, `text-left`, `rounded-l`) that will not mirror in Arabic; symmetric values like `padding: 16px` are fine |
| **The eye** | alignment near-misses, off-scale gaps, uneven lists, type sizes and scale ratio, long lines, tight leading, palette shares, colours outside the tokens, low contrast |
| **Design** | with Figma exports, a pixel diff per width with a heat map and the regions that differ |

## Commands

- `/lawha:check [url] [--fix]` checks a page and explains the results plainly. With `--fix`, the
  `lawha:inspector` agent looks at the screenshots, finds the code behind each problem and
  proposes the smallest fix that keeps the design; Claude applies it and checks again (three
  rounds at most), then reports what passes and what still fails.
- `/lawha:system` reads the project's design system: Tailwind `@theme` tokens and CSS variables,
  shadcn/ui components, your components with their props, TanStack routes, fonts. It lists drift
  (hard-coded colours, `p-[13px]`, left/right utilities) and saves `.lawha/system.json` so new
  pages reuse what exists.

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

1. **0.1, this version:** checks on every screen, the eye's measurements, the design-system index.
2. **0.2:** a `figma` command, Claude's eyes on your Figma file: batched, cached reads (a Starter plan
   allows few calls), mobile and desktop frames merged into one responsive component, then
   checked against the design until it matches.
3. **0.3:** a `direct` command for three design directions you choose by looking, and `elevate`,
   an art director that critiques with the eye's measurements and keeps only changes that win a
   blind side-by-side comparison.
4. **0.4:** motion recipes built on Motion, Figma motion, RTL icon rules, and a public benchmark
   against the leading tools.
