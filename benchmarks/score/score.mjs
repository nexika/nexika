// Score every tool's run of a benchmark task the same way.
//
//   node score/score.mjs figma   # runs/figma/<tool>/, compared with public/design/<width>.png
//   node score/score.mjs brief   # runs/brief/<tool>/, in English and Arabic, light and dark
//
// Each run folder is a copy of ../starter with the tool's output. It is installed, built and served,
// then measured with lawha's engine (Playwright, axe-core for accessibility, pixelmatch for the design
// comparison). Raw counts are kept per category; nothing is blended into one score.
import { execFileSync, spawn } from "node:child_process";
import { existsSync, readdirSync, readFileSync, statSync, writeFileSync } from "node:fs";
import { join, relative, resolve } from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

const HERE = fileURLToPath(new URL("..", import.meta.url));
const LAWHA = resolve(HERE, "../plugins/lawha/engine/dist/cli.js");
const task = process.argv[2];
if (!["figma", "brief"].includes(task)) throw new Error("usage: node score/score.mjs figma|brief");
const runs = join(HERE, "runs", task);
const tools = readdirSync(runs).filter((d) => statSync(join(runs, d)).isDirectory() && existsSync(join(runs, d, "package.json")));
const WIDTHS = task === "figma" ? [390, 768, 1024, 1280, 1440] : [360, 390, 768, 1024, 1280, 1536];

const sh = (cmd, args, cwd) => {
  try { return { ok: true, out: execFileSync(cmd, args, { cwd, encoding: "utf8", stdio: ["ignore", "pipe", "pipe"], timeout: 600_000 }) }; }
  catch (e) { return { ok: false, out: `${e.stdout ?? ""}${e.stderr ?? ""}`.slice(-2000) }; }
};

function serve(dir, port) {
  const child = spawn("npx", ["vite", "preview", "--port", String(port), "--strictPort"], { cwd: dir, stdio: "ignore", detached: true });
  return child;
}

async function waitFor(url) {
  for (let i = 0; i < 60; i++) {
    try { if ((await fetch(url)).ok) return true; } catch { /* not yet */ }
    await new Promise((r) => setTimeout(r, 500));
  }
  return false;
}

/** Colours written as literals in components instead of tokens (#abc, rgb(), arbitrary [#...] classes). */
function hardcodedColours(dir) {
  let n = 0;
  const walk = (d) => {
    for (const f of readdirSync(d)) {
      const p = join(d, f);
      if (statSync(p).isDirectory()) { if (!["node_modules", "dist", "assets"].includes(f)) walk(p); continue; }
      if (!/\.(tsx|jsx|ts)$/.test(f)) continue;
      n += (readFileSync(p, "utf8").match(/#[0-9a-fA-F]{3,8}\b|rgba?\(/g) ?? []).length;
    }
  };
  if (existsSync(join(dir, "src"))) walk(join(dir, "src"));
  return n;
}

// Did the page do what the brief asked? Counting problems alone rewards an empty page.
const { chromium } = createRequire(LAWHA)("playwright");
async function completeness(url) {
  const browser = await chromium.launch();
  const look = async (u, scheme) => {
    const page = await browser.newPage({ viewport: { width: 1280, height: 900 }, colorScheme: scheme });
    await page.goto(u, { waitUntil: "networkidle" }).catch(() => undefined);
    await page.waitForTimeout(800);
    const facts = await page.evaluate(() => {
      const text = document.body.innerText;
      const letters = text.match(/\p{L}/gu) ?? [];
      const arabic = text.match(/[\u0600-\u06FF]/g) ?? [];
      const bg = (el) => getComputedStyle(el).backgroundColor;
      const ground = [document.body, document.documentElement, document.querySelector("main")].map((e) => e && bg(e)).find((c) => c && c !== "rgba(0, 0, 0, 0)") ?? "rgb(255, 255, 255)";
      const n = ground.match(/[\d.]+/g).map(Number);
      const words = (re) => re.test(text);
      return {
        dir: getComputedStyle(document.body).direction,
        arabicShare: letters.length ? arabic.length / letters.length : 0,
        groundLightness: (n[0] * 0.2126 + n[1] * 0.7152 + n[2] * 0.0722) / 255,
        headings: document.querySelectorAll("h1, h2, h3").length,
        h1: document.querySelectorAll("h1").length,
        height: document.documentElement.scrollHeight,
        parts: {
          pricing: words(/pricing|price|free|pro\b|month|السعر|الأسعار|مجاني|شهري/i),
          testimonial: !!document.querySelector("blockquote, figure blockquote, q") || words(/[“"].{20,}[”"]/),
          howItWorks: words(/how it works|كيف يعمل|steps|step 1|الخطوة/i),
          cta: document.querySelectorAll("a[href], button").length >= 3,
        },
      };
    });
    await page.close();
    return facts;
  };
  try {
    const en = await look(url, "light");
    const dark = await look(url, "dark");
    const ar = await look(`${url}?lang=ar`, "light");
    return {
      sections: en.headings, h1: en.h1, height: en.height, parts: en.parts,
      arabic: { rtl: ar.dir === "rtl", arabicShare: Math.round(ar.arabicShare * 100) / 100 },
      dark: { changes: Math.abs(en.groundLightness - dark.groundLightness) > 0.4 },
    };
  } finally {
    await browser.close();
  }
}

const CATEGORY = (check) => check.startsWith("layout.") ? "layout" : check.startsWith("phone.") ? "phone" : check.startsWith("a11y.") ? "accessibility" : check.startsWith("motion.") ? "motion" : check.startsWith("rtl.") ? "rtl" : check.startsWith("design.") ? "design" : "other";

const results = [];
let port = 4800;
for (const tool of tools) {
  const dir = join(runs, tool);
  const r = { tool, build: false, problems: {}, looks: {}, hardcodedColours: hardcodedColours(dir), notes: [] };
  results.push(r);
  if (!sh("npm", ["install", "--no-audit", "--no-fund", "--loglevel=error"], dir).ok) { r.notes.push("npm install failed"); continue; }
  const build = sh("npm", ["run", "build"], dir);
  r.build = build.ok;
  if (!build.ok) { r.notes.push(`build failed: ${build.out.split("\n").filter(Boolean).slice(-3).join(" | ")}`); continue; }
  const server = serve(dir, ++port);
  try {
    const url = `http://localhost:${port}/`;
    if (!(await waitFor(url))) { r.notes.push("the built app did not start"); continue; }
    const out = join(dir, ".lawha", "score");
    const args = ["check", url, "--widths", WIDTHS.join(","), "--no-record", "--no-see", "--out", out];
    if (task === "figma" && existsSync(join(HERE, "public", "design"))) args.push("--against", join(HERE, "public", "design"));
    if (task === "brief") args.push("--themes", "light,dark", "--expect-rtl", "--rtl-url", `${url}?lang=ar`);
    const check = sh(process.execPath, [LAWHA, ...args], HERE);
    if (!check.ok) { r.notes.push(`check failed: ${check.out.slice(-300)}`); continue; }
    const run = JSON.parse(readFileSync(join(out, "run.json"), "utf8"));
    // One problem per check and element, whatever the number of widths it appears at.
    const seen = new Set();
    for (const f of run.findings) {
      if (f.check.startsWith("design.")) continue;
      const key = `${f.check}|${f.selector ?? f.message}`;
      if (seen.has(key)) continue;
      seen.add(key);
      const c = CATEGORY(f.check);
      r.problems[c] ??= { fail: 0, warn: 0 };
      if (f.severity !== "info") r.problems[c][f.severity]++;
    }
    for (const d of run.diffs ?? []) r.looks[d.variant.split("-")[0]] = { looks: Math.round(d.aligned.match * 1000) / 10, position: Math.round(d.match * 1000) / 10 };
    r.report = relative(HERE, join(out, "report.html")); // not committed; local to whoever ran the score
    if (task === "brief") r.complete = await completeness(url);
  } finally {
    try { process.kill(-server.pid); } catch { /* gone */ }
  }
}

writeFileSync(join(runs, "results.json"), JSON.stringify({ task, scored: new Date().toISOString(), widths: WIDTHS, results }, null, 1));
const cats = ["layout", "phone", "accessibility", "motion", ...(task === "brief" ? ["rtl"] : [])];
const lines = [`# Results: ${task === "figma" ? "Figma to code" : "brief to page"}`, "", `Scored ${new Date().toISOString().slice(0, 10)} at ${WIDTHS.join(", ")}px${task === "brief" ? ", light and dark, English and Arabic" : ""}. Problems are counted once per check and element (must fix / should fix).`, ""];
const head = ["Tool", "Builds", ...(task === "figma" ? ["Looks like the design (390 / 1024 / 1440)"] : ["Did the brief (parts / Arabic RTL / dark)"]), ...cats, "Colours hard-coded"];
lines.push(`| ${head.join(" | ")} |`, `|${head.map(() => "---").join("|")}|`);
for (const r of results) {
  const looks = ["390", "1024", "1440"].map((w) => (r.looks[w] ? `${r.looks[w].looks}%` : "–")).join(" / ");
  const cell = (c) => { const p = r.problems[c] ?? { fail: 0, warn: 0 }; return `${p.fail} / ${p.warn}`; };
  const c = r.complete;
  const did = c ? `${Object.values(c.parts).filter(Boolean).length + (c.h1 === 1 ? 1 : 0)}/5 · ${c.arabic.rtl && c.arabic.arabicShare > 0.6 ? "yes" : `no (${Math.round(c.arabic.arabicShare * 100)}% Arabic${c.arabic.rtl ? ", RTL" : ""})`} · ${c.dark.changes ? "yes" : "no"}` : "–";
  lines.push(`| ${[r.tool, r.build ? "yes" : "**no**", ...(task === "figma" ? [looks] : [did]), ...cats.map(cell), String(r.hardcodedColours)].join(" | ")} |`);
}
for (const r of results) if (r.notes.length) lines.push("", `${r.tool}: ${r.notes.join("; ")}`);
writeFileSync(join(runs, "results.md"), lines.join("\n") + "\n");
process.stdout.write(lines.join("\n") + "\n");
