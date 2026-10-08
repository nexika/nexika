#!/usr/bin/env node
// How much faster `lawha check` is with parallel browser contexts (#106).
// Runs the full matrix (6 widths x light/dark x LTR/RTL + the reduced-motion pass = 25 variants)
// at each concurrency, a few times, and prints the median time and the speed-up over 1.
//
//   node plugins/lawha/bench/speed.mjs [--pages good.html,bad.html] [--concurrency 1,2,4,8] [--repeat 3]
//
// Pages are the engine's test fixtures (or any URL). Needs the engine built and installed
// (cd plugins/lawha/engine && npm ci && npm run build).
import { spawnSync } from "node:child_process";
import { mkdtempSync, rmSync } from "node:fs";
import { cpus, tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const ENGINE = fileURLToPath(new URL("../engine/", import.meta.url));
const CLI = join(ENGINE, "dist", "cli.js");
const FIX = join(ENGINE, "test", "fixtures");

const flag = (name, fallback) => {
  const i = process.argv.indexOf(`--${name}`);
  return i > 0 && process.argv[i + 1] ? process.argv[i + 1] : fallback;
};
const pages = flag("pages", "good.html,bad.html").split(",").map((p) => (/^[a-z]+:/.test(p) ? p : pathToFileURL(join(FIX, p)).href));
const levels = flag("concurrency", "1,2,4,8").split(",").map(Number);
const repeat = Number(flag("repeat", "3"));
const homes = { LAWHA_HOME: mkdtempSync(join(tmpdir(), "lawha-bench-")), NEXIKA_STATUS_HOME: mkdtempSync(join(tmpdir(), "lawha-bench-")) };

function once(page, concurrency) {
  const out = mkdtempSync(join(tmpdir(), "lawha-bench-run-"));
  const started = process.hrtime.bigint();
  const r = spawnSync(process.execPath, [CLI, "check", page, "--themes", "light,dark", "--dirs", "ltr,rtl", "--no-record", "--no-fail-exit", "--concurrency", String(concurrency), "--out", out], { encoding: "utf8", env: { ...process.env, ...homes } });
  const seconds = Number(process.hrtime.bigint() - started) / 1e9;
  rmSync(out, { recursive: true, force: true });
  if (r.status !== 0) throw new Error(`lawha check exited ${r.status}: ${r.stderr}`);
  return seconds;
}

const median = (xs) => [...xs].sort((a, b) => a - b)[Math.floor(xs.length / 2)];
const rows = [];
for (const page of pages) {
  const base = {};
  for (const c of levels) {
    const times = Array.from({ length: repeat }, () => once(page, c));
    base[c] = median(times);
    rows.push({ page: page.split("/").pop(), concurrency: c, seconds: Number(base[c].toFixed(1)), speedup: Number((base[levels[0]] / base[c]).toFixed(2)) });
    process.stderr.write(`${rows.at(-1).page} x${c}: ${rows.at(-1).seconds}s (${rows.at(-1).speedup}x)\n`);
  }
}
process.stdout.write(JSON.stringify({ node: process.version, cpus: cpus().length, repeat, variants: 25, rows }, null, 2) + "\n");
