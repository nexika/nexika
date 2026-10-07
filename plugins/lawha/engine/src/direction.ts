/**
 * Design directions for developers who cannot picture a design: three complete token sets proposed by
 * Claude's director agent, checked here (contrast, the known "AI look", sameness), rendered as real
 * preview pages, shown side by side, and the one the person picks turned into the project's tokens.
 */

export type Hex = string;

export interface Palette {
  background: Hex;
  surface: Hex;
  text: Hex;
  muted: Hex;
  primary: Hex;
  primaryText: Hex;
  accent: Hex;
  border: Hex;
}

export interface Font {
  family: string;
  weights: number[];
}

export interface Direction {
  id: string; // "a", "b", "c"
  name: string;
  mood: string; // one sentence: what it feels like and why it fits
  fonts: { display: Font; text: Font; arabic?: Font };
  scale: { base: number; ratio: number };
  radius: number; // px for cards; buttons follow
  spacing: 4 | 8;
  palette: { light: Palette; dark: Palette };
  signature: string; // the one memorable element, in words
  /** How the signature is drawn in the preview, so the person sees it rather than reads it. */
  motif: "underline" | "cells" | "dots" | "rule" | "stamp" | "outline";
  motion: "calm" | "lively" | "precise";
  layout: "editorial" | "split" | "bento" | "stacked" | "asymmetric" | "centered";
}

export interface Brief {
  /** landing: a public page; dashboard: an app screen the person uses every day. */
  kind?: "landing" | "dashboard";
  product: string;
  audience: string;
  feeling: string;
  headline?: string;
  sub?: string;
  lang?: "en" | "ar" | "fr";
}

export interface Problem {
  direction: string;
  severity: "fail" | "warn";
  message: string;
}

// ---------------------------------------------------------------- colour

function rgb(hex: Hex): [number, number, number] {
  const h = hex.replace("#", "");
  const full = h.length === 3 ? h.split("").map((c) => c + c).join("") : h.slice(0, 6);
  const n = parseInt(full, 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

function lum(hex: Hex): number {
  const f = (v: number) => {
    const s = v / 255;
    return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
  };
  const [r, g, b] = rgb(hex);
  return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
}

export function contrastRatio(a: Hex, b: Hex): number {
  const [hi, lo] = [lum(a), lum(b)].sort((x, y) => y - x) as [number, number];
  return Math.round(((hi + 0.05) / (lo + 0.05)) * 100) / 100;
}

export function hsl(hex: Hex): { h: number; s: number; l: number } {
  const [r, g, b] = rgb(hex).map((v) => v / 255) as [number, number, number];
  const max = Math.max(r, g, b), min = Math.min(r, g, b);
  const l = (max + min) / 2;
  if (max === min) return { h: 0, s: 0, l };
  const d = max - min;
  const s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
  const h = max === r ? (g - b) / d + (g < b ? 6 : 0) : max === g ? (b - r) / d + 2 : (r - g) / d + 4;
  return { h: h * 60, s, l };
}

function near(a: Hex, b: Hex, within: number): boolean {
  const [x, y] = [rgb(a), rgb(b)];
  return Math.hypot(x[0] - y[0], x[1] - y[1], x[2] - y[2]) <= within;
}

function hueGap(a: number, b: number): number {
  const d = Math.abs(a - b) % 360;
  return d > 180 ? 360 - d : d;
}

// ---------------------------------------------------------------- checks

/** The looks that read as "made by AI", named so they can be avoided (after Anthropic's frontend-design). */
const AI_LOOKS: { name: string; test: (p: Palette, d: Direction) => boolean }[] = [
  { name: "cream background with terracotta (#F4F1EA / #D97757)", test: (p) => near(p.background, "#F4F1EA", 28) && near(p.primary, "#D97757", 48) },
  { name: "near-black background with acid green", test: (p) => lum(p.background) < 0.02 && hsl(p.primary).h > 70 && hsl(p.primary).h < 110 && hsl(p.primary).s > 0.6 && hsl(p.primary).l > 0.45 },
  { name: "indigo #6366F1 on white, the default SaaS look", test: (p) => near(p.primary, "#6366F1", 40) && lum(p.background) > 0.9 },
  { name: "purple-to-blue on white with a single sans font", test: (p, d) => hsl(p.primary).h > 240 && hsl(p.primary).h < 290 && lum(p.background) > 0.9 && d.fonts.display.family === d.fonts.text.family },
  { name: "Inter (or system sans) for everything", test: (_p, d) => /^(inter|roboto|arial|helvetica|system-ui)$/i.test(d.fonts.display.family) && d.fonts.display.family === d.fonts.text.family },
];

export function check(directions: Direction[], history: HistoryEntry[] = []): Problem[] {
  const out: Problem[] = [];
  const add = (direction: string, severity: Problem["severity"], message: string) => out.push({ direction, severity, message });
  for (const d of directions) {
    for (const [mode, p] of Object.entries(d.palette) as ["light" | "dark", Palette][]) {
      const pairs: [string, Hex, Hex, number][] = [
        ["text on background", p.text, p.background, 4.5],
        ["text on surface", p.text, p.surface, 4.5],
        ["muted text on background", p.muted, p.background, 4.5],
        ["button text on primary", p.primaryText, p.primary, 4.5],
        ["primary on background (links, outlines)", p.primary, p.background, 3],
        ["border on background", p.border, p.background, 1.3],
      ];
      for (const [what, fg, bg, need] of pairs) {
        const r = contrastRatio(fg, bg);
        if (r < need) add(d.id, need >= 3 ? "fail" : "warn", `${mode}: ${what} is ${r}:1, needs ${need}:1`);
      }
      for (const look of AI_LOOKS) if (look.test(p, d)) add(d.id, "fail", `${mode}: ${look.name}`);
    }
    if (d.scale.ratio < 1.125 || d.scale.ratio > 1.618) add(d.id, "warn", `type scale ratio ${d.scale.ratio} is outside 1.125-1.618`);
    if (d.scale.base < 16) add(d.id, "fail", `base text ${d.scale.base}px is under 16px`);
  }
  // The three must be genuinely different from each other.
  for (let i = 0; i < directions.length; i++) {
    for (let j = i + 1; j < directions.length; j++) {
      const a = directions[i]!, b = directions[j]!;
      const sameFont = a.fonts.display.family.toLowerCase() === b.fonts.display.family.toLowerCase();
      const pa = hsl(a.palette.light.primary), pb = hsl(b.palette.light.primary);
      const sameHue = pa.s > 0.15 && pb.s > 0.15 && hueGap(pa.h, pb.h) < 35;
      const sameGround = Math.abs(lum(a.palette.light.background) - lum(b.palette.light.background)) < 0.05;
      if (sameFont) add(`${a.id}+${b.id}`, "fail", `both use ${a.fonts.display.family} for display: the directions must differ`);
      if (sameHue && sameGround) add(`${a.id}+${b.id}`, "fail", "primary colours and backgrounds are too close: the directions must differ");
      if (a.layout === b.layout && a.motion === b.motion) add(`${a.id}+${b.id}`, "warn", `same layout (${a.layout}) and motion (${a.motion})`);
    }
  }
  // And different from what this person got recently, so their projects do not all look alike.
  const recent = history.slice(-6);
  for (const d of directions) {
    const p = hsl(d.palette.light.primary);
    for (const h of recent) {
      const font = h.display.toLowerCase() === d.fonts.display.family.toLowerCase();
      const hue = h.primaryHue !== null && p.s > 0.15 && hueGap(h.primaryHue, p.h) < 25;
      if (font && hue) add(d.id, "fail", `too close to "${h.name}" (${h.project.split("/").pop()}, ${h.at.slice(0, 10)}): same display font and primary hue`);
      else if (font) add(d.id, "warn", `${d.fonts.display.family} was used recently ("${h.name}")`);
    }
  }
  return out;
}

// ---------------------------------------------------------------- history

export interface HistoryEntry {
  at: string;
  project: string;
  name: string;
  display: string;
  text: string;
  primaryHue: number | null;
  layout: string;
}

export function historyEntry(d: Direction, project: string): HistoryEntry {
  const p = hsl(d.palette.light.primary);
  return { at: new Date().toISOString(), project, name: d.name, display: d.fonts.display.family, text: d.fonts.text.family, primaryHue: p.s > 0.15 ? Math.round(p.h) : null, layout: d.layout };
}

// ---------------------------------------------------------------- the project's tokens

const MOTION = {
  calm: { fast: 220, base: 420, slow: 700, ease: "cubic-bezier(0.22, 1, 0.36, 1)", distance: 10 },
  lively: { fast: 160, base: 320, slow: 520, ease: "cubic-bezier(0.34, 1.56, 0.64, 1)", distance: 16 },
  precise: { fast: 120, base: 200, slow: 320, ease: "cubic-bezier(0.2, 0, 0, 1)", distance: 6 },
} as const;

export function motionOf(d: Direction) {
  return MOTION[d.motion];
}

function size(d: Direction, step: number): string {
  return `${Math.round(d.scale.base * d.scale.ratio ** step * 10) / 10}px`;
}

/** Text on a coloured fill: whichever of the palette's text and background reads better on it. */
function onColour(fill: Hex, p: Palette): Hex {
  return contrastRatio(p.text, fill) >= contrastRatio(p.background, fill) ? p.text : p.background;
}

/** Tailwind @theme tokens plus shadcn/ui's variables (light and .dark), from the chosen direction. */
export function themeCss(d: Direction): string {
  const l = d.palette.light, k = d.palette.dark, m = motionOf(d);
  const vars = (p: Palette) => [
    `  --background: ${p.background};`, `  --foreground: ${p.text};`,
    `  --card: ${p.surface};`, `  --card-foreground: ${p.text};`,
    `  --popover: ${p.surface};`, `  --popover-foreground: ${p.text};`,
    `  --primary: ${p.primary};`, `  --primary-foreground: ${p.primaryText};`,
    `  --secondary: ${p.surface};`, `  --secondary-foreground: ${p.text};`,
    `  --muted: ${p.surface};`, `  --muted-foreground: ${p.muted};`,
    `  --accent: ${p.accent};`, `  --accent-foreground: ${onColour(p.accent, p)};`,
    `  --border: ${p.border};`, `  --input: ${p.border};`, `  --ring: ${p.primary};`,
  ];
  const family = (f: Font) => `"${f.family}"`;
  return [
    `/* lawha direction "${d.name}": ${d.mood} */`,
    `/* Signature: ${d.signature} */`,
    "",
    "@theme inline {",
    "  --color-background: var(--background);", "  --color-foreground: var(--foreground);",
    "  --color-card: var(--card);", "  --color-card-foreground: var(--card-foreground);",
    "  --color-popover: var(--popover);", "  --color-popover-foreground: var(--popover-foreground);",
    "  --color-primary: var(--primary);", "  --color-primary-foreground: var(--primary-foreground);",
    "  --color-secondary: var(--secondary);", "  --color-secondary-foreground: var(--secondary-foreground);",
    "  --color-muted: var(--muted);", "  --color-muted-foreground: var(--muted-foreground);",
    "  --color-accent: var(--accent);", "  --color-accent-foreground: var(--accent-foreground);",
    "  --color-border: var(--border);", "  --color-input: var(--input);", "  --color-ring: var(--ring);",
    `  --font-display: ${family(d.fonts.display)}, ${d.fonts.arabic ? family(d.fonts.arabic) + ", " : ""}ui-serif, Georgia, serif;`,
    `  --font-sans: ${family(d.fonts.text)}, ${d.fonts.arabic ? family(d.fonts.arabic) + ", " : ""}ui-sans-serif, system-ui, sans-serif;`,
    `  --radius-card: ${d.radius}px;`,
    `  --radius-control: ${Math.max(2, Math.round(d.radius * 0.6))}px;`,
    `  --spacing: ${d.spacing === 8 ? "0.5rem" : "0.25rem"};`,
    `  --text-display: ${size(d, 5)};`, `  --text-h1: ${size(d, 4)};`, `  --text-h2: ${size(d, 3)};`, `  --text-h3: ${size(d, 2)};`, `  --text-lead: ${size(d, 1)};`,
    `  --ease-brand: ${m.ease};`,
    `  --duration-fast: ${m.fast}ms;`, `  --duration-base: ${m.base}ms;`, `  --duration-slow: ${m.slow}ms;`,
    "}",
    "",
    ":root {", ...vars(l), `  --radius: ${Math.max(2, Math.round(d.radius * 0.6))}px;`,
    // Motion timing as plain variables, always present (Tailwind only emits the @theme ones a class
    // uses): lawha's motion recipes read these, so every animation follows the direction.
    `  --lawha-motion: ${d.motion};`, `  --lawha-ease: ${m.ease};`,
    `  --lawha-fast: ${m.fast};`, `  --lawha-base: ${m.base};`, `  --lawha-slow: ${m.slow};`, `  --lawha-distance: ${m.distance};`,
    "}",
    "",
    ".dark {", ...vars(k), "}",
    "",
  ].join("\n");
}

// ---------------------------------------------------------------- the preview page

const COPY = {
  en: {
    nav: ["Today", "Topics", "Course", "Sessions"], landingNav: ["How it works", "Pricing", "About"],
    cta: "Start now", second: "See how it works", today: "Today", review: "Review now", start: "Start the warm-up",
    items: [["Output tokens cost more", "Tokens and cost", "missed"], ["Training data cutoff", "LLM basics", "shaky"], ["List comprehensions", "Python basics", "to refresh"]],
    topics: [["Claude API", 0.67], ["Tokens and cost", 0.33], ["LLM basics", 0.33], ["Python basics", 0.5]],
    mastery: "mastery", stats: [["3", "to review"], ["4", "topics"], ["12", "sessions"]],
    session: "Last session", sessionText: "Made a first call from Python, then a follow-up that resends the whole history.",
    quote: "It finally tells me what to study next.", quoteBy: "A learner, week 3",
    form: ["Your name", "Email", "Level", "Remind me to review", "Save"], foot: "Made with care.",
    features: ["Knows what you missed", "Teaches, then checks", "Follows your course"], featureText: "One clear sentence about why this matters to the people who use it.",
  },
  fr: {
    nav: ["Aujourd'hui", "Sujets", "Cours", "Séances"], landingNav: ["Fonctionnement", "Tarifs", "À propos"],
    cta: "Commencer", second: "Voir comment ça marche", today: "Aujourd'hui", review: "Réviser", start: "Lancer l'échauffement",
    items: [["Les tokens de sortie coûtent plus", "Tokens et coût", "manqué"], ["Date limite des données", "Bases des LLM", "fragile"], ["Compréhensions de liste", "Bases de Python", "à rafraîchir"]],
    topics: [["API Claude", 0.67], ["Tokens et coût", 0.33], ["Bases des LLM", 0.33], ["Bases de Python", 0.5]],
    mastery: "maîtrise", stats: [["3", "à réviser"], ["4", "sujets"], ["12", "séances"]],
    session: "Dernière séance", sessionText: "Un premier appel depuis Python, puis une suite qui renvoie tout l'historique.",
    quote: "Enfin, il me dit quoi réviser.", quoteBy: "Une apprenante, semaine 3",
    form: ["Votre nom", "E-mail", "Niveau", "Me rappeler de réviser", "Enregistrer"], foot: "Fait avec soin.",
    features: ["Sait ce que vous avez manqué", "Explique, puis vérifie", "Suit votre cours"], featureText: "Une phrase claire sur ce que cela change pour les personnes qui l'utilisent.",
  },
  ar: {
    nav: ["اليوم", "المواضيع", "الدورة", "الجلسات"], landingNav: ["كيف يعمل", "الأسعار", "من نحن"],
    cta: "ابدأ الآن", second: "شاهد كيف يعمل", today: "اليوم", review: "راجع الآن", start: "ابدأ الإحماء",
    items: [["رموز الإخراج أغلى", "الرموز والتكلفة", "فاتك"], ["تاريخ انتهاء البيانات", "أساسيات النماذج", "غير ثابت"], ["تعابير القوائم", "أساسيات Python", "للمراجعة"]],
    topics: [["واجهة Claude", 0.67], ["الرموز والتكلفة", 0.33], ["أساسيات النماذج", 0.33], ["أساسيات Python", 0.5]],
    mastery: "إتقان", stats: [["٣", "للمراجعة"], ["٤", "مواضيع"], ["١٢", "جلسة"]],
    session: "آخر جلسة", sessionText: "أول استدعاء من Python، ثم متابعة تعيد إرسال المحادثة كلها.",
    quote: "أخيرًا يخبرني بما أراجعه بعد ذلك.", quoteBy: "متعلّمة، الأسبوع الثالث",
    form: ["اسمك", "البريد الإلكتروني", "المستوى", "ذكّرني بالمراجعة", "حفظ"], foot: "صُنع بعناية.",
    features: ["يعرف ما فاتك", "يشرح ثم يتحقق", "يتبع دورتك"], featureText: "جملة واضحة واحدة عن سبب أهمية هذا لمن يستخدمه.",
  },
};

const esc = (s: string) => s.replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]!);

function fontsLink(d: Direction): string {
  const fams = [d.fonts.display, d.fonts.text, ...(d.fonts.arabic ? [d.fonts.arabic] : [])];
  const uniq = new Map<string, Set<number>>();
  for (const f of fams) {
    const set = uniq.get(f.family) ?? new Set<number>();
    f.weights.forEach((w) => set.add(w));
    uniq.set(f.family, set);
  }
  const q = [...uniq.entries()].map(([f, w]) => `family=${encodeURIComponent(f).replace(/%20/g, "+")}:wght@${[...w].sort((a, b) => a - b).join(";")}`).join("&");
  return `https://fonts.googleapis.com/css2?${q}&display=block`;
}

/** The signature, drawn: the same data shown the way this direction would show it. */
function motif(d: Direction, value: number, label: string): string {
  const pct = Math.round(value * 100);
  switch (d.motif) {
    case "cells":
      return `<span class="cells" role="img" aria-label="${pct}% ${esc(label)}">${Array.from({ length: 10 }, (_, i) => `<i class="${i < Math.round(value * 10) ? "on" : ""}"></i>`).join("")}</span>`;
    case "dots":
      return `<span class="dots" role="img" aria-label="${pct}% ${esc(label)}">${Array.from({ length: 6 }, (_, i) => `<i class="${i < Math.round(value * 6) ? "on" : ""}"></i>`).join("")}</span>`;
    case "rule":
      return `<span class="rule" role="img" aria-label="${pct}% ${esc(label)}"><i style="inline-size:${pct}%"></i></span>`;
    case "stamp":
      return `<span class="stamp">${pct}%</span>`;
    default:
      return `<span class="bar" role="img" aria-label="${pct}% ${esc(label)}"><i style="inline-size:${pct}%"></i></span>`;
  }
}

/** A complete page in the direction: an app screen (dashboard) or a public page (landing). */
export function previewHtml(d: Direction, brief: Brief, theme: "light" | "dark"): string {
  const lang = brief.lang ?? "en";
  const c = COPY[lang];
  const p = d.palette[theme];
  const m = motionOf(d);
  const rtl = lang === "ar";
  const kind = brief.kind ?? "landing";
  const headline = brief.headline ?? brief.product;
  const sub = brief.sub ?? `${brief.product}, for ${brief.audience}.`;
  const display = d.fonts.display.family, text = d.fonts.text.family, arabic = d.fonts.arabic?.family;
  const fam = (f: string) => (rtl && arabic ? `"${arabic}", "${f}", system-ui, sans-serif` : `"${f}"${arabic ? `, "${arabic}"` : ""}, system-ui, sans-serif`);
  const r = d.radius, rc = Math.max(2, Math.round(d.radius * 0.6));
  const sz = (step: number) => size(d, step);
  // Spacing: the same rhythm for every direction, snapped to its grid (4 or 8px).
  const sp = (n: number) => `${Math.max(d.spacing, Math.round((n * 4) / d.spacing) * d.spacing)}px`;
  const heavy = Math.max(...d.fonts.display.weights);
  const tracking = rtl ? "0" : "-0.015em";
  const outline = d.motif === "outline";
  const css = `
:root{--bg:${p.background};--surface:${p.surface};--text:${p.text};--muted:${p.muted};--primary:${p.primary};--on-primary:${p.primaryText};--accent:${p.accent};--border:${p.border};--ease:${m.ease}}
*{box-sizing:border-box}html{background:var(--bg);color:var(--text);font:400 ${d.scale.base}px/1.6 ${fam(text)};-webkit-font-smoothing:antialiased}body{margin:0}
h1,h2,h3{font-family:${fam(display)};line-height:1.12;margin:0;letter-spacing:${tracking};font-weight:${heavy}}
a{color:inherit}.wrap{max-width:74rem;margin-inline:auto;padding-inline:${sp(5)}}
.top{border-bottom:1px solid var(--border);background:var(--bg)}.top nav{display:flex;align-items:center;gap:${sp(6)};min-height:${sp(16)}}
.brand{font-family:${fam(display)};font-size:${sz(1)};font-weight:${heavy};margin-inline-end:auto;text-decoration:none}
.links{display:flex;gap:${sp(5)};color:var(--muted)}.links a{text-decoration:none;padding-block:${sp(2)}}.links a[aria-current]{color:var(--text);box-shadow:inset 0 -2px var(--primary)}
.avatar{inline-size:36px;block-size:36px;border-radius:50%;background:var(--accent);display:grid;place-items:center;color:${p.background};font-weight:700}
.btn{display:inline-flex;align-items:center;justify-content:center;gap:${sp(2)};min-height:44px;padding:0 ${sp(5)};border-radius:${rc}px;font-weight:600;text-decoration:none;border:1px solid transparent;cursor:pointer;font:inherit;font-weight:600;transition:transform ${m.fast}ms var(--ease),background-color ${m.fast}ms}
.btn.primary{background:var(--primary);color:var(--on-primary)}.btn.ghost{border-color:var(--border);color:var(--text);background:transparent}.btn:active{transform:scale(.97)}
.card{background:var(--surface);border:${outline ? "2px solid var(--text)" : "1px solid var(--border)"};border-radius:${r}px;padding:${sp(6)}${outline ? ";box-shadow:4px 4px 0 var(--text)" : ""}}
.muted{color:var(--muted)}.eyebrow{color:var(--muted);font-size:.95rem}
.chip{display:inline-flex;align-items:center;gap:6px;border-radius:999px;padding:2px 10px;font-size:.85rem;font-weight:600;border:1px solid var(--border)}
.chip.missed{color:${p.text};background:color-mix(in srgb,var(--accent) 35%,transparent);border-color:transparent}
.chip.shaky{background:color-mix(in srgb,var(--primary) 14%,transparent);border-color:transparent}
.bar,.rule{display:block;block-size:8px;border-radius:99px;background:color-mix(in srgb,var(--muted) 22%,transparent);overflow:hidden}.bar i,.rule i{display:block;block-size:100%;background:var(--primary);border-radius:inherit}
.rule{block-size:4px;border-radius:0}.rule i{background:var(--accent)}
.cells{display:grid;grid-template-columns:repeat(10,1fr);gap:3px}.cells i{block-size:12px;border-radius:3px;background:color-mix(in srgb,var(--muted) 20%,transparent)}.cells i.on{background:var(--primary)}
.dots{display:flex;gap:6px}.dots i{inline-size:12px;block-size:12px;border-radius:50%;border:2px solid var(--primary)}.dots i.on{background:var(--primary)}
.stamp{display:inline-grid;place-items:center;inline-size:56px;block-size:56px;border-radius:50%;border:2px dashed var(--primary);color:var(--primary);font-weight:700;transform:rotate(-8deg)}
.mark{background-image:linear-gradient(var(--accent),var(--accent));background-repeat:no-repeat;background-position:0 92%;background-size:100% .22em;padding-inline:2px}
@media (prefers-reduced-motion:no-preference){.rise{animation:rise ${m.slow}ms var(--ease) both}.rise:nth-child(2){animation-delay:${Math.round(m.base / 3)}ms}.rise:nth-child(3){animation-delay:${Math.round((m.base * 2) / 3)}ms}.mark{animation:mark ${m.slow}ms var(--ease) ${m.base}ms both}}
@keyframes rise{from{opacity:0;transform:translateY(${m.distance}px)}}@keyframes mark{from{background-size:0 .22em}}
footer.site{padding-block:${sp(8)};color:var(--muted);border-top:1px solid var(--border);margin-top:${sp(12)}}
input,select{font:inherit;color:var(--text);background:var(--bg);border:1px solid var(--border);border-radius:${rc}px;min-height:44px;padding:0 ${sp(3)}}
form{display:grid;gap:${sp(4)}}label{display:grid;gap:${sp(2)};font-weight:600}.check{display:flex;align-items:center;gap:${sp(3)};font-weight:400}.check input{min-height:auto;inline-size:20px;block-size:20px;accent-color:var(--primary)}
@media (max-width:767px){.links{display:none}}`;

  const head = `<!doctype html><html lang="${lang}" dir="${rtl ? "rtl" : "ltr"}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>${esc(d.name)}</title><link rel="stylesheet" href="${fontsLink(d)}">`;

  if (kind === "dashboard") {
    const layoutCss = {
      editorial: ".grid{display:grid;grid-template-columns:minmax(0,1.6fr) minmax(0,1fr);gap:" + sp(10) + "}",
      split: ".grid{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:" + sp(8) + "}",
      bento: ".grid{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:" + sp(4) + "}.grid>.main{grid-column:span 4}.grid>.side{grid-column:span 2}",
      stacked: ".grid{display:grid;grid-template-columns:minmax(0,1fr);gap:" + sp(8) + "}",
      asymmetric: ".grid{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1.45fr);gap:" + sp(8) + "}.grid>.side{order:-1}",
      centered: ".grid{display:grid;grid-template-columns:minmax(0,1fr);gap:" + sp(8) + ";max-width:46rem;margin-inline:auto}",
    }[d.layout];
    const items = c.items.map(([what, topic, status], i) => `<li class="rise item"><div><b>${i === 0 && d.motif === "underline" ? `<span class="mark">${esc(what!)}</span>` : esc(what!)}</b><div class="muted">${esc(topic!)}</div></div><span class="chip ${i === 0 ? "missed" : i === 1 ? "shaky" : ""}">${esc(status!)}</span></li>`).join("");
    const topics = c.topics.map(([name, v]) => `<article class="card topic rise"><h3>${esc(name as string)}</h3>${motif(d, v as number, c.mastery)}<p class="muted">${Math.round((v as number) * 100)}% ${esc(c.mastery)}</p></article>`).join("");
    return `${head}<style>${css}
${layoutCss}
.page{padding-block:${sp(10)}}.page h1{font-size:clamp(${sz(3)},5vw,${sz(4)});margin-bottom:${sp(2)}}
.items{list-style:none;margin:${sp(5)} 0 ${sp(6)};padding:0;display:grid;gap:${sp(3)}}.item{display:flex;align-items:center;justify-content:space-between;gap:${sp(4)};padding-block:${sp(3)};border-bottom:1px solid var(--border)}
.topics{display:grid;grid-template-columns:repeat(auto-fit,minmax(13rem,1fr));gap:${sp(4)};margin-top:${sp(4)}}.topic h3{font-size:${sz(1)};margin-bottom:${sp(4)}}.topic p{margin:${sp(3)} 0 0}
.stats{display:grid;grid-template-columns:repeat(3,1fr);gap:${sp(3)}}.stats b{display:block;font-family:${fam(display)};font-size:${sz(3)};line-height:1;font-weight:${heavy}}
.side{display:grid;gap:${sp(5)};align-content:start}.side h2{font-size:${sz(1)};margin-bottom:${sp(2)}}
@media (max-width:900px){.grid{grid-template-columns:minmax(0,1fr)}.grid>.main,.grid>.side{grid-column:auto}.grid>.side{order:0}}
</style></head><body>
<header class="top"><div class="wrap"><nav aria-label="Main"><a class="brand" href="#">${esc(brief.product)}</a><div class="links">${c.nav.map((n, i) => `<a href="#"${i === 0 ? ' aria-current="page"' : ""}>${esc(n)}</a>`).join("")}</div><span class="avatar" aria-hidden="true">L</span></nav></div></header>
<main class="wrap page"><div class="grid">
<section class="main card" aria-labelledby="t"><p class="eyebrow">${esc(c.today)}</p><h1 id="t">${esc(headline)}</h1><p class="muted">${esc(sub)}</p><ul class="items">${items}</ul><div style="display:flex;flex-wrap:wrap;gap:${sp(3)}"><a class="btn primary" href="#">${esc(c.start)}</a><a class="btn ghost" href="#">${esc(c.review)}</a></div></section>
<aside class="side"><div class="card stats">${c.stats.map(([n, l]) => `<div><b>${esc(n!)}</b><span class="muted">${esc(l!)}</span></div>`).join("")}</div>
<div class="card"><h2>${esc(c.session)}</h2><p class="muted" style="margin:0">${esc(c.sessionText)}</p></div>
<form class="card" onsubmit="return false"><label>${esc(c.form[0]!)}<input autocomplete="name"></label><label>${esc(c.form[2]!)}<select><option>Beginner</option><option>Junior</option></select></label><label class="check"><input type="checkbox" checked>${esc(c.form[3]!)}</label><button class="btn primary" type="submit">${esc(c.form[4]!)}</button></form></aside>
</div><section aria-label="${esc(c.nav[1]!)}" class="topics">${topics}</section></main>
<footer class="site"><div class="wrap">${esc(c.foot)}</div></footer></body></html>`;
  }

  const heroCols = { split: "1.05fr .95fr", editorial: "1fr", asymmetric: "1.2fr .8fr", bento: "1fr 1fr", stacked: "1fr", centered: "1fr" }[d.layout];
  return `${head}<style>${css}
.hero{display:grid;grid-template-columns:${heroCols};gap:${sp(10)};align-items:center;padding-block:${sp(16)}${d.layout === "centered" ? ";text-align:center;justify-items:center" : ""}}
.hero h1{font-size:clamp(${sz(3)},5.5vw,${sz(5)});max-width:18ch}.lead{font-size:${sz(1)};color:var(--muted);max-width:36rem;margin:${sp(5)} 0 ${sp(7)}}
.actions{display:flex;flex-wrap:wrap;gap:${sp(3)}}
.mock{display:grid;gap:${sp(3)}}.mock .card{padding:${sp(5)}}
.features{display:grid;grid-template-columns:repeat(auto-fit,minmax(15rem,1fr));gap:${sp(5)};padding-block:${sp(10)}}.features h3{font-size:${sz(2)};margin-bottom:${sp(2)}}.features p{margin:0;color:var(--muted)}
blockquote{margin:${sp(10)} 0 0;font-family:${fam(display)};font-size:${sz(3)};line-height:1.2;max-width:28ch}blockquote footer{font:400 ${d.scale.base}px ${fam(text)};color:var(--muted);margin-top:${sp(4)}}
@media (max-width:767px){.hero{grid-template-columns:1fr;padding-block:${sp(10)}}}
</style></head><body>
<header class="top"><div class="wrap"><nav aria-label="Main"><a class="brand" href="#">${esc(brief.product)}</a><div class="links">${c.landingNav.map((n) => `<a href="#">${esc(n)}</a>`).join("")}</div><a class="btn primary" href="#">${esc(c.cta)}</a></nav></div></header>
<main class="wrap">
<section class="hero"><div><h1>${d.motif === "underline" ? `<span class="mark">${esc(headline)}</span>` : esc(headline)}</h1><p class="lead">${esc(sub)}</p><div class="actions"><a class="btn primary" href="#">${esc(c.cta)}</a><a class="btn ghost" href="#">${esc(c.second)}</a></div></div>
<div class="mock" aria-label="${esc(brief.product)}">${c.topics.slice(0, 2).map(([name, v]) => `<div class="card rise"><b>${esc(name as string)}</b>${motif(d, v as number, c.mastery)}</div>`).join("")}<div class="card rise"><b>${esc(c.items[0]![0]!)}</b> <span class="chip missed">${esc(c.items[0]![2]!)}</span></div></div></section>
<section class="features">${c.features.map((f) => `<article class="card rise"><h3>${esc(f)}</h3><p>${esc(c.featureText)}</p></article>`).join("")}</section>
<blockquote>“${esc(c.quote)}”<footer>${esc(c.quoteBy)}</footer></blockquote>
</main><footer class="site"><div class="wrap">${esc(c.foot)}</div></footer></body></html>`;
}
