# Showcase: lawha's motion recipes

Every recipe from [`plugins/lawha/recipes/motion`](../../plugins/lawha/recipes/motion/README.md) on one page, in
the prof dashboard's "Ink and saffron" tokens: entrances, count-up, tabs with a gliding mark, page
cross-fade, press feedback, a sheet, toasts, skeleton to content, and the six signatures.

```sh
npm install
npm run build      # copies the recipes into src/motion/, type-checks, builds
npm run preview    # http://localhost:4175 (add ?lang=ar for Arabic)
```

## What building it found

| Found by | Problem | Fix |
|---|---|---|
| `lawha check` (axe) | `CountUp` put `aria-label` on a plain `<span>` | hidden text holds the final number for screen readers; the counting digits are hidden from them |
| Testing clicks in both directions | the sheet sat on the wrong side | Tailwind 4 skips git-ignored folders; this showcase names `src/motion` with `@source` |
| Looking at the screenshot | the counters stayed at 0 | the tokens are now read once per component, so the count no longer restarts on every frame |

The final check passes with 0 problems:
- six widths, light and dark, English and Arabic, with reduced motion;
- the sheet slides from the right in English and from the left in Arabic, and does not move under reduced motion;
- the counts reach their values, or show them at once under reduced motion.
