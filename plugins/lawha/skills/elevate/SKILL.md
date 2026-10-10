---
name: elevate
description: Make a working page more beautiful, keeping only changes a blind judge prefers. Use when the user says "make it beautiful", "it looks boring", "polish this", "حسّن التصميم", "اجعلها أجمل".
argument-hint: "[url] [--rounds 3]"
---

# Elevate a page, and prove it got better

The helper is `sh "${CLAUDE_PLUGIN_ROOT}/bin/lawha"` (in a project with a frontend the session note names it
too); below it is written `lawha`.
Never show or invent a "beauty score": a change is better only when it wins a blind comparison.

0. **Remember first.** `lawha ab taste` (the person's past picks), `.lawha/design.json` (the chosen
   direction: stay inside it), and with hafiz `hafiz recall "design"`.

1. **Baseline.** The page must already pass `/lawha:check` (fix failures first: beauty does not
   excuse sideways scrolling). Run `lawha check <url> --widths 390,1280` and keep the run folder:
   `seen` in `run.json` has the eye's measurements, including `focus` (where the eye lands first).

2. **Art direction.** Launch the `lawha:art-director` agent with the run folder, the design file and
   the taste. It returns at most three proposals, each with the reason it should look better and
   the exact code change. Bold is welcome; random is not.

3. **Try each proposal blind.**
   - Save the current page: commit or stash, or keep the current build on another port.
   - Apply one proposal and build it. Then run
     `lawha ab <current url> <candidate url> --a-label current --b-label "<proposal>"`.
   - Launch the `lawha:judge` agent with **only the pair image paths**. Never pass the folder, the `.key/`
     inside it, or the labels.
   - Turn its left/right answer into a winner with
     `lawha ab reveal <dir> --pick <left|right> --by judge`.
   - **If the candidate wins:** keep it, and run `/lawha:check` again so nothing broke.
   - **If it loses, or the judge says "same":** undo it.
   - Stop after `--rounds` proposals (default 3).

4. **Let the person decide the close ones.** Show them the pair image of each kept change, without
   saying which side is new, and ask which they prefer. Record their pick with
   `lawha ab reveal <dir> --pick <left|right> --by user --note "<what they said>"`. That is their taste,
   used the next time. Their pick wins over the judge's.

5. **Report.** For each kept change, say what changed and why it looks better; give the pair images
   as the evidence. Say what was tried and lost, too.

## Motion and 3D

- **Motion has to earn its place:**
  - an entrance that sets the reading order;
  - a hover that says "this is clickable";
  - one signature movement per page.
- **Code:** use the recipes in `${CLAUDE_PLUGIN_ROOT}/recipes/motion/`:
  - entrances: `Reveal`, `RevealGroup`;
  - numbers: `CountUp`;
  - tabs: `ActiveMark`;
  - feedback: `usePress`;
  - panels and messages: `Sheet`, `Toasts`;
  - loading: `Swap`;
  - the direction's signature, matching its `motif`: `Underline`, `Rule`, `Cells`, `Dots`, `Stamp`, `Outline`.

  They take their timing from the theme and respect reduced motion and RTL.
- **Three.js** suits one hero or backdrop, never behind long text:
  - Use the recipes in `${CLAUDE_PLUGIN_ROOT}/recipes/three/` (`WaveField`, `GradientFlow`, `FloatingShapes`), always inside `Scene3D`.
  - Text on a scene uses the full text colour.
  - `lawha check` fails a scene that keeps moving under "reduce motion" (`motion.webgl-reduced`) and text that is hard to read over it (`a11y.contrast-over-media`).
