# Showcase: lawha's Three.js recipes

Three React Three Fiber scenes from [`plugins/lawha/recipes/three`](../../plugins/lawha/recipes/three/README.md),
in the prof dashboard's "Ink and saffron" tokens:

- **WaveField:** a wireframe grid that rolls, behind a dark hero.
- **GradientFlow:** the theme's colours flowing slowly, veiled so the headline stays readable.
- **FloatingShapes:** soft shapes leaning towards the pointer, on the side away from the text.

```sh
npm install
npm run build      # copies the recipes into src/three/, type-checks, builds
npm run preview    # http://localhost:4174
```

## What lawha found while building it

`lawha check` at 390 and 1280px, with "reduce motion" on and off:

| Round | Result |
|---|---|
| 1 | Contrast over the gradient failed: "Learn by building…" at 1.5:1 (needs 3:1). axe could not see it; lawha read the pixels behind the text. |
| 2 | The muted subtitles failed over the bright parts of both scenes (4.38:1 and 2.84:1). |
| 3 | GradientFlow got a `veil`, the shapes moved to the free side, subtitles use the full text colour: **0 problems**. |

With "reduce motion" on, every scene shows one still frame. lawha compares two screenshots of each
canvas taken 0.7s apart, and the check passes.
The same check flags the 3D scenes on stripe.com and louisraille.fr, which keep moving.
