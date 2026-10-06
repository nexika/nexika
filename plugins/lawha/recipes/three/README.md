# lawha Three.js recipes

React Three Fiber scenes for heroes and backdrops, built to pass `lawha check`. Copy the files you
need into the project (e.g. `src/components/three/`) and install `three @react-three/fiber motion`.

| Recipe | Feels | Use |
|---|---|---|
| `WaveField` | calm, technical: a wireframe grid rolling like a topographic map | dark heroes, developer tools |
| `GradientFlow` | warm, premium: three brand colours flowing slowly | full-bleed backdrops behind a headline |
| `FloatingShapes` | friendly, light: soft shapes floating, leaning towards the pointer | product and learning pages |

Always wrap a scene in `Scene3D`:

```tsx
<Scene3D className="absolute inset-0" fallback={<div className="h-full bg-gradient-to-br from-primary to-accent" />}>
  <WaveField />
</Scene3D>
```

`Scene3D` makes every scene behave:
- **Reduced motion:** with "reduce motion" on, the scene shows one still frame.
- **Off screen:** nothing is drawn while the scene is off screen or the tab is hidden.
- **Pixel density:** capped at 2.
- **No WebGL:** the fallback shows instead.
- **Screen readers:** the scene is hidden from them; keep real content (headings, text, buttons) outside the canvas.

**Text on a scene:**
- Use the full text colour (`text-foreground`), not the muted grey: a moving backdrop has bright and dark spots, and the muted colour fails over the bright ones.
- Keep `GradientFlow`'s veil when text sits on it.
- Put `FloatingShapes` on the side away from the text (`side="end"`, the default).

`lawha check` verifies this: `motion.webgl-reduced` fails when a canvas keeps animating with reduce
motion on, and `a11y.contrast-over-media` reads the real pixels behind any text over a scene, image or
video. Colours come from the design tokens (`--primary`, `--accent`, `--background`,
`--muted-foreground`), so the scene follows the theme.
