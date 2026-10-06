import { createHash } from "node:crypto";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { lawhaHome } from "./record.js";
/**
 * Figma access for lawha: as few calls as possible, every answer cached, every call logged.
 *
 * Starter (free) plans allow very few "Tier 1" calls (GET file, GET file nodes, GET image): 20 a
 * month on View/Collab seats, 10 a minute on Full/Dev seats. So:
 *   - the latest file version comes from the version history (Tier 2, a separate budget);
 *   - one GET nodes call fetches every selected frame, one GET image call renders all of them;
 *   - answers are cached in the project (.lawha/figma/<file>/<version>/) and reused until the file
 *     changes; a changed file is fetched again only when asked.
 * The token is read from FIGMA_TOKEN and never written anywhere.
 */
const API = "https://api.figma.com/v1";
/** https://www.figma.com/design/<key>/<name>?node-id=25-108 (also /file/, /proto/, /board/). */
export function parseUrl(url) {
    const m = url.match(/figma\.com\/(?:design|file|proto|board)\/([A-Za-z0-9]{10,64})/);
    if (!m)
        throw new Error("not a Figma file link (expected figma.com/design/<file key>/...)");
    const node = new URL(url).searchParams.get("node-id");
    return { key: m[1], node: node ? node.replace("-", ":") : null };
}
function token() {
    const t = process.env.FIGMA_TOKEN?.trim();
    if (!t)
        throw new Error("FIGMA_TOKEN is not set: create a personal access token (read-only file content) in Figma settings and export it");
    return t;
}
function logPath() {
    return join(lawhaHome(), "figma-calls.json");
}
function readLog() {
    try {
        const all = JSON.parse(readFileSync(logPath(), "utf8"));
        const cutoff = Date.now() - 62 * 86400_000;
        return Array.isArray(all) ? all.filter((c) => c.at > cutoff) : [];
    }
    catch {
        return [];
    }
}
function writeLog(log) {
    mkdirSync(lawhaHome(), { recursive: true, mode: 0o700 });
    writeFileSync(logPath(), JSON.stringify(log), { mode: 0o600 });
}
/** Tier 1 calls in the last minute and the last 30 days, for the budget line. */
export function budget() {
    const log = readLog();
    const now = Date.now();
    const tier1 = log.filter((c) => c.tier === 1);
    return {
        tier1LastMinute: tier1.filter((c) => now - c.at < 60_000).length,
        tier1Last30Days: tier1.filter((c) => now - c.at < 30 * 86400_000).length,
        calls30Days: log.filter((c) => now - c.at < 30 * 86400_000).length,
    };
}
async function call(path, tier) {
    const res = await fetch(`${API}${path}`, { headers: { "X-Figma-Token": token() } });
    const log = readLog();
    log.push({ at: Date.now(), endpoint: path.split("?")[0].replace(/\/files\/[^/]+|\/images\/[^/]+/, (s) => s.split("/").slice(0, 2).join("/") + "/:key"), tier, status: res.status });
    writeLog(log);
    if (res.status === 429) {
        const wait = res.headers.get("retry-after");
        throw new Error(`Figma rate limit reached${wait ? `: try again in ${wait} s` : ""} (plan tier ${res.headers.get("x-figma-plan-tier") ?? "unknown"})`);
    }
    if (res.status === 403)
        throw new Error("Figma refused the token for this file (403): the token needs file content read access, and the file must be yours or shared with you");
    if (res.status === 404)
        throw new Error("Figma file or node not found (404)");
    if (!res.ok)
        throw new Error(`Figma answered ${res.status}`);
    return (await res.json());
}
export function cacheDir(root, key) {
    return resolve(root, ".lawha", "figma", key);
}
function readJson(path) {
    try {
        return JSON.parse(readFileSync(path, "utf8"));
    }
    catch {
        return null;
    }
}
function saveJson(path, data) {
    mkdirSync(resolve(path, ".."), { recursive: true });
    writeFileSync(path, JSON.stringify(data));
}
/** The file's current version, from the version history (Tier 2, so it spends no Tier 1 call). */
export async function latestVersion(key) {
    const data = await call(`/files/${key}/versions?page_size=1`, 2);
    const v = data.versions?.[0];
    if (!v)
        throw new Error("Figma returned no version for this file");
    return { id: v.id, created: v.created_at };
}
/** Pages and their top-level frames (GET file with depth=2, one Tier 1 call), cached by version. */
export async function outline(root, ref, refresh = false) {
    const dir = cacheDir(root, ref.key);
    const version = await latestVersion(ref.key);
    const cached = join(dir, version.id, "outline.json");
    let data = refresh ? null : readJson(cached);
    const hit = !!data;
    if (!data) {
        data = await call(`/files/${ref.key}?depth=2`, 1);
        saveJson(cached, data);
    }
    saveJson(join(dir, "latest.json"), { version: version.id, created: version.created });
    const frames = [];
    for (const page of data.document.children ?? []) {
        for (const n of page.children ?? []) {
            const b = n.absoluteBoundingBox;
            frames.push({ id: n.id, name: n.name, type: n.type, page: page.name, width: Math.round(b?.width ?? 0), height: Math.round(b?.height ?? 0) });
        }
    }
    return { name: data.name, version: version.id, cached: hit, frames };
}
function idsKey(ids) {
    return createHash("sha1").update([...ids].sort().join(",")).digest("hex").slice(0, 10);
}
async function download(url, path) {
    const res = await fetch(url);
    if (!res.ok)
        throw new Error(`could not download a rendered image (${res.status})`);
    mkdirSync(resolve(path, ".."), { recursive: true });
    writeFileSync(path, Buffer.from(await res.arrayBuffer()));
}
/** Full trees of the given frames (1 call), their PNG renders (1 call) and the photos they use (1 Tier 2 call). */
export async function fetchFrames(root, ref, ids, opts = {}) {
    if (!ids.length)
        throw new Error("no frames given");
    const version = (await latestVersion(ref.key)).id;
    const dir = join(cacheDir(root, ref.key), version);
    const tag = idsKey(ids);
    const scale = opts.scale ?? 1;
    let calls = 1; // the version lookup
    const nodesPath = join(dir, `nodes-${tag}.json`);
    if (opts.refresh || !existsSync(nodesPath)) {
        const data = await call(`/files/${ref.key}/nodes?ids=${encodeURIComponent(ids.join(","))}&geometry=paths`, 1);
        saveJson(nodesPath, data);
        calls++;
    }
    const images = {};
    const missing = ids.filter((id) => !existsSync(join(dir, "frames", `${id.replace(/:/g, "-")}@${scale}x.png`)));
    if (missing.length || opts.refresh) {
        const want = opts.refresh ? ids : missing;
        const data = await call(`/images/${ref.key}?ids=${encodeURIComponent(want.join(","))}&format=png&scale=${scale}`, 1);
        calls++;
        for (const [id, url] of Object.entries(data.images ?? {})) {
            if (url)
                await download(url, join(dir, "frames", `${id.replace(/:/g, "-")}@${scale}x.png`));
        }
    }
    for (const id of ids) {
        const path = join(dir, "frames", `${id.replace(/:/g, "-")}@${scale}x.png`);
        if (existsSync(path))
            images[id] = path;
    }
    // Photos and other image fills: their real files, not crops of the frame render.
    const fills = {};
    const nodes = readJson(nodesPath);
    const refs = new Set();
    const collect = (n) => {
        const node = n;
        for (const f of node.fills ?? [])
            if (f.type === "IMAGE" && f.imageRef)
                refs.add(f.imageRef);
        for (const c of node.children ?? [])
            collect(c);
    };
    for (const v of Object.values(nodes?.nodes ?? {}))
        collect(v.document);
    const needed = [...refs].filter((r) => !existsSync(join(dir, "fills", `${r}.img`)));
    if (needed.length) {
        const data = await call(`/files/${ref.key}/images`, 2);
        calls++;
        for (const r of needed) {
            const url = data.meta?.images?.[r];
            if (url)
                await download(url, join(dir, "fills", `${r}.img`));
        }
    }
    for (const r of refs) {
        const path = join(dir, "fills", `${r}.img`);
        if (existsSync(path))
            fills[r] = path;
    }
    return { version, dir, nodes: nodesPath, images, fills, calls };
}
/** SVG exports of icons (one Tier 1 call for all of them), cached by file version. */
export async function svgExports(root, ref, version, ids) {
    const dir = join(cacheDir(root, ref.key), version, "svg");
    const files = {};
    const path = (id) => join(dir, `${id.replace(/[:;]/g, "-")}.svg`);
    const missing = ids.filter((id) => !existsSync(path(id)));
    let calls = 0;
    if (missing.length) {
        const data = await call(`/images/${ref.key}?ids=${encodeURIComponent(missing.join(","))}&format=svg&svg_outline_text=false&svg_simplify_stroke=true`, 1);
        calls++;
        for (const [id, url] of Object.entries(data.images ?? {}))
            if (url)
                await download(url, path(id));
    }
    for (const id of ids)
        if (existsSync(path(id)))
            files[id] = path(id);
    return { files, calls };
}
