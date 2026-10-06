// lawha 0.4 tests: motion read from a Figma prototype (offline, nodes shaped as the REST API returns them).
import { strict as assert } from "node:assert";
import { test } from "node:test";
import { extractMotion, layerNames, motionMarkdown, motionTransition } from "../dist/figma-motion.js";
import { normalize } from "../dist/normalize.js";

const box = (x, y, width, height) => ({ x, y, width, height });
const solid = (r, g, b) => [{ type: "SOLID", color: { r, g, b, a: 1 } }];
const button = (id, name, fill, interactions) => ({
  id, name, type: "INSTANCE", absoluteBoundingBox: box(0, 0, 160, 48), fills: solid(...fill), cornerRadius: 8,
  layoutMode: "HORIZONTAL", primaryAxisAlignItems: "CENTER", counterAxisAlignItems: "CENTER", paddingLeft: 24, paddingRight: 24,
  children: [{ id: `${id}t`, name: "Label", type: "TEXT", characters: "Contact me", absoluteBoundingBox: box(24, 14, 112, 20), style: { fontFamily: "Inter", fontWeight: 600, fontSize: 16, lineHeightPx: 20 }, fills: solid(1, 1, 1) }],
  ...(interactions ? { interactions } : {}),
});

const hoverVariant = button("20:2", "Button/Hover", [0.12, 0.23, 0.37]);
const frame = {
  id: "1:1", name: "Home", type: "FRAME", absoluteBoundingBox: box(0, 0, 1440, 900), fills: solid(1, 1, 1),
  interactions: [{ trigger: { type: "AFTER_TIMEOUT", timeout: 3 }, actions: [{ type: "NODE", destinationId: "2:1", navigation: "NAVIGATE", transition: { type: "DISSOLVE", duration: 0.4, easing: { type: "EASE_IN_AND_OUT" } } }] }],
  children: [
    button("10:1", "Button", [0.9, 0.66, 0.23], [
      { trigger: { type: "WHILE_HOVERING" }, actions: [{ type: "NODE", destinationId: "20:2", navigation: "CHANGE_TO", transition: { type: "SMART_ANIMATE", duration: 0.3, easing: { type: "GENTLE" } } }] },
      { trigger: { type: "ON_CLICK" }, actions: [{ type: "NODE", destinationId: "3:1", navigation: "OVERLAY", transition: { type: "MOVE_IN", direction: "LEFT", duration: 300, easing: { type: "CUSTOM_CUBIC_BEZIER", easingFunctionCubicBezier: { x1: 0.22, y1: 1, x2: 0.36, y2: 1 } } } }] },
    ]),
    { id: "10:5", name: "Menu", type: "FRAME", absoluteBoundingBox: box(0, 0, 40, 40), interactions: [{ trigger: { type: "ON_CLICK" }, actions: [{ type: "NODE", destinationId: "2:1", navigation: "NAVIGATE", transition: null }] }] },
  ],
};
const about = { id: "2:1", name: "About", type: "FRAME", absoluteBoundingBox: box(0, 0, 1440, 900), children: [] };
const contact = { id: "3:1", name: "Contact sheet", type: "FRAME", absoluteBoundingBox: box(0, 0, 420, 900), children: [] };

test("Figma curves, springs and custom curves become Motion transitions", () => {
  assert.deepEqual(motionTransition({ type: "DISSOLVE", duration: 0.4, easing: { type: "EASE_IN_AND_OUT" } }).motion, { duration: 0.4, ease: [0.42, 0, 0.58, 1] });
  assert.deepEqual(motionTransition({ type: "SMART_ANIMATE", duration: 0.3, easing: { type: "BOUNCY" } }).motion, { type: "spring", mass: 1, stiffness: 600, damping: 15 });
  assert.deepEqual(motionTransition({ type: "SMART_ANIMATE", easing: { type: "CUSTOM_SPRING", easingFunctionSpring: { mass: 1, stiffness: 220, damping: 18 } } }).motion, { type: "spring", mass: 1, stiffness: 220, damping: 18 });
  assert.equal(motionTransition({ type: "INSTANT" }).motion, null);
  // Durations: seconds as the plugin API documents them, milliseconds when the value says so.
  assert.equal(motionTransition({ type: "DISSOLVE", duration: 300, easing: { type: "LINEAR" } }).motion.duration, 0.3);
});

test("slides are written along the reading direction, so they mirror in Arabic", () => {
  assert.equal(motionTransition({ type: "MOVE_IN", direction: "LEFT", duration: 0.3 }).from, "end");
  assert.equal(motionTransition({ type: "SLIDE_IN", direction: "RIGHT", duration: 0.3 }).from, "start");
  assert.equal(motionTransition({ type: "MOVE_IN", direction: "TOP", duration: 0.3 }).from, "bottom");
});

test("a prototype's interactions become steps with triggers, recipes and what changes", () => {
  const names = new Map();
  for (const n of [frame, about, contact, hoverVariant]) layerNames(n, names);
  const specs = new Map();
  const index = (s) => { specs.set(s.id, s); s.children.forEach(index); };
  index(normalize(frame, {}));
  index(normalize(hoverVariant, {}));
  const steps = extractMotion(frame, names, specs);
  assert.equal(steps.length, 4);

  const auto = steps.find((s) => s.layer === "Home");
  assert.equal(auto.trigger, "after a delay (3000ms)");
  assert.equal(auto.action, 'goes to "About"');
  assert.match(auto.recipe, /PageTransition \(cross-fade\)/);

  const hover = steps.find((s) => s.trigger === "while hovering");
  assert.equal(hover.action, 'changes to the variant "Button/Hover"');
  assert.match(hover.recipe, /whileHover/);
  assert.equal(hover.transition.motion.type, "spring");
  assert.ok(hover.changes.some((c) => /^fill #e6a83b → #1f3b5e$/i.test(c)), hover.changes.join("; "));

  const overlay = steps.find((s) => s.action.startsWith("opens"));
  assert.equal(overlay.action, 'opens "Contact sheet" as an overlay');
  assert.equal(overlay.transition.from, "end");
  assert.deepEqual(overlay.transition.motion, { duration: 0.3, ease: [0.22, 1, 0.36, 1] });
  assert.match(overlay.recipe, /Sheet/);

  const menu = steps.find((s) => s.layer === "Menu");
  assert.equal(menu.transition.motion, null);

  const md = motionMarkdown(steps, 0);
  assert.match(md, /## Motion \(from the Figma prototype\)/);
  assert.match(md, /\*\*Button\*\*: on while hovering, changes to the variant "Button\/Hover"\. Figma: SMART_ANIMATE, GENTLE\. Motion: `transition=\{\{ type: "spring", mass: 1, stiffness: 100, damping: 15 \}\}`/);
  assert.match(md, /from end\. Motion: `transition=\{\{ duration: 0\.3, ease: \[0\.22, 1, 0\.36, 1\] \}\}`/);
});

test("a design with no prototype says so and points to the recipes", () => {
  assert.match(motionMarkdown([], 0), /no prototype interactions/);
});
