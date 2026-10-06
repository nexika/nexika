import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { join, relative, resolve } from "node:path";
import { chromium } from "playwright";
import { type Brief, check, contrastRatio, type Direction, type HistoryEntry, historyEntry, previewHtml, type Problem, themeCss } from "./direction.js";
import { appRoot, lawhaHome } from "./record.js";

export function historyPath(): string {
  return join(lawhaHome(), "history.json");
}

export function readHistory(): HistoryEntry[] {
  try {
    const h = JSON.parse(readFileSync(historyPath(), "utf8")) as HistoryEntry[];
    return Array.isArray(h) ? h : [];
  } catch {
    return [];
  }
}

function load(path: string): Direction[] {
  const data = JSON.parse(readFileSync(path, "utf8")) as Direction[] | { directions: Direction[] };
  const list = Array.isArray(data) ? data : data.directions;
  if (!Array.isArray(list) || !list.length) throw new Error("no directions in the file (expected a list, or {directions: [...]})");
  return list;
}

const esc = (s: string) => s.replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]!);

export interface PreviewResult {
  gallery: string;
  problems: Problem[];
  previews: { id: string; name: string; files: Record<string, string> }[];
}

/** Render every direction as a real page (phone and desktop, light and dark), check them, and build the gallery. */
export async function preview(directionsPath: string, brief: Brief, out: string): Promise<PreviewResult> {
  const directions = load(directionsPath);
  const problems = check(directions, readHistory());
  mkdirSync(out, { recursive: true });
  const shots: PreviewResult["previews"] = [];
  const browser = await chromium.launch();
  try {
    for (const d of directions) {
      const files: Record<string, string> = {};
      for (const theme of ["light", "dark"] as const) {
        const html = join(out, `${d.id}-${theme}.html`);
        writeFileSync(html, previewHtml(d, brief, theme));
        files[`${theme}.html`] = relative(out, html);
        for (const [label, width] of [["phone", 390], ["desktop", 1280]] as const) {
          if (theme === "dark" && label === "phone") continue;
          const page = await browser.newPage({ viewport: { width, height: 900 }, reducedMotion: "reduce" });
          await page.goto(`file://${resolve(html)}`, { waitUntil: "networkidle", timeout: 30_000 }).catch(() => undefined);
          await page.evaluate(() => (document as Document & { fonts?: FontFaceSet }).fonts?.ready);
          const png = join(out, `${d.id}-${theme}-${label}.png`);
          await page.screenshot({ path: png, fullPage: label === "phone" });
          files[`${theme}-${label}`] = relative(out, png);
          await page.close();
        }
      }
      shots.push({ id: d.id, name: d.name, files });
    }
  } finally {
    await browser.close();
  }
  const gallery = join(out, "gallery.html");
  writeFileSync(gallery, galleryHtml(directions, shots, problems, brief));
  return { gallery, problems, previews: shots };
}

function galleryHtml(directions: Direction[], shots: PreviewResult["previews"], problems: Problem[], brief: Brief): string {
  const cards = directions.map((d) => {
    const s = shots.find((x) => x.id === d.id)!;
    const mine = problems.filter((p) => p.direction.split("+").includes(d.id));
    const swatch = (name: string, hex: string, on: string) => `<span class="sw"><i style="background:${esc(hex)}"></i><span><b>${esc(name)}</b> <code>${esc(hex)}</code>${on ? ` <small>${on}</small>` : ""}</span></span>`;
    const l = d.palette.light;
    return `<section class="dir" aria-labelledby="d-${esc(d.id)}">
<header><span class="letter">${esc(d.id.toUpperCase())}</span><div><h2 id="d-${esc(d.id)}">${esc(d.name)}</h2><p>${esc(d.mood)}</p></div></header>
<div class="shots" tabindex="0" role="region" aria-label="${esc(d.name)} previews">
<figure class="phone"><figcaption>Phone</figcaption><img src="${esc(s.files["light-phone"]!)}" alt="${esc(d.name)} on a phone"></figure>
<figure><figcaption>Desktop</figcaption><img src="${esc(s.files["light-desktop"]!)}" alt="${esc(d.name)} on a desktop"></figure>
<figure><figcaption>Desktop, dark</figcaption><img src="${esc(s.files["dark-desktop"]!)}" alt="${esc(d.name)} on a desktop, dark theme"></figure>
</div>
<dl>
<dt>Type</dt><dd><b>${esc(d.fonts.display.family)}</b> for headings, <b>${esc(d.fonts.text.family)}</b> for text${d.fonts.arabic ? `, <b>${esc(d.fonts.arabic.family)}</b> for Arabic` : ""} · scale ${d.scale.ratio} from ${d.scale.base}px</dd>
<dt>Colour</dt><dd class="swatches">${swatch("background", l.background, "")}${swatch("text", l.text, `${contrastRatio(l.text, l.background)}:1`)}${swatch("primary", l.primary, `button text ${contrastRatio(l.primaryText, l.primary)}:1`)}${swatch("accent", l.accent, "")}</dd>
<dt>Shape and motion</dt><dd>${d.radius}px corners · ${d.spacing}px spacing grid · ${esc(d.layout)} layout · ${esc(d.motion)} motion</dd>
<dt>Signature</dt><dd>${esc(d.signature)} <small>(drawn as: ${esc(d.motif)})</small></dd>
<dt>Checks</dt><dd>${mine.length ? `<ul>${mine.map((p) => `<li class="${p.severity}">${esc(p.message)}</li>`).join("")}</ul>` : "<span class=\"ok\">Contrast passes in light and dark; not a known AI look; distinct.</span>"}</dd>
</dl>
<p class="open">Open the full pages: <a href="${esc(s.files["light.html"]!)}">light</a> · <a href="${esc(s.files["dark.html"]!)}">dark</a></p>
</section>`;
  }).join("");
  return `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>lawha · choose a direction</title>
<style>
:root{--bg:#f4f4f2;--panel:#fff;--ink:#141518;--muted:#596070;--line:#e2e2de;--fail:#b3261e;--warn:#8a5a00;--ok:#1f7a45}
@media (prefers-color-scheme:dark){:root{--bg:#111214;--panel:#1a1b1f;--ink:#eceef2;--muted:#a0a6b2;--line:#2b2d33;--fail:#ff7a70;--warn:#f0a63a;--ok:#4cc38a}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.55 ui-sans-serif,system-ui,sans-serif}
main{max-width:1240px;margin:0 auto;padding:40px 20px 64px}h1{font-size:clamp(24px,4vw,34px);margin:0 0 6px}main>p{color:var(--muted);margin:0 0 28px}
.dir{background:var(--panel);border:1px solid var(--line);border-radius:16px;padding:20px;margin-bottom:28px}
.dir header{display:flex;gap:16px;align-items:flex-start;margin-bottom:16px}.letter{flex:none;display:grid;place-items:center;width:44px;height:44px;border-radius:12px;background:var(--ink);color:var(--panel);font-weight:700;font-size:20px}
.dir h2{margin:0;font-size:22px}.dir header p{margin:2px 0 0;color:var(--muted)}
.shots{display:flex;gap:14px;overflow-x:auto;padding-bottom:8px}.shots:focus-visible{outline:2px solid var(--ink);outline-offset:4px}
figure{margin:0;flex:none;width:min(560px,80vw)}figure.phone{width:200px}figcaption{font-size:13px;color:var(--muted);margin-bottom:6px}
figure img{display:block;width:100%;height:auto;max-height:640px;object-fit:cover;object-position:top;border:1px solid var(--line);border-radius:10px}
dl{display:grid;grid-template-columns:max-content 1fr;gap:8px 16px;margin:16px 0 0}dt{color:var(--muted)}dd{margin:0}
.swatches{display:flex;flex-wrap:wrap;gap:10px}.sw{display:flex;gap:8px;align-items:center;font-size:14px}.sw i{width:22px;height:22px;border-radius:6px;border:1px solid var(--line)}
code{font:13px ui-monospace,monospace}small{color:var(--muted)}ul{margin:0;padding-inline-start:18px}.fail{color:var(--fail)}.warn{color:var(--warn)}.ok{color:var(--ok)}
.open{margin:14px 0 0;color:var(--muted)}a{color:inherit}
@media (max-width:640px){dl{grid-template-columns:1fr}}
</style></head><body><main>
<h1>Three directions for ${esc(brief.product)}</h1>
<p>For ${esc(brief.audience)} · feeling: ${esc(brief.feeling)}. Look at each one and tell Claude which you choose (A, B or C), or what you like from each.</p>
${cards}</main></body></html>`;
}

/** Make the chosen direction the project's design: tokens file, .lawha/design.json, and the style history. */
export function choose(directionsPath: string, id: string, cwd: string, themeOut: string): { theme: string; design: string; history: number } {
  const d = load(directionsPath).find((x) => x.id === id);
  if (!d) throw new Error(`no direction "${id}" in ${directionsPath}`);
  const root = appRoot(cwd);
  const theme = resolve(cwd, themeOut);
  mkdirSync(resolve(theme, ".."), { recursive: true });
  writeFileSync(theme, themeCss(d));
  const design = join(root, ".lawha", "design.json");
  mkdirSync(join(root, ".lawha"), { recursive: true });
  writeFileSync(design, JSON.stringify({ schema: "nexika.lawha.design/1", chosen: new Date().toISOString(), direction: d }, null, 1));
  const history = readHistory();
  history.push(historyEntry(d, root));
  mkdirSync(lawhaHome(), { recursive: true, mode: 0o700 });
  writeFileSync(historyPath(), JSON.stringify(history.slice(-50), null, 1), { mode: 0o600 });
  return { theme, design, history: history.length };
}

