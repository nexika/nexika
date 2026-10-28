// Read one tool's lawha run.json for score.mjs, kept apart so it can be tested without a build (#416).
import { readFileSync } from "node:fs";
import { relative } from "node:path";

/**
 * Returns { run } for a whole run.json, or { problem: "could not read <path>: <why>" } for one that
 * is missing, cut short or of the wrong shape, so the scorer skips that run and scores the others.
 * The path in the message is relative to `base` (the benchmarks folder).
 */
export function readRun(file, base) {
  const name = relative(base, file);
  try {
    const run = JSON.parse(readFileSync(file, "utf8"));
    if (!run || typeof run !== "object" || !Array.isArray(run.findings)) {
      return { problem: `could not read ${name}: no findings list` };
    }
    if (run.diffs !== undefined && !Array.isArray(run.diffs)) return { problem: `could not read ${name}: diffs is not a list` };
    return { run };
  } catch (e) {
    return { problem: `could not read ${name}: ${e.code ?? e.message}` };
  }
}
