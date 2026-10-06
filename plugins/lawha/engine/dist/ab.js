import { randomInt } from "node:crypto";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { chromium } from "playwright";
import { PNG } from "pngjs";
import { appRoot, lawhaHome } from "./record.js";
async function shoot(url, width, path) {
    const browser = await chromium.launch();
    try {
        const page = await browser.newPage({ viewport: { width, height: width < 768 ? 844 : 900 }, reducedMotion: "reduce" });
        await page.goto(url, { waitUntil: "networkidle", timeout: 60_000 }).catch(() => undefined);
        await page.evaluate(() => document.fonts?.ready);
        await page.waitForTimeout(600);
        await page.screenshot({ path, fullPage: true, animations: "disabled" });
    }
    finally {
        await browser.close();
    }
    return PNG.sync.read(readFileSync(path));
}
/** Two images side by side on a neutral ground, with a gutter; the taller sets the height. */
function sideBySide(left, right, maxHeight = 4000) {
    const gutter = 32;
    const h = Math.min(maxHeight, Math.max(left.height, right.height));
    const out = new PNG({ width: left.width + right.width + gutter, height: h });
    for (let i = 0; i < out.data.length; i += 4) {
        out.data[i] = 214;
        out.data[i + 1] = 214;
        out.data[i + 2] = 210;
        out.data[i + 3] = 255;
    }
    PNG.bitblt(left, out, 0, 0, left.width, Math.min(left.height, h), 0, 0);
    PNG.bitblt(right, out, 0, 0, right.width, Math.min(right.height, h), left.width + gutter, 0);
    return out;
}
export async function ab(a, b, widths, out) {
    // The single shots name which version is which, so they live in the hidden folder with the key.
    mkdirSync(join(out, ".key"), { recursive: true });
    const left = randomInt(2) === 0 ? "a" : "b";
    const pairs = [];
    for (const w of widths) {
        const pa = await shoot(a.url, w, join(out, ".key", `a-${w}.png`));
        const pb = await shoot(b.url, w, join(out, ".key", `b-${w}.png`));
        const pair = left === "a" ? sideBySide(pa, pb) : sideBySide(pb, pa);
        const path = join(out, `pair-${w}.png`);
        writeFileSync(path, PNG.sync.write(pair));
        pairs.push(path);
    }
    const key = { schema: "nexika.lawha.ab/1", a, b, left, widths, created: new Date().toISOString() };
    // The key sits apart from the pairs; the judge is given only the pair images.
    writeFileSync(join(out, ".key", "key.json"), JSON.stringify(key, null, 1));
    return { pairs, out };
}
export function reveal(out, pick, by, note, cwd) {
    const key = JSON.parse(readFileSync(join(out, ".key", "key.json"), "utf8"));
    const winner = pick === "left" ? key.left : key.left === "a" ? "b" : "a";
    let recorded = false;
    if (by === "user") {
        const path = join(lawhaHome(), "taste.json");
        let taste = [];
        try {
            taste = JSON.parse(readFileSync(path, "utf8"));
        }
        catch {
            taste = [];
        }
        taste.push({ at: new Date().toISOString(), project: appRoot(cwd), winner: key[winner].label, loser: key[winner === "a" ? "b" : "a"].label, note: note.slice(0, 300) });
        mkdirSync(lawhaHome(), { recursive: true, mode: 0o700 });
        writeFileSync(path, JSON.stringify(taste.slice(-200), null, 1), { mode: 0o600 });
        recorded = true;
    }
    return { winner, label: key[winner].label, recorded };
}
export function readTaste() {
    try {
        return JSON.parse(readFileSync(join(lawhaHome(), "taste.json"), "utf8"));
    }
    catch {
        return [];
    }
}
