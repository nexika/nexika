# lawha motion recipes

Motion for React with [Motion](https://motion.dev) (`motion/react`), timed by your design direction.
Copy `tokens.ts` and the recipes you need into the project (e.g. `src/components/motion/`) and wrap
the app in `<MotionConfig reducedMotion="user">`.

| Recipe | What it does |
|---|---|
| `Reveal`, `RevealGroup` + `RevealItem` | entrances in reading order; `inView` waits until scrolled to |
| `CountUp` | a number counts up once; screen readers get the final value at once |
| `PageTransition` | a calm cross-fade between pages, keyed by route |
| `ActiveMark` | the mark under the active tab glides to the new one (shared layout) |
| `usePress` | press feedback for buttons, a 2px lift for cards |
| `Sheet` | a side sheet on the native `<dialog>`; it slides from the end of the line and closes with Escape |
| `ToastProvider`, `Toaster`, `useToast` | polite toasts that stack and leave after 5s (held while hovered or focused) |
| `Swap` | skeleton to content without the page jumping (a reserved `minHeight`) |
| `Underline`, `Rule`, `Cells`, `Dots`, `Stamp`, `Outline` | the direction's signature movement; use one, once, on what matters most |

**Timing comes from the theme.** `lawha direct choose` writes these variables into `:root`:
- `--lawha-motion`: `calm`, `lively` or `precise`;
- `--lawha-ease`;
- `--lawha-fast`, `--lawha-base` and `--lawha-slow`, in milliseconds;
- `--lawha-distance`, in pixels.

`tokens.ts` reads them:
- `lively` moves on a soft spring;
- `calm` and `precise` move on the direction's curve.

Every recipe follows the same rules:
- **Reduced motion:** content appears at once and nothing moves.
- **Only `transform` and `opacity` move**, so animations stay cheap.
- **Reading direction:** slides and draws start where reading starts, so in Arabic a sheet comes from the left and a line draws from the right.
- **One timing:** the whole app moves alike.

**Tailwind:** the recipes use Tailwind classes. Tailwind 4 skips git-ignored files when it looks for
classes, so if you keep the recipes in an ignored folder, add `@source "./that-folder";` to your CSS.

**Checks:** `lawha check` catches what goes wrong with motion:
- `motion.reduced`: an animation still running with "reduce motion" on;
- `motion.webgl-reduced`: a 3D scene still moving;
- `motion.endless`: motion that never stops (WCAG 2.2.2 needs a way to pause anything that moves for more than 5 seconds);
- `motion.slow`: UI motion over a second;
- `motion.costly-property`: animating `width`, `height` or `top`.

For 3D, see [`../three`](../three/README.md).
