// node --test benchmarks/score/read-run.test.mjs  (tests/test_lawha_bench_score.py runs it under pytest)
import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, mkdirSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { readRun } from "./read-run.mjs";

function runFile(text) {
  const base = mkdtempSync(join(tmpdir(), "lawha-score-"));
  const out = join(base, "runs", "brief", "lawha", ".lawha", "score");
  mkdirSync(out, { recursive: true });
  if (text !== undefined) writeFileSync(join(out, "run.json"), text);
  return { base, file: join(out, "run.json") };
}

test("a whole run.json is read", () => {
  const { base, file } = runFile(JSON.stringify({ findings: [{ check: "layout.x", severity: "fail" }], diffs: [] }));
  const got = readRun(file, base);
  assert.equal(got.problem, undefined);
  assert.equal(got.run.findings.length, 1);
});

for (const [why, text] of [
  ["half-written", '{"findings": [{"check": "lay'],
  ["empty", ""],
  ["not an object", "null"],
  ["no findings list", '{"findings": 3}'],
  ["missing", undefined],
]) {
  test(`run.json ${why}: named, not thrown`, () => {
    const { base, file } = runFile(text);
    const got = readRun(file, base);
    assert.equal(got.run, undefined);
    assert.match(got.problem, /^could not read runs\/brief\/lawha\/\.lawha\/score\/run\.json/);
  });
}
