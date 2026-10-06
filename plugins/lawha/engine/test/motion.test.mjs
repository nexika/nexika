// lawha 0.4 tests: motion that never stops, motion that is too slow, and motion that behaves.
import { strict as assert } from "node:assert";
import { execFileSync } from "node:child_process";
import { mkdtempSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";
import { fileURLToPath, pathToFileURL } from "node:url";

const ROOT = fileURLToPath(new URL("..", import.meta.url));
const CLI = join(ROOT, "dist", "cli.js");
const FIX = join(ROOT, "test", "fixtures");
const tmp = () => mkdtempSync(join(tmpdir(), "lawha-test-"));
// Never touch the real ~/.claude/nexika: every run gets throwaway homes.
const HOMES = { LAWHA_HOME: tmp(), NEXIKA_STATUS_HOME: tmp() };
const check = (name) => {
  const out = tmp();
  const summary = JSON.parse(execFileSync(process.execPath, [CLI, "check", pathToFileURL(join(FIX, name)).href, "--widths", "1280", "--no-see", "--no-record", "--out", out], { encoding: "utf8", timeout: 240_000, env: { ...process.env, ...HOMES } }));
  return { summary, findings: JSON.parse(readFileSync(join(out, "run.json"), "utf8")).findings };
};

test("a banner that moves forever and a 2.4s entrance are flagged", () => {
  const { findings } = check("motion-bad.html");
  const endless = findings.filter((f) => f.check === "motion.endless");
  const slow = findings.filter((f) => f.check === "motion.slow");
  assert.equal(endless.length, 1, JSON.stringify(findings.map((f) => f.check)));
  assert.match(endless[0].selector, /banner/);
  assert.equal(slow.length, 1);
  assert.match(slow[0].message, /2\.4s/);
  assert.match(slow[0].selector, /title/);
  assert.ok(findings.some((f) => f.check === "motion.reduced"), "the drifting banner ignores reduce motion too");
});

test("a small spinner and a quick entrance that respects reduce motion pass", () => {
  const { summary, findings } = check("motion-good.html");
  assert.deepEqual(findings.filter((f) => f.check.startsWith("motion.")), []);
  assert.equal(summary.verdict, "pass");
});
