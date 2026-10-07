import { AxeBuilder } from "@axe-core/playwright";
import type { Page } from "playwright";
import { PNG } from "pngjs";
import type { Variant } from "./browser.js";
import { PHONE_MAX, type Box, type Finding, round } from "./util.js";

/** What the page reports about itself; collected inside the browser. */
interface PageFacts {
  viewport: number;
  scrollWidth: number;
  overflowing: { selector: string; box: Box }[];
  clipped: { selector: string; box: Box; text: string }[];
  overlaps: { a: string; b: string; box: Box }[];
  targets: { selector: string; box: Box; label: string; inline: boolean }[];
  bodyFont: number;
  tinyText: { selector: string; size: number }[];
  physicalCss: string[];
  physicalClasses: { selector: string; classes: string[] }[];
  cls: number;
  shifted: string[];
  animations: { selector: string; props: string[]; duration: number; running: boolean; iterations: number; area: number }[];
  /** Every animation started since the page began loading (recorded by the init script). */
  started: { selector: string; props: string[]; duration: number; iterations: number; delay: number; area: number }[];
}

function collect(): PageFacts {
  const vw = document.documentElement.clientWidth;
  const sel = (el: Element): string => {
    if (el.id) return `#${CSS.escape(el.id)}`;
    const parts: string[] = [];
    let node: Element | null = el;
    while (node && node !== document.body && parts.length < 4) {
      const parent: Element | null = node.parentElement;
      let part = node.tagName.toLowerCase();
      const cls = [...node.classList].slice(0, 2).map((c) => `.${CSS.escape(c)}`).join("");
      part += cls;
      if (parent) {
        const same = [...parent.children].filter((c) => c.tagName === node!.tagName);
        if (same.length > 1) part += `:nth-of-type(${same.indexOf(node) + 1})`;
      }
      parts.unshift(part);
      node = parent;
    }
    return parts.join(" > ");
  };
  const boxOf = (r: DOMRect) => ({ x: Math.round(r.x + scrollX), y: Math.round(r.y + scrollY), w: Math.round(r.width), h: Math.round(r.height) });
  const visible = (el: Element) => {
    const s = getComputedStyle(el);
    const r = el.getBoundingClientRect();
    return s.visibility !== "hidden" && s.display !== "none" && Number(s.opacity) > 0 && r.width > 0 && r.height > 0;
  };
  // Hidden for the eye but kept for screen readers (Tailwind's sr-only, a skip link before it gets
  // focus): not cut-off text and not a tiny tap target, it is meant to be invisible.
  const screenReaderOnly = (el: Element) => {
    for (let e: Element | null = el; e && e !== document.body; e = e.parentElement) {
      const s = getComputedStyle(e);
      const r = e.getBoundingClientRect();
      const clipRect = s.clip.startsWith("rect(") && /rect\(0(px)?,? 0(px)?,? 0(px)?,? 0(px)?\)/.test(s.clip.replace(/\s+/g, " "));
      const clipPath = /inset\(50%\)/.test(s.clipPath);
      if ((s.position === "absolute" || s.position === "fixed") && r.width <= 1 && r.height <= 1 && (clipRect || clipPath || s.overflow === "hidden")) return true;
    }
    return false;
  };
  const all = [...document.body.querySelectorAll("*")].filter((el) => !["SCRIPT", "STYLE", "NOSCRIPT", "TEMPLATE"].includes(el.tagName));

  // Horizontal overflow: elements reaching past the viewport while the page scrolls sideways.
  const overflowing: PageFacts["overflowing"] = [];
  if (document.documentElement.scrollWidth > vw + 1) {
    for (const el of all) {
      if (!visible(el)) continue;
      const r = el.getBoundingClientRect();
      if (r.right > vw + 1 || r.left < -1) {
        const inside = el.parentElement && (el.parentElement.getBoundingClientRect().right > vw + 1 || el.parentElement.getBoundingClientRect().left < -1);
        if (!inside) overflowing.push({ selector: sel(el), box: boxOf(r) });
      }
      if (overflowing.length >= 10) break;
    }
  }

  // Text cut off by overflow hidden/clip.
  const clipped: PageFacts["clipped"] = [];
  const textEls = all.filter((el) => visible(el) && !screenReaderOnly(el) && [...el.childNodes].some((n) => n.nodeType === 3 && n.textContent!.trim()));
  for (const el of textEls) {
    const s = getComputedStyle(el);
    const hides = [s.overflowX, s.overflowY].some((o) => o === "hidden" || o === "clip");
    const h = el as HTMLElement;
    if (hides && (h.scrollWidth > h.clientWidth + 1 || h.scrollHeight > h.clientHeight + 1) && s.textOverflow !== "ellipsis" && !(Number(s.webkitLineClamp) > 0)) {
      clipped.push({ selector: sel(el), box: boxOf(el.getBoundingClientRect()), text: (el.textContent || "").trim().slice(0, 60) });
    }
    if (clipped.length >= 10) break;
  }

  // Text boxes that overlap each other (measured on the text itself, not the element).
  const textBoxes: { el: Element; r: DOMRect }[] = [];
  for (const el of textEls.slice(0, 400)) {
    const range = document.createRange();
    range.selectNodeContents(el);
    for (const r of range.getClientRects()) if (r.width > 2 && r.height > 2) textBoxes.push({ el, r });
  }
  const overlaps: PageFacts["overlaps"] = [];
  for (let i = 0; i < textBoxes.length && overlaps.length < 10; i++) {
    for (let j = i + 1; j < textBoxes.length; j++) {
      const a = textBoxes[i]!, b = textBoxes[j]!;
      if (a.el === b.el || a.el.contains(b.el) || b.el.contains(a.el)) continue;
      const x = Math.min(a.r.right, b.r.right) - Math.max(a.r.left, b.r.left);
      const y = Math.min(a.r.bottom, b.r.bottom) - Math.max(a.r.top, b.r.top);
      if (x > 2 && y > 0.35 * Math.min(a.r.height, b.r.height)) {
        overlaps.push({ a: sel(a.el), b: sel(b.el), box: boxOf(a.r) });
        break;
      }
    }
  }

  // Tap targets.
  const interactive = all.filter((el) => visible(el) && !screenReaderOnly(el) && el.matches("a[href], button, input:not([type=hidden]), select, textarea, summary, [role=button], [role=link], [role=checkbox], [role=switch], [role=tab], [onclick], [tabindex]:not([tabindex='-1'])"));
  const targets = interactive.map((el) => ({
    selector: sel(el),
    box: boxOf(el.getBoundingClientRect()),
    label: ((el as HTMLElement).innerText || el.getAttribute("aria-label") || el.getAttribute("title") || "").trim().slice(0, 40),
    // WCAG 2.5.8 exempts a link inside a sentence: its size is set by the line of text around it.
    inline: el.tagName === "A" && getComputedStyle(el).display === "inline" &&
      (el.parentElement?.textContent ?? "").trim().length > (el.textContent ?? "").trim().length + 10,
  }));

  // Small text.
  const tinyText = textEls
    .map((el) => ({ selector: sel(el), size: parseFloat(getComputedStyle(el).fontSize) }))
    .filter((t) => t.size < 12)
    .slice(0, 10);

  // Physical (non-mirroring) CSS: stylesheet declarations and Tailwind-style utility classes.
  // A left/right declaration only breaks RTL when its mirror differs (padding: 16px is symmetric).
  const mirror = (prop: string) => prop.replace(/left|right/, (m) => (m === "left" ? "right" : "left"));
  const physical = /^(margin|padding|border)-(left|right)|^(left|right)$|^border-(top|bottom)-(left|right)-radius$/;
  const physicalCss = new Set<string>();
  const judge = (where: string, style: CSSStyleDeclaration) => {
    for (const prop of [...style]) {
      const value = style.getPropertyValue(prop).trim();
      const other = style.getPropertyValue(mirror(prop)).trim();
      if (physical.test(prop) && value && value !== other && !(["0", "0px", "auto", "initial"].includes(value) && !other)) physicalCss.add(where.replace("%", `${prop}: ${value}`));
      if ((prop === "text-align" || prop === "float") && (value === "left" || value === "right")) physicalCss.add(where.replace("%", `${prop}: ${value}`));
    }
  };
  // Inline styles (style="margin-left: 24px"), which React and Vue write as often as stylesheets.
  for (const el of all) {
    const style = (el as HTMLElement).style;
    if (style?.length) judge(`${sel(el)} style="%"`, style);
  }
  for (const sheet of [...document.styleSheets]) {
    let rules: CSSRuleList;
    try { rules = sheet.cssRules; } catch { continue; }
    const walk = (list: CSSRuleList) => {
      for (const rule of [...list]) {
        if (rule instanceof CSSStyleRule) judge(`${rule.selectorText} { % }`, rule.style);
        if ("cssRules" in rule && (rule as CSSGroupingRule).cssRules) walk((rule as CSSGroupingRule).cssRules);
      }
    };
    walk(rules);
  }
  const utility = /^-?(ml|mr|pl|pr|left|right|border-l|border-r|rounded-l|rounded-r|rounded-tl|rounded-tr|rounded-bl|rounded-br|scroll-ml|scroll-mr|scroll-pl|scroll-pr)-|^text-(left|right)$|^float-(left|right)$|^(border-l|border-r|rounded-l|rounded-r)$/;
  const physicalClasses: PageFacts["physicalClasses"] = [];
  for (const el of all) {
    const classes = [...el.classList].filter((c) => utility.test(c.split(":").pop() || ""));
    if (classes.length) physicalClasses.push({ selector: sel(el), classes });
    if (physicalClasses.length >= 20) break;
  }

  // Animations running right now, and which properties they animate.
  const animations = document.getAnimations().map((a) => {
    const effect = a.effect as KeyframeEffect | null;
    const target = effect?.target as Element | null;
    const props = new Set<string>();
    for (const frame of effect?.getKeyframes() ?? []) {
      for (const key of Object.keys(frame)) if (!["offset", "easing", "composite", "computedOffset"].includes(key)) props.add(key);
    }
    const timing = effect?.getComputedTiming();
    const r = target?.getBoundingClientRect();
    return {
      selector: target ? sel(target) : "(unknown)",
      props: [...props],
      duration: Number(timing?.duration) || 0,
      running: a.playState === "running",
      iterations: timing?.iterations === Infinity ? -1 : Number(timing?.iterations) || 1,
      area: r ? Math.round(r.width * r.height) : 0,
    };
  });

  return {
    viewport: vw,
    scrollWidth: document.documentElement.scrollWidth,
    overflowing,
    clipped,
    overlaps,
    targets,
    bodyFont: parseFloat(getComputedStyle(document.body).fontSize),
    tinyText,
    physicalCss: [...physicalCss].slice(0, 30),
    physicalClasses,
    cls: (window as unknown as { __lawhaCls?: number }).__lawhaCls ?? 0,
    started: (window as unknown as { __lawhaAnims?: PageFacts["started"] }).__lawhaAnims ?? [],
    shifted: Object.entries((window as unknown as { __lawhaShifts?: Record<string, number> }).__lawhaShifts ?? {}).sort((a, b) => b[1] - a[1]).slice(0, 3).map(([n]) => n),
    animations,
  };
}

const SAFE_PROPS = new Set(["transform", "opacity", "translate", "scale", "rotate", "filter", "clipPath", "offsetDistance"]);

export interface AuditResult {
  findings: Finding[];
  facts: { cls: number; targets: number; axeViolations: number };
}

/**
 * Text drawn over an image, a video or a canvas: axe cannot see those colours, so it compares the text
 * with the page background behind the media. Here the real pixels behind each such text are read from
 * a screenshot, and the contrast is taken against the worst tenth of them.
 */
async function textOverMedia(page: Page): Promise<{ selector: string; box: Box; ratio: number; needs: number; text: string }[]> {
  // Media below the first screen only draws once scrolled to (lazy images, paused 3D scenes): check
  // the page one screen at a time, then scroll back.
  const height = await page.evaluate(() => document.documentElement.scrollHeight);
  const view = page.viewportSize()?.height ?? 900;
  const found: { selector: string; box: Box; ratio: number; needs: number; text: string }[] = [];
  for (let top = 0; top < Math.min(height, view * 8); top += view) {
    await page.evaluate((y) => window.scrollTo(0, y), top);
    await page.waitForTimeout(top === 0 ? 0 : 450);
    const scrolled = await page.evaluate(() => scrollY);
    for (const f of await textOverMediaInView(page)) {
      if (!found.some((g) => g.selector === f.selector && g.text === f.text)) found.push({ ...f, box: { ...f.box, y: f.box.y + scrolled } });
    }
  }
  await page.evaluate(() => window.scrollTo(0, 0));
  return found;
}

async function textOverMediaInView(page: Page): Promise<{ selector: string; box: Box; ratio: number; needs: number; text: string }[]> {
  const items = await page.evaluate(() => {
    const media = [...document.querySelectorAll("img, video, canvas, picture, svg image")].map((m) => m.getBoundingClientRect()).filter((r) => r.width * r.height > 20_000);
    const bgImage = [...document.querySelectorAll("*")].filter((el) => getComputedStyle(el).backgroundImage !== "none").map((el) => el.getBoundingClientRect()).filter((r) => r.width * r.height > 20_000);
    const zones = [...media, ...bgImage];
    const out: { selector: string; x: number; y: number; w: number; h: number; color: string; size: number; weight: number; text: string }[] = [];
    if (!zones.length) return out;
    for (const el of document.body.querySelectorAll("*")) {
      const own = [...el.childNodes].filter((n) => n.nodeType === 3).map((n) => n.textContent ?? "").join("").trim();
      if (!own) continue;
      const r = el.getBoundingClientRect();
      if (r.width < 4 || r.height < 4 || r.bottom < 0 || r.top > innerHeight) continue;
      const overlaps = zones.some((z) => r.left < z.right && r.right > z.left && r.top < z.bottom && r.bottom > z.top);
      if (!overlaps) continue;
      // An opaque background between the text and the media hides the media: nothing to check.
      let opaque = false;
      for (let p: Element | null = el; p && p !== document.body; p = p.parentElement) {
        const s = getComputedStyle(p);
        const m = s.backgroundColor.match(/rgba?\(([^)]+)\)/);
        const alpha = m ? Number(m[1]!.split(",")[3] ?? 1) : 0;
        if (alpha >= 0.95 && s.backgroundImage === "none") { const pr = p.getBoundingClientRect(); if (pr.width * pr.height < 600_000) { opaque = true; break; } }
        if (p.matches("img, video, canvas")) break;
      }
      if (opaque) continue;
      const s = getComputedStyle(el);
      el.setAttribute("data-lawha-over-media", "");
      out.push({ selector: el.id ? `#${el.id}` : `${el.tagName.toLowerCase()}${el.classList[0] ? "." + el.classList[0] : ""}`, x: r.x, y: r.y, w: r.width, h: r.height, color: s.color, size: parseFloat(s.fontSize), weight: Number(s.fontWeight), text: own.slice(0, 50) });
      if (out.length >= 40) break;
    }
    return out;
  });
  if (!items.length) return [];
  // The background behind the letters, exactly: the same screen with that text made invisible for
  // one screenshot. (Sampling around the letters mistakes their soft edges, or a neighbour's text,
  // for background.)
  await page.addStyleTag({ content: "[data-lawha-over-media]{color:transparent!important;-webkit-text-fill-color:transparent!important;text-shadow:none!important;text-decoration-color:transparent!important}" });
  const shot = PNG.sync.read(await page.screenshot({ animations: "disabled" }));
  await page.evaluate(() => {
    document.querySelectorAll("[data-lawha-over-media]").forEach((el) => el.removeAttribute("data-lawha-over-media"));
    [...document.querySelectorAll("style")].filter((t) => t.textContent?.startsWith("[data-lawha-over-media]")).forEach((t) => t.remove());
  });
  const lum = (r: number, g: number, b: number) => {
    const f = (v: number) => { const c = v / 255; return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4; };
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
  };
  const found: { selector: string; box: Box; ratio: number; needs: number; text: string }[] = [];
  for (const it of items) {
    const m = it.color.match(/[\d.]+/g)?.map(Number) ?? [0, 0, 0];
    const lt = lum(m[0]!, m[1]!, m[2]!);
    // With the text hidden, every pixel in its box is background. Take the worst tenth.
    const background: number[] = [];
    const x0 = Math.max(0, Math.floor(it.x)), x1 = Math.min(shot.width, Math.ceil(it.x + it.w));
    const y0 = Math.max(0, Math.floor(it.y)), y1 = Math.min(shot.height, Math.ceil(it.y + it.h));
    for (let y = y0; y < y1; y += 2) {
      for (let x = x0; x < x1; x += 2) {
        const i = (y * shot.width + x) * 4;
        const lb = lum(shot.data[i]!, shot.data[i + 1]!, shot.data[i + 2]!);
        background.push((Math.max(lt, lb) + 0.05) / (Math.min(lt, lb) + 0.05));
      }
    }
    if (background.length < 10) continue;
    background.sort((a, b) => a - b);
    const worst = background[Math.floor(background.length * 0.1)]!;
    const large = it.size >= 24 || (it.size >= 18.66 && it.weight >= 700);
    const needs = large ? 3 : 4.5;
    if (worst < needs) found.push({ selector: it.selector, box: { x: Math.round(it.x), y: Math.round(it.y), w: Math.round(it.w), h: Math.round(it.h) }, ratio: Math.round(worst * 100) / 100, needs, text: it.text });
  }
  return found;
}

/** Large canvases (WebGL scenes: Three.js, R3F, Spline...) that keep drawing under "reduce motion". */
async function movingCanvases(page: Page): Promise<{ selector: string; box: Box; engine: string }[]> {
  const canvases = await page.evaluate(() => [...document.querySelectorAll("canvas")].map((c, i) => {
    const r = c.getBoundingClientRect();
    return { i, x: r.x, y: r.y, w: r.width, h: r.height, engine: c.getAttribute("data-engine") ?? "", id: c.id };
  }).filter((c) => c.w * c.h > 40_000 && c.y < innerHeight && c.x < innerWidth));
  const moving: { selector: string; box: Box; engine: string }[] = [];
  for (const c of canvases.slice(0, 4)) {
    const clip = { x: Math.max(0, c.x), y: Math.max(0, c.y), width: Math.min(c.w, 600), height: Math.min(c.h, 400) };
    const a = await page.screenshot({ clip, animations: "allow" });
    await page.waitForTimeout(700);
    const b = await page.screenshot({ clip, animations: "allow" });
    if (!a.equals(b)) moving.push({ selector: c.id ? `#${c.id}` : `canvas:nth-of-type(${c.i + 1})`, box: { x: Math.round(c.x), y: Math.round(c.y), w: Math.round(c.w), h: Math.round(c.h) }, engine: c.engine });
  }
  return moving;
}

/**
 * Motion made by script (requestAnimationFrame, timers): no CSS or Web Animation to read, so the
 * viewport is photographed twice with those paused and canvases and videos masked; what still
 * changed moves by script. A MutationObserver names the element the script writes to.
 */
async function scriptMotion(page: Page): Promise<{ selector: string; box: Box }[]> {
  await page.evaluate(() => {
    for (const a of document.getAnimations()) a.pause();
    const name = (el: Element) => el.id ? `#${el.id}` : el.tagName.toLowerCase() + [...el.classList].slice(0, 2).map((c) => `.${c}`).join("");
    const seen = new Map<string, number>();
    const w = window as unknown as { __lawhaMut?: MutationObserver; __lawhaMoved?: Map<string, number> };
    w.__lawhaMoved = seen;
    w.__lawhaMut = new MutationObserver((list) => {
      for (const m of list) {
        if (m.target.nodeType !== 1) continue;
        const r = (m.target as Element).getBoundingClientRect();
        seen.set(name(m.target as Element), Math.round(r.width * r.height));
      }
    });
    w.__lawhaMut.observe(document.body, { attributes: true, attributeFilter: ["style", "class", "transform", "d", "x", "y", "cx", "cy"], subtree: true });
  });
  const mask = [page.locator("canvas, video")];
  const first = await page.screenshot({ animations: "allow", mask });
  await page.waitForTimeout(700);
  const second = await page.screenshot({ animations: "allow", mask });
  const moved = await page.evaluate(() => {
    const w = window as unknown as { __lawhaMut?: MutationObserver; __lawhaMoved?: Map<string, number> };
    w.__lawhaMut?.disconnect();
    return [...(w.__lawhaMoved ?? new Map<string, number>())].sort((a, b) => b[1] - a[1]).map(([n]) => n);
  });
  if (first.equals(second)) return [];
  const a = PNG.sync.read(first), b = PNG.sync.read(second);
  let x0 = a.width, y0 = a.height, x1 = -1, y1 = -1;
  for (let y = 0; y < a.height; y++) {
    for (let x = 0; x < a.width; x++) {
      const i = (y * a.width + x) * 4;
      if (Math.abs(a.data[i]! - b.data[i]!) + Math.abs(a.data[i + 1]! - b.data[i + 1]!) + Math.abs(a.data[i + 2]! - b.data[i + 2]!) > 24) {
        x0 = Math.min(x0, x); y0 = Math.min(y0, y); x1 = Math.max(x1, x); y1 = Math.max(y1, y);
      }
    }
  }
  if (x1 < 0 || (x1 - x0 + 1) * (y1 - y0 + 1) < 64) return []; // a blinking caret or a pixel of noise
  return [{ selector: moved[0] ?? "(something on the page)", box: { x: x0, y: y0, w: x1 - x0 + 1, h: y1 - y0 + 1 } }];
}

export async function audit(page: Page, v: Variant, opts: { expectRtl: boolean }): Promise<AuditResult> {
  const facts = await page.evaluate(collect);
  const where = { width: v.width, theme: v.theme, dir: v.dir, motion: v.motion };
  const findings: Finding[] = [];
  const add = (f: Omit<Finding, keyof typeof where>) => findings.push({ ...f, ...where });
  if (v.motion === "reduce") {
    // This pass exists only to see what keeps moving; layout was checked in the full-motion passes.
    for (const a of facts.animations) {
      if (a.running && a.duration > 50 && a.props.some((p) => p !== "opacity")) {
        add({ check: "motion.reduced", severity: "fail", message: `An animation (${a.props.join(", ")}) still runs with "reduce motion" on.`, selector: a.selector });
      }
    }
    for (const c of await movingCanvases(page)) {
      add({ check: "motion.webgl-reduced", severity: "fail", message: `A ${c.engine || "canvas"} scene keeps animating with "reduce motion" on: render one still frame instead (R3F: frameloop="demand").`, selector: c.selector, box: c.box });
    }
    for (const m of await scriptMotion(page)) {
      add({ check: "motion.reduced", severity: "fail", message: `Something moves by script (requestAnimationFrame or a timer) with "reduce motion" on; check matchMedia("(prefers-reduced-motion: reduce)") before animating.`, selector: m.selector, box: m.box });
    }
    return { findings, facts: { cls: round(facts.cls, 3), targets: facts.targets.length, axeViolations: 0 } };
  }

  if (facts.scrollWidth > facts.viewport + 1) {
    add({
      check: "layout.horizontal-scroll",
      severity: "fail",
      message: `The page scrolls sideways: ${facts.scrollWidth}px wide in a ${facts.viewport}px viewport.`,
      selector: facts.overflowing[0]?.selector,
      box: facts.overflowing[0]?.box,
    });
  }
  for (const c of facts.clipped) {
    add({ check: "layout.clipped-text", severity: "fail", message: `Text is cut off: "${c.text}"`, selector: c.selector, box: c.box });
  }
  for (const o of facts.overlaps) {
    add({ check: "layout.overlapping-text", severity: "fail", message: `Text overlaps other text (${o.b}).`, selector: o.a, box: o.box });
  }

  const phone = v.width <= PHONE_MAX;
  for (const t of facts.targets) {
    if (t.inline) continue;
    const small = Math.min(t.box.w, t.box.h);
    if (small < 24) {
      add({ check: "phone.tap-target", severity: "fail", message: `Tap target "${t.label || t.selector}" is ${t.box.w}×${t.box.h}px; WCAG 2.2 AA needs at least 24×24 (or enough spacing).`, selector: t.selector, box: t.box });
    } else if (phone && small < 44) {
      add({ check: "phone.tap-target", severity: "warn", message: `Tap target "${t.label || t.selector}" is ${t.box.w}×${t.box.h}px; 44×44 is the comfortable size on phones.`, selector: t.selector, box: t.box });
    }
  }
  if (phone && facts.bodyFont < 16) {
    add({ check: "phone.base-font", severity: "warn", message: `Body text is ${facts.bodyFont}px on a phone; 16px is the readable minimum and stops iOS zooming into inputs.` });
  }
  for (const t of facts.tinyText) {
    add({ check: "phone.tiny-text", severity: "warn", message: `Text at ${t.size}px is hard to read.`, selector: t.selector });
  }

  if (facts.cls > 0.1) {
    add({ check: "layout.shift", severity: facts.cls > 0.25 ? "fail" : "warn", message: `Layout shifts while loading (CLS ${round(facts.cls, 3)}; good is 0.1 or less)${facts.shifted.length ? `; what moved: ${facts.shifted.join(", ")}` : ""}. Reserve the space (fixed heights, aspect-ratio, a skeleton the same size as the content).` });
  }

  const rtlSeverity = opts.expectRtl ? "fail" : "info";
  // At every width: a menu or a section a script draws only on phones has its own CSS.
  if (v.dir === "ltr" && v.theme === "light" && v.motion === "full") {
    for (const rule of facts.physicalCss) {
      add({ check: "rtl.physical-css", severity: rtlSeverity, message: `Physical left/right CSS will not mirror in RTL: ${rule}` });
    }
    for (const p of facts.physicalClasses) {
      add({ check: "rtl.physical-class", severity: rtlSeverity, message: `Use logical utilities (ms-/me-/ps-/pe-/start-/end-/text-start) instead of: ${p.classes.join(" ")}`, selector: p.selector });
    }
  }

  // Motion that never stops: WCAG 2.2.2 asks for a way to pause anything that moves on its own for
  // more than 5 seconds next to other content. Small loading indicators (under 64x64) are exempt.
  if (v.motion === "full" && v.theme === "light" && v.dir === "ltr") {
    const loops = new Map<string, number>();
    for (const a of facts.animations) if (a.running && a.iterations === -1 && a.area >= 64 * 64 && a.props.some((p) => p !== "opacity" || a.area >= 200 * 200)) loops.set(a.selector, a.area);
    for (const [selector] of [...loops].slice(0, 5)) {
      add({ check: "motion.endless", severity: "warn", message: "This keeps moving forever. Anything that moves on its own for more than 5 seconds needs a pause button, or should stop after a few cycles (WCAG 2.2.2).", selector });
    }
    // UI motion over a second feels sluggish: entrances and feedback are usually 150-600ms.
    const slow = new Map<string, number>();
    for (const a of facts.started) {
      if (a.iterations !== -1 && a.duration > 1000 && a.area > 0 && !a.props.every((p) => p === "opacity" && a.duration <= 1500)) slow.set(a.selector, Math.max(slow.get(a.selector) ?? 0, a.duration));
    }
    for (const [selector, ms] of [...slow].slice(0, 5)) {
      add({ check: "motion.slow", severity: "warn", message: `An animation takes ${(ms / 1000).toFixed(1)}s; interface motion over a second feels sluggish (entrances and feedback are usually 150-600ms).`, selector });
    }
  }

  for (const a of facts.animations) {
    const costly = a.props.filter((p) => !SAFE_PROPS.has(p));
    if (costly.length && v.width === 1280 && v.theme === "light" && v.dir === "ltr") {
      add({ check: "motion.costly-property", severity: "warn", message: `Animates ${costly.join(", ")}, which forces layout or paint; animate transform and opacity instead.`, selector: a.selector });
    }
  }

  for (const t of await textOverMedia(page)) {
    add({ check: "a11y.contrast-over-media", severity: "fail", message: `Text over an image, video or 3D scene is hard to read: "${t.text}" has ${t.ratio}:1 against the darkest or lightest part behind it (needs ${t.needs}:1). Add a veil or scrim, move the text, or change its colour.`, selector: t.selector, box: t.box });
  }

  let axeViolations = 0;
  {
    const axe = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]).analyze();
    for (const violation of axe.violations) {
      axeViolations += violation.nodes.length;
      const severity = violation.impact === "minor" ? "warn" : "fail";
      add({
        check: `a11y.${violation.id}`,
        severity,
        message: `${violation.help} (${violation.nodes.length} element${violation.nodes.length === 1 ? "" : "s"})`,
        selector: violation.nodes[0]?.target.join(" "),
      });
    }
  }
  return { findings, facts: { cls: round(facts.cls, 3), targets: facts.targets.length, axeViolations } };
}
