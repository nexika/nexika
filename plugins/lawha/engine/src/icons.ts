/**
 * Icons in right-to-left layouts. Some icons point along the reading direction and must mirror in
 * Arabic: an arrow that means "next" points left there, as do chevrons, send, reply, undo/redo,
 * log-out, text alignment and lists. Others must never mirror: media controls show the direction a
 * tape plays, clocks turn clockwise everywhere, ticks and logos are drawn one way.
 *
 * The check renders the page in both directions; each icon's name comes from its icon set (lucide,
 * tabler, Font Awesome, Bootstrap Icons, Material ligatures, <use href="#...">, image file names) or
 * is a text arrow (→), and its drawn direction comes from the transforms on it and its ancestors.
 * The same icon is then compared between the LTR and RTL renders.
 */
import type { Page } from "playwright";
import type { Variant } from "./browser.js";
import type { Box, Finding } from "./util.js";

export interface Icon {
  name: string; // what the icon set calls it, e.g. "arrow-right"
  rule: "mirror" | "never";
  points: "left" | "right" | null; // the direction its name gives, in an unflipped drawing
  flipped: boolean; // drawn mirrored horizontally (scaleX(-1), rotate(180deg), rotateY(180deg))
  label: string; // the button or link it belongs to, or its own label
  selector: string;
  box: Box;
}

/** Runs in the page: every named icon, in document order. */
export function collectIcons(): Icon[] {
  const MIRROR = /(^|[-_ ])(arrow|chevron|chevrons|caret|angle|triangle|move|corner-[a-z]+)[-_ ]?(left|right)|arrow[-_ ]?(back|forward)|navigate[-_ ](before|next)|keyboard[-_ ](arrow|double[-_ ]arrow)[-_ ](left|right)|(^|[-_ ])(back|forward|next|prev|previous)($|[-_ ])|first[-_ ]page|last[-_ ]page|(^|[-_ ])(send|reply|reply-all|undo|redo|log-?out|sign-?out|exit|log-?in|sign-?in|import|export|indent|outdent|list|list-ordered|list-bullet|format[-_ ]list|align[-_ ]?(left|right)|text[-_ ]align[-_ ]?(left|right)|trending[-_ ](up|down)|reply)($|[-_ ])/i;
  const NEVER = /(^|[-_ ])(play|pause|stop|fast[-_ ]?forward|fast[-_ ]?rewind|rewind|skip[-_ ]?(next|previous|back|forward)?|seek|media|clock|timer|alarm|watch|history|check|check-circle|github|gitlab|twitter|x-twitter|youtube|facebook|instagram|linkedin|google|apple|music|headphones)($|[-_ ])/i;
  const TEXT_ARROWS: Record<string, "left" | "right"> = { "→": "right", "←": "left", "›": "right", "‹": "left", "»": "right", "«": "left", "⟶": "right", "⟵": "left", "➜": "right", "➔": "right", "⇒": "right", "⇐": "left", "▸": "right", "◂": "left" };
  const ICONISH = /^(lucide|tabler-icon|fa|fas|far|fab|fa-solid|fa-regular|bi|material-icons|material-symbols|icon|ph|ri|mdi|heroicon|feather)/;

  const nameOf = (el: Element): string | null => {
    const fromClass = [...el.classList].filter((c) => !ICONISH.test(c) || /-(.+)/.test(c)).map((c) => c.replace(/^(lucide|tabler-icon|fa|bi|ph|ri|mdi|icon|feather)-/, "")).filter((c) => /[a-z]/.test(c) && c.length > 2);
    const iconClass = [...el.classList].some((c) => ICONISH.test(c));
    const use = el.querySelector("use")?.getAttribute("href") ?? el.querySelector("use")?.getAttribute("xlink:href");
    const candidates = [
      el.getAttribute("data-icon"), el.getAttribute("data-lucide"), el.getAttribute("icon"),
      use ? use.replace(/^.*#/, "") : null,
      el.tagName === "IMG" ? (el.getAttribute("src") ?? "").split("/").pop()!.replace(/\.(svg|png|webp)(\?.*)?$/, "") : null,
      // Material icons and symbols are ligatures: the text is the name.
      /material-(icons|symbols)/.test(el.className.toString()) ? (el.textContent ?? "").trim() : null,
      iconClass ? fromClass.join(" ") : null,
      el.tagName === "svg" ? fromClass.join(" ") : null,
      el.getAttribute("aria-label"), el.tagName === "svg" ? el.querySelector("title")?.textContent ?? null : null,
    ];
    for (const c of candidates) if (c && (MIRROR.test(c) || NEVER.test(c))) return c.trim();
    return null;
  };
  // Drawn mirrored left-right? The `transform` matrix, and the separate `scale` and `rotate`
  // properties (Tailwind 4's -scale-x-100 and rotate-180 set those, not transform).
  const flippedOf = (el: Element): boolean => {
    let sign = 1;
    for (let e: Element | null = el; e && e !== document.documentElement; e = e.parentElement) {
      const s = getComputedStyle(e);
      if (s.transform && s.transform !== "none" && Number(s.transform.replace(/^matrix(3d)?\(/, "").split(",")[0]) < 0) sign = -sign;
      if (s.scale && s.scale !== "none" && parseFloat(s.scale.split(" ")[0]!) < 0) sign = -sign;
      if (s.rotate && s.rotate !== "none") {
        // "180deg" (around z) or "y 180deg" turn an arrow around; "x 180deg" only flips it upside down.
        const m = s.rotate.match(/^(x|y|z)?\s*(-?[\d.]+)(deg|turn|rad)$/);
        if (m && m[1] !== "x") {
          const deg = m[3] === "turn" ? Number(m[2]) * 360 : m[3] === "rad" ? (Number(m[2]) * 180) / Math.PI : Number(m[2]);
          if (Math.cos((deg * Math.PI) / 180) < 0) sign = -sign;
        }
      }
    }
    return sign < 0;
  };
  const labelOf = (el: Element): string => {
    const owner = el.closest("a, button, [role=button], [role=link], [role=tab], li, label");
    const text = (owner as HTMLElement | null)?.innerText?.trim() || owner?.getAttribute("aria-label") || el.getAttribute("aria-label") || "";
    return text.replace(/\s+/g, " ").slice(0, 40);
  };
  const selectorOf = (el: Element) => el.tagName.toLowerCase() + (el.id ? `#${el.id}` : "") + [...el.classList].slice(0, 2).map((c) => `.${c}`).join("");
  const pointsOf = (name: string): "left" | "right" | null => {
    if (/left|back|before|prev|previous|first|undo|reply|outdent|←|‹|«|⟵|⇐|◂/i.test(name)) return "left";
    if (/right|forward|next|last|redo|send|log-?out|sign-?out|exit|export|indent|trending|→|›|»|⟶|➜|➔|⇒|▸|list|align/i.test(name)) return "right";
    return null;
  };

  const out: Icon[] = [];
  const els = document.body.querySelectorAll("svg, img, i, span, [data-icon]");
  for (const el of els) {
    const r = el.getBoundingClientRect();
    if (r.width === 0 || r.height === 0 || r.width > 64 || r.height > 64) continue;
    if (el.closest("svg") && el.tagName !== "svg") continue;
    let name = nameOf(el);
    if (!name && el.tagName === "SPAN" && el.childElementCount === 0) {
      const t = (el.textContent ?? "").trim();
      if (t in TEXT_ARROWS) name = `text ${t}`;
    }
    if (!name) continue;
    const never = NEVER.test(name) && !/arrow|chevron|caret/i.test(name);
    out.push({
      name, rule: never ? "never" : "mirror", points: never ? null : pointsOf(name), flipped: flippedOf(el),
      label: labelOf(el), selector: selectorOf(el),
      box: { x: Math.round(r.x + scrollX), y: Math.round(r.y + scrollY), w: Math.round(r.width), h: Math.round(r.height) },
    });
  }
  return out;
}

export async function icons(page: Page): Promise<Icon[]> {
  return page.evaluate(collectIcons);
}

const family = (name: string) => name.toLowerCase().replace(/left|right|back|forward|before|next|prev(ious)?|first|last|undo|redo|←|→|‹|›|«|»/g, "").replace(/[-_ ]+/g, " ").trim();
const facing = (i: Icon) => (i.points === null ? null : i.flipped ? (i.points === "left" ? "right" : "left") : i.points);

/** Compare the same icons in the LTR and RTL renders of one width and theme. */
export function iconFindings(ltr: Icon[], rtl: Icon[], v: Omit<Variant, "dir">, expectRtl: boolean): Finding[] {
  const out: Finding[] = [];
  const where = { width: v.width, theme: v.theme, dir: "rtl" as const, motion: v.motion };
  // Pair them in document order within each family (arrows with arrows, play with play), so an app
  // that swaps arrow-right for arrow-left in Arabic is paired correctly.
  const used = new Set<number>();
  for (const a of ltr) {
    const j = rtl.findIndex((b, k) => !used.has(k) && family(b.name) === family(a.name) && b.rule === a.rule);
    if (j < 0) continue;
    used.add(j);
    const b = rtl[j]!;
    const what = `${a.label ? `"${a.label}" ` : ""}(${a.name})`;
    if (a.rule === "mirror" && facing(a) !== null && facing(a) === facing(b)) {
      out.push({ check: "rtl.icon-not-mirrored", severity: expectRtl ? "fail" : "warn", message: `The icon ${what} points ${facing(b)} in Arabic too: it shows direction, so it should point the other way. Add \`rtl:-scale-x-100\` to it, or use the opposite icon in RTL.`, selector: b.selector, box: b.box, ...where });
    }
    if (a.rule === "never" && a.flipped !== b.flipped) {
      out.push({ check: "rtl.icon-mirrored", severity: "warn", message: `The icon ${what} is mirrored in Arabic: media controls, clocks, ticks and logos keep their direction in every language.`, selector: b.selector, box: b.box, ...where });
    }
  }
  return out;
}
