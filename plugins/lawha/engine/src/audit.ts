import { AxeBuilder } from "@axe-core/playwright";
import type { Page } from "playwright";
import type { Variant } from "./browser.js";
import { PHONE_MAX, type Box, type Finding, round } from "./util.js";

/** What the page reports about itself; collected inside the browser. */
interface PageFacts {
  viewport: number;
  scrollWidth: number;
  overflowing: { selector: string; box: Box }[];
  clipped: { selector: string; box: Box; text: string }[];
  overlaps: { a: string; b: string; box: Box }[];
  targets: { selector: string; box: Box; label: string }[];
  bodyFont: number;
  tinyText: { selector: string; size: number }[];
  physicalCss: string[];
  physicalClasses: { selector: string; classes: string[] }[];
  cls: number;
  animations: { selector: string; props: string[]; duration: number; running: boolean }[];
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
  const textEls = all.filter((el) => visible(el) && [...el.childNodes].some((n) => n.nodeType === 3 && n.textContent!.trim()));
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
  const interactive = all.filter((el) => visible(el) && el.matches("a[href], button, input:not([type=hidden]), select, textarea, summary, [role=button], [role=link], [role=checkbox], [role=switch], [role=tab], [onclick], [tabindex]:not([tabindex='-1'])"));
  const targets = interactive.map((el) => ({
    selector: sel(el),
    box: boxOf(el.getBoundingClientRect()),
    label: ((el as HTMLElement).innerText || el.getAttribute("aria-label") || el.getAttribute("title") || "").trim().slice(0, 40),
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
  for (const sheet of [...document.styleSheets]) {
    let rules: CSSRuleList;
    try { rules = sheet.cssRules; } catch { continue; }
    const walk = (list: CSSRuleList) => {
      for (const rule of [...list]) {
        if (rule instanceof CSSStyleRule) {
          for (const prop of [...rule.style]) {
            const value = rule.style.getPropertyValue(prop).trim();
            const other = rule.style.getPropertyValue(mirror(prop)).trim();
            if (physical.test(prop) && value && value !== other && !(["0", "0px", "auto", "initial"].includes(value) && !other)) physicalCss.add(`${rule.selectorText} { ${prop}: ${value} }`);
            if (prop === "text-align" && (value === "left" || value === "right")) physicalCss.add(`${rule.selectorText} { text-align: ${value} }`);
            if (prop === "float" && (value === "left" || value === "right")) physicalCss.add(`${rule.selectorText} { float: ${value} }`);
          }
        }
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
    return {
      selector: target ? sel(target) : "(unknown)",
      props: [...props],
      duration: Number(timing?.duration) || 0,
      running: a.playState === "running",
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
    animations,
  };
}

const SAFE_PROPS = new Set(["transform", "opacity", "translate", "scale", "rotate", "filter", "clipPath", "offsetDistance"]);

export interface AuditResult {
  findings: Finding[];
  facts: { cls: number; targets: number; axeViolations: number };
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
    add({ check: "layout.shift", severity: facts.cls > 0.25 ? "fail" : "warn", message: `Layout shifts while loading (CLS ${round(facts.cls, 3)}; good is 0.1 or less).` });
  }

  const rtlSeverity = opts.expectRtl ? "fail" : "info";
  if (v.dir === "ltr" && v.width === 1280 && v.theme === "light" && v.motion === "full") {
    for (const rule of facts.physicalCss) {
      add({ check: "rtl.physical-css", severity: rtlSeverity, message: `Physical left/right CSS will not mirror in RTL: ${rule}` });
    }
    for (const p of facts.physicalClasses) {
      add({ check: "rtl.physical-class", severity: rtlSeverity, message: `Use logical utilities (ms-/me-/ps-/pe-/start-/end-/text-start) instead of: ${p.classes.join(" ")}`, selector: p.selector });
    }
  }

  for (const a of facts.animations) {
    const costly = a.props.filter((p) => !SAFE_PROPS.has(p));
    if (costly.length && v.width === 1280 && v.theme === "light" && v.dir === "ltr") {
      add({ check: "motion.costly-property", severity: "warn", message: `Animates ${costly.join(", ")}, which forces layout or paint; animate transform and opacity instead.`, selector: a.selector });
    }
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
