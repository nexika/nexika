// lawha 0.3 tests: design directions, inspiration, blind comparisons, 3D and text-over-media checks.
import { strict as assert } from "node:assert";
import { execFileSync } from "node:child_process";
import { existsSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";
import { fileURLToPath, pathToFileURL } from "node:url";
import { PNG } from "pngjs";
import { check, contrastRatio, themeCss } from "../dist/direction.js";
import { licence, normalFamily } from "../dist/inspire.js";

const ROOT = fileURLToPath(new URL("..", import.meta.url));
const CLI = join(ROOT, "dist", "cli.js");
const FIX = join(ROOT, "test", "fixtures");
const tmp = () => mkdtempSync(join(tmpdir(), "lawha-test-"));
// Never touch the real ~/.claude/nexika: every run gets throwaway homes.
const HOMES = { LAWHA_HOME: tmp(), NEXIKA_STATUS_HOME: tmp() };
const lawhaIn = (cwd, ...args) => JSON.parse(execFileSync(process.execPath, [CLI, ...args], { encoding: "utf8", timeout: 240_000, env: { ...process.env, ...HOMES }, cwd }));
const lawha = (...args) => lawhaIn(undefined, ...args);
const page = (name) => pathToFileURL(join(FIX, name)).href;

const palette = (o = {}) => ({ background: "#FAF7F2", surface: "#FFFFFF", text: "#1B2330", muted: "#566070", primary: "#1F3A5F", primaryText: "#FFFFFF", accent: "#E5A93B", border: "#C9BFAF", ...o });
const dark = (o = {}) => ({ background: "#12161D", surface: "#1A2029", text: "#EEF1F5", muted: "#A7B0BE", primary: "#8DB3E2", primaryText: "#0E1A2B", accent: "#E5A93B", border: "#3A4554", ...o });
const direction = (id, o = {}) => ({
  id, name: `Direction ${id}`, mood: "calm", signature: "a line", motif: "underline", motion: "calm", layout: "editorial",
  fonts: { display: { family: "Fraunces", weights: [600] }, text: { family: "Source Sans 3", weights: [400] } },
  scale: { base: 17, ratio: 1.25 }, radius: 6, spacing: 4, palette: { light: palette(), dark: dark() }, ...o,
});
const three = () => [
  direction("a"),
  direction("b", { fonts: { display: { family: "Space Grotesk", weights: [500] }, text: { family: "IBM Plex Sans", weights: [400] } }, layout: "bento", motion: "precise", palette: { light: palette({ background: "#E9EEF3", primary: "#0F6E66" }), dark: dark() } }),
  direction("c", { fonts: { display: { family: "Bricolage Grotesque", weights: [700] }, text: { family: "Nunito Sans", weights: [400] } }, layout: "asymmetric", motion: "lively", palette: { light: palette({ background: "#F6F3F7", primary: "#7B2C63" }), dark: dark() } }),
];

test("three distinct, readable directions pass; weak contrast, small text and look-alikes fail", () => {
  assert.equal(contrastRatio("#000000", "#FFFFFF"), 21);
  assert.deepEqual(check(three()).filter((p) => p.severity === "fail"), []);
  const weak = three();
  weak[0].palette.light.muted = "#B9B4AA";
  weak[1].scale.base = 14;
  weak[2].fonts.display.family = "Fraunces";
  const fails = check(weak).filter((p) => p.severity === "fail").map((p) => `${p.direction}: ${p.message}`);
  assert.ok(fails.some((m) => m.startsWith("a: light: muted text on background")), fails.join("\n"));
  assert.ok(fails.some((m) => m.startsWith("b: base text 14px")));
  assert.ok(fails.some((m) => m.startsWith("a+c: both use Fraunces")));
});

test("a direction too close to a recent choice fails", () => {
  const recent = [{ at: "2026-10-01T00:00:00Z", project: "/x/old", name: "Old ink", display: "Fraunces", text: "Inter", primaryHue: 214, layout: "editorial" }];
  assert.ok(check(three(), recent).some((p) => p.direction === "a" && p.severity === "fail" && p.message.includes("too close")));
});

test("the chosen direction becomes Tailwind and shadcn tokens, light and dark", () => {
  const css = themeCss(direction("a"));
  for (const want of ["@theme inline", "--background: #FAF7F2", ".dark", "--background: #12161D", "--font-display", "Fraunces", "--lawha-motion: calm;", "--lawha-base: 420;"]) assert.ok(css.includes(want), `missing ${want}`);
  // Text on the accent reads in both themes: dark text on saffron even in dark mode.
  for (const block of [css.split(".dark")[0], css.split(".dark")[1]]) {
    const on = block.match(/--accent-foreground: (#[0-9A-Fa-f]{6})/)[1];
    assert.ok(contrastRatio(on, "#E5A93B") >= 4.5, `${on} on the accent`);
  }
});

test("direct renders previews and writes the choice into the app folder", () => {
  const app = tmp();
  writeFileSync(join(app, "package.json"), "{}");
  mkdirSync(join(app, "src"));
  writeFileSync(join(app, "directions.json"), JSON.stringify(three()));
  const out = join(app, "previews");
  const shown = lawhaIn(app, "direct", "preview", "directions.json", "--kind", "dashboard", "--product", "Notes", "--audience", "students", "--feeling", "calm", "--out", out);
  assert.equal(shown.fail, 0);
  assert.ok(existsSync(shown.gallery));
  assert.ok(readdirSync(out).filter((f) => f.endsWith(".png")).length >= 9, "light and dark, phone and desktop for each");
  const chosen = lawhaIn(app, "direct", "choose", "directions.json", "a");
  assert.ok(readFileSync(join(app, "src", "lawha-theme.css"), "utf8").includes("--primary"));
  assert.equal(JSON.parse(readFileSync(join(app, ".lawha", "design.json"), "utf8")).direction.id, "a");
  assert.equal(chosen.history, 1);
});

test("font licences: free fonts are free, paid ones get a free look-alike", () => {
  assert.equal(normalFamily("Inter Variable"), "inter");
  assert.equal(normalFamily("sohne-var"), "sohne");
  assert.equal(licence("Inter Variable").free, true);
  assert.equal(licence("SourceCodePro").free, true);
  assert.deepEqual(licence("Berkeley Mono"), { free: false, alike: "JetBrains Mono or Geist Mono" });
  assert.equal(licence("sohne-var").free, false);
  assert.equal(licence("Made Up Sans").free, null);
});

test("inspire reads a page's fonts, colours, motion and 3D library", () => {
  const out = tmp();
  lawha("inspire", page("inspire.html"), "--out", out);
  const dna = JSON.parse(readFileSync(join(out, "dna.json"), "utf8"));
  const md = readFileSync(join(out, "dna.md"), "utf8");
  assert.ok(dna.fonts.some((f) => f.family === "Inter Variable" && f.free === true));
  assert.ok(dna.motion.libraries.some((l) => /three/i.test(l.name ?? l)), JSON.stringify(dna.motion.libraries));
  assert.ok(dna.motion.keyframes.includes("pulse-N"), "numbered keyframes are grouped");
  assert.match(md, /cubic-bezier\(0\.22, 1, 0\.36, 1\)/, "the easing is kept whole");
  for (const f of ["desktop.png", "desktop-fold.png", "phone-fold.png"]) assert.ok(existsSync(join(out, f)), f);
});

test("ab hides which side is which, and reveal turns a pick back into a version", () => {
  const out = tmp();
  const made = lawha("ab", page("good.html"), page("scene-good.html"), "--a-label", "current", "--b-label", "candidate", "--widths", "390", "--out", out);
  assert.deepEqual(readdirSync(out).filter((f) => !f.startsWith(".")), ["pair-390.png"], "only the pair is visible");
  const pair = PNG.sync.read(readFileSync(made.pairs[0]));
  assert.equal(pair.width, 390 * 2 + 32);
  // Both pages to the end: the pair is as tall as the taller one, never cut short.
  const tall = Math.max(...["a", "b"].map((v) => PNG.sync.read(readFileSync(join(out, ".key", `${v}-390.png`))).height));
  assert.equal(pair.height, tall);
  const key = JSON.parse(readFileSync(join(out, ".key", "key.json"), "utf8"));
  const left = lawha("ab", "reveal", out, "--pick", "left");
  assert.equal(left.winner, key.left);
  assert.equal(left.recorded, false, "a judge's pick is not the person's taste");
  const right = lawha("ab", "reveal", out, "--pick", "right", "--by", "user", "--note", "cleaner");
  assert.notEqual(right.winner, key.left);
  const taste = lawha("ab", "taste");
  assert.equal(taste.at(-1).note, "cleaner");
  assert.equal(taste.at(-1).winner, right.label);
});

test("a canvas that ignores reduce motion fails, and pale text over it fails; a careful scene passes", () => {
  const bad = tmp();
  lawha("check", page("scene-bad.html"), "--widths", "1280", "--no-see", "--no-record", "--no-fail-exit", "--out", bad);
  const found = JSON.parse(readFileSync(join(bad, "run.json"), "utf8")).findings.map((f) => f.check);
  assert.ok(found.includes("motion.webgl-reduced"), found.join(", "));
  assert.ok(found.includes("a11y.contrast-over-media"), found.join(", "));
  const good = tmp();
  const summary = lawha("check", page("scene-good.html"), "--widths", "1280", "--no-see", "--no-record", "--out", good);
  const goodFound = JSON.parse(readFileSync(join(good, "run.json"), "utf8")).findings.map((f) => f.check);
  assert.ok(!goodFound.includes("motion.webgl-reduced") && !goodFound.includes("a11y.contrast-over-media"), goodFound.join(", "));
  assert.equal(summary.verdict, "pass");
});

test("the eye ranks where the eye lands first", () => {
  const out = tmp();
  lawha("check", page("inspire.html"), "--widths", "1280", "--no-record", "--no-fail-exit", "--out", out);
  const seen = JSON.parse(readFileSync(join(out, "run.json"), "utf8")).seen[0];
  assert.ok(seen.focus.length >= 2);
  assert.equal(seen.focus[0].weight, 1);
  assert.match(seen.focus.slice(0, 2).map((f) => f.label).join(" | "), /Ship calmer software/);
});
