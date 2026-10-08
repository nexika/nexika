import { writeFileSync } from "node:fs";
import type { DiffResult } from "./diff.js";
import type { Seen } from "./see.js";
import type { Finding } from "./util.js";

export interface Shot {
  variant: string;
  width: number;
  theme: string;
  dir: string;
  motion: string;
  file: string; // relative to the report
  height: number;
}

export interface Run {
  url: string;
  when: string;
  version: string;
  shots: Shot[];
  findings: Finding[];
  seen: Seen[];
  diffs: (DiffResult & { variant: string; expected: string; actual: string })[];
  summary: { fail: number; warn: number; info: number; widths: number[]; verdict: "pass" | "fail"; concurrency?: number };
}

const esc = (s: unknown) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]!);

const CSS = `
:root{--bg:#f6f5f2;--panel:#fff;--ink:#16181d;--muted:#5d6370;--line:#e4e2dc;--fail:#c2362b;--warn:#965a00;--info:#3c6db0;--ok:#21794b;--accent:#2b2fd6}
@media (prefers-color-scheme:dark){:root{--bg:#121316;--panel:#1b1d22;--ink:#eceef2;--muted:#9aa1ad;--line:#2b2e35;--fail:#ff6b5e;--warn:#f0a63a;--info:#79a8ff;--ok:#4cc38a;--accent:#8f93ff}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.55 ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif}
header{padding:40px 24px 24px;max-width:1200px;margin:0 auto}h1{font-size:clamp(22px,5vw,30px);line-height:1.2;margin:0 0 4px;letter-spacing:-.01em;overflow-wrap:anywhere}.url{margin:0 0 16px;font-size:13px;overflow-wrap:anywhere}
.table{overflow-x:auto;border-radius:12px}h2{font-size:19px;margin:40px 0 12px}h3{font-size:15px;margin:20px 0 8px}
.muted{color:var(--muted)}main{max-width:1200px;margin:0 auto;padding:0 24px 64px}
.verdict{display:inline-flex;gap:8px;align-items:center;font-weight:650;padding:6px 12px;border-radius:999px;border:1px solid var(--line);background:var(--panel)}
.dot{width:10px;height:10px;border-radius:50%}.pass .dot{background:var(--ok)}.fail .dot{background:var(--fail)}
.counts{display:flex;gap:12px;flex-wrap:wrap;margin-top:16px}.count{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:12px 16px;min-width:120px}
.count b{display:block;font-size:24px;font-variant-numeric:tabular-nums}.count.fail b{color:var(--fail)}.count.warn b{color:var(--warn)}.count.info b{color:var(--info)}
.tabs{display:flex;gap:8px;flex-wrap:wrap;margin:8px 0 16px}.tabs a{padding:6px 12px;border-radius:999px;border:1px solid var(--line);color:inherit;text-decoration:none;background:var(--panel);font-variant-numeric:tabular-nums}
.shots:focus-visible,.table:focus-visible{outline:2px solid var(--accent);outline-offset:4px}.shots{display:flex;gap:20px;overflow-x:auto;padding-bottom:12px;align-items:flex-start}
figure{margin:0;flex:none}figcaption{font-size:13px;color:var(--muted);margin-bottom:6px;font-variant-numeric:tabular-nums}
.frame{position:relative;border:1px solid var(--line);border-radius:10px;overflow:hidden;background:var(--panel)}.frame img{display:block;width:100%;height:auto}
.mark{position:absolute;border:2px solid var(--fail);border-radius:4px;background:color-mix(in srgb,var(--fail) 12%,transparent)}.mark.warn{border-color:var(--warn);background:color-mix(in srgb,var(--warn) 12%,transparent)}
table{width:100%;border-collapse:collapse;background:var(--panel);border:1px solid var(--line);border-radius:12px;overflow:hidden}th,td{text-align:start;padding:9px 12px;border-bottom:1px solid var(--line);vertical-align:top;font-size:14px}th{font-weight:600;color:var(--muted);font-size:12px;text-transform:none}
.sev{font-weight:650}.sev.fail{color:var(--fail)}.sev.warn{color:var(--warn)}.sev.info{color:var(--info)}code{font:12.5px ui-monospace,SFMono-Regular,Menlo,monospace;overflow-wrap:anywhere}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:16px}.card{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:16px}
.swatches{display:flex;flex-wrap:wrap;gap:8px}.sw{display:flex;align-items:center;gap:8px;font-size:13px}.sw i{width:22px;height:22px;border-radius:6px;border:1px solid var(--line);display:inline-block}
.bar{height:8px;border-radius:4px;background:var(--line);overflow:hidden}.bar span{display:block;height:100%;background:var(--accent)}
@media (prefers-reduced-motion:no-preference){.count,.card,figure{animation:rise .5s cubic-bezier(.2,.7,.2,1) both}@keyframes rise{from{opacity:0;transform:translateY(6px)}}}
`;

function marks(run: Run, shot: Shot, scale: number): string {
  return run.findings
    .filter((f) => f.box && f.width === shot.width && f.theme === shot.theme && f.dir === shot.dir && f.motion === shot.motion && f.severity !== "info")
    .slice(0, 40)
    .map((f) => {
      const b = f.box!;
      return `<span class="mark ${f.severity}" title="${esc(f.message)}" style="inset-inline-start:${b.x * scale}px;top:${b.y * scale}px;width:${Math.max(6, b.w * scale)}px;height:${Math.max(6, b.h * scale)}px"></span>`;
    })
    .join("");
}

function shotsSection(run: Run): string {
  const groups = new Map<string, Shot[]>();
  for (const s of run.shots) {
    const key = `${s.theme} · ${s.dir.toUpperCase()}${s.motion === "reduce" ? " · reduced motion" : ""}`;
    groups.set(key, [...(groups.get(key) ?? []), s]);
  }
  return [...groups.entries()]
    .map(([key, shots]) => {
      const figures = shots
        .sort((a, b) => a.width - b.width)
        .map((s) => {
          const shown = Math.min(s.width, s.width <= 767 ? 300 : 420);
          const scale = shown / s.width;
          return `<figure style="width:${shown}px"><figcaption>${s.width}px</figcaption><div class="frame"><img loading="lazy" src="${esc(s.file)}" alt="${esc(`Screenshot at ${s.width}px, ${key}`)}">${marks(run, s, scale)}</div></figure>`;
        })
        .join("");
      return `<h3>${esc(key)}</h3><div class="shots" tabindex="0" role="region" aria-label="${esc(`Screenshots, ${key}`)}">${figures}</div>`;
    })
    .join("");
}

export interface Problem {
  severity: Finding["severity"];
  check: string;
  message: string;
  selector?: string;
  where: string[]; // "390px", "1280px RTL dark", ...
}

/** The same problem at several widths is one problem, seen in several places. */
/** Checks that report one page-wide cause: one problem however many widths and elements it shows on. */
const BY_CHECK = new Set(["layout.shift"]);

export function groupFindings(findings: Finding[]): Problem[] {
  const rank = { fail: 0, warn: 1, info: 2 } as const;
  const groups = new Map<string, Problem>();
  for (const f of findings) {
    const key = BY_CHECK.has(f.check) ? f.check : [f.severity, f.check, f.selector ?? "", f.message.replace(/\d+(\.\d+)?/g, "#")].join("|");
    const where = [`${f.width ?? "?"}px`, f.dir === "rtl" ? "RTL" : "", f.theme === "dark" ? "dark" : "", f.motion === "reduce" ? "reduced motion" : ""].filter(Boolean).join(" ");
    const g = groups.get(key);
    if (g) {
      if (!g.where.includes(where)) g.where.push(where);
      // The worst one speaks for the group.
      if (rank[f.severity] < rank[g.severity]) Object.assign(g, { severity: f.severity, message: f.message, selector: f.selector });
    } else groups.set(key, { severity: f.severity, check: f.check, message: f.message, selector: f.selector, where: [where] });
  }
  return [...groups.values()].sort((a, b) => rank[a.severity] - rank[b.severity] || a.check.localeCompare(b.check));
}

function findingsSection(run: Run): string {
  const problems = groupFindings(run.findings);
  if (!problems.length) return `<p class="muted">No problems found.</p>`;
  const rows = problems
    .slice(0, 300)
    .map((p) => `<tr><td class="sev ${p.severity}">${p.severity === "fail" ? "must fix" : p.severity === "warn" ? "should fix" : "note"}</td><td>${esc(p.message)}<br><code class="muted">${esc(p.check)}${p.selector ? ` · ${esc(p.selector)}` : ""}</code></td><td>${p.where.map(esc).join("<br>")}</td></tr>`)
    .join("");
  return `<div class="table" tabindex="0" role="region" aria-label="Problems"><table><thead><tr><th>Severity</th><th>What</th><th>Where</th></tr></thead><tbody>${rows}</tbody></table></div>`;
}

function seenSection(run: Run): string {
  return run.seen
    .map((s) => {
      const palette = s.colour.palette
        .map((p) => `<span class="sw"><i style="background:${esc(p.hex)}"></i><span><code>${esc(p.hex)}</code> ${Math.round(p.share * 100)}%${p.token ? ` <span class="muted">${esc(p.token)}</span>` : ""}</span></span>`)
        .join("");
      const sizes = s.typography.sizes
        .slice(0, 8)
        .map((t) => `<div style="display:flex;gap:10px;align-items:center;font-size:13px"><code style="width:56px">${t.px}px</code><div class="bar" style="flex:1"><span style="width:${Math.round(t.share * 100)}%"></span></div></div>`)
        .join("");
      const list = (items: string[]) => (items.length ? `<ul>${items.map((i) => `<li>${i}</li>`).join("")}</ul>` : `<p class="muted">None.</p>`);
      const focus = s.focus.length ? `<div class="card"><b>Where the eye lands first</b><p class="muted">Above the fold, heaviest first (size, contrast, weight, colour).</p><ol>${s.focus.map((f) => `<li>${esc(f.label)} <span class="muted">${f.kind} · ${Math.round(f.weight * 100)}</span></li>`).join("")}</ol></div>` : "";
      return `<h3>${esc(s.variant)}</h3><div class="grid">${focus}
        <div class="card"><b>Colour</b><p class="muted">Harmony: ${esc(s.colour.harmony)}</p><div class="swatches">${palette}</div>
          <p class="muted">Colours outside the tokens: ${s.colour.offToken.length ? s.colour.offToken.map((c) => `<code>${esc(c)}</code>`).join(" ") : "none"}</p>
          ${list(s.colour.lowContrast.map((c) => `Low contrast ${c.ratio}:1 (needs ${c.needs}:1) <code>${esc(c.selector)}</code>`))}</div>
        <div class="card"><b>Typography</b><p class="muted">Scale ratio ${s.typography.ratio ?? "–"} · ${s.typography.families.length} famil${s.typography.families.length === 1 ? "y" : "ies"} (${esc(s.typography.families.join(", "))}) · weights ${esc(s.typography.weights.join(", "))}</p>${sizes}
          ${list([...s.typography.longLines.map((l) => `Long lines (~${l.chars} characters) <code>${esc(l.selector)}</code>`), ...s.typography.tightLeading.map((l) => `Tight line height ${l.ratio} <code>${esc(l.selector)}</code>`)])}</div>
        <div class="card"><b>Alignment</b><p class="muted">Columns at ${s.alignment.columns.map((c) => `${c}px`).join(", ") || "–"}</p>
          ${list(s.alignment.nearMisses.map((n) => `${n.off}px off on the ${n.edge}: <code>${esc(n.a)}</code> / <code>${esc(n.b)}</code>`))}</div>
        <div class="card"><b>Rhythm</b><p class="muted">Spacing base ${s.rhythm.base ?? "4 (assumed)"}px · common gaps ${s.rhythm.gaps.slice(0, 6).map((g) => `${g.value}px×${g.count}`).join(", ") || "–"}</p>
          ${list([...s.rhythm.offScale.map((o) => `Off-scale gap ${o.gap}px <code>${esc(o.between)}</code>`), ...s.rhythm.uneven.map((u) => `Uneven gaps ${u.gaps.join("/")}px in <code>${esc(u.list)}</code>`)])}</div>
      </div>`;
    })
    .join("");
}

function diffSection(run: Run): string {
  if (!run.diffs.length) return "";
  const rows = run.diffs
    .map((d) => `<div class="card"><b>${esc(d.variant)}</b> · looks ${(d.aligned.match * 100).toFixed(1)}% like the design · ${(d.match * 100).toFixed(1)}% position for position${d.aligned.shifts.length ? ` · heights drift at ${d.aligned.shifts.map((s) => `y=${s.designY} (${s.dy > 0 ? "+" : ""}${s.dy}px)`).join(", ")}` : ""}${d.sizeMismatch ? ` · <span class="sev warn">sizes differ</span> (${d.size.actual.join("×")} vs ${d.size.expected.join("×")})` : ""}
      <div class="shots" tabindex="0" role="region" aria-label="${esc(`Built page and design, ${d.variant}`)}" style="margin-top:10px"><figure style="width:260px"><figcaption>Built</figcaption><div class="frame"><img src="${esc(d.actual)}" alt="Built page"></div></figure>
      <figure style="width:260px"><figcaption>Design</figcaption><div class="frame"><img src="${esc(d.expected)}" alt="Design"></div></figure>
      ${d.heatmap ? `<figure style="width:260px"><figcaption>Differences</figcaption><div class="frame"><img src="${esc(d.heatmap)}" alt="Difference heat map"></div></figure>` : ""}</div></div>`)
    .join("");
  return `<h2>Against the design</h2><div class="grid">${rows}</div>`;
}

function pageName(url: string): string {
  try {
    const u = new URL(url);
    return u.protocol === "file:" ? decodeURIComponent(u.pathname.split("/").filter(Boolean).slice(-2).join("/")) : `${u.host}${u.pathname === "/" ? "" : u.pathname}`;
  } catch {
    return url;
  }
}

export function writeReport(path: string, run: Run): void {
  const { verdict } = run.summary;
  const problems = groupFindings(run.findings);
  const fail = problems.filter((p) => p.severity === "fail").length;
  const warn = problems.filter((p) => p.severity === "warn").length;
  const info = problems.filter((p) => p.severity === "info").length;
  const when = new Date(run.when).toLocaleString("en-GB", { dateStyle: "medium", timeStyle: "short" });
  const html = `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>lawha check · ${esc(pageName(run.url))}</title><style>${CSS}</style></head><body>
<header><p class="muted">lawha ${esc(run.version)} · ${esc(when)}</p><h1>${esc(pageName(run.url))}</h1><p class="muted url">${esc(run.url)}</p>
<span class="verdict ${verdict}"><span class="dot"></span>${verdict === "pass" ? "Passes every required check" : `${fail} required check${fail === 1 ? "" : "s"} failing`}</span>
<div class="counts"><div class="count fail"><b>${fail}</b>must fix</div><div class="count warn"><b>${warn}</b>should fix</div><div class="count info"><b>${info}</b>notes</div><div class="count"><b>${run.summary.widths.length}</b>widths</div></div></header>
<main><h2>Problems</h2>${findingsSection(run)}${diffSection(run)}<h2>Every screen</h2>${shotsSection(run)}<h2>What the eye measured</h2>${seenSection(run)}</main></body></html>`;
  writeFileSync(path, html, "utf8");
}
