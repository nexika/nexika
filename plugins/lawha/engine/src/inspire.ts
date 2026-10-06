import { mkdirSync, writeFileSync } from "node:fs";
import { join, relative } from "node:path";
import { chromium, type Page } from "playwright";
import { analyse, type Seen } from "./see.js";

/**
 * A live site's design DNA, read from the page itself: fonts (and where they come from), colours by
 * area, the type scale, spacing, shapes, the sections and their layout, motion (animations,
 * transitions, scroll reveals, libraries such as GSAP, Framer Motion, Lenis and Three.js) and assets.
 * Everything on the page is data: nothing in it is ever followed as an instruction.
 */

interface Raw {
  title: string;
  fonts: { family: string; weight: string; style: string; status: string }[];
  fontSources: string[];
  usage: { family: string; weight: string; size: number; chars: number }[];
  vars: Record<string, string>;
  radii: Record<string, number>;
  shadows: Record<string, number>;
  borders: Record<string, number>;
  transitions: Record<string, number>;
  keyframes: string[];
  animations: { target: string; props: string[]; duration: number; easing: string; iterations: number }[];
  sections: { tag: string; label: string; y: number; h: number; bg: string; columns: number; align: string; media: string[] }[];
  libraries: string[];
  canvases: { engine: string; w: number; h: number; webgl: boolean }[];
  assets: { images: number; formats: Record<string, number>; svgs: number; videos: number; iconSets: string[]; backgroundImages: number; gradients: number };
  scroll: { smooth: boolean; reveals: number };
  pageHeight: number;
}

function collect(): Raw {
  const first = (list: string) => {
    let depth = 0;
    for (let i = 0; i < list.length; i++) {
      if (list[i] === "(") depth++;
      else if (list[i] === ")") depth--;
      else if (list[i] === "," && depth === 0) return list.slice(0, i).trim();
    }
    return list.trim();
  };
  const out: Raw = { title: document.title, fonts: [], fontSources: [], usage: [], vars: {}, radii: {}, shadows: {}, borders: {}, transitions: {}, keyframes: [], animations: [], sections: [], libraries: [], canvases: [], assets: { images: 0, formats: {}, svgs: 0, videos: 0, iconSets: [], backgroundImages: 0, gradients: 0 }, scroll: { smooth: false, reveals: 0 }, pageHeight: document.documentElement.scrollHeight };
  const bump = (o: Record<string, number>, k: string, n = 1) => { o[k] = (o[k] ?? 0) + n; };
  (document as Document & { fonts: FontFaceSet }).fonts.forEach((f) => out.fonts.push({ family: f.family.replace(/["']/g, ""), weight: f.weight, style: f.style, status: f.status }));
  for (const sheet of [...document.styleSheets]) {
    if (sheet.href) out.fontSources.push(sheet.href);
    let rules: CSSRuleList;
    try { rules = sheet.cssRules; } catch { continue; }
    const walk = (list: CSSRuleList) => {
      for (const rule of [...list]) {
        if (rule instanceof CSSFontFaceRule) {
          const src = rule.style.getPropertyValue("src");
          const url = src.match(/url\(["']?([^"')]+)/);
          if (url) out.fontSources.push(url[1]!);
        } else if (rule instanceof CSSKeyframesRule) {
          out.keyframes.push(rule.name);
        } else if (rule instanceof CSSStyleRule && (rule.selectorText === ":root" || rule.selectorText === "html")) {
          for (const prop of [...rule.style]) if (prop.startsWith("--")) out.vars[prop] = rule.style.getPropertyValue(prop).trim().slice(0, 80);
        }
        if ("cssRules" in rule && (rule as CSSGroupingRule).cssRules) walk((rule as CSSGroupingRule).cssRules);
      }
    };
    walk(rules);
  }
  const usage = new Map<string, { family: string; weight: string; size: number; chars: number }>();
  const els = [...document.body.querySelectorAll("*")].slice(0, 6000);
  for (const el of els) {
    const s = getComputedStyle(el);
    if (s.display === "none" || s.visibility === "hidden") continue;
    const own = [...el.childNodes].filter((n) => n.nodeType === 3).map((n) => n.textContent ?? "").join("").trim();
    if (own) {
      const family = s.fontFamily.split(",")[0]!.replace(/["']/g, "").trim();
      const key = `${family}|${s.fontWeight}|${parseFloat(s.fontSize)}`;
      const u = usage.get(key) ?? { family, weight: s.fontWeight, size: parseFloat(s.fontSize), chars: 0 };
      u.chars += own.length;
      usage.set(key, u);
    }
    const r = el.getBoundingClientRect();
    if (r.width > 24 && r.height > 24) {
      if (s.borderTopLeftRadius !== "0px") bump(out.radii, s.borderTopLeftRadius);
      if (s.boxShadow !== "none") bump(out.shadows, s.boxShadow.replace(/rgba?\([^)]*\)/g, (c) => c.replace(/\s/g, "")).slice(0, 90));
      if (s.borderTopWidth !== "0px" && s.borderTopStyle !== "none") bump(out.borders, `${s.borderTopWidth} ${s.borderTopStyle}`);
    }
    if (s.transitionProperty && s.transitionProperty !== "all" && s.transitionDuration !== "0s") bump(out.transitions, `${s.transitionProperty.split(",").map((x) => x.trim()).slice(0, 3).join(", ")} ${first(s.transitionDuration)} ${first(s.transitionTimingFunction)}`);
    if (s.backgroundImage.includes("url(")) out.assets.backgroundImages++;
    if (s.backgroundImage.includes("gradient(")) out.assets.gradients++;
  }
  out.usage = [...usage.values()].sort((a, b) => b.chars - a.chars).slice(0, 25);
  for (const a of document.getAnimations().slice(0, 400)) {
    const eff = a.effect as KeyframeEffect | null;
    const props = new Set<string>();
    for (const k of eff?.getKeyframes() ?? []) for (const p of Object.keys(k)) if (!["offset", "easing", "composite", "computedOffset"].includes(p)) props.add(p);
    const t = eff?.getComputedTiming();
    const target = eff?.target as Element | null;
    out.animations.push({ target: target ? `${target.tagName.toLowerCase()}${target.classList[0] ? "." + target.classList[0] : ""}` : "?", props: [...props], duration: Number(t?.duration) || 0, easing: String(eff?.getTiming().easing ?? ""), iterations: Number(t?.iterations) });
  }
  // Sections: the big blocks a visitor scrolls through.
  const main = document.querySelector("main") ?? document.body;
  let blocks = [...main.children].filter((c) => c.getBoundingClientRect().height > 160);
  if (blocks.length === 1) blocks = [...blocks[0]!.children].filter((c) => c.getBoundingClientRect().height > 160);
  for (const b of blocks.slice(0, 30)) {
    const r = b.getBoundingClientRect();
    const s = getComputedStyle(b);
    let bg = s.backgroundColor;
    for (let p: Element | null = b; p && (bg === "rgba(0, 0, 0, 0)" || bg === "transparent"); p = p.parentElement) bg = getComputedStyle(p).backgroundColor;
    const kids = [...b.querySelectorAll(":scope > * > *, :scope > *")].filter((k) => k.getBoundingClientRect().width > 80);
    const xs = new Set(kids.map((k) => Math.round(k.getBoundingClientRect().left / 8)));
    const heading = b.querySelector("h1, h2, h3");
    const media = [...new Set([...b.querySelectorAll("img, video, canvas, svg, picture")].map((m) => m.tagName.toLowerCase()))];
    out.sections.push({ tag: b.tagName.toLowerCase(), label: ((heading as HTMLElement | null)?.innerText ?? b.getAttribute("aria-label") ?? "").replace(/\s+/g, " ").trim().slice(0, 70), y: Math.round(r.top + scrollY), h: Math.round(r.height), bg, columns: Math.min(xs.size, 12), align: getComputedStyle(heading ?? b).textAlign, media });
  }
  const w = window as unknown as Record<string, unknown>;
  const scripts = [...document.scripts].map((s) => s.src).join(" ");
  const libs: [string, boolean][] = [
    ["GSAP", !!w.gsap || /gsap/i.test(scripts)], ["GSAP ScrollTrigger", !!w.ScrollTrigger || /scrolltrigger/i.test(scripts)],
    ["Lenis smooth scroll", !!w.lenis || !!w.Lenis || document.documentElement.classList.contains("lenis") || /lenis/i.test(scripts)],
    ["Locomotive Scroll", document.documentElement.classList.contains("has-scroll-smooth") || /locomotive/i.test(scripts)],
    ["Framer Motion / Motion", !!document.querySelector("[style*='will-change'][data-projection-id], [data-framer-component-type], [data-framer-name]") || /framer|motion/i.test(scripts)],
    ["Three.js", !!w.THREE || [...document.querySelectorAll("canvas")].some((c) => /three/i.test(c.getAttribute("data-engine") ?? "")) || /three/i.test(scripts)],
    ["Spline", !!document.querySelector("spline-viewer, canvas[data-spline]") || /spline/i.test(scripts)],
    ["Lottie", !!document.querySelector("lottie-player, dotlottie-player") || /lottie/i.test(scripts)],
    ["Rive", /rive/i.test(scripts) || !!document.querySelector("canvas[data-rive]")],
    ["Webflow interactions", !!document.querySelector("html[data-wf-page]")],
    ["Next.js", !!document.querySelector("#__next, script#__NEXT_DATA__") || /_next\//.test(scripts)],
  ];
  out.libraries = libs.filter(([, yes]) => yes).map(([n]) => n);
  for (const c of [...document.querySelectorAll("canvas")].slice(0, 10)) {
    const r = c.getBoundingClientRect();
    out.canvases.push({ engine: c.getAttribute("data-engine") ?? "", w: Math.round(r.width), h: Math.round(r.height), webgl: !!c.getAttribute("data-engine") || r.width * r.height > 100_000 });
  }
  const imgs = [...document.images];
  out.assets.images = imgs.length;
  for (const i of imgs) {
    const src = (i.currentSrc || i.src).split("?")[0]!;
    const ext = (src.match(/\.(avif|webp|png|jpe?g|gif|svg)$/i)?.[1] ?? (src.startsWith("data:") ? "data" : "other")).toLowerCase();
    bump(out.assets.formats, ext);
  }
  out.assets.svgs = document.querySelectorAll("svg").length;
  out.assets.videos = document.querySelectorAll("video").length;
  const cls = [...document.querySelectorAll("svg[class], i[class]")].map((e) => e.getAttribute("class") ?? "").join(" ");
  out.assets.iconSets = [["Lucide", /lucide/], ["Heroicons", /heroicon/], ["Font Awesome", /\bfa-/], ["Phosphor", /\bph-/], ["Material Symbols", /material-symbols|material-icons/], ["Tabler", /tabler/]]
    .filter(([, re]) => (re as RegExp).test(cls)).map(([n]) => n as string);
  out.scroll.smooth = getComputedStyle(document.documentElement).scrollBehavior === "smooth" || out.libraries.some((l) => /Lenis|Locomotive/.test(l));
  return out;
}

/** Elements whose opacity or transform changes as the page scrolls: scroll-triggered reveals. */
async function scrollReveals(page: Page): Promise<number> {
  const snapshot = () => page.evaluate(() => [...document.body.querySelectorAll("*")].slice(0, 4000).map((el) => {
    const s = getComputedStyle(el);
    return `${s.opacity}|${s.transform}`;
  }));
  const before = await snapshot();
  const h = await page.evaluate(() => document.documentElement.scrollHeight);
  for (let y = 0; y < Math.min(h, 12000); y += 700) {
    await page.evaluate((top) => window.scrollTo(0, top), y);
    await page.waitForTimeout(140);
  }
  await page.waitForTimeout(600);
  const after = await snapshot();
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.waitForTimeout(300);
  let changed = 0;
  for (let i = 0; i < Math.min(before.length, after.length); i++) if (before[i] !== after[i]) changed++;
  return changed;
}

export interface Dna {
  url: string;
  title: string;
  when: string;
  fonts: { family: string; weights: string[]; share: number; source: string; free: boolean | null; alike?: string }[];
  seen: Seen;
  colorVars: Record<string, string>;
  shape: { radii: [string, number][]; shadows: [string, number][]; borders: [string, number][] };
  motion: { libraries: string[]; transitions: [string, number][]; keyframes: string[]; animations: Raw["animations"]; scrollReveals: number; smoothScroll: boolean; canvases: Raw["canvases"] };
  sections: Raw["sections"];
  assets: Raw["assets"];
  shots: Record<string, string>;
  frames: string[];
}

const GOOGLE = /fonts\.(googleapis|gstatic)\.com/;

/** Free fonts (OFL / Apache) seen on many sites, and well-known paid ones with free look-alikes. */
const FREE = ["inter", "inter tight", "geist", "geist mono", "manrope", "dm sans", "dm serif display", "poppins", "montserrat", "roboto", "roboto mono", "open sans", "lato", "source sans 3", "source serif 4", "source code pro", "sourcecodepro", "ibm plex sans", "ibm plex mono", "ibm plex serif", "jetbrains mono", "space grotesk", "space mono", "fraunces", "playfair display", "bodoni moda", "martian mono", "barlow", "barlow condensed", "big shoulders display", "bricolage grotesque", "outfit", "plus jakarta sans", "work sans", "nunito", "nunito sans", "rubik", "sora", "syne", "unbounded", "instrument serif", "instrument sans", "newsreader", "libre baskerville", "cormorant", "eb garamond", "crimson pro", "archivo", "hanken grotesk", "figtree", "onest", "mona sans", "hubot sans", "satoshi", "general sans", "cabinet grotesk", "clash display", "switzer", "noto sans", "noto serif", "big shoulders", "big shoulders display", "ibm plex sans arabic", "tajawal", "cairo", "almarai", "readex pro", "noto kufi arabic"];
const PAID: Record<string, string> = {
  "söhne": "Inter Tight, Geist or Hanken Grotesk", sohne: "Inter Tight, Geist or Hanken Grotesk", "berkeley mono": "JetBrains Mono or Geist Mono",
  graphik: "Inter or Figtree", "gt america": "Inter Tight or Archivo", "gt walsheim": "Outfit or Plus Jakarta Sans", circular: "Figtree or DM Sans",
  "neue haas grotesk": "Inter Tight", "neue haas unica": "Inter Tight", "helvetica now": "Inter Tight", "neue montreal": "Inter Tight or Hanken Grotesk",
  "suisse int'l": "Inter Tight", "suisse intl": "Inter Tight", "aeonik": "Manrope or Onest", "basis grotesque": "Work Sans", "founders grotesk": "Archivo",
  "gt sectra": "Fraunces or Newsreader", "tiempos": "Newsreader or Source Serif 4", "canela": "Instrument Serif or Fraunces", "sf pro": "Inter (SF Pro is only licensed for Apple platforms)",
  "san francisco": "Inter", "pp neue montreal": "Inter Tight", "pp editorial new": "Instrument Serif", "messina sans": "Figtree", "apercu": "DM Sans",
};

/** "Inter Variable", "sohne-var", "SourceCodePro" -> a comparable family name. */
export function normalFamily(family: string): string {
  return family.toLowerCase().replace(/[-_](var|variable|vf)$|\s+(variable|var|vf|display)$/g, "").replace(/[-_]/g, " ").trim();
}

export function licence(family: string): { free: boolean | null; alike?: string } {
  const f = normalFamily(family);
  if (FREE.includes(f) || FREE.includes(f.replace(/\s+/g, ""))) return { free: true };
  for (const [paid, alike] of Object.entries(PAID)) if (f === paid || f.startsWith(paid)) return { free: false, alike };
  return { free: null };
}

function fontSource(family: string, sources: string[]): { source: string; free: boolean | null; alike?: string } {
  const known = licence(family);
  const where = fontHost(family, sources);
  return { source: where.source, free: known.free ?? where.free, alike: known.alike };
}

function fontHost(family: string, sources: string[]): { source: string; free: boolean | null } {
  const slug = family.toLowerCase().replace(/\s+/g, "");
  const hit = sources.find((s) => s.toLowerCase().replace(/[-_\s]/g, "").includes(slug));
  if (hit && GOOGLE.test(hit)) return { source: "Google Fonts", free: true };
  if (sources.some((s) => GOOGLE.test(s) && s.toLowerCase().includes(family.toLowerCase().replace(/\s+/g, "+")))) return { source: "Google Fonts", free: true };
  if (/typekit|use\.typekit/.test(hit ?? "")) return { source: "Adobe Fonts (licensed)", free: false };
  if (hit) return { source: `self-hosted (${hit.split("/").pop()?.slice(0, 40)})`, free: null };
  if (/^(system-ui|-apple-system|blinkmacsystemfont|segoe ui|helvetica|arial|sans-serif|serif|ui-)/i.test(family)) return { source: "system font", free: true };
  return { source: "unknown", free: null };
}

export async function inspire(url: string, out: string): Promise<{ dna: Dna; json: string; md: string }> {
  mkdirSync(join(out, "frames"), { recursive: true });
  const browser = await chromium.launch();
  try {
    const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1, locale: "en-US", extraHTTPHeaders: { "Accept-Language": "en-US,en;q=0.9" } });
    const page = await context.newPage();
    // Entrance motion: frames from the first moments after load.
    await page.goto(url, { waitUntil: "domcontentloaded", timeout: 60_000 });
    const frames: string[] = [];
    for (let i = 0; i < 6; i++) {
      const f = join(out, "frames", `load-${i}.png`);
      await page.screenshot({ path: f });
      frames.push(relative(out, f));
      await page.waitForTimeout(250);
    }
    await page.waitForLoadState("networkidle", { timeout: 20_000 }).catch(() => undefined);
    await page.evaluate(() => (document as Document & { fonts?: FontFaceSet }).fonts?.ready);
    await page.waitForTimeout(800);
    const reveals = await scrollReveals(page);
    const raw = await page.evaluate(collect);
    const shots: Record<string, string> = {};
    const desktop = join(out, "desktop.png");
    await page.screenshot({ path: desktop, fullPage: true, clip: undefined }).catch(async () => page.screenshot({ path: desktop }));
    shots.desktop = relative(out, desktop);
    const fold = join(out, "desktop-fold.png");
    await page.screenshot({ path: fold });
    shots.fold = relative(out, fold);
    await page.setViewportSize({ width: 390, height: 844 });
    await page.waitForTimeout(800);
    const phone = join(out, "phone-fold.png");
    await page.screenshot({ path: phone });
    shots.phone = relative(out, phone);
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.waitForTimeout(500);
    const { see: seeOnPage } = await import("./see.js");
    const seen = await seeOnPage(page, { width: 1440, theme: "light", dir: "ltr", motion: "full" }, "1440");
    const total = raw.usage.reduce((a, u) => a + u.chars, 0) || 1;
    const byFamily = new Map<string, { weights: Set<string>; chars: number }>();
    for (const u of raw.usage) {
      const f = byFamily.get(u.family) ?? { weights: new Set<string>(), chars: 0 };
      f.weights.add(u.weight);
      f.chars += u.chars;
      byFamily.set(u.family, f);
    }
    const sorted = (o: Record<string, number>) => Object.entries(o).sort((a, b) => b[1] - a[1]).slice(0, 8) as [string, number][];
    const colorVars = Object.fromEntries(Object.entries(raw.vars).filter(([, v]) => /^(#|rgb|hsl|oklch|lab|color\()/i.test(v)).slice(0, 40));
    const dna: Dna = {
      url, title: raw.title, when: new Date().toISOString(),
      fonts: [...byFamily.entries()].sort((a, b) => b[1].chars - a[1].chars).slice(0, 6).map(([family, f]) => ({ family, weights: [...f.weights].sort(), share: Math.round((f.chars / total) * 100) / 100, ...fontSource(family, raw.fontSources) })),
      seen,
      colorVars,
      shape: { radii: sorted(raw.radii), shadows: sorted(raw.shadows), borders: sorted(raw.borders) },
      motion: { libraries: raw.libraries, transitions: sorted(raw.transitions), keyframes: [...new Set(raw.keyframes.map((k) => k.replace(/__[A-Za-z0-9_-]{4,}$/, "").replace(/[-_]\d+([-_]\d+)*/g, "-N")))].slice(0, 20), animations: raw.animations, scrollReveals: reveals, smoothScroll: raw.scroll.smooth, canvases: raw.canvases },
      sections: raw.sections, assets: raw.assets, shots, frames,
    };
    const json = join(out, "dna.json");
    writeFileSync(json, JSON.stringify(dna, null, 1));
    const md = join(out, "dna.md");
    writeFileSync(md, dnaMarkdown(dna));
    await context.close();
    return { dna, json, md };
  } finally {
    await browser.close();
  }
}

/** Many identical animations (a grid of 20 pulsing dots) are one pattern: group them. */
function groupAnimations(list: Raw["animations"]): string {
  if (!list.length) return "none";
  const groups = new Map<string, { n: number; target: string }>();
  for (const a of list) {
    const key = `${a.props.join("/") || "custom"} ${Math.round(a.duration)}ms ${a.easing}${a.iterations === Infinity ? " loop" : ""}`;
    const g = groups.get(key) ?? { n: 0, target: a.target.replace(/[-_]\d+([-_]\d+)*/g, "-N") };
    g.n++;
    groups.set(key, g);
  }
  return [...groups.entries()].sort((a, b) => b[1].n - a[1].n).slice(0, 10).map(([k, g]) => `${g.target} ${k}${g.n > 1 ? ` ×${g.n}` : ""}`).join("; ");
}

export function dnaMarkdown(d: Dna): string {
  const s = d.seen;
  const lines = [
    `# Design DNA: ${d.title || d.url}`,
    "",
    `${d.url} · read ${d.when.slice(0, 10)} · screenshots: ${Object.values(d.shots).join(", ")} · first moments after load: ${d.frames.length} frames`,
    "",
    "## Type",
    ...d.fonts.map((f) => `- **${f.family}** ${Math.round(f.share * 100)}% of the text · weights ${f.weights.join(", ")} · ${f.source} · ${f.free === true ? "free to use (open licence)" : f.free === false ? `paid licence: use a free look-alike such as ${f.alike}` : "licence unknown: check before reusing"}`),
    `- Sizes (largest first): ${s.typography.sizes.slice(0, 10).map((t) => `${t.px}px`).join(", ")} · scale ratio ${s.typography.ratio ?? "–"}`,
    "",
    "## Colour",
    `- On screen, by area: ${s.colour.palette.slice(0, 8).map((p) => `${p.hex} ${Math.round(p.share * 100)}%`).join(", ")}`,
    `- Harmony: ${s.colour.harmony}`,
    Object.keys(d.colorVars).length ? `- CSS variables: ${Object.entries(d.colorVars).slice(0, 14).map(([k, v]) => `${k}: ${v}`).join("; ")}` : "- No colour variables on :root",
    "",
    "## Space and shape",
    `- Common gaps: ${s.rhythm.gaps.slice(0, 8).map((g) => `${g.value}px×${g.count}`).join(", ") || "–"} · spacing base ${s.rhythm.base ?? "not declared"}`,
    `- Columns at: ${s.alignment.columns.filter((c) => c >= 0 && c < 1440).slice(0, 8).map((c) => `${c}px`).join(", ") || "–"}`,
    `- Corner radii: ${d.shape.radii.map(([r, n]) => `${r}×${n}`).join(", ") || "none"}`,
    `- Shadows: ${d.shape.shadows.slice(0, 4).map(([v, n]) => `\`${v}\` ×${n}`).join("; ") || "none"}`,
    `- Borders: ${d.shape.borders.map(([b, n]) => `${b}×${n}`).join(", ") || "none"}`,
    "",
    "## Sections (top to bottom)",
    ...d.sections.map((x) => `- ${x.label ? `"${x.label}"` : `<${x.tag}>`} · ${x.h}px tall · ${x.columns} column${x.columns === 1 ? "" : "s"} · text ${x.align} · background ${x.bg}${x.media.length ? ` · ${x.media.join(", ")}` : ""}`),
    "",
    "## Motion",
    `- Libraries: ${d.motion.libraries.join(", ") || "none detected (CSS only)"}`,
    `- Smooth scrolling: ${d.motion.smoothScroll ? "yes" : "no"} · elements that change as you scroll (reveals, parallax): ${d.motion.scrollReveals}`,
    `- 3D / canvas: ${d.motion.canvases.length ? d.motion.canvases.map((c) => `${c.w}×${c.h}${c.engine ? ` (${c.engine})` : ""}`).join(", ") : "none"}`,
    `- Transitions (property, duration, easing): ${d.motion.transitions.slice(0, 6).map(([t, n]) => `\`${t}\` ×${n}`).join("; ") || "none"}`,
    `- Running animations at load: ${groupAnimations(d.motion.animations)}`,
    `- Keyframes: ${d.motion.keyframes.slice(0, 12).join(", ") || "none"}`,
    "",
    "## Assets",
    `- Images: ${d.assets.images} (${Object.entries(d.assets.formats).map(([f, n]) => `${f} ${n}`).join(", ") || "–"}) · inline SVG ${d.assets.svgs} · video ${d.assets.videos} · CSS background images ${d.assets.backgroundImages} · gradients ${d.assets.gradients}`,
    `- Icon sets: ${d.assets.iconSets.join(", ") || "none recognised (custom SVG)"}`,
    "",
    "Use the patterns, rhythm and motion as inspiration. Do not copy logos, photos, illustrations, copy or licensed fonts.",
  ];
  return lines.join("\n") + "\n";
}

