#!/usr/bin/env node
import { existsSync, mkdirSync, readFileSync } from "node:fs";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { audit } from "./audit.js";
import { closePage, launch, openVariant, type Variant, variantName } from "./browser.js";
import { ab, readTaste, reveal } from "./ab.js";
import { diff } from "./diff.js";
import { type Icon, iconFindings, icons } from "./icons.js";
import { choose, preview, readHistory } from "./direct.js";
import { inspire } from "./inspire.js";
import { budget, outline, parseUrl } from "./figma.js";
import { figmaSpec } from "./figma-spec.js";
import { indexProject } from "./index-project.js";
import { record } from "./record.js";
import { groupFindings, type Run, type Shot, writeReport } from "./report.js";
import { type Seen, see } from "./see.js";
import { DEFAULT_WIDTHS, type Finding, list, parseArgs, stamp, writeJson } from "./util.js";

const HERE = dirname(fileURLToPath(import.meta.url));
const VERSION = (JSON.parse(readFileSync(join(HERE, "..", "package.json"), "utf8")) as { version: string }).version;

const HELP = `lawha ${VERSION} - see and check web pages

  lawha check <url>   render at every width, screenshot, audit, measure, report
      --widths 360,390,768,1024,1280,1536   --themes light[,dark]   --dirs ltr[,rtl]
      --rtl-url <url>      page to use for RTL (default: the same page with dir="rtl")
      --expect-rtl         physical left/right CSS fails instead of being a note
      --against <dir>      compare with design images named <width>.png (Figma exports)
      --against-scale <n>  scale of those images (Figma 2x exports: 0.5)
      --no-audit --no-see  skip parts      --out <dir>   default .lawha/runs/<time>
      --no-record          do not share the result with mizan and itqan (status/lawha.json)
  lawha diff <actual.png> <expected.png> [--scale n] [--heatmap out.png]
  lawha index [project]  [--out <file>]   default <project>/.lawha/system.json
  lawha figma outline <figma link>           pages and top-level frames (1 call, cached by version)
  lawha figma spec <figma link> --frames <id,id,...> [--assets public/figma] [--refresh]
      fetch the frames (cached), merge them by width, write spec.md, theme.css, design images
      and the photos and icons; the frames are the same page at different widths
  lawha figma budget                          Figma calls made in the last minute and 30 days
  lawha direct preview <directions.json> [--kind landing|dashboard] --product <name> --audience <who> --feeling <word>
      [--headline <text>] [--sub <text>] [--lang en|ar|fr] [--out <dir>]
      check the directions (contrast, known AI looks, sameness) and render them; writes gallery.html
  lawha direct choose <directions.json> <id> [--theme-out src/lawha-theme.css]
      the chosen direction becomes the project's tokens (Tailwind @theme + shadcn variables)
  lawha direct history                        the directions chosen recently (kept to avoid repeats)
  lawha ab <url A> <url B> [--a-label <text>] [--b-label <text>] [--widths 390,1280] [--out <dir>]
      both versions side by side in a random order (pair-<width>.png); the key stays hidden in <dir>/.key/
  lawha ab reveal <dir> --pick left|right [--by judge|user] [--note <why>]
      which version won; a person's pick is kept as their taste (~/.claude/nexika/lawha/taste.json)
  lawha ab taste                              the picks kept so far
  lawha inspire <url> [--out <dir>]           a live site's design DNA: fonts, colours, scale, spacing,
      shapes, sections, motion (incl. GSAP, Lenis, Framer Motion, Three.js) and assets; dna.md + screenshots
  (Figma needs FIGMA_TOKEN: a personal access token with read-only file content)
  lawha version

Prints JSON on standard output: for check, the summary and the report path.`;

async function check(url: string, a: ReturnType<typeof parseArgs>): Promise<number> {
  const widths = list(a.widths, DEFAULT_WIDTHS.map(String)).map(Number).filter((n) => n >= 200 && n <= 4000);
  const themes = list(a.themes, ["light"]).filter((t): t is "light" | "dark" => t === "light" || t === "dark");
  const expectRtl = a["expect-rtl"] === true;
  const dirs = list(a.dirs, expectRtl || a["rtl-url"] ? ["ltr", "rtl"] : ["ltr"]).filter((d): d is "ltr" | "rtl" => d === "ltr" || d === "rtl");
  const out = resolve(typeof a.out === "string" ? a.out : join(".lawha", "runs", stamp()));
  mkdirSync(join(out, "shots"), { recursive: true });

  const variants: Variant[] = [];
  for (const theme of themes) for (const dir of dirs) for (const width of widths) variants.push({ width, theme, dir, motion: "full" });
  // One reduced-motion pass on a phone is enough to see what keeps moving.
  variants.push({ width: widths.includes(390) ? 390 : widths[0]!, theme: themes[0]!, dir: "ltr", motion: "reduce" });

  const run: Run = { url, when: new Date().toISOString(), version: VERSION, shots: [], findings: [], seen: [], diffs: [], summary: { fail: 0, warn: 0, info: 0, widths, verdict: "pass" } };
  const browser = await launch();
  // Icons per width and theme, in each direction, to compare after all renders (rtl.icon-*).
  const iconsBy = new Map<string, { ltr?: Icon[]; rtl?: Icon[] }>();
  try {
    for (const v of variants) {
      const name = variantName(v);
      const page = await openVariant(browser, { url, rtlUrl: typeof a["rtl-url"] === "string" ? a["rtl-url"] : undefined }, v);
      try {
        const file = join(out, "shots", `${name}.png`);
        await page.screenshot({ path: file, fullPage: true, animations: "disabled" });
        const height = await page.evaluate(() => document.documentElement.scrollHeight);
        run.shots.push({ variant: name, width: v.width, theme: v.theme, dir: v.dir, motion: v.motion, file: relative(out, file), height } satisfies Shot);
        if (a["no-audit"] !== true) run.findings.push(...(await audit(page, v, { expectRtl })).findings);
        if (a["no-audit"] !== true && v.motion === "full" && dirs.length > 1) {
          const key = `${v.width}|${v.theme}`;
          iconsBy.set(key, { ...iconsBy.get(key), [v.dir]: await icons(page) });
        }
        if (a["no-see"] !== true && v.motion === "full" && v.theme === themes[0]) run.seen.push((await see(page, v, name)) as Seen);
      } catch (error) {
        run.findings.push({ check: "engine.error", severity: "fail", message: `Could not check ${name}: ${(error as Error).message}`, width: v.width, theme: v.theme, dir: v.dir, motion: v.motion } satisfies Finding);
      } finally {
        await closePage(page);
      }
    }
  } finally {
    await browser.close();
  }
  for (const [key, pair] of iconsBy) {
    if (!pair.ltr || !pair.rtl) continue;
    const [width, theme] = key.split("|") as [string, "light" | "dark"];
    run.findings.push(...iconFindings(pair.ltr, pair.rtl, { width: Number(width), theme, motion: "full" }, expectRtl));
  }

  if (typeof a.against === "string") {
    const scale = typeof a["against-scale"] === "string" ? Number(a["against-scale"]) : 1;
    for (const shot of run.shots.filter((s) => s.theme === themes[0] && s.dir === "ltr" && s.motion === "full")) {
      const expected = resolve(a.against, `${shot.width}.png`);
      if (!existsSync(expected)) continue;
      const heat = join(out, "shots", `${shot.variant}.diff.png`);
      const result = diff(join(out, shot.file), expected, { heatmap: heat, expectedScale: scale });
      run.diffs.push({ ...result, variant: shot.variant, expected: relative(out, expected), actual: shot.file, heatmap: relative(out, heat) });
      const looks = result.aligned.match;
      if (looks < 0.95) {
        run.findings.push({ check: "design.match", severity: looks < 0.85 ? "fail" : "warn", message: `Looks ${(looks * 100).toFixed(1)}% like the design (content aligned; ${(result.match * 100).toFixed(1)}% position for position).`, width: shot.width, theme: shot.theme, dir: shot.dir, motion: shot.motion, box: result.regions[0] });
      }
      for (const s of result.aligned.shifts.slice(0, 6)) {
        run.findings.push({ check: "design.height-drift", severity: "warn", message: `From y=${s.designY}px in the design, the page sits ${Math.abs(s.dy)}px ${s.dy > 0 ? "lower" : "higher"} (a section above is ${s.dy > 0 ? "taller" : "shorter"} than designed).`, width: shot.width, theme: shot.theme, dir: shot.dir, motion: shot.motion, box: { x: 0, y: s.builtY, w: shot.width, h: 4 } });
      }
    }
  }

  const problems = groupFindings(run.findings);
  for (const p of problems) run.summary[p.severity]++;
  run.summary.verdict = run.summary.fail ? "fail" : "pass";
  writeJson(join(out, "run.json"), run);
  writeReport(join(out, "report.html"), run);
  // Tell the other Nexika plugins (mizan's band, itqan's proof); --no-record for throwaway checks.
  let recorded: string | null = null;
  if (a["no-record"] !== true) {
    try {
      recorded = record(process.cwd(), {
        url, widths, themes, dirs, verdict: run.summary.verdict,
        counts: { fail: run.summary.fail, warn: run.summary.warn, info: run.summary.info },
        problems, report: join(out, "report.html"), run: join(out, "run.json"),
      });
    } catch {
      recorded = null; // the check itself succeeded; sharing it is best effort
    }
  }

  const top = problems.filter((p) => p.severity !== "info").slice(0, 15).map((p) => `[${p.severity}] ${p.message} (${p.check} at ${p.where.join(", ")})`);
  process.stdout.write(JSON.stringify({ verdict: run.summary.verdict, fail: run.summary.fail, warn: run.summary.warn, info: run.summary.info, report: join(out, "report.html"), run: join(out, "run.json"), recorded, top }, null, 2) + "\n");
  return 0;
}

async function main(argv: string[]): Promise<number> {
  const [command, ...rest] = argv;
  const a = parseArgs(rest, ["expect-rtl", "no-audit", "no-see", "no-record", "refresh"]);
  switch (command) {
    case "check": {
      const url = a._[0];
      if (!url) break;
      return check(url, a);
    }
    case "diff": {
      const [actual, expected] = a._;
      if (!actual || !expected) break;
      const result = diff(actual, expected, { heatmap: typeof a.heatmap === "string" ? a.heatmap : undefined, expectedScale: typeof a.scale === "string" ? Number(a.scale) : 1 });
      process.stdout.write(JSON.stringify(result, null, 2) + "\n");
      return 0;
    }
    case "index": {
      const root = resolve(a._[0] ?? ".");
      const target = resolve(typeof a.out === "string" ? a.out : join(root, ".lawha", "system.json"));
      const index = indexProject(root);
      writeJson(target, index);
      process.stdout.write(JSON.stringify({ written: target, tokens: index.tokens.length, components: index.components.length, shadcn: index.shadcn.components.length, routes: index.routes.length, drift: index.drift.length, stack: index.stack }, null, 2) + "\n");
      return 0;
    }
    case "figma": {
      const [sub, link] = a._;
      if (sub === "budget") {
        process.stdout.write(JSON.stringify(budget(), null, 2) + "\n");
        return 0;
      }
      if (!link) break;
      const ref = parseUrl(link);
      const root = process.cwd();
      if (sub === "outline") {
        const o = await outline(root, ref, a.refresh === true);
        process.stdout.write(JSON.stringify({ ...o, selected: ref.node, budget: budget() }, null, 2) + "\n");
        return 0;
      }
      if (sub === "spec") {
        const ids = list(a.frames, ref.node ? [ref.node] : []);
        const result = await figmaSpec(root, ref, ids, { assets: typeof a.assets === "string" ? a.assets : join("public", "figma"), refresh: a.refresh === true, title: typeof a.title === "string" ? a.title : undefined });
        process.stdout.write(JSON.stringify({ ...result, budget: budget() }, null, 2) + "\n");
        return 0;
      }
      break;
    }
    case "direct": {
      const [sub, file, id] = a._;
      if (sub === "history") {
        process.stdout.write(JSON.stringify(readHistory().slice(-10), null, 2) + "\n");
        return 0;
      }
      if (sub === "preview" && file) {
        const str = (k: string) => (typeof a[k] === "string" ? (a[k] as string) : undefined);
        const brief = { kind: (str("kind") ?? "landing") as "landing" | "dashboard", product: str("product") ?? "Your product", audience: str("audience") ?? "the people who use it", feeling: str("feeling") ?? "clear", headline: str("headline"), sub: str("sub"), lang: (str("lang") ?? "en") as "en" | "ar" | "fr" };
        const out = resolve(str("out") ?? join(".lawha", "directions", stamp()));
        const result = await preview(file, brief, out);
        process.stdout.write(JSON.stringify({ gallery: result.gallery, fail: result.problems.filter((p) => p.severity === "fail").length, problems: result.problems, previews: result.previews.map((p) => p.name) }, null, 2) + "\n");
        return 0;
      }
      if (sub === "choose" && file && id) {
        const result = choose(file, id, process.cwd(), typeof a["theme-out"] === "string" ? a["theme-out"] : join("src", "lawha-theme.css"));
        process.stdout.write(JSON.stringify(result, null, 2) + "\n");
        return 0;
      }
      break;
    }
    case "ab": {
      const [first, second] = a._;
      if (first === "taste") {
        process.stdout.write(JSON.stringify(readTaste().slice(-20), null, 2) + "\n");
        return 0;
      }
      if (first === "reveal" && second) {
        const pick = a.pick === "left" || a.pick === "right" ? a.pick : null;
        if (!pick) break;
        const result = reveal(resolve(second), pick, a.by === "user" ? "user" : "judge", typeof a.note === "string" ? a.note : "", process.cwd());
        process.stdout.write(JSON.stringify(result, null, 2) + "\n");
        return 0;
      }
      if (first && second) {
        const widths = list(a.widths, ["390", "1280"]).map(Number);
        const out = resolve(typeof a.out === "string" ? a.out : join(".lawha", "ab", stamp()));
        const result = await ab({ url: first, label: typeof a["a-label"] === "string" ? a["a-label"] : "current" }, { url: second, label: typeof a["b-label"] === "string" ? a["b-label"] : "candidate" }, widths, out);
        process.stdout.write(JSON.stringify({ ...result, note: "Give the judge only the pair images, never the folder's .key/ (it says which is which)." }, null, 2) + "\n");
        return 0;
      }
      break;
    }
    case "inspire": {
      const url = a._[0];
      if (!url) break;
      const host = (() => { try { return new URL(url).hostname.replace(/^www\./, ""); } catch { return "page"; } })();
      const out = resolve(typeof a.out === "string" ? a.out : join(".lawha", "inspire", `${host}-${stamp()}`));
      const result = await inspire(url, out);
      process.stdout.write(JSON.stringify({ dna: result.json, report: result.md, fonts: result.dna.fonts.map((f) => f.family), libraries: result.dna.motion.libraries, sections: result.dna.sections.length }, null, 2) + "\n");
      return 0;
    }
    case "version":
      process.stdout.write(`${VERSION}\n`);
      return 0;
  }
  process.stdout.write(HELP + "\n");
  return command && command !== "help" && command !== "--help" ? 2 : 0;
}

main(process.argv.slice(2)).then(
  (code) => process.exit(code),
  (error: Error) => {
    process.stderr.write(`lawha: ${error.message}\n`);
    process.exit(1);
  },
);
