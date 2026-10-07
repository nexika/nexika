import { copyFileSync, existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { join, relative, resolve } from "node:path";
import { type FigmaRef, cacheDir, fetchFrames, svgExports } from "./figma.js";
import { extractMotion, layerNames, type MotionStep, motionMarkdown } from "./figma-motion.js";
import { merge, specMarkdown } from "./merge.js";
import { normalize, type Spec, type StyleIndex, tokens, typeStyles } from "./normalize.js";

/** The image type from its first bytes, for a sensible file extension. */
function extension(path: string): string {
  const b = readFileSync(path).subarray(0, 12);
  if (b[0] === 0x89 && b[1] === 0x50) return "png";
  if (b[0] === 0xff && b[1] === 0xd8) return "jpg";
  if (b.subarray(0, 4).toString() === "RIFF" && b.subarray(8, 12).toString() === "WEBP") return "webp";
  if (b.subarray(0, 3).toString() === "GIF") return "gif";
  return "img";
}

function vectors(s: Spec, out: Spec[] = []): Spec[] {
  if (s.kind === "vector" && s.width.px >= 8) out.push(s);
  else s.children.forEach((c) => vectors(c, out));
  return out;
}

function slug(text: string): string {
  return text.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 40) || "item";
}

export interface SpecResult {
  dir: string;
  spec: string;
  json: string;
  tokensCss: string;
  designs: string; // folder with <width>.png, for lawha check --against
  assets: { photos: string[]; icons: string[] };
  breakpoints: { name: string; width: number }[];
  motion: number; // prototype interactions found
  calls: number;
  notes: number;
  restructured: number;
}

/**
 * Fetch the frames (cached), normalise them, merge the breakpoints and write what Claude builds from:
 *   spec.md        the merged, mobile-first spec (with design-file habits read as intent)
 *   spec.json      the same, as data
 *   theme.css      Tailwind @theme tokens: colours from the named styles, fonts in use
 *   designs/<w>.png  each frame's render, for `lawha check --against`
 *   <assets>/      the photos (real files, not crops) and the icons as SVG
 */
export async function figmaSpec(root: string, ref: FigmaRef, ids: string[], opts: { assets: string; title?: string; refresh?: boolean }): Promise<SpecResult> {
  const fetched = await fetchFrames(root, ref, ids, { refresh: opts.refresh });
  const data = JSON.parse(readFileSync(fetched.nodes, "utf8")) as { name?: string; nodes: Record<string, { document: Parameters<typeof normalize>[0]; styles?: StyleIndex }> };
  const frames = ids.map((id) => {
    const node = data.nodes[id];
    if (!node) throw new Error(`frame ${id} is not in the file`);
    const spec = normalize(node.document, node.styles ?? {});
    if (!spec) throw new Error(`frame ${id} is hidden`);
    return { id, width: spec.width.px, spec };
  });
  const merged = merge(frames.map((f) => ({ width: f.width, spec: f.spec })));
  const out = join(fetched.dir, "spec");
  mkdirSync(join(out, "designs"), { recursive: true });

  // Designs by width, for the check.
  for (const f of frames) {
    const png = fetched.images[f.id];
    if (png) copyFileSync(png, join(out, "designs", `${f.width}.png`));
  }

  // Photos: copied into the project's assets folder under readable names.
  const assetsDir = resolve(root, opts.assets);
  mkdirSync(assetsDir, { recursive: true });
  const photoNames: Record<string, string> = {};
  const names = new Map<string, string>();
  const nameFills = (s: Spec) => {
    for (const p of s.fills) if (p.kind === "image" && p.imageRef && !names.has(p.imageRef)) names.set(p.imageRef, slug(s.name === "image" ? `photo-${names.size + 1}` : s.name));
    s.children.forEach(nameFills);
  };
  frames.forEach((f) => nameFills(f.spec));
  for (const [ref2, file] of Object.entries(fetched.fills)) {
    // Designers reuse layer names ("Rectangle 6" holding three different photos): number repeats,
    // never overwrite.
    const base = names.get(ref2) ?? ref2.slice(0, 8);
    let name = `${base}.${extension(file)}`;
    for (let n = 2; Object.values(photoNames).some((p) => p.endsWith(`/${name}`)); n++) name = `${base}-${n}.${extension(file)}`;
    copyFileSync(file, join(assetsDir, name));
    photoNames[ref2] = relative(root, join(assetsDir, name));
  }

  // Icons: one SVG export call for every icon in every frame (cached). The same icon in several frames
  // (same name and size) is exported once; icons that only exist on the phone or tablet (a menu
  // button, a fold arrow) are included.
  const byWidth = [...frames].sort((a, b) => b.width - a.width);
  const iconKeys = new Set<string>();
  const icons: Spec[] = [];
  for (const f of byWidth) for (const v of vectors(f.spec)) {
    const key = `${v.name}|${Math.round(v.width.px)}x${Math.round(v.height.px)}`;
    if (!iconKeys.has(key)) { iconKeys.add(key); icons.push(v); }
  }
  const svgs = await svgExports(root, ref, fetched.version, icons.map((i) => i.id));
  const iconNames: Record<string, string> = {};
  for (const icon of icons) {
    const file = svgs.files[icon.id];
    if (!file) continue;
    const base = slug(icon.name.replace(/^[a-z]+:/, ""));
    let name = `${base}.svg`;
    for (let n = 2; Object.values(iconNames).some((p) => p.endsWith(`/${name}`)); n++) name = `${base}-${n}.svg`;
    copyFileSync(file, join(assetsDir, name));
    iconNames[icon.id] = relative(root, join(assetsDir, name));
  }

  // Tokens.
  const t = tokens(frames.map((f) => f.spec));
  const type = typeStyles(frames.map((f) => f.spec));
  const families = [...new Set(type.map((s) => s.family))];
  // The leading most text uses (Figma "auto" gives each font its natural one): the theme's default,
  // so Tailwind's tighter text-size line heights do not shrink every line.
  const ratios = new Map<number, number>();
  for (const s of type) if (s.lineHeight) {
    const r = Math.round((s.lineHeight / s.size) * 20) / 20;
    ratios.set(r, (ratios.get(r) ?? 0) + s.uses);
  }
  const [leading] = [...ratios.entries()].sort((a, b) => b[1] - a[1])[0] ?? [null];
  const css = [
    "/* lawha: design tokens from Figma. Colours come from the file's named styles. */",
    "@theme {",
    ...Object.entries(t.colors).map(([name, hex]) => `  --color-${name}: ${hex};`),
    ...families.map((f) => `  --font-${slug(f)}: "${f}", ui-sans-serif, system-ui, sans-serif;`),
    ...(leading ? [`  /* Most text in the design uses ${leading}× line height. */`, ...["xs", "sm", "base", "lg", "xl", "2xl", "3xl", "4xl", "5xl", "6xl"].map((k) => `  --text-${k}--line-height: ${leading};`)] : []),
    "}",
    ...(leading ? ["", `html {`, `  line-height: ${leading};`, `}`] : []),
    "",
    "/* Figma's vertical trim (\"trim cap\" in the spec): the text box is cut to the capitals' height.",
    "   Chromium 133+ and Safari 18.2+; elsewhere the text keeps its normal line box. */",
    "@utility trim-cap {",
    "  text-box: trim-both cap alphabetic;",
    "}",
    "",
    "@utility trim-none {",
    "  text-box: normal;",
    "}",
    "",
  ].join("\n");
  writeFileSync(join(out, "theme.css"), css);

  // Prototype motion: interactions on every fetched layer, with destinations named and, when a
  // destination was fetched too (pass its id with the frames), what changes between the two.
  const layers = new Map<string, string>();
  for (const n of Object.values(data.nodes)) if (n?.document) layerNames(n.document as never, layers);
  const byId = new Map<string, Spec>();
  const index = (s: Spec) => { byId.set(s.id, s); s.children.forEach(index); };
  for (const n of Object.values(data.nodes)) { const s = n?.document ? normalize(n.document, n.styles ?? {}) : null; if (s) index(s); }
  const motion: MotionStep[] = [];
  const seen = new Set<string>();
  for (const id of ids) for (const step of extractMotion(data.nodes[id]!.document as never, layers, byId)) {
    const key = `${step.layer}|${step.trigger}|${step.action}|${step.transition.figma}`;
    if (!seen.has(key)) { seen.add(key); motion.push(step); } // the same button in every breakpoint frame
  }
  const unresolved = new Set(motion.filter((m) => m.destination && !byId.has(m.destination.id) && !m.action.startsWith("goes to")).map((m) => m.destination!.id)).size;

  let md = specMarkdown(merged, opts.title ?? data.name ?? "Figma design");
  md += motionMarkdown(motion, unresolved);
  md += "\n## Tokens\n\n" + Object.entries(t.colors).map(([n, h]) => `- \`--color-${n}\` ${h}`).join("\n") + "\n";
  if (t.untokened.length) md += "\nColours used without a named style: " + t.untokened.slice(0, 12).map((c) => `${c.hex} (${c.uses}×)`).join(", ") + "\n";
  md += "\n## Type styles (largest first)\n\n" + type.map((s) => `- ${s.family} ${s.weight}, ${s.size}px${s.lineHeight ? `/${s.lineHeight}px` : ""}${s.letterSpacing ? `, tracking ${s.letterSpacing}px` : ""}${s.transform !== "none" ? `, ${s.transform}case` : ""} · ${s.uses}× · e.g. "${s.sample}"`).join("\n") + "\n";
  md += `\nFonts to load: ${families.join(", ")}.\n`;
  md += "\n`trim cap` = Figma's vertical trim: the text box is only as tall as the capital letters, so the layout around it is tighter than the line height. Use the `trim-cap` utility from theme.css (CSS `text-box: trim-both cap alphabetic`).\n";
  md += "\n## Assets\n\n" + Object.entries(photoNames).map(([r, p]) => `- photo \`${r}\` → ${p}`).join("\n") + "\n" + Object.entries(iconNames).map(([id, p]) => `- icon ${id} → ${p}`).join("\n") + "\n";
  md += `\nDesign images for the check: ${relative(root, join(out, "designs"))}/<width>.png (${frames.map((f) => f.width).join(", ")}).\n`;
  const specPath = join(out, "spec.md");
  writeFileSync(specPath, md);
  const jsonPath = join(out, "spec.json");
  writeFileSync(jsonPath, JSON.stringify({ breakpoints: merged.breakpoints, root: merged.root, tokens: t, type, photos: photoNames, icons: iconNames, motion }, null, 1));

  const countNotes = (m: typeof merged.root): number => m.notes.length + m.children.reduce((a, c) => a + countNotes(c), 0);
  const countRe = (m: typeof merged.root): number => (m.restructured ? 1 : 0) + m.children.reduce((a, c) => a + countRe(c), 0);
  return {
    dir: out, spec: specPath, json: jsonPath, tokensCss: join(out, "theme.css"), designs: join(out, "designs"),
    assets: { photos: Object.values(photoNames), icons: Object.values(iconNames) },
    breakpoints: merged.breakpoints, motion: motion.length, calls: fetched.calls + svgs.calls, notes: countNotes(merged.root), restructured: countRe(merged.root),
  };
}

export { cacheDir, existsSync };
