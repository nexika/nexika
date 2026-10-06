import { mkdirSync, writeFileSync } from "node:fs";
import { dirname } from "node:path";
export const DEFAULT_WIDTHS = [360, 390, 768, 1024, 1280, 1536];
export const PHONE_MAX = 767;
/** Minimal flag parser: --name value, --name=value, --flag (boolean). */
export function parseArgs(argv, booleans = []) {
    const out = { _: [] };
    for (let i = 0; i < argv.length; i++) {
        const arg = argv[i];
        if (!arg.startsWith("--")) {
            out._.push(arg);
            continue;
        }
        const [name, inline] = arg.slice(2).split("=", 2);
        if (inline !== undefined)
            out[name] = inline;
        else if (booleans.includes(name))
            out[name] = true;
        else
            out[name] = argv[++i] ?? "";
    }
    return out;
}
export function list(value, fallback) {
    if (typeof value !== "string" || !value.trim())
        return fallback;
    return value.split(",").map((v) => v.trim()).filter(Boolean);
}
export function writeJson(path, data) {
    mkdirSync(dirname(path), { recursive: true });
    writeFileSync(path, JSON.stringify(data, null, 2) + "\n", "utf8");
}
export function stamp(date = new Date()) {
    return date.toISOString().replace(/[:.]/g, "-").replace("T", "_").slice(0, 19);
}
export function round(n, digits = 2) {
    const f = 10 ** digits;
    return Math.round(n * f) / f;
}
