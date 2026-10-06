import { randomInt } from "node:crypto";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { chromium } from "playwright";
import { PNG } from "pngjs";
import { appRoot, lawhaHome } from "./record.js";

/**
 * Blind side by side: two versions of a page rendered at the same widths and placed left and right in
 * a random order. The judge sees only "left" and "right"; which one is the candidate is kept in a key
 * file the judge is never shown. `reveal` turns the pick back into A or B, and a person's picks are
 * kept as their taste.
 */

export interface AbKey {
  schema: "nexika.lawha.ab/1";
  a: { url: string; label: string };
  b: { url: string; label: string };
  left: "a" | "b";
  widths: number[];
  created: string;
}

async function shoot(url: string, width: number, path: string): Promise<PNG> {
  const browser = await chromium.launch();
  try {
    const page = await browser.newPage({ viewport: { width, height: width < 768 ? 844 : 900 }, reducedMotion: "reduce" });
    await page.goto(url, { waitUntil: "networkidle", timeout: 60_000 }).catch(() => undefined);
    await page.evaluate(() => (document as Document & { fonts?: FontFaceSet }).fonts?.ready);
    await page.waitForTimeout(600);
    await page.screenshot({ path, fullPage: true, animations: "disabled" });
  } finally {
    await browser.close();
  }
  return PNG.sync.read(readFileSync(path));
}

/** Two images side by side on a neutral ground, with a gutter; the taller sets the height. */
function sideBySide(left: PNG, right: PNG, maxHeight = 4000): PNG {
  const gutter = 32;
  const h = Math.min(maxHeight, Math.max(left.height, right.height));
  const out = new PNG({ width: left.width + right.width + gutter, height: h });
  for (let i = 0; i < out.data.length; i += 4) { out.data[i] = 214; out.data[i + 1] = 214; out.data[i + 2] = 210; out.data[i + 3] = 255; }
  PNG.bitblt(left, out, 0, 0, left.width, Math.min(left.height, h), 0, 0);
  PNG.bitblt(right, out, 0, 0, right.width, Math.min(right.height, h), left.width + gutter, 0);
  return out;
}

export async function ab(a: { url: string; label: string }, b: { url: string; label: string }, widths: number[], out: string): Promise<{ pairs: string[]; out: string }> {
  // The single shots name which version is which, so they live in the hidden folder with the key.
  mkdirSync(join(out, ".key"), { recursive: true });
  const left: "a" | "b" = randomInt(2) === 0 ? "a" : "b";
  const pairs: string[] = [];
  for (const w of widths) {
    const pa = await shoot(a.url, w, join(out, ".key", `a-${w}.png`));
    const pb = await shoot(b.url, w, join(out, ".key", `b-${w}.png`));
    const pair = left === "a" ? sideBySide(pa, pb) : sideBySide(pb, pa);
    const path = join(out, `pair-${w}.png`);
    writeFileSync(path, PNG.sync.write(pair));
    pairs.push(path);
  }
  const key: AbKey = { schema: "nexika.lawha.ab/1", a, b, left, widths, created: new Date().toISOString() };
  // The key sits apart from the pairs; the judge is given only the pair images.
  writeFileSync(join(out, ".key", "key.json"), JSON.stringify(key, null, 1));
  return { pairs, out };
}

export interface Taste {
  at: string;
  project: string;
  winner: string; // the label of the version chosen
  loser: string;
  note: string;
}

export function reveal(out: string, pick: "left" | "right", by: "user" | "judge", note: string, cwd: string): { winner: "a" | "b"; label: string; recorded: boolean } {
  const key = JSON.parse(readFileSync(join(out, ".key", "key.json"), "utf8")) as AbKey;
  const winner: "a" | "b" = pick === "left" ? key.left : key.left === "a" ? "b" : "a";
  let recorded = false;
  if (by === "user") {
    const path = join(lawhaHome(), "taste.json");
    let taste: Taste[] = [];
    try { taste = JSON.parse(readFileSync(path, "utf8")) as Taste[]; } catch { taste = []; }
    taste.push({ at: new Date().toISOString(), project: appRoot(cwd), winner: key[winner].label, loser: key[winner === "a" ? "b" : "a"].label, note: note.slice(0, 300) });
    mkdirSync(lawhaHome(), { recursive: true, mode: 0o700 });
    writeFileSync(path, JSON.stringify(taste.slice(-200), null, 1), { mode: 0o600 });
    recorded = true;
  }
  return { winner, label: key[winner].label, recorded };
}

export function readTaste(): Taste[] {
  try {
    return JSON.parse(readFileSync(join(lawhaHome(), "taste.json"), "utf8")) as Taste[];
  } catch {
    return [];
  }
}
