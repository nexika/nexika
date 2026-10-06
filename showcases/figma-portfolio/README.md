# Showcase: a Figma design built with lawha 0.2

The free Figma community file "Responsive Landing Page Design | Personal Portfolio" (mobile 387,
tablet 1024 and desktop 1440 frames) built with React, TanStack Router, Tailwind CSS 4, shadcn/ui
and Motion, then checked against the design with `lawha check --against`.

| Width | Looks like the design | Position for position | Height (built / design) |
|---|---|---|---|
| 387 (mobile) | 95.4% | 95.7% | 3015 / 3014 |
| 1024 (tablet) | 91.4% | 89.2% | 2215 / 2231 |
| 1440 (desktop) | 93.2% | 93.1% | 2901 / 2901 |

It also passes every required check at 360, 387, 768, 1024, 1280 and 1440 px (sideways scroll, clipped
text, tap targets, axe accessibility, motion). It still has 7 warnings: 11.4px text that the design
itself uses in the tablet contact section, and nav tap targets under the comfortable 44px.

What it took, and what lawha learned from it:

- **Borders.** Figma draws borders inside the box; CSS adds them. Three contact cards with 1px borders
  overflowed their row by 6px and wrapped. Inset rings fix that.
- **"Auto" line heights.** Figma still reports the rendered line height (1.5× for Poppins). Without
  it, Tailwind's tighter defaults shrink every line.
- **Vertical trim** (`leadingTrim: CAP_HEIGHT`) is on 25 text layers. It becomes CSS
  `text-box: trim-both cap alphabetic`.
- **Character style overrides.** These made the tablet card titles bold while the layer's own style
  said regular.
- **A typed line separator** (U+2028) is what breaks the tablet title.
- **Breakpoint start.** The tablet layout starts at 768, where its fixed widths overflowed, so the
  check runs at the breakpoint start as well as at each frame's width.

Two things are kept exactly as designed and flagged rather than fixed: "Portfoilo" (a typo) and
"hello@Bernard Smith.com" (an address with a space).

## Run it

```bash
npm install
. ~/.figma_token   # FIGMA_TOKEN, read-only file content; duplicate the community file to your drafts
lawha figma spec "<your copy's link>" --frames 39:2,41:100,17:2 --assets public/figma
npm run build && npm run preview
lawha check http://localhost:4173/ --widths 387,768,1024,1280,1440 --against .lawha/figma/<file>/<version>/spec/designs
```

The photos and icons belong to the design's author and are not committed; `lawha figma spec`
downloads them into `public/figma/`.
