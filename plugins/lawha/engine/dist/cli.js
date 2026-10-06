#!/usr/bin/env node
import { existsSync, mkdirSync, readFileSync } from "node:fs";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { audit } from "./audit.js";
import { closePage, launch, openVariant, variantName } from "./browser.js";
import { diff } from "./diff.js";
import { indexProject } from "./index-project.js";
import { groupFindings, writeReport } from "./report.js";
import { see } from "./see.js";
import { DEFAULT_WIDTHS, list, parseArgs, stamp, writeJson } from "./util.js";
const HERE = dirname(fileURLToPath(import.meta.url));
const VERSION = JSON.parse(readFileSync(join(HERE, "..", "package.json"), "utf8")).version;
const HELP = `lawha ${VERSION} - see and check web pages

  lawha check <url>   render at every width, screenshot, audit, measure, report
      --widths 360,390,768,1024,1280,1536   --themes light[,dark]   --dirs ltr[,rtl]
      --rtl-url <url>      page to use for RTL (default: the same page with dir="rtl")
      --expect-rtl         physical left/right CSS fails instead of being a note
      --against <dir>      compare with design images named <width>.png (Figma exports)
      --against-scale <n>  scale of those images (Figma 2x exports: 0.5)
      --no-audit --no-see  skip parts      --out <dir>   default .lawha/runs/<time>
  lawha diff <actual.png> <expected.png> [--scale n] [--heatmap out.png]
  lawha index [project]  [--out <file>]   default <project>/.lawha/system.json
  lawha version

Prints JSON on standard output: for check, the summary and the report path.`;
async function check(url, a) {
    const widths = list(a.widths, DEFAULT_WIDTHS.map(String)).map(Number).filter((n) => n >= 200 && n <= 4000);
    const themes = list(a.themes, ["light"]).filter((t) => t === "light" || t === "dark");
    const expectRtl = a["expect-rtl"] === true;
    const dirs = list(a.dirs, expectRtl || a["rtl-url"] ? ["ltr", "rtl"] : ["ltr"]).filter((d) => d === "ltr" || d === "rtl");
    const out = resolve(typeof a.out === "string" ? a.out : join(".lawha", "runs", stamp()));
    mkdirSync(join(out, "shots"), { recursive: true });
    const variants = [];
    for (const theme of themes)
        for (const dir of dirs)
            for (const width of widths)
                variants.push({ width, theme, dir, motion: "full" });
    // One reduced-motion pass on a phone is enough to see what keeps moving.
    variants.push({ width: widths.includes(390) ? 390 : widths[0], theme: themes[0], dir: "ltr", motion: "reduce" });
    const run = { url, when: new Date().toISOString(), version: VERSION, shots: [], findings: [], seen: [], diffs: [], summary: { fail: 0, warn: 0, info: 0, widths, verdict: "pass" } };
    const browser = await launch();
    try {
        for (const v of variants) {
            const name = variantName(v);
            const page = await openVariant(browser, { url, rtlUrl: typeof a["rtl-url"] === "string" ? a["rtl-url"] : undefined }, v);
            try {
                const file = join(out, "shots", `${name}.png`);
                await page.screenshot({ path: file, fullPage: true, animations: "disabled" });
                const height = await page.evaluate(() => document.documentElement.scrollHeight);
                run.shots.push({ variant: name, width: v.width, theme: v.theme, dir: v.dir, motion: v.motion, file: relative(out, file), height });
                if (a["no-audit"] !== true)
                    run.findings.push(...(await audit(page, v, { expectRtl })).findings);
                if (a["no-see"] !== true && v.motion === "full" && v.theme === themes[0])
                    run.seen.push((await see(page, v, name)));
            }
            catch (error) {
                run.findings.push({ check: "engine.error", severity: "fail", message: `Could not check ${name}: ${error.message}`, width: v.width, theme: v.theme, dir: v.dir, motion: v.motion });
            }
            finally {
                await closePage(page);
            }
        }
    }
    finally {
        await browser.close();
    }
    if (typeof a.against === "string") {
        const scale = typeof a["against-scale"] === "string" ? Number(a["against-scale"]) : 1;
        for (const shot of run.shots.filter((s) => s.theme === themes[0] && s.dir === "ltr" && s.motion === "full")) {
            const expected = resolve(a.against, `${shot.width}.png`);
            if (!existsSync(expected))
                continue;
            const heat = join(out, "shots", `${shot.variant}.diff.png`);
            const result = diff(join(out, shot.file), expected, { heatmap: heat, expectedScale: scale });
            run.diffs.push({ ...result, variant: shot.variant, expected: relative(out, expected), actual: shot.file, heatmap: relative(out, heat) });
            if (result.match < 0.95) {
                run.findings.push({ check: "design.match", severity: result.match < 0.85 ? "fail" : "warn", message: `Matches the design at ${(result.match * 100).toFixed(1)}%; ${result.regions.length} region(s) differ.`, width: shot.width, theme: shot.theme, dir: shot.dir, motion: shot.motion, box: result.regions[0] });
            }
        }
    }
    const problems = groupFindings(run.findings);
    for (const p of problems)
        run.summary[p.severity]++;
    run.summary.verdict = run.summary.fail ? "fail" : "pass";
    writeJson(join(out, "run.json"), run);
    writeReport(join(out, "report.html"), run);
    const top = problems.filter((p) => p.severity !== "info").slice(0, 15).map((p) => `[${p.severity}] ${p.message} (${p.check} at ${p.where.join(", ")})`);
    process.stdout.write(JSON.stringify({ verdict: run.summary.verdict, fail: run.summary.fail, warn: run.summary.warn, info: run.summary.info, report: join(out, "report.html"), run: join(out, "run.json"), top }, null, 2) + "\n");
    return 0;
}
async function main(argv) {
    const [command, ...rest] = argv;
    const a = parseArgs(rest, ["expect-rtl", "no-audit", "no-see"]);
    switch (command) {
        case "check": {
            const url = a._[0];
            if (!url)
                break;
            return check(url, a);
        }
        case "diff": {
            const [actual, expected] = a._;
            if (!actual || !expected)
                break;
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
        case "version":
            process.stdout.write(`${VERSION}\n`);
            return 0;
    }
    process.stdout.write(HELP + "\n");
    return command && command !== "help" && command !== "--help" ? 2 : 0;
}
main(process.argv.slice(2)).then((code) => process.exit(code), (error) => {
    process.stderr.write(`lawha: ${error.message}\n`);
    process.exit(1);
});
