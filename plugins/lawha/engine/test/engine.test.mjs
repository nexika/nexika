// lawha engine tests: run the built CLI against fixture pages with known faults.
import { strict as assert } from "node:assert";
import { execFile, execFileSync, spawn, spawnSync } from "node:child_process";
import { cpSync, mkdtempSync, readFileSync, statSync, symlinkSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";
import { fileURLToPath, pathToFileURL } from "node:url";
import { PNG } from "pngjs";

const ROOT = fileURLToPath(new URL("..", import.meta.url));
const CLI = join(ROOT, "dist", "cli.js");
const FIX = join(ROOT, "test", "fixtures");
const tmp = () => mkdtempSync(join(tmpdir(), "lawha-test-"));
// Never touch the real ~/.claude/nexika: every run gets throwaway homes.
const HOMES = { LAWHA_HOME: tmp(), NEXIKA_STATUS_HOME: tmp() };
// A fail verdict exits 1 with the summary still on stdout; anything else non-zero is a crash.
const exec = (args, opts = {}) => spawnSync(process.execPath, [CLI, ...args], { encoding: "utf8", timeout: 240_000, env: { ...process.env, ...HOMES, ...opts.env }, cwd: opts.cwd });
const run = (args, opts = {}) => {
  const r = exec(args, opts);
  if (r.status !== 0 && r.status !== 1) throw new Error(`lawha ${args[0]} exited ${r.status}: ${r.stderr}`);
  const out = JSON.parse(r.stdout);
  if (out && typeof out === "object" && "verdict" in out) assert.equal(r.status, out.verdict === "fail" ? 1 : 0, `exit code for verdict ${out.verdict}`);
  else assert.equal(r.status, 0, `lawha ${args[0]} exited ${r.status}`);
  return out;
};
const lawha = (...args) => run(args);
const page = (name) => pathToFileURL(join(FIX, name)).href;

test("a clean page passes with no problems", () => {
  const out = tmp();
  const summary = lawha("check", page("good.html"), "--widths", "360,1280", "--out", out);
  assert.equal(summary.verdict, "pass");
  assert.deepEqual([summary.fail, summary.warn], [0, 0]);
  const run = JSON.parse(readFileSync(join(out, "run.json"), "utf8"));
  assert.equal(run.shots.length, 3); // two widths and one reduced-motion pass
  assert.match(readFileSync(join(out, "report.html"), "utf8"), /Passes every required check/);
});

test("a fail verdict exits 1 so gates stop; --no-fail-exit keeps 0 for callers that read the JSON", () => {
  const failing = exec(["check", page("bad.html"), "--widths", "390", "--no-see", "--out", tmp()]);
  assert.equal(failing.status, 1, failing.stderr);
  assert.equal(JSON.parse(failing.stdout).verdict, "fail");
  const parsed = exec(["check", page("bad.html"), "--widths", "390", "--no-see", "--no-fail-exit", "--out", tmp()]);
  assert.equal(parsed.status, 0, parsed.stderr);
  assert.equal(JSON.parse(parsed.stdout).verdict, "fail");
});

test("a page that redirects elsewhere (a login wall) fails instead of passing as the page asked for", () => {
  const out = tmp();
  const summary = lawha("check", page("private.html"), "--widths", "390", "--no-see", "--out", out);
  assert.equal(summary.verdict, "fail");
  const run = JSON.parse(readFileSync(join(out, "run.json"), "utf8"));
  const moved = run.findings.filter((f) => f.check === "page.redirected");
  assert.ok(moved.length >= 1 && moved.every((f) => f.severity === "fail"));
  assert.match(moved[0].message, /good\.html/);
  assert.ok(summary.top.some((t) => t.includes("page.redirected")));
});

// The app runs in its own process: the CLI runs synchronously in the tests.
const app = async () => {
  const child = spawn(process.execPath, [join(FIX, "server.mjs")], { stdio: ["ignore", "pipe", "inherit"] });
  const port = await new Promise((done) => child.stdout.once("data", (d) => done(Number(String(d).trim()))));
  return { url: (path) => `http://127.0.0.1:${port}${path}`, stop: () => child.kill() };
};
const checkAsync = (args) => new Promise((done) => {
  execFile(process.execPath, [CLI, "check", ...args, "--widths", "390", "--no-see", "--no-record", "--no-fail-exit", "--out", tmp()], { encoding: "utf8", timeout: 240_000, env: { ...process.env, ...HOMES } }, (error, stdout) => {
    assert.ok(!error || error.code === undefined, String(error));
    done(JSON.parse(stdout));
  });
});
const checks = (summary) => new Set(JSON.parse(readFileSync(summary.run, "utf8")).findings.map((f) => f.check));

test("a page behind login is checked with a cookie, a header or a saved storage state", async () => {
  const server = await app();
  try {
    assert.ok(checks(await checkAsync([server.url("/private")])).has("page.redirected"));
    assert.ok(!checks(await checkAsync([server.url("/private"), "--cookie", "session=ok"])).has("page.redirected"));
    assert.ok(!checks(await checkAsync([server.url("/private"), "--cookie=session=ok"])).has("page.redirected"));
    assert.ok(!checks(await checkAsync([server.url("/private"), "--header", "X-Token: t"])).has("page.redirected"));
    const state = join(tmp(), "state.json");
    writeFileSync(state, JSON.stringify({ cookies: [{ name: "session", value: "ok", domain: "127.0.0.1", path: "/", expires: -1, httpOnly: false, secure: false, sameSite: "Lax" }], origins: [] }));
    assert.ok(!checks(await checkAsync([server.url("/private"), "--storage-state", state])).has("page.redirected"));
  } finally {
    server.stop();
  }
});

test("--wait-for waits for content a client-rendered app draws after the load event", async () => {
  const server = await app();
  try {
    assert.ok(!checks(await checkAsync([server.url("/spa"), "--settle", "100"])).has("a11y.image-alt"), "the late image is not there yet");
    assert.ok(checks(await checkAsync([server.url("/spa"), "--settle", "100", "--wait-for", "#late", "--network-idle"])).has("a11y.image-alt"));
  } finally {
    server.stop();
  }
});

test("a broken module breaks only its own command", () => {
  // A half-written figma-spec.js once took down lawha check: every module loaded at start.
  const copy = tmp();
  cpSync(join(ROOT, "dist"), join(copy, "dist"), { recursive: true });
  cpSync(join(ROOT, "package.json"), join(copy, "package.json"));
  symlinkSync(join(ROOT, "node_modules"), join(copy, "node_modules"), "dir");
  writeFileSync(join(copy, "dist", "figma-spec.js"), "export const = ;\n");
  const cli = (...args) => spawnSync(process.execPath, [join(copy, "dist", "cli.js"), ...args], { encoding: "utf8", timeout: 240_000, env: { ...process.env, ...HOMES } });
  assert.equal(cli("version").status, 0);
  const checked = cli("check", page("good.html"), "--widths", "360", "--no-see", "--no-record", "--out", tmp());
  assert.equal(checked.status, 0, checked.stderr);
  assert.equal(JSON.parse(checked.stdout).verdict, "pass");
  const figma = cli("figma", "spec", "https://www.figma.com/design/AbCdEfGhIjKl/x?node-id=1-2");
  assert.notEqual(figma.status, 0);
  assert.match(figma.stderr, /lawha:/);
});

test("one layout shift is one problem across widths, and one unlucky load is not reported", async () => {
  const out = tmp();
  const summary = lawha("check", page("shift.html"), "--widths", "390,1280", "--no-see", "--no-record", "--out", out);
  assert.equal(summary.top.filter((t) => t.includes("layout.shift")).length, 1, summary.top.join("\n"));
  assert.match(summary.top.find((t) => t.includes("layout.shift")), /median/);
  const server = await app();
  try {
    assert.ok(!checks(await checkAsync([server.url("/shift")])).has("layout.shift"), "only the first of three loads shifted");
  } finally {
    server.stop();
  }
});

test("index reads Next.js routes, Vue components and tailwind.config.js", () => {
  const out = join(tmp(), "system.json");
  lawha("index", join(FIX, "project-wide"), "--out", out);
  const s = JSON.parse(readFileSync(out, "utf8"));
  assert.deepEqual(s.routes, ["/", "/about", "/blog/[slug]", "/pricing"]);
  assert.ok(s.tokens.some((t) => t.name === "colors.brand" && t.value === "#1f3a5f" && t.source === "tailwind.config.js"), JSON.stringify(s.tokens));
  assert.ok(s.tokens.some((t) => t.name === "borderRadius.card" && t.value === "12px"));
  const card = s.components.find((c) => c.name === "PriceCard");
  assert.deepEqual(card?.props, [{ name: "title", type: "string", optional: false }, { name: "price", type: "number", optional: true }]);
  assert.ok(s.drift.some((d) => d.file.endsWith("PriceCard.vue") && d.kind === "physical utility"));
  assert.ok(s.drift.some((d) => d.file.endsWith("PriceCard.vue") && d.kind === "hard-coded colour"));
  assert.equal(s.stack.next, "15.5.0");
  assert.equal(s.stack.vue, "3.5.0");
});

test("every planted fault is found, once per problem", () => {
  const out = tmp();
  const summary = lawha("check", page("bad.html"), "--widths", "390,1280", "--out", out);
  const run = JSON.parse(readFileSync(join(out, "run.json"), "utf8"));
  const checks = new Set(run.findings.map((f) => `${f.check}:${f.severity}`));
  for (const expected of [
    "layout.horizontal-scroll:fail",
    "layout.clipped-text:fail",
    "phone.tap-target:fail",
    "phone.base-font:warn",
    "a11y.color-contrast:fail",
    "a11y.image-alt:fail",
    "motion.reduced:fail",
    "motion.costly-property:warn",
    "rtl.physical-class:info",
    "rtl.physical-css:info",
  ]) assert.ok(checks.has(expected), `missing ${expected}`);
  assert.ok(!checks.has("layout.overlapping-text:fail"), "lines that only touch are not overlapping text");
  assert.equal(summary.verdict, "fail");
  assert.equal(summary.fail, 6); // grouped across widths
  assert.equal(run.findings.filter((f) => f.check === "layout.horizontal-scroll").length, 1, "1280px does not scroll sideways");
});

test("symmetric shorthands are not RTL problems; asymmetric ones are, and fail when RTL is expected", () => {
  const out = tmp();
  lawha("check", page("bad.html"), "--widths", "1280", "--expect-rtl", "--no-see", "--out", out);
  const run = JSON.parse(readFileSync(join(out, "run.json"), "utf8"));
  const rtl = run.findings.filter((f) => f.check === "rtl.physical-css");
  assert.ok(rtl.length >= 1 && rtl.every((f) => f.severity === "fail"));
  assert.ok(rtl.some((f) => f.message.includes("margin-left: 16px")));
  const clean = tmp();
  lawha("check", page("good.html"), "--widths", "1280", "--expect-rtl", "--no-see", "--out", clean);
  const good = JSON.parse(readFileSync(join(clean, "run.json"), "utf8"));
  assert.equal(good.findings.filter((f) => f.check.startsWith("rtl.")).length, 0, "padding: 16px mirrors fine");
});

test("the eye measures rhythm, alignment, type and colour", () => {
  const out = tmp();
  lawha("check", page("bad.html"), "--widths", "1280", "--no-audit", "--out", out);
  const [seen] = JSON.parse(readFileSync(join(out, "run.json"), "utf8")).seen;
  assert.ok(seen.rhythm.offScale.some((o) => o.gap === 13), "13px is off a 4px scale");
  assert.ok(seen.alignment.nearMisses.some((n) => n.off === 3), "boxes 3px apart are a near-miss");
  assert.ok(seen.typography.sizes.some((s) => s.px === 13));
  assert.ok(seen.colour.lowContrast.some((c) => c.ratio < 4.5));
  assert.ok(seen.colour.palette.length >= 2);
});

test("lawha's own report passes lawha's check", () => {
  const first = tmp();
  lawha("check", page("bad.html"), "--widths", "390", "--out", first);
  const second = tmp();
  const summary = lawha("check", pathToFileURL(join(first, "report.html")).href, "--widths", "360,768,1280", "--themes", "light,dark", "--out", second);
  assert.equal(summary.fail, 0, JSON.stringify(summary.top));
  assert.equal(summary.warn, 0, JSON.stringify(summary.top));
});

function png(path, width, height, paint) {
  const img = new PNG({ width, height });
  for (let y = 0; y < height; y++) for (let x = 0; x < width; x++) {
    const [r, g, b] = paint(x, y);
    const i = (y * width + x) * 4;
    img.data[i] = r; img.data[i + 1] = g; img.data[i + 2] = b; img.data[i + 3] = 255;
  }
  writeFileSync(path, PNG.sync.write(img));
}

test("diff scores identical images 100% and finds the changed region", () => {
  const dir = tmp();
  const white = () => [255, 255, 255];
  png(join(dir, "a.png"), 200, 120, white);
  png(join(dir, "b.png"), 200, 120, white);
  png(join(dir, "c.png"), 200, 120, (x, y) => (x >= 100 && x < 150 && y >= 40 && y < 80 ? [0, 0, 0] : [255, 255, 255]));
  assert.equal(lawha("diff", join(dir, "a.png"), join(dir, "b.png")).match, 1);
  const changed = lawha("diff", join(dir, "c.png"), join(dir, "a.png"), "--heatmap", join(dir, "heat.png"));
  assert.ok(changed.match < 1 && changed.match > 0.9);
  const [region] = changed.regions;
  assert.ok(region.x <= 100 && region.x + region.w >= 150 && region.y <= 40 && region.y + region.h >= 80, JSON.stringify(region));
  assert.ok(readFileSync(join(dir, "heat.png")).length > 0);
});

test("diff handles a 2x design export and different sizes", () => {
  const dir = tmp();
  png(join(dir, "built.png"), 100, 50, () => [20, 40, 200]);
  png(join(dir, "design@2x.png"), 200, 100, () => [20, 40, 200]);
  assert.equal(lawha("diff", join(dir, "built.png"), join(dir, "design@2x.png"), "--scale", "0.5").match, 1);
  const taller = lawha("diff", join(dir, "built.png"), join(dir, "design@2x.png"));
  assert.ok(taller.sizeMismatch && taller.match < 0.5);
});

test("index reads tokens, shadcn, components with props, routes, fonts and drift", () => {
  const out = join(tmp(), "system.json");
  lawha("index", join(FIX, "project"), "--out", out);
  const s = JSON.parse(readFileSync(out, "utf8"));
  assert.equal(s.stack.tanstackRouter, "1.130.0");
  assert.deepEqual(s.shadcn.components, ["button"]);
  const card = s.components.find((c) => c.name === "LessonCard");
  assert.deepEqual(card.props.map((p) => [p.name, p.optional]), [["title", false], ["minutes", true], ["status", false]]);
  assert.ok(s.components.some((c) => c.name === "Badge"));
  assert.ok(!s.components.some((c) => c.name === "Button"), "shadcn ui components are listed separately");
  assert.deepEqual(s.routes, ["/index", "/lessons/$id"]);
  assert.ok(s.tokens.some((t) => t.name === "--color-brand" && t.value === "#2b2fd6"));
  assert.deepEqual(new Set(s.drift.map((d) => d.kind)), new Set(["hard-coded colour", "arbitrary size", "physical utility"]));
});

test("a check is recorded in lawha's folder and announced in the shared status file", () => {
  const homes = { LAWHA_HOME: tmp(), NEXIKA_STATUS_HOME: tmp() };
  const project = tmp();
  execFileSync("git", ["init", "-q", project]);
  const summary = run(["check", page("bad.html"), "--widths", "390", "--no-see", "--out", join(project, ".lawha", "runs", "x")], { env: homes, cwd: project });
  assert.ok(summary.recorded.startsWith(homes.LAWHA_HOME), summary.recorded);
  const rec = JSON.parse(readFileSync(summary.recorded, "utf8"));
  assert.equal(rec.schema, "nexika.lawha.check/1");
  assert.equal(rec.verdict, "fail");
  assert.equal(rec.counts.fail, summary.fail);
  assert.ok(rec.problems.length > 0 && rec.problems.every((p) => p.severity !== "info"));
  assert.ok(rec.project.endsWith(project.split("/").pop()));
  const status = JSON.parse(readFileSync(join(homes.NEXIKA_STATUS_HOME, "lawha.json"), "utf8"));
  assert.equal(status.schema, "nexika.lawha/1");
  assert.equal(Object.values(status.checks)[0], summary.recorded);
  assert.equal(statSync(summary.recorded).mode & 0o777, 0o600, "records are owner-only");
  const quiet = run(["check", page("good.html"), "--widths", "390", "--no-see", "--no-record", "--out", tmp()], { env: homes, cwd: project });
  assert.equal(quiet.recorded, null);
});

test("variants run in parallel browser contexts and give the same result as one at a time", () => {
  // #106: the full matrix ran one variant after another (80 s inside a 3-round fix loop).
  const args = ["check", page("bad.html"), "--widths", "390,768,1280", "--themes", "light,dark", "--no-see", "--no-record"];
  const one = tmp(), many = tmp();
  run([...args, "--concurrency", "1", "--out", one]);
  run([...args, "--concurrency", "4", "--out", many]);
  const read = (dir) => JSON.parse(readFileSync(join(dir, "run.json"), "utf8"));
  const [a, b] = [read(one), read(many)];
  assert.equal(a.summary.concurrency, 1);
  assert.equal(b.summary.concurrency, 4);
  assert.deepEqual(b.shots.map((s) => s.variant), a.shots.map((s) => s.variant), "shots keep the matrix order");
  const key = (f) => `${f.check}|${f.severity}|${f.width}|${f.theme}|${f.dir}|${f.motion}`;
  assert.deepEqual(b.findings.map(key), a.findings.map(key), "same findings, same order");
});
